import ee
import pytest

import openet.ssebop.utils as utils


def test_constant_image_value(tol=0.000001):
    expected = 10.123456789
    input_img = ee.Image.constant(expected)
    output = utils.constant_image_value(input_img)
    assert abs(output - expected) <= tol


def test_point_image_value(tol=0.01):
    expected = 2364.35
    output = utils.point_image_value(ee.Image('USGS/NED'), [-106.03249, 37.17777])
    assert abs(output - expected) <= tol


def test_c_to_k(c=20, k=293.15, tol=0.000001):
    output = utils.constant_image_value(utils._c_to_k(ee.Image.constant(c)))
    assert abs(output - k) <= tol


@pytest.mark.parametrize(
    'input, expected',
    [
        ['2015-07-13T18:33:39', 1436745600000],
        ['2015-07-13T00:00:00', 1436745600000],

    ]
)
def test_date_to_time_0utc(input, expected):
    input_img = ee.Date(input)
    assert utils._date_to_time_0utc(input_img).getInfo() == expected


@pytest.mark.parametrize(
    # Note: These are made up values
    'input, expected',
    [
        [300, True],
        ['300', True],
        [300.25, True],
        ['300.25', True],
        ['a', False],
    ]
)
def test_is_number(input, expected):
    assert utils._is_number(input) == expected
