import datetime
import pprint

import ee
import pytest

import openet.ssebop as ssebop
import openet.ssebop.utils as utils
# TODO: import utils from openet.core
# import openet.core.utils as utils


COLL_ID = 'LANDSAT/LC08/C01/T1_TOA/'
SCENE_ID = 'LC08_042035_20150713'
SCENE_DT = datetime.datetime.strptime(SCENE_ID[-8:], '%Y%m%d')
SCENE_DATE = SCENE_DT.strftime('%Y-%m-%d')
SCENE_DOY = int(SCENE_DT.strftime('%j'))
SCENE_TIME = utils.millis(SCENE_DT)
SCENE_POINT = (-119.5, 36.0)
TEST_POINT = (-119.44252382373145, 36.04047742246546)

# SCENE_TIME = utils.getinfo(ee.Date(SCENE_DATE).millis())
# SCENE_POINT = (-119.44252382373145, 36.04047742246546)
# SCENE_POINT = utils.getinfo(
#     ee.Image(COLL_ID + SCENE_ID).geometry().centroid())['coordinates']


# Should these be test fixtures instead?
# I'm not sure how to make them fixtures and allow input parameters
def toa_image(red=0.1, nir=0.9, bt=305):
    """Construct a fake Landsat 8 TOA image with renamed bands"""
    return ee.Image.constant([red, nir, bt])\
        .rename(['red', 'nir', 'lst']) \
        .set({
            'system:time_start': ee.Date(SCENE_DATE).millis(),
            'k1_constant': ee.Number(607.76),
            'k2_constant': ee.Number(1260.56),
        })


def default_image(lst=305, ndvi=0.8):
    # First construct a fake 'prepped' input image
    return ee.Image.constant([lst, ndvi]).rename(['lst', 'ndvi']) \
        .set({
            'system:index': SCENE_ID,
            'system:time_start': ee.Date(SCENE_DATE).millis(),
            'system:id': COLL_ID + SCENE_ID,
        })


# Setting et_reference_source and et_reference_band on the default image to
#   simplify testing but these do not have defaults in the Image class init
def default_image_args(lst=305, ndvi=0.8,
                       et_reference_source='IDAHO_EPSCOR/GRIDMET',
                       et_reference_band='etr', et_reference_factor=0.85,
                       et_reference_resample='nearest'):
    return {
        'image': default_image(lst=lst, ndvi=ndvi),
        'et_reference_source': et_reference_source,
        'et_reference_band': et_reference_band,
        'et_reference_factor': et_reference_factor,
        'et_reference_resample': et_reference_resample,
    }


def default_image_obj(lst=305, ndvi=0.8,
                      et_reference_source='IDAHO_EPSCOR/GRIDMET',
                      et_reference_band='etr', et_reference_factor=0.85,
                      et_reference_resample='nearest'):
    return ssebop.Image(**default_image_args(
        lst=lst, ndvi=ndvi,
        et_reference_source=et_reference_source,
        et_reference_band=et_reference_band,
        et_reference_factor=et_reference_factor,
        et_reference_resample=et_reference_resample,
    ))


def test_Image_init_default_parameters():
    m = ssebop.Image(default_image())
    assert m.et_reference_source == None
    assert m.et_reference_band == None
    assert m.et_reference_factor == None
    assert m.et_reference_resample == None
    # TODO: Change to 'DAYMET_MEDIAN_V0'
    assert m._dt_source == 'DAYMET_MEDIAN_V1'
    assert m._elev_source == 'SRTM'
    assert m._tcorr_source == 'IMAGE'
    # TODO: Change to 'DAYMET_MEDIAN_V2'
    assert m._tmax_source == 'TOPOWX_MEDIAN_V0'
    assert m._elr_flag == False
    # DEADBEEF - Tdiff threshold parameter is being removed
    # assert m._tdiff_threshold == 15
    assert m._dt_min == 6
    assert m._dt_max == 25


# Todo: Break these up into separate functions?
def test_Image_init_calculated_properties():
    m = default_image_obj()
    assert utils.getinfo(m._time_start) == SCENE_TIME
    assert utils.getinfo(m._scene_id) == SCENE_ID
    assert utils.getinfo(m._wrs2_tile) == 'p{}r{}'.format(
        SCENE_ID.split('_')[1][:3], SCENE_ID.split('_')[1][3:])


def test_Image_init_date_properties():
    m = default_image_obj()
    assert utils.getinfo(m._date)['value'] == SCENE_TIME
    assert utils.getinfo(m._year) == int(SCENE_DATE.split('-')[0])
    assert utils.getinfo(m._month) == int(SCENE_DATE.split('-')[1])
    assert utils.getinfo(m._start_date)['value'] == SCENE_TIME
    assert utils.getinfo(m._end_date)['value'] == utils.millis(
        SCENE_DT + datetime.timedelta(days=1))
    assert utils.getinfo(m._doy) == SCENE_DOY
    assert utils.getinfo(m._cycle_day) == int(
        (SCENE_DT - datetime.datetime(1970, 1, 3)).days % 8 + 1)


def test_Image_init_scene_id_property():
    """Test that the system:index from a merged collection is parsed"""
    input_img = default_image()
    m = ssebop.Image(input_img.set('system:index', '1_2_' + SCENE_ID))
    assert utils.getinfo(m._scene_id) == SCENE_ID


def test_Image_init_elr_flag_str():
    """Test that the elr_flag can be read as a string"""
    assert ssebop.Image(default_image(), elr_flag='FALSE')._elr_flag == False
    assert ssebop.Image(default_image(), elr_flag='true')._elr_flag == True
    with pytest.raises(ValueError):
        utils.getinfo(ssebop.Image(default_image(), elr_flag='FOO')._elr_flag)


def test_Image_ndvi_properties():
    """Test if properties are set on the NDVI image"""
    output = utils.getinfo(ssebop.Image(default_image()).ndvi)
    assert output['bands'][0]['id'] == 'ndvi'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == COLL_ID + SCENE_ID


def test_Image_lst_properties():
    """Test if properties are set on the LST image"""
    output = utils.getinfo(ssebop.Image(default_image()).lst)
    assert output['bands'][0]['id'] == 'lst'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == COLL_ID + SCENE_ID


@pytest.mark.parametrize(
    'dt_source, doy, xy, expected',
    [
        ['DAYMET_MEDIAN_V0', 194, [-120.113, 36.336], 19.262],
        ['DAYMET_MEDIAN_V1', 194, [-120.113, 36.336], 18],
        ['DAYMET_MEDIAN_V1', 194, [-119.0, 37.5], 21],
    ]
)
def test_Image_dt_source_median(dt_source, doy, xy, expected, tol=0.001):
    """Test getting median dT values for a single date at a real point"""
    m = ssebop.Image(default_image(), dt_source=dt_source)
    m._doy = doy
    output = utils.point_image_value(ee.Image(m.dt), xy)
    assert abs(output['dt'] - expected) <= tol


@pytest.mark.parametrize(
    'dt_source, doy, xy, expected',
    [
        ['DAYMET_MEDIAN_V0', 1, [-120.113, 36.336], 6],
        ['DAYMET_MEDIAN_V1', 1, [-120.113, 36.336], 6],
        ['DAYMET_MEDIAN_V0', 194, [-119.0, 37.5], 25],
    ]
)
def test_Image_dt_source_clamping(dt_source, doy, xy, expected, tol=0.001):
    """Check that dT values are clamped to dt_min and dt_max (6, 25)"""
    m = ssebop.Image(default_image(), dt_source=dt_source)
    m._doy = doy
    output = utils.point_image_value(ee.Image(m.dt), xy)
    assert abs(output['dt'] - expected) <= tol


@pytest.mark.parametrize(
    'dt_source, xy, expected',
    [
        ['19.262', [-120.113, 36.336], 19.262],
        [19.262, [-120.113, 36.336], 19.262],
    ]
)
def test_Image_dt_source_constant(dt_source, xy, expected, tol=0.001):
    """Test getting condatnt dT values for a single date at a real point"""
    m = ssebop.Image(default_image(), dt_source=dt_source)
    output = utils.point_image_value(ee.Image(m.dt), xy)
    assert abs(output['dt'] - expected) <= tol


@pytest.mark.parametrize(
    'dt_source, date, xy, expected',
    [
        ['CIMIS', '2017-07-16', [-122.1622, 39.1968], 17.1013],
        ['DAYMET', '2017-07-16', [-122.1622, 39.1968], 13.5525],
        ['GRIDMET', '2017-07-16', [-122.1622, 39.1968], 18.1711],
    ]
)
def test_Image_dt_source_calculated(dt_source, date, xy, expected, tol=0.001):
    """Test getting calculated dT values for a single date at a real point"""
    m = ssebop.Image(default_image(), dt_source=dt_source)
    # Start/end date are needed to filter the source collection
    m._start_date = ee.Date.parse('yyyy-MM-dd', date)
    m._end_date = ee.Date.parse('yyyy-MM-dd', date).advance(1, 'day')
    # DOY is needed in dT calculation
    m._doy = ee.Date.parse('yyyy-MM-dd', date).getRelative('day', 'year')\
        .int().add(1)
    output = utils.point_image_value(ee.Image(m.dt), xy)
    assert abs(output['dt'] - expected) <= tol


def test_Image_dt_sources_exception():
    with pytest.raises(ValueError):
        utils.getinfo(ssebop.Image(default_image(), dt_source='').dt)


@pytest.mark.parametrize(
    'doy, dt_min, dt_max',
    [
        [1, 6, 25],
        [200, 6, 25],
        [200, 10, 15],
    ]
)
def test_Image_dt_clamping(doy, dt_min, dt_max):
    m = ssebop.Image(default_image(), dt_source='DAYMET_MEDIAN_V1',
                    dt_min=dt_min, dt_max=dt_max)
    m._doy = doy
    reducer = ee.Reducer.min().combine(ee.Reducer.max(), sharedInputs=True)
    output = utils.getinfo(ee.Image(m.dt)\
        .reduceRegion(reducer=reducer, scale=1000, tileScale=4, maxPixels=2E8,
                      geometry=ee.Geometry.Rectangle(-125, 25, -65, 50)))
    assert output['dt_min'] >= dt_min
    assert output['dt_max'] <= dt_max


@pytest.mark.parametrize(
    'elev_source, xy, expected',
    [
        ['ASSET', [-106.03249, 37.17777], 2369.0],
        ['GTOPO', [-106.03249, 37.17777], 2369.0],
        ['NED', [-106.03249, 37.17777], 2364.351],
        ['SRTM', [-106.03249, 37.17777], 2362.0],
        # Check string/float constant values
        ['2364.351', [-106.03249, 37.17777], 2364.351],
        [2364.351, [-106.03249, 37.17777], 2364.351],
        # Check custom images
        ['projects/earthengine-legacy/assets/projects/usgs-ssebop/srtm_1km', [-106.03249, 37.17777], 2369.0],
        ['projects/earthengine-legacy/assets/projects/usgs-ssebop/srtm_1km', [-106.03249, 37.17777], 2369.0],
        # DEADBEEF - We should allow any EE image (not just users/projects)
        # ['USGS/NED', [-106.03249, 37.17777], 2364.35],
    ]
)
def test_Image_elev_sources(elev_source, xy, expected, tol=0.001):
    """Test getting elevation values for a single date at a real point"""
    output = utils.point_image_value(
        ssebop.Image(default_image(), elev_source=elev_source).elev, xy)
    assert abs(output['elev'] - expected) <= tol


def test_Image_elev_sources_exception():
    with pytest.raises(ValueError):
        utils.getinfo(ssebop.Image(default_image(), elev_source='').elev)


def test_Image_elev_band_name():
    output = utils.getinfo(default_image_obj().elev)['bands'][0]['id']
    assert output == 'elev'


@pytest.mark.parametrize(
    'tcorr_source, tmax_source, scene_id, month, expected',
    [
        ['FEATURE', 'CIMIS', SCENE_ID, 7, [0.9789, 0]],
        ['FEATURE', 'DAYMET', SCENE_ID, 7, [0.9825, 0]],
        ['FEATURE', 'GRIDMET', SCENE_ID, 7, [0.9835, 0]],
        ['FEATURE', 'CIMIS_MEDIAN_V1', SCENE_ID, 7, [0.9742, 0]],
        ['FEATURE', 'DAYMET_MEDIAN_V0', SCENE_ID, 7, [0.9764, 0]],
        ['FEATURE', 'DAYMET_MEDIAN_V1', SCENE_ID, 7, [0.9762, 0]],
        ['FEATURE', 'GRIDMET_MEDIAN_V1', SCENE_ID, 7, [0.9750, 0]],
        ['FEATURE', 'TOPOWX_MEDIAN_V0', SCENE_ID, 7, [0.9752, 0]],
        ['FEATURE', 'TOPOWX_MEDIAN_V0B', SCENE_ID, 7, [0.9752, 0]],
        # If scene_id doesn't match, use monthly value
        ['FEATURE', 'CIMIS', 'XXXX_042035_20150713', 7, [0.9701, 1]],
        ['FEATURE', 'DAYMET', 'XXXX_042035_20150713', 7, [0.9718, 1]],
        ['FEATURE', 'GRIDMET', 'XXXX_042035_20150713', 7, [0.9743, 1]],
        ['FEATURE', 'CIMIS_MEDIAN_V1', 'XXXX_042035_20150713', 7, [0.9694, 1]],
        ['FEATURE', 'DAYMET_MEDIAN_V0', 'XXXX_042035_20150713', 7, [0.9727, 1]],
        ['FEATURE', 'DAYMET_MEDIAN_V1', 'XXXX_042035_20150713', 7, [0.9717, 1]],
        ['FEATURE', 'GRIDMET_MEDIAN_V1', 'XXXX_042035_20150713', 7, [0.9725, 1]],
        ['FEATURE', 'TOPOWX_MEDIAN_V0', 'XXXX_042035_20150713', 7, [0.9720, 1]],
        ['FEATURE', 'TOPOWX_MEDIAN_V0B', 'XXXX_042035_20150713', 7, [0.9723, 1]],
        # Get monthly value directly (ignore scene ID)
        ['FEATURE_MONTH', 'CIMIS', SCENE_ID, 7, [0.9701, 1]],
        ['FEATURE_MONTH', 'DAYMET', SCENE_ID, 7, [0.9718, 1]],
        ['FEATURE_MONTH', 'GRIDMET', SCENE_ID, 7, [0.9743, 1]],
        ['FEATURE_MONTH', 'CIMIS_MEDIAN_V1', SCENE_ID, 7, [0.9694, 1]],
        ['FEATURE_MONTH', 'DAYMET_MEDIAN_V0', SCENE_ID, 7, [0.9727, 1]],
        ['FEATURE_MONTH', 'DAYMET_MEDIAN_V1', SCENE_ID, 7, [0.9717, 1]],
        ['FEATURE_MONTH', 'GRIDMET_MEDIAN_V1', SCENE_ID, 7, [0.9725, 1]],
        ['FEATURE_MONTH', 'TOPOWX_MEDIAN_V0', SCENE_ID, 7, [0.9720, 1]],
        ['FEATURE_MONTH', 'TOPOWX_MEDIAN_V0B', SCENE_ID, 7, [0.9723, 1]],
        # Get annual value directly
        # ['FEATURE_ANNUAL', 'TOPOWX_MEDIAN_V0B', SCENE_ID, 7, [0.9786, 2]],
        # If scene_id and wrs2_tile/month don't match, use default value
        # Testing one Tmax source should be good
        ['FEATURE', 'DAYMET', 'XXXX_042035_20150713', 13, [0.9780, 3]],
        ['FEATURE_MONTH', 'DAYMET', SCENE_ID, 13, [0.9780, 3]],
        # Test a user defined Tcorr value
        ['0.9850', 'DAYMET', SCENE_ID, 6, [0.9850, 4]],
        [0.9850, 'DAYMET', SCENE_ID, 6, [0.9850, 4]],
        # Check that deprecated 'SCENE' source works
        ['SCENE', 'CIMIS', SCENE_ID, 7, [0.9789, 0]],
    ]
)
def test_Image_tcorr_ftr_source(tcorr_source, tmax_source, scene_id, month,
                                expected, tol=0.0001):
    """Test getting Tcorr value and index for a single date at a real point"""
    scene_date = datetime.datetime.strptime(scene_id.split('_')[-1], '%Y%m%d') \
        .strftime('%Y-%m-%d')
    input_image = ee.Image.constant(1).set({
        'system:index': scene_id,
        'system:time_start': ee.Date(scene_date).millis()})
    m = ssebop.Image(input_image, tcorr_source=tcorr_source,
                     tmax_source=tmax_source)
    # Overwrite the month property with the test value
    m._month = ee.Number(month)

    # _tcorr returns a tuple of the tcorr and tcorr_index
    tcorr, tcorr_index = m.tcorr
    tcorr = utils.getinfo(tcorr)
    tcorr_index = utils.getinfo(tcorr_index)

    assert abs(tcorr - expected[0]) <= tol
    assert tcorr_index == expected[1]


@pytest.mark.parametrize(
    'tcorr_source, tmax_source, scene_id, expected',
    [
        # TOPOWX_MEDIAN_V0
        ['IMAGE', 'TOPOWX_MEDIAN_V0', 'LC08_042035_20150713', [0.9752, 0]],
        ['IMAGE_DAILY', 'TOPOWX_MEDIAN_V0', 'LC08_042035_20150713', [0.9752, 0]],
        ['IMAGE_MONTHLY', 'TOPOWX_MEDIAN_V0', 'LC08_042035_20150713', [0.9723, 1]],
        ['IMAGE_ANNUAL', 'TOPOWX_MEDIAN_V0', 'LC08_042035_20150713', [0.9786, 2]],
        ['IMAGE_DEFAULT', 'TOPOWX_MEDIAN_V0', 'LC08_042035_20150713', [0.978, 3]],
        # DAYMET_MEDIAN_V2
        # ['IMAGE', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713', [0.9752, 0]],
        # ['IMAGE_DAILY', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713', [0.9752, 0]],
        # ['IMAGE_MONTHLY', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713', [0.9723, 1]],
        # ['IMAGE_ANNUAL', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713', [0.9786, 2]],
        # ['IMAGE_DEFAULT', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713', [0.978, 3]],
    ]
)
def test_Image_tcorr_image_source(tcorr_source, tmax_source, scene_id,
                                  expected, tol=0.0001):
    """Test getting Tcorr value and index for a single date at a real point"""
    scene_date = datetime.datetime.strptime(scene_id.split('_')[-1], '%Y%m%d') \
        .strftime('%Y-%m-%d')
    input_image = ee.Image.constant(1).set({
        'system:time_start': ee.Date(scene_date).millis()})
    tcorr_img, index_img = ssebop.Image(
        input_image, tcorr_source=tcorr_source, tmax_source=tmax_source).tcorr

    # Tcorr images are constant images and need to be queried at a point
    tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
    index = utils.point_image_value(index_img, SCENE_POINT)
    assert abs(tcorr['tcorr'] - expected[0]) <= tol
    assert index['index'] == expected[1]


def test_Image_tcorr_image_month(expected=[0.9723, 1], tol=0.0001):
    """Test getting monthly Tcorr from composite when daily is missing"""
    # Setting start date to well before beginning of daily Tcorr images
    # 1980-07-04 should have the same cycle_day value as previous tests
    input_image = ee.Image.constant(1).set({
        'system:time_start': ee.Date('1980-07-04').millis()})
    m = ssebop.Image(input_image, tcorr_source='IMAGE',
                     tmax_source='TOPOWX_MEDIAN_V0')
    tcorr_img, index_img = m.tcorr
    tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
    index = utils.point_image_value(index_img, SCENE_POINT)
    assert abs(tcorr['tcorr'] - expected[0]) <= tol
    assert index['index'] == expected[1]


def test_Image_tcorr_image_annual(expected=[0.9786, 2], tol=0.0001):
    """Test getting annual Tcorr from composite when monthly/daily are missing"""
    input_image = ee.Image.constant(1).set({
        'system:time_start': ee.Date('1980-07-04').millis()})
    m = ssebop.Image(input_image, tcorr_source='IMAGE',
                     tmax_source='TOPOWX_MEDIAN_V0')
    m._month = ee.Number(9999)
    tcorr_img, index_img = m.tcorr
    tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
    index = utils.point_image_value(index_img, SCENE_POINT)
    assert abs(tcorr['tcorr'] - expected[0]) <= tol
    assert index['index'] == expected[1]


def test_Image_tcorr_image_default(expected=[0.978, 3], tol=0.0001):
    """Test getting default Tcorr from composite"""
    input_image = ee.Image.constant(1).set({
        'system:time_start': ee.Date('1980-07-04').millis()})
    m = ssebop.Image(input_image, tcorr_source='IMAGE',
                     tmax_source='TOPOWX_MEDIAN_V0')
    m._month = ee.Number(9999)
    m._cycle_day = ee.Number(9999)
    tcorr_img, index_img = m.tcorr
    tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
    index = utils.point_image_value(index_img, SCENE_POINT)
    assert abs(tcorr['tcorr'] - expected[0]) <= tol
    assert index['index'] == expected[1]


def test_Image_tcorr_image_daily():
    """Tcorr should be masked for date outside range with IMAGE_DAILY"""
    input_image = ee.Image.constant(1).set({
        'system:time_start': ee.Date('1980-07-04').millis()})
    m = ssebop.Image(input_image, tcorr_source='IMAGE_DAILY',
                     tmax_source='TOPOWX_MEDIAN_V0')
    tcorr_img, index_img = m.tcorr
    tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
    index = utils.point_image_value(index_img, SCENE_POINT)
    assert tcorr['tcorr'] is None
    assert index['index'] is None


def test_Image_tcorr_image_daily_last_date_ingested():
    """Test if last exported daily Tcorr image is used

    Two extra daily images with system:time_starts of "1979-01-01" but different
    "date_ingested" properties were added to the collection for this test.
    The "first" and "second" images have values of 1 and 2 respectively.
    """
    input_image = ee.Image.constant(1).set({
        'system:time_start': ee.Date('1979-01-01').millis()})
    m = ssebop.Image(input_image, tcorr_source='IMAGE_DAILY',
                     tmax_source='TOPOWX_MEDIAN_V0')
    tcorr_img, index_img = m.tcorr
    tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
    assert tcorr['tcorr'] == 2


@pytest.mark.parametrize(
    'tcorr_src',
    [
        '',
        'FEATURE_DEADBEEF',
        'IMAGE_DEADBEEF',
    ]
)
def test_Image_tcorr_sources_exception(tcorr_src):
    with pytest.raises(ValueError):
        utils.getinfo(ssebop.Image(default_image(), tcorr_source=tcorr_src).tcorr)


@pytest.mark.parametrize(
    'tcorr_src, tmax_src',
    [
        ['FEATURE', 'DEADBEEF'],
        ['IMAGE', 'DEADBEEF'],
    ]
)
def test_Image_tcorr_tmax_sources_exception(tcorr_src, tmax_src):
    with pytest.raises(ValueError):
        utils.getinfo(ssebop.Image(default_image(), tcorr_source=tcorr_src,
                                   tmax_source=tmax_src).tcorr)


# TODO: Add test for when there is no Tcorr image for the Landsat date


@pytest.mark.parametrize(
    'tmax_source, xy, expected',
    [
        ['CIMIS', [-120.113, 36.336], 307.725],
        ['DAYMET', [-120.113, 36.336], 308.150],
        ['GRIDMET', [-120.113, 36.336], 306.969],
        # ['TOPOWX', [-120.113, 36.336], 301.67],
        ['CIMIS_MEDIAN_V1', [-120.113, 36.336], 308.946],
        ['DAYMET_MEDIAN_V0', [-120.113, 36.336], 310.150],
        ['DAYMET_MEDIAN_V1', [-120.113, 36.336], 310.150],
        ['DAYMET_MEDIAN_V2', [-120.113, 36.336], 310.150],
        # Added extra test point where DAYMET median values differ
        # TEST_POINT, [-119.0, 37.5], [-122.1622, 39.1968], [-106.03249, 37.17777]
        ['DAYMET_MEDIAN_V0', [-122.1622, 39.1968], 308.15],
        ['DAYMET_MEDIAN_V1', [-122.1622, 39.1968], 308.4],
        ['DAYMET_MEDIAN_V2', [-122.1622, 39.1968], 308.65],
        ['GRIDMET_MEDIAN_V1', [-120.113, 36.336], 310.436],
        ['TOPOWX_MEDIAN_V0', [-120.113, 36.336], 310.430],
        # Check string/float constant values
        ['305', [-120.113, 36.336], 305],
        [305, [-120.113, 36.336], 305],
    ]
)
def test_Image_tmax_sources(tmax_source, xy, expected, tol=0.001):
    """Test getting Tmax values for a single date at a real point"""
    output_img = ssebop.Image(default_image(), tmax_source=tmax_source).tmax
    output = utils.point_image_value(ee.Image(output_img), xy)
    assert abs(output['tmax'] - expected) <= tol


def test_Image_tmax_sources_exception():
    with pytest.raises(ValueError):
        utils.getinfo(ssebop.Image(default_image(), tmax_source='').tmax)


@pytest.mark.parametrize(
    'tmax_source, xy, expected',
    [
        ['CIMIS', [-120.113, 36.336], 308.946],
        ['DAYMET', [-120.113, 36.336], 310.150],
        ['GRIDMET', [-120.113, 36.336], 310.436],
        # ['TOPOWX', [-106.03249, 37.17777], 298.91],
    ]
)
def test_Image_tmax_fallback(tmax_source, xy, expected, tol=0.001):
    """Test getting Tmax median value when daily doesn't exist

    To test this, move the test date into the future
    """
    input_img = ee.Image.constant([300, 0.8]).rename(['lst', 'ndvi']) \
        .set({'system:index': SCENE_ID,
              'system:time_start': ee.Date(SCENE_DATE).update(2099).millis()})
    output_img = ssebop.Image(input_img, tmax_source=tmax_source).tmax
    output = utils.point_image_value(ee.Image(output_img), xy)
    assert abs(output['tmax'] - expected) <= tol


today_dt = datetime.datetime.today()
@pytest.mark.parametrize(
    'tmax_source, expected',
    [
        ['CIMIS', {'tmax_version': '{}'.format(today_dt.strftime('%Y-%m-%d'))}],
        ['DAYMET', {'tmax_version': '{}'.format(today_dt.strftime('%Y-%m-%d'))}],
        ['GRIDMET', {'tmax_version': '{}'.format(today_dt.strftime('%Y-%m-%d'))}],
        # ['TOPOWX', {'tmax_version': '{}'.format(today_dt.strftime('%Y-%m-%d'))}],
        ['CIMIS_MEDIAN_V1', {'tmax_version': 'median_v1'}],
        ['DAYMET_MEDIAN_V0', {'tmax_version': 'median_v0'}],
        ['DAYMET_MEDIAN_V1', {'tmax_version': 'median_v1'}],
        # ['DAYMET_MEDIAN_V2', {'tmax_version': 'median_v2'}],
        ['GRIDMET_MEDIAN_V1', {'tmax_version': 'median_v1'}],
        ['TOPOWX_MEDIAN_V0', {'tmax_version': 'median_v0'}],
        ['305', {'tmax_version': 'custom_305'}],
        [305, {'tmax_version': 'custom_305'}],
    ]
)
def test_Image_tmax_properties(tmax_source, expected):
    """Test if properties are set on the Tmax image"""
    output = utils.getinfo(
        ssebop.Image(default_image(), tmax_source=tmax_source).tmax)
    assert output['properties']['tmax_source'] == tmax_source
    assert output['properties']['tmax_version'] == expected['tmax_version']


@pytest.mark.parametrize(
    'dt, elev, tcorr, tmax, expected', [[10, 50, 0.98, 310, 0.88]]
)
def test_Image_et_fraction_values(dt, elev, tcorr, tmax, expected, tol=0.0001):
    output_img = ssebop.Image(
        default_image(), dt_source=dt, elev_source=elev,
        tcorr_source=tcorr, tmax_source=tmax).et_fraction
    output = utils.constant_image_value(ee.Image(output_img))
    assert abs(output['et_fraction'] - expected) <= tol
    # assert output['et_fraction'] > 0


@pytest.mark.parametrize(
    # Note: These are made up values
    'lst, ndvi, dt, elev, tcorr, tmax, elr_flag, expected',
    [
        # Test ELR flag
        [305, 0.80, 15, 2000, 0.98, 310, False, 0.9200],
        [305, 0.80, 15, 2000, 0.98, 310, True, 0.8220],
        [315, 0.10, 15, 2000, 0.98, 310, True, 0.1553],
    ]
)
def test_Image_et_fraction_elr_param(lst, ndvi, dt, elev, tcorr, tmax, elr_flag,
                                     expected, tol=0.0001):
    """Test that elr_flag works and changes ETf values"""
    output_img = ssebop.Image(
        default_image(lst=lst, ndvi=ndvi), dt_source=dt, elev_source=elev,
        tcorr_source=tcorr, tmax_source=tmax, elr_flag=elr_flag).et_fraction
    output = utils.constant_image_value(ee.Image(output_img))
    assert abs(output['et_fraction'] - expected) <= tol


# DEADBEEF - Tdiff threshold parameter is being removed
# @pytest.mark.parametrize(
#     'lst, ndvi, dt, elev, tcorr, tmax, tdiff, expected',
#     [
#         [299, 0.80, 15, 50, 0.98, 310, 10, None],
#         [299, 0.80, 15, 50, 0.98, 310, 10, None],
#         [304, 0.10, 15, 50, 0.98, 310, 5, None],
#     ]
# )
# def test_Image_et_fraction_tdiff_param(lst, ndvi, dt, elev, tcorr, tmax, tdiff,
#                                        expected):
#     """Test that ETf is set to nodata for tdiff values outside threshold"""
#     output_img = ssebop.Image(
#         default_image(lst=lst, ndvi=ndvi), dt_source=dt, elev_source=elev,
#         tcorr_source=tcorr, tmax_source=tmax, tdiff_threshold=tdiff).et_fraction
#     output = utils.constant_image_value(ee.Image(output_img))
#     assert output['et_fraction'] is None and expected is None


def test_Image_et_fraction_properties():
    """Test if properties are set on the ETf image"""
    output = utils.getinfo(default_image_obj().et_fraction)
    assert output['bands'][0]['id'] == 'et_fraction'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME


def test_Image_et_fraction_image_tcorr_properties():
    """Test if Tcorr properties are set when tcorr_source is a feature"""
    output = utils.getinfo(
        ssebop.Image(default_image(), tcorr_source='IMAGE').et_fraction)
    assert 'tcorr' not in output['properties'].keys()
    assert 'tcorr_index' not in output['properties'].keys()


def test_Image_et_fraction_feature_tcorr_properties(tol=0.0001):
    """Test if Tcorr properties are set when tcorr_source is a feature"""
    output = utils.getinfo(
        ssebop.Image(default_image(), tcorr_source='FEATURE').et_fraction)
    assert abs(output['properties']['tcorr'] - 0.9752) <= tol
    assert output['properties']['tcorr_index'] == 0


def test_Image_et_reference_properties():
    """Test if properties are set on the ETr image"""
    output =  utils.getinfo(default_image_obj().et_reference)
    assert output['bands'][0]['id'] == 'et_reference'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == COLL_ID + SCENE_ID


def test_Image_et_reference_values(tol=0.0001):
    output = utils.constant_image_value(
        ssebop.Image(default_image(), et_reference_source=10).et_reference)
    assert abs(output['et_reference'] - 10) <= tol


def test_Image_et_properties(tol=0.0001):
    """Test if properties are set on the ET image"""
    output =  utils.getinfo(default_image_obj().et)
    assert output['bands'][0]['id'] == 'et'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == COLL_ID + SCENE_ID


def test_Image_et_values(tol=0.0001):
    output_img = ssebop.Image(
        default_image(ndvi=0.5, lst=308), dt_source=10, elev_source=50,
        tcorr_source=0.98, tmax_source=310, et_reference_source=10).et
    output = utils.constant_image_value(output_img)
    assert abs(output['et'] - 5.8) <= tol


def test_Image_mask_properties():
    """Test if properties are set on the time image"""
    output = utils.getinfo(default_image_obj().mask)
    assert output['bands'][0]['id'] == 'mask'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == COLL_ID + SCENE_ID


def test_Image_mask_values():
    output_img = ssebop.Image(
        default_image(ndvi=0.5, lst=308), dt_source=10, elev_source=50,
        tcorr_source=0.98, tmax_source=310).mask
    output = utils.constant_image_value(output_img)
    assert output['mask'] == 1


def test_Image_time_properties():
    """Test if properties are set on the time image"""
    output = utils.getinfo(default_image_obj().time)
    assert output['bands'][0]['id'] == 'time'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == COLL_ID + SCENE_ID


def test_Image_time_values():
    # The time image is currently being built from the et_fraction image, so all
    #   the ancillary values must be set for the constant_image_value to work.
    output = utils.constant_image_value(ssebop.Image(
        default_image(ndvi=0.5, lst=308), dt_source=10, elev_source=50,
        tcorr_source=0.98, tmax_source=310).time)
    assert output['time'] == SCENE_TIME


def test_Image_calculate_properties():
    """Test if properties are set on the output image"""
    output =  utils.getinfo(default_image_obj().calculate(['ndvi']))
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == COLL_ID + SCENE_ID


def test_Image_calculate_variables_default():
    output = utils.getinfo(default_image_obj().calculate())
    assert {x['id'] for x in output['bands']} == {'et', 'et_reference', 'et_fraction'}


def test_Image_calculate_variables_custom():
    variables = {'ndvi'}
    output = utils.getinfo(default_image_obj().calculate(variables))
    assert {x['id'] for x in output['bands']} == variables


def test_Image_calculate_variables_all():
    variables = {'et', 'et_fraction', 'et_reference', 'mask', 'ndvi', 'time'}
    output = utils.getinfo(default_image_obj().calculate(variables=variables))
    assert {x['id'] for x in output['bands']} == variables


def test_Image_calculate_values(tol=0.0001):
    """Test if the calculate method returns ET, ETr, and ETf values"""
    output_img = ssebop.Image(
            default_image(ndvi=0.5, lst=308), dt_source=10, elev_source=50,
            tcorr_source=0.98, tmax_source=310, et_reference_source=10)\
        .calculate(['et', 'et_reference', 'et_fraction'])
    output = utils.constant_image_value(output_img)
    assert abs(output['et'] - 5.8) <= tol
    assert abs(output['et_reference'] - 10) <= tol
    assert abs(output['et_fraction'] - 0.58) <= tol


def test_Image_calculate_variables_valueerror():
    """Test if calculate method raises a valueerror for invalid variables"""
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj().calculate(['FOO']))


# How should these @classmethods be tested?
def test_Image_from_landsat_c1_toa_default_image():
    """Test that the classmethod is returning a class object"""
    output = ssebop.Image.from_landsat_c1_toa(ee.Image(COLL_ID + SCENE_ID))
    assert type(output) == type(default_image_obj())


@pytest.mark.parametrize(
    'image_id',
    [
        'LANDSAT/LC08/C01/T1_RT_TOA/LC08_044033_20170716',
        'LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716',
        'LANDSAT/LE07/C01/T1_RT_TOA/LE07_044033_20170708',
        'LANDSAT/LE07/C01/T1_TOA/LE07_044033_20170708',
        'LANDSAT/LT05/C01/T1_TOA/LT05_044033_20110716',
    ]
)
def test_Image_from_landsat_c1_toa_image_id(image_id):
    """Test instantiating the class from a Landsat TOA image ID"""
    output = utils.getinfo(ssebop.Image.from_landsat_c1_toa(image_id).ndvi)
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_from_landsat_c1_toa_image():
    """Test instantiating the class from a Landsat TOA ee.Image"""
    image_id = 'LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716'
    output = utils.getinfo(ssebop.Image.from_landsat_c1_toa(
        ee.Image(image_id)).ndvi)
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_from_landsat_c1_toa_et_fraction():
    """Test if ETf can be built for a Landsat TOA image"""
    image_id = 'LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716'
    output = utils.getinfo(ssebop.Image.from_landsat_c1_toa(image_id).et_fraction)
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_from_landsat_c1_toa_et():
    """Test if ET can be built for a Landsat TOA image"""
    image_id = 'LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716'
    output = utils.getinfo(ssebop.Image.from_landsat_c1_toa(
        image_id, et_reference_source='IDAHO_EPSCOR/GRIDMET',
        et_reference_band='etr').et)
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_from_landsat_c1_toa_exception():
    with pytest.raises(Exception):
        utils.getinfo(ssebop.Image.from_landsat_c1_toa(ee.Image('FOO')).ndvi)


def test_Image_from_landsat_c1_sr_default_image():
    """Test that the classmethod is returning a class object"""
    output = ssebop.Image.from_landsat_c1_sr(ee.Image(COLL_ID + SCENE_ID))
    assert type(output) == type(default_image_obj())


@pytest.mark.parametrize(
    'image_id',
    [
        # 'LANDSAT/LC08/C01/T1_RT_SR/LC08_044033_20170716',
        'LANDSAT/LC08/C01/T1_SR/LC08_044033_20170716',
        # 'LANDSAT/LE07/C01/T1_RT_SR/LE07_044033_20170708',
        'LANDSAT/LE07/C01/T1_SR/LE07_044033_20170708',
        'LANDSAT/LT05/C01/T1_SR/LT05_044033_20110716',
    ]
)
def test_Image_from_landsat_c1_sr_image_id(image_id):
    """Test instantiating the class from a Landsat SR image ID"""
    output = utils.getinfo(ssebop.Image.from_landsat_c1_sr(image_id).ndvi)
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_from_landsat_c1_sr_image():
    """Test instantiating the class from a Landsat SR ee.Image"""
    image_id = 'LANDSAT/LC08/C01/T1_SR/LC08_044033_20170716'
    output = utils.getinfo(ssebop.Image.from_landsat_c1_sr(ee.Image(image_id)).ndvi)
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_from_landsat_c1_sr_et_fraction():
    """Test if ETf can be built for a Landsat SR image"""
    image_id = 'LANDSAT/LC08/C01/T1_SR/LC08_044033_20170716'
    output = utils.getinfo(ssebop.Image.from_landsat_c1_sr(image_id).et_fraction)
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_from_landsat_c1_sr_et():
    """Test if ET can be built for a Landsat image"""
    image_id = 'LANDSAT/LC08/C01/T1_SR/LC08_044033_20170716'
    output = utils.getinfo(ssebop.Image.from_landsat_c1_sr(
        image_id, et_reference_source='IDAHO_EPSCOR/GRIDMET',
        et_reference_band='etr').et)
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_from_landsat_c1_sr_exception():
    """Test instantiating the class for an invalid image ID"""
    with pytest.raises(Exception):
        utils.getinfo(ssebop.Image.from_landsat_c1_sr(ee.Image('FOO')).ndvi)


def test_Image_from_landsat_c1_sr_scaling():
    """Test if Landsat SR images images are being scaled"""
    sr_img = ee.Image('LANDSAT/LC08/C01/T1_SR/LC08_044033_20170716')
    input_img = ee.Image.constant([100, 100, 100, 100, 100, 100, 3000.0, 322])\
        .rename(['B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B10', 'pixel_qa'])\
        .set({'SATELLITE': ee.String(sr_img.get('SATELLITE')),
              'system:id': ee.String(sr_img.get('system:id')),
              'system:index': ee.String(sr_img.get('system:index')),
              'system:time_start': ee.Number(sr_img.get('system:time_start'))})
    output = utils.constant_image_value(
        ssebop.Image.from_landsat_c1_sr(input_img).lst)
    # Won't be exact because of emissivity correction
    assert abs(output['lst'] - 300) <= 10


# @pytest.mark.parametrize(
#     'image_id',
#     [
#         'LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716',
#         'LANDSAT/LC08/C01/T1_SR/LC08_044033_20170716',
#     ]
# )
# def test_Image_from_image_id(image_id):
#     """Test instantiating the class using the from_image_id method"""
#     output = utils.getinfo(ssebop.Image.from_image_id(image_id).ndvi)
#     assert output['properties']['system:index'] == image_id.split('/')[-1]
#     assert output['properties']['image_id'] == image_id


def test_Image_from_method_kwargs():
    """Test that the init parameters can be passed through the helper methods"""
    assert ssebop.Image.from_landsat_c1_toa(
        'LANDSAT/LC08/C01/T1_TOA/LC08_042035_20150713',
        elev_source='DEADBEEF')._elev_source == 'DEADBEEF'
    assert ssebop.Image.from_landsat_c1_sr(
        'LANDSAT/LC08/C01/T1_SR/LC08_042035_20150713',
        elev_source='DEADBEEF')._elev_source == 'DEADBEEF'


def test_Image_tcorr_image_values(lst=300, ndvi=0.8, tmax=306, expected=0.9804,
                                  tol=0.0001):
    output = utils.constant_image_value(ssebop.Image(
        default_image(lst=lst, ndvi=ndvi), tmax_source=tmax).tcorr_image)
    assert abs(output['tcorr'] - expected) <= tol


@pytest.mark.parametrize(
    # Note: These are made up values
    'lst, ndvi, tmax, expected',
    [
        [300, 0.69, 306, None],  # NDVI < 0.7
        [269, 0.69, 306, None],  # LST < 270
        # DEADBEEF - Tdiff threshold parameter is being removed
        # [290, 0.20, 306, None],  # Tdiff > 15
        # [307, 0.20, 306, None],  # Tdiff < 0
        # TODO: Add a test for the NDVI smoothing
    ]
)
def test_Image_tcorr_image_nodata(lst, ndvi, tmax, expected):
    output = utils.constant_image_value(ssebop.Image(
        default_image(lst=lst, ndvi=ndvi), tmax_source=tmax).tcorr_image)
    assert output['tcorr'] is None and expected is None


def test_Image_tcorr_image_band_name():
    output = utils.getinfo(default_image_obj().tcorr_image)
    assert output['bands'][0]['id'] == 'tcorr'


def test_Image_tcorr_image_properties(tmax_source='TOPOWX_MEDIAN_V0',
                                      expected={'tmax_version': 'median_v0'}):
    """Test if properties are set on the tcorr image"""
    output = utils.getinfo(default_image_obj().tcorr_image)
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['tmax_source'] == tmax_source
    assert output['properties']['tmax_version'] == expected['tmax_version']


def test_Image_tcorr_stats_constant(expected=0.993548387, tol=0.00000001):
    # The input image needs to be clipped otherwise it is unbounded
    input_image = ee.Image(default_image(ndvi=0.8, lst=308)) \
        .clip(ee.Geometry.Rectangle(-120, 39, -119, 40))
    output = utils.getinfo(
        ssebop.Image(input_image, dt_source=10, elev_source=50,
                     tcorr_source=0.98, tmax_source=310).tcorr_stats)
    assert abs(output['tcorr_p5'] - expected) <= tol
    assert output['tcorr_count'] == 1


@pytest.mark.parametrize(
    'image_id, expected',
    [
        # TopoWX median v0 values
        # Note, these values are slightly different than those in the tcorr
        #   feature collection (commented out values), because the original
        #   values were built with snap points of 0, 0 instead of 15, 15.
        ['LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716',
         {'tcorr_p5': 0.9938986398112951, 'tcorr_count': 2463005}],  # 0.99255676, 971875
        ['LANDSAT/LE07/C01/T1_TOA/LE07_044033_20170708',
         {'tcorr_p5': 0.9819725106056428, 'tcorr_count': 743774}], # 0.98302000, 1700567
        ['LANDSAT/LT05/C01/T1_TOA/LT05_044033_20110716',
         {'tcorr_p5': 0.9569143183692558, 'tcorr_count': 514997}], # 0.95788514, 2315630
    ]
)
def test_Image_tcorr_stats_landsat(image_id, expected, tol=0.00000001):
    output = utils.getinfo(ssebop.Image.from_landsat_c1_toa(
        ee.Image(image_id)).tcorr_stats)
    assert abs(output['tcorr_p5'] - expected['tcorr_p5']) <= tol
    assert output['tcorr_count'] == expected['tcorr_count']
