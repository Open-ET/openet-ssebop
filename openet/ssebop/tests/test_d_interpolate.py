import pprint

import ee
import pytest

import openet.ssebop.interpolate as interpolate
import openet.ssebop.utils as utils


def test_from_scene_et_fraction_values():
    img = ee.Image('LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716') \
        .select(['B2']).double().multiply(0)
    mask = img.add(1).updateMask(1).uint8()

    time1 = ee.Number(ee.Date.fromYMD(2017, 7, 8).millis())
    time2 = ee.Number(ee.Date.fromYMD(2017, 7, 16).millis())
    time3 = ee.Number(ee.Date.fromYMD(2017, 7, 24).millis())

    # Mask and time bands currently get added on to the scene collection
    #   and images are unscaled just before interpolating in the export tool
    band_names = ['et_fraction', 'ndvi', 'time', 'mask']
    scene_coll = ee.ImageCollection([
        ee.Image([img.add(0.4), img.add(0.5), img.add(time1), mask]) \
            .rename(band_names) \
            .set({'system:index': 'LE07_044033_20170708',
                  'system:time_start': time1}),
        ee.Image([img.add(0.4), img.add(0.5), img.add(time2), mask]) \
            .rename(band_names) \
            .set({'system:index': 'LC08_044033_20170716',
                  'system:time_start': time2}),
        ee.Image([img.add(0.4), img.add(0.5), img.add(time3), mask]) \
            .rename(band_names) \
            .set({'system:index': 'LE07_044033_20170724',
                  'system:time_start': time3}),
        ])

    etf_coll = interpolate.from_scene_et_fraction(
        scene_coll,
        start_date='2017-07-01', end_date='2017-07-31',
        variables=['et', 'et_reference', 'et_fraction', 'ndvi', 'count'],
        model_args={'et_reference_source': 'IDAHO_EPSCOR/GRIDMET',
                    'et_reference_band': 'etr',
                    'et_reference_factor': 1.0,
                    'et_reference_resample': 'nearest'},
        t_interval='monthly', interp_method='linear', interp_days=32)

    TEST_POINT = (-121.5265, 38.7399)
    output = utils.point_coll_value(etf_coll, TEST_POINT, scale=10)

    tol = 0.0001
    assert abs(output['ndvi']['2017-07-01'] - 0.5) <= tol
    assert abs(output['et_fraction']['2017-07-01'] - 0.4) <= tol
    assert abs(output['et_reference']['2017-07-01'] - 303.622559) <= tol
    assert abs(output['et']['2017-07-01'] - (303.622559 * 0.4)) <= tol
    assert output['count']['2017-07-01'] == 3
