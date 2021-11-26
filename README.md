## Usage:
`python rotate_accent_color.py +21`

where 21 is the deltaE color difference between the new accent color and the current accent color. Using `+` will increase the hue, and using `-` will decrease the hue. A number without `+` or `-` sets the hue to that number.

## More Information:

There are some settings at the top of the script. By default, a random maximum chroma between 10 and 90 will be chosen, but this can be turned off so that the chosen maximum chroma is always used (currently 90). The script can generate a background image of a gradient of adjacent colors to the new accent color and try to set it, but I've turned this off because most of the time, the background image won't change and it has to be done manually in the settings app.

## Dependencies:
Python modules: coloraide, Pillow (if background image generation is turned on)