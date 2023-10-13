import sys
import datetime
from winreg import *
import coloraide
import os
import random
import math

maxChroma = 0.322
randomMaxChroma = True
minMaxChroma = 0.01

def lch_to_rgb(lightness, chroma, hue):
	c = coloraide.Color('oklch', [lightness, chroma, hue]).convert('srgb')
	if c.in_gamut():
		return c
	return None

# input channels are 0-255
def rgb_to_lch(red, green, blue):
	c = coloraide.Color('srgb', [red/255, green/255, blue/255]).convert('oklch')
	if c.in_gamut():
		return c
	return None

def highestChromaColor(lightness, hue, maxChroma=0.4):
	chromaStep = 0.1
	if maxChroma < 0.1:
		chromaStep = 0.01
	chroma = maxChroma
	iteration = 0
	while iteration < 45:
		c = lch_to_rgb(lightness, chroma, hue)
		if not c is None:
			if chromaStep == 0.0001 or maxChroma == 0 or iteration == 0:
				return c
			else:
				chroma += chromaStep
				chromaStep /= 10
				chroma -= chromaStep
		chroma = max(0, chroma - chromaStep)
		iteration += 1
	print(chromaStep, lightness, chroma, hue, iteration)

def hexToIntDwordColor(hexString):
	convertable = '0xff' + hexString[4:] + hexString[2:4] + hexString[:2]
	return int(convertable, 16)

def intDwordColorToRGB(dwordInt):
	reverse = hex(dwordInt)
	r = int('0x' + reverse[8:], 16)
	g = int('0x' + reverse[6:8], 16)
	b = int('0x' + reverse[4:6], 16)
	return [r, g, b]

lightnessMin = 0.25
lightnessMax = 0.85
l = lightnessMax
lStep = (lightnessMax - lightnessMin) / 6
lightnessPoints = []
for n in range(0, 7):
	lightnessPoints.append(l)
	l = l - lStep
# print(lightnessPoints)

hue = 0

if len(sys.argv) > 2:
	maxChroma = float(sys.argv[2])
elif randomMaxChroma == True:
	maxChroma = random.uniform(minMaxChroma, maxChroma)
print('maxChroma:', maxChroma)

if len(sys.argv) < 2:
	hue = random.uniform(0, 359)
else:
	arg = sys.argv[1]
	if arg[:1] == '+' or arg[:1] == '-':
		hueAdd = float(arg[1:])
		if arg[:1] == '-':
			hueAdd = (0 - hueAdd) % 360
		# get current accent color
		key = OpenKey(HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent', 0, KEY_ALL_ACCESS)
		val = QueryValueEx(key, "AccentColorMenu")
		rgbVal = intDwordColorToRGB(val[0])
		lchC = rgb_to_lch(rgbVal[0], rgbVal[1], rgbVal[2])
		hue = lchC.h + hueAdd
	else:
		hue = float(arg)

print('hue:', '{:.2f}'.format(hue))

hexStrings = []

startDT = datetime.datetime.now()
for lightness in lightnessPoints:
	rgbC = highestChromaColor(lightness, hue, maxChroma)
	hs = rgbC.to_string(hex=True)[1:]
	print(hs, 'lightness:', '{:.3f}'.format(lightness), 'chroma:', '{:.3f}'.format(rgbC.convert('oklch').c))
	hexStrings.append(hs)
weirdHue = ((hue + 180) % 360)
weirdRGBC = highestChromaColor(0.5, weirdHue, maxChroma)
hexStrings.append(weirdRGBC.to_string(hex=True)[1:])
print('found colors in', datetime.datetime.now() - startDT)

# exit()

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