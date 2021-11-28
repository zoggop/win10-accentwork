import sys
import datetime
from winreg import *
import coloraide
import os
import random
import math

maxChroma = 90 # pure blue has chroma of 133.81
randomMaxChroma = True
minMaxChroma = 10

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

def nextHueByDeltaE(lchColor, deltaEAdd, negative):
	for hueAdd in range(1, 180):
		if negative == True:
			newHue = lchColor.h - hueAdd
			if newHue < 0:
				newHue = newHue + 360
		else:
			newHue = lchColor.h + hueAdd
			if newHue > 360:
				newHue = newHue - 360
		newC = highestChromaColor(lchColor.l, newHue)
		deltaE = lchColor.delta_e(newC, method='2000')
		if deltaE >= deltaEAdd:
			return lchColor.h + hueAdd

# lightnessPoints = [84.2, 72.7, 62.1, 49.9, 37.4, 27.2, 14.3]
lightnessMin = 15
lightnessMax = 85
l = lightnessMax
lStep = (lightnessMax - lightnessMin) / 6
lightnessPoints = []
for n in range(0, 7):
	lightnessPoints.append(l)
	l = l - lStep
# print(lightnessPoints)

hue = 0
if randomMaxChroma == True:
	maxChroma = random.randrange(minMaxChroma, maxChroma+1)
print('maxChroma:', maxChroma)

if len(sys.argv) < 2:
	exit();
arg = sys.argv[1]

if arg[:1] == '+' or arg[:1] == '-':
	deltaEAdd = int(arg[1:])
	negative = False
	if arg[:1] == '-':
		negative = True
	# get current accent color
	key = OpenKey(HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent', 0, KEY_ALL_ACCESS)
	val = QueryValueEx(key, "AccentColorMenu")
	rgbVal = intDwordColorToRGB(val[0])
	lchC = rgb_to_lch(rgbVal[0], rgbVal[1], rgbVal[2])
	if deltaEAdd == 0:
		hue = lchC.h
	else:
		hue = nextHueByDeltaE(lchC, deltaEAdd, negative)
else:
	hue = float(arg)

print('hue:', '{:.2f}'.format(hue))

hexStrings = []

startDT = datetime.datetime.now()
for lightness in lightnessPoints:
	rgbC = highestChromaColor(lightness, hue)
	hs = rgbC.to_string(hex=True)[1:]
	print(hs, 'lightness:', '{:.2f}'.format(lightness), 'chroma:', '{:.2f}'.format(rgbC.convert('lch-d65').c))
	hexStrings.append(hs)
weirdHue = ((hue + 180) % 360) + 1
weirdRGBC = highestChromaColor(50, weirdHue)
hexStrings.append(weirdRGBC.to_string(hex=True)[1:])
print('found colors in', datetime.datetime.now() - startDT)

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