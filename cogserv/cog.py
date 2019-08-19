import base64
import math
import numpy as np
import matplotlib
import rasterio
import mercantile

from matplotlib.cm import ScalarMappable, get_cmap
from matplotlib.colors import LinearSegmentedColormap, ListedColormap, \
                              NoNorm, Normalize, BoundaryNorm

from PIL import Image

from rasterio.crs import CRS
from rasterio.vrt import WarpedVRT
from rasterio.io import MemoryFile
from rasterio.enums import Resampling, MaskFlags, ColorInterp
from rasterio import transform
from rasterio import windows
from rasterio.warp import calculate_default_transform, transform_bounds

from io import BytesIO
from colour import Color

class CogException(Exception):
    pass

class CogImg(object):
    """
    Simple image wrapper that lets you access the raw data with the 'raw' 
    property, export the file with export(), or use it as a base64 inline image 
    with 'base64' property.
    """
    def __init__(self, raw, mimetype='application/octet-stream'):
        self.raw = raw
        self.mimetype = mimetype

    def export(self, filename):
        with open(filename, 'wb') as f:
            f.write(self.raw)

    @property
    def base64(self):
        return b"data:"+self.mimetype+";base64,"+base64.b64encode(self.raw)

class Colorizer(object):
    def __init__(self, **kwargs):
        self.params = kwargs
        
    def __repr__(self):
        return "<Colorizer bands={} colormap='{}' interp='{}' ranges='{}'>".format(self.bands, self.colormap, self.interp, self.ranges)

    def apply(self, data, mask):
        """
        Apply the colorizer to a data/mask set.

        TODO: Clean this up a bit
        """
        self.rgba = None

        if len(self.bands) == 1:
            # Singleband pseudocolor
            data = data[0,:,:]
        else:
            # Multiband RGB. No colorizing to do, just transpose the
            # data array and add the mask band. Mask may be discarded 
            # later when using jpg as output, for example.
            self.rgba = np.dstack((np.transpose(data, (1, 2, 0)), mask))
            return self.rgba
        
        if self.interp == 'linear':
            norm = Normalize(self.ranges[0],self.ranges[-1])
            sm = ScalarMappable(norm=norm, cmap=self.colormap)
            self.rgba = sm.to_rgba(data, bytes=True)

        if self.interp == 'discrete':
            norm = BoundaryNorm(boundaries=self.ranges, ncolors=256)
            sm = ScalarMappable(norm=norm, cmap=self.colormap)
            self.rgba = sm.to_rgba(data, bytes=True)

        if self.interp == 'exact':
            norm = NoNorm()
            sm = ScalarMappable(norm=norm, cmap=self.colormap)

            # Copy and mask the entire array.
            tmp_data = data.copy()
            tmp_data.fill(0)
            tmp_mask = mask.copy()
            tmp_mask.fill(0)

            # Reclassify the data
            for n,r in enumerate(self.ranges):
                ix = np.logical_and((data == r), (mask == 255))
                tmp_data[ix] = n+1
                tmp_mask[ix] = 255

            self.rgba = sm.to_rgba(tmp_data, bytes=True)
            mask = tmp_mask

        self.rgba[:,:,3] = mask
        return self.rgba

    def image(self, format='png', quality=80):
        im_data = self.rgba
        opts = {}

        if format == 'png':
            opts = {
                "format": "PNG"
            }
            
        if format == 'jpg':
            im_data = self.rgba[:,:,:3]
            opts = {
                "format": "JPEG", 
                "quality": quality,
                "optimize": True,
                "progressive":True
            }

        if format == 'webp':
            opts = {
                "format": "WEBP",
                "quality": quality
            }

        im_mode = 'RGBA' if im_data.shape[2] == 4 else 'RGB'
        im = Image.fromarray(im_data, mode=im_mode)
        im_buffer = BytesIO()
        im.save(im_buffer, **opts)
        mimetype = "image/"+opts.get("format").lower()

        return CogImg(im_buffer.getvalue(), mimetype=mimetype)

    @property
    def bands(self):
        if hasattr(self, '_bands'):
            return self._bands

        if 'bands' not in self.params:
            self._bands = (1, )
        else:
            try:
                self._bands = list(map(int, self.params.get('bands').split(',')))
            except:
                self._bands = (1, )

        return self._bands

    @property
    def colormap(self):
        if hasattr(self, '_colormap'):
            return self._colormap

        if 'colormap' not in self.params:
            self._colormap = None
            return self._colormap

        # Try to parse as a named colormap
        try:
            self._colormap = get_cmap(self.params.get("colormap", "jet"))
        except:
            self._colormap = None

        # If that doesnt work, try to parse as a list of individual colors
        if not self._colormap:
            try:
                colorlist = []
                for c in self.params.get("colormap").split(","):
                    colorlist.append(Color(c).rgb)

                if self.interp == 'exact':
                    # Insert a color whose class will be used for a mask
                    colorlist.insert(0,Color('black').rgb)
                    self._colormap = ListedColormap(colorlist, 'custom')
                    return self._colormap
                else:
                    print('creating LinearSegmentedColormap with colorlist:')
                    print(colorlist)
                    if len(colorlist) < 2:
                        raise Exception("Need at least two colors in colormap.")
                    else:
                        self._colormap = LinearSegmentedColormap.from_list('custom', colorlist, N=256)
                        return self._colormap
            except:
                self._colormap = None

        if not self._colormap:
            self._colormap = get_cmap("jet")

        return self._colormap

    @property
    def ranges(self):
        if hasattr(self, '_ranges'):
            return self._ranges

        if 'ranges' not in self.params:
            self._ranges = None
        else:
            try:
                self._ranges = list(map(float, self.params.get("ranges").split(",")))
            except:
                self._ranges = None
        return self._ranges

    @property
    def interp(self):
        if hasattr(self, '_interp'):
            return self._interp

        interp = self.params.get("interp")
        if interp in ('linear', 'discrete', 'exact'):
            self._interp = interp
        else:
            self._interp = 'linear'
        return self._interp

class Cog(object):
    def __init__(self, url):
        self.url = url

    def __enter__(self):        
        self.src = rasterio.open(self.url)
        return self

    def __exit__(self, exc_type, exc_val, exc_traceback):
        self.src.close()

    def __repr__(self):
        return "<Cog url='{}'>".format(self.url)

    def get_map(self, width=500, format='png', colorizer={}):
        self.crs = CRS({"init": "EPSG:4326"})
        self.bounds = transform_bounds(*[self.src.crs, "epsg:4326"] + list(self.src.bounds), densify_pts=21)
        self.width = width
        w, s, e, n = self.bounds
        self.height = int(width*(abs(n-s)/abs(w-e)))

        return self._make_image(colorizer)
    
    def get_tile(self, z, x, y, format='png', colorizer={}):
        self.width = 256
        self.height = 256
        self.bounds = mercantile.xy_bounds(x, y, z)
        self.crs = CRS({"init": "EPSG:3857"})

        return self._make_image(colorizer, format)

    def _make_image(self, colorizer, format='png'):
        colorizer = Colorizer(**colorizer)
        self._load_data(bands=colorizer.bands)
        colorizer.apply(self.data, self.mask)
        return colorizer.image(format=format)

    def _load_data(self, nodata=None, resampling_method='nearest', bands=(1,)):
        """
        Warp the data from the remote GTiff into a numpy array
        """

        vrt_params = dict(
            add_alpha=True, crs=self.crs, resampling=Resampling[resampling_method]
        )

        vrt_transform, vrt_width, vrt_height = self._get_vrt_transform()

        out_window = windows.Window(
            col_off=0, row_off=0, width=vrt_width, height=vrt_height
        )

        vrt_params.update(dict(transform=vrt_transform, width=vrt_width, height=vrt_height))

        out_shape = (len(bands), self.height, self.width)

        nodata = nodata if nodata is not None else self.src.nodata
        if nodata is not None:
            vrt_params.update(dict(nodata=nodata, add_alpha=False, src_nodata=nodata))

        if self._has_alpha_band():
            vrt_params.update(dict(add_alpha=False))

        with WarpedVRT(self.src, **vrt_params) as vrt:
            self.data = vrt.read(
                out_shape=out_shape,
                indexes=bands,
                window=out_window,
                resampling=Resampling[resampling_method],
            )
            self.mask = vrt.dataset_mask(
                out_shape=(self.height, self.width), 
                window=out_window
            )

    def _get_vrt_transform(self):
        """
        """
        dst_transform, _, _ = calculate_default_transform(
            self.src.crs, self.crs, self.width, self.height, *self.src.bounds
        )
        w, s, e, n = self.bounds
        vrt_width = math.ceil((e - w) / dst_transform.a)
        vrt_height = math.ceil((s - n) / dst_transform.e)
        vrt_transform = transform.from_bounds(w, s, e, n, vrt_width, vrt_height)

        return vrt_transform, vrt_width, vrt_height

    def _has_alpha_band(self):
        if (
            any([MaskFlags.alpha in flags for flags in self.src.mask_flag_enums])
            or ColorInterp.alpha in self.src.colorinterp
        ):
            return True
        return False