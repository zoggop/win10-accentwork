import sys
import datetime
from winreg import *
import coloraide
import os
import subprocess
import random
import math

backgroundLightness = 33
backgroundHueAdd = 45

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

# get current accent color hue
key = OpenKey(HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent', 0, KEY_ALL_ACCESS)
val = QueryValueEx(key, "AccentColorMenu")
rgbVal = intDwordColorToRGB(val[0])
lchC = rgb_to_lch(rgbVal[0], rgbVal[1], rgbVal[2])
hue = lchC.h

bgAHue = (hue - backgroundHueAdd) % 360
bgBHue = (hue + backgroundHueAdd) % 360
print("background hues", bgAHue, bgBHue)
bgAC = highestChromaColor(backgroundLightness, bgAHue)
bgBC = highestChromaColor(backgroundLightness, bgBHue)
bgChroma = min(bgAC.convert('lch-d65').c, bgBC.convert('lch-d65').c)
print("background chroma", bgChroma)
bgAC = lch_to_rgb(backgroundLightness, bgChroma, bgAHue)
bgBC = lch_to_rgb(backgroundLightness, bgChroma, bgBHue)

from PIL import Image
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