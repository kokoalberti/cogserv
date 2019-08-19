"""cogserv"""

import os
import json
import urllib
import numpy
import mercantile
import rasterio

from osgeo import gdal

from rasterio import warp
from rasterio.transform import from_bounds

from rio_tiler import main as cogTiler
from rio_tiler.mercator import get_zooms
from rio_tiler.profiles import img_profiles
from rio_tiler.utils import (
    array_to_image,
    get_colormap,
    expression,
    linear_rescale,
    _chunks,
)

from rio_color.operations import parse_operations
from rio_color.utils import scale_dtype, to_math_type


from cogserv.cog import Cog

from lambda_proxy.proxy import API

app = API(name="cogserv")

@app.route("/cogserv/<regex([-a-zA-Z0-9_]+):bucket>/<regex([-a-zA-Z0-9_\\.\\/]+):key>~/tile/<int:z>/<int:x>/<int:y>.<ext>", methods=["GET"], cors=True, payload_compression_method="gzip", binary_b64encode=True)
def tile(bucket, key, z, x, y, ext=None, url=None, nodata=None, color_map=None):
    if bucket and key:
        url = f'https://{bucket}.s3.amazonaws.com/{key}'
    else:
        raise Error("Invalid bucket/key.")
        
    with Cog(url) as src:
        colorizer = {
            'colormap':'Blues',
            'ranges':'100,150',
            'interp':'linear'
        }
        image = src.get_tile(z=z, x=x, y=y, format=ext, colorizer=colorizer)
        
    return ("OK", image.mimetype, image.raw)

@app.route("/cogserv/<regex([-a-zA-Z0-9_]+):bucket>/<regex([-a-zA-Z0-9_\\.\\/]+):key>~/map.<ext>", methods=["GET"], cors=True, payload_compression_method="gzip", binary_b64encode=True)
def map_image(bucket, key, ext=None):
    if bucket and key:
        url = f'https://{bucket}.s3.amazonaws.com/{key}'
    else:
        raise Error("Invalid bucket/key.")
        
    with Cog(url) as src:
        colorizer = {
            'colormap':'Blues',
            'ranges':'100,150',
            'interp':'linear'
        }
        image = src.get_map(width=500, format=ext, colorizer=colorizer)
        
    return ("OK", image.mimetype, image.raw)


@app.route("/cogserv/about")
def about():
    about = "Cogserv (rasterio={} gdal={})".format(rasterio.__version__, gdal.__version__)
    return ("OK", "application/json", json.dumps(about))

