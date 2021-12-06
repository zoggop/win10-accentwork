import math
from urllib.request import urlopen, Request
from io import BytesIO
from PIL import Image, ImageOps
import sys
import subprocess
import os
import re
import random
import coloraide
from winreg import *
import datetime
import concurrent.futures
import geocoder
import pycountry
import numpy as np

backgroundLightnessA = 25
backgroundLightnessB = 75
randomBackgroundLightness = True
minBackgroundLightnessA = 17
maxBackgroundLightnessA = 33
backgroundDeltaE = 35 # the desired delta e color difference between the two background hues
useRandomHue = False # instead of the accent color, pick a random hue
useAccentMaxChroma = True # limit chroma to the accent color
maxChroma = 134 # maximum chroma (if not using the accent color's maximum chroma)
minShades = 24 # how many shades of grey must be in the test tile to be accepted

# smurl = r"http://a.tile.openstreetmap.org/{0}/{1}/{2}.png"
smurl = r"http://services.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{0}/{2}/{1}"
CurrentZoom = None

degreesPerZ = 90 / (math.pi / 2)

def uniformlyRandomLatLon():
	z = random.randint(-10000000, 10000000) / 10000000
	lat = math.asin(z) * degreesPerZ
	lon = random.randint(-18000000, 18000000) / 100000
	return lat, lon

def angleDist(a, b):
	return abs(((b - a) + 180) % 360 - 180)

def lch_to_rgb(lightness, chroma, hue):
	c = coloraide.Color('lch-d65', [lightness, chroma, hue]).convert('srgb')
	if c.in_gamut():
		return c
	return None

def rgb_to_lch(red, green, blue):
	c = coloraide.Color('srgb', [red/255, green/255, blue/255]).convert('lch-d65')
	if c.in_gamut():
		return c
	return None

def highestChromaColor(lightness, hue):
	for chroma in range(maxChroma, 0, -1):
		c = lch_to_rgb(lightness, chroma, hue)
		if not c is None:
			if chroma < maxChroma:
				decaChroma = chroma + 0.9
				while decaChroma >= chroma:
					dc = lch_to_rgb(lightness, decaChroma, hue)
					if not dc is None:
						centiChroma = decaChroma + 0.09
						while centiChroma >= decaChroma:
							cc = lch_to_rgb(lightness, centiChroma, hue)
							if not cc is None:
								return cc
							centiChroma -= 0.01
					decaChroma -= 0.1
			else:
				return c

def hexToIntDwordColor(hexString):
	convertable = '0xff' + hexString[4:] + hexString[2:4] + hexString[:2]
	return int(convertable, 16)

def intDwordColorToRGB(dwordInt):
	reverse = hex(dwordInt)
	r = int('0x' + reverse[8:], 16)
	g = int('0x' + reverse[6:8], 16)
	b = int('0x' + reverse[4:6], 16)
	return [r, g, b]

def deg2num(lat_deg, lon_deg, zoom):
  lat_rad = math.radians(lat_deg)
  n = 2.0 ** zoom
  xtile = int((lon_deg + 180.0) / 360.0 * n)
  ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)
  return (xtile, ytile)
  
def num2deg(xtile, ytile, zoom):
  n = 2.0 ** zoom
  lon_deg = xtile / n * 360.0 - 180.0
  lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * ytile / n)))
  lat_deg = math.degrees(lat_rad)
  return (lat_deg, lon_deg)

def imgHasContrast(bwT):
	colors = bwT.getcolors()
	shades = len(colors)
	contrast = colors[-1][1] - colors[0][1]
	print("contrast:", contrast, "shades:", shades)
	if contrast == 153 and shades == 65:
		return None # contrast 153 with 65 shades is the "tile not available" tile
	else:
		if shades < minShades:
			return False
		else:
			return True

def manualGrade(bwImage, interpolation):
	grade = [(int(interpolation(l/255).red * 255), int(interpolation(l/255).green * 255), int(interpolation(l/255).blue * 255)) for l in range(256)]
	print(grade[0], grade[127], grade[255])
	colorImage = Image.new('RGB', bwImage.size)
	px = bwImage.load()
	for x in range(0, bwImage.size[0]):
		for y in range(0, bwImage.size[1]):
			l = px[x, y]
			colorImage.putpixel((x, y), grade[l])
	return colorImage

def spoof(url): # this function pretends not to be a Python script
	req = Request(url) # start request
	req.add_header('User-agent','Anaconda 3') # add user agent to request
	# req.add_header('Desired-tile-form', 'BW')
	fh = urlopen(req)
	im_data = BytesIO(fh.read()) # get image
	fh.close() # close url
	img = Image.open(im_data) # open image with PIL
	return img

def getOneTile(tile):
	try:
		imgurl = smurl.format(CurrentZoom, tile.get('x'), tile.get('y'))
		# print("Opening: " + imgurl)
		img = spoof(imgurl)
		img = img.convert('L')
		tile['img'] = img
	except: 
		print("Couldn't download image")

def getImageCluster(lat_deg, lon_deg, xTileNum, yTileNum, zoom):
	global CurrentZoom
	centerX, centerY = deg2num(lat_deg, lon_deg, zoom)
	xmin = centerX - math.ceil(xTileNum/2)
	xmax = centerX + math.floor(xTileNum/2)
	ymin = centerY - math.ceil(yTileNum/2)
	ymax = centerY + math.floor(yTileNum/2)
	# xmin, ymax = deg2num(lat_deg - delta_lat, lon_deg - delta_long, zoom)
	# xmax, ymin = deg2num(lat_deg + delta_lat, lon_deg + delta_long, zoom)
	CurrentZoom = zoom
	# test the corners for image data (make sure we're not in the ocean)
	tests = [
		# {'x':xmin, 'y':ymin},
		# {'x':xmax, 'y':ymin},
		# {'x':xmin, 'y':ymax},
		# {'x':xmax, 'y':ymax},
		{'x':centerX, 'y':centerY}
	]
	with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
		executor.map(getOneTile, tests)
	for tile in tests:
		img = tile.get('img')
		if img is None:
			return None
		else:
			contrast = imgHasContrast(img)
			if not contrast:
				return contrast
	# get all the tiles
	tiles = []
	for xtile in range(xmin, xmax+1):
		for ytile in range(ymin, ymax+1):
			tiles.append({'x':xtile, 'y':ytile})
	with concurrent.futures.ThreadPoolExecutor(max_workers=len(tiles)) as executor:
		executor.map(getOneTile, tiles)
	# paste them into the full image
	Cluster = Image.new('L',((xmax-xmin+1)*256-1,(ymax-ymin+1)*256-1))
	print(xmin, xmax, ymin, ymax, Cluster.size)
	for tile in tiles:
		xtile = tile.get('x')
		ytile = tile.get('y')
		img = tile.get('img')
		if img == None:
			return None
		Cluster.paste(img, box=((xtile-xmin)*256 ,  (ytile-ymin)*255))
	return Cluster

def hueSwapMaybe(lightnessA, hueA, lightnessB, hueB):
	lAhA = highestChromaColor(lightnessA, hueA)
	lBhB = highestChromaColor(lightnessB, hueB)
	lAhB = highestChromaColor(lightnessA, hueB)
	lBhA = highestChromaColor(lightnessB, hueA)
	if random.randint(0,1) == 1:
		print("straight hues")
		a = lAhB
		b = lBhA
	else:
		print("swapped hues")
		a = lAhA
		b = lBhB
	return a, b

def findColorPairByDeltaE(startHue, deltaE, lightnessA, lightnessB):
	testLightness = (lightnessA + lightnessB) / 2
	highestDE, highestHues = None, None
	for hAdd in range(1, 180):
		hA = (startHue - hAdd) % 360
		hB = (startHue + hAdd) % 360
		testA = highestChromaColor(testLightness, hA)
		testB = highestChromaColor(testLightness, hB)
		chroma = min(testA.convert('lch-d65').c, testB.convert('lch-d65').c)
		testA = lch_to_rgb(testLightness, chroma, hA)
		testB = lch_to_rgb(testLightness, chroma, hB)
		de = testA.delta_e(testB, method='2000')
		if de >= deltaE:
			highestHues = [hA, hB]
			break
		if highestDE == None or de > highestDE:
			highestDE = de
			highestHues = [hA, hB]
	print(highestHues, angleDist(highestHues[0], highestHues[1]))
	return hueSwapMaybe(lightnessA, highestHues[0], lightnessB, highestHues[1])

def locationName(latLon):
	for provider in ['arcgis', 'osm', 'geocodefarm']:
		func = getattr(geocoder, provider)
		try:
			g = func(latLon, method='reverse')
		except:
			print("could not get location with", provider)
		finally:
			output = g.address
			s = {'address':g.address}
			print(provider)
			if g.raw != None:
				address = g.raw.get('address') or g.raw.get('ADDRESS')
				if address != None:
					# print(address)
					for k in ['county', 'state', 'country', 'County', 'State', 'Country', 'CountryCode', 'Region', 'Subregion', 'LongLabel', 'Match_addr', 'admin_2', 'admin_1', ]:
						v = address.get(k)
						if v != None and v != '':
							# print(k.upper(), v)
							s[k.lower()] = v
			if s.get('country') == None and s.get('countrycode') != None:
				s['country'] = pycountry.countries.get(alpha_3=s.get('countrycode')).name
			if s.get('county') and s.get('state') and s.get('country'):
				output = '{}, {}, {}'.format(s.get('county'), s.get('state'), s.get('country'))
			elif s.get('subregion') and s.get('region') and s.get('country'):
				output = '{}, {}, {}'.format(s.get('subregion'), s.get('region'), s.get('country'))
			elif s.get('admin_2') and s.get('admin_1') and s.get('country'):
				output = '{}, {}, {}'.format(s.get('admin_2'), s.get('admin_1'), s.get('country'))
			elif s.get('state') and s.get('country'):
				output = '{}, {}'.format(s.get('state'), s.get('country'))
			elif s.get('region') and s.get('country'):
				output = '{}, {}'.format(s.get('region'), s.get('country'))
			elif s.get('admin_1') and s.get('country'):
				output = '{}, {}'.format(s.get('admin_1'), s.get('country'))
			elif s.get('county') and s.get('country'):
				output = '{}, {}'.format(s.get('county'), s.get('country'))
			elif s.get('subregion') and s.get('country'):
				output = '{}, {}'.format(s.get('subregion'), s.get('country'))
			elif s.get('admin_2') and s.get('country'):
				output = '{}, {}'.format(s.get('admin_2'), s.get('country'))
			elif s.get('longlabel'):
				output = s.get('longlabel')
			elif s.get('match_addr'):
				output = s.get('match_addr')
			if output != None and output != '':
				return output


if __name__ == '__main__':

	attemptNum = 0
	a = None
	while not a and attemptNum < 50:
		# centerLatLon = (random.randrange(-9000, 9000) / 100, random.randrange(-18000, 18000) / 100)
		# lat, lon = num2deg(random.randint(0,1048576), random.randint(0,1048576), 20)
		lat, lon = uniformlyRandomLatLon()
		centerLatLon = [lat, lon]
		zooms = [*range(10, 14)]
		while len(zooms) != 0:
			zoom = zooms.pop(random.randrange(len(zooms)))
			a = getImageCluster(centerLatLon[0], centerLatLon[1], 8, 5, zoom)
			if not a is None:
				if a == False:
					# got image okay but it's too low contrast, choose a new location
					break
				print("zoom:", zoom)
				break
		print(centerLatLon, a)
		attemptNum += 1
	if attemptNum == 50:
		exit()

	bw = ImageOps.equalize(a)
	# contrasted = ImageOps.autocontrast(eq, cutoff=1, ignore=None)
	# bw.save(os.path.expanduser('~/Desktop/bw.png'))

	if useRandomHue:
		hue = random.randint(0, 359)
	else:
		# get current accent color hue
		key = OpenKey(HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent', 0, KEY_ALL_ACCESS)
		val = QueryValueEx(key, "AccentColorMenu")
		rgbVal = intDwordColorToRGB(val[0])
		lchC = rgb_to_lch(rgbVal[0], rgbVal[1], rgbVal[2])
		hue = lchC.h
		if useAccentMaxChroma:
			maxChroma = int(lchC.c)
	print('hue', hue)

	if randomBackgroundLightness:
		backgroundLightnessA = random.randint(minBackgroundLightnessA, maxBackgroundLightnessA)
		backgroundLightnessB = 100 - backgroundLightnessA

	bgAC, bgBC = findColorPairByDeltaE(hue, backgroundDeltaE, backgroundLightnessA, backgroundLightnessB)
	# bgAC, bgBC = colorPairByHueDiff(hue, backgroundHueDiff, backgroundLightnessA, backgroundLightnessB)
	print(bgAC.convert('lch-d65'))
	print(bgBC.convert('lch-d65'))

	print("delta e", bgAC.delta_e(bgBC, method='2000'))
	i = bgAC.interpolate(bgBC, space='lch-d65')

	# startDT = datetime.datetime.now()
	# grade = [(int(i(l/2).red * 255), int(i(l/2).green * 255), int(i(l/2).blue * 255)) for l in range(3)]
	# colorized = ImageOps.colorize(bw, grade[0], grade[2], mid=grade[1])
	# print(datetime.datetime.now() - startDT, "done PIL colorizing")
	startDT = datetime.datetime.now()
	manually = manualGrade(bw, i)
	print(datetime.datetime.now() - startDT, "done manually colorizing")
	# colorized.save(os.path.expanduser('~/Desktop/pil.png'))
	manually.save(os.path.expanduser('~/Desktop/manually.png'))

	fitted = ImageOps.fit(manually, (1920,1080))
	fitted.save(os.path.expanduser('~/AppData/Roaming/Microsoft/Windows/Themes/TranscodedWallpaper'), format='PNG')
	# create path if not existant
	if not os.path.exists(os.path.expanduser('~/Pictures/autowalls')):
		os.makedirs(os.path.expanduser('~/Pictures/autowalls'))
	manually.save(os.path.expanduser('~/Pictures/autowalls/topobg.png'), format='PNG')
	place = locationName(centerLatLon)
	print(place)
	fp = open(os.path.expanduser('~/Pictures/autowalls/topobg_location.txt'), 'w')
	fp.write(place)
	fp.close()
	keyVal = r'Control Panel\Desktop'
	try:
	    key = OpenKey(HKEY_CURRENT_USER, keyVal, 0, KEY_ALL_ACCESS)
	except:
	    key = CreateKey(HKEY_CURRENT_USER, keyVal)
	SetValueEx(key, "Wallpaper", 0, REG_SZ, os.path.expanduser('~/Pictures/autowalls/topobg.png'))
	CloseKey(key)
	subprocess.run(['rundll32.exe', 'user32.dll,', 'UpdatePerUserSystemParameters'])
	subprocess.run(['rundll32.exe', 'user32.dll,', 'UpdatePerUserSystemParameters'])