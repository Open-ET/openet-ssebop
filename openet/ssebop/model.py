import math

import ee


def et_fraction(lst, tmax, tcorr, dt):
    """SSEBop fraction of reference ET (ETf)

    Parameters
    ----------
    lst : ee.Image
        Land surface temperature (lst) [L].
    tmax : ee.Image
        Maximum air temperature [K].
    tcorr : ee.Image, ee.Number
        Tcorr.
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
    et_fraction = lst.expression(
        '(lst * (-1) + tmax * tcorr + dt) / dt',
        {'tmax': tmax, 'dt': dt, 'lst': lst, 'tcorr': tcorr})

    return et_fraction\
        .updateMask(et_fraction.lte(2.0))\
        .clamp(0, 1.0)\
        .rename(['et_fraction'])


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
    delta = doy.multiply(2 * math.pi / 365).subtract(1.39).sin()\
        .multiply(0.409)
    ws = phi.tan().multiply(-1).multiply(delta.tan()).acos()
    dr = doy.multiply(2 * math.pi / 365).cos().multiply(0.033).add(1)
    ra = ws.multiply(phi.sin()).multiply(delta.sin())\
        .add(phi.cos().multiply(delta.cos()).multiply(ws.sin()))\
        .multiply(dr)\
        .multiply((1367.0 / math.pi) * 0.0820)

    # Simplified clear sky solar formulation (Rso) [MJ m-2 d-1] (Eqn 37)
    rso = elev.multiply(2E-5).add(0.75).multiply(ra)

    # Derive cloudiness fraction from Rs and Rso (see FAO56 Eqn 39)
    # Use Rso for Rs if not set
    if rs is None:
        rs = rso.multiply(1)
        fcd = 1
    else:
        fcd = rs.divide(rso).max(0.3).min(1.0).multiply(1.35).subtract(0.35)
        # fcd = rs.divide(rso).clamp(0.3, 1).multiply(1.35).subtract(0.35)

    # Net shortwave radiation [MJ m-2 d-1] (FAO56 Eqn 38)
    rns = rs.multiply(1 - 0.23)

    # Actual vapor pressure [kPa] (FAO56 Eqn 14)
    if ea is None:
        ea = tmin.subtract(273.15).multiply(17.27)\
            .divide(tmin.subtract(273.15).add(237.3)).exp().multiply(0.6108)

    # Net longwave radiation [MJ m-2 d-1] (FAO56 Eqn 39)
    rnl = tmax.pow(4).add(tmin.pow(4))\
        .multiply(ea.sqrt().multiply(-0.14).add(0.34))\
        .multiply(4.901E-9 * 0.5).multiply(fcd)

    # Net radiation [MJ m-2 d-1] (FAO56 Eqn 40)
    rn = rns.subtract(rnl)

    # Air pressure [kPa] (FAO56 Eqn 7)
    pair = elev.multiply(-0.0065).add(293.0).divide(293.0).pow(5.26)\
        .multiply(101.3)

    # Air density [Kg m-3] (Senay2018 A.11 & A.13)
    den = tmax.add(tmin).multiply(0.5).pow(-1).multiply(pair)\
        .multiply(3.486 / 1.01)

    # Temperature difference [K] (Senay2018 A.5)
    dt = rn.divide(den).multiply(110.0 / ((1.013 / 1000) * 86400))

    return dt


def lapse_adjust(temperature, elev, lapse_threshold=1500):
    """Elevation Lapse Rate (ELR) adjusted temperature [K]

    Parameters
    ----------
    temperature : ee.Image
        Temperature [K].
    elev : ee.Image
        Elevation [m].
    lapse_threshold : float
        Minimum elevation to adjust temperature [m] (the default is 1500).

    Returns
    -------
    ee.Image

    """
    elr_adjust = ee.Image(temperature).expression(
        '(temperature - (0.003 * (elev - threshold)))',
        {
            'temperature': temperature, 'elev': elev,
            'threshold': lapse_threshold
        })
    return ee.Image(temperature).where(elev.gt(lapse_threshold), elr_adjust)


def elr_adjust(temperature, elevation, radius=80):
    """Elevation Lapse Rate (ELR) adjusted temperature [K]

    Parameters
    ----------
    temperature : ee.Image
        Air temperature [K].
    elevation : ee.Image
        Elevation [m].
    radius : int
        Smoothing radius (the default is 80)

    Returns
    -------
    ee.Image of adjusted temperature

    Notes
    -----
    The radius was selected for the DAYMET 1km grid and will likely need to be
    adjusted for other temperature datasets.

    """
    tmax_img = ee.Image(temperature)
    elev_img = ee.Image(elevation)

    tmax_projection = tmax_img.projection()

    # First resample the elevation data to the temperature grid
    # These approaches for resampling should all be really similar
    #   but simple resampling is probably the fastest
    elev_tmax_fine = elev_img.reproject(crs=tmax_projection)
    # elev_tmax_fine = elev_img.resample('bilinear').reproject(crs=tmax_projection)
    # elev_tmax_fine = elev_img\
    #     .reduceResolution(reducer=ee.Reducer.median(), maxPixels=65536)\
    #     .reproject(crs=tmax_projection)

    # Then generate the smoothed elevation image
    elev_tmax_smoothed = elev_tmax_fine\
        .reduceNeighborhood(reducer=ee.Reducer.median(),
                            kernel=ee.Kernel.square(radius=radius,
                                                    units='pixels'))\
        .reproject(crs=tmax_projection)

    # Final ELR mask: (DEM-(medDEM.add(100)).gt(0))
    elev_diff = elev_tmax_fine.subtract(elev_tmax_smoothed.add(100))
    elr_mask = elev_diff.gt(0)

    # temperature - (0.005 * (elr_layer))
    elr_adjust = tmax_img.subtract(elev_diff.multiply(0.005))

    tmax_img = tmax_img.where(elr_mask, elr_adjust)

    return tmax_img
