import datetime

import ee
import pytest

import openet.ssebop.utils as utils


def test_getinfo():
    assert utils.getinfo(ee.Number(1)) == 1


def test_constant_image_value(tol=0.000001):
    expected = 10.123456789
    input_img = ee.Image.constant(expected)
    output = utils.constant_image_value(input_img)
    assert abs(output['constant'] - expected) <= tol


def test_point_image_value(tol=0.001):
    expected = 2364.351
    output = utils.point_image_value(ee.Image('USGS/NED'), [-106.03249, 37.17777])
    assert abs(output['elevation'] - expected) <= tol


def test_point_coll_value(tol=0.001):
    expected = 2364.351
    output = utils.point_coll_value(
        ee.ImageCollection([ee.Image('USGS/NED')]), [-106.03249, 37.17777])
    assert abs(output['elevation']['2012-04-04'] - expected) <= tol


def test_c_to_k(c=20, k=293.15, tol=0.000001):
    output = utils.constant_image_value(utils.c_to_k(ee.Image.constant(c)))
    assert abs(output['constant'] - k) <= tol


@pytest.mark.parametrize(
    'input, expected',
    [
        ['2015-07-13T18:33:39', 1436745600000],
        ['2015-07-13T00:00:00', 1436745600000],

    ]
)


def test_date_to_time_0utc(input, expected):
    input_img = ee.Date(input)
    assert utils.getinfo(utils.date_to_time_0utc(input_img)) == expected


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
    assert utils.is_number(input) == expected


def test_millis():
    assert utils.millis(datetime.datetime(2015, 7, 13)) == 1436745600000


def test_valid_date():
    assert utils.valid_date('2015-07-13') == True
    assert utils.valid_date('2015-02-30') == False
    assert utils.valid_date('20150713') == False
    assert utils.valid_date('07/13/2015') == False
    assert utils.valid_date('07-13-2015', '%m-%d-%Y') == True
