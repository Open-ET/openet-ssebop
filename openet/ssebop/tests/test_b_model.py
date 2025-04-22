import ee
import pytest

import openet.ssebop.model as model
import openet.ssebop.utils as utils

COLL_ID = 'LANDSAT/LC08/C02/T1_L2'
SCENE_ID = 'LC08_042035_20150713'
SCENE_TIME = 1436812419150
SCENE_POINT = (-119.5, 36.0)
TEST_POINT = (-119.44252382373145, 36.04047742246546)


@pytest.mark.parametrize(
    # Note: These are made up values
    'lst, ndvi, dt, tcold, expected',
    [
        # Basic ETf test
        [308, 0.50, 10, 0.98 * 310, 0.58],
        # Test ETf clamp conditions
        [300, 0.80, 15, 0.98 * 310, 1.0],  # Clamped to 1.0
        [319, 0.80, 15, 0.98 * 310, 0.0],
        # Test dT high, max/min, and low clamp values
        # CGM: dT clamping currently happens when dT source is read
        # [305, 0.80, 26, 0.98, 310, 0.952],
        [305, 0.80, 25, 0.98 * 310, 0.952],
        [305, 0.80, 6, 0.98 * 310, 0.8],
        # [305, 0.80, 5, 0.98 * 310, 0.8],
        # High and low test values (made up numbers)
        [305, 0.80, 15, 0.98 * 310, 0.9200],
        [315, 0.10, 15, 0.98 * 310, 0.2533],
        # Test changing Tcorr
        [305, 0.80, 15, 0.983 * 310, 0.9820],
        [315, 0.10, 15, 0.985 * 310, 0.3566],
        # Central Valley test values
        [302, 0.80, 17, 0.985 * 308, 1.0],  # Clamped to 1.0
        [327, 0.08, 17, 0.985 * 308, 0.0],
    ]
)
def test_Model_et_fraction_values(lst, ndvi, dt, tcold, expected, tol=0.0001):
    output = utils.constant_image_value(model.et_fraction(
        lst=ee.Image.constant(lst), tcold=tcold, dt=dt))
    assert abs(output['et_fraction'] - expected) <= tol


@pytest.mark.parametrize(
    'lst, dt, tcold, expected',
    [
        # The ETf mask limit was changed from 1.5 to 2.0 for gridded Tcorr
        [304, 10, 0.98 * 310, 0.98],  # 0.98 ETf will not be clamped
        [303, 10, 0.98 * 310, 1.00],  # 1.08 ETf will be clamped to 1.0
        [293, 10, 0.98 * 310, None],  # 2.08 ETf should be set to None (>2.0)
        # The ETf mask limit was changed from 1.3 to 1.5 for gridded Tcorr
        # [302, 10, 0.98, 310, 1.05],  # 1.18 ETf should be clamped to 1.05
        # [300, 10, 0.98, 310, 1.05],  # 1.38 ETf should be clamped to 1.05
        # [298, 10, 0.98, 310, None],  # 1.58 ETf should be set to None (>1.5)
    ]
)
def test_Model_et_fraction_clamp_nodata(lst, dt, tcold, expected):
    """Test that ETf is set to nodata for ETf > 2.0"""
    output_img = model.et_fraction(lst=ee.Image.constant(lst), tcold=tcold, dt=dt)
    output = utils.constant_image_value(ee.Image(output_img))
    if expected is None:
        assert output['et_fraction'] is None
    else:
        assert abs(output['et_fraction'] - expected) <= 0.000001


@pytest.mark.parametrize(
    'tmax, tmin, elev, doy, lat, expected',
    [
        # Test values are slightly different than in this old playground script
        # https://code.earthengine.google.com/8316e79baf5c2e3332913e5ec3224e92
        # 2015-07-13
        [309.1128, 292.6634, 68.4937, 194, 36.0405, 18.8347],  # CIMIS
        [307.6500, 291.6500, 68.4937, 194, 36.0405, 18.5681],  # DAYMET
        [307.3597, 291.8105, 68.4937, 194, 36.0405, 18.6148],  # GRIDMET

        # 2017-07-16
        [313.5187, 292.2343, 18, 197, 39.1968, 18.3925],  # CIMIS
        [313.1500, 293.6500, 18, 197, 39.1968, 18.8163],  # DAYMET
        [312.3927, 293.2107, 18, 197, 39.1968, 18.6917],  # GRIDMET

    ]
)
def test_Model_dt_calc_rso_no_ea(tmax, tmin, elev, doy, lat, expected, tol=0.0001):
    """Test dt calculation using Rso and Ea from Tmin"""
    dt = utils.getinfo(model.dt(
        tmax=ee.Number(tmax), tmin=ee.Number(tmin),
        elev=ee.Number(elev), rs=None, doy=ee.Number(doy), lat=ee.Number(lat)))
    assert abs(float(dt) - expected) <= tol


@pytest.mark.parametrize(
    'tmax, tmin, elev, doy, lat, rs, expected',
    [
        # Test values are slightly different than in this old playground script
        # https://code.earthengine.google.com/8316e79baf5c2e3332913e5ec3224e92
        # 2017-07-16
        [313.5187, 292.2343, 18, 197, 39.1968, 29.1144, 18.4785],  # CIMIS
        [313.1500, 293.6500, 18, 197, 39.1968, 25.3831, 16.7078],  # DAYMET
        [312.3927, 293.2107, 18, 197, 39.1968, 30.2915, 19.7663],  # GRIDMET
    ]
)
def test_Model_dt_calc_rs_no_ea(tmax, tmin, elev, doy, lat, rs, expected, tol=0.0001):
    """Test dt calculation using measured Rs and Ea from Tmin"""
    dt = utils.getinfo(model.dt(
        tmax=ee.Number(tmax), tmin=ee.Number(tmin), elev=ee.Number(elev),
        rs=ee.Number(rs), doy=ee.Number(doy), lat=ee.Number(lat)))
    assert abs(float(dt) - expected) <= tol


@pytest.mark.parametrize(
    'tmax, tmin, elev, doy, lat, ea, expected',
    [
        # Test values are slightly different than in this old playground script
        # https://code.earthengine.google.com/8316e79baf5c2e3332913e5ec3224e92
        # 2017-07-16
        [313.5187, 292.2343, 18, 197, 39.1968, 1.6110, 17.0153],  # CIMIS
        [313.1500, 293.6500, 18, 197, 39.1968, 0.9200, 15.0200],  # DAYMET
        [312.3927, 293.2107, 18, 197, 39.1968, 1.6384, 17.0965],  # GRIDMET
    ]
)
def test_Model_dt_calc_rso_ea(tmax, tmin, elev, doy, lat, ea, expected, tol=0.0001):
    """Test dt calculation using 'measured' Ea (from Tdew, sph, vp) and Rso"""
    dt = utils.getinfo(model.dt(
        tmax=ee.Number(tmax), tmin=ee.Number(tmin), elev=ee.Number(elev),
        ea=ee.Number(ea), doy=ee.Number(doy), lat=ee.Number(lat)))
    assert abs(float(dt) - expected) <= tol


@pytest.mark.parametrize(
    'tmax, tmin, elev, doy, lat, rs, ea, expected',
    [
        # Test values are slightly different than in this old playground script
        # https://code.earthengine.google.com/8316e79baf5c2e3332913e5ec3224e92
        # 2017-07-16
        [313.5187, 292.2343, 18, 197, 39.1968, 29.1144, 1.6110, 17.1013],  # CIMIS
        [313.1500, 293.6500, 18, 197, 39.1968, 25.3831, 0.9200, 13.5525],  # DAYMET
        [312.3927, 293.2107, 18, 197, 39.1968, 30.2915, 1.6384, 18.1711],  # GRIDMET
    ]
)
def test_Model_dt_calc_rs_ea(tmax, tmin, elev, doy, lat, rs, ea, expected, tol=0.0001):
    """Test dt calculation using 'measured' Rs and Ea (from Tdew, sph, vp)"""
    dt = utils.getinfo(model.dt(
        tmax=ee.Number(tmax), tmin=ee.Number(tmin), elev=ee.Number(elev),
        rs=ee.Number(rs), ea=ee.Number(ea), doy=ee.Number(doy),
        lat=ee.Number(lat)))
    assert abs(float(dt) - expected) <= tol


def test_Model_dt_doy_exception():
    with pytest.raises(ValueError):
        utils.getinfo(model.dt(tmax=313.15, tmin=293.65, elev=21.83, doy=None))


def test_Model_etf_grass_type_adjust_parameters():
    """Check that the function parameter names and order don't change"""
    etf_img = (
        ee.Image(f'{COLL_ID}/{SCENE_ID}').select([0]).multiply(0).add(1.0)
        .rename(['et_fraction']).set('system:time_start', SCENE_TIME)
    )
    output = model.etf_grass_type_adjust(
        etf=etf_img, src_coll_id='NASA/NLDAS/FORA0125_H002',
        time_start=SCENE_TIME, resample_method='bilinear',
    )
    assert utils.point_image_value(output, SCENE_POINT, scale=100)['et_fraction'] > 1

    output = model.etf_grass_type_adjust(
        etf_img, 'NASA/NLDAS/FORA0125_H002', SCENE_TIME, 'bilinear'
    )
    assert utils.point_image_value(output, SCENE_POINT, scale=100)['et_fraction'] > 1


@pytest.mark.parametrize(
    'src_coll_id, resample_method, expected',
    [
        ['NASA/NLDAS/FORA0125_H002', 'nearest', 1.228],
        ['NASA/NLDAS/FORA0125_H002', 'bilinear', 1.232],
        ['ECMWF/ERA5_LAND/HOURLY', 'nearest', 1.156],
        ['ECMWF/ERA5_LAND/HOURLY', 'bilinear', 1.156],
    ]
)
def test_Model_etf_grass_type_adjust(src_coll_id, resample_method, expected, tol=0.001):
    """Check alfalfa to grass reference adjustment factor"""
    etf_img = (
        ee.Image(f'{COLL_ID}/{SCENE_ID}').select([0]).multiply(0).add(1.0)
        .rename(['et_fraction']).set('system:time_start', SCENE_TIME)
    )
    output = model.etf_grass_type_adjust(
        etf=etf_img, src_coll_id=src_coll_id, time_start=SCENE_TIME,
        resample_method=resample_method
    )
    output = utils.point_image_value(output, SCENE_POINT, scale=100)
    assert abs(output['et_fraction'] - expected) <= tol


def test_Model_etf_grass_type_adjust_src_coll_id_exception():
    """Function should raise an exception for unsupported src_coll_id values"""
    with pytest.raises(ValueError):
        utils.getinfo(model.etf_grass_type_adjust(
            etf=ee.Image.constant(1), src_coll_id='DEADBEEF', time_start=SCENE_TIME
        ))


