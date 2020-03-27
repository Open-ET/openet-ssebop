import copy
import datetime
import pprint

from dateutil.relativedelta import *
import ee

from . import utils
from .image import Image
# Importing to get version number, is there a better way?
import openet.ssebop
import openet.core.interpolate
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
            cloud_cover_max=70,
            et_reference_source=None,
            et_reference_band=None,
            et_reference_factor=None,
            et_reference_resample=None,
            filter_args=None,
            model_args=None,
            # model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
            #             'et_reference_band': 'etr',
            #             'et_reference_factor': 0.85,
            #             'et_reference_resample': 'bilinear},
            # **kwargs
        ):
        """Earth Engine based SSEBop Image Collection

        Parameters
        ----------
        collections : list, str
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
        cloud_cover_max : float, str
            Maximum cloud cover percentage (the default is 70%).
                - Landsat TOA: CLOUD_COVER_LAND
                - Landsat SR: CLOUD_COVER_LAND
        et_reference_source : str, float, optional
            Reference ET source (the default is None).  Source must
            be set here or in model args to interpolate ET, ETf, or ETr.
        et_reference_band : str, optional
            Reference ET band name (the default is None).  Band must
            be set here or in model args to interpolate ET, ETf, or ETr.
        et_reference_factor : float, None, optional
            Reference ET scaling factor.  The default is None which is
            equivalent to 1.0 (or no scaling).
        et_reference_resample : {'nearest', 'bilinear', 'bicubic', None}, optional
            Reference ET resampling.  The default is None which is equivalent
            to nearest neighbor resampling.
        filter_args : dict
            Image collection filter keyword arguments (the default is None).
            Organize filter arguments as a nested dictionary with the primary
            key being the collection ID.
        model_args : dict
            Model Image initialization keyword arguments (the default is None).
            Dictionary will be passed through to model Image init.

        """
        self.collections = collections
        self.variables = variables
        self.start_date = start_date
        self.end_date = end_date
        self.geometry = geometry
        self.cloud_cover_max = cloud_cover_max

        # CGM - Should we check that model_args and filter_args are dict?
        if model_args is not None:
            self.model_args = model_args
        else:
            self.model_args = {}
        if filter_args is not None:
            self.filter_args = filter_args
        else:
            self.filter_args = {}

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

        # Set/update the reference ET parameters in model_args if they were set in init()
        if self.et_reference_source:
            self.model_args['et_reference_source'] = self.et_reference_source
        if self.et_reference_band:
            self.model_args['et_reference_band'] = self.et_reference_band
        if self.et_reference_factor:
            self.model_args['et_reference_factor'] = self.et_reference_factor
        if self.et_reference_resample:
            self.model_args['et_reference_resample'] = self.et_reference_resample

        # Model specific variables that can be interpolated to a daily timestep
        # CGM - Should this be specified in the interpolation method instead?
        self._interp_vars = ['ndvi', 'et_fraction']

        self._landsat_c1_sr_collections = [
            'LANDSAT/LC08/C01/T1_SR',
            'LANDSAT/LE07/C01/T1_SR',
            'LANDSAT/LT05/C01/T1_SR',
            'LANDSAT/LT04/C01/T1_SR',
        ]
        self._landsat_c1_toa_collections = [
            'LANDSAT/LC08/C01/T1_RT_TOA',
            'LANDSAT/LE07/C01/T1_RT_TOA',
            'LANDSAT/LC08/C01/T1_TOA',
            'LANDSAT/LE07/C01/T1_TOA',
            'LANDSAT/LT05/C01/T1_TOA',
            'LANDSAT/LT04/C01/T1_TOA',
        ]

        # If collections is a string, place in a list
        if type(self.collections) is str:
            self.collections = [self.collections]

        # Check that collection IDs are supported
        for coll_id in self.collections:
            if (coll_id not in self._landsat_c1_sr_collections and
                    coll_id not in self._landsat_c1_toa_collections):
                raise ValueError('unsupported collection: {}'.format(coll_id))

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
        if (not type(self.cloud_cover_max) is int and
                not type(self.cloud_cover_max) is float and
                not utils.is_number(self.cloud_cover_max)):
            raise TypeError('cloud_cover_max must be a number')
        if (type(self.cloud_cover_max) is str and
                utils.is_number(self.cloud_cover_max)):
            self.cloud_cover_max = float(self.cloud_cover_max)
        if self.cloud_cover_max < 0 or self.cloud_cover_max > 100:
            raise ValueError('cloud_cover_max must be in the range 0 to 100')

        # # Attempt to cast string geometries to ee.Geometry
        # # This should work for geojson
        # if isinstance(self.geometry, ee.computedobject.ComputedObject):
        #     pass
        # elif type(self.geometry) is str:
        #     self.geometry = ee.Geometry(self.geometry())

        # Filter collection list based on start/end dates
        # if self.end_date <= '1982-01-01':
        #     self.collections = [c for c in self.collections if 'LT04' not in c]
        # if self.start_date >= '1994-01-01':
        #     self.collections = [c for c in self.collections if 'LT04' not in c]
        if self.end_date <= '1984-01-01':
            self.collections = [c for c in self.collections if 'LT05' not in c]
        if self.start_date >= '2012-01-01':
            self.collections = [c for c in self.collections if 'LT05' not in c]
        if self.end_date <= '1999-01-01':
            self.collections = [c for c in self.collections if 'LE07' not in c]
        if self.end_date <= '2013-01-01':
            self.collections = [c for c in self.collections if 'LC08' not in c]

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
            Set an exclusive end_date that is different than the class end_date.

        Returns
        -------
        ee.ImageCollection

        Raises
        ------
        ValueError if collection IDs are invalid.
        ValueError if variables is not set here and in class init.

        """
        # Override the class parameters if necessary
        if not variables:
            if self.variables:
                variables = self.variables
            else:
                raise ValueError('variables parameter must be set')
        if not start_date:
            start_date = self.start_date
        if not end_date:
            end_date = self.end_date

        # Build the variable image collection
        variable_coll = ee.ImageCollection([])
        for coll_id in self.collections:
            # DEADBEEF - Move to separate methods/functions for each type
            if coll_id in self._landsat_c1_toa_collections:
                input_coll = ee.ImageCollection(coll_id)\
                    .filterDate(start_date, end_date)\
                    .filterBounds(self.geometry)\
                    .filterMetadata('DATA_TYPE', 'equals', 'L1TP')\
                    .filterMetadata('CLOUD_COVER_LAND', 'less_than',
                                    self.cloud_cover_max)

                # TODO: Need to come up with a system for applying
                #   generic filter arguments to the collections
                if coll_id in self.filter_args.keys():
                    for f in copy.deepcopy(self.filter_args[coll_id]):
                        try:
                            filter_type = f.pop('type')
                        except KeyError:
                            continue
                        if filter_type.lower() == 'equals':
                            input_coll = input_coll.filter(ee.Filter.equals(**f))

                # Time filters are to remove bad (L5) and pre-op (L8) images
                if 'LT05' in coll_id:
                    input_coll = input_coll.filter(ee.Filter.lt(
                        'system:time_start', ee.Date('2011-12-31').millis()))
                elif 'LC08' in coll_id:
                    input_coll = input_coll.filter(ee.Filter.gt(
                        'system:time_start', ee.Date('2013-03-24').millis()))

                def compute_ltoa(image):
                    model_obj = Image.from_landsat_c1_toa(
                        toa_image=ee.Image(image), **self.model_args)
                    return model_obj.calculate(variables)

                variable_coll = variable_coll.merge(
                    ee.ImageCollection(input_coll.map(compute_ltoa)))

            elif coll_id in self._landsat_c1_sr_collections:
                input_coll = ee.ImageCollection(coll_id)\
                    .filterDate(start_date, end_date)\
                    .filterBounds(self.geometry)\
                    .filterMetadata('CLOUD_COVER_LAND', 'less_than',
                                    self.cloud_cover_max)

                # TODO: Need to come up with a system for applying
                #   generic filter arguments to the collections
                if coll_id in self.filter_args.keys():
                    for f in copy.deepcopy(self.filter_args[coll_id]):
                        try:
                            filter_type = f.pop('type')
                        except KeyError:
                            continue
                        if filter_type.lower() == 'equals':
                            input_coll = input_coll.filter(ee.Filter.equals(**f))

                # Time filters are to remove bad (L5) and pre-op (L8) images
                if 'LT05' in coll_id:
                    input_coll = input_coll.filter(ee.Filter.lt(
                        'system:time_start', ee.Date('2011-12-31').millis()))
                elif 'LC08' in coll_id:
                    input_coll = input_coll.filter(ee.Filter.gt(
                        'system:time_start', ee.Date('2013-03-24').millis()))

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

    def interpolate(self, variables=None, t_interval='custom',
                    interp_method='linear', interp_days=32, **kwargs):
        """

        Parameters
        ----------
        variables : list, optional
            List of variables that will be returned in the Image Collection.
            If variables is not set here it must be specified in the class
            instantiation call.
        t_interval : {'daily', 'monthly', 'annual', 'custom'}, optional
            Time interval over which to interpolate and aggregate values
            (the default is 'monthly').
        interp_method : {'linear}, optional
            Interpolation method (the default is 'linear').
        interp_days : int, str, optional
            Number of extra days before the start date and after the end date
            to include in the interpolation calculation. (the default is 32).
        kwargs : dict, optional

        Returns
        -------
        ee.ImageCollection

        Raises
        ------
        ValueError for unsupported input parameters
        ValueError for negative interp_days values
        TypeError for non-integer interp_days

        Notes
        -----
        Not all variables can be interpolated to new time steps.
        Variables like reference ET are simply summed whereas ET fraction is
            computed from the interpolated/aggregated values.

        """
        # Check that the input parameters are valid
        if t_interval.lower() not in ['daily', 'monthly', 'annual', 'custom']:
            raise ValueError('unsupported t_interval: {}'.format(t_interval))
        elif interp_method.lower() not in ['linear']:
            raise ValueError('unsupported interp_method: {}'.format(
                interp_method))

        if type(interp_days) is str and utils.is_number(interp_days):
            interp_days = int(interp_days)
        elif not type(interp_days) is int:
            raise TypeError('interp_days must be an integer')
        elif interp_days <= 0:
            raise ValueError('interp_days must be a positive integer')

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
        # (+/- interp_days) than are included in the reference ET collection
        interp_start_dt = start_dt - datetime.timedelta(days=interp_days)
        interp_end_dt = end_dt + datetime.timedelta(days=interp_days)
        interp_start_date = interp_start_dt.date().isoformat()
        interp_end_date = interp_end_dt.date().isoformat()

        # Update model_args if reference ET parameters were passed to interpolate
        # Intentionally using model_args (instead of self.et_reference_source, etc.) in
        #   this function since model_args is passed to Image class in _build()
        # if 'et' in variables or 'et_reference' in variables:
        if ('et_reference_source' in kwargs.keys() and \
                kwargs['et_reference_source'] is not None):
            self.model_args['et_reference_source'] = kwargs['et_reference_source']
        if ('et_reference_band' in kwargs.keys() and \
                kwargs['et_reference_band'] is not None):
            self.model_args['et_reference_band'] = kwargs['et_reference_band']
        if ('et_reference_factor' in kwargs.keys() and \
                kwargs['et_reference_factor'] is not None):
            self.model_args['et_reference_factor'] = kwargs['et_reference_factor']
        if ('et_reference_resample' in kwargs.keys() and \
                kwargs['et_reference_resample'] is not None):
            self.model_args['et_reference_resample'] = kwargs['et_reference_resample']

        # Check that all reference ET parameters were set
        # print(self.model_args)
        for et_reference_param in ['et_reference_source', 'et_reference_band',
                                   'et_reference_factor']:
            if et_reference_param not in self.model_args.keys():
                raise ValueError('{} was not set'.format(et_reference_param))
            elif not self.model_args[et_reference_param]:
                raise ValueError('{} was not set'.format(et_reference_param))

        if type(self.model_args['et_reference_source']) is str:
            # Assume a string source is an single image collection ID
            #   not an list of collection IDs or ee.ImageCollection
            daily_et_ref_coll_id = self.model_args['et_reference_source']
            daily_et_ref_coll = ee.ImageCollection(daily_et_ref_coll_id)\
                .filterDate(start_date, end_date)\
                .select([self.model_args['et_reference_band']], ['et_reference'])
        # elif isinstance(self.model_args['et_reference_source'], computedobject.ComputedObject):
        #     # Interpret computed objects as image collections
        #     daily_et_ref_coll = self.model_args['et_reference_source'] \
        #         .filterDate(self.start_date, self.end_date) \
        #         .select([self.model_args['et_reference_band']])
        else:
            raise ValueError('unsupported et_reference_source: {}'.format(
                self.model_args['et_reference_source']))

        # Scale reference ET images (if necessary)
        # CGM - Resampling is not working correctly so not including for now
        if (self.model_args['et_reference_factor'] and
                self.model_args['et_reference_factor'] != 1):
            def et_reference_adjust(input_img):
                return input_img \
                    .multiply(self.model_args['et_reference_factor']) \
                    .copyProperties(input_img) \
                    .set({'system:time_start': input_img.get('system:time_start')})

            daily_et_ref_coll = daily_et_ref_coll.map(et_reference_adjust)

        # Initialize variable list to only variables that can be interpolated
        interp_vars = list(set(self._interp_vars) & set(variables))

        # To return ET, the ET fraction must be interpolated
        if 'et' in variables and 'et_fraction' not in interp_vars:
            interp_vars.append('et_fraction')

        # With the current interpolate.daily() function,
        #   something has to be interpolated in order to return et_reference
        if 'et_reference' in variables and 'et_fraction' not in interp_vars:
            interp_vars.append('et_fraction')

        # The time band is always needed for interpolation
        interp_vars.append('time')

        # Count will be determined using the aggregate_coll image masks
        if 'count' in variables:
            interp_vars.append('mask')
            # interp_vars.remove('count')

        # Build initial scene image collection
        scene_coll = self._build(
            variables=interp_vars, start_date=interp_start_date,
            end_date=interp_end_date)

        # For count, compute the composite/mosaic image for the mask band only
        if 'count' in variables:
            aggregate_coll = openet.core.interpolate.aggregate_to_daily(
                image_coll=scene_coll.select(['mask']),
                start_date=start_date, end_date=end_date)

            # The following is needed because the aggregate collection can be
            #   empty if there are no scenes in the target date range but there
            #   are scenes in the interpolation date range.
            # Without this the count image will not be built but the other
            #   bands will be which causes a non-homogenous image collection.
            aggregate_coll = aggregate_coll.merge(
                ee.Image.constant(0).rename(['mask'])
                    .set({'system:time_start': ee.Date(start_date).millis()}))

        # Including count/mask causes problems in interpolate.daily() function.
        # Issues with mask being an int but the values need to be double.
        # Casting the mask band to a double would fix this problem also.
        if 'mask' in interp_vars:
            interp_vars.remove('mask')

        # Interpolate to a daily time step
        # NOTE: the daily function is not computing ET (ETf x ETr)
        #   but is returning the target (ETr) band
        daily_coll = openet.core.interpolate.daily(
            target_coll=daily_et_ref_coll,
            source_coll=scene_coll.select(interp_vars),
            interp_method=interp_method,  interp_days=interp_days,
        )

        # Compute ET from ET fraction and reference ET (if necessary)
        # if 'et' in variables or 'et_fraction' in variables:
        def compute_et(img):
            """This function assumes reference ET and ET fraction are present"""
            et_img = img.select(['et_fraction'])\
                .multiply(img.select(['et_reference']))
            return img.addBands(et_img.rename('et'))
        daily_coll = daily_coll.map(compute_et)

        interp_properties = {
            'cloud_cover_max': self.cloud_cover_max,
            'collections': ', '.join(self.collections),
            'interp_days': interp_days,
            'interp_method': interp_method,
            'model_name': openet.ssebop.MODEL_NAME,
            'model_version': openet.ssebop.__version__,
        }
        interp_properties.update(self.model_args)

        def aggregate_image(agg_start_date, agg_end_date, date_format):
            """Aggregate the daily images within the target date range

            Parameters
            ----------
            agg_start_date: str
                Start date (inclusive).
            agg_end_date : str
                End date (exclusive).
            date_format : str
                Date format for system:index (uses EE JODA format).

            Returns
            -------
            ee.Image

            Notes
            -----
            Since this function takes multiple inputs it is being called
            for each time interval by separate mappable functions

            """
            if 'et' in variables or 'et_fraction' in variables:
                et_img = daily_coll.filterDate(agg_start_date, agg_end_date) \
                    .select(['et']).sum()
            if 'et_reference' in variables or 'et_fraction' in variables:
                # et_reference_img = daily_et_ref_coll \
                et_reference_img = daily_coll \
                    .filterDate(agg_start_date, agg_end_date) \
                    .select(['et_reference']).sum()

            image_list = []
            if 'et' in variables:
                image_list.append(et_img.float())
            if 'et_reference' in variables:
                image_list.append(et_reference_img.float())
            if 'et_fraction' in variables:
                # Compute average et fraction over the aggregation period
                image_list.append(
                    et_img.divide(et_reference_img).rename(['et_fraction']).float())
            if 'ndvi' in variables:
                # Compute average ndvi over the aggregation period
                ndvi_img = daily_coll \
                    .filterDate(agg_start_date, agg_end_date) \
                    .mean().select(['ndvi']).float()
                image_list.append(ndvi_img)
            if 'count' in variables:
                count_img = aggregate_coll \
                    .filterDate(agg_start_date, agg_end_date) \
                    .select(['mask']).count().rename('count').uint8()
                image_list.append(count_img)

            return ee.Image(image_list) \
                .set(interp_properties) \
                .set({
                    'system:index': ee.Date(agg_start_date).format(date_format),
                    'system:time_start': ee.Date(agg_start_date).millis(),
                })

        # Combine input, interpolated, and derived values
        if t_interval.lower() == 'daily':
            def aggregate_daily(daily_img):
                # CGM - Double check that this time_start is a 0 UTC time.
                # It should be since it is coming from the interpolate source
                #   collection, but what if source is GRIDMET (+6 UTC)?
                agg_start_date = ee.Date(daily_img.get('system:time_start'))
                # CGM - This calls .sum() on collections with only one image
                return aggregate_image(
                    agg_start_date=agg_start_date,
                    agg_end_date=ee.Date(agg_start_date).advance(1, 'day'),
                    date_format='YYYYMMdd')

            return ee.ImageCollection(daily_coll.map(aggregate_daily))

        elif t_interval.lower() == 'monthly':
            def month_gen(iter_start_dt, iter_end_dt):
                iter_dt = iter_start_dt
                # Conditional is "less than" because end date is exclusive
                while iter_dt < iter_end_dt:
                    yield iter_dt.strftime('%Y-%m-%d')
                    iter_dt += relativedelta(months=+1)
            month_list = ee.List(list(month_gen(start_dt, end_dt)))

            def aggregate_monthly(agg_start_date):
                return aggregate_image(
                    agg_start_date=agg_start_date,
                    agg_end_date=ee.Date(agg_start_date).advance(1, 'month'),
                    date_format='YYYYMM')

            return ee.ImageCollection(month_list.map(aggregate_monthly))

        elif t_interval.lower() == 'annual':
            def year_gen(iter_start_dt, iter_end_dt):
                iter_dt = iter_start_dt
                while iter_dt < iter_end_dt:
                    yield iter_dt.strftime('%Y-%m-%d')
                    iter_dt += relativedelta(years=+1)
            year_list = ee.List(list(year_gen(start_dt, end_dt)))

            def aggregate_annual(agg_start_date):
                return aggregate_image(
                    agg_start_date=agg_start_date,
                    agg_end_date=ee.Date(agg_start_date).advance(1, 'year'),
                    date_format='YYYY')

            return ee.ImageCollection(year_list.map(aggregate_annual))

        elif t_interval.lower() == 'custom':
            # Returning an ImageCollection to be consistent
            return ee.ImageCollection(aggregate_image(
                agg_start_date=start_date, agg_end_date=end_date,
                date_format='YYYYMMdd'))

    def get_image_ids(self):
        """Return image IDs of the input images

        Returns
        -------
        list

        Notes
        -----
        This image list is based on the collection start and end dates and may
        not include all of the images used for interpolation.

        """
        return sorted(list(self._build(variables=['ndvi'])\
            .aggregate_array('image_id').getInfo()))
