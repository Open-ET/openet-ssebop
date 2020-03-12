import datetime
# import pprint

import ee
import pytest

import openet.ssebop.landsat as landsat
import openet.ssebop.utils as utils
# TODO: import utils from openet.core
# import openet.core.utils as utils


# Should these be test fixtures instead?
# I'm not sure how to make them fixtures and allow input parameters
def toa_image(red=0.1, nir=0.9, bt=305):
    """Construct a fake Landsat 8 TOA image with renamed bands"""
    return ee.Image.constant([red, nir, bt])\
        .rename(['red', 'nir', 'tir']) \
        .set({
            # 'system:time_start': ee.Date(SCENE_DATE).millis(),
            'k1_constant': ee.Number(607.76),
            'k2_constant': ee.Number(1260.56),
        })


def sr_image(red=1000, nir=9000, bt=305):
    """Construct a fake Landsat 8 TOA image with renamed bands"""
    return ee.Image.constant([red, nir, bt])\
        .rename(['red', 'nir', 'tir']) \
        .set({
            # 'system:time_start': ee.Date(SCENE_DATE).millis(),
            'k1_constant': ee.Number(607.76),
            'k2_constant': ee.Number(1260.56),
        })

@pytest.mark.parametrize(
    'red, nir, expected',
    [
        [0.2, 9.0 / 55, -0.1],
        [0.2, 0.2,  0.0],
        [0.1, 11.0 / 90,  0.1],
        [0.2, 0.3, 0.2],
        [0.1, 13.0 / 70, 0.3],
        [0.3, 0.7, 0.4],
        [0.2, 0.6, 0.5],
        [0.2, 0.8, 0.6],
        [0.1, 17.0 / 30, 0.7],
        [0.1, 0.9, 0.8],
    ]
)
def test_ndvi_calculation(red, nir, expected, tol=0.000001):
    toa = toa_image(red=red, nir=nir)
    output = utils.constant_image_value(landsat.ndvi(toa))
    assert abs(output['ndvi'] - expected) <= tol


def test_ndvi_band_name():
    output = utils.getinfo(landsat.ndvi(toa_image()))
    assert output['bands'][0]['id'] == 'ndvi'


@pytest.mark.parametrize(
    'red, nir, expected',
    [
        [0.2, 9.0 / 55, 0.985],      # -0.1
        [0.2, 0.2,  0.977],          # 0.0
        [0.1, 11.0 / 90,  0.977],    # 0.1
        [0.2, 0.2999, 0.977],        # 0.3- (0.3 NIR isn't exactly an NDVI of 0.2)
        [0.2, 0.3001, 0.986335],     # 0.3+
        [0.1, 13.0 / 70, 0.986742],  # 0.3
        [0.3, 0.7, 0.987964],        # 0.4
        [0.2, 0.6, 0.99],            # 0.5
        [0.2, 0.8, 0.99],            # 0.6
        [0.1, 17.0 / 30, 0.99],      # 0.7
    ]
)
def test_emissivity_calculation(red, nir, expected, tol=0.000001):
    output = utils.constant_image_value(
        landsat.emissivity(toa_image(red=red, nir=nir)))
    assert abs(output['emissivity'] - expected) <= tol


def test_emissivity_band_name():
    output = utils.getinfo(landsat.emissivity(toa_image()))
    assert output['bands'][0]['id'] == 'emissivity'


@pytest.mark.parametrize(
    'red, nir, bt, expected',
    [
        [0.2, 0.7, 300, 303.471031],
    ]
)
def test_lst_calculation(red, nir, bt, expected, tol=0.000001):
    output = utils.constant_image_value(
        landsat.lst(toa_image(red=red, nir=nir, bt=bt)))
    assert abs(output['lst'] - expected) <= tol


def test_lst_band_name():
    output = utils.getinfo(landsat.lst(toa_image()))
    assert output['bands'][0]['id'] == 'lst'
