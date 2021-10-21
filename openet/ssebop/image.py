import datetime
import pprint
import re

import ee
import openet.core.common
# TODO: import utils from common
# import openet.core.utils as utils

from openet.ssebop import landsat
from openet.ssebop import model
from openet.ssebop import utils


PROJECT_FOLDER = 'projects/earthengine-legacy/assets/projects/usgs-ssebop'
# PROJECT_FOLDER = 'projects/usgs-ssebop'


def lazy_property(fn):
    """Decorator that makes a property lazy-evaluated

    https://stevenloria.com/lazy-properties/
    """
    attr_name = '_lazy_' + fn.__name__

    @property
    def _lazy_property(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, fn(self))
        return getattr(self, attr_name)
    return _lazy_property


class Image():
    """Earth Engine based SSEBop Image"""

    def __init__(
            self, image,
            et_reference_source=None,
            et_reference_band=None,
            et_reference_factor=None,
            et_reference_resample=None,
            et_reference_date_type=None,
            dt_source='DAYMET_MEDIAN_V2',
            elev_source=None,
            tcorr_source='DYNAMIC',
            tmax_source='DAYMET_MEDIAN_V2',
            elr_flag=False,
            dt_min=5,
            dt_max=25,
            et_fraction_type='alfalfa',
            # reflectance_type='TOA',
            reflectance_type='SR',
            **kwargs,
        ):
        """Construct a generic SSEBop Image

        Parameters
        ----------
        image : ee.Image
            A "prepped" SSEBop input image.
            Image must have bands: "ndvi" and "lst".
            Image must have properties: 'system:id', 'system:index', and
                'system:time_start'.
        et_reference_source : str, float, optional
            Reference ET source (the default is None).
            Parameter is required if computing 'et' or 'et_reference'.
        et_reference_band : str, optional
            Reference ET band name (the default is None).
            Parameter is required if computing 'et' or 'et_reference'.
        et_reference_factor : float, None, optional
            Reference ET scaling factor.  The default is None which is
            equivalent to 1.0 (or no scaling).
        et_reference_resample : {'nearest', 'bilinear', 'bicubic', None}, optional
            Reference ET resampling.  The default is None which is equivalent
            to nearest neighbor resampling.
        dt_source : {'DAYMET_MEDIAN_V0', 'DAYMET_MEDIAN_V1', or float}, optional
            dT source keyword (the default is 'DAYMET_MEDIAN_V1').
        elev_source : {'ASSET', 'GTOPO', 'NED', 'SRTM', or float}, optional
            Elevation source keyword (the default is None).
        tcorr_source : {'DYNAMIC', 'GRIDDED', 'SCENE_GRIDDED',
                        'SCENE', 'SCENE_DAILY', 'SCENE_MONTHLY',
                        'SCENE_ANNUAL', 'SCENE_DEFAULT', or float}, optional
            Tcorr source keyword (the default is 'DYNAMIC').
        tmax_source : {'CIMIS', 'DAYMET_V3', 'DAYMET_V4', 'GRIDMET',
                       'DAYMET_MEDIAN_V2', 'CIMIS_MEDIAN_V1', 'GRIDMET_MEDIAN_V1',
                       collection ID, or float}, optional
            Maximum air temperature source.  The default is
            'projects/usgs-ssebop/tmax/daymet_v3_median_1980_2018'.
        elr_flag : bool, str, optional
            If True, apply Elevation Lapse Rate (ELR) adjustment
            (the default is False).
        dt_min : float, optional
            Minimum allowable dT [K] (the default is 6).
        dt_max : float, optional
            Maximum allowable dT [K] (the default is 25).
        et_fraction_type : {'alfalfa', 'grass'}, optional
            ET fraction  (the default is 'alfalfa').
        reflectance_type : {'SR', 'TOA'}, optional
            Used to select the set the Tcorr NDVI thresholds
            (the default is 'TOA').
        kwargs : dict, optional
            tmax_resample : {'nearest', 'bilinear'}
            dt_resample : {'nearest', 'bilinear'}
            tcorr_resample : {'nearest', 'bilinear'}
            min_pixels_per_image : int
            min_pixels_per_grid_cell : int
            min_grid_cells_per_image : int

        Notes
        -----
        Input image must have a Landsat style 'system:index' in order to
        lookup Tcorr value from table asset.  (i.e. LC08_043033_20150805)

        """
        self.image = ee.Image(image)

        # Set as "lazy_property" below in order to return custom properties
        # self.lst = self.image.select('lst')
        # self.ndvi = self.image.select('ndvi')

        # Copy system properties
        self._id = self.image.get('system:id')
        self._index = self.image.get('system:index')
        self._time_start = self.image.get('system:time_start')
        self._properties = {
            'system:index': self._index,
            'system:time_start': self._time_start,
            'image_id': self._id,
        }

        # Build SCENE_ID from the (possibly merged) system:index
        scene_id = ee.List(ee.String(self._index).split('_')).slice(-3)
        self._scene_id = ee.String(scene_id.get(0)).cat('_')\
            .cat(ee.String(scene_id.get(1))).cat('_')\
            .cat(ee.String(scene_id.get(2)))

        # Build WRS2_TILE from the scene_id
        self._wrs2_tile = ee.String('p').cat(self._scene_id.slice(5, 8))\
            .cat('r').cat(self._scene_id.slice(8, 11))

        # Set server side date/time properties using the 'system:time_start'
        self._date = ee.Date(self._time_start)
        self._year = ee.Number(self._date.get('year'))
        self._month = ee.Number(self._date.get('month'))
        self._start_date = ee.Date(utils.date_to_time_0utc(self._date))
        self._end_date = self._start_date.advance(1, 'day')
        self._doy = ee.Number(self._date.getRelative('day', 'year')).add(1).int()
        self._cycle_day = self._start_date.difference(
            ee.Date.fromYMD(1970, 1, 3), 'day').mod(8).add(1).int()

        # Reference ET parameters
        self.et_reference_source = et_reference_source
        self.et_reference_band = et_reference_band
        self.et_reference_factor = et_reference_factor
        self.et_reference_resample = et_reference_resample
        self.et_reference_date_type = et_reference_date_type

        # Check reference ET parameters
        if et_reference_factor and not utils.is_number(et_reference_factor):
            raise ValueError('et_reference_factor must be a number')
        if et_reference_factor and self.et_reference_factor < 0:
            raise ValueError('et_reference_factor must be greater than zero')
        et_reference_resample_methods = ['nearest', 'bilinear', 'bicubic']
        if (et_reference_resample and
                et_reference_resample.lower() not in et_reference_resample_methods):
            raise ValueError('unsupported et_reference_resample method')
        et_reference_date_type_methods = ['doy', 'daily']
        if (et_reference_date_type and
                et_reference_date_type.lower() not in et_reference_date_type_methods):
            raise ValueError('unsupported et_reference_date_type method')

        # Model input parameters
        self._dt_source = dt_source
        self._elev_source = elev_source
        self._tcorr_source = tcorr_source
        self._tmax_source = tmax_source
        self._elr_flag = elr_flag
        self._dt_min = float(dt_min)
        self._dt_max = float(dt_max)

        # Convert elr_flag from string to bool if necessary
        if type(self._elr_flag) is str:
            if self._elr_flag.upper() in ['TRUE']:
                self._elr_flag = True
            elif self._elr_flag.upper() in ['FALSE']:
                self._elr_flag = False
            else:
                raise ValueError('elr_flag "{}" could not be interpreted as '
                                 'bool'.format(self._elr_flag))

        # ET fraction type
        # CGM - Should et_fraction_type be set as a kwarg instead?
        if et_fraction_type.lower() not in ['alfalfa', 'grass']:
            raise ValueError('et_fraction_type must "alfalfa" or "grass"')
        self.et_fraction_type = et_fraction_type.lower()
        # if 'et_fraction_type' in kwargs.keys():
        #     self.et_fraction_type = kwargs['et_fraction_type'].lower()
        # else:
        #     self.et_fraction_type = 'alfalfa'

        self.reflectance_type = reflectance_type

        # Image projection and geotransform
        self.crs = image.projection().crs()
        self.transform = ee.List(ee.Dictionary(
            ee.Algorithms.Describe(image.projection())).get('transform'))
        # self.crs = image.select([0]).projection().getInfo()['crs']
        # self.transform = image.select([0]).projection().getInfo()['transform']

        """Keyword arguments"""
        # CGM - What is the right way to process kwargs with default values?
        self.kwargs = kwargs

        # CGM - Should these be checked in the methods they are used in instead?
        # Set the resample method as properties so they can be modified
        if 'dt_resample' in kwargs.keys():
            self._dt_resample = kwargs['dt_resample'].lower()
        else:
            self._dt_resample = 'bilinear'
        if 'tmax_resample' in kwargs.keys():
            self._tmax_resample = kwargs['tmax_resample'].lower()
        else:
            self._tmax_resample = 'bilinear'
        if 'tcorr_resample' in kwargs.keys():
            self._tcorr_resample = kwargs['tcorr_resample'].lower()
        else:
            self._tcorr_resample = 'bilinear'

        """Gridded Tcorr keyword arguments"""
        # TODO: This should probably be moved into tcorr_gridded()
        if 'min_pixels_per_grid_cell' in kwargs.keys():
            self.min_pixels_per_grid_cell = kwargs['min_pixels_per_grid_cell']
        else:
            self.min_pixels_per_grid_cell = 10

        # TODO: This should probably be moved into tcorr_gridded()
        if 'min_grid_cells_per_image' in kwargs.keys():
            self.min_grid_cells_per_image = kwargs['min_grid_cells_per_image']
        else:
            self.min_grid_cells_per_image = 5

        # DEADBEEF - This is checked in tcorr() since the GRIDDED and DYNAMIC
        #   options have different defaults
        # if 'min_pixels_per_image' in kwargs.keys():
        #     self.min_pixels_per_image = kwargs['min_pixels_per_image']
        # else:
        #     self.min_pixels_per_image = 250

    def calculate(self, variables=['et', 'et_reference', 'et_fraction']):
        """Return a multiband image of calculated variables

        Parameters
        ----------
        variables : list

        Returns
        -------
        ee.Image

        """
        output_images = []
        for v in variables:
            if v.lower() == 'et':
                output_images.append(self.et.float())
            elif v.lower() == 'et_fraction':
                output_images.append(self.et_fraction.float())
            elif v.lower() == 'et_reference':
                output_images.append(self.et_reference.float())
            elif v.lower() == 'lst':
                output_images.append(self.lst.float())
            elif v.lower() == 'mask':
                output_images.append(self.mask)
            elif v.lower() == 'ndvi':
                output_images.append(self.ndvi.float())
            # elif v.lower() == 'qa':
            #     output_images.append(self.qa)
            elif v.lower() == 'quality':
                output_images.append(self.quality)
            elif v.lower() == 'time':
                output_images.append(self.time)
            else:
                raise ValueError('unsupported variable: {}'.format(v))

        return ee.Image(output_images).set(self._properties)

    @lazy_property
    def et_fraction(self):
        """Fraction of reference ET"""

        # Adjust air temperature based on elevation (Elevation Lapse Rate)
        # TODO: Eventually point thisat the model.elr_adjust() function instead
        if self._elr_flag:
            tmax = ee.Image(model.lapse_adjust(self.tmax, ee.Image(self.elev)))
        else:
            tmax = self.tmax

        et_fraction = model.et_fraction(
            lst=self.lst, tmax=tmax, tcorr=self.tcorr, dt=self.dt)

        # TODO: Add support for setting the conversion source dataset
        # TODO: Interpolate "instantaneous" ETo and ETr?
        # TODO: Move openet.refetgee import to top?
        # TODO: Check if etr/eto is right (I think it is)
        if self.et_fraction_type.lower() == 'grass':
            import openet.refetgee
            nldas_coll = ee.ImageCollection('NASA/NLDAS/FORA0125_H002')\
                .select(['temperature', 'specific_humidity', 'shortwave_radiation',
                         'wind_u', 'wind_v'])
            
            # Interpolating hourly NLDAS to the Landsat scene time
            # CGM - The 2 hour window is useful in case an image is missing
            #   I think EEMETRIC is using a 4 hour window
            # CGM - Need to check if the NLDAS images are instantaneous
            #   or some sort of average of the previous or next hour
            time_start = ee.Number(self._time_start)
            nldas_prev_img = ee.Image(nldas_coll
                .filterDate(time_start.subtract(2 * 60 * 60 * 1000), time_start)
                .limit(1, 'system:time_start', False).first())
            nldas_next_img = ee.Image(nldas_coll
                .filterDate(time_start, time_start.add(2 * 60 * 60 * 1000))
                .first())
            nldas_prev_time = ee.Number(nldas_prev_img.get('system:time_start'))
            nldas_next_time = ee.Number(nldas_next_img.get('system:time_start'))
            time_ratio = time_start.subtract(nldas_prev_time)\
                .divide(nldas_next_time.subtract(nldas_prev_time))
            nldas_img = nldas_next_img.subtract(nldas_prev_img)\
                .multiply(time_ratio).add(nldas_prev_img)\
                .set({'system:time_start': self._time_start})

            # # DEADBEEF - Select NLDAS image before the Landsat scene time
            # nldas_img = ee.Image(nldas_coll
            #     .filterDate(self._date.advance(-1, 'hour'), self._date)
            #     .first())

            et_fraction = et_fraction\
                .multiply(openet.refetgee.Hourly.nldas(nldas_img).etr)\
                .divide(openet.refetgee.Hourly.nldas(nldas_img).eto)

        return et_fraction.set(self._properties) \
            .set({'tcorr_index': self.tcorr.get('tcorr_index'),
                  'et_fraction_type': self.et_fraction_type.lower()})

    @lazy_property
    def et_reference(self):
        """Reference ET for the image date"""
        if utils.is_number(self.et_reference_source):
            # Interpret numbers as constant images
            # CGM - Should we use the ee_types here instead?
            #   i.e. ee.ee_types.isNumber(self.et_reference_source)
            et_reference_img = ee.Image.constant(self.et_reference_source)
        elif type(self.et_reference_source) is str:
            # Assume a string source is an image collection ID (not an image ID)
            if (self.et_reference_date_type is None or
                    self.et_reference_date_type.lower() == 'daily'):
                # Assume the collection is daily with valid system:time_start values
                et_reference_coll = ee.ImageCollection(self.et_reference_source)\
                    .filterDate(self._start_date, self._end_date)\
                    .select([self.et_reference_band])
            elif self.et_reference_date_type.lower() == 'doy':
                # Assume the image collection is a climatology with a "DOY" property
                et_reference_coll = ee.ImageCollection(self.et_reference_source)\
                    .filter(ee.Filter.rangeContains('DOY', self._doy, self._doy))\
                    .select([self.et_reference_band])
                #     .limit(1, 'system:time_start', True)

                # # CGM - Is this mapped function over GRIDMET really needed?
                # #   Couldn't you just filter the source to the image DOY
                # def et_reference_replace_daily(image):
                #     """Mapping function to get daily time_start and system:index
                #
                #     Returns the doy-based reference et with daily time properties from GRIDMET
                #     """
                #     image_date = ee.Algorithms.Date(image.get("system:time_start"))
                #     doy = ee.Number(image_date.getRelative('day', 'year')).add(1).double()
                #     coll_doy = ee.ImageCollection(self.et_reference_source)\
                #         .filter(ee.Filter.rangeContains('DOY', doy, doy)) \
                #         .select([self.et_reference_band]).mean() #.first() returns a FC not IC
                #     return coll_doy.copyProperties(image, ['system:index', 'system:time_start'])
                # # Map over the GRIDMET collection to get a collection with the
                # #   a single image for the target date
                # et_reference_coll = ee.ImageCollection(('IDAHO_EPSCOR/GRIDMET')) \
                #     .filterDate(self._start_date, self._end_date) \
                #     .select([self.et_reference_band])\
                #     .map(et_reference_replace_daily)
            else:
                raise ValueError('unsupported et_reference_date_type: {}'.format(
                    self.et_reference_date_type))

            et_reference_img = ee.Image(et_reference_coll.first())
            if self.et_reference_resample in ['bilinear', 'bicubic']:
                et_reference_img = et_reference_img\
                    .resample(self.et_reference_resample)
        # elif type(self.et_reference_source) is list:
        #     # Interpret as list of image collection IDs to composite/mosaic
        #     #   i.e. Spatial CIMIS and GRIDMET
        #     # CGM - Need to check the order of the collections
        #     et_reference_coll = ee.ImageCollection([])
        #     for coll_id in self.et_reference_source:
        #         coll = ee.ImageCollection(coll_id)\
        #             .select([self.et_reference_band])\
        #             .filterDate(self.start_date, self.end_date)
        #         et_reference_img = et_reference_coll.merge(coll)
        #     et_reference_img = et_reference_coll.mosaic()
        # elif isinstance(self.et_reference_source, computedobject.ComputedObject):
        #     # Interpret computed objects as image collections
        #     et_reference_coll = ee.ImageCollection(self.et_reference_source)\
        #         .select([self.et_reference_band])\
        #         .filterDate(self.start_date, self.end_date)
        else:
            raise ValueError('unsupported et_reference_source: {}'.format(
                self.et_reference_source))

        if self.et_reference_factor:
            et_reference_img = et_reference_img.multiply(self.et_reference_factor)

        # Map ETr values directly to the input (i.e. Landsat) image pixels
        # The benefit of this is the ETr image is now in the same crs as the
        #   input image.  Not all models may want this though.
        # Note, doing this will cause the reference ET to be cloud masked.
        # CGM - Should the output band name match the input ETr band name?
        return self.ndvi.multiply(0).add(et_reference_img)\
            .rename(['et_reference']).set(self._properties)

    @lazy_property
    def et(self):
        """Actual ET as fraction of reference times"""
        return self.et_fraction.multiply(self.et_reference) \
            .rename(['et']).set(self._properties)

    @lazy_property
    def lst(self):
        """Input land surface temperature (LST) [K]"""
        return self.image.select(['lst']).set(self._properties)

    @lazy_property
    def mask(self):
        """Mask of all active pixels (based on the final et_fraction)"""
        return self.et_fraction.multiply(0).add(1).updateMask(1)\
            .rename(['mask']).set(self._properties).uint8()

    @lazy_property
    def ndvi(self):
        """Input normalized difference vegetation index (NDVI)"""
        return self.image.select(['ndvi']).set(self._properties)

    @lazy_property
    def quality(self):
        """Set quality to 1 for all active pixels (for now)"""
        return self.mask\
            .rename(['quality']).set(self._properties)

    @lazy_property
    def time(self):
        """Return an image of the 0 UTC time (in milliseconds)"""
        return self.mask\
            .double().multiply(0).add(utils.date_to_time_0utc(self._date))\
            .rename(['time']).set(self._properties)

    @lazy_property
    def dt(self):
        """

        Returns
        -------
        ee.Image

        Raises
        ------
        ValueError
            If `self._dt_source` is not supported.

        """
        if utils.is_number(self._dt_source):
            dt_img = ee.Image.constant(float(self._dt_source))
        # Use precomputed dT median assets
        elif self._dt_source.upper() == 'DAYMET_MEDIAN_V0':
            dt_coll = ee.ImageCollection(PROJECT_FOLDER + '/dt/daymet_median_v0')\
                .filter(ee.Filter.calendarRange(self._doy, self._doy, 'day_of_year'))
            dt_img = ee.Image(dt_coll.first())
        elif self._dt_source.upper() == 'DAYMET_MEDIAN_V1':
            dt_coll = ee.ImageCollection(PROJECT_FOLDER + '/dt/daymet_median_v1')\
                .filter(ee.Filter.calendarRange(self._doy, self._doy, 'day_of_year'))
            dt_img = ee.Image(dt_coll.first())
        elif self._dt_source.upper() == 'DAYMET_MEDIAN_V2':
            dt_coll = ee.ImageCollection(PROJECT_FOLDER + '/dt/daymet_median_v2')\
                .filter(ee.Filter.calendarRange(self._doy, self._doy, 'day_of_year'))
            dt_img = ee.Image(dt_coll.first())        # Compute dT for the target date
        elif self._dt_source.upper() == 'CIMIS':
            input_img = ee.Image(
                ee.ImageCollection('projects/earthengine-legacy/assets/'
                                   'projects/climate-engine/cimis/daily')\
                    .filterDate(self._start_date, self._end_date)\
                    .select(['Tx', 'Tn', 'Rs', 'Tdew'])
                    .first())
            # Convert units to T [K], Rs [MJ m-2 d-1], ea [kPa]
            # Compute Ea from Tdew
            dt_img = model.dt(
                tmax=input_img.select(['Tx']).add(273.15),
                tmin=input_img.select(['Tn']).add(273.15),
                rs=input_img.select(['Rs']),
                ea=input_img.select(['Tdew']).add(237.3).pow(-1)
                    .multiply(input_img.select(['Tdew']))\
                    .multiply(17.27).exp().multiply(0.6108).rename(['ea']),
                elev=self.elev,
                doy=self._doy)
        elif self._dt_source.upper() == 'DAYMET':
            input_img = ee.Image(
                ee.ImageCollection('NASA/ORNL/DAYMET_V3')\
                    .filterDate(self._start_date, self._end_date)\
                    .select(['tmax', 'tmin', 'srad', 'dayl', 'vp'])
                    .first())
            # Convert units to T [K], Rs [MJ m-2 d-1], ea [kPa]
            # Solar unit conversion from DAYMET documentation:
            #   https://daymet.ornl.gov/overview.html
            dt_img = model.dt(
                tmax=input_img.select(['tmax']).add(273.15),
                tmin=input_img.select(['tmin']).add(273.15),
                rs=input_img.select(['srad'])\
                    .multiply(input_img.select(['dayl'])).divide(1000000),
                ea=input_img.select(['vp'], ['ea']).divide(1000),
                elev=self.elev,
                doy=self._doy)
        elif self._dt_source.upper() == 'GRIDMET':
            input_img = ee.Image(
                ee.ImageCollection('IDAHO_EPSCOR/GRIDMET')\
                    .filterDate(self._start_date, self._end_date)\
                    .select(['tmmx', 'tmmn', 'srad', 'sph'])
                    .first())
            # Convert units to T [K], Rs [MJ m-2 d-1], ea [kPa]
            q = input_img.select(['sph'], ['q'])
            pair = self.elev.multiply(-0.0065).add(293.0).divide(293.0).pow(5.26)\
                .multiply(101.3)
            # pair = self.elev.expression(
            #     '101.3 * pow((293.0 - 0.0065 * elev) / 293.0, 5.26)',
            #     {'elev': self.elev})
            dt_img = model.dt(
                tmax=input_img.select(['tmmx']),
                tmin=input_img.select(['tmmn']),
                rs=input_img.select(['srad']).multiply(0.0864),
                ea=q.multiply(0.378).add(0.622).pow(-1).multiply(q)\
                    .multiply(pair).rename(['ea']),
                elev=self.elev,
                doy=self._doy)
        else:
            raise ValueError('Invalid dt_source: {}\n'.format(self._dt_source))

        if (self._dt_resample and
                self._dt_resample.lower() in ['bilinear', 'bicubic']):
            dt_img = dt_img.resample(self._dt_resample)
        # TODO: A reproject call may be needed here also
        # dt_img = dt_img.reproject(self.crs, self.transform)

        return dt_img.clamp(self._dt_min, self._dt_max).rename('dt')

    @lazy_property
    def elev(self):
        """Elevation [m]

        Returns
        -------
        ee.Image

        Raises
        ------
        ValueError
            If `self._elev_source` is not supported.

        """
        if self._elev_source is None:
            raise ValueError('elev_source was not set')
        elif utils.is_number(self._elev_source):
            elev_image = ee.Image.constant(float(self._elev_source))
        elif self._elev_source.upper() == 'ASSET':
            elev_image = ee.Image(PROJECT_FOLDER + '/srtm_1km')
        elif self._elev_source.upper() == 'GTOPO':
            elev_image = ee.Image('USGS/GTOPO30')
        elif self._elev_source.upper() == 'NED':
            elev_image = ee.Image('USGS/NED')
        elif self._elev_source.upper() == 'SRTM':
            elev_image = ee.Image('USGS/SRTMGL1_003')
        elif (self._elev_source.lower().startswith('projects/') or
              self._elev_source.lower().startswith('users/')):
            elev_image = ee.Image(self._elev_source)
        else:
            raise ValueError('Unsupported elev_source: {}\n'.format(
                self._elev_source))

        return elev_image.select([0], ['elev'])

    @lazy_property
    def tcorr(self):
        """Get Tcorr from pre-computed assets for each Tmax source

        Returns
        -------


        Raises
        ------
        ValueError
            If `self._tcorr_source` is not supported.

        Notes
        -----
        Tcorr Index values indicate which level of Tcorr was used
          0 - Gridded blended cold/hot Tcorr (*)
          1 - Gridded cold Tcorr
          2 - Gridded hot Tcorr (*)
          3 - Scene specific Tcorr
          4 - Mean monthly Tcorr per WRS2 tile
          5 - Mean seasonal Tcorr per WRS2 tile (*)
          6 - Mean annual Tcorr per WRS2 tile
          7 - Default Tcorr
          8 - User defined Tcorr
          9 - No data

        """
        # TODO: Make this a class property or method that we can query
        tcorr_indices = {
            'gridded': 0,
            'gridded_cold': 1,
            'gridded_hot': 2,
            'scene': 3,
            'month': 4,
            'season': 5,
            'annual': 6,
            'default': 7,
            'user': 8,
            'nodata': 9,
        }

        # First check if Tcorr is a number, and if so return
        if utils.is_number(self._tcorr_source):
            return ee.Image.constant(float(self._tcorr_source))\
                .rename(['tcorr']).set({'tcorr_index': tcorr_indices['user']})
        # Then check if Tmax source is a number but Tcorr is a spatial calculation
        elif (utils.is_number(self._tmax_source) and
              (self._tcorr_source.upper() in ['DYNAMIC', 'SCENE_GRIDDED'] or
               'SCENE' in self._tcorr_source.upper())):
            raise ValueError(
                '\nInvalid tmax_source for tcorr: {} / {}\n'.format(
                    self._tcorr_source, self._tmax_source))


        # Set Tcorr folder and collections based on the Tmax source (if needed)
        if 'SCENE_GRIDDED' == self._tcorr_source.upper():
            # Check that there is a tcorr_gridded collection corresponding to the tmax
            # TODO: We should probably also check if the Landsat Collection numbers
            #   match but this is probably good enough for now
            scene_dict = {
                'DAYMET_MEDIAN_V2':
                    f'{PROJECT_FOLDER}/tcorr_gridded/daymet_median_v2_scene',
                # f'daymet_v3_median_1980_2018':
                #     f'{PROJECT_FOLDER}/tcorr_gridded/daymet_median_v2_scene',
                f'daymet_v3_median_1980_2018':
                    f'{PROJECT_FOLDER}/tcorr_gridded/c01/daymet_v3_median_1980_2018',
                f'daymet_v4_median_1980_2019':
                    f'{PROJECT_FOLDER}/tcorr_gridded/c02/daymet_v4_median_1980_2019',
                f'daymet_v4_mean_1981_2010':
                    f'{PROJECT_FOLDER}/tcorr_gridded/c02/daymet_v4_mean_1981_2010',
                f'daymet_v4_mean_1981_2010_elr':
                    f'{PROJECT_FOLDER}/tcorr_gridded/c02/daymet_v4_mean_1981_2010_elr',
            }

            if self._tmax_source.upper() in scene_dict.keys():
                tmax_key = self._tmax_source.upper()
            elif (self._tmax_source.startswith('projects/') and
                    self._tmax_source.split('/')[-1] in scene_dict.keys()):
                tmax_key = self._tmax_source.split('/')[-1]
                print('the tmax key \n', tmax_key)
            else:
                raise ValueError(
                    '\nInvalid tmax_source for tcorr: {} / {}\n'.format(
                        self._tcorr_source, self._tmax_source))

        elif ('DYNAMIC' == self._tcorr_source.upper() or
              self._tcorr_source.upper().startswith('SCENE')):
            # Use the precomputed scene monthly/annual climatologies if Tcorr
            #   can't be computed dynamically.
            scene_dict = {
                'DAYMET_MEDIAN_V2':
                    f'{PROJECT_FOLDER}/tcorr_scene/daymet_median_v2_scene',
                f'daymet_v3_median_1980_2018':
                    f'{PROJECT_FOLDER}/tcorr_scene/daymet_median_v2_scene',
            }
            month_dict = {
                'DAYMET_MEDIAN_V2':
                    f'{PROJECT_FOLDER}/tcorr_scene/daymet_median_v2_monthly',
                f'daymet_v3_median_1980_2018':
                    f'{PROJECT_FOLDER}/tcorr_scene/daymet_median_v2_monthly',
            }
            annual_dict = {
                'DAYMET_MEDIAN_V2':
                    f'{PROJECT_FOLDER}/tcorr_scene/daymet_median_v2_annual',
                f'daymet_v3_median_1980_2018':
                    f'{PROJECT_FOLDER}/tcorr_scene/daymet_median_v2_annual',
            }
            default_dict = {
                'DAYMET_MEDIAN_V2':
                    f'{PROJECT_FOLDER}/tcorr_scene/daymet_median_v2_default',
                f'daymet_v3_median_1980_2018':
                    f'{PROJECT_FOLDER}/tcorr_scene/daymet_median_v2_default',
            }

            # Check Tmax source value
            if self._tmax_source.upper() in scene_dict.keys():
                tmax_key = self._tmax_source.upper()
            elif (self._tmax_source.startswith('projects/') and
                    self._tmax_source.split('/')[-1] in scene_dict.keys()):
                tmax_key = self._tmax_source.split('/')[-1]
            else:
                raise ValueError(
                    '\nInvalid tmax_source for tcorr: {} / {}\n'.format(
                        self._tcorr_source, self._tmax_source))

            # Build the Tcorr scene and fallback collections
            default_coll = ee.ImageCollection(default_dict[tmax_key])\
                .filterMetadata('wrs2_tile', 'equals', self._wrs2_tile)
            annual_coll = ee.ImageCollection(annual_dict[tmax_key])\
                .filterMetadata('wrs2_tile', 'equals', self._wrs2_tile)\
                .select(['tcorr'])
            month_coll = ee.ImageCollection(month_dict[tmax_key])\
                .filterMetadata('wrs2_tile', 'equals', self._wrs2_tile)\
                .filterMetadata('month', 'equals', self._month)\
                .select(['tcorr'])


        # Load the Tcorr image
        # if self._tcorr_source.startswith('projects/'):
        if re.match('projects/.+/tcorr_gridded/.+', self._tcorr_source):
            # Read precomputed tcorr images
            # CGM - Do we need to check that the tmax and tcorr source have the
            #   the same "name"?
            # CGM - How strict should the name matching be in the regex?
            #   For now I'm only matching "tcorr_gridded" folders
            # CGM - This section will need to be modified if monthly fallback
            #   values are needed
            # The following check assumes the tmax source is also a collection ID
            tmax_key = self._tmax_source.split('/')[-1]
            if tmax_key != self._tcorr_source.split('/')[-1]:
                raise ValueError(
                        '\nInvalid tmax_source for tcorr: {} / {}\n'.format(
                            self._tcorr_source, self._tmax_source))

            scene_coll = ee.ImageCollection(self._tcorr_source)\
                .filterDate(self._start_date, self._end_date)\
                .filterMetadata('wrs2_tile', 'equals', self._wrs2_tile)\
                .select(['tcorr'])
            #     .filterMetadata('scene_id', 'equals', scene_id)
            #     .filterMetadata('date', 'equals', self._date)
            return ee.Image(scene_coll.first())
        elif 'GRIDDED' == self._tcorr_source.upper():
            # Compute gridded blended Tcorr for the scene
            tcorr_img = ee.Image(self.tcorr_gridded).select(['tcorr'])
            # e.g. .select([0, 1], ['tcorr', 'count'])

            if self._tcorr_resample.lower() in ['bilinear']:
                tcorr_img = tcorr_img\
                    .resample(self._tcorr_resample.lower())\
                    .reproject(crs=self.crs, crsTransform=self.transform)
            elif self._tcorr_resample.lower() != 'nearest':
                # EE will resample using nearest neighbor by default
                raise ValueError('Unsupported tcorr_resample: {}\n'.format(
                    self._tcorr_resample))

            return tcorr_img

        elif 'GRIDDED_COLD' == self._tcorr_source.upper():
            # Compute gridded Tcorr for the scene
            tcorr_img = ee.Image(self.tcorr_gridded_cold).select(['tcorr'])

            # EE will resample using nearest neighbor by default
            if self._tcorr_resample.lower() in ['bilinear']:
                tcorr_img = tcorr_img\
                    .resample(self._tcorr_resample.lower())\
                    .reproject(crs=self.crs, crsTransform=self.transform)
            elif self._tcorr_resample.lower() != 'nearest':
                raise ValueError('Unsupported tcorr_resample: {}\n'.format(
                    self._tcorr_resample))

            return tcorr_img.rename(['tcorr'])

        elif 'DYNAMIC' == self._tcorr_source.upper():
            # Compute Tcorr dynamically for the scene
            mask_img = ee.Image(default_coll.first()).multiply(0)
            mask_coll = ee.ImageCollection(
                mask_img.updateMask(0).set({'tcorr_index': tcorr_indices['nodata']}))

            # Use a larger default minimum pixel count for dynamic Tcorr
            if 'min_pixels_per_image' in self.kwargs.keys():
                min_pixels_per_image = self.kwargs['min_pixels_per_image']
            else:
                min_pixels_per_image = 1000

            t_stats = ee.Dictionary(self.tcorr_stats)\
                .combine({'tcorr_value': 0, 'tcorr_count': 0}, overwrite=False)
            tcorr_value = ee.Number(t_stats.get('tcorr_value'))
            tcorr_count = ee.Number(t_stats.get('tcorr_count'))
            tcorr_index = tcorr_count.lt(min_pixels_per_image)\
                .multiply(tcorr_indices['nodata'])
            # tcorr_index = ee.Number(ee.Algorithms.If(
            #     tcorr_count.gte(min_pixels_per_image),
            #     0, tcorr_indices['nodata']))

            mask_img = mask_img.add(tcorr_count.gte(min_pixels_per_image))
            scene_img = mask_img.multiply(tcorr_value)\
                .updateMask(mask_img.unmask(0))\
                .rename(['tcorr'])\
                .set({'tcorr_index': tcorr_index})

            # tcorr_coll = ee.ImageCollection([scene_img])
            tcorr_coll = ee.ImageCollection([scene_img])\
                .merge(month_coll).merge(annual_coll)\
                .merge(default_coll).merge(mask_coll)\
                .sort('tcorr_index')

            return ee.Image(tcorr_coll.first()).rename(['tcorr'])

        elif 'SCENE_GRIDDED' == self._tcorr_source.upper():
            # Load precomputed gridded Tcorr images
            scene_coll = ee.ImageCollection(scene_dict[tmax_key])\
                .filterDate(self._start_date, self._end_date)\
                .filterMetadata('wrs2_tile', 'equals', self._wrs2_tile)\
                .select(['tcorr'])
            #     .filterMetadata('scene_id', 'equals', scene_id)
            #     .filterMetadata('date', 'equals', self._date)

            return ee.Image(scene_coll.first())

        elif self._tcorr_source.upper().startswith('SCENE'):
            # Load Tcorr from precomputed scene images with monthly/annual fallbacks
            scene_coll = ee.ImageCollection(scene_dict[tmax_key])\
                .filterDate(self._start_date, self._end_date)\
                .filterMetadata('wrs2_tile', 'equals', self._wrs2_tile)\
                .select(['tcorr'])
            #     .filterMetadata('scene_id', 'equals', scene_id)
            #     .filterMetadata('date', 'equals', self._date)
            default_img = default_coll.first()
            mask_coll = ee.ImageCollection(
                default_img.updateMask(0).set({'tcorr_index': 9}))

            if self._tcorr_source.upper() == 'SCENE':
                tcorr_img = scene_coll\
                    .merge(month_coll).merge(annual_coll)\
                    .merge(default_coll).merge(mask_coll)\
                    .sort('tcorr_index').first()
            # TODO: Calling this DAILY is confusing and should be changed
            elif 'DAILY' in self._tcorr_source.upper():
                tcorr_img = scene_coll.merge(mask_coll).sort('tcorr_index').first()
            elif 'MONTH' in self._tcorr_source.upper():
                tcorr_img = month_coll.merge(mask_coll).sort('tcorr_index').first()
            elif 'ANNUAL' in self._tcorr_source.upper():
                tcorr_img = annual_coll.merge(mask_coll).sort('tcorr_index').first()
            elif 'DEFAULT' in self._tcorr_source.upper():
                tcorr_img = default_coll.merge(mask_coll).sort('tcorr_index').first()
            else:
                raise ValueError(
                    'Invalid tcorr_source: {} / {}\n'.format(
                        self._tcorr_source, self._tmax_source))

            return tcorr_img.rename(['tcorr'])

        else:
            raise ValueError('Unsupported tcorr_source: {}\n'.format(
                self._tcorr_source))

    @lazy_property
    def tmax(self):
        """Get Tmax image from precomputed climatology collections or dynamically

        Returns
        -------
        ee.Image

        Raises
        ------
        ValueError
            If `self._tmax_source` is not supported.

        """
        if utils.is_number(self._tmax_source):
            # Allow Tmax source to be set as a number for testing
            tmax_image = ee.Image.constant(float(self._tmax_source))\
                .rename(['tmax'])\
                .set({'tmax_source': 'custom_{}'.format(self._tmax_source)})
        elif re.match(r'^projects/.+/tmax/.+_(mean|median)_\d{4}_\d{4}(_\w+)?',
                      self._tmax_source):
            # Process Tmax source as a collection ID
            # The new Tmax collections do not have a time_start so filter using
            #   the "doy" property instead
            tmax_coll = ee.ImageCollection(self._tmax_source)\
                .filterMetadata('doy', 'equals', self._doy)
            #     .filterMetadata('doy', 'equals', self._doy.format('%03d'))
            tmax_image = ee.Image(tmax_coll.first())\
                .set({'tmax_source': self._tmax_source})
        elif '_MEDIAN_' in self._tmax_source:
            # Process the existing keyword median sources
            doy_filter = ee.Filter.calendarRange(self._doy, self._doy, 'day_of_year')
            tmax_coll = ee.ImageCollection(
                PROJECT_FOLDER + '/tmax/' + self._tmax_source.lower())
            tmax_image = ee.Image(tmax_coll.filter(doy_filter).first())\
                .set({'tmax_source': self._tmax_source})
        elif self._tmax_source.upper() in ['DAYMET_V3', 'DAYMET_V4']:
            # DAYMET does not include Dec 31st on leap years
            # Adding one extra date to end date to avoid errors here
            # This image be slightly different than the median collection for
            #   Dec 31st on leap years (DOY 366).
            tmax_coll = ee.ImageCollection(f'NASA/ORNL/{self._tmax_source.upper()}')\
                .filterDate(self._start_date, self._end_date.advance(1, 'day'))\
                .select(['tmax']).map(utils.c_to_k)
            tmax_image = ee.Image(tmax_coll.first())\
                .set({'tmax_source': self._tmax_source})
        elif self._tmax_source.upper() == 'CIMIS':
            tmax_coll_id = 'projects/earthengine-legacy/assets/' \
                           'projects/climate-engine/cimis/daily'
            tmax_coll = ee.ImageCollection(tmax_coll_id)\
                .filterDate(self._start_date, self._end_date)\
                .select(['Tx'], ['tmax']).map(utils.c_to_k)
            tmax_image = ee.Image(tmax_coll.first())\
                .set({'tmax_source': self._tmax_source})
        elif self._tmax_source.upper() == 'GRIDMET':
            tmax_coll = ee.ImageCollection('IDAHO_EPSCOR/GRIDMET')\
                .filterDate(self._start_date, self._end_date)\
                .select(['tmmx'], ['tmax'])
            tmax_image = ee.Image(tmax_coll.first())\
                .set({'tmax_source': self._tmax_source})
        # elif self.tmax_source.upper() == 'TOPOWX':
        #     tmax_coll = ee.ImageCollection('X')\
        #         .filterDate(self.start_date, self.end_date)\
        #         .select(['tmmx'], ['tmax'])
        #     tmax_image = ee.Image(tmax_coll.first())\
        #         .set({'tmax_source': self._tmax_source})
        else:
            raise ValueError('Unsupported tmax_source: {}\n'.format(
                self._tmax_source))

        if (self._tmax_resample and
                self._tmax_resample.lower() in ['bilinear', 'bicubic']):
            tmax_image = tmax_image.resample(self._tmax_resample)
        # TODO: A reproject call may be needed here also
        # tmax_image = tmax_image.reproject(self.crs, self.transform)

        return tmax_image

    @classmethod
    def from_image_id(cls, image_id, **kwargs):
        """Constructs an SSEBop Image instance from an image ID

        Parameters
        ----------
        image_id : str
            An earth engine image ID.
            (i.e. 'LANDSAT/LC08/C01/T1_SR/LC08_044033_20170716')
        kwargs
            Keyword arguments to pass through to model init.

        Returns
        -------
        new instance of Image class

        """
        # DEADBEEF - Should the supported image collection IDs and helper
        # function mappings be set in a property or method of the Image class?
        collection_methods = {
            'LANDSAT/LC08/C01/T1_RT_TOA': 'from_landsat_c1_toa',
            'LANDSAT/LE07/C01/T1_RT_TOA': 'from_landsat_c1_toa',
            'LANDSAT/LC08/C01/T1_TOA': 'from_landsat_c1_toa',
            'LANDSAT/LE07/C01/T1_TOA': 'from_landsat_c1_toa',
            'LANDSAT/LT05/C01/T1_TOA': 'from_landsat_c1_toa',
            'LANDSAT/LT04/C01/T1_TOA': 'from_landsat_c1_toa',
            'LANDSAT/LC08/C01/T1_SR': 'from_landsat_c1_sr',
            'LANDSAT/LE07/C01/T1_SR': 'from_landsat_c1_sr',
            'LANDSAT/LT05/C01/T1_SR': 'from_landsat_c1_sr',
            'LANDSAT/LT04/C01/T1_SR': 'from_landsat_c1_sr',
            'LANDSAT/LC08/C02/T1_L2': 'from_landsat_c2_sr',
            'LANDSAT/LE07/C02/T1_L2': 'from_landsat_c2_sr',
            'LANDSAT/LT05/C02/T1_L2': 'from_landsat_c2_sr',
            'LANDSAT/LT04/C02/T1_L2': 'from_landsat_c2_sr',
        }

        try:
            method_name = collection_methods[image_id.rsplit('/', 1)[0]]
        except KeyError:
            raise ValueError('unsupported collection ID: {}'.format(image_id))
        except Exception as e:
            raise Exception('unhandled exception: {}'.format(e))

        method = getattr(Image, method_name)

        return method(ee.Image(image_id), **kwargs)

    @classmethod
    def from_landsat_c1_toa(cls, toa_image, cloudmask_args={}, **kwargs):
        """Returns a SSEBop Image instance from a Landsat Collection 1 TOA image

        Parameters
        ----------
        toa_image : ee.Image, str
            A raw Landsat Collection 1 TOA image or image ID.
        cloudmask_args : dict
            keyword arguments to pass through to cloud mask function
        kwargs : dict
            Keyword arguments to pass through to Image init function

        Returns
        -------
        Image

        """
        toa_image = ee.Image(toa_image)

        # Use the SPACECRAFT_ID property identify each Landsat type
        spacecraft_id = ee.String(toa_image.get('SPACECRAFT_ID'))

        # Rename bands to generic names
        # Rename thermal band "k" coefficients to generic names
        input_bands = ee.Dictionary({
            'LANDSAT_4': ['B1', 'B2', 'B3', 'B4', 'B5', 'B7', 'B6', 'BQA'],
            'LANDSAT_5': ['B1', 'B2', 'B3', 'B4', 'B5', 'B7', 'B6', 'BQA'],
            'LANDSAT_7': ['B1', 'B2', 'B3', 'B4', 'B5', 'B7', 'B6_VCID_1',
                          'BQA'],
            'LANDSAT_8': ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B10', 'BQA'],
        })
        output_bands = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'tir',
                        'BQA']
        k1 = ee.Dictionary({
            'LANDSAT_4': 'K1_CONSTANT_BAND_6',
            'LANDSAT_5': 'K1_CONSTANT_BAND_6',
            'LANDSAT_7': 'K1_CONSTANT_BAND_6_VCID_1',
            'LANDSAT_8': 'K1_CONSTANT_BAND_10',
        })
        k2 = ee.Dictionary({
            'LANDSAT_4': 'K2_CONSTANT_BAND_6',
            'LANDSAT_5': 'K2_CONSTANT_BAND_6',
            'LANDSAT_7': 'K2_CONSTANT_BAND_6_VCID_1',
            'LANDSAT_8': 'K2_CONSTANT_BAND_10',
        })
        prep_image = toa_image\
            .select(input_bands.get(spacecraft_id), output_bands)\
            .set({
                'k1_constant': ee.Number(toa_image.get(k1.get(spacecraft_id))),
                'k2_constant': ee.Number(toa_image.get(k2.get(spacecraft_id))),
            })

        cloud_mask = openet.core.common.landsat_c1_toa_cloud_mask(
            toa_image, **cloudmask_args)

        # Build the input image
        input_image = ee.Image([
            landsat.lst(prep_image),
            landsat.ndvi(prep_image),
        ])

        # Apply the cloud mask and add properties
        input_image = input_image\
            .updateMask(cloud_mask)\
            .set({
                'system:index': toa_image.get('system:index'),
                'system:time_start': toa_image.get('system:time_start'),
                'system:id': toa_image.get('system:id'),
            })

        # Instantiate the class
        return cls(input_image, reflectance_type='TOA', **kwargs)

    @classmethod
    def from_landsat_c1_sr(cls, sr_image, cloudmask_args={}, **kwargs):
        """Returns a SSEBop Image instance from a Landsat Collection 1 SR image

        Parameters
        ----------
        sr_image : ee.Image, str
            A raw Landsat Collection 1 SR image or image ID.
        cloudmask_args : dict
            keyword arguments to pass through to cloud mask function
        kwargs : dict
            Keyword arguments to pass through to Image init function

        Returns
        -------
        Image

        """
        sr_image = ee.Image(sr_image)

        # Use the SATELLITE property identify each Landsat type
        spacecraft_id = ee.String(sr_image.get('SATELLITE'))

        # Rename bands to generic names
        # Rename thermal band "k" coefficients to generic names
        input_bands = ee.Dictionary({
            'LANDSAT_4': ['B1', 'B2', 'B3', 'B4', 'B5', 'B7', 'B6', 'pixel_qa'],
            'LANDSAT_5': ['B1', 'B2', 'B3', 'B4', 'B5', 'B7', 'B6', 'pixel_qa'],
            'LANDSAT_7': ['B1', 'B2', 'B3', 'B4', 'B5', 'B7', 'B6', 'pixel_qa'],
            'LANDSAT_8': ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B10', 'pixel_qa'],
        })
        output_bands = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'tir',
                        'pixel_qa']
        # TODO: Follow up with Simon about adding K1/K2 to SR collection
        # Hardcode values for now
        k1 = ee.Dictionary({
            'LANDSAT_4': 607.76, 'LANDSAT_5': 607.76,
            'LANDSAT_7': 666.09, 'LANDSAT_8': 774.8853})
        k2 = ee.Dictionary({
            'LANDSAT_4': 1260.56, 'LANDSAT_5': 1260.56,
            'LANDSAT_7': 1282.71, 'LANDSAT_8': 1321.0789})
        prep_image = sr_image\
            .select(input_bands.get(spacecraft_id), output_bands)\
            .multiply([0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.1, 1])\
            .set({'k1_constant': ee.Number(k1.get(spacecraft_id)),
                  'k2_constant': ee.Number(k2.get(spacecraft_id))})

        # k1 = ee.Dictionary({
        #     'LANDSAT_4': 'K1_CONSTANT_BAND_6',
        #     'LANDSAT_5': 'K1_CONSTANT_BAND_6',
        #     'LANDSAT_7': 'K1_CONSTANT_BAND_6_VCID_1',
        #     'LANDSAT_8': 'K1_CONSTANT_BAND_10'})
        # k2 = ee.Dictionary({
        #     'LANDSAT_4': 'K2_CONSTANT_BAND_6',
        #     'LANDSAT_5': 'K2_CONSTANT_BAND_6',
        #     'LANDSAT_7': 'K2_CONSTANT_BAND_6_VCID_1',
        #     'LANDSAT_8': 'K2_CONSTANT_BAND_10'})
        # prep_image = sr_image\
        #     .select(input_bands.get(spacecraft_id), output_bands)\
        #     .multiply([0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.0001, 0.1, 1])\
        #     .set({'k1_constant': ee.Number(sr_image.get(k1.get(spacecraft_id))),
        #           'k2_constant': ee.Number(sr_image.get(k2.get(spacecraft_id)))})

        cloud_mask = openet.core.common.landsat_c1_sr_cloud_mask(
            sr_image, **cloudmask_args)

        # Build the input image
        input_image = ee.Image([
            landsat.lst(prep_image),
            landsat.ndvi(prep_image),
        ])

        # Apply the cloud mask and add properties
        input_image = input_image\
            .updateMask(cloud_mask)\
            .set({'system:index': sr_image.get('system:index'),
                  'system:time_start': sr_image.get('system:time_start'),
                  'system:id': sr_image.get('system:id'),
            })

        # Instantiate the class
        return cls(input_image, reflectance_type='SR', **kwargs)

    @classmethod
    def from_landsat_c2_sr(cls, sr_image, cloudmask_args={}, **kwargs):
        """Returns a SSEBop Image instance from a Landsat Collection 2 SR image

        Parameters
        ----------
        sr_image : ee.Image, str
            A raw Landsat Collection 2 SR image or image ID.
        cloudmask_args : dict
            keyword arguments to pass through to cloud mask function
        kwargs : dict
            Keyword arguments to pass through to Image init function

        Returns
        -------
        Image

        """
        sr_image = ee.Image(sr_image)

        # Use the SPACECRAFT_ID property identify each Landsat type
        spacecraft_id = ee.String(sr_image.get('SPACECRAFT_ID'))

        # Rename bands to generic names
        input_bands = ee.Dictionary({
            'LANDSAT_4': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7',
                          'ST_B6', 'QA_PIXEL'],
            'LANDSAT_5': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7',
                          'ST_B6', 'QA_PIXEL'],
            'LANDSAT_7': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7',
                          'ST_B6', 'QA_PIXEL'],
            'LANDSAT_8': ['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7',
                          'ST_B10', 'QA_PIXEL'],
        })
        output_bands = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2',
                        'tir', 'QA_PIXEL']

        prep_image = sr_image \
            .select(input_bands.get(spacecraft_id), output_bands) \
            .multiply([0.0000275, 0.0000275, 0.0000275, 0.0000275,
                       0.0000275, 0.0000275, 0.00341802, 1])\
            .add([-0.2, -0.2, -0.2, -0.2, -0.2, -0.2, 149.0, 1])\

        # Default the cloudmask flags to True if they were not
        # Eventually these will probably all default to True in openet.core
        if 'cirrus_flag' not in cloudmask_args.keys():
            cloudmask_args['cirrus_flag'] = True
        if 'dilate_flag' not in cloudmask_args.keys():
            cloudmask_args['dilate_flag'] = True
        if 'shadow_flag' not in cloudmask_args.keys():
            cloudmask_args['shadow_flag'] = True
        if 'snow_flag' not in cloudmask_args.keys():
            cloudmask_args['snow_flag'] = True

        cloud_mask = openet.core.common.landsat_c2_sr_cloud_mask(
            sr_image, **cloudmask_args)

        # Build the input image
        # Don't compute LST since it is being provided
        input_image = ee.Image([
            prep_image.select(['tir'], ['lst']),
            # landsat.lst(prep_image),
            landsat.ndvi(prep_image),
        ])

        # Apply the cloud mask and add properties
        input_image = input_image\
            .updateMask(cloud_mask)\
            .set({'system:index': sr_image.get('system:index'),
                  'system:time_start': sr_image.get('system:time_start'),
                  'system:id': sr_image.get('system:id'),
            })

        # Instantiate the class
        return cls(input_image, reflectance_type='SR', **kwargs)

    @lazy_property
    def tcorr_image(self):
        """Compute the scene wide Tcorr for the current image

        Returns
        -------
        ee.Image of Tcorr values

        """
        lst = ee.Image(self.lst)
        ndvi = ee.Image(self.ndvi)
        tmax = ee.Image(self.tmax)

        # Compute Tcorr
        tcorr = lst.divide(tmax)

        # Adjust NDVI
        if self.reflectance_type.upper() == 'SR':
            ndvi_threshold = 0.75
        # elif self.reflectance_type.upper() == 'TOA':
        else:
            ndvi_threshold = 0.7

        # Select high NDVI pixels that are also surrounded by high NDVI
        ndvi_smooth_mask = ndvi.focal_mean(radius=90, units='meters')\
            .reproject(crs=self.crs, crsTransform=self.transform)\
            .gte(ndvi_threshold)
        ndvi_buffer_mask = ndvi.gte(ndvi_threshold)\
            .reduceNeighborhood(reducer=ee.Reducer.min(),
                                kernel=ee.Kernel.square(radius=60, units='meters'))

        # Remove low LST and low NDVI
        tcorr_mask = lst.gt(270).And(ndvi_smooth_mask).And(ndvi_buffer_mask)

        return tcorr.updateMask(tcorr_mask).rename(['tcorr'])\
            .set({'system:index': self._index,
                  'system:time_start': self._time_start,
                  'tmax_source': tmax.get('tmax_source'),
                  'tmax_version': tmax.get('tmax_version')})

    @lazy_property
    def tcorr_image_hot(self):
        """Compute the scene wide HOT Tcorr for the current image

        Returns
        -------
        ee.Image of Tcorr values

        """

        lst = ee.Image(self.lst)
        ndvi = ee.Image(self.ndvi)
        tmax = ee.Image(self.tmax)
        dt = ee.Image(self.dt)
        # TODO need lc mask for barren landcover
        lc = None

        # Compute Hot Tcorr (Same as cold tcorr but you subtract dt from Land Surface Temp.)
        hottemp = lst.subtract(dt)
        tcorr = hottemp.divide(tmax)

        # Adjust NDVI thresholds based on reflectance type
        if self.reflectance_type.upper() == 'SR':
            ndvi_threshold = 0.3
        # elif self.reflectance_type.upper() == 'TOA':
        else:
            ndvi_threshold = 0.25

        # Select LOW (but non-negative) NDVI pixels that are also surrounded by LOW NDVI, but
        ndvi_smooth = ndvi.focal_mean(radius=90, units='meters') \
            .reproject(crs=self.crs, crsTransform=self.transform)
        ndvi_smooth_mask = ndvi_smooth.gt(0.0).And(ndvi_smooth.lte(ndvi_threshold))

        #changed the gt and lte to be after the reduceNeighborhood() call
        ndvi_buffer = ndvi.reduceNeighborhood(
            ee.Reducer.min(), ee.Kernel.square(radius=60, units='meters'))
        ndvi_buffer_mask = ndvi_buffer.gt(0.0).And(ndvi_buffer.lte(ndvi_threshold))

        # No longer worry about low LST. Filter out high NDVI vals and mask out areas that aren't 'Barren'
        tcorr_mask = lst.And(ndvi_smooth_mask).And(ndvi_buffer_mask) #.And(lc)

        return tcorr.updateMask(tcorr_mask).rename(['tcorr']) \
            .set({'system:index': self._index,
                  'system:time_start': self._time_start,
                  'tmax_source': tmax.get('tmax_source'),
                  'tmax_version': tmax.get('tmax_version')})

    @lazy_property
    def tcorr_stats(self):
        """Compute the Tcorr 2.5 percentile and count statistics

        Returns
        -------
        dictionary

        """
        return ee.Image(self.tcorr_image).reduceRegion(
            reducer=ee.Reducer.percentile([2.5], outputNames=['value'])\
                .combine(ee.Reducer.count(), '', True),
            crs=self.crs,
            crsTransform=self.transform,
            geometry=self.image.geometry().buffer(1000),
            bestEffort=False,
            maxPixels=2*10000*10000,
            tileScale=1,
        )

    @lazy_property
    def tcorr_gridded(self):
        """Compute a continuous gridded Tcorr for the current image

        Returns
        -------
        ee.Image of Tcorr values

        1.Calculate cold tcorr 5km using the 2.5th percentile of temperatures in degrees K (10pixelCount/5km minimum)
        2.Calculate hot tcorr 5km using the 70th percentile of temperatures in degrees K (10pixelCount/5km minimum)
        3.Calculate COLD Zonal Mean (ee.ReduceNeighborhood()) at:
            a. 1 pixel radius
            b. 2 pixel radius
            c. 3 pixel radius
            d. 4 pixel radius
            e. 5 pixel radius
        4. Calculate HOT Zonal Mean at:
            a. 2 pixel radius
        5. Mosaic hot and cold together. Layers are listed in order of priority given in ee.Reducer.firstNonNull() call:
            a. Original 5km Cold Tcorr
            b. Cold Tcorr Zonal Mean 1 pixel radius
            c. Cold Tcorr Zonal Mean 2 pixel radius
            d. Cold Tcorr Zonal Mean 3 pixel radius
            e. Cold Tcorr Zonal Mean 4 pixel radius
            f. Cold Tcorr Zonal Mean 5 pixel radius
            g. Original 5km Hot Tcorr
            h. Hot Tcorr Zonal Mean 2 pixel radius
        6. Calculate BLENDED Zonal Mean at:
            a. 2 pixel radius
            b. 4 pixel radius
            c. 16 pixel radius
        7. Create a weighted mean from step 6 and step 5:
            a. Where (and if) #5, #6.a, #6.b and #6.c are non-null, weight them 0.4, 0.3, 0.2 and 0.1 respectively
             & mosaic.
            b. Where (and if)  #6.a, #6.b and #6.c are non-null, weight them 0.5, 0.33,and 0.17 respectively & mosaic.
            c. Where (and if)  #6.b and #6.c are non-null, weight them 0.67 and 0.33 respectively & mosaic.

        8. Combine #7.a-#7.c using firstNonNull(). This is ALMOST the final tcorr.

        9. FINALLY: Zonal mean (1 pixel radius) of #8 to smooth and return as FINAL C FACTOR

        Quality Band Explanation
        (RN = ReduceNeighborhood())
        0 - Empty, there was no c factor of any interpolation that covers the cell
        1 - RN 16 of blended filled the cell
        2 - RN 16 and RN 4 coverage
        3 - RN 16, RN4 and RN2 blended coverage
        4* - RN 16, RN4, RN2 and Original C factor Coverage
        ====================================================
        6 - (2 + 4*) 5km original HOT cfactor calculated for cell
        7 - (3 + 4*) 5km original COLD cfactor calculated for cell
        ====================================================
        9** (2 + 3 + 4*) - 5km original HOT and COLD cfactor were calculated for the cell
        in 9**, only the cold was used.
        ====================================================
        9*** We add another value of 9 for an RN05 Cold layer, which takes priority.
        13 ->(9***+ 4*), 15 ->(9*** + 6->[2 + 4*]), 16 -> (9*** + 7->[3 + 4*]) , 18->(9*** + 9**->[2 + 3 + 4*])

        Questions to asnwer
        1. When are we using a cold-based C factor? 18, 16, 15, 13,  (9**, 6, 7 don't occur)
        2. When are we using Hot-based C factor? 14
        3. When are we using a weighted blending to gap-fill? 4-1
        4. Where did ANY hot pixel occur? Score of 14 or 18
        5. Where did the ORIGINAL 5km cold pixel come from (that we actually use)? 18, 16

        """

        # TODO: Define coarse cell-size/transform as a parameter
        # NOTE: This transform is being snapped to the Landsat grid
        #   but this may not be necessary
        coarse_transform = [5000, 0, 15, 0, -5000, 15]

        ## step 1: calculate the gridded cfactor for the cold filtered Tcorr
        # === Cold Tcorr ===
        # Resample to 5km taking 2.5 percentile (equal to Mean-2StDev)

        tcorr_coarse_cold_img = self.tcorr_image \
            .reproject(crs=self.crs, crsTransform=self.transform) \
            .reduceResolution(
                reducer=ee.Reducer.percentile(percentiles=[2.5])
                    .combine(reducer2=ee.Reducer.count(), sharedInputs=True),
                bestEffort=False, maxPixels=30000) \
            .reproject(crs=self.crs, crsTransform=coarse_transform) \
            .select([0, 1], ['tcorr', 'count'])

        # === Hot Tcorr ===
        # Resample to 5km taking 70th percentile # todo - consider toggling up and down.
        tcorr_coarse_hot_img = self.tcorr_image_hot \
            .reproject(crs=self.crs, crsTransform=self.transform) \
            .reduceResolution(
                reducer=ee.Reducer.percentile(percentiles=[70])
                    .combine(reducer2=ee.Reducer.count(), sharedInputs=True),
                bestEffort=False, maxPixels=30000) \
            .reproject(crs=self.crs, crsTransform=coarse_transform) \
            .select([0, 1], ['tcorr', 'count'])

        ### =================== Cold ===================
        # # Deadbeef
        # # Mask cells without enough fine resolution Tcorr cells
        # # The count band is dropped after it is used to mask
        # tcorr_coarse_cold = tcorr_coarse_cold_img.select(['tcorr']) \
        #     .updateMask(tcorr_coarse_cold_img.select(['count'])
        #                 .gte(self.min_pixels_per_grid_cell))
        # change variable names in order to keep same naming conventions lower down.
        tcorr_coarse_cold = tcorr_coarse_cold_img.select(['tcorr'])

        # Count the number of coarse resolution Tcorr cells
        count_coarse_cold = tcorr_coarse_cold \
            .reduceRegion(reducer=ee.Reducer.count(),
                          crs=self.crs, crsTransform=coarse_transform,
                          bestEffort=False, maxPixels=100000)
        tcorr_count_cold = ee.Number(count_coarse_cold.get('tcorr'))

        ### =================== HOT ===================
        # TODO - if there is a Null Image, do we get problems
        # TODO - test export tcorr coarse hot
        # Mask cells without enough fine resolution Tcorr cells
        # The count band is dropped after it is used to mask
        # # Minimum pixel count could be important (to ignore that is...)
        # tcorr_coarse_hot = tcorr_coarse_hot_img.select(['tcorr']) \
        #     .updateMask(tcorr_coarse_hot_img.select(['count'])
        #                 .gte(self.min_pixels_per_grid_cell))
        tcorr_coarse_hot = tcorr_coarse_hot_img.select(['tcorr']) \
            .updateMask(tcorr_coarse_hot_img.select(['count']))

        # Count the number of coarse resolution Tcorr cells
        count_coarse_hot = tcorr_coarse_hot \
            .reduceRegion(reducer=ee.Reducer.count(),
                          crs=self.crs, crsTransform=coarse_transform,
                          bestEffort=False, maxPixels=100000)
        tcorr_count_hot = ee.Number(count_coarse_hot.get('tcorr'))

        # return tcorr_coarse_hot, tcorr_coarse_cold
        # Do reduce neighborhood to interpolate c factor using a square kernel
        tcorr_rn01_cold = tcorr_coarse_cold\
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=1, units='pixels'),
                                skipMasked=False)\
            .reproject(crs=self.crs, crsTransform=coarse_transform)\
            .updateMask(1)
        tcorr_rn02_cold = tcorr_coarse_cold \
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=2, units='pixels'),
                                # kernel=ee.Kernel.square(radius=2, units='pixels'),
                                # optimization='boxcar',
                                skipMasked=False) \
            .reproject(crs=self.crs, crsTransform=coarse_transform) \
            .updateMask(1)
        tcorr_rn03_cold = tcorr_coarse_cold \
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=3, units='pixels'),
                                # kernel=ee.Kernel.square(radius=2, units='pixels'),
                                # optimization='boxcar',
                                skipMasked=False) \
            .reproject(crs=self.crs, crsTransform=coarse_transform) \
            .updateMask(1)
        tcorr_rn04_cold = tcorr_coarse_cold \
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=4, units='pixels'),
                                # kernel=ee.Kernel.square(radius=2, units='pixels'),
                                # optimization='boxcar',
                                skipMasked=False) \
            .reproject(crs=self.crs, crsTransform=coarse_transform) \
            .updateMask(1)
        tcorr_rn05_cold = tcorr_coarse_cold \
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=5, units='pixels'),
                                # kernel=ee.Kernel.square(radius=2, units='pixels'),
                                # optimization='boxcar',
                                skipMasked=False) \
            .reproject(crs=self.crs, crsTransform=coarse_transform) \
            .updateMask(1)

        tcorr_rn02_hot = tcorr_coarse_hot\
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=2, units='pixels'),
                                # kernel=ee.Kernel.square(radius=2, units='pixels'),
                                # optimization='boxcar',
                                skipMasked=False)\
            .reproject(crs=self.crs, crsTransform=coarse_transform)\
            .updateMask(1)


        # First non null mosiac of hot and cold (COLD priority) -> out image goes into rn04 and so on.
        hotCold_mosaic = ee.Image([tcorr_coarse_cold, tcorr_rn01_cold, tcorr_rn02_cold, tcorr_rn03_cold,
                                        tcorr_rn04_cold, tcorr_rn05_cold, tcorr_coarse_hot, tcorr_rn02_hot]) \
            .reduce(ee.Reducer.firstNonNull())
        # # TODO - ...and then the first blended

        # TODO - Try SQUARE Kernel
        tcorr_rn02_blended = hotCold_mosaic \
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=2, units='pixels'),
                                # kernel=ee.Kernel.square(radius=4, units='pixels'),
                                # optimization='boxcar',
                                skipMasked=False) \
            .reproject(crs=self.crs, crsTransform=coarse_transform) \
            .updateMask(1)

        tcorr_rn04_blended = hotCold_mosaic\
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=4, units='pixels'),
                                # kernel=ee.Kernel.square(radius=4, units='pixels'),
                                # optimization='boxcar',
                                skipMasked=False)\
            .reproject(crs=self.crs, crsTransform=coarse_transform)\
            .updateMask(1)
        tcorr_rn16_blended = hotCold_mosaic\
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=16, units='pixels'),
                                # kernel=ee.Kernel.square(radius=16, units='pixels'),
                                # optimization='boxcar',
                                skipMasked=False)\
            .reproject(crs=self.crs, crsTransform=coarse_transform)\
            .updateMask(1)

        # --- In this section we build an image to weight the cfactor
        #   proportionally to how close it is to the original c ---
        # todo - ^^^ tcorr_rno4 and 16 are made above by blending hot and cold and smoothing...
        # we make the mosaic below only to use it as a template for zero_img.
        fm_mosaic = ee.Image([hotCold_mosaic, tcorr_rn02_cold, tcorr_rn04_blended, tcorr_rn16_blended])\
            .reduce(ee.Reducer.firstNonNull())
        # create a zero image to add binary images to, in order to weight the image.
        zero_img = fm_mosaic.multiply(0).updateMask(1)

        ## ===== OLD SCORING =====
        # # We make a series of binary images to map the extent of each layer's c factor
        # score_coarse = zero_img.add(hotCold_rn02_mosaic.gt(0)).updateMask(1)
        # score_02 = zero_img.add(tcorr_rn02.gt(0)).updateMask(1)
        # score_04 = zero_img.add(tcorr_rn04.gt(0)).updateMask(1)
        # score_16 = zero_img.add(tcorr_rn16.gt(0)).updateMask(1)

        ## ===== NEW SCORING =====
        # 0 - Empty, there was no c factor of any interpolation that covers the cell
        # 1 - RN 16 of blended filled the cell
        # 2 - RN 16 and RN 4 coverage
        # 3 - RN 16, RN4 and RN2 blended coverage
        # 5 - 5km original HOT cfactor calculated for cell
        # 6 - 5km original COLD cfactor calculated for cell
        # 8 - 5km original HOT and COLD cfactor were calculated for the cell

        # We make a series of binary images to map the extent of each layer's c factor
        score_null = zero_img.add(hotCold_mosaic.gt(0)).updateMask(1)
        score_02 = zero_img.add(tcorr_rn02_blended.gt(0)).updateMask(1)
        score_04 = zero_img.add(tcorr_rn04_blended.gt(0)).updateMask(1)
        score_16 = zero_img.add(tcorr_rn16_blended.gt(0)).updateMask(1)

        # cold and hot scores
        # These scores are just to help the end user see areas where either
        #   hot or cold images to begin with
        cold_rn05_score = zero_img.add(tcorr_rn05_cold.gt(0)).updateMask(1)
        cold_rn05_score = cold_rn05_score.multiply(9).updateMask(1)
        coldscore = zero_img.add(tcorr_coarse_cold.gt(0)).updateMask(1)
        coldscore = coldscore.multiply(3).updateMask(1)
        hotscore = zero_img.add(tcorr_coarse_hot.gt(0)).updateMask(1)
        hotscore = hotscore.multiply(2).updateMask(1)

        # This layer has a score of 0-3 based on where the binaries overlap.
        # This will help us to know where to apply different weights as directed by G. Senay.
        # TODO - make this into a band of tcorr image!
        total_score_img = ee.Image([score_null, score_02, score_04, score_16])\
            .reduce(ee.Reducer.sum())

        # *WEIGHTED MEAN*
        # Use the score band to mask out the areas of overlap to weight the c factor:
        # for 4:3:2:1
        fm_mosaic_4 = ee.Image([hotCold_mosaic.multiply(0.4).updateMask(1),
                                tcorr_rn02_blended.multiply(0.3).updateMask(1),
                                tcorr_rn04_blended.multiply(0.2).updateMask(1),
                                tcorr_rn16_blended.multiply(0.1).updateMask(1)])\
            .reduce(ee.Reducer.sum())\
            .updateMask(total_score_img.eq(4))
        # for 3:2:1 use weights (3/6, 2/6, 1/6)
        fm_mosaic_3 = ee.Image([tcorr_rn02_blended.multiply(0.5).updateMask(1),
                                tcorr_rn04_blended.multiply(0.33).updateMask(1),
                                tcorr_rn16_blended.multiply(0.17).updateMask(1)]) \
            .reduce(ee.Reducer.sum()) \
            .updateMask(total_score_img.eq(3))
        # for 2:1 use weights (2/3, 1/3)
        fm_mosaic_2 = ee.Image([tcorr_rn04_blended.multiply(0.67).updateMask(1),
                                tcorr_rn16_blended.multiply(0.33).updateMask(1)])\
            .reduce(ee.Reducer.sum())\
            .updateMask(total_score_img.eq(2))
        # for 1 use the value of 16
        fm_mosaic_1 = tcorr_rn16_blended.updateMask(total_score_img.eq(1))

        # Combine the weighted means into a single image using first non-null
        tcorr = ee.Image([fm_mosaic_4, fm_mosaic_3, fm_mosaic_2, fm_mosaic_1])\
            .reduce(ee.Reducer.firstNonNull()).updateMask(1)

        tcorr = tcorr\
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.circle(radius=1, units='pixels'),
                                # kernel=ee.Kernel.square(radius=1, units='pixels'),
                                # optimization='boxcar',
                                skipMasked=False)\
            .reproject(crs=self.crs, crsTransform=coarse_transform)\
            .updateMask(1)

        quality_score_img = ee.Image([total_score_img, hotscore, coldscore, cold_rn05_score])\
            .reduce(ee.Reducer.sum())

        # Set tcorr index to 9 if coarse count is 0
        # This if should be fast but the calculation below works also
        tcorr_index = ee.Algorithms.If(tcorr_count_cold.gt(0), 0, 9)

        return ee.Image([tcorr, quality_score_img]).rename(['tcorr', 'quality'])\
            .set(self._properties)\
            .set({'tcorr_index': tcorr_index,
                  'tcorr_coarse_count_cold': tcorr_count_cold})

    @lazy_property
    def tcorr_gridded_cold(self):
        """Compute a continuous gridded Tcorr for the current image

        Returns
        -------
        ee.Image of Tcorr values

        """
        # TODO: Define coarse cellsize or transform as a parameter
        # NOTE: This transform is being snapped to the Landsat grid
        #   but this may not be necessary
        coarse_transform = [5000, 0, 15, 0, -5000, 15]

        # Resample to 5km taking 2.5 percentile (equal to Mean-2StDev)
        tcorr_coarse_img = self.tcorr_image\
            .reproject(crs=self.crs, crsTransform=self.transform)\
            .reduceResolution(
                reducer=ee.Reducer.percentile(percentiles=[2.5])
                    .combine(reducer2=ee.Reducer.count(), sharedInputs=True),
                bestEffort=True, maxPixels=30000)\
            .reproject(crs=self.crs, crsTransform=coarse_transform)\
            .select([0, 1], ['tcorr', 'count'])

        # Mask cells without enough fine resolution Tcorr cells
        # The count band is dropped after it is used to mask
        # tcorr_coarse = tcorr_coarse_img.select(['tcorr'])\
        #     .updateMask(tcorr_coarse_img.select(['count'])
        #                 .gte(self.min_pixels_per_grid_cell))

        # Count the number of coarse resolution Tcorr cells
        count_coarse = tcorr_coarse_img\
            .reduceRegion(reducer=ee.Reducer.count(), crs=self.crs,
                          crsTransform=coarse_transform,
                          bestEffort=False, maxPixels=100000)
        tcorr_count = ee.Number(count_coarse.get('tcorr'))

        # select only the tcorr band.
        tcorr_coarse = tcorr_coarse_img.select(['tcorr'])

        # Do reduce neighborhood to interpolate c factor
        tcorr_rn02 = tcorr_coarse\
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=2, units='pixels'),
                                skipMasked=False)\
            .reproject(crs=self.crs, crsTransform=coarse_transform)\
            .updateMask(1)

        tcorr_rn04 = tcorr_coarse\
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=4, units='pixels'),
                                skipMasked=False)\
            .reproject(crs=self.crs, crsTransform=coarse_transform)\
            .updateMask(1)

        tcorr_rn16 = tcorr_coarse\
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=16, units='pixels'),
                                skipMasked=False)\
            .reproject(crs=self.crs, crsTransform=coarse_transform)\
            .updateMask(1)

        # rn64 (added to make sure that the whole scene is covered on 3/25/2021)
        tcorr_rn64 = tcorr_coarse \
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=64, units='pixels'),
                                skipMasked=False) \
            .reproject(crs=self.crs, crsTransform=coarse_transform) \
            .updateMask(1)

        # --- In this section we build an image to weight the cfactor
        #   proportionally to how close it is to the original c ---
        fm_mosaic = ee.Image([tcorr_coarse, tcorr_rn02, tcorr_rn04, tcorr_rn16, tcorr_rn64])\
            .reduce(ee.Reducer.firstNonNull())
        zero_img = fm_mosaic.multiply(0).updateMask(1)

        ## ===== SCORING =====
        # 0 - Empty: there was no c factor of any interpolation that covers the cell
        # 1 - RN 64 zonal filled the cell (zonal stats value is not weighted)
        # 2 - RN 64 and RN 16 coverage (weighted)
        # 3 - RN 64, RN16 and RN4 coverage (weighted)
        # 4 - RN 64, RN16, RN4 and RN02 coverage (weighted)
        # 5 - 5km original COLD cfactor calculated for cell (The original value, however, is smoothed by weighting)

        # We make a series of binary images to map the extent of each layer's c factor
        score_coarse = zero_img.add(tcorr_coarse.gt(0)).updateMask(1)
        score_02 = zero_img.add(tcorr_rn02.gt(0)).updateMask(1)
        score_04 = zero_img.add(tcorr_rn04.gt(0)).updateMask(1)
        score_16 = zero_img.add(tcorr_rn16.gt(0)).updateMask(1)
        score_64 = zero_img.add(tcorr_rn64.gt(0)).updateMask(1)

        # This layer has a score of 0-5 based on where the binaries overlap.
        # This will help us to know where to apply different weights as directed by G. Senay.
        total_score_img = ee.Image([score_coarse, score_02, score_04, score_16, score_64])\
            .reduce(ee.Reducer.sum())

        # *WEIGHTED MEAN*
        # Use the score band to mask out the areas of overlap to weight the c factor:

        # Same as 4:3:2:1 below but use weights 75/1000 and 25/1000 for the last two layers to get 1/10
        fm_mosaic_5 = ee.Image([tcorr_coarse.multiply(0.4).updateMask(1),
                                tcorr_rn02.multiply(0.3).updateMask(1),
                                tcorr_rn04.multiply(0.2).updateMask(1),
                                tcorr_rn16.multiply(0.075).updateMask(1),
                                tcorr_rn64.multiply(0.025).updateMask(1)])\
            .reduce(ee.Reducer.sum())\
            .updateMask(total_score_img.eq(5))

        # for 4:3:2:1 use weights (4/10, 3/10, 2/10, 1/10)
        fm_mosaic_4 = ee.Image([tcorr_rn02.multiply(0.4).updateMask(1),
                                tcorr_rn04.multiply(0.3).updateMask(1),
                                tcorr_rn16.multiply(0.2).updateMask(1),
                                tcorr_rn64.multiply(0.1).updateMask(1)])\
            .reduce(ee.Reducer.sum())\
            .updateMask(total_score_img.eq(4))

        # for 3:2:1 use weights (3/6, 2/6, 1/6)
        fm_mosaic_3 = ee.Image([tcorr_rn04.multiply(0.5).updateMask(1),
                                tcorr_rn16.multiply(0.33).updateMask(1),
                                tcorr_rn64.multiply(0.17).updateMask(1)])\
            .reduce(ee.Reducer.sum())\
            .updateMask(total_score_img.eq(3))

        # for 2:1 use weights (2/3, 1/3)
        fm_mosaic_2 = ee.Image([tcorr_rn16.multiply(0.67).updateMask(1),
                                tcorr_rn64.multiply(0.33).updateMask(1)])\
            .reduce(ee.Reducer.sum())\
            .updateMask(total_score_img.eq(2))

        # for 1 use the value of 64
        fm_mosaic_1 = tcorr_rn64.updateMask(total_score_img.eq(1))

        # Combine the weighted means into a single image using first non-null
        tcorr = ee.Image([fm_mosaic_5, fm_mosaic_4, fm_mosaic_3, fm_mosaic_2, fm_mosaic_1])\
            .reduce(ee.Reducer.firstNonNull())

        # Do one more reduce neighborhood to smooth the c factor
        tcorr = tcorr\
            .reduceNeighborhood(reducer=ee.Reducer.mean(),
                                kernel=ee.Kernel.square(radius=1, units='pixels'),
                                skipMasked=False)\
            .reproject(crs=self.crs, crsTransform=coarse_transform)\
            .updateMask(1)

        # Set tcorr index to 9 if coarse count is 0
        # This "if" should be fast but the calculation approach works also
        tcorr_index = ee.Algorithms.If(tcorr_count.gt(0), 1, 9)
        # tcorr_index = tcorr_count.multiply(-1).max(-1).add(1).multiply(8).add(1)

        return ee.Image([tcorr, total_score_img]).rename(['tcorr', 'quality']) \
            .set(self._properties) \
            .set({'tcorr_index': tcorr_index,
                  'tcorr_coarse_count': tcorr_count})
