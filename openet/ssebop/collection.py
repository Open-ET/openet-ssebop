import datetime
import pprint

from dateutil.relativedelta import *
import ee

from . import utils
from .image import Image
import openet.core.interp as interp
# TODO: import utils from openet.core
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


class Collection():
    """"""

    def __init__(
            self,
            collections,
            start_date,
            end_date,
            geometry,
            variables=None,
            etr_source='IDAHO_EPSCOR/GRIDMET',
            etr_band='etr',
            cloud_cover_max=70,
            filter_args={},
            model_args={},
            **kwargs
        ):
        """Earth Engine based SSEBop Image Collection

        Parameters
        ----------
        collections : list
            GEE satellite image collection IDs.
        start_date : str
            ISO format inclusive start date (i.e. YYYY-MM-DD).
        end_date : str
            ISO format exclusive end date (i.e. YYYY-MM-DD).
            This date needs to be exclusive since it will be passed directly
            to the .filterDate() calls.
        geometry : ee.Geometry
            The geometry object will be used to filter the input collections
            using the ee.ImageCollection.filterBounds() method.
        variables : list, optional
            Output variables can also be specified in the method calls.
        etr_source : str, float, optional
            Reference ET source (the default is 'IDAHO_EPSCOR/GRIDMET').
            If source is a list,
        etr_band : str, optional
            Reference ET band name (the default is 'etr').
        cloud_cover_max : float
            Maximum cloud cover percentage (the default is 70%).
                - Landsat TOA: CLOUD_COVER_LAND
                - Landsat SR: CLOUD_COVER_LAND
        filter_args : dict
            Image collection filter keyword arguments (the default is None).
            Organize filter arguments as a nested dictionary with the primary
            key being the collection ID.
        model_args : dict
            Model Image initialization keyword arguments (the default is None).
        kwargs : dict

        """
        self.collections = collections
        self.variables = variables
        self.start_date = start_date
        self.end_date = end_date
        self.geometry = geometry
        self.cloud_cover_max = cloud_cover_max
        self.model_args = model_args
        self.filter_args = filter_args

        # Pass the ETr parameters through as model keyword arguments
        self.etr_source = etr_source
        self.etr_band = etr_band
        self.model_args['etr_source'] = etr_source
        self.model_args['etr_band'] = etr_band

        # Model specific variables that can be interpolated to a daily timestep
        # Should this be specified in the interpolation method instead?
        self._interp_vars = ['ndvi', 'etf']
        # self._interp_vars = ['ndvi', 'etf', 'qa']

        self._landsat_c1_toa_collections = [
            'LANDSAT/LC08/C01/T1_RT_TOA',
            'LANDSAT/LE07/C01/T1_RT_TOA',
            'LANDSAT/LC08/C01/T1_TOA',
            'LANDSAT/LE07/C01/T1_TOA',
            'LANDSAT/LT05/C01/T1_TOA',
            # 'LANDSAT/LT04/C01/T1_TOA',
        ]
        self._landsat_c1_sr_collections = [
            'LANDSAT/LC08/C01/T1_SR',
            'LANDSAT/LE07/C01/T1_SR',
            'LANDSAT/LT05/C01/T1_SR',
            'LANDSAT/LT04/C01/T1_SR',
        ]

        # Check that collection IDs are supported
        for coll_id in collections:
            if (coll_id not in self._landsat_c1_toa_collections and
                    coll_id not in self._landsat_c1_sr_collections):
                raise ValueError('unsupported collection')

        # Check that collections don't have "duplicates"
        #   (i.e TOA and SR or TOA and TOA_RT for same Landsat)
        def duplicates(x):
            return len(x) != len(set(x))
        if duplicates([c.split('/')[1] for c in self.collections]):
            raise ValueError('duplicate landsat types in collection list')

        # Check start/end date
        if not utils.valid_date(self.start_date):
            raise ValueError('start_date is not a valid')
        elif not utils.valid_date(self.end_date):
            raise ValueError('end_date is not valid')
        elif not self.start_date < self.end_date:
            raise ValueError('end_date must be after start_date')

        # Check cloud_cover_max
        if not utils.is_number(self.cloud_cover_max):
            raise ValueError('cloud_cover_max must be a number')
        elif self.cloud_cover_max < 0 or self.cloud_cover_max > 100:
            raise ValueError('cloud_cover_max must be in the range 0 to 100')

        # Check geometry?
        # if not isinstance(self.geometry, computedobject.ComputedObject):
        #     raise ValueError()


    def _build(self, variables=None, start_date=None, end_date=None):
        """Build a merged model variable image collection

        Parameters
        ----------
        variables : list
            Set a variable list that is different than the class variable list.
        start_date : str, optional
            Set a start_date that is different than the class start_date.
            This is needed when defining the scene collection to have extra
            images for interpolation.
        end_date : str, optional
            Set a end_date that is different than the class end_date.

        Returns
        -------
        ee.ImageCollection

        Raises
        ------
        ValueError if collection IDs are invalid.

        """

        # Override the class parameters if necessary
        if variables is None:
            if self.variables:
                variables = self.variables
            else:
                raise ValueError('variables parameter must be set')
        if start_date is None or not start_date:
            start_date = self.start_date
        if end_date is None :
            end_date = self.end_date

        # Build the variable image collection
        variable_coll = ee.ImageCollection([])
        for coll_id in self.collections:

            # DEADBEEF - Move to separate methods/functions for each type
            if coll_id in self._landsat_c1_toa_collections:
                input_coll = ee.ImageCollection(coll_id) \
                    .filterDate(start_date, end_date) \
                    .filterBounds(self.geometry) \
                    .filterMetadata('DATA_TYPE', 'equals', 'L1TP') \
                    .filterMetadata(
                        'CLOUD_COVER_LAND', 'less_than', self.cloud_cover_max)

                # DEADBEEF - Need to come up with a system for applying
                #   generic filter arguments to the collections
                # What if DATA_TYPE was a list instead of string?
                # For now, always filter DATA_TYPE == L1TP
                # try:
                #     coll_filter_args = self.filter_args[coll_id]
                # except:
                #     coll_filter_args = {}

                def compute_ltoa(image):
                    model_obj = Image.from_landsat_c1_toa(
                        toa_image=ee.Image(image), **self.model_args)
                    return model_obj.calculate(variables)

                variable_coll = variable_coll.merge(
                    ee.ImageCollection(input_coll.map(compute_ltoa)))

            elif coll_id in self._landsat_c1_sr_collections:
                input_coll = ee.ImageCollection(coll_id) \
                    .filterDate(start_date, end_date) \
                    .filterBounds(self.geometry) \
                    .filterMetadata(
                        'CLOUD_COVER_LAND', 'less_than', self.cloud_cover_max)

                def compute_lsr(image):
                    model_obj = Image.from_landsat_c1_sr(
                        sr_image=ee.Image(image), **self.model_args)
                    return model_obj.calculate(variables)

                variable_coll = variable_coll.merge(
                    ee.ImageCollection(input_coll.map(compute_lsr)))

            else:
                raise ValueError('unsupported collection: {}'.format(coll_id))

        return variable_coll

    def overpass(self, variables=None):
        """Return a collection of computed values for the overpass images

        Parameters
        ----------
        variables : list, optional
            List of variables that will be returned in the Image Collection.
            If variables is not set here it must be specified in the class
            instantiation call.

        Returns
        -------
        ee.ImageCollection

        Raises
        ------
        ValueError

        """
        # Does it make sense to use the class variable list if not set?
        if not variables:
            if self.variables:
                variables = self.variables
            else:
                raise ValueError('variables parameter must be set')

        return self._build(variables=variables)

    def interpolate(self, variables=None, t_interval='monthly',
                    interp_method='linear', interp_days=32):
        """

        Parameters
        ----------
        variables : list, optional
            List of variables that will be returned in the Image Collection.
            If variables is not set here it must be specified in the class
            instantiation call.
        t_interval : {'daily', 'monthly', 'annual'}, optional
            Time interval over which to interpolate and aggregate values
            (the default is 'monthly').
        interp_method : {'linear}, optional
            Interpolation method (the default is 'linear').
        interp_days : int, optional
            Number of extra days before the start date and after the end date
            to include in the interpolation calculation. (the default is 32).

        Returns
        -------
        ee.ImageCollection

        Raises
        ------
        ValueError

        Notes
        -----
        Not all variables can be interpolated to new time steps.
        Variables like ETr are simply summed whereas ETf is computed from the
        interpolated/aggregated values.

        """
        # Check that the input parameters are valid
        if t_interval.lower() not in ['daily', 'monthly', 'annual']:
            raise ValueError('unsupported t_interval: {}'.format(t_interval))
        elif interp_method.lower() not in ['linear']:
            raise ValueError('unsupported interp_method: {}'.format(
                interp_method))
        elif interp_days <= 0:
            raise ValueError('t_interval must be a positive integer')

        # Does it make sense to use the class variable list if not set?
        if not variables:
            if self.variables:
                variables = self.variables
            else:
                raise ValueError('variables parameter must be set')

        # Adjust start/end dates based on t_interval
        # Increase the date range to fully include the time interval
        start_dt = datetime.datetime.strptime(self.start_date, '%Y-%m-%d')
        end_dt = datetime.datetime.strptime(self.end_date, '%Y-%m-%d')
        if t_interval.lower() == 'annual':
            start_dt = datetime.datetime(start_dt.year, 1, 1)
            # Covert end date to inclusive, flatten to beginning of year,
            # then add a year which will make it exclusive
            end_dt -= relativedelta(days=+1)
            end_dt = datetime.datetime(end_dt.year, 1, 1)
            end_dt += relativedelta(years=+1)
        elif t_interval.lower() == 'monthly':
            start_dt = datetime.datetime(start_dt.year, start_dt.month, 1)
            end_dt -= relativedelta(days=+1)
            end_dt = datetime.datetime(end_dt.year, end_dt.month, 1)
            end_dt += relativedelta(months=+1)
        start_date = start_dt.strftime('%Y-%m-%d')
        end_date = end_dt.strftime('%Y-%m-%d')

        # The start/end date for the interpolation include more days
        # (+/- interp_days) than are included in the ETr collection
        interp_start_dt = start_dt - datetime.timedelta(days=interp_days)
        interp_end_dt = end_dt + datetime.timedelta(days=interp_days)
        interp_start_date = interp_start_dt.date().isoformat()
        interp_end_date = interp_end_dt.date().isoformat()
        # print('Start date: {}'.format(start_date))
        # print('End date:   {}'.format(end_date))
        # print('Interp start date: {}'.format(interp_start_date))
        # print('Interp end date:   {}'.format(interp_end_date))

        if type(self.etr_source) is str:
            # Assume a string source is an single image collection ID
            #   not an list of collection IDs or ee.ImageCollection
            daily_et_reference_coll = ee.ImageCollection(self.etr_source) \
                .filterDate(start_date, end_date) \
                .select([self.etr_band], ['etr'])
        # elif type(self.etr_source) is list:
        #     # Interpret as list of image collection IDs to composite/mosaic
        #     #   i.e. Spatial CIMIS and GRIDMET
        #     # CGM - The following from the Image class probably won't work
        #     #   I think the two collections will need to be joined together,
        #     #   probably in some sort of mapped function
        #     daily_et_reference_coll = ee.ImageCollection([])
        #     for coll_id in self.etr_source:
        #         coll = ee.ImageCollection(coll_id) \
        #             .select([self.etr_band]) \
        #             .filterDate(self.start_date, self.end_date)
        #         daily_et_reference_coll = daily_et_reference_coll.merge(coll)
        # elif isinstance(self.etr_source, computedobject.ComputedObject):
        #     # Interpret computed objects as image collections
        #     daily_et_reference_coll = ee.ImageCollection(self.etr_source) \
        #         .select([self.etr_band]) \
        #         .filterDate(self.start_date, self.end_date)
        else:
            raise ValueError('unsupported etr_source: {}'.format(
                self.etr_source))

        # Only interpolate variables that can be interpolated
        interp_vars = list(set(self._interp_vars) & set(variables))
        # To return ET, the ETf must be interpolated
        if 'et' in variables and 'etf' not in interp_vars:
            interp_vars.append('etf')
        # With the current interp.daily() function,
        #   something has to be interpolated in order to return etr
        if 'etr' in variables and 'etf' not in interp_vars:
            interp_vars.append('etf')

        # Build initial scene image collection
        scene_coll = self._build(
            variables=interp_vars, start_date=interp_start_date,
            end_date=interp_end_date)

        # Compute composite/mosaic images for each image date
        aggregate_coll = interp.aggregate_daily(
            image_coll=scene_coll,
            start_date=interp_start_date,
            end_date=interp_end_date)

        # Interpolate to a daily time step
        # NOTE: the daily function is not currently scaling the data but it is
        #   returning the target (etr) band
        daily_coll = interp.daily(
            target_coll=daily_et_reference_coll,
            source_coll=aggregate_coll,
            interp_method=interp_method,  interp_days=interp_days)

        # Compute ET from ETf and ETr (if necessary)
        # DEADBEEF - It might make more sense to compute and return this from
        #   the interp.daily() call instead
        if 'et' in variables:
            def compute_et(img):
                """This function assumes ETr and ETf are present"""
                return img.addBands(img.select(['etf']).multiply(
                    img.select(['etr'])).rename('et'))
                # img_dt = ee.Date(img.get('system:time_start'))
                # etr_coll = daily_et_reference_coll\
                #     .filterDate(img_dt, img_dt.advance(1, 'day'))
                # Set ETr to Landsat resolution/projection?
                # etr_img = img.select(['etf']).multiply(0)\
                #     .add(ee.Image(etr_coll.first())).rename('etr')
                # et_img = img.select(['etf']).multiply(etr_img).rename('et')
                # return img.addBands(et_img)
            daily_coll = daily_coll.map(compute_et)
        # pprint.pprint(daily_coll.first().getInfo())

        # DEADBEEF - Some of this functionality could be moved to core
        #   The monthly and annual aggregation code is almost identical

        # Combine input, interpolated, and derived values
        if t_interval == 'daily':
            return daily_coll.select(variables)

        elif t_interval == 'monthly':
            def month_gen(iter_start_dt, iter_end_dt):
                iter_dt = iter_start_dt
                # Conditional is "less than" because end date is exclusive
                while iter_dt < iter_end_dt:
                    yield iter_dt.strftime('%Y-%m-%d')
                    iter_dt += relativedelta(months=+1)

            month_list = list(month_gen(start_dt, end_dt))

            def aggregate_monthly(agg_start_date):
                agg_end_date = ee.Date(agg_start_date).advance(1, 'month')
                if 'et' in variables or 'etf' in variables:
                    et_img = daily_coll.select(['et'])\
                        .filterDate(agg_start_date, agg_end_date)\
                        .sum()
                if 'etr' in variables or 'etf' in variables:
                    etr_img = daily_coll.select(['etr'])\
                        .filterDate(agg_start_date, agg_end_date)\
                        .sum()

                image_list = []
                if 'et' in variables:
                    image_list.append(et_img)
                if 'etr' in variables:
                    image_list.append(etr_img)
                if 'etf' in variables:
                    etf_img = et_img.divide(etr_img).rename('etf')
                    image_list.append(etf_img)
                if 'ndvi' in variables:
                    ndvi_img = daily_coll\
                        .filterDate(agg_start_date, agg_end_date) \
                        .mean().select(['ndvi'])
                    image_list.append(ndvi_img)

                return ee.Image(image_list).set({
                    'system:index': ee.Date(agg_start_date).format('YYYYMM'),
                    'system:time_start': ee.Date(agg_start_date).millis(),
                })

            return ee.ImageCollection(ee.List(month_list).map(aggregate_monthly))

        elif t_interval == 'annual':
            # CGM - All of this code is almost identical to the monthly function above
            def year_gen(iter_start_dt, iter_end_dt):
                iter_dt = iter_start_dt
                while iter_dt < iter_end_dt:
                    yield iter_dt.strftime('%Y-%m-%d')
                    iter_dt += relativedelta(years=+1)
            year_list = list(year_gen(start_dt, end_dt))

            def aggregate_annual(agg_start_date):
                agg_end_date = ee.Date(agg_start_date).advance(1, 'year')
                if 'et' in variables or 'etf' in variables:
                    et_img = daily_coll.select(['et']) \
                        .filterDate(agg_start_date, agg_end_date) \
                        .sum()
                if 'etr' in variables or 'etf' in variables:
                    etr_img = daily_coll.select(['etr']) \
                        .filterDate(agg_start_date, agg_end_date) \
                        .sum()

                image_list = []
                if 'et' in variables:
                    image_list.append(et_img)
                if 'etr' in variables:
                    image_list.append(etr_img)
                if 'etf' in variables:
                    etf_img = et_img.divide(etr_img).rename('etf')
                    image_list.append(etf_img)
                if 'ndvi' in variables:
                    ndvi_img = daily_coll \
                        .filterDate(agg_start_date, agg_end_date) \
                        .mean().select(['ndvi'])
                    image_list.append(ndvi_img)

                return ee.Image(image_list).set({
                    'system:index': ee.Date(agg_start_date).format('YYYY'),
                    'system:time_start': ee.Date(agg_start_date).millis(),
                })

            return ee.ImageCollection(ee.List(year_list).map(aggregate_annual))


    def get_image_ids(self):
        """Return image IDs of the input images

        Returns
        -------
        list

        """
        # DEADBEEF - This doesn't return the extra images used for interpolation
        #   and may not be that useful of a method
        # CGM - Could the build function and Image class support returning
        #   the system:index?
        output = list(self._build(variables=['ndvi'])\
            .aggregate_histogram('IMAGE_ID').getInfo().keys())
        return sorted(output)
        # Strip merge indices (this works for Landsat image IDs
        # return sorted(['_'.join(x.split('_')[-3:]) for x in output])
