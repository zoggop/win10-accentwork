import math
from urllib.request import urlopen, Request
from io import BytesIO
from PIL import Image, ImageOps, ImageFilter
import sys
if sys.platform == 'win32':
	from winreg import *
	import subprocess
import os
import random
import coloraide
import concurrent.futures
from screeninfo import get_monitors

identifyLocation = True # get a name for the coordinates of the image?
backgroundLightnessA = 25
backgroundLightnessB = 75
randomBackgroundLightness = True # overrides backgroundLightnessA and backgroundLightnessB, using the min and max below
minBackgroundLightnessA = 17 # (lightnessB will just be 100 minus the randomly chosen lightnessA)
maxBackgroundLightnessA = 33
backgroundDeltaE = 35 # the desired delta e color difference between the two background hues
useAccentHue = True # use the accent color's hue, if available, otherwise random
useAccentMaxChroma = True # limit chroma to the accent color
minZoom = 11 # minimum zoom level of tiles
maxZoom = 15 # maximum zoom level of tiles
maxChroma = 134 # maximum chroma (if not using the accent color's maximum chroma)
minShades = 15 # how many shades of grey must be in the test tile to be accepted

smurl = r"http://services.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{0}/{2}/{1}"
CurrentZoom = None
CurrentGrade = None

degreesPerZ = 90 / (math.pi / 2)

locStruct = [
		['city', 'locality', 'municipality', 'town', 'village'],
		['county', 'admin_2', 'subregion'],
		['state', 'admin_1', 'region', 'territory'],
		['country'],
		['longlabel', 'match_addr', 'address']] # fallbacks

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
	if contrast == 153 and shades == 65:
		return None # contrast 153 with 65 shades is the "tile not available" tile
	else:
		print("contrast:", contrast, "shades:", shades)
		if shades < minShades:
			return False
		else:
			return True

def colorComponentFloatToChanceList(componentFloat):
	component = componentFloat * 255
	down = math.floor(component)
	up = math.ceil(component)
	upChances = math.floor((component - down) * 10)
	chances = []
	for i in range(upChances):
		chances.append(up)
	for i in range(10 - upChances):
		chances.append(down)
	return chances

def gradeFunc(v):
	return CurrentGrade[v]

def colorizeWithInterpolation(bwImage, interpolation):
	global CurrentGrade
	redGrade = [int(interpolation(l/255).red * 255) for l in range(256)]
	greenGrade = [int(interpolation(l/255).green * 255) for l in range(256)]
	blueGrade = [int(interpolation(l/255).blue * 255) for l in range(256)]
	CurrentGrade = redGrade
	redImage = Image.eval(bwImage, gradeFunc)
	CurrentGrade = greenGrade
	greenImage = Image.eval(bwImage, gradeFunc)
	CurrentGrade = blueGrade
	blueImage = Image.eval(bwImage, gradeFunc)
	return Image.merge('RGB', (redImage, greenImage, blueImage))

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

def getTiles(tiles):
	with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
		executor.map(getOneTile, tiles)

def getImageCluster(lat_deg, lon_deg, xTileNum, yTileNum, zoom, rotation):
	global CurrentZoom
	centerX, centerY = deg2num(lat_deg, lon_deg, zoom)
	if rotation == 1 or rotation == 3:
		# to rotate 90 or 270 degrees, switch the dimensions so that the right dimensions come out after rotation
		xtn = xTileNum+0
		xTileNum = yTileNum+0
		yTileNum = xtn
	xmin = centerX - math.ceil(xTileNum/2)
	xmax = centerX + math.floor(xTileNum/2) - 1
	ymin = centerY - math.ceil(yTileNum/2)
	ymax = centerY + math.floor(yTileNum/2) - 1
	# xmin, ymax = deg2num(lat_deg - delta_lat, lon_deg - delta_long, zoom)
	# xmax, ymin = deg2num(lat_deg + delta_lat, lon_deg + delta_long, zoom)
	CurrentZoom = zoom
	# test the center for image data (make sure we're not in the ocean)
	testTile = {'x':centerX, 'y':centerY}
	getOneTile(testTile)
	img = testTile.get('img')
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
	getTiles(tiles)
	# paste them into the full image
	Cluster = Image.new('L',((xmax-xmin+1)*256-1,(ymax-ymin+1)*256-1))
	print(xmin, xmax, ymin, ymax, Cluster.size)
	for tile in tiles:
		xtile = tile.get('x')
		ytile = tile.get('y')
		img = tile.get('img')
		if img is None:
			return None
		Cluster.paste(img, box=((xtile-xmin)*256 ,  (ytile-ymin)*255))
	if rotation == 1:
		return Cluster.transpose(Image.ROTATE_90)
	elif rotation == 2:
		return Cluster.transpose(Image.ROTATE_180)
	elif rotation == 3:
		return Cluster.transpose(Image.ROTATE_270)
	return Cluster

def hueSwapMaybe(lightnessA, hueA, lightnessB, hueB):
	lAhA = highestChromaColor(lightnessA, hueA)
	lBhB = highestChromaColor(lightnessB, hueB)
	lAhB = highestChromaColor(lightnessA, hueB)
	lBhA = highestChromaColor(lightnessB, hueA)
	if random.randint(0,1) == 1:
		# print("straight hues")
		a = lAhB
		b = lBhA
	else:
		# print("swapped hues")
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

def latinOnly(st):
	if st is None:
		print("st is None")
		return False
	try:
		st.encode('latin1')
	except UnicodeEncodeError:
		return False
	return True

def nameFromData(s):
	output = ''
	if s.get('country') == None and s.get('countrycode') != None:
		s['country'] = pycountry.countries.get(alpha_3=s.get('countrycode')).name
	strings = {}
	l = 0
	for level in locStruct:
		l += 1
		if l == 5 and output != '':
			break
		for k in level:
			v = s.get(k)
			if not v is None and v != '':
				if strings.get(v) is None:
					if l > 1:
						output = output + ', '
					output = output + v
					strings[v] = True
					break
	if output == '':
		return None
	else:
		return output

def locationName(latLon):
	s = {}
	latinS = {}
	for provider in ['arcgis', 'osm', 'geocodefarm']:
		func = getattr(geocoder, provider)
		try:
			g = func(latLon, method='reverse')
		except:
			print("could not get location with", provider)
		finally:
			if latinOnly(g.address) and latinS.get('address') is None:
				latinS['address'] = g.address
			if s.get('address') is None:
				s['address'] = g.address
			# print(provider)
			if g.raw != None:
				a = g.raw.get('address') or g.raw.get('ADDRESS')
				if a != None:
					address = {}
					for k in a.keys():
						address[k.lower()] = a.get(k)
					# print(address)
					for level in locStruct:
						for k in level:
							v = address.get(k)
							if not v is None and v != '':
								if s.get(k) is None:
									s[k] = v
								if latinS.get(k) is None and latinOnly(v):
									latinS[k] = v
	return nameFromData(s), nameFromData(latinS)


if __name__ == '__main__':

	# get screen size
	maxWidth, maxHeight = None, None
	for m in get_monitors():
		if maxWidth == None or m.width > maxWidth:
			maxWidth = m.width
		if maxHeight == None or m.height > maxHeight:
			maxHeight = m.height
	widthInTiles = math.ceil((maxWidth + 1) / 256)
	heightInTiles = math.ceil((maxHeight + 1) / 256)


	if len(sys.argv) > 4:
		rotation = int(sys.argv[4])
	else:
		rotation = random.randint(0, 3)
	print("rotation:", rotation)
	attemptNum = 0
	a = None
	while not a and attemptNum < 50:
		if attemptNum == 0 and len(sys.argv) > 2:
			lat, lon = float(sys.argv[1]), float(sys.argv[2])
		else:
			lat, lon = uniformlyRandomLatLon()
		centerLatLon = [lat, lon]
		triedSpecifiedZoom = False
		zooms = [*range(minZoom, maxZoom+1)]
		while len(zooms) != 0:
			if len(sys.argv) > 3 and not triedSpecifiedZoom:
				zoom = int(sys.argv[3])
				triedSpecifiedZoom = True
			else:
				zoom = zooms.pop(random.randrange(len(zooms)))
			a = getImageCluster(centerLatLon[0], centerLatLon[1], widthInTiles, heightInTiles, zoom, rotation)
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

	if useAccentHue == True and sys.platform == 'win32':
		# get current accent color hue
		key = OpenKey(HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent', 0, KEY_ALL_ACCESS)
		val = QueryValueEx(key, "AccentColorMenu")
		rgbVal = intDwordColorToRGB(val[0])
		lchC = rgb_to_lch(rgbVal[0], rgbVal[1], rgbVal[2])
		hue = lchC.h
		if useAccentMaxChroma:
			maxChroma = int(lchC.c)
	else:
		hue = random.randint(0, 359)
	print('hue', hue)

	if randomBackgroundLightness:
		backgroundLightnessA = random.randint(minBackgroundLightnessA, maxBackgroundLightnessA)
		backgroundLightnessB = 100 - backgroundLightnessA

	bgAC, bgBC = findColorPairByDeltaE(hue, backgroundDeltaE, backgroundLightnessA, backgroundLightnessB)
	# bgAC, bgBC = colorPairByHueDiff(hue, backgroundHueDiff, backgroundLightnessA, backgroundLightnessB)
	print(bgAC.convert('lch-d65'))
	print(bgBC.convert('lch-d65'))
	print("delta e", bgAC.delta_e(bgBC, method='2000'))

	# colorize greyscale image
	i = bgAC.interpolate(bgBC, space='lch-d65')
	colorized = colorizeWithInterpolation(bw, i)

	# create path if not existant
	if not os.path.exists(os.path.expanduser('~/color_out_of_earth')):
		os.makedirs(os.path.expanduser('~/color_out_of_earth'))

	# fit image to background size and save it
	fitted = ImageOps.fit(colorized, (maxWidth,maxHeight))
	fitted.save(os.path.expanduser('~/color_out_of_earth/background.png'))
	print(os.path.expanduser('~/color_out_of_earth/background.png'), 'saved')

	if sys.platform == 'win32':
		# set windows background
		fitted.save(os.path.expanduser('~/AppData/Roaming/Microsoft/Windows/Themes/TranscodedWallpaper'), format='PNG')
		keyVal = r'Control Panel\Desktop'
		try:
			key = OpenKey(HKEY_CURRENT_USER, keyVal, 0, KEY_ALL_ACCESS)
		except:
			key = CreateKey(HKEY_CURRENT_USER, keyVal)
		SetValueEx(key, "Wallpaper", 0, REG_SZ, os.path.expanduser('~/color_out_of_earth/background.png'))
		CloseKey(key)
		subprocess.run(['rundll32.exe', 'user32.dll,', 'UpdatePerUserSystemParameters'])
		subprocess.run(['rundll32.exe', 'user32.dll,', 'UpdatePerUserSystemParameters'])

	if identifyLocation == True:
		import geocoder
		import pycountry
		name, latinName = locationName(centerLatLon)
		nameText = name or ''
		print(name)
		if latinName != name:
			nameText = nameText + "\n" + (latinName or '')
			print(latinName)
		fp = open(os.path.expanduser('~/color_out_of_earth/location.txt'), 'w', encoding='utf8')
		fp.write(nameText)
		fp.close()
		print(os.path.expanduser('~/color_out_of_earth/location.txt'), 'saved')