import numpy as np
import matplotlib.pyplot as plt
from matplotlib.cbook import get_sample_data
from matplotlib.colors import LightSource
from urllib.request import urlopen, Request
from io import BytesIO
from PIL import Image, ImageOps, ImageFilter
from wand.image import Image as WandImage
import os

def spoof(url): # this function pretends not to be a Python script
    req = Request(url) # start request
    req.add_header('User-agent','Firefox') # add user agent to request
    # req.add_header('Desired-tile-form', 'BW')
    fh = urlopen(req)
    im_data = BytesIO(fh.read()) # get image
    fh.close() # close url
    img = Image.open(im_data) # open image with PIL
    return img

def getOneTile():
    try:
        # imgurl = CurrentURL.format(CurrentZoom, tile.get('x'), tile.get('y'))
        imgurl = 'https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL1.003/2000.02.11/N42W123.SRTMGL1.2.jpg'
        # print("Opening: " + imgurl)
        img = spoof(imgurl)
        return img
    except: 
        print("Couldn't download image")

# img  = getOneTile()
# img.save(os.path.expanduser('~/color_out_of_earth/temp.png'))
wim = WandImage(filename = os.path.expanduser('~/color_out_of_earth/temp2.png'))
wim.blur(sigma = 20)
# wim.shade(gray=True, azimuth=135, elevation=45)
# wim.equalize()
wim.save(filename = os.path.expanduser('~/color_out_of_earth/temp3.png'))
exit()
smo = Image.open(os.path.expanduser('~/color_out_of_earth/temp3.png'))

z = np.array(smo)
dx, dy = 10375, 13875

# dem = get_sample_data('jacksboro_fault_dem.npz', np_load=True)
# z = dem['elevation']
print(z)
# -- Optional dx and dy for accurate vertical exaggeration --------------------
# If you need topographically accurate vertical exaggeration, or you don't want
# to guess at what *vert_exag* should be, you'll need to specify the cellsize
# of the grid (i.e. the *dx* and *dy* parameters).  Otherwise, any *vert_exag*
# value you specify will be relative to the grid spacing of your input data
# (in other words, *dx* and *dy* default to 1.0, and *vert_exag* is calculated
# relative to those parameters).  Similarly, *dx* and *dy* are assumed to be in
# the same units as your input z-values.  Therefore, we'll need to convert the
# given dx and dy from decimal degrees to meters.
# dx, dy = dem['dx'], dem['dy']
# dy = 111200 * dy
# dx = 111200 * dx * np.cos(np.radians(dem['ymin']))
# -----------------------------------------------------------------------------

# Shade from the northwest, with the sun 45 degrees from horizontal
ls = LightSource(azdeg=315, altdeg=45)

fig, ax = plt.subplots()

rgb = ls.hillshade(z, vert_exag=10, dx=dx, dy=dy)

# rgb = ls.shade(z, cmap=cmap, blend_mode='overlay', vert_exag=1, dx=dx, dy=dy)
ax.imshow(rgb, cmap='gray')

plt.show()