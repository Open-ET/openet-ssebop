import ee
import pytest

import openet.ssebop.model as model
import openet.ssebop.utils as utils


@pytest.mark.parametrize(
    'tmax, elev, threshold, expected',
    [
        [305, 1500, 1500, 305],
        [305, 2000, 1500, 303.5],
        [305, 500, 0, 303.5],
    ]
)
def test_Image_static_lapse_adjust(tmax, elev, threshold, expected, tol=0.0001):
    output = utils.constant_image_value(model.lapse_adjust(
        ee.Image.constant(tmax), ee.Image.constant(elev), threshold))
    assert abs(output['constant'] - expected) <= tol


@pytest.mark.parametrize(
    # Note: These are made up values
    'lst, ndvi, dt, tcorr, tmax, expected',
    [
        # Basic ETf test
        [308, 0.50, 10, 0.98, 310, 0.58],
        # Test ETf clamp conditions
        [300, 0.80, 15, 0.98, 310, 1.05],
        [319, 0.80, 15, 0.98, 310, 0.0],
        # Test dT high, max/min, and low clamp values
        # CGM: dT clamping currently happens when dT source is read
        # [305, 0.80, 26, 0.98, 310, 0.952],
        [305, 0.80, 25, 0.98, 310, 0.952],
        [305, 0.80, 6, 0.98, 310, 0.8],
        # [305, 0.80, 5, 0.98, 310, 0.8],
        # High and low test values (made up numbers)
        [305, 0.80, 15, 0.98, 310, 0.9200],
        [315, 0.10, 15, 0.98, 310, 0.2533],
        # Test changing Tcorr
        [305, 0.80, 15, 0.985, 310, 1.0233],
        [315, 0.10, 15, 0.985, 310, 0.3566],
        # Central Valley test values
        [302, 0.80, 17, 0.985, 308, 1.05],
        [327, 0.08, 17, 0.985, 308, 0.0],
    ]
)
def test_Image_et_fraction_values(lst, ndvi, dt, tcorr, tmax, expected, tol=0.0001):
    output = utils.constant_image_value(model.et_fraction(
        lst=ee.Image.constant(lst), tmax=ee.Image.constant(tmax),
        tcorr=tcorr, dt=dt))
    assert abs(output['et_fraction'] - expected) <= tol


@pytest.mark.parametrize(
    'lst, dt, tcorr, tmax, expected',
    [
        # The ETf mask limit was changed from 1.3 to 1.5 for gridded Tcorr
        [302, 10, 0.98, 310, 1.05], # 1.18 ETf should be clamped to 1.05
        [300, 10, 0.98, 310, 1.05], # 1.38 ETf should be clamped to 1.05
        [298, 10, 0.98, 310, None], # 1.58 ETf should be set to None (>1.5)
    ]
)
def test_Image_et_fraction_clamp_nodata(lst, dt, tcorr, tmax, expected):
    """Test that ETf is set to nodata for ETf > 1.3"""
    output_img = model.et_fraction(
        lst=ee.Image.constant(lst), tmax=ee.Image.constant(tmax),
        tcorr=tcorr, dt=dt)
    output = utils.constant_image_value(ee.Image(output_img))
    if expected is None:
        assert output['et_fraction'] is None
    else:
        assert output['et_fraction'] == expected


@pytest.mark.parametrize(
    # Note: These are made up values
    'lst, dt, elev, tcorr, tmax, elr_flag, expected',
    [
        # Test ELR flag
        [305, 15, 2000, 0.98, 310, False, 0.9200],
        [305, 15, 2000, 0.98, 310, True, 0.8220],
        [315, 15, 2000, 0.98, 310, True, 0.1553],
    ]
)
def test_Image_et_fraction_elr_param(lst, dt, elev, tcorr, tmax, elr_flag,
                                     expected, tol=0.0001):
    """Test that elr_flag works and changes ETf values"""
    output_img = model.et_fraction(
        lst=ee.Image.constant(lst), tmax=ee.Image.constant(tmax),
        tcorr=tcorr, dt=dt, elr_flag=elr_flag, elev=elev)
    output = utils.constant_image_value(ee.Image(output_img))
    assert abs(output['et_fraction'] - expected) <= tol


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
def test_Model_dt_calc_rso_no_ea(tmax, tmin, elev, doy, lat, expected,
                                 tol=0.0001):
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
def test_Model_dt_calc_rs_no_ea(tmax, tmin, elev, doy, lat, rs, expected,
                                tol=0.0001):
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
def test_Model_dt_calc_rso_ea(tmax, tmin, elev, doy, lat, ea, expected,
                              tol=0.0001):
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
def test_Model_dt_calc_rs_ea(tmax, tmin, elev, doy, lat, rs, ea, expected,
                             tol=0.0001):
    """Test dt calculation using 'measured' Rs and Ea (from Tdew, sph, vp)"""
    dt = utils.getinfo(model.dt(
        tmax=ee.Number(tmax), tmin=ee.Number(tmin), elev=ee.Number(elev),
        rs=ee.Number(rs), ea=ee.Number(ea), doy=ee.Number(doy),
        lat=ee.Number(lat)))
    assert abs(float(dt) - expected) <= tol


def test_Model_dt_doy_exception():
    with pytest.raises(ValueError):
        utils.getinfo(model.dt(tmax=313.15, tmin=293.65, elev=21.83, doy=None))
