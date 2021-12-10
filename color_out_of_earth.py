import math
from urllib.request import urlopen, Request
from io import BytesIO
from PIL import Image, ImageOps
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
languageCode = 'en'
backgroundLightnessA = 25
backgroundLightnessB = 75
randomBackgroundLightness = True # overrides backgroundLightnessA and backgroundLightnessB, using the min and max below
minBackgroundLightnessA = 17
maxBackgroundLightnessA = 33
lightnessCeiling = 90 # lightnessB will be lightnessCeiling minus the randomly chosen lightnessA
backgroundDeltaE = 38 # the desired delta e color difference between the two background hues
useAccentHue = False # use the accent color's hue, if available, otherwise random
useAccentMaxChroma = True # limit chroma to the accent color, if available
maxChroma = 134 # maximum chroma (if not using the accent color's maximum chroma)
minShades = 5 # how many colors must be in the test tile to be accepted
maxShades = 16777216 # above this many colors in the test tile will not be accepted

# x is 1, y is 2, z is 0
earthURL = r"http://services.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{0}/{2}/{1}"
marsURL = r"https://s3.us-east-2.amazonaws.com/opmmarstiles/hillshade-tiles/{0}/{1}/{2}.png"
xyzURLspecs = [
	{'url':earthURL, 'name':'Earth',
	'minZoom':11, 'maxZoom':13,
	'xOrder':0, 'yOrder':0,
	'redMult':1, 'greenMult':0.9961, 'blueMult':0.9856,
	'filterShades':123}, # exact number of shades in a tile that indicates location should be thrown out

	# {'url':marsURL, 'name':'Mars', 'extraterrestrial':True,
	# 'minZoom':6, 'maxZoom':6,
	# 'xOrder':0, 'yOrder':1,
	# 'redMult':1, 'greenMult':1, 'blueMult':1,},
]

CurrentURL = None
CurrentZoom = None
CurrentGrade = None
CurrentMult = None
CurrentUnavailImageList = None
urlSpec = None

degreesPerTheta = 90 / (math.pi / 2)

locStruct = [
		['city', 'locality', 'municipality', 'town', 'village'],
		['county', 'admin_2', 'subregion'],
		['state', 'admin_1', 'region', 'territory'],
		['country'],
		['longlabel', 'match_addr', 'address']] # fallbacks

def uniformlyRandomLatLon():
	# https://www.cs.cmu.edu/~mws/rpos.html
	z = random.randint(-10000000, 10000000) / 10000000
	lat = math.asin(z) * degreesPerTheta
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
	chromaStep = 10
	if maxChroma < 10:
		chromaStep = 1
	chroma = maxChroma
	iteration = 0
	while iteration < 35:
		c = lch_to_rgb(lightness, chroma, hue)
		if not c is None:
			if chromaStep == 0.01 or maxChroma == 0:
				return c
			else:
				chroma += chromaStep
				chromaStep /= 10
				chroma -= chromaStep
		chroma -= chromaStep
		iteration += 1

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

def imgHasContrast(img):
	if img is None:
		return None
	colors = img.getcolors(16777216)
	if colors is None:
		return None
	shades = len(colors)
	if CurrentUnavailImageList is None and shades == urlSpec.get('filterShades'):
		return None # this number of shades is probably a "tile not available" tile
	else:
		if shades < minShades or shades > maxShades:
			return False
		else:
			print('test tile shades: ', shades)
			return True

def imgIsUnavailable(img):
	if CurrentUnavailImageList is None:
		return None
	if list(img.getdata()) == CurrentUnavailImageList:
		# print("unavailable image")
		return True
	return False

def rotateImage(img, rotation):
	if rotation == 1:
		return img.transpose(Image.ROTATE_90)
	elif rotation == 2:
		return img.transpose(Image.ROTATE_180)
	elif rotation == 3:
		return img.transpose(Image.ROTATE_270)
	else:
		return img

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
		imgurl = CurrentURL.format(CurrentZoom, tile.get('x'), tile.get('y'))
		# print("Opening: " + imgurl)
		img = spoof(imgurl)
		# img = img.convert('L')
		tile['img'] = img
	except: 
		print("Couldn't download image")

def getTiles(tiles):
	with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
		executor.map(getOneTile, tiles)

def getImageCluster(lat_deg, lon_deg, xTileNum, yTileNum, zoom, rotation, xOrder, yOrder):
	global CurrentZoom
	CurrentZoom = zoom
	centerX, centerY = deg2num(lat_deg, lon_deg, zoom)
	if rotation == 1 or rotation == 3:
		# to rotate 90 or 270 degrees, switch the dimensions so that the right dimensions come out after rotation
		xtn = xTileNum+0
		xTileNum = yTileNum+0
		yTileNum = xtn
	xmin = centerX - math.floor(xTileNum/2)
	xmax = centerX + math.ceil(xTileNum/2) - 1
	ymin = centerY - math.floor(yTileNum/2)
	ymax = centerY + math.ceil(yTileNum/2) - 1
	# test the center for contrast (not in the ocean) or "tile not available"
	testTile = {'x':centerX, 'y':centerY}
	getOneTile(testTile)
	img = testTile.get('img')
	if img is None or imgIsUnavailable(img):
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
	Cluster = Image.new('RGB',((xmax-xmin+1)*256-1,(ymax-ymin+1)*256-1))
	# print(xmin, xmax, ymin, ymax, Cluster.size)
	for tile in tiles:
		xtile = tile.get('x')
		ytile = tile.get('y')
		img = tile.get('img')
		if img is None:
			return None
		if xOrder == 0:
			boxX = xtile - xmin
		elif xOrder == 1:
			boxX = xmax - xtile
		if yOrder == 0:
			boxY = ytile - ymin
		elif yOrder == 1:
			boxY = ymax - ytile
		# Cluster.paste(img, box=((xtile-xmin)*256 ,  (ytile-ymin)*256))
		Cluster.paste(img, box=(boxX*256, boxY*256))
	return rotateImage(Cluster, rotation)

def image_histogram_equalization(image, number_bins=256):
    # from http://www.janeriksolem.net/histogram-equalization-with-python-and.html
    # get image histogram
    image_histogram, bins = np.histogram(image.flatten(), number_bins, density=True)
    cdf = image_histogram.cumsum() # cumulative distribution function
    cdf = 255 * cdf / cdf[-1] # normalize
    # use linear interpolation of cdf to find new pixel values
    image_equalized = np.interp(image.flatten(), bins[:-1], cdf)
    return image_equalized.reshape(image.shape), cdf

def averageImageColor(img):
	rSum, gSum, bSum = 0, 0, 0
	colors = img.getcolors(16777216)
	numColors = len(colors)
	for c in colors:
		rgb = c[1]
		rSum += rgb[0]
		gSum += rgb[1]
		bSum += rgb[2]
	return [rSum / numColors, gSum / numColors, bSum / numColors]

def dominantImageColor(img):
	colors = img.getcolors(16777216)
	most, mostColor = None, None
	for c in colors:
		if most is None or c[0] > most:
			most = c[0]
			mostColor = c[1]
	return mostColor

def gradeFunc(v):
	return CurrentGrade[v]

# adjusting for the warm-toned hillshade
def gradeAndCorrectFunc(v):
	return CurrentGrade[max(0, min(255, int(v * CurrentMult)))]

def correctFunc(v):
	return max(0, min(255, int(v * CurrentMult)))

def correctWhiteBalance(img):
	global CurrentMult
	domRGB = dominantImageColor(img)
	highestComponent = max(*domRGB)
	CurrentMult = highestComponent / domRGB[0]
	redImage = Image.eval(img.getchannel('R'), correctFunc)
	CurrentMult = highestComponent / domRGB[1]
	greenImage = Image.eval(img.getchannel('G'), correctFunc)
	CurrentMult = highestComponent / domRGB[2]
	blueImage = Image.eval(img.getchannel('B'), correctFunc)
	return Image.merge('RGB', (redImage, greenImage, blueImage))

def colorizeAndCorrectWithInterpolation(img, interpolation):
	global CurrentGrade, CurrentMult
	redGrade = [int(interpolation(l/255).red * 255) for l in range(256)]
	greenGrade = [int(interpolation(l/255).green * 255) for l in range(256)]
	blueGrade = [int(interpolation(l/255).blue * 255) for l in range(256)]
	domRGB = dominantImageColor(img)
	highestComponent = max(*domRGB)
	CurrentGrade = redGrade
	CurrentMult = highestComponent / domRGB[0]
	redImage = Image.eval(img.getchannel('R'), gradeAndCorrectFunc)
	CurrentGrade = greenGrade
	CurrentMult = highestComponent / domRGB[1]
	greenImage = Image.eval(img.getchannel('G'), gradeAndCorrectFunc)
	CurrentGrade = blueGrade
	CurrentMult = highestComponent / domRGB[2]
	blueImage = Image.eval(img.getchannel('B'), gradeAndCorrectFunc)
	return Image.merge('RGB', (redImage, greenImage, blueImage))

def colorizeWithInterpolation(img, interpolation):
	global CurrentGrade
	redGrade = [int(interpolation(l/255).red * 255) for l in range(256)]
	greenGrade = [int(interpolation(l/255).green * 255) for l in range(256)]
	blueGrade = [int(interpolation(l/255).blue * 255) for l in range(256)]
	CurrentGrade = redGrade
	redImage = Image.eval(img.getchannel('R'), gradeFunc)
	CurrentGrade = greenGrade
	greenImage = Image.eval(img.getchannel('G'), gradeFunc)
	CurrentGrade = blueGrade
	blueImage = Image.eval(img.getchannel('B'), gradeFunc)
	return Image.merge('RGB', (redImage, greenImage, blueImage))

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
	# print(highestHues, angleDist(highestHues[0], highestHues[1]))
	return hueSwapMaybe(lightnessA, highestHues[0], lightnessB, highestHues[1])

def latinOnly(st):
	if st is None:
		# print("st is None")
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
			if not g.address is None and g.address != '':
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

	urlSpec = random.choice(xyzURLspecs)
	print(urlSpec.get('name'))
	CurrentURL = urlSpec.get('url')
	# get image that server provides when it has no data, if possible
	if os.path.exists('{}-unavail.png'.format(urlSpec.get('name'))):
		CurrentUnavailImageList = list(Image.open('{}-unavail.png'.format(urlSpec.get('name'))).getdata())
	elif os.path.exists(os.path.expanduser('~/color_out_of_earth/{}-unavail.png'.format(urlSpec.get('name')))):
		CurrentUnavailImageList = list(Image.open(os.path.expanduser('~/color_out_of_earth/{}-unavail.png'.format(urlSpec.get('name')))).getdata())

	if len(sys.argv) > 4:
		rotation = int(sys.argv[4])
	else:
		rotation = random.randint(0, 3)
	print("rotation:", rotation)
	attemptNum = 0
	a = None
	while not a and attemptNum < 100:
		if attemptNum == 0 and len(sys.argv) > 2:
			lat, lon = float(sys.argv[1]), float(sys.argv[2])
		else:
			lat, lon = uniformlyRandomLatLon()
		centerLatLon = [lat, lon]
		triedSpecifiedZoom = False
		zooms = [*range(urlSpec.get('minZoom'), urlSpec.get('maxZoom')+1)]
		while len(zooms) != 0:
			if len(sys.argv) > 3 and not triedSpecifiedZoom:
				zoom = int(sys.argv[3])
				triedSpecifiedZoom = True
			else:
				zoom = zooms.pop(random.randrange(len(zooms)))
			a = getImageCluster(centerLatLon[0], centerLatLon[1], widthInTiles, heightInTiles, zoom, rotation, urlSpec.get('xOrder'), urlSpec.get('yOrder'))
			if not a is None:
				if a == False:
					# got image okay but it's too low contrast, choose a new location
					break
				break
		# print(*centerLatLon, zoom, rotation)
		if a:
			argString = "{} {} {} {}".format(*centerLatLon, zoom, rotation)
		attemptNum += 1
	if attemptNum == 50:
		exit()

	eqImg = ImageOps.equalize(a)
	acImg = ImageOps.autocontrast(a, cutoff=0, ignore=None)
	blendedImg = Image.blend(eqImg, acImg, 0.5)
	# print(len(acImg.getcolors(16777216)), "autocontrast")
	# print(len(eqImg.getcolors(16777216)), "equalized")
	# print(len(eqImg.convert('L').getcolors(16777216)), "grayscale")
	# print(len(ImageOps.equalize(eqImg.convert('L')).getcolors(16777216)), "equalized grayscale")
	# eqImg.save(os.path.expanduser('~/color_out_of_earth/eq.png'))
	# acImg.save(os.path.expanduser('~/color_out_of_earth/ac.png'))
	# blendedImg.save(os.path.expanduser('~/color_out_of_earth/blend.png'))
	# a.save(os.path.expanduser('~/color_out_of_earth/a.png'))

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
		backgroundLightnessB = lightnessCeiling - backgroundLightnessA

	bgAC, bgBC = findColorPairByDeltaE(hue, backgroundDeltaE, backgroundLightnessA, backgroundLightnessB)
	# bgAC, bgBC = colorPairByHueDiff(hue, backgroundHueDiff, backgroundLightnessA, backgroundLightnessB)
	print(bgAC.convert('lch-d65'))
	print(bgBC.convert('lch-d65'))
	# print("delta e", bgAC.delta_e(bgBC, method='2000'))

	# colorize image
	i = bgAC.interpolate(bgBC, space='lch-d65')
	# i = coloraide.Color('srgb', [0,0,0]).interpolate(coloraide.Color('srgb', [1,1,1]), space='lab-d65') # for testing white balance
	colorized = colorizeAndCorrectWithInterpolation(blendedImg, i)
	# correctedImg = correctWhiteBalance(blendedImg)
	# colorized = colorizeWithInterpolation(correctedImg, i)
	# print(len(a.getcolors(16777216)), "original")
	# print(len(blendedImg.getcolors(16777216)), "equalized autocontrasted blend")
	# print(len(correctedImg.getcolors(16777216)), "corrected")
	# print(len(colorized.getcolors(16777216)), "colorized")
	# correctedImg.save(os.path.expanduser('~/color_out_of_earth/corrected.png'))
	# print(averageImageColor(eqImg), dominantImageColor(eqImg))
	# print(averageImageColor(colorized), dominantImageColor(colorized))

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

	if identifyLocation == True and not urlSpec.get('extraterrestrial'):
		print(argString)
		import geocoder
		import pycountry
		from googletrans import Translator, constants
		name, latinName = locationName(centerLatLon)
		name = name or ''
		latinName = latinName or ''
		translator = Translator()
		transName = translator.translate(name, dest=languageCode).text
		nameText = name + "\n" + transName
		print(name)
		print(transName)
		if latinName != name:
			transLatinName = translator.translate(latinName, dest=languageCode).text
			nameText = nameText + "\n" + latinName + "\n" + transLatinName
			print(latinName)
			print(transLatinName)
		fp = open(os.path.expanduser('~/color_out_of_earth/location.txt'), 'w', encoding='utf8')
		fp.write(nameText + "\n" + argString)
		fp.close()
		print(os.path.expanduser('~/color_out_of_earth/location.txt'), 'saved')