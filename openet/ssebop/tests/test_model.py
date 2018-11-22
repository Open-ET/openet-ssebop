import datetime
import logging

import ee
import pytest

import openet.ssebop as ssebop
import openet.ssebop.utils as utils
# TODO: import utils from openet.core
# import openet.core.utils as utils


SCENE_ID = 'LC08_042035_20150713'
SCENE_DT = datetime.datetime.strptime(SCENE_ID[-8:], '%Y%m%d')
SCENE_DATE = SCENE_DT.strftime('%Y-%m-%d')
SCENE_DOY = int(SCENE_DT.strftime('%j'))


# Should these be test fixtures instead?
# I'm not sure how to make them fixtures and allow input parameters
def toa_image(red=0.2, nir=0.7, bt=300):
    """Construct a fake Landsat 8 TOA image with renamed bands"""
    return ee.Image.constant([red, nir, bt])\
        .rename(['red', 'nir', 'lst']) \
        .setMulti({
            'system:time_start': ee.Date(SCENE_DATE).millis(),
            'k1_constant': ee.Number(607.76),
            'k2_constant': ee.Number(1260.56)})


def default_image(lst=300, ndvi=0.8):
    # First construct a fake 'prepped' input image
    return ee.Image.constant([lst, ndvi]).rename(['lst', 'ndvi']) \
        .setMulti({
            'system:index': SCENE_ID,
            'system:time_start': ee.Date(SCENE_DATE).millis(),
    })


def test_ee_init():
    """Check that Earth Engine was initialized"""
    assert ee.Number(1).getInfo() == 1


def test_Image_default_parameters():
    s = ssebop.Image(default_image())
    assert s._dt_source == 'DAYMET_MEDIAN_V1'
    assert s._elev_source == 'SRTM'
    assert s._tcorr_source == 'SCENE'
    assert s._tmax_source == 'TOPOWX_MEDIAN_V0'
    assert s._elr_flag == False
    assert s._tdiff_threshold == 15
    assert s._dt_min == 6
    assert s._dt_max == 25


# Todo: Break these up into separate functions?
def test_Image_calculated_properties():
    s = ssebop.Image(default_image())
    assert s._time_start.getInfo() == ee.Date(SCENE_DATE).millis().getInfo()
    assert s._scene_id.getInfo() == SCENE_ID
    assert s._wrs2_tile.getInfo() == 'p{}r{}'.format(
        SCENE_ID.split('_')[1][:3], SCENE_ID.split('_')[1][3:])


def test_Image_date_properties():
    s = ssebop.Image(default_image())
    assert s._date.getInfo()['value'] == utils.millis(SCENE_DT)
    assert s._year.getInfo() == int(SCENE_DATE.split('-')[0])
    assert s._month.getInfo() == int(SCENE_DATE.split('-')[1])
    assert s._start_date.getInfo()['value'] == utils.millis(SCENE_DT)
    assert s._end_date.getInfo()['value'] == utils.millis(
        SCENE_DT + datetime.timedelta(days=1))
    assert s._doy.getInfo() == SCENE_DOY


def test_Image_scene_id_property():
    """Test that the system:index from a merged collection is parsed"""
    input_img = default_image()
    s = ssebop.Image(input_img.set('system:index', '1_2_' + SCENE_ID))
    assert s._scene_id.getInfo() == SCENE_ID


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
def test_Image_ndvi_calculation(red, nir, expected, tol=0.000001):
    toa = toa_image(red=red, nir=nir)
    output = utils.constant_image_value(ssebop.Image._ndvi(toa))
    # logging.debug('\n  Target values: {}'.format(expected))
    # logging.debug('  Output values: {}'.format(output))
    assert abs(output - expected) <= tol


def test_Image_ndvi_band_name():
    output = ssebop.Image._ndvi(toa_image()).getInfo()['bands'][0]['id']
    assert output == 'ndvi'


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
def test_Image_emissivity_calculation(red, nir, expected, tol=0.000001):
    toa = toa_image(red=red, nir=nir)
    output = utils.constant_image_value(ssebop.Image._emissivity(toa))
    assert abs(output - expected) <= tol


def test_Image_emissivity_band_name():
    output = ssebop.Image._emissivity(toa_image()).getInfo()['bands'][0]['id']
    assert output == 'emissivity'


@pytest.mark.parametrize(
    'red, nir, bt, expected',
    [
        [0.2, 0.7, 300, 303.471031],
    ]
)
def test_Image_lst_calculation(red, nir, bt, expected, tol=0.000001):
    toa = toa_image(red=red, nir=nir, bt=bt)
    output = utils.constant_image_value(ssebop.Image._lst(toa))
    assert abs(output - expected) <= tol


def test_Image_lst_band_name():
    output = ssebop.Image._lst(toa_image()).getInfo()['bands'][0]['id']
    assert output == 'lst'


@pytest.mark.parametrize(
    'tmax, elev, threshold, expected',
    [
        [305, 1500, 1500, 305],
        [305, 2000, 1500, 303.5],
        [305, 500, 0, 303.5],
    ]
)
def test_Image_lapse_adjust(tmax, elev, threshold, expected, tol=0.0001):
    output = utils.constant_image_value(ssebop.Image._lapse_adjust(
        ee.Image.constant(tmax), ee.Image.constant(elev), threshold))
    assert abs(output - expected) <= tol


@pytest.mark.parametrize(
    'dt_source, doy, xy, expected',
    [
        ['DAYMET_MEDIAN_V0', 194, [-120.113, 36.336], 19.262],
        ['DAYMET_MEDIAN_V1', 194, [-120.113, 36.336], 18],
        ['DAYMET_MEDIAN_V1', 194, [-119.0, 37.5], 21],
        # Check default clamped values
        ['DAYMET_MEDIAN_V0', 1, [-120.113, 36.336], 6],
        ['DAYMET_MEDIAN_V1', 1, [-120.113, 36.336], 6],
        ['DAYMET_MEDIAN_V0', 194, [-119.0, 37.5], 25],
        # Check string/float constant values
        ['19.262', 194, [-120.113, 36.336], 19.262],  # Check constant values
        [19.262, 194, [-120.113, 36.336], 19.262],    # Check constant values
    ]
)
def test_Image_dt_sources(dt_source, doy, xy, expected, tol=0.001):
    """Test getting dT values for a single date at a real point"""
    s = ssebop.Image(default_image(), dt_source=dt_source)
    s._doy = doy
    output = utils.point_image_value(ee.Image(s._dt), xy)
    assert abs(output - expected) <= tol


def test_Image_dt_sources_exception():
    with pytest.raises(ValueError):
        ssebop.Image(default_image(), dt_source='')._dt.getInfo()


@pytest.mark.parametrize(
    'doy, dt_min, dt_max',
    [
        [1, 6, 25],
        [200, 6, 25],
        [200, 10, 15],
    ]
)
def test_Image_dt_clamping(doy, dt_min, dt_max):
    s = ssebop.Image(default_image(), dt_source='DAYMET_MEDIAN_V1',
                     dt_min=dt_min, dt_max=dt_max)
    s._doy = doy
    reducer = ee.Reducer.min().combine(ee.Reducer.max(), sharedInputs=True)
    output = ee.Image(s._dt)\
        .reduceRegion(reducer=reducer, scale=1000, tileScale=4, maxPixels=2E8,
                      geometry=ee.Geometry.Rectangle(-125, 25, -65, 50))\
        .getInfo()
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
        ['projects/usgs-ssebop/srtm_1km', [-106.03249, 37.17777], 2369.0],
        ['projects/usgs-ssebop/srtm_1km', [-106.03249, 37.17777], 2369.0],
        # DEADBEEF - We should allow any EE image (not just users/projects)
        # ['USGS/NED', [-106.03249, 37.17777], 2364.35],
    ]
)
def test_Image_elev_sources(elev_source, xy, expected, tol=0.001):
    """Test getting elevation values for a single date at a real point"""
    output_img = ssebop.Image(default_image(), elev_source=elev_source)._elev
    output = utils.point_image_value(ee.Image(output_img), xy)
    assert abs(output - expected) <= tol


def test_Image_elev_sources_exception():
    with pytest.raises(ValueError):
        ssebop.Image(default_image(), elev_source='')._elev.getInfo()


def test_Image_elev_band_name():
    output = ssebop.Image(default_image())._elev.getInfo()['bands'][0]['id']
    assert output == 'elev'


@pytest.mark.parametrize(
    'tcorr_source, tmax_source, scene_id, month, expected',
    [
        ['SCENE', 'CIMIS', SCENE_ID, 7, [0.9789, 0]],
        ['SCENE', 'DAYMET', SCENE_ID, 7, [0.9825, 0]],
        ['SCENE', 'GRIDMET', SCENE_ID, 7, [0.9835, 0]],
        ['SCENE', 'CIMIS_MEDIAN_V1', SCENE_ID, 7, [0.9742, 0]],
        ['SCENE', 'DAYMET_MEDIAN_V0', SCENE_ID, 7, [0.9764, 0]],
        ['SCENE', 'DAYMET_MEDIAN_V1', SCENE_ID, 7, [0.9762, 0]],
        ['SCENE', 'GRIDMET_MEDIAN_V1', SCENE_ID, 7, [0.9750, 0]],
        ['SCENE', 'TOPOWX_MEDIAN_V0', SCENE_ID, 7, [0.9752, 0]],
        # If scene_id doesn't match, use monthly value
        ['SCENE', 'CIMIS', 'XXXX_042035_20150713', 7, [0.9701, 1]],
        ['SCENE', 'DAYMET', 'XXXX_042035_20150713', 7, [0.9718, 1]],
        ['SCENE', 'GRIDMET', 'XXXX_042035_20150713', 7, [0.9743, 1]],
        ['SCENE', 'CIMIS_MEDIAN_V1', 'XXXX_042035_20150713', 7, [0.9694, 1]],
        ['SCENE', 'DAYMET_MEDIAN_V0', 'XXXX_042035_20150713', 7, [0.9727, 1]],
        ['SCENE', 'DAYMET_MEDIAN_V1', 'XXXX_042035_20150713', 7, [0.9717, 1]],
        ['SCENE', 'GRIDMET_MEDIAN_V1', 'XXXX_042035_20150713', 7, [0.9725, 1]],
        ['SCENE', 'TOPOWX_MEDIAN_V0', 'XXXX_042035_20150713', 7, [0.9720, 1]],
        # Get monthly value directly (ignore scene ID)
        ['MONTH', 'CIMIS', SCENE_ID, 7, [0.9701, 1]],
        ['MONTH', 'DAYMET', SCENE_ID, 7, [0.9718, 1]],
        ['MONTH', 'GRIDMET', SCENE_ID, 7, [0.9743, 1]],
        ['MONTH', 'CIMIS_MEDIAN_V1', SCENE_ID, 7, [0.9694, 1]],
        ['MONTH', 'DAYMET_MEDIAN_V0', SCENE_ID, 7, [0.9727, 1]],
        ['MONTH', 'DAYMET_MEDIAN_V1', SCENE_ID, 7, [0.9717, 1]],
        ['MONTH', 'GRIDMET_MEDIAN_V1', SCENE_ID, 7, [0.9725, 1]],
        ['MONTH', 'TOPOWX_MEDIAN_V0', SCENE_ID, 7, [0.9720, 1]],
        # If scene_id and wrs2_tile/month don't match, use default value
        # Testing one Tmax source should be good
        ['SCENE', 'DAYMET', 'XXXX_042035_20150713', 13, [0.9780, 2]],
        ['MONTH', 'DAYMET', SCENE_ID, 13, [0.9780, 2]],
        # Test a user defined Tcorr value
        ['0.9850', 'DAYMET', SCENE_ID, 6, [0.9850, 3]],
        [0.9850, 'DAYMET', SCENE_ID, 6, [0.9850, 3]],
    ]
)
def test_Image_tcorr_source(tcorr_source, tmax_source, scene_id, month,
                            expected, tol=0.0001):
    """Test getting Tcorr value and index for a single date at a real point"""
    logging.debug('\n  {} {}'.format(tcorr_source, tmax_source))
    scene_date = datetime.datetime.strptime(scene_id.split('_')[-1], '%Y%m%d') \
        .strftime('%Y-%m-%d')
    input_image = ee.Image.constant(1).setMulti({
        'system:index': scene_id,
        'system:time_start': ee.Date(scene_date).millis()})
    s = ssebop.Image(input_image, tcorr_source=tcorr_source,
                     tmax_source=tmax_source)
    # Overwrite the month property with test value
    s._month = ee.Number(month)

    # _tcorr returns a tuple of the tcorr and tcorr_index
    tcorr, tcorr_index = s._tcorr
    tcorr = tcorr.getInfo()
    tcorr_index = tcorr_index.getInfo()

    assert abs(tcorr - expected[0]) <= tol
    assert tcorr_index == expected[1]


def test_Image_tcorr_sources_exception():
    with pytest.raises(ValueError):
        ssebop.Image(default_image(), tcorr_source='')._tcorr.getInfo()


@pytest.mark.parametrize(
    'tmax_source, xy, expected',
    [
        ['CIMIS', [-120.113, 36.336], 307.725],
        ['DAYMET', [-120.113, 36.336], 308.650],
        ['GRIDMET', [-120.113, 36.336], 306.969],
        # ['TOPOWX', [-120.113, 36.336], 301.67],
        ['CIMIS_MEDIAN_V1', [-120.113, 36.336], 308.946],
        ['DAYMET_MEDIAN_V0', [-120.113, 36.336], 310.150],
        ['DAYMET_MEDIAN_V1', [-120.113, 36.336], 310.150],
        ['GRIDMET_MEDIAN_V1', [-120.113, 36.336], 310.436],
        ['TOPOWX_MEDIAN_V0', [-120.113, 36.336], 310.430],
        # Check string/float constant values
        ['305', [-120.113, 36.336], 305],
        [305, [-120.113, 36.336], 305],
    ]
)
def test_Image_tmax_sources(tmax_source, xy, expected, tol=0.001):
    """Test getting Tmax values for a single date at a real point"""
    output_img = ssebop.Image(default_image(), tmax_source=tmax_source)._tmax
    output = utils.point_image_value(ee.Image(output_img), xy)
    assert abs(output - expected) <= tol


def test_Image_tmax_sources_exception():
    with pytest.raises(ValueError):
        ssebop.Image(default_image(), tmax_source='')._tmax.getInfo()


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
        .setMulti({
            'system:index': SCENE_ID,
            'system:time_start': ee.Date(SCENE_DATE).update(2099).millis()})
    output_img = ssebop.Image(input_img, tmax_source=tmax_source)._tmax
    output = utils.point_image_value(ee.Image(output_img), xy)
    assert abs(output - expected) <= tol


today_dt = datetime.datetime.today()
@pytest.mark.parametrize(
    'tmax_source, expected',
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
        ['305', {'TMAX_VERSION': 'CUSTOM_305'}],
        [305, {'TMAX_VERSION': 'CUSTOM_305'}],
    ]
)
def test_Image_tmax_properties(tmax_source, expected):
    """Test if properties are set on the Tmax image"""
    tmax_img = ssebop.Image(default_image(), tmax_source=tmax_source)._tmax
    output = tmax_img.getInfo()['properties']
    assert output['TMAX_SOURCE'] == tmax_source
    assert output['TMAX_VERSION'] == expected['TMAX_VERSION']


@pytest.mark.parametrize(
    # Note: These are made up values
    'lst, ndvi, dt, elev, tcorr, tmax, tdiff, elr, expected',
    [
        # Test ETf clamp conditions
        [300, 0.80, 10, 50, 0.98, 310, 15, False, None],
        [300, 0.80, 15, 50, 0.98, 310, 15, False, 1.05],
        # Test dT high, max/min, and low clamp values
        [305, 0.80, 29, 50, 0.98, 310, 10, False, 0.952],
        [305, 0.80, 25, 50, 0.98, 310, 10, False, 0.952],
        [305, 0.80, 6, 50, 0.98, 310, 10, False, 0.8],
        [305, 0.80, 5, 50, 0.98, 310, 10, False, 0.8],
        # High and low test values (made up numbers)
        [305, 0.80, 15, 50, 0.98, 310, 10, False, 0.9200],
        [315, 0.10, 15, 50, 0.98, 310, 10, False, 0.2533],
        # Test Tcorr
        [305, 0.80, 15, 50, 0.985, 310, 10, False, 1.0233],
        [315, 0.10, 15, 50, 0.985, 310, 10, False, 0.3566],
        # Test ELR flag
        [305, 0.80, 15, 2000, 0.98, 310, 10, False, 0.9200],
        [305, 0.80, 15, 2000, 0.98, 310, 10, True, 0.8220],
        [315, 0.10, 15, 2000, 0.98, 310, 10, True, 0.1553],
        # Test Tdiff buffer value masking
        [299, 0.80, 15, 50, 0.98, 310, 10, False, None],
        [304, 0.10, 15, 50, 0.98, 310, 5, False, None],
        # Central Valley test values
        [302, 0.80, 17, 50, 0.985, 308, 10, False, 1.05],
        [327, 0.08, 17, 50, 0.985, 308, 10, False, 0.0],
    ]
)
def test_Image_etf(lst, ndvi, dt, elev, tcorr, tmax, tdiff, elr, expected,
                   tol=0.0001):
    output_img = ssebop.Image(
            default_image(lst=lst, ndvi=ndvi), dt_source=dt, elev_source=elev,
            tcorr_source=tcorr, tmax_source=tmax, tdiff_threshold=tdiff,
            elr_flag=elr)\
        .etf
    output = utils.constant_image_value(ee.Image(output_img))

    # For some ETf tests, returning None is the correct result
    if output is None and expected is None:
        assert True
    else:
        assert abs(output - expected) <= tol


def test_Image_etf_band_name():
    output = ssebop.Image(default_image()).etf.getInfo()['bands'][0]['id']
    assert output == 'etf'


def test_Image_etf_properties(tol=0.0001):
    """Test if properties are set on the ETf image"""
    etf_img = ssebop.Image(default_image()).etf
    output = etf_img.getInfo()['properties']
    assert output['system:index'] == SCENE_ID
    assert output['system:time_start'] == ee.Date(SCENE_DATE).millis().getInfo()
    assert abs(output['TCORR'] - 0.9752) <= tol
    assert output['TCORR_INDEX'] == 0


# How should these @classmethods be tested?
def test_Image_from_landsat_c1_toa_default_image():
    """Test that the classmethod is returning a class object"""
    output = ssebop.Image.from_landsat_c1_toa(
        ee.Image('LANDSAT/LC08/C01/T1_TOA/LC08_044033_20170716'))
    assert type(output) == type(ssebop.Image(default_image()))


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
def test_Image_from_landsat_c1_toa_landsat_image(image_id):
    """Test instantiating the class from a real Landsat images"""
    output = ssebop.Image.from_landsat_c1_toa(ee.Image(image_id)).ndvi.getInfo()
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_from_landsat_c1_toa_exception():
    """Test instantiating the class for an invalid image ID"""
    with pytest.raises(Exception):
        ssebop.Image.from_landsat_c1_toa(ee.Image('DEADBEEF'))._index.getInfo()


def test_Image_from_landsat_c1_sr_default_image():
    """Test that the classmethod is returning a class object"""
    output = ssebop.Image.from_landsat_c1_sr(
        ee.Image('LANDSAT/LC08/C01/T1_SR/LC08_044033_20170716'))
    assert type(output) == type(ssebop.Image(default_image()))


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
def test_Image_from_landsat_c1_sr_landsat_image(image_id):
    """Test instantiating the class from a real Landsat images"""
    output = ssebop.Image.from_landsat_c1_sr(ee.Image(image_id)).ndvi.getInfo()
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_from_landsat_c1_sr_exception():
    """Test instantiating the class for an invalid image ID"""
    with pytest.raises(Exception):
        ssebop.Image.from_landsat_c1_sr(ee.Image('DEADBEEF'))._index.getInfo()
