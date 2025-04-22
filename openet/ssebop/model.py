import math

import ee

import openet.refetgee


def et_fraction(lst, tcold, dt):
    """SSEBop fraction of reference ET (ETf)

    Parameters
    ----------
    lst : ee.Image
        Land surface temperature (lst) [L].
    tcold : ee.Image
        Cold temperature [K].
    dt : ee.Image, ee.Number
        Temperature difference [K].

    Returns
    -------
    ee.Image

    References
    ----------


    Notes
    -----
    Clamping function assumes this is an alfalfa fraction.

    """

    etf = lst.expression(
        '(lst * (-1) + tcold + dt) / dt',
        {'lst': lst, 'tcold': tcold, 'dt': dt}
    )

    return etf.updateMask(etf.lte(2.0)).clamp(0, 1.0).rename(['et_fraction'])


def dt(tmax, tmin, elev, doy, lat=None, rs=None, ea=None):
    """Temperature difference between hot/dry ground and cold/wet canopy

    Parameters
    ----------
    tmax : ee.Image, ee.Number
        Maximum daily air temperature [K].
    tmin : ee.Image, ee.Number
        Maximum daily air temperature [K].
    elev : ee.Image, ee.Number
        Elevation [m].
    doy : ee.Number, int
        Day of year.
    lat : ee.Image, ee.Number, optional
        Latitude [deg].  If not set, use GEE pixelLonLat() method.
    rs : ee.Image, ee.Number, optional
        Incoming solar radiation [MJ m-2 d-1].  If not set the theoretical
        clear sky solar (Rso) will be used for the Rs.
    ea : ee.Image, ee.Number, optional
        Actual vapor pressure [kPa].  If not set, vapor pressure will be
        computed from Tmin.

    Returns
    -------
    ee.Image

    Raises
    ------
    ValueError if doy is not set.

    References
    ----------
    .. [FAO56] Allen, R., Pereira, L., Raes, D., & Smith, M. (1998).
       Crop evapotranspiration: Guidelines for computing crop water
       requirements. FAO Irrigation and Drainage Paper (Vol. 56).
    .. [Senay2018] Senay, G. (2018). Satellite psychrometric formulation of
       the operational simplified surface energy balance (SSEBop) model for
       quantifying and mapping evapotranspiration.
       Applied Engineering in Agriculture, Vol 34(3).

    """
    if lat is None:
        lat = ee.Image.pixelLonLat().select(['latitude'])
    if doy is None:
        # TODO: attempt to read time_start from one of the images
        raise ValueError('doy must be set')

    # Convert latitude to radians
    phi = lat.multiply(math.pi / 180)

    # Make a DOY image from the DOY number
    doy = tmax.multiply(0).add(doy)

    # Extraterrestrial radiation (Ra) (FAO56 Eqns 24, 25, 23, 21)
    delta = doy.multiply(2 * math.pi / 365).subtract(1.39).sin().multiply(0.409)
    ws = phi.tan().multiply(-1).multiply(delta.tan()).acos()
    dr = doy.multiply(2 * math.pi / 365).cos().multiply(0.033).add(1)
    ra = (
        ws.multiply(phi.sin()).multiply(delta.sin())
        .add(phi.cos().multiply(delta.cos()).multiply(ws.sin()))
        .multiply(dr).multiply((1367.0 / math.pi) * 0.0820)
    )

    # Simplified clear sky solar formulation (Rso) [MJ m-2 d-1] (Eqn 37)
    rso = elev.multiply(2E-5).add(0.75).multiply(ra)

    # Derive cloudiness fraction from Rs and Rso (see FAO56 Eqn 39)
    # Use Rso for Rs if not set
    if rs is None:
        rs = rso.multiply(1)
        fcd = 1
    else:
        fcd = rs.divide(rso).max(0.3).min(1.0).multiply(1.35).subtract(0.35)

    # Net shortwave radiation [MJ m-2 d-1] (FAO56 Eqn 38)
    rns = rs.multiply(1 - 0.23)

    # Actual vapor pressure [kPa] (FAO56 Eqn 14)
    if ea is None:
        ea = (
            tmin.subtract(273.15).multiply(17.27)
            .divide(tmin.subtract(273.15).add(237.3))
            .exp().multiply(0.6108)
        )

    # Net longwave radiation [MJ m-2 d-1] (FAO56 Eqn 39)
    rnl = (
        tmax.pow(4).add(tmin.pow(4))
        .multiply(ea.sqrt().multiply(-0.14).add(0.34))
        .multiply(4.901E-9 * 0.5).multiply(fcd)
    )

    # Net radiation [MJ m-2 d-1] (FAO56 Eqn 40)
    rn = rns.subtract(rnl)

    # Air pressure [kPa] (FAO56 Eqn 7)
    pair = elev.multiply(-0.0065).add(293.0).divide(293.0).pow(5.26).multiply(101.3)

    # Air density [Kg m-3] (Senay2018 A.11 & A.13)
    den = tmax.add(tmin).multiply(0.5).pow(-1).multiply(pair).multiply(3.486 / 1.01)

    # Temperature difference [K] (Senay2018 A.5)
    return rn.divide(den).multiply(110.0 / ((1.013 / 1000) * 86400))


# TODO: Decide if using the interpolated instantaneous is the right/best approach
#   We could use the closest hour in time, an average of a few hours
#   or just switch to using the raw daily or bias corrected assets
def etf_grass_type_adjust(etf, src_coll_id, time_start, resample_method='bilinear'):
    """"Convert ET fraction from an alfalfa reference to grass reference

    Parameters
    ----------
    etf : ee.Image
        ET fraction (alfalfa reference).
    src_coll_id : str
        Hourly meteorology collection ID for computing reference ET.
    time_start : int, ee.Number
        Image system time start [millis].
    resample_method : {'nearest', 'bilinear', 'bicubic'}
        Resample method for hourly meteorology collection.

    Returns
    -------
    ee.Image

    """
    hourly_et_reference_sources = [
        'NASA/NLDAS/FORA0125_H002',
        'ECMWF/ERA5_LAND/HOURLY',
    ]
    if src_coll_id not in hourly_et_reference_sources:
        raise ValueError(f'unsupported hourly ET reference source: {src_coll_id}')
    elif not src_coll_id:
        raise ValueError('hourly ET reference source not')
    else:
        src_coll = ee.ImageCollection(src_coll_id)

    # Interpolating hourly NLDAS to the Landsat scene time
    # CGM - The 2 hour window is useful in case an image is missing
    #   I think EEMETRIC is using a 4 hour window
    # CGM - Need to check if the NLDAS images are instantaneous
    #   or some sort of average of the previous or next hour
    time_start = ee.Number(time_start)
    prev_img = ee.Image(
        src_coll
        .filterDate(time_start.subtract(2 * 60 * 60 * 1000), time_start)
        .limit(1, 'system:time_start', False)
        .first()
    )
    next_img = ee.Image(
        src_coll.filterDate(time_start, time_start.add(2 * 60 * 60 * 1000)).first()
    )
    prev_time = ee.Number(prev_img.get('system:time_start'))
    next_time = ee.Number(next_img.get('system:time_start'))
    time_ratio = time_start.subtract(prev_time).divide(next_time.subtract(prev_time))
    interp_img = (
        next_img.subtract(prev_img).multiply(time_ratio).add(prev_img)
        .set({'system:time_start': time_start})
    )

    if src_coll_id.upper() == 'NASA/NLDAS/FORA0125_H002':
        ratio = (
            openet.refetgee.Hourly.nldas(interp_img).etr
            .divide(openet.refetgee.Hourly.nldas(interp_img).eto)
        )
        if resample_method and (resample_method.lower() in ['bilinear', 'bicubic']):
            ratio = ratio.resample(resample_method)
        etf_grass = etf.multiply(ratio)
    elif src_coll_id.upper() == 'ECMWF/ERA5_LAND/HOURLY':
        ratio = (
            openet.refetgee.Hourly.era5_land(interp_img).etr
            .divide(openet.refetgee.Hourly.era5_land(interp_img).eto)
        )
        if resample_method and (resample_method.lower() in ['bilinear', 'bicubic']):
            ratio = ratio.resample(resample_method)
        etf_grass = etf.multiply(ratio)

    return etf_grass
