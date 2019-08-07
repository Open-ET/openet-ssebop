import ee
import pytest

import openet.ssebop.model as model
import openet.ssebop.utils as utils


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
def test_Image_dt_calc_rso_no_ea(tmax, tmin, elev, doy, lat, expected, tol=0.0001):
    """Test dt calculation using Rso and Ea from Tmin"""
    dt = model.dt(tmax=ee.Number(tmax), tmin=ee.Number(tmin),
                  elev=ee.Number(elev), rs=None, doy=ee.Number(doy),
                  lat=ee.Number(lat)).getInfo()
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
def test_Image_dt_calc_rs_no_ea(tmax, tmin, elev, doy, lat, rs, expected, tol=0.0001):
    """Test dt calculation using measured Rs and Ea from Tmin"""
    dt = model.dt(tmax=ee.Number(tmax), tmin=ee.Number(tmin),
                  elev=ee.Number(elev), rs=ee.Number(rs),
                  doy=ee.Number(doy), lat=ee.Number(lat)).getInfo()
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
def test_Image_dt_calc_rso_ea(tmax, tmin, elev, doy, lat, ea, expected, tol=0.0001):
    """Test dt calculation using 'measured' Ea (from Tdew, sph, vp) and Rso"""
    dt = model.dt(tmax=ee.Number(tmax), tmin=ee.Number(tmin),
                  elev=ee.Number(elev), ea=ee.Number(ea),
                  doy=ee.Number(doy), lat=ee.Number(lat)).getInfo()
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
def test_Image_dt_calc_rs_ea(tmax, tmin, elev, doy, lat, rs, ea, expected, tol=0.0001):
    """Test dt calculation using 'measured' Rs and Ea (from Tdew, sph, vp)"""
    dt = model.dt(tmax=ee.Number(tmax), tmin=ee.Number(tmin),
                  elev=ee.Number(elev), rs=ee.Number(rs), ea=ee.Number(ea),
                  doy=ee.Number(doy), lat=ee.Number(lat)).getInfo()
    assert abs(float(dt) - expected) <= tol


def test_Image_dt_doy_exception():
    with pytest.raises(ValueError):
        utils.getinfo(model.dt(tmax=313.15, tmin=293.65, elev=21.8306, doy=None))
