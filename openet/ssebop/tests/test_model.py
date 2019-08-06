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
        [307.65, 291.65, 68.4937, 194, 36.0405, 18.5681],      # DAYMET
        [307.3597, 291.8105, 68.4937, 194, 36.0405, 18.6148],  # GRIDMET
        [309.1128, 292.6634, 68.4937, 194, 36.0405, 18.8347],  # CIMIS
        # 2017-07-16
        [313.15, 293.65, 21.8306, 197, 39.1968, 18.8273],      # DAYMET
        [312.3927, 293.2107, 21.8306, 197, 39.1968, 18.7025],  # GRIDMET
        [313.5187, 292.2343, 21.8306, 197, 39.1968, 18.4032],  # CIMIS
    ]
)
def test_Image_dt_calc_rso(tmax, tmin, elev, doy, lat, expected, tol=0.0001):
    """Test dt calculation using Rso"""
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
        [313.15, 293.65, 21.8306, 197, 39.1968, 25.3831, 16.7160],      # DAYMET
        [312.3927, 293.2107, 21.8306, 197, 39.1968, 30.2915, 19.7751],  # GRIDMET
        [313.5187, 292.2343, 21.8306, 197, 39.1968, 29.1144, 18.4867],  # CIMIS
    ]
)
def test_Image_dt_calc_rs(tmax, tmin, elev, doy, lat, rs, expected, tol=0.0001):
    """Test dt calculation using measured Rs"""
    dt = model.dt(tmax=ee.Number(tmax), tmin=ee.Number(tmin),
                  elev=ee.Number(elev), rs=ee.Number(rs),
                  doy=ee.Number(doy), lat=ee.Number(lat)).getInfo()
    assert abs(float(dt) - expected) <= tol


def test_Image_dt_doy_exception():
    with pytest.raises(ValueError):
        utils.getinfo(model.dt(tmax=313.15, tmin=293.65, elev=21.8306, doy=None))
