import sys
import datetime
from winreg import *
import coloraide
import os
import subprocess
import random
import math

from scipy.spatial import KDTree
from webcolors import (
    CSS3_HEX_TO_NAMES,
    hex_to_rgb,
)

backgroundLightness = 33
backgroundHueAdd = 45
maxChroma = 90

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

def convert_rgb_to_names(rgb_tuple):
	# a dictionary of all the hex and their respective names in css3
	css3_db = CSS3_HEX_TO_NAMES
	names = []
	rgb_values = []
	for color_hex, color_name in css3_db.items():
		names.append(color_name)
		rgb_values.append(hex_to_rgb(color_hex))
	kdt_db = KDTree(rgb_values)
	distance, index = kdt_db.query(rgb_tuple)
	return names[index]

# get current accent color hue
key = OpenKey(HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent', 0, KEY_ALL_ACCESS)
val = QueryValueEx(key, "AccentColorMenu")
rgbVal = intDwordColorToRGB(val[0])
lchC = rgb_to_lch(rgbVal[0], rgbVal[1], rgbVal[2])
hue = lchC.h
maxChroma = int(lchC.c)
print(lchC.convert('srgb').to_string(hex=True, upper=True), convert_rgb_to_names((rgbVal[0], rgbVal[1], rgbVal[2])))

bgAHue = (hue - backgroundHueAdd) % 360
bgBHue = (hue + backgroundHueAdd) % 360
print("background hues", bgAHue, bgBHue)
bgAC = highestChromaColor(backgroundLightness, bgAHue)
bgBC = highestChromaColor(backgroundLightness, bgBHue)
bgChroma = min(bgAC.convert('lch-d65').c, bgBC.convert('lch-d65').c)
print("background chroma", bgChroma)
bgAC = lch_to_rgb(backgroundLightness, bgChroma, bgAHue)
bgBC = lch_to_rgb(backgroundLightness, bgChroma, bgBHue)
print(convert_rgb_to_names((int(bgAC.r*255), int(bgAC.g*255), int(bgAC.b*255))))
print(convert_rgb_to_names((int(bgBC.r*255), int(bgBC.g*255), int(bgBC.b*255))))

from PIL import Image
bgImg = Image.new('RGB', (1920,1080))
i = bgAC.interpolate(bgBC, space='lch-d65')
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