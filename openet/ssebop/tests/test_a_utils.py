import datetime

import ee
import pytest

import openet.ssebop.utils as utils


def test_getinfo():
    assert utils.getinfo(ee.Number(1)) == 1


def test_getinfo_exception():
    with pytest.raises(Exception):
        utils.getinfo('deadbeef')


# # CGM - Not sure how to trigger an EEException to test that the output is None
# #   This fails before it is sent to the getinfo function
# def test_getinfo_eeexception():
#     assert utils.getinfo(ee.Number('deadbeef')) is None


def test_constant_image_value(expected=10.123456789, tol=0.000001):
    output = utils.constant_image_value(ee.Image.constant(expected))
    assert abs(output['constant'] - expected) <= tol


@pytest.mark.parametrize(
    'image_id, xy, scale, expected, tol',
    [
        ['USGS/NED', [-106.03249, 37.17777], 10, 2364.351, 0.001],
        ['USGS/NED', [-106.03249, 37.17777], 1, 2364.351, 0.001],
    ]
)
def test_point_image_value(image_id, xy, scale, expected, tol):
    output = utils.point_image_value(ee.Image(image_id).rename('output'), xy)
    assert abs(output['output'] - expected) <= tol


@pytest.mark.parametrize(
    'image_id, image_date, xy, scale, expected, tol',
    [
        # CGM - This test stopped working for a scale of 1 and returns a different
        #   value for a scale of 10 than the point_image_value() function above.
        # This function uses getRegion() instead of a reduceRegion() call,
        #   so there might have been some sort of change in getRegion().
        ['USGS/NED', '2012-04-04', [-106.03249, 37.17777], 10, 2364.286, 0.001],
        # CGM - The default scale of 1 now returns None/Null for some reason
        # ['USGS/NED', '2012-04-04', [-106.03249, 37.17777], 1, 2364.351, 0.001],
    ]
)
def test_point_coll_value(image_id, image_date, xy, scale, expected, tol):
    input_img = ee.Image(image_id).rename(['output'])
    output = utils.point_coll_value(ee.ImageCollection([input_img]), xy, scale)
    assert abs(output['output'][image_date] - expected) <= tol


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
    assert utils.getinfo(utils.date_to_time_0utc(ee.Date(input))) == expected


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
    assert utils.valid_date('2015-07-13') is True
    assert utils.valid_date('2015-02-30') is False
    assert utils.valid_date('20150713') is False
    assert utils.valid_date('07/13/2015') is False
    assert utils.valid_date('07-13-2015', '%m-%d-%Y') is True
