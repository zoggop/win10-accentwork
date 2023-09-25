import winreg
from winreg import *
import coloraide

def intDwordColorToRGB(dwordInt):
	reverse = hex(dwordInt)
	r = int('0x' + reverse[8:], 16)
	g = int('0x' + reverse[6:8], 16)
	b = int('0x' + reverse[4:6], 16)
	return [r, g, b]

def rgb_to_lch(red, green, blue):
	c = coloraide.Color('srgb', [red/255, green/255, blue/255]).convert('lch-d65')
	if c.in_gamut():
		return c
	return None

def get_accent_rgb():
	key = OpenKey(HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Accent', 0, KEY_ALL_ACCESS)
	val = QueryValueEx(key, "AccentColorMenu")
	rgbVal = intDwordColorToRGB(val[0])
	return rgbVal

rgb = get_accent_rgb()
lch = rgb_to_lch(*rgb)

print('RGB', *rgb)
print('LCH', int(lch.l), int(lch.c), int(lch.h))