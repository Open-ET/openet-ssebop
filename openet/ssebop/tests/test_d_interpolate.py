import pprint

import ee
import pytest

import openet.ssebop.interpolate as interpolate
import openet.ssebop.utils as utils


def scene_coll(variables, et_fraction=0.4, et=5, ndvi=0.6):
    """Return a generic scene collection to test scene interpolation functions

    Parameters
    ----------
    variables : list
        The variables to return in the collection
    et_fraction : float
    et : float
    ndvi : float

    Returns
    -------
    ee.ImageCollection

    """
    img = ee.Image('LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716') \
        .select(['B2']).double().multiply(0)
    mask = img.add(1).updateMask(1).uint8()

    time1 = ee.Number(ee.Date.fromYMD(2017, 7, 8).millis())
    time2 = ee.Number(ee.Date.fromYMD(2017, 7, 16).millis())
    time3 = ee.Number(ee.Date.fromYMD(2017, 7, 24).millis())

    # Mask and time bands currently get added on to the scene collection
    #   and images are unscaled just before interpolating in the export tool
    scene_img = ee.Image([img.add(et_fraction), img.add(et), img.add(ndvi), mask])\
        .rename(['et_fraction', 'et', 'ndvi', 'mask'])
    # CGM - I was having issues when I removed these backslashes,
    #   even though they shouldn't be needed
    scene_coll = ee.ImageCollection([
        scene_img.addBands([img.add(time1).rename('time')]) \
            .set({'system:index': 'LE07_044033_20170708',
                  'system:time_start': time1}),
        scene_img.addBands([img.add(time2).rename('time')]) \
            .set({'system:index': 'LC08_044033_20170716',
                  'system:time_start': time2}),
        scene_img.addBands([img.add(time3).rename('time')]) \
            .set({'system:index': 'LE07_044033_20170724',
                  'system:time_start': time3}),
    ])
    return scene_coll.select(variables)


def test_from_scene_et_fraction_t_interval_daily_values(tol=0.0001):
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi', 'time', 'mask']),
        start_date='2017-07-01', end_date='2017-08-01',
        variables=['et', 'et_reference', 'et_fraction', 'ndvi'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_factor': 1.0,
                    'et_reference_resample': 'nearest'},
        t_interval='daily')

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=10)
    assert abs(output['ndvi']['2017-07-10'] - 0.6) <= tol
    assert abs(output['et_fraction']['2017-07-10'] - 0.4) <= tol
    assert abs(output['et_reference']['2017-07-10'] - 10.5) <= tol
    assert abs(output['et']['2017-07-10'] - (10.5 * 0.4)) <= tol
    # assert abs(output['et_reference']['2017-07-10'] - 10.508799553) <= tol
    # assert abs(output['et']['2017-07-10'] - (10.508799553 * 0.4)) <= tol
    assert abs(output['et_fraction']['2017-07-01'] - 0.4) <= tol
    assert abs(output['et_fraction']['2017-07-31'] - 0.4) <= tol
    assert '2017-08-01' not in output['et_fraction'].keys()
    # assert output['count']['2017-07-01'] == 3


def test_from_scene_et_fraction_t_interval_monthly_values(tol=0.0001):
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi', 'time', 'mask']),
        start_date='2017-07-01', end_date='2017-08-01',
        variables=['et', 'et_reference', 'et_fraction', 'ndvi', 'count'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_factor': 1.0,
                    'et_reference_resample': 'nearest'},
        t_interval='monthly')

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=10)
    assert abs(output['ndvi']['2017-07-01'] - 0.6) <= tol
    assert abs(output['et_fraction']['2017-07-01'] - 0.4) <= tol
    assert abs(output['et_reference']['2017-07-01'] - 310.3) <= tol
    assert abs(output['et']['2017-07-01'] - (310.3 * 0.4)) <= tol
    # assert abs(output['et_reference']['2017-07-01'] - 303.622559) <= tol
    # assert abs(output['et']['2017-07-01'] - (303.622559 * 0.4)) <= tol
    assert output['count']['2017-07-01'] == 3


def test_from_scene_et_fraction_t_interval_custom_values(tol=0.0001):
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi', 'time', 'mask']),
        start_date='2017-07-01', end_date='2017-08-01',
        variables=['et', 'et_reference', 'et_fraction', 'ndvi', 'count'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_factor': 1.0,
                    'et_reference_resample': 'nearest'},
        t_interval='custom')

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=10)
    assert abs(output['ndvi']['2017-07-01'] - 0.6) <= tol
    assert abs(output['et_fraction']['2017-07-01'] - 0.4) <= tol
    assert abs(output['et_reference']['2017-07-01'] - 310.3) <= tol
    assert abs(output['et']['2017-07-01'] - (310.3 * 0.4)) <= tol
    # assert abs(output['et_reference']['2017-07-01'] - 303.622559) <= tol
    # assert abs(output['et']['2017-07-01'] - (303.622559 * 0.4)) <= tol
    assert output['count']['2017-07-01'] == 3


def test_from_scene_et_fraction_t_interval_monthly_et_reference_factor(tol=0.0001):
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi', 'time', 'mask']),
        start_date='2017-07-01', end_date='2017-08-01',
        variables=['et', 'et_reference', 'et_fraction', 'ndvi', 'count'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_factor': 0.5,
                    'et_reference_resample': 'nearest'},
        t_interval='monthly')

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=10)
    assert abs(output['ndvi']['2017-07-01'] - 0.6) <= tol
    assert abs(output['et_fraction']['2017-07-01'] - 0.4) <= tol
    assert abs(output['et_reference']['2017-07-01'] - 310.3 * 0.5) <= tol
    assert abs(output['et']['2017-07-01'] - (310.3 * 0.5 * 0.4)) <= tol
    # assert abs(output['et_reference']['2017-07-01'] - 303.622559 * 0.5) <= tol
    # assert abs(output['et']['2017-07-01'] - (303.622559 * 0.5 * 0.4)) <= tol
    assert output['count']['2017-07-01'] == 3


# CGM - Resampling is not being applied so this should be equal to nearest
def test_from_scene_et_fraction_t_interval_monthly_et_reference_resample(tol=0.0001):
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi', 'time', 'mask']),
        start_date='2017-07-01', end_date='2017-08-01',
        variables=['et', 'et_reference', 'et_fraction', 'ndvi', 'count'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_factor': 1.0,
                    'et_reference_resample': 'bilinear'},
        t_interval='monthly')

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=10)
    assert abs(output['ndvi']['2017-07-01'] - 0.6) <= tol
    assert abs(output['et_fraction']['2017-07-01'] - 0.4) <= tol
    assert abs(output['et_reference']['2017-07-01'] - 310.3) <= tol
    assert abs(output['et']['2017-07-01'] - (310.3 * 0.4)) <= tol
    # assert abs(output['et_reference']['2017-07-01'] - 303.622559) <= tol
    # assert abs(output['et']['2017-07-01'] - (303.622559 * 0.4)) <= tol
    assert output['count']['2017-07-01'] == 3


def test_from_scene_et_fraction_t_interval_monthly_et_reference_date_type_doy(tol=0.01):
    # Check that et_reference_date_type 'doy' parameter works with a reference ET climatology
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi', 'time', 'mask']),
        start_date='2017-07-01', end_date='2017-08-01',
        variables=['et_reference'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'projects/usgs-ssebop/pet/gridmet_median_v1',
                    'et_reference_band': 'etr',
                    'et_reference_factor': 1.0,
                    'et_reference_resample': 'nearest',
                    'et_reference_date_type': 'doy'},
        t_interval='monthly')

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=10)
    assert abs(output['et_reference']['2017-07-01'] - 291.56) <= tol


def test_from_scene_et_fraction_t_interval_monthly_et_reference_date_type_daily(tol=0.01):
    # Check that et_reference_date_type 'doy' parameter works with a reference ET climatology
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi', 'time', 'mask']),
        start_date='2017-07-01', end_date='2017-08-01',
        variables=['et_reference'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_factor': 1.0,
                    'et_reference_resample': 'nearest',
                    'et_reference_date_type': 'daily'},
        t_interval='monthly')

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=10)
    assert abs(output['et_reference']['2017-07-01'] - 310.3) <= tol


def test_from_scene_et_fraction_t_interval_bad_value():
    # Function should raise a ValueError if t_interval is not supported
    with pytest.raises(ValueError):
        interpolate.from_scene_et_fraction(
            scene_coll(['et', 'time', 'mask']),
            start_date='2017-07-01', end_date='2017-08-01', variables=['et'],
            interp_args={'interp_method': 'linear', 'interp_days': 32},
            model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                        'et_reference_band': 'etr',
                        'et_reference_factor': 0.5,
                        'et_reference_resample': 'nearest'},
            t_interval='deadbeef')


def test_from_scene_et_fraction_t_interval_no_value():
    # Function should raise an Exception if t_interval is not set
    with pytest.raises(TypeError):
        interpolate.from_scene_et_fraction(
            scene_coll(['et', 'time', 'mask']),
            start_date='2017-07-01', end_date='2017-08-01',
            variables=['et', 'et_reference', 'et_fraction', 'count'],
            interp_args={'interp_method': 'linear', 'interp_days': 32},
            model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                        'et_reference_band': 'etr',
                        'et_reference_factor': 0.5,
                        'et_reference_resample': 'nearest'})


def test_from_scene_et_fraction_interp_args_use_joins_true(tol=0.01):
    # Check that the use_joins interp_args parameter works
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'time', 'mask']),
        start_date='2017-07-01', end_date='2017-08-01',
        variables=['et', 'et_reference'],
        interp_args={'interp_method': 'linear', 'interp_days': 32, 'use_joins': True},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_factor': 1.0,
                    'et_reference_resample': 'nearest'},
        t_interval='monthly')

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=10)
    assert abs(output['et_reference']['2017-07-01'] - 310.3) <= tol
    assert abs(output['et']['2017-07-01'] - (310.3 * 0.4)) <= tol


def test_from_scene_et_fraction_interp_args_use_joins_false(tol=0.01):
    # Check that the use_joins interp_args parameter works
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'time', 'mask']),
        start_date='2017-07-01', end_date='2017-08-01',
        variables=['et', 'et_reference'],
        interp_args={'interp_method': 'linear', 'interp_days': 32, 'use_joins': False},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_factor': 1.0,
                    'et_reference_resample': 'nearest'},
        t_interval='monthly')

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=10)
    assert abs(output['et_reference']['2017-07-01'] - 310.3) <= tol
    assert abs(output['et']['2017-07-01'] - (310.3 * 0.4)) <= tol
