# Cogserv

**This is an experimental AWS Lambda/GTiff server. Do not use for anything serious.**

If you're interested in GTiff on Lambda, check out the following (rather more stable) projects:

* https://github.com/vincentsarago/lambda-tiler
* https://github.com/mojodna/marblecutter
* https://github.com/DHI-GRAS/terracotta

## About

Coxserv is an experimental AWS Lambda function for serving GeoTIFF files as tiles and a few other formats. It heavily inspired by and modeled after the very nice https://github.com/vincentsarago/lambda-tiler. 

There are a few additional and different types of features that I'd like to implement for a project I'm working on:

* Some additional visualization options (on the fly raster classifications, discrete colormaps, on the fly colormaps, maybe some different modes like equal interval, quantiles, natural breaks, etc)
* Allow visualization options (colormaps, etc) to be defined by custom metadata keys in the GTiff
* Different URL pattern: `/<bucket>/<key>~/<endpoint>?<query>` to remove `url` from the query string
* Endpoint for querying data from multi-band rasters for making simple charts (i.e. returning JSON with monthly values from a 12-band raster). A bit like rasterstats/GetLocationInfo combo.
* Endpoint to return a single map image that can be easily included in HTML pages and reports
* Endpoint to return some sort of JSON map legend object. Not sure yet how this will work.
* Endpoint to return data on transects. For example, pass a `transect=LINESTRING(...)` and get back a json object with values, for example to make elevation profiles from a DEM.

## Endpoints

### `~/tile`

### `~/map`

### `~/bounds.json`

TODO

## Quick Start

### Lambda Layers

So getting a geospatial Python environment up and running on Lambda can be a bit of work. Instead of bundling everything into a large deployment package, I'm using two Lambda layers stacked on top of each other. These are based on https://github.com/developmentseed/geolambda. The first is layer with GDAL libs, and the second contains a bunch of Python geo packages which are useful. Both layers are in `eu-central-1`.

    arn:aws:lambda:eu-central-1:059606879383:layer:geolambda:2
    arn:aws:lambda:eu-central-1:059606879383:layer:geolambda-python36:7

They aren't exactly the same as the default layers created by geolambda because I've added a couple of Python packages (lambda-proxy, rio-tiler, shapely, matplotlib, PIL) and the aws command line tools to be able to do the magical `aws s3 sync` from within my Lambda.

### Serverless Deploy

Deploys using Serverless. Create an admin account in AWS with API access, and configure Serverless:

    # configure
    serverless config credentials --provider aws --key XXXXXX --secret XXXXXX --profile serverless-admin

    # deploy
    serverless deploy --aws-profile serverless-admin

    # update only the function code
    serverless deploy function --function cogserv

    # update only the configuration
    serverless deploy function --function cogserv --update-config

    # remove everything
    serverless remove

## Notes

### Raster Colorizer

Colorizing of the raster data is done based on several keys which may be defined in one of two ways:

* As query string params to the endpoint (for on the fly colorization).
* As metadata parameters in the original geotiff file. Not sure about length of metadata items, might be too small. 
* Maybe as a .json sidecar file to the original tiff.

#### Keys

(Not all options are implemented yet.)

`version`

Version info.

`bands`

Select the band data that are needed for the visualization. For a single-band pseudocolor, simply use the band number. For an RGB or RGBA image just specify the bands to map to the respective channel. Colormaps (and all other options below) can only be applied when one band is selected.

`colormap`

A colormap may be defined as a string with a lowercase colormap name such as `spectral` or `blues`. You may reverse the colormap by appending `_i` to the name, for example `spectral_i`. 

A colormap may also be defined as a comma-separated list of colors, for example: `red,orange,yellow,green` or as hex colors: `ffffff,000000`. The color `none` is transparent.


`ranges` 

Ranges describes how values in the dataset are mapped to the colormap. 

You may use absolute values, then `20,80` will map `20` to the start of the colormap, and `80` to the end.

You may use statistics to define ranges, which are replaced by the corresponding value in the raster. In that case a ranges parameter of `min,max` will map the minimum and maximum to the beginning and end of the colormap. It is also possible to use percentiles such as `q50` or `q95`, or percentages between the minimum and maximum value as `p25`.

There are some special values possible to create equally divided ranges. For example `qqqq` is the same as `q25,q50,q75`, and `ppp` is the same as `p33,p66`, and `bbbbb` will break the value range into 5 values with nice 'breaks'.


To be able to use the statistics and special values in ranges the `v_cdf` must be defined.

`interp` 

One of `linear`, `discrete`, or `exact`. This defines how the values described in `v_ranges` are to be interpreted. 


`labels`

    Labels for `interp=linear` will be displayed as:

    Label1     Label2        Label3       Label4 <--- labels here
    |            |             |             |
    +----------------------------------------+
    | %%%%%%%% colormap gradient here %%%%%% |
    +----------------------------------------+
    10     20     30     40     50    60    70   <--- values here

    Labels for `interp=discrete` or `interp=exact` will be displayed as:

    +-----+
    | %%% |  10-20  Label 1
    +-----+
    +-----+
    | %%% |  20-30  Label 2
    +-----+
    (etc)


`cdf`

A cumulative distribution function that describes the distribution of data in the raster. The `cdf` is a comma separated list of percentile values, with the first value always representing the minimum, the last value representing the maximum, and the values in the middle everything inbetween. For example, a `v_cdf=10,20,30,40,50` means 10 is the minimum, 50 the maximum value in the dataset, and 20, 30, and 40 are the 25th, 50th, and 75 percentile. You may provide as many values in the middle as you desire for increased accuracy.


#### Examples

Land cover classification:

    bands=1
    title=Land Cover (-)
    colormap=blue,green,yellow
    ranges=210,32,33
    interp=discrete
    labels=Water,Forest,Cropland

Elevation model:

    bands=1
    title=Elevation (m)
    colormap=schwarzwald
    ranges=min,max
    interp=linear
    labels=


RGB images:

    bands=1,2,3
    title=Photo image

False color composite:

    bands=2,3,4
    title=False color composite map

Erosion Risk Map with values in raster of soil loss between 0-300

    bands=1
    title=Soil loss (t/ha)
    colormap=green,yellow,orange,red,darkred
    ranges=0,10,50,100,200
    interp=discrete
    labels=Very low risk,Low risk,Medium risk,High Risk,Very high risk


