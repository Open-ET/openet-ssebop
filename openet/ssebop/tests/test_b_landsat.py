# import datetime
# import pprint

import ee
import pytest

import openet.ssebop.landsat as landsat
import openet.ssebop.utils as utils
# TODO: import utils from openet.core
# import openet.core.utils as utils


def sr_image(blue=0.1, green=0.1, red=0.1, nir=0.9, swir1=0.1, swir2=0.1, bt=305, qa=1):
    """Construct a fake Landsat 8 SR image with renamed bands"""
    return (
        ee.Image.constant([blue, green, red, nir, swir1, swir2, bt, qa])
        .rename(['blue', 'green', 'red', 'nir', 'swir1', 'swir2', 'tir', 'QA_PIXEL'])
        .set({
            # 'system:time_start': ee.Date(SCENE_DATE).millis(),
            'k1_constant': ee.Number(607.76),
            'k2_constant': ee.Number(1260.56),
        })
    )


def test_ndvi_band_name():
    output = utils.getinfo(landsat.ndvi(sr_image()))
    assert output['bands'][0]['id'] == 'ndvi'


@pytest.mark.parametrize(
    'red, nir, expected',
    [
        [0.02, 0.9 / 55, -0.1],
        [0.02, 0.02,  0.0],
        [0.01, 0.11 / 9, 0.1],
        [0.02, 0.03, 0.2],
        [0.01, 0.13 / 7, 0.3],
        [0.03, 0.07, 0.4],
        [0.02, 0.06, 0.5],
        [0.02, 0.08, 0.6],
        [0.01, 0.17 / 3, 0.7],
        [0.01, 0.09, 0.8],
    ]
)
def test_ndvi_calculation(red, nir, expected, tol=0.000001):
    output = utils.constant_image_value(landsat.ndvi(sr_image(red=red, nir=nir)))
    assert abs(output['ndvi'] - expected) <= tol


@pytest.mark.parametrize(
    'red, nir, expected',
    [
        [1.0, 0.4, 0.0],
        [0.4, 1.0, 0.0],
        [1.0, 1.0, 0.0],
    ]
)
def test_ndvi_saturated_reflectance(red, nir, expected, tol=0.000001):
    # Check that saturated reflectance values return 0
    output = utils.constant_image_value(landsat.ndvi(sr_image(red=red, nir=nir)))
    assert abs(output['ndvi'] - expected) <= tol


@pytest.mark.parametrize(
    'red, nir, expected',
    [
        [-0.1, -0.1, 0.0],
        [0.0, 0.0, 0.0],
        [0.009, 0.009, 0.0],
        [0.009, -0.01, 0.0],
        [-0.01, 0.009, 0.0],
        # Check that calculation works correctly if one value is above threshold
        [-0.01, 0.1, 1.0],
        [0.1, -0.01, -1.0],
    ]
)
def test_ndvi_negative_non_water(red, nir, expected, tol=0.000001):
    # Check that non-water pixels with very low or negative reflectance values are set to 0.0
    output = utils.constant_image_value(landsat.ndvi(sr_image(red=red, nir=nir, qa=1)))
    assert abs(output['ndvi'] - expected) <= tol


@pytest.mark.parametrize(
    'red, nir, expected',
    [
        [-0.1, -0.1, -0.1],
        [0.0, 0.0, -0.1],
        [0.009, 0.009, -0.1],
        [0.009, -0.01, -0.1],
        [-0.01, 0.009, -0.1],
    ]
)
def test_ndvi_negative_water(red, nir, expected, tol=0.000001):
    # Check that water pixels with very low or negative reflectance values are set to -0.1
    output = utils.constant_image_value(landsat.ndvi(
        sr_image(red=red, nir=nir, qa=128), gsw_extent_flag=False
    ))
    assert abs(output['ndvi'] - expected) <= tol


def test_ndwi_band_name():
    output = utils.getinfo(landsat.ndwi(sr_image()))
    assert output['bands'][0]['id'] == 'ndwi'


@pytest.mark.parametrize(
    'green, swir1, expected',
    [
        [0.01, 0.07, 0.75],
        [0.01, 0.03, 0.5],
        [0.9 / 55, 0.02, 0.1],
        [0.2, 0.2, 0.0],
        [0.11 / 9, 0.01, -0.1],
        [0.07, 0.03, -0.4],
        [0.09, 0.01, -0.8],
    ]
)
def test_ndwi_calculation(green, swir1, expected, tol=0.000001):
    output = utils.constant_image_value(landsat.ndwi(sr_image(green=green, swir1=swir1)))
    assert abs(output['ndwi'] - expected) <= tol


@pytest.mark.parametrize(
    'green, swir1, expected',
    [
        [-0.1, -0.1, 0.0],
        [0.0, 0.0, 0.0],
        [0.009, 0.009, 0.0],
        [0.009, -0.01, 0.0],
        [-0.01, 0.009, 0.0],
        # Check that calculation works correctly if one value is above threshold
        [-0.01, 0.1, 1.0],
        [0.1, -0.01, -1.0],
    ]
)
def test_ndwi_negative_reflectance(green, swir1, expected, tol=0.000001):
    # Check that very low or negative reflectance values are set to 0
    output = utils.constant_image_value(landsat.ndwi(sr_image(green=green, swir1=swir1)))
    assert abs(output['ndwi'] - expected) <= tol


@pytest.mark.parametrize(
    'green, swir1, expected',
    [
        [1.0, 0.4, 0.0],
        [0.4, 1.0, 0.0],
        [1.0, 1.0, 0.0],
    ]
)
def test_ndwi_saturated_reflectance(green, swir1, expected, tol=0.000001):
    # Check that saturated reflectance values return 0
    output = utils.constant_image_value(landsat.ndwi(sr_image(green=green, swir1=swir1)))
    assert abs(output['ndwi'] - expected) <= tol


def test_emissivity_band_name():
    output = utils.getinfo(landsat.emissivity(sr_image()))
    assert output['bands'][0]['id'] == 'emissivity'


@pytest.mark.parametrize(
    'red, nir, expected',
    [
        [0.02, 0.9 / 55, 0.985],     # -0.1
        [0.02, 0.02,  0.977],        # 0.0
        [0.01, 0.11 / 9,  0.977],    # 0.1
        [0.02, 0.02999, 0.977],      # 0.3- (0.3 NIR isn't exactly an NDVI of 0.2)
        [0.02, 0.03001, 0.986335],   # 0.3+
        [0.01, 0.13 / 7, 0.986742],  # 0.3
        [0.03, 0.07, 0.987964],      # 0.4
        [0.02, 0.06, 0.99],          # 0.5
        [0.02, 0.08, 0.99],          # 0.6
        [0.01, 0.17 / 3, 0.99],      # 0.7
    ]
)
def test_emissivity_calculation(red, nir, expected, tol=0.000001):
    output = utils.constant_image_value(landsat.emissivity(sr_image(red=red, nir=nir)))
    assert abs(output['emissivity'] - expected) <= tol


def test_lst_band_name():
    output = utils.getinfo(landsat.lst(sr_image()))
    assert output['bands'][0]['id'] == 'lst'


@pytest.mark.parametrize(
    'red, nir, bt, expected',
    [
        [0.02, 0.07, 300, 303.471031],
    ]
)
def test_lst_calculation(red, nir, bt, expected, tol=0.000001):
    output = utils.constant_image_value(landsat.lst(sr_image(red=red, nir=nir, bt=bt)))
    assert abs(output['lst'] - expected) <= tol
