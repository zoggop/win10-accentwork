import coloraide
import random

for l in range(5, 95, 5):
	c = coloraide.Color('lch-d65', [l, 0, 0]).convert('oklch')
	print(l, c.l)

print('002642', coloraide.Color('#002642').convert('oklch'), coloraide.Color('#002642').convert('lch-d65'))
print('A6D8FF', coloraide.Color('#A6D8FF').convert('oklch'), coloraide.Color('#A6D8FF').convert('lch-d65'))

print(coloraide.Color('srgb', [0, 0, 1]).convert('oklch'))