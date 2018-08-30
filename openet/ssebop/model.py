import logging
import sys

import ee

system_properties = ['system:index', 'system:time_start']


def collection(
        variable,
        collections,
        start_date,
        end_date,
        t_interval,
        geometry,
        **kwargs
        ):
    """Generic OpenET Collection

    Parameters
    ----------
    self :
    variable : str

    collections : list
        GEE satellite image collection IDs.
    start_date : str
        ISO format inclusive start date (i.e. YYYY-MM-DD).
    end_date : str
        ISO format exclusive end date (i.e. YYYY-MM-DD).
    t_interval : {'daily', 'monthly', 'annual', 'overpass'}
        Time interval over which to interpolate and aggregate values.
        Selecting 'overpass' will return values only for the overpass dates.
    geometry : ee.Geometry
        The geometry object will be used to filter the input collections.
    kwargs :

    Returns
    -------
    ee.ImageCollection

    """

    # CGM - Make this a global or collection property?
    landsat_c1_toa_collections = [
        'LANDSAT/LC08/C01/T1_RT_TOA',
        'LANDSAT/LE07/C01/T1_RT_TOA',
        'LANDSAT/LC08/C01/T1_TOA',
        'LANDSAT/LE07/C01/T1_TOA',
        'LANDSAT/LT05/C01/T1_TOA',
    ]

    # TODO: Test whether the requested variable is supported

    # Build the variable image collection
    variable_coll = ee.ImageCollection([])
    for coll_id in collections:
        if coll_id in landsat_c1_toa_collections:
            def compute(image):
                model_obj = SSEBop.from_landsat_c1_toa(
                    toa_image=ee.Image(image))
                return ee.Image(model_obj.get_variable(variable))
        else:
            raise ValueError('unsupported collection: {}'.format(coll_id))

        var_coll = ee.ImageCollection(coll_id) \
            .filterDate(start_date, end_date) \
            .filterBounds(geometry) \
            .map(compute)

        # TODO: Allow additional filter parameters (like CLOUD_COVER_LAND for Landsat)
        # .filterMetadata() \

        variable_coll = variable_coll.merge(var_coll)

    # TODO: Add interpolation component

    # Interpolate/aggregate to t_interval
    # Should this only be allowed for specific variables (ETf, ETa)?
    # We would need a daily reference collection to get to ET
    # output_coll = openet.interp.interpolate(variable_coll)

    return variable_coll


class SSEBop():
    def __init__(
            self, image,
            k_factor=1.0,
            dt_source='ASSET',
            elev_source='ASSET',
            tcorr_source='SCENE',
            tmax_source='GRIDMET',
            tdiff_threshold=15,
            **kwargs
            ):
        """Initialize an image for computing SSEBop.

        Parameters
        ----------
        image :  ee.Image
            A SSEBop input image.
            Image must have bands: "ndvi" and "lst".
        k_factor : float, optional
            Scale factor for ETf (or ETo) values.
            Used to convert ETf from "ETrF" (0-1) to EToF (0-1.2) to match ETo
            (Or to convert ETo to ETr).
        dt_source : {'ASSET'}, optional
            dT data set keyword (the default is 'ASSET').
        elev_source : {'ASSET', 'GTOPO', 'NED', 'SRTM'}, optional
            Elevation data set keyword (the default is 'ASSET').
        tcorr_source : {'SCENE', 'MONTHLY', or constant}, optional
            Tcorr data set keyword (the default is 'SCENE').
        tmax_source :  {'DAYMET', 'GRIDMET', 'TOPOWX_MEDIAN'}, optional
            Maximum air temperature data set keyword (the default is 'DAYMET').
        tdiff_threshold :  float, optional
            Cloud mask buffer using Tdiff (in K) (the default is 15).
        kwargs :

        Notes
        -----
        Currently image must have a Landsat style 'system:index' in order to
        lookup Tcorr value from table asset.  (i.e. LC08_043033_20150805)

        """
        input_image = ee.Image(image)

        # Unpack the input bands as properties
        self.lst = input_image.select('lst')
        self.ndvi = input_image.select('ndvi')

        # Copy system properties
        self.index = input_image.get('system:index')
        self.time_start = input_image.get('system:time_start')

        # Build SCENE_ID from the (possibly merged) system:index
        scene_id = ee.List(ee.String(self.index).split('_')).slice(-3)
        self.scene_id = ee.String(scene_id.get(0)).cat('_') \
            .cat(ee.String(scene_id.get(1))).cat('_') \
            .cat(ee.String(scene_id.get(2)))

        # Build WRS2_TILE from the scene_id
        self.wrs2_tile = ee.String('p').cat(self.scene_id.slice(5, 8)) \
            .cat('r').cat(self.scene_id.slice(8, 11))

        # Set server side date/time properties using the 'system:time_start'
        self.date = ee.Date(self.time_start)
        self.year = ee.Number(self.date.get('year'))
        self.month = ee.Number(self.date.get('month'))
        self.start_date = ee.Date(_date_to_time_0utc(self.date))
        self.end_date = self.start_date.advance(1, 'day')
        self.doy = ee.Number(self.date.getRelative('day', 'year')).add(1).int()

        # Input parameters
        self.dt_source = dt_source
        self.elev_source = elev_source
        self.tcorr_source = tcorr_source
        self.tmax_source = tmax_source
        self.k_factor = k_factor
        self.tdiff_threshold = tdiff_threshold

    def get_variable(self, variable):
        if variable == 'etf':
            return self.etf()
        # CGM - Returning ET requires ETr to be passed in (maybe via kwargs)
        # elif variable == 'et':
        #     return self.et()
        elif variable == 'lst':
            return self.lst
        elif variable == 'ndvi':
            return self.ndvi

    def etf(self):
        """Compute SSEBop ETf for a single image

        Apply Tdiff cloud mask buffer (mask values of 0 are set to nodata)

        """
        # Get input images and ancillary data needed to compute SSEBop ETf
        lst = ee.Image(self.lst)
        tcorr, tcorr_index = self._tcorr()
        tmax = ee.Image(self._tmax())
        dt = ee.Image(self._dt())

        # Compute SSEBop ETf
        etf = lst.expression(
            '(lst * (-1) + tmax * tcorr + dt) / dt',
            {'tmax': tmax, 'dt': dt, 'lst': lst, 'tcorr': tcorr})
        etf = etf.updateMask(etf.lt(1.3)) \
            .clamp(0, 1.05) \
            .updateMask(tmax.subtract(lst).lte(self.tdiff_threshold)) \
            .setMulti({
                'system:index': self.index,
                'system:time_start': self.time_start,
                'TCORR': tcorr,
                'TCORR_INDEX': tcorr_index})
        return ee.Image(etf).rename(['etf'])

    def _dt(self):
        """"""
        if _is_number(self.dt_source):
            return ee.Image.constant(self.dt_source).set('DOY', self.doy)
        elif self.dt_source.upper() == 'ASSET':
            dt_coll = ee.ImageCollection('projects/usgs-ssebop/daymet_dt_median') \
                .filter(ee.Filter.calendarRange(self.doy, self.doy, 'day_of_year'))
            return ee.Image(dt_coll.first())
        else:
            logging.error('\nInvalid dT: {}\n'.format(self.dt_source))
            sys.exit()

    def _elev(self):
        """"""
        if _is_number(self.elev_source):
            elev_image = ee.Image.constant(ee.Number(self.elev_source))
        elif self.elev_source.upper() == 'ASSET':
            elev_image = ee.Image('projects/usgs-ssebop/srtm_1km')
        elif self.elev_source.upper() == 'GTOPO':
            elev_image = ee.Image('USGS/GTOPO30')
        elif self.elev_source.upper() == 'NED':
            elev_image = ee.Image('USGS/NED')
        elif self.elev_source.upper() == 'SRTM':
            elev_image = ee.Image('CGIAR/SRTM90_V4')
        else:
            logging.error('\nUnsupported elev_source: {}\n'.format(
                self.elev_source))
            sys.exit()
        return elev_image.select([0], ['elev'])

    def _tcorr(self):
        """Get Tcorr from pre-computed assets for each Tmax source

        This function is setup to get Tcorr based on the following priority:
          1) user specificed Tcorr value
          2) pre-compted scene specific Tcorr if available
          3) pre-computed WRS2 tile (path/row) monthly Tcorr if avaiable
          4) global default Tcorr of 0.978

        The Tcorr collections are a function the Tmax dataset that is used.
        Each Tcorr collection has an "INDEX" which specificed the priority
        (see table below) with lower values being preferred.
        The Tcorr prioritization is done my merging the collections,
        sorting based on the INDEX, and taking the first object.

        Tcorr INDEX values indicate
          0 - Scene specific Tcorr
          1 - Mean monthly Tcorr per WRS2 tile
          2 - Default Tcorr
          3 - User defined Tcorr

        Returns:
            ee.Number: Tcorr value
            ee.Number: Tcorr INDEX value
        """

        if _is_number(self.tcorr_source):
            tcorr = ee.Number(self.tcorr_source)
            tcorr_index = ee.Number(3)
        elif (self.tcorr_source.upper() == 'SCENE' and
              self.tmax_source.upper() == 'DAYMET'):
            default_coll = ee.FeatureCollection([
                ee.Feature(None, {'INDEX': 2, 'TCORR': 0.978})])
            month_coll = ee.FeatureCollection(
                    'projects/usgs-ssebop/tcorr_daymet_monthly') \
                .filterMetadata('WRS2_TILE', 'equals', self.wrs2_tile) \
                .filterMetadata('MONTH', 'equals', self.month)
            scene_coll = ee.FeatureCollection(
                    'projects/usgs-ssebop/tcorr_daymet') \
                .filterMetadata('SCENE_ID', 'equals', self.scene_id)
            tcorr_coll = ee.FeatureCollection(
                default_coll.merge(month_coll).merge(scene_coll)).sort('INDEX')
            tcorr_ftr = ee.Feature(tcorr_coll.first())
            tcorr = ee.Number(tcorr_ftr.get('TCORR'))
            tcorr_index = ee.Number(tcorr_ftr.get('INDEX'))
        elif (self.tcorr_source.upper() == 'MONTH' and
              self.tmax_source.upper() == 'DAYMET'):
            default_coll = ee.FeatureCollection([
                ee.Feature(None, {'INDEX': 2, 'TCORR': 0.978})])
            month_coll = ee.FeatureCollection(
                'projects/usgs-ssebop/tcorr_daymet_monthly') \
                .filterMetadata('WRS2_TILE', 'equals', self.wrs2_tile) \
                .filterMetadata('MONTH', 'equals', self.month)
            tcorr_coll = ee.FeatureCollection(
                default_coll.merge(month_coll)).sort('INDEX')
            tcorr_ftr = ee.Feature(tcorr_coll.first())
            tcorr = ee.Number(tcorr_ftr.get('TCORR'))
            tcorr_index = ee.Number(tcorr_ftr.get('INDEX'))
        elif (self.tcorr_source.upper() == 'SCENE' and
              self.tmax_source.upper() == 'GRIDMET'):
            default_coll = ee.FeatureCollection([
                ee.Feature(None, {'INDEX': 2, 'TCORR': 0.978})])
            month_coll = ee.FeatureCollection(
                'projects/usgs-ssebop/tcorr_gridmet_monthly') \
                .filterMetadata('WRS2_TILE', 'equals', self.wrs2_tile) \
                .filterMetadata('MONTH', 'equals', self.month)
            scene_coll = ee.FeatureCollection(
                'projects/usgs-ssebop/tcorr_gridmet') \
                .filterMetadata('SCENE_ID', 'equals', self.scene_id)
            tcorr_coll = ee.FeatureCollection(
                default_coll.merge(month_coll).merge(scene_coll)).sort('INDEX')
            tcorr_ftr = ee.Feature(tcorr_coll.first())
            tcorr = ee.Number(tcorr_ftr.get('TCORR'))
            tcorr_index = ee.Number(tcorr_ftr.get('INDEX'))
        elif (self.tcorr_source.upper() == 'MONTH' and
              self.tmax_source.upper() == 'GRIDMET'):
            default_coll = ee.FeatureCollection([
                ee.Feature(None, {'INDEX': 2, 'TCORR': 0.978})])
            month_coll = ee.FeatureCollection(
                'projects/usgs-ssebop/tcorr_gridmet_monthly') \
                .filterMetadata('WRS2_TILE', 'equals', self.wrs2_tile) \
                .filterMetadata('MONTH', 'equals', self.month)
            tcorr_coll = ee.FeatureCollection(
                default_coll.merge(month_coll)).sort('INDEX')
            tcorr_ftr = ee.Feature(tcorr_coll.first())
            tcorr = ee.Number(tcorr_ftr.get('TCORR'))
            tcorr_index = ee.Number(tcorr_ftr.get('INDEX'))
        else:
            logging.error(
                '\nInvalid tcorr_source/tmax_source: {} / {}\n'.format(
                    self.tcorr_source, self.tmax_source))
            sys.exit()
        return tcorr, tcorr_index

    def _tmax(self):
        if _is_number(self.tmax_source):
            return ee.Image.constant(self.tmax_source).rename(['tmax'])
        elif self.tmax_source.upper() == 'DAYMET':
            # DAYMET does not include Dec 31st on leap years
            # Adding one extra date to end date to avoid errors
            tmax_coll = ee.ImageCollection('NASA/ORNL/DAYMET_V3') \
                .filterDate(self.start_date, self.end_date.advance(1, 'day')) \
                .select(['tmax']) \
                .map(_c_to_k)
            return ee.Image(tmax_coll.first())
        elif self.tmax_source.upper() == 'GRIDMET':
            tmax_coll = ee.ImageCollection('IDAHO_EPSCOR/GRIDMET') \
                .filterDate(self.start_date, self.end_date) \
                .select(['tmmx'], ['tmax'])
            return ee.Image(tmax_coll.first())
        else:
            logging.error('\nUnsupported tmax_source: {}\n'.format(
                self.tmax_source))
            sys.exit()

    @classmethod
    def from_landsat_c1_toa(cls, toa_image, **kwargs):
        """Constructs a SSEBop object from a Landsat TOA image

        Parameters
        ----------
        toa_image : ee.Image
            A raw Landsat Collection 1 TOA image.

        Returns
        -------
        SSEBop

        """
        # Use the SPACECRAFT_ID property identify each Landsat type
        spacecraft_id = ee.String(ee.Image(toa_image).get('SPACECRAFT_ID'))

        # Rename bands to generic names
        # Rename thermal band "k" coefficients to generic names
        input_bands = ee.Dictionary({
            'LANDSAT_5': ['B1', 'B2', 'B3', 'B4', 'B5', 'B7', 'B6', 'BQA'],
            'LANDSAT_7': ['B1', 'B2', 'B3', 'B4', 'B5', 'B7', 'B6_VCID_1', 'BQA'],
            'LANDSAT_8': ['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B10', 'BQA']})
        output_bands = [
            'blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'lst', 'BQA']
        k1 = ee.Dictionary({
            'LANDSAT_5': 'K1_CONSTANT_BAND_6',
            'LANDSAT_7': 'K1_CONSTANT_BAND_6_VCID_1',
            'LANDSAT_8': 'K1_CONSTANT_BAND_10'})
        k2 = ee.Dictionary({
            'LANDSAT_5': 'K2_CONSTANT_BAND_6',
            'LANDSAT_7': 'K2_CONSTANT_BAND_6_VCID_1',
            'LANDSAT_8': 'K2_CONSTANT_BAND_10'})
        prep_image = ee.Image(toa_image) \
            .select(input_bands.get(spacecraft_id), output_bands) \
            .set('k1_constant', ee.Number(ee.Image(toa_image).get(k1.get(spacecraft_id)))) \
            .set('k2_constant', ee.Number(ee.Image(toa_image).get(k2.get(spacecraft_id))))

        # Build the input image
        input_image = ee.Image([
            cls._lst(prep_image),
            cls._ndvi(prep_image)
        ])

        # Add properties and instantiate class
        input_image = ee.Image(input_image.setMulti({
            'system:index': ee.Image(toa_image).get('system:index'),
            'system:time_start': ee.Image(toa_image).get('system:time_start')
        }))

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
            Renamed TOA image with 'red' and 'nir' bands.

        Returns
        -------
        ee.Image

        Notes
        -----
        Note, the coefficients were derived from a small number of scenes in
        southern Idaho [Allen2007] and may not be appropriate for other areas.

        References
        ----------
        .. [ALlen2007a] R. Allen, M. Tasumi, R. Trezza (2007),
            Satellite-Based Energy Balance for Mapping Evapotranspiration with
            Internalized Calibration (METRIC) Model,
            Journal of Irrigation and Drainage Engineering, Vol 133(4),
            http://dx.doi.org/10.1061/(ASCE)0733-9437(2007)133:4(380)

        """
        # Get properties from image
        k1 = ee.Number(ee.Image(toa_image).get('k1_constant'))
        k2 = ee.Number(ee.Image(toa_image).get('k2_constant'))

        ts_brightness = ee.Image(toa_image).select(['lst'])
        emissivity = SSEBop._emissivity(toa_image)

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
        ndvi = SSEBop._ndvi(toa_image)
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
            .where((ndvi.gte(0)).And(ndvi.lt(0.2)), 0.977) \
            .where(ndvi.gt(0.5), 0.99) \
            .where((ndvi.gte(0.2)).And(ndvi.lte(0.5)), RangeEmiss)
        emissivity = emissivity.clamp(0.977, 0.99)
        return emissivity.select([0], ['emissivity']) \
            .copyProperties(ndvi, system_properties)

# Eventually move to common or utils
def _c_to_k(image):
    """Convert temperature from C to K"""
    return image.add(273.15) \
        .copyProperties(image, system_properties)


def _date_to_time_0utc(date):
    """Get the 0 UTC time_start for a date

    Extra operations are needed since update() does not set milliseconds to 0.

    Args:
        date (ee.Date):

    Returns:
        ee.Number
    """
    return date.update(hour=0, minute=0, second=0).millis()\
        .divide(1000).floor().multiply(1000)


def _is_number(x):
    try:
        float(x)
        return True
    except:
        return False
