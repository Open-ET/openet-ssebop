# import pprint

import ee
import pytest

import openet.ssebop.interpolate as interpolate
import openet.ssebop.utils as utils


def scene_coll(variables, etf=[0.4, 0.4, 0.4], et=[5, 5, 5], ndvi=[0.6, 0.6, 0.6]):
    """Return a generic scene collection to test scene interpolation functions

    Parameters
    ----------
    variables : list
        The variables to return in the collection
    et_fraction : list
    et : list
    ndvi : list

    Returns
    -------
    ee.ImageCollection

    """
    img = (
        ee.Image('LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716')
        .select(['SR_B3']).double().multiply(0)
    )

    # The "time" is advanced to match the typical Landsat overpass time
    time1 = ee.Number(ee.Date.fromYMD(2017, 7, 8).advance(18, 'hours').millis())
    time2 = ee.Number(ee.Date.fromYMD(2017, 7, 16).advance(18, 'hours').millis())
    time3 = ee.Number(ee.Date.fromYMD(2017, 7, 24).advance(18, 'hours').millis())

    # TODO: Add code to convert et, et_fraction, and ndvi to lists if they
    #   are set as a single value

    # Don't add mask or time band to scene collection
    # since they are now added in the interpolation calls
    scene_coll = ee.ImageCollection.fromImages([
        ee.Image([img.add(etf[0]), img.add(et[0]), img.add(ndvi[0])])
            .rename(['et_fraction', 'et', 'ndvi'])
            .set({'system:index': 'LE07_044033_20170708', 'system:time_start': time1}),
        ee.Image([img.add(etf[1]), img.add(et[1]), img.add(ndvi[1])])
            .rename(['et_fraction', 'et', 'ndvi'])
            .set({'system:index': 'LC08_044033_20170716', 'system:time_start': time2}),
        ee.Image([img.add(etf[2]), img.add(et[2]), img.add(ndvi[2])])
            .rename(['et_fraction', 'et', 'ndvi'])
            .set({'system:index': 'LE07_044033_20170724', 'system:time_start': time3}),
    ])

    return scene_coll.select(variables)


def test_from_scene_et_fraction_t_interval_daily_values(tol=0.0001):
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi'], ndvi=[0.6, 0.6, 0.6]),
        start_date='2017-07-01',
        end_date='2017-08-01',
        variables=['et', 'et_reference', 'et_fraction', 'ndvi'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_resample': 'nearest'},
        t_interval='daily',
    )

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=30)
    assert abs(output['ndvi']['2017-07-10'] - 0.6) <= tol
    assert abs(output['et_fraction']['2017-07-10'] - 0.4) <= tol
    assert abs(output['et_reference']['2017-07-10'] - 10.5) <= tol
    assert abs(output['et']['2017-07-10'] - (10.5 * 0.4)) <= tol
    assert abs(output['et_fraction']['2017-07-01'] - 0.4) <= tol
    assert abs(output['et_fraction']['2017-07-31'] - 0.4) <= tol
    assert '2017-08-01' not in output['et_fraction'].keys()
    # assert output['count']['2017-07-01'] == 3


def test_from_scene_et_fraction_t_interval_monthly_values(tol=0.0001):
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi']),
        start_date='2017-07-01',
        end_date='2017-08-01',
        variables=['et', 'et_reference', 'et_fraction', 'ndvi', 'count'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_resample': 'nearest'},
        t_interval='monthly',
    )

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=30)
    assert abs(output['ndvi']['2017-07-01'] - 0.6) <= tol
    assert abs(output['et_fraction']['2017-07-01'] - 0.4) <= tol
    assert abs(output['et_reference']['2017-07-01'] - 310.3) <= tol
    assert abs(output['et']['2017-07-01'] - (310.3 * 0.4)) <= tol
    assert output['count']['2017-07-01'] == 3


def test_from_scene_et_fraction_t_interval_custom_values(tol=0.0001):
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi']),
        start_date='2017-07-01',
        end_date='2017-08-01',
        variables=['et', 'et_reference', 'et_fraction', 'ndvi', 'count'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_resample': 'nearest'},
        t_interval='custom',
    )

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=30)
    assert abs(output['ndvi']['2017-07-01'] - 0.6) <= tol
    assert abs(output['et_fraction']['2017-07-01'] - 0.4) <= tol
    assert abs(output['et_reference']['2017-07-01'] - 310.3) <= tol
    assert abs(output['et']['2017-07-01'] - (310.3 * 0.4)) <= tol
    assert output['count']['2017-07-01'] == 3


def test_from_scene_et_fraction_t_interval_custom_daily_count(tol=0.0001):
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi']),
        start_date='2017-07-01',
        end_date='2017-08-01',
        variables=['et_fraction', 'daily_count'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_resample': 'nearest'},
        t_interval='custom',
    )

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=30)
    assert abs(output['et_fraction']['2017-07-01'] - 0.4) <= tol
    assert output['daily_count']['2017-07-01'] == 31


def test_from_scene_et_fraction_t_interval_monthly_et_reference_factor(tol=0.0001):
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi']),
        start_date='2017-07-01',
        end_date='2017-08-01',
        variables=['et', 'et_reference', 'et_fraction', 'ndvi', 'count'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_factor': 0.5,
                    'et_reference_resample': 'nearest'},
        t_interval='monthly',
    )

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=30)
    assert abs(output['ndvi']['2017-07-01'] - 0.6) <= tol
    assert abs(output['et_fraction']['2017-07-01'] - 0.4) <= tol
    assert abs(output['et_reference']['2017-07-01'] - 310.3 * 0.5) <= tol
    assert abs(output['et']['2017-07-01'] - (310.3 * 0.5 * 0.4)) <= tol
    assert output['count']['2017-07-01'] == 3


def test_from_scene_et_fraction_t_interval_monthly_et_reference_resample(tol=0.0001):
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi']),
        start_date='2017-07-01',
        end_date='2017-08-01',
        variables=['et', 'et_reference', 'et_fraction', 'ndvi', 'count'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_resample': 'bilinear'},
        t_interval='monthly',
    )

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=30)
    assert abs(output['ndvi']['2017-07-01'] - 0.6) <= tol
    assert abs(output['et_fraction']['2017-07-01'] - 0.4) <= tol
    # CGM - ETo (and ET) test values are slightly different with bilinear resampling
    #   but ET fraction should be the same
    assert abs(output['et_reference']['2017-07-01'] - 309.4239807128906) <= tol
    assert abs(output['et']['2017-07-01'] - (309.4239807128906 * 0.4)) <= tol
    # assert abs(output['et_reference']['2017-07-01'] - 310.3) <= tol
    # assert abs(output['et']['2017-07-01'] - (310.3 * 0.4)) <= tol
    assert output['count']['2017-07-01'] == 3


def test_from_scene_et_fraction_t_interval_monthly_et_reference_date_type_doy(tol=0.01):
    # Check that et_reference_date_type 'doy' parameter works with a reference ET climatology
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi']),
        start_date='2017-07-01',
        end_date='2017-08-01',
        variables=['et_reference'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'projects/usgs-ssebop/pet/gridmet_median_v1',
                    'et_reference_band': 'etr',
                    'et_reference_resample': 'nearest',
                    'et_reference_date_type': 'doy'},
        t_interval='monthly',
    )

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=30)
    assert abs(output['et_reference']['2017-07-01'] - 291.56) <= tol


def test_from_scene_et_fraction_t_interval_monthly_et_reference_date_type_daily(tol=0.01):
    # Check that et_reference_date_type 'daily' parameter works with a reference ET collection
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction', 'ndvi']),
        start_date='2017-07-01',
        end_date='2017-08-01',
        variables=['et_reference'],
        interp_args={'interp_method': 'linear', 'interp_days': 32},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_resample': 'nearest',
                    'et_reference_date_type': 'daily'},
        t_interval='monthly',
    )

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=30)
    assert abs(output['et_reference']['2017-07-01'] - 310.3) <= tol


def test_from_scene_et_fraction_t_interval_bad_value():
    # Function should raise a ValueError if t_interval is not supported
    with pytest.raises(ValueError):
        interpolate.from_scene_et_fraction(
            scene_coll(['et']),
            start_date='2017-07-01',
            end_date='2017-08-01',
            variables=['et'],
            interp_args={'interp_method': 'linear', 'interp_days': 32},
            model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                        'et_reference_band': 'etr',
                        'et_reference_resample': 'nearest'},
            t_interval='deadbeef',
        )


def test_from_scene_et_fraction_t_interval_no_value():
    # Function should raise an Exception if t_interval is not set
    with pytest.raises(TypeError):
        interpolate.from_scene_et_fraction(
            scene_coll(['et']),
            start_date='2017-07-01',
            end_date='2017-08-01',
            variables=['et', 'et_reference', 'et_fraction', 'count'],
            interp_args={'interp_method': 'linear', 'interp_days': 32},
            model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                        'et_reference_band': 'etr',
                        'et_reference_resample': 'nearest'},
        )


def test_from_scene_et_fraction_interp_args_use_joins_true(tol=0.01):
    # Check that the use_joins interp_args parameter works
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction']),
        start_date='2017-07-01',
        end_date='2017-08-01',
        variables=['et', 'et_reference'],
        interp_args={'interp_method': 'linear', 'interp_days': 32, 'use_joins': True},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_resample': 'nearest'},
        t_interval='monthly',
    )

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=30)
    assert abs(output['et_reference']['2017-07-01'] - 310.3) <= tol
    assert abs(output['et']['2017-07-01'] - (310.3 * 0.4)) <= tol


def test_from_scene_et_fraction_interp_args_use_joins_false(tol=0.01):
    # Check that the use_joins interp_args parameter works
    output_coll = interpolate.from_scene_et_fraction(
        scene_coll(['et_fraction']),
        start_date='2017-07-01',
        end_date='2017-08-01',
        variables=['et', 'et_reference'],
        interp_args={'interp_method': 'linear', 'interp_days': 32, 'use_joins': False},
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_resample': 'nearest'},
        t_interval='monthly',
    )

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(output_coll, TEST_POINT, scale=30)
    assert abs(output['et_reference']['2017-07-01'] - 310.3) <= tol
    assert abs(output['et']['2017-07-01'] - (310.3 * 0.4)) <= tol
