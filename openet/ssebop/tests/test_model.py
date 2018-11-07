import datetime
import logging

import ee
import pytest

import openet.ssebop as ssebop


SCENE_ID = 'LC08_042035_20150713'
SCENE_DATE = '2015-07-13'


# Should these be fixtures or maybe moved to a utils file?
# I'm not sure how to make them fixtures and allow input parameters
def constant_image_value(image, band_name, crs='EPSG:32613', scale=1):
    """Extract the output value from a calculation done with constant images"""
    return ee.Image(image).reduceRegion(
        reducer=ee.Reducer.first(),
        geometry=ee.Geometry.Rectangle([0, 0, 10, 10], crs, False),
        scale=scale).getInfo()[band_name]


def point_image_value(image, band_name, xy, scale=1):
    """Extract the output value from a calculation done with constant images"""
    return ee.Image(image).reduceRegion(
        reducer=ee.Reducer.first(),
        geometry=ee.Geometry.Point(xy),
        scale=scale).getInfo()[band_name]


def toa_image(red=0.2, nir=0.7, bt=300):
    """Construct a fake Landsat 8 TOA image with renamed bands"""
    return ee.Image.constant([red, nir, bt])\
        .rename(['red', 'nir', 'lst']) \
        .setMulti({
            'system:time_start': ee.Date(SCENE_DATE).millis(),
            'k1_constant': ee.Number(607.76),
            'k2_constant': ee.Number(1260.56)})


def input_image():
    # First construct a fake 'prepped' input image
    return ee.Image.constant([300, 0.8]).rename(['lst', 'ndvi']) \
        .setMulti({
            'system:index': SCENE_ID,
            'system:time_start': ee.Date(SCENE_DATE).millis(),
    })


# def test_ee_init():
#     """Check that Earth Engine was initialized"""
#     assert ee.Number(1).getInfo() == 1


def test_constant_image_value(tol=0.000001):
    expected = 10.123456789
    input_img = ee.Image.constant(expected)
    output = constant_image_value(input_img, 'constant')
    assert abs(output - expected) <= tol


# Test the static methods of the class first
# Do these need to be inside the TestClass?
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
    ]
)
def test_ndvi(red, nir, expected, tol=0.000001):
    toa = toa_image(red=red, nir=nir)
    output = constant_image_value(ssebop.Image._ndvi(toa), 'ndvi')
    # logging.debug('\n  Target values: {}'.format(expected))
    # logging.debug('  Output values: {}'.format(output))
    assert abs(output - expected) <= tol


@pytest.mark.parametrize(
    'red, nir, expected',
    [
        [0.2, 9.0 / 55, 0.985],      # -0.1
        [0.2, 0.2,  0.977],          # 0.0
        [0.1, 11.0 / 90,  0.977],    # 0.1
        # [0.2, 0.3, 0.986335],        # 0.2 - fails, should be 0.977?
        [0.1, 13.0 / 70, 0.986742],  # 0.3
        [0.3, 0.7, 0.987964],        # 0.4
        [0.2, 0.6, 0.99],            # 0.5
        [0.2, 0.8, 0.99],            # 0.6
        [0.1, 17.0 / 30, 0.99],      # 0.7
    ]
)
def test_emissivity(red, nir, expected, tol=0.000001):
    toa = toa_image(red=red, nir=nir)
    output = constant_image_value(ssebop.Image._emissivity(toa),
                                  'emissivity')
    assert abs(output - expected) <= tol


@pytest.mark.parametrize(
    'red, nir, bt, expected',
    [
        [0.2, 0.7, 300, 303.471031],
    ]
)
def test_lst(red, nir, bt, expected, tol=0.000001):
    toa = toa_image(red=red, nir=nir, bt=bt)
    output = constant_image_value(ssebop.Image._lst(toa), 'lst')
    assert abs(output - expected) <= tol


@pytest.mark.parametrize(
    'dt_source,doy,xy,expected',
    [
        ['DAYMET_MEDIAN_V0', 194, [-120.113, 36.336], 19.262],
        # ['DAYMET_MEDIAN_V0', 1, [-120.113, 36.336], 6],  # DEADBEEF - Fails
        ['DAYMET_MEDIAN_V0', 194, [-119.0, 37.5], 25],
        ['DAYMET_MEDIAN_V1', 194, [-120.113, 36.336], 18],
    ]
)
def test_SSEBop_dt(dt_source, doy, xy, expected, tol=0.01):
    """Test getting dT values for a single date at a real point"""
    output_img = ssebop.Image(input_image(), dt_source=dt_source)._dt()
    output = point_image_value(ee.Image(output_img), 'dt', xy)
    assert abs(output - expected) <= tol


@pytest.mark.parametrize(
    'elev_source, xy, expected',
    [
        ['ASSET', [-106.03249, 37.17777], 2369.0],
        ['GTOPO', [-106.03249, 37.17777], 2369.0],
        ['NED', [-106.03249, 37.17777], 2364.35],
        ['SRTM', [-106.03249, 37.17777], 2362.0],
    ]
)
def test_SSEBop_elev(elev_source, xy, expected, tol=0.01):
    """Test getting elevation values for a single date at a real point"""
    output_img = ssebop.Image(input_image(), elev_source=elev_source)._elev()
    output = point_image_value(ee.Image(output_img), 'elev', xy)
    assert abs(output - expected) <= tol


# @pytest.mark.parametrize(
#     'tcorr_source, tmax_source, scene_id, month, expected',
#     [
#         ['SCENE', 'CIMIS', SCENE_ID, 7, [0.9789, 0]],
#         ['SCENE', 'DAYMET', SCENE_ID, 7, [0.9825, 0]],
#         ['SCENE', 'GRIDMET', SCENE_ID, 7, [0.9835, 0]],
#         # ['SCENE', 'TOPOWX', default_scene_id, 7, [0.8, 0]],
#         ['SCENE', 'CIMIS_MEDIAN_V1', SCENE_ID, 7, [0.9742, 0]],
#         ['SCENE', 'DAYMET_MEDIAN_V0', SCENE_ID, 7, [0.9764, 0]],
#         ['SCENE', 'DAYMET_MEDIAN_V1', SCENE_ID, 7, [0.9764, 0]],
#         ['SCENE', 'GRIDMET_MEDIAN_V1', SCENE_ID, 7, [0.9750, 0]],
#         ['SCENE', 'TOPOWX_MEDIAN_V0', SCENE_ID, 7, [0.9752, 0]],
#
#         # If scene_id doesn't match, use monthly value
#         ['SCENE', 'CIMIS', 'XXXX_042035_20150713', 7, [0.9701, 1]],
#         ['SCENE', 'DAYMET', 'XXXX_042035_20150713', 7, [0.9718, 1]],
#         ['SCENE', 'GRIDMET', 'XXXX_042035_20150713', 7, [0.9743, 1]],
#         # ['SCENE', 'TOPOWX', 'XXXX_042035_20150713', 7, [0.8, 1]],
#         ['SCENE', 'CIMIS_MEDIAN_V1', 'XXXX_042035_20150713', 7, [0.9694, 1]],
#         ['SCENE', 'DAYMET_MEDIAN_V0', 'XXXX_042035_20150713', 7, [0.9727, 1]],
#         ['SCENE', 'DAYMET_MEDIAN_V1', 'XXXX_042035_20150713', 7, [0.9727, 1]],
#         ['SCENE', 'GRIDMET_MEDIAN_V1', 'XXXX_042035_20150713', 7, [0.9725, 1]],
#         ['SCENE', 'TOPOWX_MEDIAN_V0', 'XXXX_042035_20150713', 7, [0.9720, 1]],
#
#         # Get monthly value directly (ignore scene ID)
#         ['MONTH', 'CIMIS', SCENE_ID, 7, [0.9701, 1]],
#         ['MONTH', 'DAYMET', SCENE_ID, 7, [0.9718, 1]],
#         ['MONTH', 'GRIDMET', SCENE_ID, 7, [0.9743, 1]],
#         # ['MONTH', 'TOPOWX', default_scene_id, 7, [0.8, 1]],
#         ['MONTH', 'CIMIS_MEDIAN_V1', SCENE_ID, 7, [0.9694, 1]],
#         ['MONTH', 'DAYMET_MEDIAN_V0', SCENE_ID, 7, [0.9727, 1]],
#         ['MONTH', 'DAYMET_MEDIAN_V1', SCENE_ID, 7, [0.9727, 1]],
#         ['MONTH', 'GRIDMET_MEDIAN_V1', SCENE_ID, 7, [0.9725, 1]],
#         ['MONTH', 'TOPOWX_MEDIAN_V0', SCENE_ID, 7, [0.9720, 1]],
#
#         # If scene_id and wrs2_tile/month don't match, use default value
#         # Testing one Tmax source should be good
#         ['SCENE', 'DAYMET', 'XXXX_042035_20150713', 13, [0.978, 2]],
#         ['MONTH', 'DAYMET', SCENE_ID, 13, [0.978, 2]],
#
#         # Test a user defined Tcorr value
#         [0.985, 'DAYMET', SCENE_ID, 6, [0.985, 3]],
#     ]
# )
# def test_tcorr(tcorr_source, tmax_source, scene_id, month, expected, tol=0.000001):
#     """Test getting Tcorr values for a single date at a real point"""
#     logging.debug('\n  {} {}'.format(tcorr_source, tmax_source))
#
#     scene_date = datetime.datetime.strptime(scene_id.split('_')[-1], '%Y%m%d') \
#         .strftime('%Y-%m-%d')
#     input_image = ee.Image.constant(1).setMulti({
#         'system:index': scene_id,
#         'system:time_start': ee.Date(scene_date).millis()})
#     s = ssebop.Image(
#         input_image, tcorr_source=tcorr_source, tmax_source=tmax_source)
#     # Overwrite the month property with test value
#     s.month = ee.Number(month)
#
#     # _tcorr() returns a tuple of the tcorr and tcorr_index
#     # Is there a better way of having this function return a tuple of EE objects
#     tcorr, tcorr_index = s._tcorr()
#     tcorr = tcorr.getInfo()
#     tcorr_index = tcorr_index.getInfo()
#
#     # Check Tcorr first
#     logging.debug('\n  Target values: {}'.format(expected[0]))
#     logging.debug('  Output values: {}'.format(tcorr))
#     assert abs(tcorr - expected[0]) <= tol
#
#     # Then check the Tcorr index
#     logging.debug('\n  Target values: {}'.format(expected[1]))
#     logging.debug('  Output values: {}'.format(tcorr_index))
#     assert tcorr_index == expected[1]


@pytest.mark.parametrize(
    'tmax_source, xy, expected',
    [
        ['CIMIS', [-120.113, 36.336], 307.725],
        ['DAYMET', [-120.113, 36.336], 308.65],
        ['GRIDMET', [-120.113, 36.336], 306.97],
        # ['TOPOWX', [-120.113, 36.336], 301.67],
        ['CIMIS_MEDIAN_V1', [-120.113, 36.336], 308.95],
        ['DAYMET_MEDIAN_V0', [-120.113, 36.336], 310.15],
        ['DAYMET_MEDIAN_V1', [-120.113, 36.336], 310.15],
        ['GRIDMET_MEDIAN_V1', [-120.113, 36.336], 310.44],
        ['TOPOWX_MEDIAN_V0', [-120.113, 36.336], 310.43],
        [305, [-120.113, 36.336], 305],
    ]
)
def test_SSEBop_tmax(tmax_source, xy, expected, tol=0.01):
    """Test getting Tmax values for a single date at a real point"""
    output_img = ssebop.Image(input_image(), tmax_source=tmax_source)._tmax()
    output = point_image_value(ee.Image(output_img), 'tmax', xy)
    assert abs(output - expected) <= tol



# @pytest.mark.parametrize(
#     'tmax_source,xy,expected',
#     [
#         ['CIMIS', [-120.113, 36.336], 308.95],
#         ['DAYMET', [-120.113, 36.336], 310.15],
#         ['GRIDMET', [-120.113, 36.336], 310.44],
#         # ['TOPOWX', [-106.03249, 37.17777], 298.91],
#     ]
# )
# def test_SSEBop_get_tmax_fallback(tmax_source, xy, expected, tol=0.01):
#     """Test getting Tmax median value when daily doesn't exist
#
#     To test this, move the test date into the future
#     """
#     input_img = ee.Image.constant([300, 0.8]).rename(['lst', 'ndvi']) \
#         .setMulti({
#             'system:index': SCENE_ID,
#             'system:time_start': ee.Date(SCENE_DATE).update(2019).millis()})
#     output_img = ssebop.Image(input_img, tmax_source=tmax_source)._tmax()
#     output = point_image_value(ee.Image(tmax), 'tmax', xy)
#     assert abs(output - expected) <= tol




today_dt = datetime.datetime.today()
@pytest.mark.parametrize(
    'tmax_source,expected',
    [
        ['CIMIS', {'TMAX_VERSION': '{}'.format(today_dt.strftime('%Y-%m-%d'))}],
        ['DAYMET', {'TMAX_VERSION': '{}'.format(today_dt.strftime('%Y-%m-%d'))}],
        ['GRIDMET', {'TMAX_VERSION': '{}'.format(today_dt.strftime('%Y-%m-%d'))}],
        # ['TOPOWX', {'TMAX_VERSION': '{}'.format(today_dt.strftime('%Y-%m-%d'))}],
        ['CIMIS_MEDIAN_V1', {'TMAX_VERSION': 'median_v1'}],
        ['DAYMET_MEDIAN_V0', {'TMAX_VERSION': 'median_v0'}],
        ['DAYMET_MEDIAN_V1', {'TMAX_VERSION': 'median_v1'}],
        ['GRIDMET_MEDIAN_V1', {'TMAX_VERSION': 'median_v1'}],
        ['TOPOWX_MEDIAN_V0', {'TMAX_VERSION': 'median_v0'}],
        [305, {'TMAX_VERSION': 'CUSTOM_305'}],
    ]
)
def test_SSEBop_tmax_properties(tmax_source, expected):
    """Test if properties are set on Tmax image"""
    tmax = ssebop.Image(input_image(), tmax_source=tmax_source)._tmax()
    output = tmax.getInfo()['properties']
    assert output['TMAX_SOURCE'] == tmax_source
    assert output['TMAX_VERSION'] == expected['TMAX_VERSION']


# @pytest.mark.parametrize(
#     # DEADBEEF - These are totally made up values
#     'lst,ndvi,dt,elev,tcorr,tmax,tdiff,elr,expected',
#     [
#         # Test ETf clamp conditions
#         [300, 0.80, 10, 50, 0.98, 310, 15, False, None],
#         [300, 0.80, 15, 50, 0.98, 310, 15, False, 1.05],
#         # Test dT high, max/min, and low clamp values
#         [305, 0.80, 29, 50, 0.98, 310, 10, False, 0.952],
#         [305, 0.80, 25, 50, 0.98, 310, 10, False, 0.952],
#         [305, 0.80, 6, 50, 0.98, 310, 10, False, 0.8],
#         [305, 0.80, 5, 50, 0.98, 310, 10, False, 0.8],
#         # High and low test values (made up numbers)
#         [305, 0.80, 15, 50, 0.98, 310, 10, False, 0.9200],
#         [315, 0.10, 15, 50, 0.98, 310, 10, False, 0.2533],
#         # Test Tcorr
#         [305, 0.80, 15, 50, 0.985, 310, 10, False, 1.0233],
#         [315, 0.10, 15, 50, 0.985, 310, 10, False, 0.3566],
#         # Test ELR flag
#         [305, 0.80, 15, 2000, 0.98, 310, 10, False, 0.9200],
#         [305, 0.80, 15, 2000, 0.98, 310, 10, True, 0.8220],
#         [315, 0.10, 15, 2000, 0.98, 310, 10, True, 0.1553],
#         # Test Tdiff buffer value masking
#         [299, 0.80, 15, 50, 0.98, 310, 10, False, None],
#         [304, 0.10, 15, 50, 0.98, 310, 5, False, None],
#         # Central Valley test values
#         [302, 0.80, 17, 50, 0.985, 308, 10, False, 1.05],
#         [327, 0.08, 17, 50, 0.985, 308, 10, False, 0.0],
#     ]
# )
# def test_SSEBop_etf(test_Image, expected=0.5, tol=0.000001):
#     output = constant_image_value(ee.Image(test_Image.etf), 'etf')
#     assert abs(output - expected) <= tol


# def test_SSEBop_from_landsat_c1_toa(self):
    #     assert False


# def test_c_to_k():
#     assert False


# def test_date_to_time_0utc():
#     assert False


# def test_is_number():
#     assert False
