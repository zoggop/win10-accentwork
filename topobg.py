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

backgroundLightnessA = 25
backgroundLightnessB = 75
backgroundHueAdd = 120
maxChroma = 134
avoidOcean = True

# smurl = r"http://a.tile.openstreetmap.org/{0}/{1}/{2}.png"
smurl = r"http://services.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{0}/{2}/{1}"
CurrentZoom = None

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
	# print(tile.size[0], tile.size[1])
	# bwT.convert('L')
	lMin, lMax = None, None
	lVals = {}
	lCount = 0
	for x in range(0, bwT.size[0]):
		for y in range(0, bwT.size[1]):
			l = bwT.getpixel((x, y))
			if lMin == None or l < lMin:
				lMin = l
			if lMax == None or l > lMax:
				lMax = l
			if lVals.get(l) == None:
				lCount += 1
				lVals[l] = True
	contrast = lMax - lMin
	print("contrast:", contrast, "shades:", lCount)
	return contrast > 10 and lCount > 10 and not (contrast == 153 and lCount == 65)

def manualGrade(bwImage, interpolation):
	grade = [(int(interpolation(l/255).red * 255), int(interpolation(l/255).green * 255), int(interpolation(l/255).blue * 255)) for l in range(256)]
	print(grade[0], grade[127], grade[255])
	colorImage = Image.new('RGB', bwImage.size)
	for x in range(0, bwImage.size[0]):
		for y in range(0, bwImage.size[1]):
			l = bwImage.getpixel((x, y))
			colorImage.putpixel((x, y), grade[l])
	return colorImage

def pollSensor(entry):
	sid = entry['index']
	entry['sensor'] = Sensor(sid)

def pollAllSensors(entries):
	startDT = datetime.datetime.now()
	with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
		executor.map(pollSensor, entries)
	print("downloaded individual sensor data in", datetime.datetime.now() - startDT)

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
		{'x':xmin, 'y':ymin},
		{'x':xmax, 'y':ymin},
		{'x':xmin, 'y':ymax},
		{'x':xmax, 'y':ymax},
	]
	with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
		executor.map(getOneTile, tests)
	for tile in tests:
		img = tile.get('img')
		if not img or not imgHasContrast(img):
			return None
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
	place = None
	while (a is None or place is None or (place != None and avoidOcean and 'ocean' in place.lower())) and attemptNum < 50:
		centerLatLon = (random.randrange(-9000, 9000) / 100, random.randrange(-18000, 18000) / 100)
		a = getImageCluster(centerLatLon[0], centerLatLon[1], 8, 5, 11)
		if a != None:
			place = locationName(centerLatLon)
		print(centerLatLon, a)
		attemptNum += 1
	if attemptNum == 50:
		exit()
	print(place)

	# bw = contrasted.convert('L')
	bw = ImageOps.equalize(a)
	# contrasted = ImageOps.autocontrast(eq, cutoff=1, ignore=None)
	# bw = eq.convert('L')
	# contrasted.save(os.path.expanduser('~/Desktop/contrasted.png'))
	a.save(os.path.expanduser('~/Desktop/a.png'))
	# eq.save(os.path.expanduser('~/Desktop/eq.png'))
	bw.save(os.path.expanduser('~/Desktop/bw.png'))

	# get current accent color hue
	key = OpenKey(HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent', 0, KEY_ALL_ACCESS)
	val = QueryValueEx(key, "AccentColorMenu")
	rgbVal = intDwordColorToRGB(val[0])
	lchC = rgb_to_lch(rgbVal[0], rgbVal[1], rgbVal[2])
	hue = lchC.h
	maxChroma = int(lchC.c)

	bgAHue = (hue - backgroundHueAdd) % 360
	bgBHue = (hue + backgroundHueAdd) % 360
	print("background hues", bgAHue, bgBHue)
	lAhA = highestChromaColor(backgroundLightnessA, bgAHue)
	lBhB = highestChromaColor(backgroundLightnessB, bgBHue)
	lAhB = highestChromaColor(backgroundLightnessA, bgBHue)
	lBhA = highestChromaColor(backgroundLightnessB, bgAHue)
	print(lAhA.convert('lch-d65').c, lAhB.convert('lch-d65').c)
	print(lBhB.convert('lch-d65').c, lBhA.convert('lch-d65').c)
	print((lAhA.convert('lch-d65').c + lBhB.convert('lch-d65').c), (lAhB.convert('lch-d65').c + lBhA.convert('lch-d65').c))
	if (lAhB.convert('lch-d65').c + lBhA.convert('lch-d65').c) > (lAhA.convert('lch-d65').c + lBhB.convert('lch-d65').c):
		bgAC = lAhB
		bgBC = lBhA
	else:
		bgAC = lAhA
		bgBC = lBhB

	i = bgAC.interpolate(bgBC, space='lch-d65')

	# startDT = datetime.datetime.now()
	# grade = [(int(i(l/2).red * 255), int(i(l/2).green * 255), int(i(l/2).blue * 255)) for l in range(3)]
	# colorized = ImageOps.colorize(bw, grade[0], grade[2], grade[1])
	# print(datetime.datetime.now() - startDT, "done PIL colorizing")
	startDT = datetime.datetime.now()
	manually = manualGrade(bw, i)
	print(datetime.datetime.now() - startDT, "done manually colorizing")
	# colorized.save(os.path.expanduser('~/Desktop/colorized.png'))
	manually.save(os.path.expanduser('~/Desktop/manually.png'))

	fitted = ImageOps.fit(manually, (1920,1080))
	fitted.save(os.path.expanduser('~/Desktop/fitted.png'))
	fitted.save(os.path.expanduser('~/AppData/Roaming/Microsoft/Windows/Themes/TranscodedWallpaper'), format='PNG')
	# create path if not existant
	if not os.path.exists(os.path.expanduser('~/Pictures/autowalls')):
		os.makedirs(os.path.expanduser('~/Pictures/autowalls'))
	manually.save(os.path.expanduser('~/Pictures/autowalls/topobg.png'), format='PNG')
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