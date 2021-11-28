## Usage:
`python rotate_accent_color.py +21`

where 21 is the deltaE color difference between the new accent color and the current accent color. Using `+` will increase the hue, and using `-` will decrease the hue. A number without `+` or `-` sets the hue to that number.

## More Information:

There are some settings at the top of the script. By default, a random maximum chroma between 5 and 134 will be chosen, but this can be turned off so that the maximum chroma is always 134 (the maximum possible). The range of possible maximum chroma can be changed.

## Dependencies:
Python module: coloraide