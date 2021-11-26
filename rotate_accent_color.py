import sys
import datetime
from winreg import *
import coloraide
import os
import subprocess
from PIL import Image
import random
import math

maxChroma = 90
randomMaxChroma = True
minMaxChroma = 10
setBackground = False
backgroundHueAdd = 45
backgroundLightness = 33

lightnessPoints = [83.8, 72.2, 61.4, 49.0, 36.7, 26.7, 13.9]

def twentyFourBitRGB(rgb):
	floats = []
	for component in rgb:
		floats.append(min(1,max(0,component))*255)
	pairs = []
	for component in floats:
		down = int(math.floor(component))
		up = int(math.ceil(component))
		downFraction = component - down
		upFraction = up - component
		pairs.append([down, up, downFraction, upFraction])
	colorChoices = [[0,0,0], [0,0,1], [0,1,1], [1,1,1], [1,1,0], [1,0,0], [1,0,1], [0,1,0]]
	chances = []
	for cc in colorChoices:
		color = (pairs[0][cc[0]], pairs[1][cc[1]], pairs[2][cc[2]])
		error = pairs[0][cc[0]+2] + pairs[1][cc[1]+2] + pairs[2][cc[2]+2]
		chance = int((3 - error) * 4)
		# print(error, chance, color, rgb)
		for i in range(chance+1):
			chances.append(color)
	return chances

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

def nextHueByDeltaE(lchColor, deltaEAdd):
	for hueAdd in range(1, 180):
		newC = highestChromaColor(lchColor.l, lchColor.h + hueAdd)
		deltaE = lchColor.delta_e(newC, method='2000')
		if deltaE >= deltaEAdd:
			return lchColor.h + hueAdd

hue = 0
if randomMaxChroma == True:
	maxChroma = random.randrange(minMaxChroma, maxChroma+1)
print('maxChroma:', maxChroma)

if len(sys.argv) < 2:
	exit();
arg = sys.argv[1]

if arg[:1] == '+' or arg[:1] == '-':
	deltaEAdd = int(arg[1:])
	if arg[:1] == '-':
		deltaEAdd = 0 - deltaEAdd
	# get current accent color
	key = OpenKey(HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent', 0, KEY_ALL_ACCESS)
	val = QueryValueEx(key, "AccentColorMenu")
	print('AccentColorMenu:', val[0])
	rgbVal = intDwordColorToRGB(val[0])
	lchC = rgb_to_lch(rgbVal[0], rgbVal[1], rgbVal[2])
	hue = nextHueByDeltaE(lchC, deltaEAdd)
	# hue = (lchC.h + deltaEAdd) % 360
else:
	hue = float(arg)

print('hue:', hue)

hexStrings = []

startDT = datetime.datetime.now()
for lightness in lightnessPoints:
	rgbC = highestChromaColor(lightness, hue)
	hs = rgbC.to_string(hex=True)[1:]
	hexStrings.append(hs)
weirdHue = ((hue + 180) % 360) + 1
weirdRGBC = highestChromaColor(50, weirdHue)
hexStrings.append(weirdRGBC.to_string(hex=True)[1:])
print('found colors in', datetime.datetime.now() - startDT)

if setBackground == True:
	bgAHue = (hue - backgroundHueAdd) % 360
	bgBHue = (hue + backgroundHueAdd) % 360
	print("background hues", bgAHue, bgBHue)
	bgAC = highestChromaColor(backgroundLightness, bgAHue)
	bgBC = highestChromaColor(backgroundLightness, bgBHue)
	bgChroma = min(bgAC.convert('lch-d65').c, bgBC.convert('lch-d65').c)
	print("background chroma", bgChroma)
	bgAC = lch_to_rgb(backgroundLightness, bgChroma, bgAHue)
	bgBC = lch_to_rgb(backgroundLightness, bgChroma, bgBHue)

# print(hexStrings)
fullHexString = '00'.join(hexStrings) + '00'
# print(fullHexString)
hexBytes = bytes.fromhex(fullHexString)
# print(hexBytes)

menuInt = hexToIntDwordColor(hexStrings[3])
startInt = hexToIntDwordColor(hexStrings[4])
# print(menuInt, startInt)

keyVal = r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent'
try:
    key = OpenKey(HKEY_CURRENT_USER, keyVal, 0, KEY_ALL_ACCESS)
except:
    key = CreateKey(HKEY_CURRENT_USER, keyVal)
SetValueEx(key, "AccentPalette", 0, REG_BINARY, hexBytes)
SetValueEx(key, "AccentColorMenu", 0, REG_DWORD, menuInt)
SetValueEx(key, "StartColorMenu", 0, REG_DWORD, startInt)
CloseKey(key)

if setBackground == True:
	bgImg = Image.new('RGB', (1920,1080))
	i = bgAC.interpolate(bgBC, space='lab-d65')
	rawrows = [i(x/1080).coords() for x in range(1080)]
	rows = []
	for row in rawrows:
		rows.append(twentyFourBitRGB(row))
	ditherer = [-1,1]
	flat = []
	for ri in range(1080):
		row = rows[ri]
		for x in range(1920):
			a = random.choice(ditherer) * random.randint(1, 24)
			row = rows[min(1079,max(0,ri+a))]
			rgbTup = row[random.randint(0,len(row)-1)]
			flat.append(rgbTup)
	bgImg.putdata(flat)
	bgImg.save(os.path.expanduser('~/AppData/Roaming/Microsoft/Windows/Themes/TranscodedWallpaper'), format='PNG')
	# create path if not existant
	if not os.path.exists(os.path.expanduser('~/Pictures/autowalls')):
		os.makedirs(os.path.expanduser('~/Pictures/autowalls'))
	bgImg.save(os.path.expanduser('~/Pictures/autowalls/rotate_accent_color.png'), format='PNG')
	keyVal = r'Control Panel\Desktop'
	try:
	    key = OpenKey(HKEY_CURRENT_USER, keyVal, 0, KEY_ALL_ACCESS)
	except:
	    key = CreateKey(HKEY_CURRENT_USER, keyVal)
	SetValueEx(key, "Wallpaper", 0, REG_SZ, os.path.expanduser('~/Pictures/autowalls/rotate_accent_color.png'))
	CloseKey(key)
	subprocess.run(['rundll32.exe', 'user32.dll,', 'UpdatePerUserSystemParameters'])
	subprocess.run(['rundll32.exe', 'user32.dll,', 'UpdatePerUserSystemParameters'])