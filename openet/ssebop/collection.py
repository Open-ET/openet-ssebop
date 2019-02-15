import datetime

import ee

from . import utils
from .image import Image
import openet.core.interp as interp
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


# TODO: Make this into a Collection class
def collection(
        variable,
        collections,
        start_date,
        end_date,
        t_interval,
        geometry,
        **kwargs
    ):
    """Earth Engine based SSEBop Image Collection

    Parameters
    ----------
    variable : str
        Variable to compute.
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
    kwargs : dict

    """

    # Should this be a global (or Collection class property)
    landsat_c1_toa_collections = [
        'LANDSAT/LC08/C01/T1_RT_TOA',
        'LANDSAT/LE07/C01/T1_RT_TOA',
        'LANDSAT/LC08/C01/T1_TOA',
        'LANDSAT/LE07/C01/T1_TOA',
        'LANDSAT/LT05/C01/T1_TOA',
    ]

    # Test whether the requested variable is supported
    # Force variable to be lowercase for now
    variable = variable.lower()
    if variable.lower() not in dir(Image):
        raise ValueError('unsupported variable: {}'.format(variable))
    if variable.lower() not in ['etf']:
        raise ValueError('unsupported variable: {}'.format(variable))

    # Build the variable image collection
    variable_coll = ee.ImageCollection([])
    for coll_id in collections:
        if coll_id in landsat_c1_toa_collections:
            def compute(image):
                model_obj = Image.from_landsat_c1_toa(
                    toa_image=ee.Image(image))
                return ee.Image(getattr(model_obj, variable))
        else:
            raise ValueError('unsupported collection: {}'.format(coll_id))

        var_coll = ee.ImageCollection(coll_id) \
            .filterDate(start_date, end_date) \
            .filterBounds(geometry) \
            .map(compute)

        # TODO: Apply additional filter parameters from kwargs
        #   (like CLOUD_COVER_LAND for Landsat)
        # .filterMetadata() \

        variable_coll = variable_coll.merge(var_coll)

    # Interpolate/aggregate to t_interval
    # TODO: Test whether the requested variable can/should be interpolated
    # TODO: Only load ET reference collection if interpolating ET
    # TODO: Get reference ET collection ID and band name from kwargs
    # TODO:   or accept an ee.ImageCollection directly
    # TODO: Get interp_days and interp_type from kwargs

    # Hardcoding to GRIDMET for now
    et_reference_coll = ee.ImageCollection('IDAHO_EPSCOR/GRIDMET')\
        .select(['etr'])\
        .filterDate(start_date, end_date)

    # Interpolate to a daily timestep
    # This function is currently setup to always multiply
    interp_coll = interp.daily(et_reference_coll, variable_coll,
                               interp_days=32, interp_method='linear')

    return interp_coll
