import datetime
import math
import pprint

import ee

from . import landsat
from . import model
from . import utils
import openet.core.common as common
# TODO: import utils from common
# import openet.core.utils as utils


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
            dt_source='DAYMET_MEDIAN_V0',
            elev_source='SRTM',
            tcorr_source='SCENE',
            tmax_source='DAYMET_MEDIAN_V2',
            elr_flag=False,
            dt_min=6,
            dt_max=25,
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
            Elevation source keyword (the default is 'SRTM').
        tcorr_source : {'FEATURE', 'FEATURE_MONTHLY', 'FEATURE_ANNUAL',
                        'SCENE', 'SCENE_DAILY', 'SCENE_MONTHLY',
                        'SCENE_ANNUAL', 'SCENE_DEFAULT'
                        'IMAGE', 'IMAGE_DAILY', 'IMAGE_MONTHLY',
                        'IMAGE_ANNUAL', 'IMAGE_DEFAULT', or float}, optional
            Tcorr source keyword (the default is 'IMAGE').
        tmax_source : {'CIMIS', 'DAYMET', 'GRIDMET', 'DAYMET_MEDIAN_V2',
                       'TOPOWX_MEDIAN_V0', or float}, optional
            Maximum air temperature source (the default is 'TOPOWX_MEDIAN_V0').
        elr_flag : bool, str, optional
            If True, apply Elevation Lapse Rate (ELR) adjustment
            (the default is False).
        dt_min : float, optional
            Minimum allowable dT [K] (the default is 6).
        dt_max : float, optional
            Maximum allowable dT [K] (the default is 25).
        kwargs : dict, optional
            tmax_resample : {'nearest', 'bilinear'}
            dt_resample : {'nearest', 'bilinear'}

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

        # Check reference ET parameters
        if et_reference_factor and not utils.is_number(et_reference_factor):
            raise ValueError('et_reference_factor must be a number')
        if et_reference_factor and self.et_reference_factor < 0:
            raise ValueError('et_reference_factor must be greater than zero')
        et_reference_resample_methods = ['nearest', 'bilinear', 'bicubic']
        if (et_reference_resample and
                et_reference_resample.lower() not in et_reference_resample_methods):
            raise ValueError('unsupported et_reference_resample method')

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

        # Image projection and geotransform
        self.crs = image.projection().crs()
        self.transform = ee.List(ee.Dictionary(
            ee.Algorithms.Describe(image.projection())).get('transform'))
        # self.crs = image.select([0]).projection().getInfo()['crs']
        # self.transform = image.select([0]).projection().getInfo()['transform']

        # Set the resample method as properties so they can be modified
        if 'dt_resample' in kwargs.keys():
            self._dt_resample = kwargs['dt_resample'].lower()
        else:
            self._dt_resample = 'bilinear'
        if 'tmax_resample' in kwargs.keys():
            self._tmax_resample = kwargs['tmax_resample'].lower()
        else:
            self._tmax_resample = 'bilinear'

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
        et_fraction = model.et_fraction(
            lst=self.lst, tmax=self.tmax, tcorr=self.tcorr, dt=self.dt,
            elr_flag=self._elr_flag, elev=self.elev,
        )

        return et_fraction.set(self._properties) \
            .set({'tcorr_index': self.tcorr.get('tcorr_index')})

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
            et_reference_coll = ee.ImageCollection(self.et_reference_source)\
                .filterDate(self._start_date, self._end_date)\
                .select([self.et_reference_band])
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
        tcorr, tcorr_index = self._tcorr
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
        # Compute dT for the target date
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
        if utils.is_number(self._elev_source):
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
          0 - Scene specific Tcorr
          1 - Mean monthly Tcorr per WRS2 tile
          2 - Mean annual Tcorr per WRS2 tile
          3 - Default Tcorr
          4 - User defined Tcorr
          9 - No data

        """

        # month_field = ee.String('M').cat(ee.Number(self.month).format('%02d'))
        if utils.is_number(self._tcorr_source):
            return ee.Image.constant(float(self._tcorr_source))\
                .rename(['tcorr']).set({'tcorr_index': 4})

        elif 'DYNAMIC' == self._tcorr_source.upper():
            # Compute Tcorr dynamically for the scene
            tcorr_folder = PROJECT_FOLDER + '/tcorr_scene'
            month_dict = {
                'DAYMET_MEDIAN_V2': tcorr_folder + '/daymet_median_v2_monthly',
            }
            annual_dict = {
                'DAYMET_MEDIAN_V2': tcorr_folder + '/daymet_median_v2_annual',
            }
            default_dict = {
                'DAYMET_MEDIAN_V2': tcorr_folder + '/daymet_median_v2_default',
            }

            # Check Tmax source value
            if (utils.is_number(self._tmax_source) or
                    self._tmax_source.upper() not in default_dict.keys()):
                raise ValueError(
                    '\nInvalid tmax_source for tcorr: {} / {}\n'.format(
                        self._tcorr_source, self._tmax_source))
            tmax_key = self._tmax_source.upper()

            default_coll = ee.ImageCollection(default_dict[tmax_key])\
                .filterMetadata('wrs2_tile', 'equals', self._wrs2_tile)
            mask_img = ee.Image(default_coll.first()).multiply(0)

            mask_coll = ee.ImageCollection(
                mask_img.updateMask(0).set({'tcorr_index': 9}))
            annual_coll = ee.ImageCollection(annual_dict[tmax_key])\
                .filterMetadata('wrs2_tile', 'equals', self._wrs2_tile)\
                .select(['tcorr'])
            month_coll = ee.ImageCollection(month_dict[tmax_key])\
                .filterMetadata('wrs2_tile', 'equals', self._wrs2_tile)\
                .filterMetadata('month', 'equals', self._month)\
                .select(['tcorr'])

            # TODO: Allow MIN_PIXEL_COUNT to be set as a parameter to the class
            MIN_PIXEL_COUNT = 1000
            t_stats = ee.Dictionary(self.tcorr_stats)\
                .combine({'tcorr_p5': 0, 'tcorr_count': 0}, overwrite=False)
            tcorr_value = ee.Number(t_stats.get('tcorr_p5'))
            tcorr_count = ee.Number(t_stats.get('tcorr_count'))
            tcorr_index = tcorr_count.lt(MIN_PIXEL_COUNT).multiply(9)
            # tcorr_index = ee.Number(
            #     ee.Algorithms.If(tcorr_count.gte(MIN_PIXEL_COUNT), 0, 9))

            mask_img = mask_img.add(tcorr_count.gte(MIN_PIXEL_COUNT))
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

        elif 'SCENE' in self._tcorr_source.upper():
            tcorr_folder = PROJECT_FOLDER + '/tcorr_scene'
            scene_dict = {
                'DAYMET_MEDIAN_V2': tcorr_folder + '/daymet_median_v2_scene',
            }
            month_dict = {
                'DAYMET_MEDIAN_V2': tcorr_folder + '/daymet_median_v2_monthly',
            }
            annual_dict = {
                'DAYMET_MEDIAN_V2': tcorr_folder + '/daymet_median_v2_annual',
            }
            default_dict = {
                'DAYMET_MEDIAN_V2': tcorr_folder + '/daymet_median_v2_default',
            }

            # Check Tmax source value
            if (utils.is_number(self._tmax_source) or
                    self._tmax_source.upper() not in default_dict.keys()):
                raise ValueError(
                    '\nInvalid tmax_source for tcorr: {} / {}\n'.format(
                        self._tcorr_source, self._tmax_source))
            tmax_key = self._tmax_source.upper()

            default_coll = ee.ImageCollection(default_dict[tmax_key])\
                .filterMetadata('wrs2_tile', 'equals', self._wrs2_tile)
            scene_coll = ee.ImageCollection(scene_dict[tmax_key])\
                .filterDate(self._start_date, self._end_date)\
                .filterMetadata('wrs2_tile', 'equals', self._wrs2_tile)\
                .select(['tcorr'])
            #     .filterMetadata('scene_id', 'equals', scene_id)
            #     .filterMetadata('date', 'equals', self._date)
            month_coll = ee.ImageCollection(month_dict[tmax_key])\
                .filterMetadata('wrs2_tile', 'equals', self._wrs2_tile)\
                .filterMetadata('month', 'equals', self._month)\
                .select(['tcorr'])
            annual_coll = ee.ImageCollection(annual_dict[tmax_key])\
                .filterMetadata('wrs2_tile', 'equals', self._wrs2_tile)\
                .select(['tcorr'])

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

        # elif 'FEATURE' in self._tcorr_source.upper():
        #     # Lookup Tcorr collections by keyword value
        #
        #     scene_coll_dict = {
        #         'CIMIS': PROJECT_FOLDER + '/tcorr/cimis_scene',
        #         'DAYMET': PROJECT_FOLDER + '/tcorr/daymet_scene',
        #         'GRIDMET': PROJECT_FOLDER + '/tcorr/gridmet_scene',
        #         # 'TOPOWX': PROJECT_FOLDER + '/tcorr/topowx_scene',
        #         'CIMIS_MEDIAN_V1': PROJECT_FOLDER + '/tcorr/cimis_median_v1_scene',
        #         'DAYMET_MEDIAN_V0': PROJECT_FOLDER + '/tcorr/daymet_median_v0_scene',
        #         'DAYMET_MEDIAN_V1': PROJECT_FOLDER + '/tcorr/daymet_median_v1_scene',
        #         'GRIDMET_MEDIAN_V1': PROJECT_FOLDER + '/tcorr/gridmet_median_v1_scene',
        #         'TOPOWX_MEDIAN_V0': PROJECT_FOLDER + '/tcorr/topowx_median_v0_scene',
        #         'TOPOWX_MEDIAN_V0B': PROJECT_FOLDER + '/tcorr/topowx_median_v0b_scene',
        #     }
        #     month_coll_dict = {
        #         'CIMIS': PROJECT_FOLDER + '/tcorr/cimis_monthly',
        #         'DAYMET': PROJECT_FOLDER + '/tcorr/daymet_monthly',
        #         'GRIDMET': PROJECT_FOLDER + '/tcorr/gridmet_monthly',
        #         # 'TOPOWX': PROJECT_FOLDER + '/tcorr/topowx_monthly',
        #         'CIMIS_MEDIAN_V1': PROJECT_FOLDER + '/tcorr/cimis_median_v1_monthly',
        #         'DAYMET_MEDIAN_V0': PROJECT_FOLDER + '/tcorr/daymet_median_v0_monthly',
        #         'DAYMET_MEDIAN_V1': PROJECT_FOLDER + '/tcorr/daymet_median_v1_monthly',
        #         'GRIDMET_MEDIAN_V1': PROJECT_FOLDER + '/tcorr/gridmet_median_v1_monthly',
        #         'TOPOWX_MEDIAN_V0': PROJECT_FOLDER + '/tcorr/topowx_median_v0_monthly',
        #         'TOPOWX_MEDIAN_V0B': PROJECT_FOLDER + '/tcorr/topowx_median_v0b_monthly',
        #     }
        #     # annual_coll_dict = {}
        #     default_value_dict = {
        #         'CIMIS': 0.978,
        #         'DAYMET': 0.978,
        #         'GRIDMET': 0.978,
        #         'TOPOWX': 0.978,
        #         'CIMIS_MEDIAN_V1': 0.978,
        #         'DAYMET_MEDIAN_V0': 0.978,
        #         'DAYMET_MEDIAN_V1': 0.978,
        #         'GRIDMET_MEDIAN_V1': 0.978,
        #         'TOPOWX_MEDIAN_V0': 0.978,
        #         'TOPOWX_MEDIAN_V0B': 0.978,
        #     }
        #
        #     # Check Tmax source value
        #     if (utils.is_number(self._tmax_source) or
        #             self._tmax_source.upper() not in default_value_dict.keys()):
        #         raise ValueError(
        #             '\nInvalid tmax_source for tcorr: {} / {}\n'.format(
        #                 self._tcorr_source, self._tmax_source))
        #     tmax_key = self._tmax_source.upper()
        #
        #     default_coll = ee.FeatureCollection([
        #         ee.Feature(None, {'INDEX': 3, 'TCORR': default_value_dict[tmax_key]})])
        #     month_coll = ee.FeatureCollection(month_coll_dict[tmax_key])\
        #         .filterMetadata('WRS2_TILE', 'equals', self._wrs2_tile)\
        #         .filterMetadata('MONTH', 'equals', self._month)
        #     if self._tcorr_source.upper() in ['FEATURE', 'SCENE']:
        #         scene_coll = ee.FeatureCollection(scene_coll_dict[tmax_key])\
        #             .filterMetadata('SCENE_ID', 'equals', self._scene_id)
        #         tcorr_coll = ee.FeatureCollection(
        #             default_coll.merge(month_coll).merge(scene_coll)).sort('INDEX')
        #     elif 'MONTH' in self._tcorr_source.upper():
        #         tcorr_coll = ee.FeatureCollection(
        #             default_coll.merge(month_coll)).sort('INDEX')
        #     else:
        #         raise ValueError(
        #             'Invalid tcorr_source: {} / {}\n'.format(
        #                 self._tcorr_source, self._tmax_source))
        #
        #     tcorr_ftr = ee.Feature(tcorr_coll.first())
        #     tcorr = ee.Number(tcorr_ftr.get('TCORR'))
        #     tcorr_index = ee.Number(tcorr_ftr.get('INDEX'))
        #
        #     return tcorr, tcorr_index
        #
        # elif 'IMAGE' in self._tcorr_source.upper():
        #     # Lookup Tcorr collections by keyword value
        #     daily_dict = {
        #         'DAYMET_MEDIAN_V2': PROJECT_FOLDER + '/tcorr_image/daymet_median_v2_daily',
        #         'TOPOWX_MEDIAN_V0': PROJECT_FOLDER + '/tcorr_image/topowx_median_v0_daily',
        #     }
        #     month_dict = {
        #         'DAYMET_MEDIAN_V2': PROJECT_FOLDER + '/tcorr_image/daymet_median_v2_monthly',
        #         'TOPOWX_MEDIAN_V0': PROJECT_FOLDER + '/tcorr_image/topowx_median_v0_monthly',
        #     }
        #     annual_dict = {
        #         'DAYMET_MEDIAN_V2': PROJECT_FOLDER + '/tcorr_image/daymet_median_v2_annual',
        #         'TOPOWX_MEDIAN_V0': PROJECT_FOLDER + '/tcorr_image/topowx_median_v0_annual',
        #     }
        #     default_dict = {
        #         'DAYMET_MEDIAN_V2': PROJECT_FOLDER + '/tcorr_image/daymet_median_v2_default',
        #         'TOPOWX_MEDIAN_V0': PROJECT_FOLDER + '/tcorr_image/topowx_median_v0_default',
        #     }
        #
        #     # Check Tmax source value
        #     if (utils.is_number(self._tmax_source) or
        #             self._tmax_source.upper() not in default_dict.keys()):
        #         raise ValueError(
        #             '\nInvalid tmax_source for tcorr: {} / {}\n'.format(
        #                 self._tcorr_source, self._tmax_source))
        #     tmax_key = self._tmax_source.upper()
        #
        #     # The mask image will be merged into all the Tcorr image collections
        #     #   to ensure that all collections (daily, monthly, annual) have data
        #     #   even if the collection is empty
        #     default_img = ee.Image(default_dict[tmax_key])
        #     mask_img = default_img.updateMask(0)
        #
        #     if (self._tcorr_source.upper() == 'IMAGE' or
        #             'DAILY' in self._tcorr_source.upper()):
        #         daily_coll = ee.ImageCollection(daily_dict[tmax_key])\
        #             .filterDate(self._start_date, self._end_date)\
        #             .select(['tcorr'])
        #         # Assume there may be multiple daily images for the same date
        #         # Use the one with the latest EXPORT_DATE property
        #         daily_coll = daily_coll\
        #             .limit(1, 'date_ingested', False)\
        #             .merge(ee.ImageCollection(mask_img))
        #         daily_img = ee.Image(daily_coll.mosaic())
        #         # .filterMetadata('DATE', 'equals', self._date)
        #     if (self._tcorr_source.upper() == 'IMAGE' or
        #             'MONTH' in self._tcorr_source.upper()):
        #         month_coll = ee.ImageCollection(month_dict[tmax_key])\
        #             .filterMetadata('cycle_day', 'equals', self._cycle_day)\
        #             .filterMetadata('month', 'equals', self._month)\
        #             .select(['tcorr'])
        #         month_coll = month_coll.merge(ee.ImageCollection(mask_img))
        #         month_img = ee.Image(month_coll.mosaic())
        #     if (self._tcorr_source.upper() == 'IMAGE' or
        #             'ANNUAL' in self._tcorr_source.upper()):
        #         annual_coll = ee.ImageCollection(annual_dict[tmax_key])\
        #             .filterMetadata('cycle_day', 'equals', self._cycle_day)\
        #             .select(['tcorr'])
        #         annual_coll = annual_coll.merge(ee.ImageCollection(mask_img))
        #         annual_img = ee.Image(annual_coll.mosaic())
        #
        #     if self._tcorr_source.upper() == 'IMAGE':
        #         # Composite Tcorr images to ensure that a value is returned
        #         #   (even if the daily image doesn't exist)
        #         composite_coll = ee.ImageCollection([
        #             default_img.addBands(default_img.multiply(0).add(3).uint8()),
        #             annual_img.addBands(annual_img.multiply(0).add(2).uint8()),
        #             month_img.addBands(month_img.multiply(0).add(1).uint8()),
        #             daily_img.addBands(daily_img.multiply(0).uint8())])
        #         composite_img = composite_coll.mosaic()
        #         tcorr_img = composite_img.select([0], ['tcorr'])
        #         index_img = composite_img.select([1], ['index'])
        #     elif 'DAILY' in self._tcorr_source.upper():
        #         tcorr_img = daily_img
        #         index_img = daily_img.multiply(0).uint8()
        #     elif 'MONTH' in self._tcorr_source.upper():
        #         tcorr_img = month_img
        #         index_img = month_img.multiply(0).add(1).uint8()
        #     elif 'ANNUAL' in self._tcorr_source.upper():
        #         tcorr_img = annual_img
        #         index_img = annual_img.multiply(0).add(2).uint8()
        #     elif 'DEFAULT' in self._tcorr_source.upper():
        #         tcorr_img = default_img
        #         index_img = default_img.multiply(0).add(3).uint8()
        #     else:
        #         raise ValueError(
        #             'Invalid tcorr_source: {} / {}\n'.format(
        #                 self._tcorr_source, self._tmax_source))
        #
        #     return tcorr_img, index_img.rename(['index'])

        else:
            raise ValueError('Unsupported tcorr_source: {}\n'.format(
                self._tcorr_source))

    @lazy_property
    def tmax(self):
        """Fall back on median Tmax if daily image does not exist

        Returns
        -------
        ee.Image

        Raises
        ------
        ValueError
            If `self._tmax_source` is not supported.

        """
        doy_filter = ee.Filter.calendarRange(self._doy, self._doy, 'day_of_year')
        date_today = datetime.datetime.today().strftime('%Y-%m-%d')

        if utils.is_number(self._tmax_source):
            tmax_image = ee.Image.constant(float(self._tmax_source))\
                .rename(['tmax'])\
                .set('tmax_version', 'custom_{}'.format(self._tmax_source))
        elif self._tmax_source.upper() == 'CIMIS':
            daily_coll_id = 'projects/earthengine-legacy/assets/' \
                            'projects/climate-engine/cimis/daily'
            daily_coll = ee.ImageCollection(daily_coll_id)\
                .filterDate(self._start_date, self._end_date)\
                .select(['Tx'], ['tmax']).map(utils.c_to_k)
            daily_image = ee.Image(daily_coll.first())\
                .set('tmax_version', date_today)
            median_version = 'median_v1'
            median_coll = ee.ImageCollection(
                PROJECT_FOLDER + '/tmax/cimis_{}'.format(median_version))
            median_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('tmax_version', median_version)
            tmax_image = ee.Image(ee.Algorithms.If(
                daily_coll.size().gt(0), daily_image, median_image))
        elif self._tmax_source.upper() == 'DAYMET':
            # DAYMET does not include Dec 31st on leap years
            # Adding one extra date to end date to avoid errors
            daily_coll = ee.ImageCollection('NASA/ORNL/DAYMET_V3')\
                .filterDate(self._start_date, self._end_date.advance(1, 'day'))\
                .select(['tmax']).map(utils.c_to_k)
            daily_image = ee.Image(daily_coll.first())\
                .set('tmax_version', date_today)
            median_version = 'median_v2'
            median_coll = ee.ImageCollection(
                PROJECT_FOLDER + '/tmax/daymet_{}'.format(median_version))
            median_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('tmax_version', median_version)
            tmax_image = ee.Image(ee.Algorithms.If(
                daily_coll.size().gt(0), daily_image, median_image))
        elif self._tmax_source.upper() == 'GRIDMET':
            daily_coll = ee.ImageCollection('IDAHO_EPSCOR/GRIDMET')\
                .filterDate(self._start_date, self._end_date)\
                .select(['tmmx'], ['tmax'])
            daily_image = ee.Image(daily_coll.first())\
                .set('tmax_version', date_today)
            median_version = 'median_v1'
            median_coll = ee.ImageCollection(
                PROJECT_FOLDER + '/tmax/gridmet_{}'.format(median_version))
            median_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('tmax_version', median_version)
            tmax_image = ee.Image(ee.Algorithms.If(
                daily_coll.size().gt(0), daily_image, median_image))
        # elif self.tmax_source.upper() == 'TOPOWX':
        #     daily_coll = ee.ImageCollection('X')\
        #         .filterDate(self.start_date, self.end_date)\
        #         .select(['tmmx'], ['tmax'])
        #     daily_image = ee.Image(daily_coll.first())\
        #         .set('tmax_version', date_today)
        #
        #     median_version = 'median_v1'
        #     median_coll = ee.ImageCollection(
        #         PROJECT_FOLDER + '/tmax/topowx_{}'.format(median_version))
        #     median_image = ee.Image(median_coll.filter(doy_filter).first())\
        #         .set('tmax_version', median_version)
        #
        #     tmax_image = ee.Image(ee.Algorithms.If(
        #         daily_coll.size().gt(0), daily_image, median_image))
        elif self._tmax_source.upper() == 'CIMIS_MEDIAN_V1':
            median_version = 'median_v1'
            median_coll = ee.ImageCollection(
                PROJECT_FOLDER + '/tmax/cimis_{}'.format(median_version))
            tmax_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('tmax_version', median_version)
        elif self._tmax_source.upper() == 'DAYMET_MEDIAN_V0':
            median_version = 'median_v0'
            median_coll = ee.ImageCollection(
                PROJECT_FOLDER + '/tmax/daymet_{}'.format(median_version))
            tmax_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('tmax_version', median_version)
        elif self._tmax_source.upper() == 'DAYMET_MEDIAN_V1':
            median_version = 'median_v1'
            median_coll = ee.ImageCollection(
                PROJECT_FOLDER + '/tmax/daymet_{}'.format(median_version))
            tmax_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('tmax_version', median_version)
        elif self._tmax_source.upper() == 'DAYMET_MEDIAN_V2':
            median_version = 'median_v2'
            median_coll = ee.ImageCollection(
                PROJECT_FOLDER + '/tmax/daymet_{}'.format(median_version))
            tmax_image = ee.Image(median_coll.filter(doy_filter).first()) \
                .set('tmax_version', median_version)
        elif self._tmax_source.upper() == 'GRIDMET_MEDIAN_V1':
            median_version = 'median_v1'
            median_coll = ee.ImageCollection(
                PROJECT_FOLDER + '/tmax/gridmet_{}'.format(median_version))
            tmax_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('tmax_version', median_version)
        elif self._tmax_source.upper() == 'TOPOWX_MEDIAN_V0':
            median_version = 'median_v0'
            median_coll = ee.ImageCollection(
                PROJECT_FOLDER + '/tmax/topowx_{}'.format(median_version))
            tmax_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('tmax_version', median_version)
        # elif self.tmax_source.upper() == 'TOPOWX_MEDIAN_V1':
        #     median_version = 'median_v1'
        #     median_coll = ee.ImageCollection(
        #         PROJECT_FOLDER + '/tmax/topowx_{}'.format(median_version))
        #     tmax_image = ee.Image(median_coll.filter(doy_filter).first())
        else:
            raise ValueError('Unsupported tmax_source: {}\n'.format(
                self._tmax_source))

        if (self._tmax_resample and
                self._tmax_resample.lower() in ['bilinear', 'bicubic']):
            tmax_image = tmax_image.resample(self._tmax_resample)
        # TODO: A reproject call may be needed here also
        # tmax_image = tmax_image.reproject(self.crs, self.transform)

        return tmax_image.set('tmax_source', self._tmax_source)

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
            'LANDSAT_8': ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B10', 'BQA']})
        output_bands = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'lst',
                        'BQA']
        k1 = ee.Dictionary({
            'LANDSAT_4': 'K1_CONSTANT_BAND_6',
            'LANDSAT_5': 'K1_CONSTANT_BAND_6',
            'LANDSAT_7': 'K1_CONSTANT_BAND_6_VCID_1',
            'LANDSAT_8': 'K1_CONSTANT_BAND_10'})
        k2 = ee.Dictionary({
            'LANDSAT_4': 'K2_CONSTANT_BAND_6',
            'LANDSAT_5': 'K2_CONSTANT_BAND_6',
            'LANDSAT_7': 'K2_CONSTANT_BAND_6_VCID_1',
            'LANDSAT_8': 'K2_CONSTANT_BAND_10'})
        prep_image = toa_image\
            .select(input_bands.get(spacecraft_id), output_bands)\
            .set({'k1_constant': ee.Number(toa_image.get(k1.get(spacecraft_id))),
                  'k2_constant': ee.Number(toa_image.get(k2.get(spacecraft_id)))})

        # Build the input image
        input_image = ee.Image([
            landsat.lst(prep_image),
            landsat.ndvi(prep_image),
        ])

        # Apply the cloud mask and add properties
        input_image = input_image\
            .updateMask(common.landsat_c1_toa_cloud_mask(
                toa_image, **cloudmask_args))\
            .set({
                'system:index': toa_image.get('system:index'),
                'system:time_start': toa_image.get('system:time_start'),
                'system:id': toa_image.get('system:id'),
            })

        # Instantiate the class
        return cls(ee.Image(input_image), **kwargs)

    @classmethod
    def from_landsat_c1_sr(cls, sr_image, **kwargs):
        """Returns a SSEBop Image instance from a Landsat Collection 1 SR image

        Parameters
        ----------
        sr_image : ee.Image, str
            A raw Landsat Collection 1 SR image or image ID.

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
            'LANDSAT_8': ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B10',
                          'pixel_qa']})
        output_bands = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'lst',
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

        # Build the input image
        input_image = ee.Image([
            landsat.lst(prep_image),
            landsat.ndvi(prep_image),
        ])

        # Apply the cloud mask and add properties
        input_image = input_image\
            .updateMask(common.landsat_c1_sr_cloud_mask(sr_image))\
            .set({'system:index': sr_image.get('system:index'),
                  'system:time_start': sr_image.get('system:time_start'),
                  'system:id': sr_image.get('system:id')})

        # Instantiate the class
        return cls(input_image, **kwargs)

    # TODO: Move calculation to model.py
    @lazy_property
    def tcorr_image(self):
        """Compute Tcorr for the current image

        Returns
        -------
        ee.Image of Tcorr values

        """
        lst = ee.Image(self.lst)
        ndvi = ee.Image(self.ndvi)
        tmax = ee.Image(self.tmax)

        # Compute Tcorr
        tcorr = lst.divide(tmax)

        # Select high NDVI pixels that are also surrounded by high NDVI
        ndvi_smooth_mask = ndvi.focal_mean(radius=120, units='meters')\
          .reproject(crs=self.crs, crsTransform=self.transform)\
          .gt(0.7)
        ndvi_buffer_mask = ndvi.gt(0.7).reduceNeighborhood(
            ee.Reducer.min(), ee.Kernel.square(radius=60, units='meters'))

        # Remove low LST and low NDVI
        tcorr_mask = lst.gt(270).And(ndvi_smooth_mask).And(ndvi_buffer_mask)

        return tcorr.updateMask(tcorr_mask).rename(['tcorr'])\
            .set({'system:index': self._index,
                  'system:time_start': self._time_start,
                  'tmax_source': tmax.get('tmax_source'),
                  'tmax_version': tmax.get('tmax_version')})

    @lazy_property
    def tcorr_stats(self):
        """Compute the Tcorr 5th percentile and count statistics

        Returns
        -------
        dictionary

        """
        return ee.Image(self.tcorr_image).reduceRegion(
            reducer=ee.Reducer.percentile([5])\
                .combine(ee.Reducer.count(), '', True),
            crs=self.crs,
            crsTransform=self.transform,
            geometry=self.image.geometry().buffer(1000),
            bestEffort=False,
            maxPixels=2*10000*10000,
            tileScale=1,
        )
