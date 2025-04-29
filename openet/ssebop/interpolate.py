from datetime import datetime, timedelta
import logging

from dateutil.relativedelta import relativedelta
import ee
import openet.core.interpolate
# TODO: import utils from openet.core
# import openet.core.utils as utils

from . import utils

RESAMPLE_METHODS = ['nearest', 'bilinear', 'bicubic']

def from_scene_et_fraction(
        scene_coll,
        start_date,
        end_date,
        variables,
        interp_args,
        model_args,
        t_interval,
        _interp_vars=['et_fraction', 'ndvi'],
):
    """Interpolate from a precomputed collection of Landsat ET fraction scenes

    Parameters
    ----------
    scene_coll : ee.ImageCollection
        Non-daily 'et_fraction' images that will be interpolated.
    start_date : str
        ISO format start date.
    end_date : str
        ISO format end date (exclusive, passed directly to .filterDate()).
    variables : list
        List of variables that will be returned in the Image Collection.
    interp_args : dict
        Parameters from the INTERPOLATE section of the INI file.
        # TODO: Look into a better format for showing the options
        interp_method : {'linear}, optional
            Interpolation method.  The default is 'linear'.
        interp_days : int, str, optional
            Number of extra days before the start date and after the end date
            to include in the interpolation calculation. The default is 32.
        et_reference_source : str
            Reference ET collection ID.
        et_reference_band : str
            Reference ET band name.
        et_reference_factor : float, None, optional
            Reference ET scaling factor.  The default is 1.0 which is
            equivalent to no scaling.
        et_reference_resample : {'nearest', 'bilinear', 'bicubic', None}, optional
            Reference ET resampling.  The default is 'nearest'.
        mask_partial_aggregations : bool, optional
            If True, pixels with an aggregation count less than the number of
            days in the aggregation time period will be masked.  The default is True.
        use_joins : bool, optional
            If True, use joins to link the target and source collections.
            If False, the source collection will be filtered for each target image.
            This parameter is passed through to interpolate.daily().
    model_args : dict
        Parameters from the MODEL section of the INI file.
    t_interval : {'daily', 'monthly', 'custom'}
        Time interval over which to interpolate and aggregate values
        The 'custom' interval will aggregate all days within the start and end
        dates into an image collection with a single image.
    _interp_vars : list, optional
        The variables that can be interpolated to daily timesteps.
        The default is to interpolate the 'et_fraction' and 'ndvi' bands.

    Returns
    -------
    ee.ImageCollection

    Raises
    ------
    ValueError

    Notes
    -----
    This function assumes that "mask" and "time" bands are not in the scene collection.

    """
    # Get interp_method
    if 'interp_method' in interp_args.keys():
        interp_method = interp_args['interp_method']
    else:
        interp_method = 'linear'
        logging.debug('interp_method was not set in interp_args, default to "linear"')

    # Get interp_days
    if 'interp_days' in interp_args.keys():
        interp_days = interp_args['interp_days']
    else:
        interp_days = 32
        logging.debug('interp_days was not set in interp_args, default to 32')

    # Get mask_partial_aggregations
    if 'mask_partial_aggregations' in interp_args.keys():
        mask_partial_aggregations = interp_args['mask_partial_aggregations']
    else:
        mask_partial_aggregations = True
        logging.debug('mask_partial_aggregations was not set in interp_args, default to True')

    # Get use_joins
    if 'use_joins' in interp_args.keys():
        use_joins = interp_args['use_joins']
    else:
        use_joins = True
        logging.debug('use_joins was not set in interp_args, default to True')

    # Check that the input parameters are valid
    if t_interval.lower() not in ['daily', 'monthly', 'custom']:
        raise ValueError(f'unsupported t_interval: {t_interval}')
    elif interp_method.lower() not in ['linear']:
        raise ValueError(f'unsupported interp_method: {interp_method}')

    if (((type(interp_days) is str) or (type(interp_days) is float)) and
            utils.is_number(interp_days)):
        interp_days = int(interp_days)
    elif not type(interp_days) is int:
        raise TypeError('interp_days must be an integer')
    elif interp_days <= 0:
        raise ValueError('interp_days must be a positive integer')

    if not variables:
        raise ValueError('variables parameter must be set')

    # Adjust start/end dates based on t_interval
    # Increase the date range to fully include the time interval
    start_dt = datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = datetime.strptime(end_date, '%Y-%m-%d')
    if t_interval.lower() == 'monthly':
        start_dt = datetime(start_dt.year, start_dt.month, 1)
        end_dt -= relativedelta(days=+1)
        end_dt = datetime(end_dt.year, end_dt.month, 1)
        end_dt += relativedelta(months=+1)
    start_date = start_dt.strftime('%Y-%m-%d')
    end_date = end_dt.strftime('%Y-%m-%d')

    # The start/end date for the interpolation include more days
    # (+/- interp_days) than are included in the ETr collection
    interp_start_dt = start_dt - timedelta(days=interp_days)
    interp_end_dt = end_dt + timedelta(days=interp_days)
    interp_start_date = interp_start_dt.date().isoformat()
    interp_end_date = interp_end_dt.date().isoformat()

    # Get reference ET parameters
    # Supporting reading the parameters from both the interp_args and model_args dictionaries
    # Check interp_args then model_args, and eventually drop support for reading from model_args
    # Assume that if source and band are present, factor and resample should also be read
    if ('et_reference_source' in interp_args.keys()) and ('et_reference_band' in interp_args.keys()):
        et_reference_source = interp_args['et_reference_source']
        et_reference_band = interp_args['et_reference_band']
        if not et_reference_source or not et_reference_band:
            raise ValueError('et_reference_source or et_reference_band were not set')

        if 'et_reference_factor' in interp_args.keys():
            et_reference_factor = interp_args['et_reference_factor']
        else:
            et_reference_factor = 1.0
            logging.debug('et_reference_factor was not set, default to 1.0')

        if 'et_reference_resample' in interp_args.keys():
            et_reference_resample = interp_args['et_reference_resample'].lower()
            if not et_reference_resample:
                et_reference_resample = 'nearest'
                logging.debug('et_reference_resample was not set, default to nearest')
            elif et_reference_resample not in RESAMPLE_METHODS:
                raise ValueError(f'unsupported et_reference_resample method: '
                                 f'{et_reference_resample}')
        else:
            et_reference_resample = 'nearest'
            logging.debug('et_reference_resample was not set, default to nearest')

    elif ('et_reference_source' in model_args.keys()) and ('et_reference_band' in model_args.keys()):
        et_reference_source = model_args['et_reference_source']
        et_reference_band = model_args['et_reference_band']
        if not et_reference_source or not et_reference_band:
            raise ValueError('et_reference_source or et_reference_band were not set')

        if 'et_reference_factor' in model_args.keys():
            et_reference_factor = model_args['et_reference_factor']
        else:
            et_reference_factor = 1.0
            logging.debug('et_reference_factor was not set, default to 1.0')

        if 'et_reference_resample' in model_args.keys():
            et_reference_resample = model_args['et_reference_resample'].lower()
            if not et_reference_resample:
                et_reference_resample = 'nearest'
                logging.debug('et_reference_resample was not set, default to nearest')
            elif et_reference_resample not in RESAMPLE_METHODS:
                raise ValueError(f'unsupported et_reference_resample method: '
                                 f'{et_reference_resample}')
        else:
            et_reference_resample = 'nearest'
            logging.debug('et_reference_resample was not set, default to nearest')

    else:
        raise ValueError('et_reference_source or et_reference_band were not set')


    if 'et_reference_date_type' in model_args.keys():
        et_reference_date_type = model_args['et_reference_date_type']
    else:
        et_reference_date_type = None
        # logging.debug('et_reference_date_type was not set, default to "daily"')
        # et_reference_date_type = 'daily'


    if type(et_reference_source) is str:
        # Assume a string source is a single image collection ID
        #   not a list of collection IDs or ee.ImageCollection
        if (et_reference_date_type is None) or (et_reference_date_type.lower() == 'daily'):
            daily_et_ref_coll = (
                ee.ImageCollection(et_reference_source)
                .filterDate(start_date, end_date)
                .select([et_reference_band], ['et_reference'])
            )
        elif et_reference_date_type.lower() == 'doy':
            # Assume the image collection is a climatology with a "DOY" property
            def doy_image(input_img):
                """Return the doy-based reference et with daily time properties from GRIDMET"""
                image_date = ee.Algorithms.Date(input_img.get('system:time_start'))
                image_doy = ee.Number(image_date.getRelative('day', 'year')).add(1).int()
                doy_coll = (
                    ee.ImageCollection(et_reference_source)
                    .filterMetadata('DOY', 'equals', image_doy)
                    .select([et_reference_band], ['et_reference'])
                )
                # CGM - Was there a reason to use rangeContains if limiting to one DOY?
                #     .filter(ee.Filter.rangeContains('DOY', doy, doy))\
                return (
                    ee.Image(doy_coll.first())
                    .set({'system:index': input_img.get('system:index'),
                          'system:time_start': input_img.get('system:time_start')})
                )
            # Note, the collection and band that are used are not important as
            #   long as they are daily and available for the time period
            daily_et_ref_coll = (
                ee.ImageCollection('IDAHO_EPSCOR/GRIDMET')
                .filterDate(start_date, end_date)
                .select(['eto'])
                .map(doy_image)
            )
        else:
            raise ValueError(f'unsupported et_reference_date_type: {et_reference_date_type}')
    # elif isinstance(et_reference_source, computedobject.ComputedObject):
    #     # Interpret computed objects as image collections
    #     daily_et_ref_coll = (
    #         et_reference_source
    #         .filterDate(start_date, end_date)
    #         .select([et_reference_band], ['et_reference'])
    #     )
    else:
        raise ValueError(f'unsupported et_reference_source: {et_reference_source}')

    # Scale reference ET images (if necessary)
    if et_reference_factor and (et_reference_factor != 1):
        def et_reference_adjust(input_img):
            return (
                input_img.multiply(et_reference_factor)
                .copyProperties(input_img)
                .set({'system:time_start': input_img.get('system:time_start')})
            )
        daily_et_ref_coll = daily_et_ref_coll.map(et_reference_adjust)

    # Initialize variable list to only variables that can be interpolated
    interp_vars = list(set(_interp_vars) & set(variables))

    # To return ET, the ETf must be interpolated
    if ('et' in variables) and ('et_fraction' not in interp_vars):
        interp_vars = interp_vars + ['et_fraction']

    # With the current interpolate.daily() function,
    #   something has to be interpolated in order to return et_reference
    if ('et_reference' in variables) and ('et_fraction' not in interp_vars):
        interp_vars = interp_vars + ['et_fraction']

    # To compute the daily count, the ETf must be interpolated
    # We may want to add support for computing daily_count when interpolating NDVI
    if ('daily_count' in variables) and ('et_fraction' not in interp_vars):
        interp_vars = interp_vars + ['et_fraction']

    # TODO: Look into implementing et_fraction clamping here
    #   (similar to et_actual below)

    def interpolate_prep(img):
        """Prep WRS2 scene images for interpolation

        "Unscale" the images using the "scale_factor_et_fraction" property
            and convert to double.
        Add a mask and time band to each image in the scene_coll since
            interpolator is assuming time and mask bands exist.
        The interpolation could be modified to get the mask from the
            time band instead of setting it here.
        The time image must be the 0 UTC time

        """
        mask_img = (
            img.select(['et_fraction']).multiply(0).add(1).updateMask(1).uint8().rename(['mask'])
        )
        time_img = (
            img.select(['et_fraction']).double().multiply(0)
            .add(utils.date_0utc(ee.Date(img.get('system:time_start'))).millis())
            .rename(['time'])
        )

        # Set the default scale factor to 1 if the image does not have the property
        scale_factor = (
            ee.Dictionary({'scale_factor': img.get('scale_factor_et_fraction')})
            .combine({'scale_factor': 1.0}, overwrite=False)
        )

        return (
            img.select(interp_vars)
            .double().multiply(ee.Number(scale_factor.get('scale_factor')))
            .addBands([mask_img, time_img])
            .set({
                'system:time_start': ee.Number(img.get('system:time_start')),
                'system:index': ee.String(img.get('system:index')),
            })
        )

    # Filter scene collection to the interpolation range
    #   This probably isn't needed since scene_coll was built to this range
    # Then add the time and mask bands needed for interpolation
    scene_coll = ee.ImageCollection(
        scene_coll.filterDate(interp_start_date, interp_end_date)
        .map(interpolate_prep)
    )

    # For scene count, compute the composite/mosaic image for the mask band only
    if ('scene_count' in variables) or ('count' in variables):
        aggregate_coll = openet.core.interpolate.aggregate_to_daily(
            image_coll=scene_coll.select(['mask']),
            start_date=start_date,
            end_date=end_date,
        )

        # The following is needed because the aggregate collection can be
        #   empty if there are no scenes in the target date range but there
        #   are scenes in the interpolation date range.
        # Without this the count image will not be built but the other
        #   bands will be which causes a non-homogeneous image collection.
        aggregate_coll = aggregate_coll.merge(
            ee.Image.constant(0).rename(['mask'])
            .set({'system:time_start': ee.Date(start_date).millis()})
        )

    # Interpolate to a daily time step
    # The time band is needed for interpolation
    daily_coll = openet.core.interpolate.daily(
        target_coll=daily_et_ref_coll,
        source_coll=scene_coll.select(interp_vars + ['time']),
        interp_method=interp_method,
        interp_days=interp_days,
        use_joins=use_joins,
        compute_product=False,
    )

    # The interpolate.daily() function can/will return the product of
    # the source and target image named as "{source_band}_1".
    # The problem with this approach is that it will drop any other bands
    # that are being interpolated (such as the ndvi).
    # daily_coll = daily_coll.select(['et_fraction_1'], ['et'])

    # Compute ET from ETf and ETr (if necessary)
    # This isn't needed if compute_product=True in daily() and band is renamed
    # The check for et_fraction is needed since it is back computed from ET and ETr
    # if 'et' in variables or 'et_fraction' in variables:
    def compute_et(img):
        """This function assumes ETf and ETr bands are present in the image"""
        # Apply any resampling to the reference ET image before computing ET
        et_reference_img = img.select(['et_reference'])
        if et_reference_resample and (et_reference_resample in ['bilinear', 'bicubic']):
            et_reference_img = et_reference_img.resample(et_reference_resample)

        et_img = img.select(['et_fraction']).multiply(et_reference_img)

        return img.addBands(et_img.double().rename('et'))

    daily_coll = daily_coll.map(compute_et)

    # This function is being declared here to avoid passing in all the common parameters
    #   such as: daily_coll, daily_et_ref_coll, interp_properties, variables, etc.
    # Long term it should probably be declared outside of this function
    #   so it can be called directly and tested separately, or read from openet-core
    def aggregate_image(agg_start_date, agg_end_date, date_format):
        """Aggregate the daily images within the target date range

        Parameters
        ----------
        agg_start_date: ee.Date, str
            Start date (inclusive).
        agg_end_date : ee.Date, str
            End date (exclusive).
        date_format : str
            Date format for system:index (uses EE JODA format).

        Returns
        -------
        ee.Image

        """
        et_img = None
        eto_img = None

        if ('et' in variables) or ('et_fraction' in variables):
            et_img = daily_coll.filterDate(agg_start_date, agg_end_date).select(['et']).sum()

        if ('et_reference' in variables) or ('et_fraction' in variables):
            eto_img = (
                daily_et_ref_coll.filterDate(agg_start_date, agg_end_date)
                .select(['et_reference']).sum()
            )
            if et_reference_resample and (et_reference_resample in ['bilinear', 'bicubic']):
                eto_img = (
                    eto_img.setDefaultProjection(daily_et_ref_coll.first().projection())
                    .resample(et_reference_resample)
                )

        # Count the number of interpolated/aggregated values
        # Mask pixels that do not have a full aggregation count for the start/end
        # Use "et" band so that count is a function of ET and reference ET
        if ('et' in variables) or ('et_fraction' in variables) or ('et_reference' in variables):
            aggregation_band = 'et'
        elif 'ndvi' in variables:
            aggregation_band = 'ndvi'
        else:
            raise ValueError('no supported aggregation band')
        aggregation_count_img = (
            daily_coll.filterDate(agg_start_date, agg_end_date)
            .select([aggregation_band]).reduce(ee.Reducer.count())
        )

        image_list = []
        if 'et' in variables:
            image_list.append(et_img.float())
        if 'et_reference' in variables:
            image_list.append(eto_img.float())
        if 'et_fraction' in variables:
            # Compute average et fraction over the aggregation period
            image_list.append(et_img.divide(eto_img).rename(['et_fraction']).float())
        if 'ndvi' in variables:
            # Compute average NDVI over the aggregation period
            ndvi_img = (
                daily_coll.filterDate(agg_start_date, agg_end_date)
                .select(['ndvi']).mean().float()
            )
            image_list.append(ndvi_img)
        if ('scene_count' in variables) or ('count' in variables):
            scene_count_img = (
                aggregate_coll.filterDate(agg_start_date, agg_end_date)
                .select(['mask']).reduce(ee.Reducer.sum()).rename('count')
                .uint8()
            )
            image_list.append(scene_count_img)
        if 'daily_count' in variables:
            image_list.append(aggregation_count_img.rename('daily_count').uint8())

        output_img = ee.Image(image_list)

        if mask_partial_aggregations:
            aggregation_days = ee.Date(agg_end_date).difference(ee.Date(agg_start_date), 'day')
            aggregation_count_mask = aggregation_count_img.gte(aggregation_days.subtract(1))
            output_img = output_img.updateMask(aggregation_count_mask)

        return (
            output_img
            .set({
                'system:index': ee.Date(agg_start_date).format(date_format),
                'system:time_start': ee.Date(agg_start_date).millis(),
            })
        )

    # Combine input, interpolated, and derived values
    if t_interval.lower() == 'custom':
        # Return an ImageCollection to be consistent with the other t_interval options
        return ee.ImageCollection(aggregate_image(
            agg_start_date=start_date,
            agg_end_date=end_date,
            date_format='YYYYMMdd',
        ))
    elif t_interval.lower() == 'daily':
        def agg_daily(daily_img):
            # CGM - Double check that this time_start is a 0 UTC time.
            # It should be since it is coming from the interpolate source
            #   collection, but what if source is GRIDMET (+6 UTC)?
            agg_start_date = ee.Date(daily_img.get('system:time_start'))
            # This calls .sum() on collections with only one image
            return aggregate_image(
                agg_start_date=agg_start_date,
                agg_end_date=ee.Date(agg_start_date).advance(1, 'day'),
                date_format='YYYYMMdd',
            )
        return ee.ImageCollection(daily_coll.map(agg_daily))
    elif t_interval.lower() == 'monthly':
        def month_gen(iter_start_dt, iter_end_dt):
            iter_dt = iter_start_dt
            # Conditional is "less than" because end date is exclusive
            while iter_dt < iter_end_dt:
                yield iter_dt.strftime('%Y-%m-%d')
                iter_dt += relativedelta(months=+1)
        def agg_monthly(agg_start_date):
            return aggregate_image(
                agg_start_date=agg_start_date,
                agg_end_date=ee.Date(agg_start_date).advance(1, 'month'),
                date_format='YYYYMM',
            )
        return ee.ImageCollection(ee.List(list(month_gen(start_dt, end_dt))).map(agg_monthly))
    else:
        raise ValueError(f'unsupported t_interval: {t_interval}')
