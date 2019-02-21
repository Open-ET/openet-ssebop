import datetime
import pprint

import ee

from . import utils
import openet.core.common as common
# TODO: import utils from common
# import openet.core.utils as utils


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
            etr_source='IDAHO_EPSCOR/GRIDMET',
            etr_band='etr',
            dt_source='DAYMET_MEDIAN_V1',
            elev_source='SRTM',
            tcorr_source='IMAGE_DAILY',
            tmax_source='TOPOWX_MEDIAN_V0',
            elr_flag=False,
            tdiff_threshold=15,
            dt_min=6,
            dt_max=25,
            ):
        """Construct a generic SSEBop Image

        Parameters
        ----------
        image : ee.Image
            A "prepped" SSEBop input image.
            Image must have bands "ndvi" and "lst".
            Image must have 'system:index' and 'system:time_start' properties.
        etr_source : str, float, optional
            Reference ET source (the default is 'IDAHO_EPSCOR/GRIDMET').
        etr_band : str, optional
            Reference ET band name (the default is 'etr').
        dt_source : {'DAYMET_MEDIAN_V0', 'DAYMET_MEDIAN_V1', or float}, optional
            dT source keyword (the default is 'DAYMET_MEDIAN_V1').
        elev_source : {'ASSET', 'GTOPO', 'NED', 'SRTM', or float}, optional
            Elevation source keyword (the default is 'SRTM').
        tcorr_source : {'FEATURE', 'FEATURE_MONTHLY', 'FEATURE_ANNUAL',
                        'IMAGE', 'IMAGE_DAILY', 'IMAGE_MONTHLY',
                        'IMAGE_ANNUAL', 'IMAGE_DEFAULT', or float}, optional
            Tcorr source keyword (the default is 'IMAGE_DAILY').
        tmax_source : {'CIMIS', 'DAYMET', 'GRIDMET', 'CIMIS_MEDIAN_V1',
                       'DAYMET_MEDIAN_V1', 'GRIDMET_MEDIAN_V1',
                       'TOPOWX_MEDIAN_V0', or float}, optional
            Maximum air temperature source (the default is 'TOPOWX_MEDIAN_V0').
        elr_flag : bool, optional
            If True, apply Elevation Lapse Rate (ELR) adjustment
            (the default is False).
        tdiff_threshold : float, optional
            Cloud mask buffer using Tdiff [K] (the default is 15).
            Pixels with (Tmax - LST) > Tdiff threshold will be masked.
        dt_min : float, optional
            Minimum allowable dT [K] (the default is 6).
        dt_max : float, optional
            Maximum allowable dT [K] (the default is 25).

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
            'IMAGE_ID': self._id,
        }

        # Build SCENE_ID from the (possibly merged) system:index
        scene_id = ee.List(ee.String(self._index).split('_')).slice(-3)
        self._scene_id = ee.String(scene_id.get(0)).cat('_') \
            .cat(ee.String(scene_id.get(1))).cat('_') \
            .cat(ee.String(scene_id.get(2)))

        # Build WRS2_TILE from the scene_id
        self._wrs2_tile = ee.String('p').cat(self._scene_id.slice(5, 8)) \
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

        #
        self.etr_source = etr_source
        self.etr_band = etr_band

        # Model input parameters
        self._dt_source = dt_source
        self._elev_source = elev_source
        self._tcorr_source = tcorr_source
        self._tmax_source = tmax_source
        self._elr_flag = elr_flag
        self._tdiff_threshold = float(tdiff_threshold)
        self._dt_min = float(dt_min)
        self._dt_max = float(dt_max)

    def calculate(self, variables=['et', 'etr', 'etf']):
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
                output_images.append(self.et)
            elif v.lower() == 'etf':
                output_images.append(self.etf)
            elif v.lower() == 'etr':
                output_images.append(self.etr)
            elif v.lower() == 'ndvi':
                output_images.append(self.ndvi)
            # elif v.lower() == 'qa':
            #     output_images.append(self.qa)
            # elif v.lower() == 'quality':
            #     output_images.append(self.quality)
            elif v.lower() == 'time':
                output_images.append(self.time)
            else:
                raise ValueError('unsupported variable: {}'.format(v))

        return ee.Image(output_images).set(self._properties)

    @lazy_property
    def lst(self):
        """Return land surface temperature (LST) image"""
        return self.image.select(['lst']).set(self._properties)

    @lazy_property
    def ndvi(self):
        """Return NDVI image"""
        return self.image.select(['ndvi']).set(self._properties)

    @lazy_property
    def time(self):
        """Return 0 UTC time image (in milliseconds)"""
        return self.etf\
            .double().multiply(0).add(utils.date_to_time_0utc(self._date)) \
            .rename(['time']).set(self._properties)
        # return ee.Image.constant(utils.date_to_time_0utc(self._date)) \
        #     .double().rename(['time']).set(self._properties)

    @lazy_property
    def etf(self):
        """Compute SSEBop ETf for a single image

        Returns
        -------
        ee.Image

        Notes
        -----
        Apply Tdiff cloud mask buffer (mask values of 0 are set to nodata)

        """
        # Get input images and ancillary data needed to compute SSEBop ETf
        lst = ee.Image(self.lst)
        tcorr, tcorr_index = self._tcorr
        tmax = ee.Image(self._tmax)
        dt = ee.Image(self._dt)

        # Adjust air temperature based on elevation (Elevation Lapse Rate)
        if self._elr_flag:
            tmax = ee.Image(self._lapse_adjust(tmax, ee.Image(self._elev)))

        # Compute SSEBop ETf
        etf = lst.expression(
            '(lst * (-1) + tmax * tcorr + dt) / dt',
            {'tmax': tmax, 'dt': dt, 'lst': lst, 'tcorr': tcorr})

        etf = etf.updateMask(etf.lt(1.3)) \
            .clamp(0, 1.05) \
            .updateMask(tmax.subtract(lst).lte(self._tdiff_threshold)) \
            .set(self._properties) \
            .rename(['etf'])

        # Don't set TCORR and INDEX properties for IMAGE Tcorr sources
        if (type(self._tcorr_source) is str and
                'IMAGE' not in self._tcorr_source.upper()):
            etf = etf.set({'TCORR': tcorr, 'TCORR_INDEX': tcorr_index})

        return etf

    @lazy_property
    def etr(self):
        """Compute reference ET for the image date"""
        if utils.is_number(self.etr_source):
            # Interpret numbers as constant images
            # CGM - Should we use the ee_types here instead?
            #   i.e. ee.ee_types.isNumber(self.etr_source)
            etr_img = ee.Image.constant(self.etr_source)
        elif type(self.etr_source) is str:
            # Assume a string source is an image collection ID (not an image ID)
            etr_img = ee.Image(
                ee.ImageCollection(self.etr_source) \
                    .filterDate(self._start_date, self._end_date) \
                    .select([self.etr_band]) \
                    .first())
        # elif type(self.etr_source) is list:
        #     # Interpret as list of image collection IDs to composite/mosaic
        #     #   i.e. Spatial CIMIS and GRIDMET
        #     # CGM - Need to check the order of the collections
        #     etr_coll = ee.ImageCollection([])
        #     for coll_id in self.etr_source:
        #         coll = ee.ImageCollection(coll_id) \
        #             .select([self.etr_band]) \
        #             .filterDate(self.start_date, self.end_date)
        #         etr_img = etr_coll.merge(coll)
        #     etr_img = etr_coll.mosaic()
        # elif isinstance(self.etr_source, computedobject.ComputedObject):
        #     # Interpret computed objects as image collections
        #     etr_coll = ee.ImageCollection(self.etr_source) \
        #         .select([self.etr_band]) \
        #         .filterDate(self.start_date, self.end_date)
        else:
            raise ValueError('unsupported etr_source: {}'.format(
                self.etr_source))

        # Map ETr values directly to the input (i.e. Landsat) image pixels
        # The benefit of this is the ETr image is now in the same crs as the
        #   input image.  Not all models may want this though.
        # CGM - Should the output band name match the input ETr band name?
        return self.ndvi.multiply(0).add(etr_img) \
            .rename(['etr']).set(self._properties)

    @lazy_property
    def et(self):
        """Compute actual ET as fraction of reference times reference"""
        return self.etf.multiply(self.etr) \
            .rename(['et']).set(self._properties)

    # @lazy_property
    # def quality(self):
    #     """Set quality to 1 for all active pixels (for now)"""
    #     return self.etf.multiply(0).add(1) \
    #         .rename(['quality']).set(self._properties)

    @lazy_property
    def _dt(self):
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
        elif self._dt_source.upper() == 'DAYMET_MEDIAN_V0':
            dt_coll = ee.ImageCollection('projects/usgs-ssebop/dt/daymet_median_v0') \
                .filter(ee.Filter.calendarRange(self._doy, self._doy, 'day_of_year'))
            dt_img = ee.Image(dt_coll.first())
        elif self._dt_source.upper() == 'DAYMET_MEDIAN_V1':
            dt_coll = ee.ImageCollection('projects/usgs-ssebop/dt/daymet_median_v1') \
                .filter(ee.Filter.calendarRange(self._doy, self._doy, 'day_of_year'))
            dt_img = ee.Image(dt_coll.first())
        else:
            raise ValueError('Invalid dt_source: {}\n'.format(self._dt_source))

        return dt_img.clamp(self._dt_min, self._dt_max).rename('dt')

    @lazy_property
    def _elev(self):
        """

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
            elev_image = ee.Image('projects/usgs-ssebop/srtm_1km')
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
    def _tcorr(self):
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
            Annuals don't exist for feature Tcorr assets (yet)
          3 - Default Tcorr
          4 - User defined Tcorr

        """

        # month_field = ee.String('M').cat(ee.Number(self.month).format('%02d'))
        if utils.is_number(self._tcorr_source):
            tcorr = ee.Number(float(self._tcorr_source))
            tcorr_index = ee.Number(4)
            return tcorr, tcorr_index

        # DEADBEEF - Leaving 'SCENE' checking to be backwards compatible (for now)
        elif ('FEATURE' in self._tcorr_source.upper() or
                self._tcorr_source.upper() == 'SCENE'):
            # Lookup Tcorr collections by keyword value
            scene_coll_dict = {
                'CIMIS': 'projects/usgs-ssebop/tcorr/cimis_scene',
                'DAYMET': 'projects/usgs-ssebop/tcorr/daymet_scene',
                'GRIDMET': 'projects/usgs-ssebop/tcorr/gridmet_scene',
                # 'TOPOWX': 'projects/usgs-ssebop/tcorr/topowx_scene',
                'CIMIS_MEDIAN_V1': 'projects/usgs-ssebop/tcorr/cimis_median_v1_scene',
                'DAYMET_MEDIAN_V0': 'projects/usgs-ssebop/tcorr/daymet_median_v0_scene',
                'DAYMET_MEDIAN_V1': 'projects/usgs-ssebop/tcorr/daymet_median_v1_scene',
                'GRIDMET_MEDIAN_V1': 'projects/usgs-ssebop/tcorr/gridmet_median_v1_scene',
                'TOPOWX_MEDIAN_V0': 'projects/usgs-ssebop/tcorr/topowx_median_v0_scene',
                'TOPOWX_MEDIAN_V0B': 'projects/usgs-ssebop/tcorr/topowx_median_v0b_scene',
            }
            month_coll_dict = {
                'CIMIS': 'projects/usgs-ssebop/tcorr/cimis_monthly',
                'DAYMET': 'projects/usgs-ssebop/tcorr/daymet_monthly',
                'GRIDMET': 'projects/usgs-ssebop/tcorr/gridmet_monthly',
                # 'TOPOWX': 'projects/usgs-ssebop/tcorr/topowx_monthly',
                'CIMIS_MEDIAN_V1': 'projects/usgs-ssebop/tcorr/cimis_median_v1_monthly',
                'DAYMET_MEDIAN_V0': 'projects/usgs-ssebop/tcorr/daymet_median_v0_monthly',
                'DAYMET_MEDIAN_V1': 'projects/usgs-ssebop/tcorr/daymet_median_v1_monthly',
                'GRIDMET_MEDIAN_V1': 'projects/usgs-ssebop/tcorr/gridmet_median_v1_monthly',
                'TOPOWX_MEDIAN_V0': 'projects/usgs-ssebop/tcorr/topowx_median_v0_monthly',
                'TOPOWX_MEDIAN_V0B': 'projects/usgs-ssebop/tcorr/topowx_median_v0b_monthly',
            }
            # annual_coll_dict = {}
            default_value_dict = {
                'CIMIS': 0.978,
                'DAYMET': 0.978,
                'GRIDMET': 0.978,
                'TOPOWX': 0.978,
                'CIMIS_MEDIAN_V1': 0.978,
                'DAYMET_MEDIAN_V0': 0.978,
                'DAYMET_MEDIAN_V1': 0.978,
                'GRIDMET_MEDIAN_V1': 0.978,
                'TOPOWX_MEDIAN_V0': 0.978,
                'TOPOWX_MEDIAN_V0B': 0.978,
            }

            # Check Tmax source value
            tmax_key = self._tmax_source.upper()
            if tmax_key not in default_value_dict.keys():
                raise ValueError(
                    '\nInvalid tmax_source for tcorr: {} / {}\n'.format(
                        self._tcorr_source, self._tmax_source))

            default_coll = ee.FeatureCollection([
                ee.Feature(None, {'INDEX': 3, 'TCORR': default_value_dict[tmax_key]})])
            month_coll = ee.FeatureCollection(month_coll_dict[tmax_key]) \
                .filterMetadata('WRS2_TILE', 'equals', self._wrs2_tile) \
                .filterMetadata('MONTH', 'equals', self._month)
            if self._tcorr_source.upper() in ['FEATURE', 'SCENE']:
                scene_coll = ee.FeatureCollection(scene_coll_dict[tmax_key]) \
                    .filterMetadata('SCENE_ID', 'equals', self._scene_id)
                tcorr_coll = ee.FeatureCollection(
                    default_coll.merge(month_coll).merge(scene_coll)).sort('INDEX')
            elif 'MONTH' in self._tcorr_source.upper():
                tcorr_coll = ee.FeatureCollection(
                    default_coll.merge(month_coll)).sort('INDEX')
            else:
                raise ValueError(
                    'Invalid tcorr_source: {} / {}\n'.format(
                        self._tcorr_source, self._tmax_source))

            tcorr_ftr = ee.Feature(tcorr_coll.first())
            tcorr = ee.Number(tcorr_ftr.get('TCORR'))
            tcorr_index = ee.Number(tcorr_ftr.get('INDEX'))

            return tcorr, tcorr_index

        elif 'IMAGE' in self._tcorr_source.upper():
            # Lookup Tcorr collections by keyword value
            daily_dict = {
                'TOPOWX_MEDIAN_V0': 'projects/usgs-ssebop/tcorr_image/topowx_median_v0_daily'
            }
            month_dict = {
                'TOPOWX_MEDIAN_V0': 'projects/usgs-ssebop/tcorr_image/topowx_median_v0_monthly',
            }
            annual_dict = {
                'TOPOWX_MEDIAN_V0': 'projects/usgs-ssebop/tcorr_image/topowx_median_v0_annual',
            }
            default_dict = {
                'TOPOWX_MEDIAN_V0': 'projects/usgs-ssebop/tcorr_image/topowx_median_v0_default'
            }

            # Check Tmax source value
            tmax_key = self._tmax_source.upper()
            if tmax_key not in default_dict.keys():
                raise ValueError(
                    '\nInvalid tmax_source: {} / {}\n'.format(
                        self._tcorr_source, self._tmax_source))

            default_img = ee.Image(default_dict[tmax_key])
            mask_img = default_img.updateMask(0)

            if (self._tcorr_source.upper() == 'IMAGE' or
                    'DAILY' in self._tcorr_source.upper()):
                daily_coll = ee.ImageCollection(daily_dict[tmax_key]) \
                    .filterDate(self._start_date, self._end_date) \
                    .select(['tcorr'])
                daily_coll = daily_coll.merge(ee.ImageCollection(mask_img))
                daily_img = ee.Image(daily_coll.mosaic())
                # .filterMetadata('DATE', 'equals', self._date)
            if (self._tcorr_source.upper() == 'IMAGE' or
                    'MONTH' in self._tcorr_source.upper()):
                month_coll = ee.ImageCollection(month_dict[tmax_key]) \
                    .filterMetadata('CYCLE_DAY', 'equals', self._cycle_day) \
                    .filterMetadata('MONTH', 'equals', self._month) \
                    .select(['tcorr'])
                month_coll = month_coll.merge(ee.ImageCollection(mask_img))
                month_img = ee.Image(month_coll.mosaic())
            if (self._tcorr_source.upper() == 'IMAGE' or
                    'ANNUAL' in self._tcorr_source.upper()):
                annual_coll = ee.ImageCollection(annual_dict[tmax_key]) \
                    .filterMetadata('CYCLE_DAY', 'equals', self._cycle_day) \
                    .select(['tcorr'])
                annual_coll = annual_coll.merge(ee.ImageCollection(mask_img))
                annual_img = ee.Image(annual_coll.mosaic())

            if self._tcorr_source.upper() == 'IMAGE':
                # Composite Tcorr images to ensure that a value is returned
                #   (even if the daily image doesn't exist)
                composite_img = ee.ImageCollection([
                        default_img.addBands(default_img.multiply(0).add(3).uint8()),
                        annual_img.addBands(annual_img.multiply(0).add(2).uint8()),
                        month_img.addBands(month_img.multiply(0).add(1).uint8()),
                        daily_img.addBands(daily_img.multiply(0).uint8())]) \
                    .mosaic().rename(['tcorr', 'index'])
                tcorr_img = composite_img.select(['tcorr'])
                index_img = composite_img.select(['index'])
            elif 'DAILY' in self._tcorr_source.upper():
                tcorr_img = daily_img
                index_img = daily_img.multiply(0).uint8()
            elif 'MONTH' in self._tcorr_source.upper():
                tcorr_img = month_img
                index_img = month_img.multiply(0).add(1).uint8()
            elif 'ANNUAL' in self._tcorr_source.upper():
                tcorr_img = annual_img
                index_img = annual_img.multiply(0).add(2).uint8()
            elif 'DEFAULT' in self._tcorr_source.upper():
                tcorr_img = default_img
                index_img = default_img.multiply(0).add(3).uint8()
            else:
                raise ValueError(
                    'Invalid tcorr_source: {} / {}\n'.format(
                        self._tcorr_source, self._tmax_source))

            return tcorr_img, index_img.rename(['index'])

            # # Construct Tcorr images as composites
            # elif 'DAILY' in self._tcorr_source.upper():
            #     tcorr_img = ee.ImageCollection([
            #             default_img.addBands(default_img.multiply(0).add(3).uint8()),
            #             annual_img.addBands(annual_img.multiply(0).add(2).uint8()),
            #             month_img.addBands(month_img.multiply(0).add(1).uint8()),
            #             daily_img.addBands(daily_img.multiply(0).uint8())]) \
            #         .mosaic()
            # elif 'MONTH' in self._tcorr_source.upper():
            #     tcorr_img = ee.ImageCollection([
            #             default_img.addBands(default_img.multiply(0).add(3).uint8()),
            #             annual_img.addBands(annual_img.multiply(0).add(2).uint8()),
            #             month_img.addBands(month_img.multiply(0).add(1).uint8())]) \
            #         .mosaic()
            # elif 'ANNUAL' in self._tcorr_source.upper():
            #     tcorr_img = ee.ImageCollection([
            #             default_img.addBands(default_img.multiply(0).add(3).uint8()),
            #             annual_img.addBands(annual_img.multiply(0).add(2).uint8())]) \
            #         .mosaic()
        else:
            raise ValueError('Unsupported tcorr_source: {}\n'.format(
                self._tcorr_source))

    @lazy_property
    def _tmax(self):
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
                .set('TMAX_VERSION', 'CUSTOM_{}'.format(self._tmax_source))
        elif self._tmax_source.upper() == 'CIMIS':
            daily_coll = ee.ImageCollection('projects/climate-engine/cimis/daily') \
                .filterDate(self._start_date, self._end_date) \
                .select(['Tx'], ['tmax']).map(utils.c_to_k)
            daily_image = ee.Image(daily_coll.first())\
                .set('TMAX_VERSION', date_today)
            median_version = 'median_v1'
            median_coll = ee.ImageCollection(
                'projects/usgs-ssebop/tmax/cimis_{}'.format(median_version))
            median_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('TMAX_VERSION', median_version)
            tmax_image = ee.Image(ee.Algorithms.If(
                daily_coll.size().gt(0), daily_image, median_image))
        elif self._tmax_source.upper() == 'DAYMET':
            # DAYMET does not include Dec 31st on leap years
            # Adding one extra date to end date to avoid errors
            daily_coll = ee.ImageCollection('NASA/ORNL/DAYMET_V3') \
                .filterDate(self._start_date, self._end_date.advance(1, 'day')) \
                .select(['tmax']).map(utils.c_to_k)
            daily_image = ee.Image(daily_coll.first())\
                .set('TMAX_VERSION', date_today)
            median_version = 'median_v0'
            median_coll = ee.ImageCollection(
                'projects/usgs-ssebop/tmax/daymet_{}'.format(median_version))
            median_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('TMAX_VERSION', median_version)
            tmax_image = ee.Image(ee.Algorithms.If(
                daily_coll.size().gt(0), daily_image, median_image))
        elif self._tmax_source.upper() == 'GRIDMET':
            daily_coll = ee.ImageCollection('IDAHO_EPSCOR/GRIDMET') \
                .filterDate(self._start_date, self._end_date) \
                .select(['tmmx'], ['tmax'])
            daily_image = ee.Image(daily_coll.first())\
                .set('TMAX_VERSION', date_today)
            median_version = 'median_v1'
            median_coll = ee.ImageCollection(
                'projects/usgs-ssebop/tmax/gridmet_{}'.format(median_version))
            median_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('TMAX_VERSION', median_version)
            tmax_image = ee.Image(ee.Algorithms.If(
                daily_coll.size().gt(0), daily_image, median_image))
        # elif self.tmax_source.upper() == 'TOPOWX':
        #     daily_coll = ee.ImageCollection('X') \
        #         .filterDate(self.start_date, self.end_date) \
        #         .select(['tmmx'], ['tmax'])
        #     daily_image = ee.Image(daily_coll.first())\
        #         .set('TMAX_VERSION', date_today)
        #
        #     median_version = 'median_v1'
        #     median_coll = ee.ImageCollection(
        #         'projects/usgs-ssebop/tmax/topowx_{}'.format(median_version))
        #     median_image = ee.Image(median_coll.filter(doy_filter).first())\
        #         .set('TMAX_VERSION', median_version)
        #
        #     tmax_image = ee.Image(ee.Algorithms.If(
        #         daily_coll.size().gt(0), daily_image, median_image))
        elif self._tmax_source.upper() == 'CIMIS_MEDIAN_V1':
            median_version = 'median_v1'
            median_coll = ee.ImageCollection(
                'projects/usgs-ssebop/tmax/cimis_{}'.format(median_version))
            tmax_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('TMAX_VERSION', median_version)
        elif self._tmax_source.upper() == 'DAYMET_MEDIAN_V0':
            median_version = 'median_v0'
            median_coll = ee.ImageCollection(
                'projects/usgs-ssebop/tmax/daymet_{}'.format(median_version))
            tmax_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('TMAX_VERSION', median_version)
        elif self._tmax_source.upper() == 'DAYMET_MEDIAN_V1':
            median_version = 'median_v1'
            median_coll = ee.ImageCollection(
                'projects/usgs-ssebop/tmax/daymet_{}'.format(median_version))
            tmax_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('TMAX_VERSION', median_version)
        elif self._tmax_source.upper() == 'GRIDMET_MEDIAN_V1':
            median_version = 'median_v1'
            median_coll = ee.ImageCollection(
                'projects/usgs-ssebop/tmax/gridmet_{}'.format(median_version))
            tmax_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('TMAX_VERSION', median_version)
        elif self._tmax_source.upper() == 'TOPOWX_MEDIAN_V0':
            median_version = 'median_v0'
            median_coll = ee.ImageCollection(
                'projects/usgs-ssebop/tmax/topowx_{}'.format(median_version))
            tmax_image = ee.Image(median_coll.filter(doy_filter).first())\
                .set('TMAX_VERSION', median_version)
        # elif self.tmax_source.upper() == 'TOPOWX_MEDIAN_V1':
        #     median_version = 'median_v1'
        #     median_coll = ee.ImageCollection(
        #         'projects/usgs-ssebop/tmax/topowx_{}'.format(median_version))
        #     tmax_image = ee.Image(median_coll.filter(doy_filter).first())
        else:
            raise ValueError('Unsupported tmax_source: {}\n'.format(
                self._tmax_source))

        return ee.Image(tmax_image.set('TMAX_SOURCE', self._tmax_source))

    # @classmethod
    # def from_image_id(cls, image_id, **kwargs):
    #     """Constructs an SSEBop Image instance from an image ID
    #
    #     Parameters
    #     ----------
    #     image_id : str
    #         An earth engine image ID.
    #         (i.e. 'LANDSAT/LC08/C01/T1_SR/LC08_044033_20170716')
    #     kwargs
    #         Keyword arguments to pass through to model init.
    #
    #     Returns
    #     -------
    #     new instance of Image class
    #
    #     """
    #     # DEADBEEF - Should the supported image collection IDs and helper
    #     # function mappings be set in a property or method of the Image class?
    #     collection_methods = {
    #         'LANDSAT/LC08/C01/T1_RT_TOA': 'from_landsat_c1_toa',
    #         'LANDSAT/LE07/C01/T1_RT_TOA': 'from_landsat_c1_toa',
    #         'LANDSAT/LC08/C01/T1_TOA': 'from_landsat_c1_toa',
    #         'LANDSAT/LE07/C01/T1_TOA': 'from_landsat_c1_toa',
    #         'LANDSAT/LT05/C01/T1_TOA': 'from_landsat_c1_toa',
    #         # 'LANDSAT/LT04/C01/T1_TOA': 'from_landsat_c1_toa',
    #         'LANDSAT/LC08/C01/T1_SR': 'from_landsat_c1_sr',
    #         'LANDSAT/LE07/C01/T1_SR': 'from_landsat_c1_sr',
    #         'LANDSAT/LT05/C01/T1_SR': 'from_landsat_c1_sr',
    #         # 'LANDSAT/LT04/C01/T1_SR': 'from_landsat_c1_sr',
    #     }
    #
    #     try:
    #         method_name = collection_methods[image_id.rsplit('/', 1)[0]]
    #     except KeyError:
    #         raise ValueError('unsupported collection ID: {}'.format(image_id))
    #     except Exception as e:
    #         raise Exception('unhandled exception: {}'.format(e))
    #
    #     method = getattr(Image, method_name)
    #
    #     return method(ee.Image(image_id), **kwargs)

    @classmethod
    def from_landsat_c1_toa(cls, toa_image, cloudmask_args={}, **kwargs):
        """Returns a SSEBop Image instance from a Landsat Collection 1 TOA image

        Parameters
        ----------
        toa_image : ee.Image
            A raw Landsat Collection 1 TOA image.
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
            'LANDSAT_5': ['B1', 'B2', 'B3', 'B4', 'B5', 'B7', 'B6', 'BQA'],
            'LANDSAT_7': ['B1', 'B2', 'B3', 'B4', 'B5', 'B7', 'B6_VCID_1',
                          'BQA'],
            'LANDSAT_8': ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B10', 'BQA']})
        output_bands = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'lst',
                        'BQA']
        k1 = ee.Dictionary({
            'LANDSAT_5': 'K1_CONSTANT_BAND_6',
            'LANDSAT_7': 'K1_CONSTANT_BAND_6_VCID_1',
            'LANDSAT_8': 'K1_CONSTANT_BAND_10'})
        k2 = ee.Dictionary({
            'LANDSAT_5': 'K2_CONSTANT_BAND_6',
            'LANDSAT_7': 'K2_CONSTANT_BAND_6_VCID_1',
            'LANDSAT_8': 'K2_CONSTANT_BAND_10'})
        prep_image = toa_image \
            .select(input_bands.get(spacecraft_id), output_bands) \
            .set('k1_constant', ee.Number(toa_image.get(k1.get(spacecraft_id)))) \
            .set('k2_constant', ee.Number(toa_image.get(k2.get(spacecraft_id))))

        # Build the input image
        input_image = ee.Image([cls._lst(prep_image), cls._ndvi(prep_image)])

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
        sr_image : ee.Image
            A raw Landsat Collection 1 SR image.

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
            'LANDSAT_5': ['B1', 'B2', 'B3', 'B4', 'B5', 'B7', 'B6', 'pixel_qa'],
            'LANDSAT_7': ['B1', 'B2', 'B3', 'B4', 'B5', 'B7', 'B6', 'pixel_qa'],
            'LANDSAT_8': ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B10',
                          'pixel_qa']})
        output_bands = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'lst',
                        'pixel_qa']
        # TODO: Follow up with Simon about adding K1/K2 to SR collection
        # Hardcode values for now
        k1 = ee.Dictionary({
            'LANDSAT_5': 607.76, 'LANDSAT_7': 666.09, 'LANDSAT_8': 774.8853})
        k2 = ee.Dictionary({
            'LANDSAT_5': 1260.56, 'LANDSAT_7': 1282.71, 'LANDSAT_8': 1321.0789})
        prep_image = sr_image \
            .select(input_bands.get(spacecraft_id), output_bands) \
            .set('k1_constant', ee.Number(k1.get(spacecraft_id))) \
            .set('k2_constant', ee.Number(k2.get(spacecraft_id)))
        # k1 = ee.Dictionary({
        #     'LANDSAT_5': 'K1_CONSTANT_BAND_6',
        #     'LANDSAT_7': 'K1_CONSTANT_BAND_6_VCID_1',
        #     'LANDSAT_8': 'K1_CONSTANT_BAND_10'})
        # k2 = ee.Dictionary({
        #     'LANDSAT_5': 'K2_CONSTANT_BAND_6',
        #     'LANDSAT_7': 'K2_CONSTANT_BAND_6_VCID_1',
        #     'LANDSAT_8': 'K2_CONSTANT_BAND_10'})
        # prep_image = sr_image \
        #     .select(input_bands.get(spacecraft_id), output_bands) \
        #     .set('k1_constant', ee.Number(sr_image.get(k1.get(spacecraft_id)))) \
        #     .set('k2_constant', ee.Number(sr_image.get(k2.get(spacecraft_id))))

        # Build the input image
        input_image = ee.Image([cls._lst(prep_image), cls._ndvi(prep_image)])

        # Apply the cloud mask and add properties
        input_image = input_image\
            .updateMask(common.landsat_c1_sr_cloud_mask(sr_image))\
            .set({
                'system:index': sr_image.get('system:index'),
                'system:time_start': sr_image.get('system:time_start'),
                'system:id': sr_image.get('system:id'),
            })

        # Instantiate the class
        return cls(input_image, **kwargs)

    @staticmethod
    def _ndvi(toa_image):
        """Compute NDVI

        Parameters
        ----------
        toa_image : ee.Image
            Renamed TOA image with 'nir' and 'red bands.

        Returns
        -------
        ee.Image

        """
        return ee.Image(toa_image).normalizedDifference(['nir', 'red']) \
            .rename(['ndvi'])

    @staticmethod
    def _lst(toa_image):
        """Compute emissivity corrected land surface temperature (LST)
        from brightness temperature.

        Parameters
        ----------
        toa_image : ee.Image
            Renamed TOA image with 'red', 'nir', and 'lst' bands.
            Image must also have 'k1_constant' and 'k2_constant' properties.

        Returns
        -------
        ee.Image

        Notes
        -----
        The corrected radiation coefficients were derived from a small number
        of scenes in southern Idaho [Allen2007] and may not be appropriate for
        other areas.

        References
        ----------
        .. [Allen2007] R. Allen, M. Tasumi, R. Trezza (2007),
            Satellite-Based Energy Balance for Mapping Evapotranspiration with
            Internalized Calibration (METRIC) Model,
            Journal of Irrigation and Drainage Engineering, Vol 133(4),
            http://dx.doi.org/10.1061/(ASCE)0733-9437(2007)133:4(380)

        """
        # Get properties from image
        k1 = ee.Number(ee.Image(toa_image).get('k1_constant'))
        k2 = ee.Number(ee.Image(toa_image).get('k2_constant'))

        ts_brightness = ee.Image(toa_image).select(['lst'])
        emissivity = Image._emissivity(toa_image)

        # First back out radiance from brightness temperature
        # Then recalculate emissivity corrected Ts
        thermal_rad_toa = ts_brightness.expression(
            'k1 / (exp(k2 / ts_brightness) - 1)',
            {'ts_brightness': ts_brightness, 'k1': k1, 'k2': k2})

        # tnb = 0.866   # narrow band transmissivity of air
        # rp = 0.91     # path radiance
        # rsky = 1.32   # narrow band clear sky downward thermal radiation
        rc = thermal_rad_toa.expression(
            '((thermal_rad_toa - rp) / tnb) - ((1. - emiss) * rsky)',
            {
                'thermal_rad_toa': thermal_rad_toa,
                'emiss': emissivity,
                'rp': 0.91, 'tnb': 0.866, 'rsky': 1.32})
        lst = rc.expression(
            'k2 / log(emiss * k1 / rc + 1)',
            {'emiss': emissivity, 'rc': rc, 'k1': k1, 'k2': k2})

        return lst.rename(['lst'])

    @staticmethod
    def _emissivity(toa_image):
        """Compute emissivity as a function of NDVI

        Parameters
        ----------
        toa_image : ee.Image

        Returns
        -------
        ee.Image

        """
        ndvi = Image._ndvi(toa_image)
        Pv = ndvi.expression(
            '((ndvi - 0.2) / 0.3) ** 2', {'ndvi': ndvi})
        # ndviRangevalue = ndvi_image.where(
        #     ndvi_image.gte(0.2).And(ndvi_image.lte(0.5)), ndvi_image)
        # Pv = ndviRangevalue.expression(
        # '(((ndviRangevalue - 0.2)/0.3)**2',{'ndviRangevalue':ndviRangevalue})

        # Assuming typical Soil Emissivity of 0.97 and Veg Emissivity of 0.99
        #   and shape Factor mean value of 0.553
        dE = Pv.expression(
            '(((1 - 0.97) * (1 - Pv)) * (0.55 * 0.99))', {'Pv': Pv})
        RangeEmiss = dE.expression(
            '((0.99 * Pv) + (0.97 * (1 - Pv)) + dE)', {'Pv': Pv, 'dE': dE})

        # RangeEmiss = 0.989 # dE.expression(
        #  '((0.99*Pv)+(0.97 *(1-Pv))+dE)',{'Pv':Pv, 'dE':dE})
        emissivity = ndvi \
            .where(ndvi.lt(0), 0.985) \
            .where(ndvi.gte(0).And(ndvi.lt(0.2)), 0.977) \
            .where(ndvi.gt(0.5), 0.99) \
            .where(ndvi.gte(0.2).And(ndvi.lte(0.5)), RangeEmiss)
        emissivity = emissivity.clamp(0.977, 0.99)

        return emissivity.select([0], ['emissivity'])

    @staticmethod
    def _lapse_adjust(temperature, elev, lapse_threshold=1500):
        """Compute Elevation Lapse Rate (ELR) adjusted temperature

        Parameters
        ----------
        temperature : ee.Image
            Temperature [K].
        elev : ee.Image
            Elevation [m].
        lapse_threshold : float
            Minimum elevation to adjust temperature [m] (the default is 1500).

        Returns
        -------
        ee.Image of adjusted temperature

        """
        elr_adjust = ee.Image(temperature).expression(
            '(temperature - (0.003 * (elev - threshold)))',
            {
                'temperature': temperature, 'elev': elev,
                'threshold': lapse_threshold
            })
        return ee.Image(temperature).where(elev.gt(lapse_threshold), elr_adjust)

    @lazy_property
    def tcorr_image(self):
        """Compute Tcorr for the current image

        Apply Tdiff cloud mask buffer (mask values of 0 are set to nodata)

        """
        lst = ee.Image(self.lst)
        ndvi = ee.Image(self.ndvi)
        tmax = ee.Image(self._tmax)

        # Compute tcorr
        tcorr = lst.divide(tmax)

        # Remove low LST and low NDVI
        tcorr_mask = lst.gt(270).And(ndvi.gt(0.7))

        # Filter extreme Tdiff values
        tdiff = tmax.subtract(lst)
        tcorr_mask = tcorr_mask.And(
            tdiff.gt(0).And(tdiff.lte(self._tdiff_threshold)))

        return tcorr.updateMask(tcorr_mask).rename(['tcorr']) \
            .set({'system:index': self._index,
                  'system:time_start': self._time_start,
                  'TMAX_SOURCE': tmax.get('TMAX_SOURCE'),
                  'TMAX_VERSION': tmax.get('TMAX_VERSION')})

    @lazy_property
    def tcorr_stats(self):
        """Compute the Tcorr 5th percentile and count statistics"""
        image_proj = self.image.select([0]).projection()
        image_crs = image_proj.crs()
        image_geo = ee.List(ee.Dictionary(
            ee.Algorithms.Describe(image_proj)).get('transform'))
        # image_shape = ee.List(ee.Dictionary(ee.List(ee.Dictionary(
        #     ee.Algorithms.Describe(self.image)).get('bands')).get(0)).get('dimensions'))
        # print(image_shape.getInfo())
        # print(image_crs.getInfo())
        # print(image_geo.getInfo())

        return ee.Image(self.tcorr_image).reduceRegion(
            reducer=ee.Reducer.percentile([5]).combine(ee.Reducer.count(), '', True),
            crs=image_crs,
            crsTransform=image_geo,
            geometry=ee.Image(self.image).geometry().buffer(1000),
            bestEffort=False,
            maxPixels=2*10000*10000,
            tileScale=1)
