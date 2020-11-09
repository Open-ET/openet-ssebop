import datetime
import pprint

import ee
import pytest

import openet.ssebop as ssebop
import openet.ssebop.utils as utils
# TODO: import utils from openet.core
# import openet.core.utils as utils


COLL_ID = 'LANDSAT/LC08/C01/T1_TOA'
SCENE_ID = 'LC08_042035_20150713'
SCENE_DT = datetime.datetime.strptime(SCENE_ID[-8:], '%Y%m%d')
SCENE_DATE = SCENE_DT.strftime('%Y-%m-%d')
SCENE_DOY = int(SCENE_DT.strftime('%j'))
# SCENE_TIME = utils.millis(SCENE_DT)
SCENE_TIME = 1436812419150
SCENE_POINT = (-119.5, 36.0)
TEST_POINT = (-119.44252382373145, 36.04047742246546)

# SCENE_TIME = utils.getinfo(ee.Date(SCENE_DATE).millis())
# SCENE_POINT = (-119.44252382373145, 36.04047742246546)
# SCENE_POINT = utils.getinfo(
#     ee.Image(f'{COLL_ID}/{SCENE_ID}').geometry().centroid())['coordinates']


# Should these be test fixtures instead?
# I'm not sure how to make them fixtures and allow input parameters
def toa_image(red=0.1, nir=0.9, bt=305):
    """Construct a fake Landsat 8 TOA image with renamed bands"""
    mask_img = ee.Image(f'{COLL_ID}/{SCENE_ID}').select(['B3']).multiply(0)
    return ee.Image([mask_img.add(red), mask_img.add(nir), mask_img.add(bt)]) \
        .rename(['red', 'nir', 'tir'])\
        .set({
            'system:time_start': SCENE_TIME,
            'k1_constant': ee.Number(607.76),
            'k2_constant': ee.Number(1260.56),
        })
    # return ee.Image.constant([red, nir, bt])\
    #     .rename(['red', 'nir', 'lst']) \
    #     .set({
    #         'system:time_start': ee.Date(SCENE_DATE).millis(),
    #         'k1_constant': ee.Number(607.76),
    #         'k2_constant': ee.Number(1260.56),
    #     })


def default_image(lst=305, ndvi=0.8):
    # First construct a fake 'prepped' input image
    mask_img = ee.Image(f'{COLL_ID}/{SCENE_ID}').select(['B3']).multiply(0)
    return ee.Image([mask_img.add(lst), mask_img.add(ndvi)]) \
        .rename(['lst', 'ndvi']) \
        .set({
            'system:index': SCENE_ID,
            'system:time_start': SCENE_TIME,
            'system:id': f'{COLL_ID}/{SCENE_ID}',
        })
    # return ee.Image.constant([lst, ndvi]).rename(['lst', 'ndvi']) \
    #     .set({
    #         'system:index': SCENE_ID,
    #         'system:time_start': ee.Date(SCENE_DATE).millis(),
    #         'system:id': f'{COLL_ID}/{SCENE_ID}',
    #     })


# Setting et_reference_source and et_reference_band on the default image to
#   simplify testing but these do not have defaults in the Image class init
def default_image_args(lst=305, ndvi=0.8,
                       # et_reference_source='IDAHO_EPSCOR/GRIDMET',
                       et_reference_source=9.5730,
                       et_reference_band='etr',
                       et_reference_factor=1,
                       et_reference_resample='nearest',
                       dt_source=18,
                       elev_source=67,
                       elr_flag=False,
                       tcorr_source=0.9744,
                       tmax_source=310.15,
                       dt_resample='nearest',
                       tmax_resample='nearest',
                       tcorr_resample='nearest',
                       et_fraction_type='alfalfa',
                       ):
    return {
        'image': default_image(lst=lst, ndvi=ndvi),
        'et_reference_source': et_reference_source,
        'et_reference_band': et_reference_band,
        'et_reference_factor': et_reference_factor,
        'et_reference_resample': et_reference_resample,
        'dt_source': dt_source,
        'elev_source': elev_source,
        'elr_flag': elr_flag,
        'tcorr_source': tcorr_source,
        'tmax_source': tmax_source,
        'dt_resample': dt_resample,
        'tmax_resample': tmax_resample,
        'tcorr_resample': tcorr_resample,
        'et_fraction_type': et_fraction_type,
    }


def default_image_obj(lst=305, ndvi=0.8,
                      # et_reference_source='IDAHO_EPSCOR/GRIDMET',
                      et_reference_source=9.5730,
                      et_reference_band='etr',
                      et_reference_factor=1,
                      et_reference_resample='nearest',
                      dt_source=18,
                      elev_source=67,
                      elr_flag=False,
                      tcorr_source=0.9744,
                      tmax_source=310.15,
                      dt_resample='nearest',
                      tmax_resample='nearest',
                      tcorr_resample='nearest',
                      et_fraction_type='alfalfa',
                      ):
    return ssebop.Image(**default_image_args(
        lst=lst, ndvi=ndvi,
        et_reference_source=et_reference_source,
        et_reference_band=et_reference_band,
        et_reference_factor=et_reference_factor,
        et_reference_resample=et_reference_resample,
        dt_source=dt_source,
        elev_source=elev_source,
        elr_flag=elr_flag,
        tcorr_source=tcorr_source,
        tmax_source=tmax_source,
        dt_resample=dt_resample,
        tmax_resample=tmax_resample,
        tcorr_resample=tcorr_resample,
        et_fraction_type=et_fraction_type,
    ))


def test_Image_init_default_parameters():
    m = ssebop.Image(default_image())
    assert m.et_reference_source == None
    assert m.et_reference_band == None
    assert m.et_reference_factor == None
    assert m.et_reference_resample == None
    assert m._dt_source == 'DAYMET_MEDIAN_V2'
    assert m._elev_source == 'SRTM'
    assert m._tcorr_source == 'DYNAMIC'
    assert m._tmax_source == 'DAYMET_MEDIAN_V2'
    assert m._elr_flag == False
    assert m._dt_min == 5
    assert m._dt_max == 25
    assert m._dt_resample == 'bilinear'
    assert m._tmax_resample == 'bilinear'
    assert m._tcorr_resample == 'nearest'


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
    assert utils.getinfo(m._start_date)['value'] == utils.millis(SCENE_DT)
    assert utils.getinfo(m._end_date)['value'] == (
        utils.millis(SCENE_DT) + 24 * 3600 * 1000)
    # assert utils.getinfo(m._end_date)['value'] == utils.millis(
    #     SCENE_DT + datetime.timedelta(days=1))
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
    assert default_image_obj(elr_flag='FALSE')._elr_flag == False
    assert default_image_obj(elr_flag='true')._elr_flag == True
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj(elr_flag='FOO')._elr_flag)


def test_Image_ndvi_properties():
    """Test if properties are set on the NDVI image"""
    output = utils.getinfo(default_image_obj().ndvi)
    assert output['bands'][0]['id'] == 'ndvi'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


def test_Image_lst_properties():
    """Test if properties are set on the LST image"""
    output = utils.getinfo(default_image_obj().lst)
    assert output['bands'][0]['id'] == 'lst'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


@pytest.mark.parametrize(
    'elev_source, xy, expected',
    [
        ['SRTM', TEST_POINT, 67.0],
        ['SRTM', [-122.1622, 39.1968], 18.0],
        ['ASSET', [-106.03249, 37.17777], 2369.0],
        ['GTOPO', [-106.03249, 37.17777], 2369.0],
        ['NED', [-106.03249, 37.17777], 2364.351],
        ['SRTM', [-106.03249, 37.17777], 2362.0],
        # Check string/float constant values
        ['2364.351', [-106.03249, 37.17777], 2364.351],
        [2364.351, [-106.03249, 37.17777], 2364.351],
        # Check custom images
        ['projects/earthengine-legacy/assets/projects/usgs-ssebop/srtm_1km',
         [-106.03249, 37.17777], 2369.0],
        # ['projects/assets/usgs-ssebop/srtm_1km', [-106.03249, 37.17777], 2369.0],
        # DEADBEEF - We should allow any EE image (not just users/projects)
        # ['USGS/NED', [-106.03249, 37.17777], 2364.35],
    ]
)
def test_Image_elev_sources(elev_source, xy, expected, tol=0.001):
    """Test getting elevation values for a single date at a real point"""
    output = utils.point_image_value(default_image_obj(
        elev_source=elev_source).elev, xy)
    assert abs(output['elev'] - expected) <= tol


def test_Image_elev_sources_exception():
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj(elev_source='').elev)


def test_Image_elev_band_name():
    output = utils.getinfo(default_image_obj().elev)['bands'][0]['id']
    assert output == 'elev'


@pytest.mark.parametrize(
    'dt_source, doy, xy, expected',
    [
        ['DAYMET_MEDIAN_V0', SCENE_DOY, TEST_POINT, 19.4612],
        ['DAYMET_MEDIAN_V0', 194, [-120.113, 36.336], 19.262],
        ['DAYMET_MEDIAN_V1', SCENE_DOY, TEST_POINT, 18],
        ['DAYMET_MEDIAN_V1', 194, [-120.113, 36.336], 18],
        ['DAYMET_MEDIAN_V1', 194, [-119.0, 37.5], 21],
        ['DAYMET_MEDIAN_V2', SCENE_DOY, TEST_POINT, 19.5982],
        ['DAYMET_MEDIAN_V2', 194, [-120.113, 36.336], 19.4762],
        ['DAYMET_MEDIAN_V2', 194, [-119.0, 37.5], 25],
    ]
)
def test_Image_dt_source_median(dt_source, doy, xy, expected, tol=0.001):
    """Test getting median dT values for a single date at a real point"""
    m = default_image_obj(dt_source=dt_source)
    m._doy = doy
    output = utils.point_image_value(ee.Image(m.dt), xy)
    assert abs(output['dt'] - expected) <= tol


@pytest.mark.parametrize(
    'dt_source, doy, xy, expected',
    [
        ['DAYMET_MEDIAN_V0', 1, [-120.113, 36.336], 5],
        ['DAYMET_MEDIAN_V0', 194, [-119.0, 37.5], 25],
        ['DAYMET_MEDIAN_V1', 1, [-120.113, 36.336], 5],
        # ['DAYMET_MEDIAN_V1', 194, [-119.0, 37.5], 25],
        ['DAYMET_MEDIAN_V2', 1, [-96.6255, 43.7359], 5],
        ['DAYMET_MEDIAN_V2', 194, [-119.0, 37.5], 25],
    ]
)
def test_Image_dt_source_clamping(dt_source, doy, xy, expected, tol=0.001):
    """Check that dT values are clamped to dt_min and dt_max (5, 25)"""
    m = default_image_obj(dt_source=dt_source)
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
    """Test getting constant dT values for a single date at a real point"""
    m = default_image_obj(dt_source=dt_source)
    output = utils.point_image_value(ee.Image(m.dt), xy)
    assert abs(output['dt'] - expected) <= tol


@pytest.mark.parametrize(
    'dt_source, elev, date, xy, expected',
    [
        ['CIMIS', 18, '2017-07-16', [-122.1622, 39.1968], 17.1013],
        ['DAYMET', 18, '2017-07-16', [-122.1622, 39.1968], 13.5525],
        ['GRIDMET', 18, '2017-07-16', [-122.1622, 39.1968], 18.1700],
        # ['GRIDMET', 18, '2017-07-16', [-122.1622, 39.1968], 18.1711],
        # ['CIMIS', 67, SCENE_DATE, TEST_POINT, 17.10647],
        # ['DAYMET', 67, SCENE_DATE, TEST_POINT, 12.99047],
        # ['GRIDMET', 67, SCENE_DATE, TEST_POINT, 17.79065],
    ]
)
def test_Image_dt_source_calculated(dt_source, elev, date, xy, expected, tol=0.001):
    """Test getting calculated dT values for a single date at a real point"""
    m = default_image_obj(dt_source=dt_source, elev_source=elev)
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
        utils.getinfo(default_image_obj(dt_source='').dt)


@pytest.mark.parametrize(
    'doy, dt_min, dt_max',
    [
        [1, 6, 25],
        [200, 6, 25],
        [200, 10, 15],
    ]
)
def test_Image_dt_clamping(doy, dt_min, dt_max):
    m = default_image_obj(dt_source='DAYMET_MEDIAN_V1')
    m._dt_min = dt_min
    m._dt_max = dt_max
    m._doy = doy
    reducer = ee.Reducer.min().combine(ee.Reducer.max(), sharedInputs=True)
    output = utils.getinfo(ee.Image(m.dt)\
        .reduceRegion(reducer=reducer, scale=1000, tileScale=4, maxPixels=2E8,
                      geometry=ee.Geometry.Rectangle(-125, 25, -65, 50)))
    assert output['dt_min'] >= dt_min
    assert output['dt_max'] <= dt_max


@pytest.mark.parametrize(
    'tmax_source, xy, expected',
    [
        ['DAYMET_MEDIAN_V2', TEST_POINT, 310.15],
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
    m = default_image_obj(tmax_source=tmax_source)
    output = utils.point_image_value(ee.Image(m.tmax), xy)
    assert abs(output['tmax'] - expected) <= tol


def test_Image_tmax_sources_exception():
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj(tmax_source='').tmax)


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
    Tmax collections are filtered based on start_date and end_date
    """
    m = default_image_obj(tmax_source=tmax_source)
    m._start_date = ee.Date.fromYMD(2099, 7, 1)
    m._end_date = ee.Date.fromYMD(2099, 7, 2)
    output = utils.point_image_value(ee.Image(m.tmax), xy)
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
        ['DAYMET_MEDIAN_V2', {'tmax_version': 'median_v2'}],
        ['GRIDMET_MEDIAN_V1', {'tmax_version': 'median_v1'}],
        ['TOPOWX_MEDIAN_V0', {'tmax_version': 'median_v0'}],
        ['305', {'tmax_version': 'custom_305'}],
        [305, {'tmax_version': 'custom_305'}],
    ]
)
def test_Image_tmax_properties(tmax_source, expected):
    """Test if properties are set on the Tmax image"""
    output = utils.getinfo(default_image_obj(tmax_source=tmax_source).tmax)
    assert output['properties']['tmax_source'] == tmax_source
    assert output['properties']['tmax_version'] == expected['tmax_version']


def test_Image_tcorr_stats_constant(tcorr=0.993548387, count=41479998,
                                    tol=0.00000001):
    output = utils.getinfo(default_image_obj(
        ndvi=0.8, lst=308, dt_source=10, elev_source=50,
        tcorr_source=0.98, tmax_source=310).tcorr_stats)
    assert abs(output['tcorr_value'] - tcorr) <= tol
    assert output['tcorr_count'] == count


# NOTE: Testing tcorr_stats() here is a little out of order, but it is only a
#   function of the tmax_source and is used by the other tcorr functions
# NOTE: These values seem to change by small amounts for no reason
@pytest.mark.parametrize(
    'image_id, tmax_source, expected',
    [
        # TOPOWX_MEDIAN_V0
        ['LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716', 'TOPOWX_MEDIAN_V0',
         {'tcorr_value': 0.9938986398112951, 'tcorr_count': 2463129}], # 2463133
        ['LANDSAT/LE07/C01/T1_TOA/LE07_044033_20170708', 'TOPOWX_MEDIAN_V0',
         {'tcorr_value': 0.9819725106056428, 'tcorr_count': 743774}],
        ['LANDSAT/LT05/C01/T1_TOA/LT05_044033_20110716', 'TOPOWX_MEDIAN_V0',
         {'tcorr_value': 0.9569143183692558, 'tcorr_count': 514997}], # 514981
        # DAYMET_MEDIAN_V2
        ['LANDSAT/LC08/C01/T1_TOA/LC08_042035_20150713', 'DAYMET_MEDIAN_V2',
         {'tcorr_value': 0.9743747113938074, 'tcorr_count': 761231}],
        ['LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716', 'DAYMET_MEDIAN_V2',
         {'tcorr_value': 0.9880444668266360, 'tcorr_count': 2463129}],
        ['LANDSAT/LE07/C01/T1_TOA/LE07_044033_20170708', 'DAYMET_MEDIAN_V2',
         {'tcorr_value': 0.9817142973468178, 'tcorr_count': 743774}],
        ['LANDSAT/LT05/C01/T1_TOA/LT05_044033_20110716', 'DAYMET_MEDIAN_V2',
         {'tcorr_value': 0.9520545648466826, 'tcorr_count': 514997}],
        ['LANDSAT/LC08/C01/T1_TOA/LC08_042035_20161206', 'DAYMET_MEDIAN_V2',
         {'tcorr_value': 0.9907451827474001, 'tcorr_count': 11}],
    ]
)
def test_Image_tcorr_stats_landsat(image_id, tmax_source, expected,
                                   tol=0.0000001):
    output = utils.getinfo(ssebop.Image.from_landsat_c1_toa(
        ee.Image(image_id), tmax_source=tmax_source,
        tmax_resample='nearest').tcorr_stats)
    assert abs(output['tcorr_value'] - expected['tcorr_value']) <= tol
    assert abs(output['tcorr_count'] == expected['tcorr_count']) <= 1
    # assert (abs(output['tcorr_count'] == expected['tcorr_count']) /
    #         expected['tcorr_count']) <= 0.0000001


def test_Image_tcorr_image_values(lst=300, ndvi=0.8, tmax=306, expected=0.9804,
                                  tol=0.0001):
    output_img = default_image_obj(
        lst=lst, ndvi=ndvi, tmax_source=tmax).tcorr_image
    output = utils.point_image_value(output_img, TEST_POINT)
    assert abs(output['tcorr'] - expected) <= tol


@pytest.mark.parametrize(
    # Note: These are made up values
    'lst, ndvi, tmax, expected',
    [
        [300, 0.69, 306, None],  # NDVI < 0.7
        [269, 0.69, 306, None],  # LST < 270
        # TODO: Add a test for the NDVI smoothing
    ]
)
def test_Image_tcorr_image_nodata(lst, ndvi, tmax, expected):
    output = utils.constant_image_value(default_image_obj(
        lst=lst, ndvi=ndvi, tmax_source=tmax).tcorr_image)
    assert output['tcorr'] is None and expected is None


def test_Image_tcorr_image_band_name():
    output = utils.getinfo(default_image_obj().tcorr_image)
    assert output['bands'][0]['id'] == 'tcorr'


def test_Image_tcorr_image_properties(tmax_source='DAYMET_MEDIAN_V2',
                                      expected={'tmax_version': 'median_v2'}):
    """Test if properties are set on the tcorr image"""
    output = utils.getinfo(default_image_obj(
        tmax_source='DAYMET_MEDIAN_V2').tcorr_image)
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['tmax_source'] == tmax_source
    assert output['properties']['tmax_version'] == expected['tmax_version']


@pytest.mark.parametrize(
    'tcorr_source, tmax_source, image_id, expected',
    [
        ['DYNAMIC', 'DAYMET_MEDIAN_V2',
         'LANDSAT/LC08/C01/T1_TOA/LC08_042035_20150713',
         [0.9738927482041165, 0]],
        ['DYNAMIC', 'DAYMET_MEDIAN_V2',
        'LANDSAT/LC08/C01/T1_TOA/LC08_042035_20161206',
         [0.9798917542625591, 1]],
    ]
)
def test_Image_tcorr_dynamic_source(tcorr_source, tmax_source, image_id,
                                    expected, tol=0.000001):
    """Test getting Tcorr value and index for a single date at a real point"""
    tcorr_img = ssebop.Image.from_landsat_c1_toa(
        ee.Image(image_id), tcorr_source=tcorr_source,
        tmax_source=tmax_source, tmax_resample='nearest').tcorr
    tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
    index = utils.getinfo(tcorr_img.get('tcorr_index'))
    assert abs(tcorr['tcorr'] - expected[0]) <= tol
    assert index == expected[1]


# TODO: Modify these tests for the DYNAMIC tcorr source
#   to check that the monthly and annual fallback collections are used
# @pytest.mark.parametrize(
#     'tcorr_source, tmax_source, scene_id, expected',
#     [
#         # TOPOWX_MEDIAN_V0
#         ['IMAGE', 'TOPOWX_MEDIAN_V0', 'LC08_042035_20150713', [0.9752, 0]],
#         ['IMAGE_DAILY', 'TOPOWX_MEDIAN_V0', 'LC08_042035_20150713', [0.9752, 0]],
#         ['IMAGE_MONTHLY', 'TOPOWX_MEDIAN_V0', 'LC08_042035_20150713', [0.9723, 1]],
#         ['IMAGE_ANNUAL', 'TOPOWX_MEDIAN_V0', 'LC08_042035_20150713', [0.9786, 2]],
#         ['IMAGE_DEFAULT', 'TOPOWX_MEDIAN_V0', 'LC08_042035_20150713', [0.978, 3]],
#         # DAYMET_MEDIAN_V2
#         ['IMAGE', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713', [0.9744, 0]],
#         ['IMAGE_DAILY', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713', [0.9744, 0]],
#         ['IMAGE_MONTHLY', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713', [0.9756, 1]],
#         ['IMAGE_ANNUAL', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713', [0.9829, 2]],
#         ['IMAGE_DEFAULT', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713', [0.978, 3]],
#     ]
# )
# def test_Image_tcorr_image_source(tcorr_source, tmax_source, scene_id,
#                                   expected, tol=0.0001):
#     """Test getting Tcorr value and index for a single date at a real point"""
#     scene_date = datetime.datetime.strptime(scene_id.split('_')[-1], '%Y%m%d') \
#         .strftime('%Y-%m-%d')
#     input_image = ee.Image.constant(1).set({
#         'system:time_start': ee.Date(scene_date).millis()})
#     tcorr_img, index_img = ssebop.Image(
#         input_image, tcorr_source=tcorr_source, tmax_source=tmax_source).tcorr
#
#     # Tcorr images are constant images and need to be queried at a point
#     tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
#     index = utils.point_image_value(index_img, SCENE_POINT)
#     assert abs(tcorr['tcorr'] - expected[0]) <= tol
#     assert index['index'] == expected[1]
#
#
# def test_Image_tcorr_image_month(expected=[0.9723, 1], tol=0.0001):
#     """Test getting monthly Tcorr from composite when daily is missing"""
#     # Setting start date to well before beginning of daily Tcorr images
#     # 1980-07-04 should have the same cycle_day value as previous tests
#     input_image = ee.Image.constant(1).set({
#         'system:time_start': ee.Date('1980-07-04').millis()})
#     m = ssebop.Image(input_image, tcorr_source='IMAGE',
#                      tmax_source='TOPOWX_MEDIAN_V0')
#     tcorr_img, index_img = m.tcorr
#     tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
#     index = utils.point_image_value(index_img, SCENE_POINT)
#     assert abs(tcorr['tcorr'] - expected[0]) <= tol
#     assert index['index'] == expected[1]
#
#
# def test_Image_tcorr_image_annual(expected=[0.9786, 2], tol=0.0001):
#     """Test getting annual Tcorr from composite when monthly/daily are missing"""
#     input_image = ee.Image.constant(1).set({
#         'system:time_start': ee.Date('1980-07-04').millis()})
#     m = ssebop.Image(input_image, tcorr_source='IMAGE',
#                      tmax_source='TOPOWX_MEDIAN_V0')
#     m._month = ee.Number(9999)
#     tcorr_img, index_img = m.tcorr
#     tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
#     index = utils.point_image_value(index_img, SCENE_POINT)
#     assert abs(tcorr['tcorr'] - expected[0]) <= tol
#     assert index['index'] == expected[1]
#
#
# def test_Image_tcorr_image_default(expected=[0.978, 3], tol=0.0001):
#     """Test getting default Tcorr from composite"""
#     input_image = ee.Image.constant(1).set({
#         'system:time_start': ee.Date('1980-07-04').millis()})
#     m = ssebop.Image(input_image, tcorr_source='IMAGE',
#                      tmax_source='TOPOWX_MEDIAN_V0')
#     m._month = ee.Number(9999)
#     m._cycle_day = ee.Number(9999)
#     tcorr_img, index_img = m.tcorr
#     tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
#     index = utils.point_image_value(index_img, SCENE_POINT)
#     assert abs(tcorr['tcorr'] - expected[0]) <= tol
#     assert index['index'] == expected[1]


# CGM - Only checking that for a small area a consistent Tcorr value is returned
#   for each of the GRIDDED source options
@pytest.mark.parametrize(
    'tcorr_source, tmax_source, image_id, clip, xy, expected',
    [
        ['GRIDDED', 'DAYMET_MEDIAN_V2',
         'LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716',
         [600000, 4270000, 625000, 4285000], [612500, 4277500],
         [0.991065976970446, 0]],
    ]
)
def test_Image_tcorr_gridded_source(tcorr_source, tmax_source, image_id,
                                    clip, xy, expected, tol=0.000001):
    """Test getting the gridded Tcorr values"""
    image_crs = ee.Image(image_id).select([3]).projection().crs()
    clip_geom = ee.Geometry.Rectangle(clip, image_crs, False)
    point_xy = ee.Geometry.Point(xy, image_crs).transform('EPSG:4326', 1)\
        .coordinates().getInfo()
    tcorr_img = ssebop.Image.from_landsat_c1_toa(
        ee.Image(image_id).clip(clip_geom), tcorr_source=tcorr_source,
        tmax_source=tmax_source, tmax_resample='nearest').tcorr
    tcorr = utils.point_image_value(tcorr_img, point_xy)
    index = utils.getinfo(tcorr_img.get('tcorr_index'))
    assert abs(tcorr['tcorr'] - expected[0]) <= tol
    assert index == expected[1]


@pytest.mark.parametrize(
    'tcorr_source, tmax_source, image_id, clip, xy, expected',
    [
        ['GRIDDED', 'DAYMET_MEDIAN_V2',
         'LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716',
         [600000, 4270000, 625000, 4285000], [612500, 4277500],
         [0.991065976970446, 18, 0]],
    ]
)
def test_Image_tcorr_gridded_method(tcorr_source, tmax_source, image_id,
                                    clip, xy, expected, tol=0.000001):
    """Test the tcorr_gridded method directly

    Note that this method returns separate tcorr and  quality bands
    """
    image_crs = ee.Image(image_id).select([3]).projection().crs()
    clip_geom = ee.Geometry.Rectangle(clip, image_crs, False)
    point_xy = ee.Geometry.Point(xy, image_crs).transform('EPSG:4326', 1)\
        .coordinates().getInfo()
    tcorr_img = ssebop.Image.from_landsat_c1_toa(
        ee.Image(image_id).clip(clip_geom), tcorr_source=tcorr_source,
        tmax_source=tmax_source, tmax_resample='nearest').tcorr_gridded
    tcorr = utils.point_image_value(tcorr_img, point_xy)
    index = utils.getinfo(tcorr_img.get('tcorr_index'))
    assert abs(tcorr['tcorr'] - expected[0]) <= tol
    assert abs(tcorr['quality'] - expected[1]) <= tol
    assert index == expected[2]


@pytest.mark.parametrize(
    'tcorr_source, tmax_source, image_id, clip, xy, expected',
    [
        ['GRIDDED', 'DAYMET_MEDIAN_V2',
         'LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716',
         [600000, 4270000, 625000, 4285000], [612500, 4277500],
         [0.9901338160695725, 1]],
    ]
)
def test_Image_tcorr_gridded_cold_method(tcorr_source, tmax_source, image_id,
                                         clip, xy, expected, tol=0.000001):
    """Test the tcorr_gridded_cold method directly"""
    image_crs = ee.Image(image_id).select([3]).projection().crs()
    clip_geom = ee.Geometry.Rectangle(clip, image_crs, False)
    point_xy = ee.Geometry.Point(xy, image_crs).transform('EPSG:4326', 1)\
        .coordinates().getInfo()
    tcorr_img = ssebop.Image.from_landsat_c1_toa(
        ee.Image(image_id).clip(clip_geom), tcorr_source=tcorr_source,
        tmax_source=tmax_source, tmax_resample='nearest').tcorr_gridded_cold
    tcorr = utils.point_image_value(tcorr_img, point_xy)
    index = utils.getinfo(tcorr_img.get('tcorr_index'))
    assert abs(tcorr['tcorr'] - expected[0]) <= tol
    assert index == expected[1]


# @pytest.mark.parametrize(
#     'tcorr_source, tmax_source, image_id, clip, xy, expected',
#     [
#         ['GRIDDED', 'DAYMET_MEDIAN_V2',
#          'LANDSAT/LC08/C01/T1_TOA/LC08_041032_20170711',
#          [510000, 4440000, 560000, 4470000],
#          [515000 + 2500, 4445000 + 2500],
#          sum([0.9841927, 0.9841927, 0.9841927, 0.9823752]) * 0.25],
#         ['GRIDDED', 'DAYMET_MEDIAN_V2',
#          'LANDSAT/LC08/C01/T1_TOA/LC08_041032_20170711',
#          [510000, 4440000, 560000, 4470000],
#          [530000 + 2500, 4460000 + 2500],
#          sum([0.9850194, 0.9814665, 0.9814665, 0.9823752]) * 0.25],
#         ['GRIDDED', 'DAYMET_MEDIAN_V2',
#          'LANDSAT/LC08/C01/T1_TOA/LC08_041032_20170711',
#          [510000, 4440000, 560000, 4470000],
#          [540000 + 2500, 4460000 + 2500],
#          sum([0.9779135, 0.9814665, 0.9814665, 0.9823752]) * 0.25],
#     ]
# )
# def test_Image_tcorr_gridded_values(tcorr_source, tmax_source, image_id,
#                                     clip, xy, expected, tol=0.000001):
#     """Test getting the gridded Tcorr values"""
#     image_crs = ee.Image(image_id).select([3]).projection().crs()
#     print(image_crs.getInfo())
#     clip_geom = ee.Geometry.Rectangle(clip, image_crs, False)
#     point_xy = ee.Geometry.Point(xy, image_crs).transform('EPSG:4326', 1)\
#         .coordinates().getInfo()
#     print(point_xy)
#     tcorr_img = ssebop.Image.from_landsat_c1_toa(
#         ee.Image(image_id).clip(clip_geom), tcorr_source=tcorr_source,
#         tmax_source=tmax_source, tmax_resample='nearest').tcorr
#     tcorr = utils.point_image_value(tcorr_img, point_xy)
#     index = utils.getinfo(tcorr_img.get('tcorr_index'))
#     assert abs(tcorr['tcorr'] - expected) <= tol
#     # CGM - Add check for tcorr_coarse_count, should be 3 for these 3 tests


# TODO: Add check for Tcorr coarse count property


# NOTE: Support for reading the scene Tcorr functions will likely be deprecated
@pytest.mark.parametrize(
    'tcorr_source, tmax_source, scene_id, expected',
    [
        # DAYMET_MEDIAN_V2 "static" assets
        ['SCENE', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713',
         [0.9743747113938074, 0]],
        ['SCENE_DAILY', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713',
         [0.9743747113938074, 0]],
        ['SCENE_MONTHLY', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713',
         [0.9700734316155846, 1]],
        ['SCENE_MONTHLY', 'DAYMET_MEDIAN_V2', 'LC08_042035_20161206',
         [0.9798917542625591, 1]],
        ['SCENE_ANNUAL', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713',
         [0.9762643456613403, 2]],
        ['SCENE_DEFAULT', 'DAYMET_MEDIAN_V2', 'LC08_042035_20150713',
         [0.978, 3]],
    ]
)
def test_Image_tcorr_scene_source(tcorr_source, tmax_source, scene_id,
                                  expected, tol=0.000001):
    """Test getting Tcorr value and index for a single date at a real point"""
    scene_date = datetime.datetime.strptime(scene_id.split('_')[-1], '%Y%m%d') \
        .strftime('%Y-%m-%d')
    input_image = ee.Image.constant(1).set({
        'system:index': scene_id,
        'system:time_start': ee.Date(scene_date).millis()
    })
    tcorr_img = ssebop.Image(
        input_image, tcorr_source=tcorr_source,
        tmax_source=tmax_source, tmax_resample='nearest').tcorr

    # Tcorr images are constant images and need to be queried at a point
    tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
    index = utils.getinfo(tcorr_img.get('tcorr_index'))
    assert abs(tcorr['tcorr'] - expected[0]) <= tol
    assert index == expected[1]


def test_Image_tcorr_scene_month(expected=[0.9700734316155846, 1], tol=0.000001):
    """Test getting monthly Tcorr from composite when daily is missing"""
    # Setting start date to well before beginning of daily Tcorr images
    input_image = ee.Image.constant(1).set({
        'system:index': 'LC08_042035_20150713',
        'system:time_start': ee.Date('1980-07-13').millis()})
    m = ssebop.Image(
        input_image, tcorr_source='SCENE', tmax_source='DAYMET_MEDIAN_V2',
        tmax_resample='nearest')
    tcorr_img = m.tcorr
    tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
    index = utils.getinfo(tcorr_img.get('tcorr_index'))
    assert abs(tcorr['tcorr'] - expected[0]) <= tol
    assert index == expected[1]


def test_Image_tcorr_scene_annual(expected=[0.9762643456613403, 2], tol=0.000001):
    """Test getting annual Tcorr from composite when monthly/daily are missing"""
    input_image = ee.Image.constant(1).set({
        'system:index': 'LC08_042035_20150713',
        'system:time_start': ee.Date('1980-07-13').millis()})
    m = ssebop.Image(
        input_image, tcorr_source='SCENE', tmax_source='DAYMET_MEDIAN_V2',
        tmax_resample='nearest')
    m._month = ee.Number(9999)
    tcorr_img = m.tcorr
    tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
    index = utils.getinfo(tcorr_img.get('tcorr_index'))
    assert abs(tcorr['tcorr'] - expected[0]) <= tol
    assert index == expected[1]


# CGM - I'm not quite sure how to test this condition
# def test_Image_tcorr_scene_default(expected=[0.978, 3], tol=0.0001):
#     """Test getting default Tcorr from composite"""
#     input_image = ee.Image.constant(1).set({
#         'system:index': 'LC08_042035_20150713',
#         'system:time_start': ee.Date('1980-07-13').millis()})
#     m = ssebop.Image(input_image, tcorr_source='SCENE',
#                      tmax_source='DAYMET_MEDIAN_V2')
#     m._month = ee.Number(9999)
#     tcorr_img = m.tcorr
#     tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
#     index = utils.getinfo(tcorr_img.get('tcorr_index'))
#     assert abs(tcorr['tcorr'] - expected[0]) <= tol
#     assert index['index'] == expected[1]


def test_Image_tcorr_scene_daily():
    """Tcorr should be masked for date outside range with SCENE_DAILY"""
    input_image = ee.Image.constant(1).set({
        'system:index': 'LC08_042035_20150713',
        'system:time_start': ee.Date('1980-07-04').millis()})
    m = ssebop.Image(input_image, tcorr_source='SCENE_DAILY',
                     tmax_source='DAYMET_MEDIAN_V2')
    tcorr_img = m.tcorr
    tcorr = utils.point_image_value(tcorr_img, SCENE_POINT)
    index = utils.getinfo(tcorr_img.get('tcorr_index'))
    assert tcorr['tcorr'] is None
    assert index == 9


@pytest.mark.parametrize(
    'tcorr_src',
    [
        '',
        'DEADBEEF',
        'SCENE_DEADBEEF',
        'FEATURE',
        'IMAGE',
    ]
)
def test_Image_tcorr_sources_exception(tcorr_src):
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj(tcorr_source=tcorr_src).tcorr)


@pytest.mark.parametrize(
    'tcorr_src, tmax_src',
    [
        ['GRIDDED', 'DEADBEEF'],
        ['DYNAMIC', 'DEADBEEF'],
        ['SCENE', 'DEADBEEF'],
    ]
)
def test_Image_tcorr_tmax_sources_exception(tcorr_src, tmax_src):
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj(
            tcorr_source=tcorr_src, tmax_source=tmax_src).tcorr)


# TODO: Add test for when there is no Tcorr image for the Landsat date


def test_Image_et_fraction_properties():
    """Test if properties are set on the ETf image"""
    output = utils.getinfo(default_image_obj().et_fraction)
    assert output['bands'][0]['id'] == 'et_fraction'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME


@pytest.mark.parametrize(
    'dt, elev, tcorr, tmax, expected', [[10, 50, 0.98, 310, 0.88]]
)
def test_Image_et_fraction_values(dt, elev, tcorr, tmax, expected, tol=0.0001):
    output_img = default_image_obj(
        dt_source=dt, elev_source=elev,
        tcorr_source=tcorr, tmax_source=tmax).et_fraction
    output = utils.point_image_value(ee.Image(output_img), TEST_POINT)
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
    output_img = default_image_obj(
        lst=lst, ndvi=ndvi, dt_source=dt, elev_source=elev,
        tcorr_source=tcorr, tmax_source=tmax, elr_flag=elr_flag).et_fraction
    output = utils.point_image_value(ee.Image(output_img), TEST_POINT)
    assert abs(output['et_fraction'] - expected) <= tol


# def test_Image_et_fraction_image_tcorr_properties(tol=0.0001):
#     """Test if Tcorr properties are set when tcorr_source is an image"""
#     output = utils.getinfo(default_image_obj(
#         tcorr_source='IMAGE', tmax_source='DAYMET_MEDIAN_V2').et_fraction)
#     assert 'tcorr' not in output['properties'].keys()
#     assert 'tcorr_index' not in output['properties'].keys()
#
#
# def test_Image_et_fraction_feature_tcorr_properties(tol=0.0001):
#     """Test if Tcorr properties are set when tcorr_source is a feature"""
#     output = utils.getinfo(default_image_obj(
#         tcorr_source='FEATURE', tmax_source='TOPOWX_MEDIAN_V0').et_fraction)
#     assert abs(output['properties']['tcorr'] - 0.9752) <= tol
#     assert output['properties']['tcorr_index'] == 0


def test_Image_et_reference_properties():
    """Test if properties are set on the ETr image"""
    output =  utils.getinfo(default_image_obj().et_reference)
    assert output['bands'][0]['id'] == 'et_reference'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


@pytest.mark.parametrize(
    'source, band, factor, xy, expected',
    [
        ['IDAHO_EPSCOR/GRIDMET', 'etr', 1, TEST_POINT, 9.5730],
        ['IDAHO_EPSCOR/GRIDMET', 'etr', 0.85, TEST_POINT, 9.5730 * 0.85],
        ['projects/earthengine-legacy/assets/projects/climate-engine/cimis/daily',
         'ETr_ASCE', 1, TEST_POINT, 10.0220],
        [10, 'FOO', 1, TEST_POINT, 10.0],
        [10, 'FOO', 0.85, TEST_POINT, 8.5],
    ]
)
def test_Image_et_reference_sources(source, band, factor, xy, expected,
                                    tol=0.001):
    """Test getting reference ET values for a single date at a real point"""
    output = utils.point_image_value(default_image_obj(
        et_reference_source=source, et_reference_band=band,
        et_reference_factor=factor).et_reference, xy)
    assert abs(output['et_reference'] - expected) <= tol


# TODO: Exception should be raised if source is not named like a collection
# def test_Image_et_reference_sources_exception():
#     with pytest.raises(ValueError):
#         utils.getinfo(default_image_obj(et_reference_source='DEADBEEF').et_reference)


def test_Image_et_properties():
    """Test if properties are set on the ET image"""
    output =  utils.getinfo(default_image_obj().et)
    assert output['bands'][0]['id'] == 'et'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


def test_Image_et_values(tol=0.0001):
    output_img = default_image_obj(
        ndvi=0.5, lst=308, dt_source=10, elev_source=50,
        tcorr_source=0.98, tmax_source=310, et_reference_source=10).et
    output = utils.point_image_value(output_img, TEST_POINT)
    assert abs(output['et'] - 5.8) <= tol


def test_Image_mask_properties():
    """Test if properties are set on the time image"""
    output = utils.getinfo(default_image_obj().mask)
    assert output['bands'][0]['id'] == 'mask'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


def test_Image_mask_values():
    output_img = default_image_obj(
        ndvi=0.5, lst=308, dt_source=10, elev_source=50,
        tcorr_source=0.98, tmax_source=310).mask
    output = utils.point_image_value(output_img, TEST_POINT)
    assert output['mask'] == 1


def test_Image_time_properties():
    """Test if properties are set on the time image"""
    output = utils.getinfo(default_image_obj().time)
    assert output['bands'][0]['id'] == 'time'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


def test_Image_time_values():
    # The time band should be the 0 UTC datetime, not the system:time_start
    # The time image is currently being built from the et_fraction image, so all
    #   the ancillary values must be set.
    output_img = default_image_obj(
        ndvi=0.5, lst=308, dt_source=10, elev_source=50,
        tcorr_source=0.98, tmax_source=310).time
    output = utils.point_image_value(output_img, TEST_POINT)
    assert output['time'] == utils.millis(SCENE_DT)


def test_Image_calculate_properties():
    """Test if properties are set on the output image"""
    output =  utils.getinfo(default_image_obj().calculate(['ndvi']))
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


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
    output_img = default_image_obj(
            ndvi=0.5, lst=308, dt_source=10, elev_source=50,
            tcorr_source=0.98, tmax_source=310, et_reference_source=10)\
        .calculate(['et', 'et_reference', 'et_fraction'])
    output = utils.point_image_value(output_img, TEST_POINT)
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
    output = ssebop.Image.from_landsat_c1_toa(ee.Image(f'{COLL_ID}/{SCENE_ID}'))
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
    output = utils.getinfo(ssebop.Image.from_landsat_c1_toa(
        image_id).et_fraction)
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
        # Intentionally using .getInfo()
        ssebop.Image.from_landsat_c1_toa(ee.Image('FOO')).ndvi.getInfo()


def test_Image_from_landsat_c1_sr_default_image():
    """Test that the classmethod is returning a class object"""
    output = ssebop.Image.from_landsat_c1_sr(ee.Image(f'{COLL_ID}/{SCENE_ID}'))
    assert type(output) == type(default_image_obj())


@pytest.mark.parametrize(
    'image_id',
    [
        'LANDSAT/LC08/C01/T1_SR/LC08_044033_20170716',
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
    output = utils.getinfo(ssebop.Image.from_landsat_c1_sr(
        ee.Image(image_id)).ndvi)
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_from_landsat_c1_sr_et_fraction():
    """Test if ETf can be built for a Landsat SR image"""
    image_id = 'LANDSAT/LC08/C01/T1_SR/LC08_044033_20170716'
    output = utils.getinfo(ssebop.Image.from_landsat_c1_sr(
        image_id).et_fraction)
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
        # Intentionally using .getInfo()
        ssebop.Image.from_landsat_c1_sr(ee.Image('FOO')).ndvi.getInfo()


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
    output_img = default_image_obj(
        lst=lst, ndvi=ndvi, tmax_source=tmax).tcorr_image
    output = utils.point_image_value(output_img, TEST_POINT)
    assert abs(output['tcorr'] - expected) <= tol


@pytest.mark.parametrize(
    # Note: These are made up values
    'lst, ndvi, tmax, expected',
    [
        [300, 0.69, 306, None],  # NDVI < 0.7
        [269, 0.69, 306, None],  # LST < 270
        # TODO: Add a test for the NDVI smoothing
    ]
)
def test_Image_tcorr_image_nodata(lst, ndvi, tmax, expected):
    output = utils.constant_image_value(default_image_obj(
        lst=lst, ndvi=ndvi, tmax_source=tmax).tcorr_image)
    assert output['tcorr'] is None and expected is None


def test_Image_tcorr_image_band_name():
    output = utils.getinfo(default_image_obj().tcorr_image)
    assert output['bands'][0]['id'] == 'tcorr'


def test_Image_tcorr_image_properties(tmax_source='DAYMET_MEDIAN_V2',
                                      expected={'tmax_version': 'median_v2'}):
    """Test if properties are set on the tcorr image"""
    output = utils.getinfo(default_image_obj(
        tmax_source='DAYMET_MEDIAN_V2').tcorr_image)
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['tmax_source'] == tmax_source
    assert output['properties']['tmax_version'] == expected['tmax_version']


def test_Image_tcorr_stats_constant(tcorr=0.993548387, count=41479998,
                                    tol=0.00000001):
    output = utils.getinfo(default_image_obj(
        ndvi=0.8, lst=308, dt_source=10, elev_source=50,
        tcorr_source=0.98, tmax_source=310).tcorr_stats)
    assert abs(output['tcorr_value'] - tcorr) <= tol
    assert output['tcorr_count'] == count


@pytest.mark.parametrize(
    'image_id, tmax_source, expected',
    [
        # TOPOWX_MEDIAN_V0
        # Note, these values are slightly different than those in the tcorr
        #   feature collection (commented out values), because the original
        #   values were built with snap points of 0, 0 instead of 15, 15.
        ['LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716', 'TOPOWX_MEDIAN_V0',
         {'tcorr_value': 0.9929312773213419, 'tcorr_count': 2463133}],  # 0.99255676, 971875
        ['LANDSAT/LE07/C01/T1_TOA/LE07_044033_20170708', 'TOPOWX_MEDIAN_V0',
         {'tcorr_value': 0.9819725106056428, 'tcorr_count': 743774}],   # 0.98302000, 1700567
        ['LANDSAT/LT05/C01/T1_TOA/LT05_044033_20110716', 'TOPOWX_MEDIAN_V0',
         {'tcorr_value': 0.9561832021931235, 'tcorr_count': 514981}],   # 0.95788514, 2315630
        # DAYMET_MEDIAN_V2
        ['LANDSAT/LC08/C01/T1_TOA/LC08_042035_20150713', 'DAYMET_MEDIAN_V2',
         {'tcorr_value': 0.9738927482041165, 'tcorr_count': 761231}],
        ['LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716', 'DAYMET_MEDIAN_V2',
         {'tcorr_value': 0.9870731706021387, 'tcorr_count': 2463133}],
        ['LANDSAT/LE07/C01/T1_TOA/LE07_044033_20170708', 'DAYMET_MEDIAN_V2',
         {'tcorr_value': 0.9799146240259888, 'tcorr_count': 743774}],
        ['LANDSAT/LT05/C01/T1_TOA/LT05_044033_20110716', 'DAYMET_MEDIAN_V2',
         {'tcorr_value': 0.951809413760349, 'tcorr_count': 514981}],
        ['LANDSAT/LC08/C01/T1_TOA/LC08_042035_20161206', 'DAYMET_MEDIAN_V2',
         {'tcorr_value': 0.9907451827474001, 'tcorr_count': 11}],
        # # Old values using 5th percentile for Tcorr
        # # Keeping in case we make the tcorr percentile a parameter
        # ['LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716', 'TOPOWX_MEDIAN_V0',
        #  {'tcorr_value': 0.9938986398112951, 'tcorr_count': 2463133}],  # 0.99255676, 971875
        # ['LANDSAT/LE07/C01/T1_TOA/LE07_044033_20170708', 'TOPOWX_MEDIAN_V0',
        #  {'tcorr_value': 0.9819725106056428, 'tcorr_count': 743774}],   # 0.98302000, 1700567
        # ['LANDSAT/LT05/C01/T1_TOA/LT05_044033_20110716', 'TOPOWX_MEDIAN_V0',
        #  {'tcorr_value': 0.9569143183692558, 'tcorr_count': 514981}],   # 0.95788514, 2315630
        # # DAYMET_MEDIAN_V2
        # ['LANDSAT/LC08/C01/T1_TOA/LC08_042035_20150713', 'DAYMET_MEDIAN_V2',
        #  {'tcorr_value': 0.9743747113938074, 'tcorr_count': 761231}],
        # ['LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716', 'DAYMET_MEDIAN_V2',
        #  {'tcorr_value': 0.9880444668266360, 'tcorr_count': 2463133}],
        # ['LANDSAT/LE07/C01/T1_TOA/LE07_044033_20170708', 'DAYMET_MEDIAN_V2',
        #  {'tcorr_value': 0.9817142973468178, 'tcorr_count': 743774}],
        # ['LANDSAT/LT05/C01/T1_TOA/LT05_044033_20110716', 'DAYMET_MEDIAN_V2',
        #  {'tcorr_value': 0.9520545648466826, 'tcorr_count': 514981}],
        # ['LANDSAT/LC08/C01/T1_TOA/LC08_042035_20161206', 'DAYMET_MEDIAN_V2',
        #  {'tcorr_value': 0.9907451827474001, 'tcorr_count': 11}],
    ]
)
def test_Image_tcorr_stats_landsat(image_id, tmax_source, expected,
                                   tol=0.0000001):
    output = utils.getinfo(ssebop.Image.from_landsat_c1_toa(
        ee.Image(image_id), tmax_source=tmax_source,
        tmax_resample='nearest').tcorr_stats)
    assert abs(output['tcorr_value'] - expected['tcorr_value']) <= tol
    assert output['tcorr_count'] == expected['tcorr_count']


# def test_Image_et_fraction_properties():
#     """Test if properties are set on the ETf image"""
#     output = utils.getinfo(default_image_obj().et_fraction)
#     assert output['bands'][0]['id'] == 'et_fraction'
#     assert output['properties']['system:index'] == SCENE_ID
#     assert output['properties']['system:time_start'] == SCENE_TIME
#
#
# @pytest.mark.parametrize(
#     'dt, elev, tcorr, tmax, expected', [[10, 50, 0.98, 310, 0.88]]
# )
# def test_Image_et_fraction_values(dt, elev, tcorr, tmax, expected, tol=0.0001):
#     output_img = default_image_obj(
#         dt_source=dt, elev_source=elev,
#         tcorr_source=tcorr, tmax_source=tmax).et_fraction
#     output = utils.point_image_value(ee.Image(output_img), TEST_POINT)
#     assert abs(output['et_fraction'] - expected) <= tol
#     # assert output['et_fraction'] > 0


@pytest.mark.parametrize(
    'et_fraction_type, expected',
    [
        # ['alfalfa', 0.88],
        ['grass', 0.88 * 1.24],
        # ['Grass', 0.88 * 0.5],
    ]
)
def test_Image_et_fraction_type(et_fraction_type, expected, tol=0.0001):
    output_img = default_image_obj(
        dt_source=10, elev_source=50,
        tcorr_source=0.98, tmax_source=310,
        et_fraction_type=et_fraction_type).et_fraction
    output = utils.point_image_value(ee.Image(output_img), TEST_POINT)
    assert abs(output['et_fraction'] - expected) <= tol
    # assert output['bands'][0]['id'] == 'et_fraction'


def test_Image_et_fraction_type_exception():
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj(et_fraction_type='deadbeef').et_fraction)
