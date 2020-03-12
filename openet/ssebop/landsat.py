import ee


def emissivity(landsat_image):
    """Emissivity as a function of NDVI

    Parameters
    ----------
    landsat_image : ee.Image
        "Prepped" Landsat image with standardized band names.

    Returns
    -------
    ee.Image

    References
    ----------
    .. [Sobrino2004] Sobrino, J., J. Jiménez-Muñoz, & L. Paolini (2004).
        Land surface temperature retrieval from LANDSAT TM 5.
        Remote Sensing of Environment, 90(4), 434-440.
        https://doi.org/10.1016/j.rse.2004.02.003

    """
    ndvi_img = ndvi(landsat_image)
    Pv = ndvi_img.expression('((ndvi - 0.2) / 0.3) ** 2', {'ndvi': ndvi_img})
    # ndviRangevalue = ndvi_image.where(
    #     ndvi_image.gte(0.2).And(ndvi_image.lte(0.5)), ndvi_image)
    # Pv = ndviRangevalue.expression(
    #     '(((ndviRangevalue - 0.2) / 0.3) ** 2',
    #     {'ndviRangevalue':ndviRangevalue})

    # Assuming typical Soil Emissivity of 0.97 and Veg Emissivity of 0.99
    #   and shape Factor mean value of 0.553
    dE = Pv.expression(
        '(1 - 0.97) * (1 - Pv) * (0.55 * 0.99)', {'Pv': Pv})
    RangeEmiss = dE.expression(
        '(0.99 * Pv) + (0.97 * (1 - Pv)) + dE', {'Pv': Pv, 'dE': dE})

    # RangeEmiss = 0.989 # dE.expression(
    #  '((0.99 * Pv) + (0.97 * (1 - Pv)) + dE)', {'Pv':Pv, 'dE':dE})
    return ndvi_img\
        .where(ndvi_img.lt(0), 0.985)\
        .where(ndvi_img.gte(0).And(ndvi_img.lt(0.2)), 0.977)\
        .where(ndvi_img.gt(0.5), 0.99)\
        .where(ndvi_img.gte(0.2).And(ndvi_img.lte(0.5)), RangeEmiss)\
        .clamp(0.977, 0.99)\
        .rename(['emissivity'])\


def lst(landsat_image):
    """Emissivity corrected land surface temperature (LST) from brightness Ts.

    Parameters
    ----------
    landsat_image : ee.Image
        "Prepped" Landsat image with standardized band names.
        Image must also have 'k1_constant' and 'k2_constant' properties.

    Returns
    -------
    ee.Image

    Notes
    -----
    The corrected radiation coefficients were derived from a small number
    of scenes in southern Idaho [Allen2007] and may not be appropriate for
    other areas.

    References
    ----------
    .. [Allen2007] R. Allen, M. Tasumi, R. Trezza (2007),
        Satellite-Based Energy Balance for Mapping Evapotranspiration with
        Internalized Calibration (METRIC) Model,
        Journal of Irrigation and Drainage Engineering, Vol 133(4),
        http://dx.doi.org/10.1061/(ASCE)0733-9437(2007)133:4(380)

    Notes
    -----
    tnb = 0.866   # narrow band transmissivity of air
    rp = 0.91     # path radiance
    rsky = 1.32   # narrow band clear sky downward thermal radiation

    """
    # Get properties from image
    k1 = ee.Number(ee.Image(landsat_image).get('k1_constant'))
    k2 = ee.Number(ee.Image(landsat_image).get('k2_constant'))

    ts_brightness = ee.Image(landsat_image).select(['tir'])
    emissivity_img = emissivity(landsat_image)

    # First back out radiance from brightness temperature
    # Then recalculate emissivity corrected Ts
    thermal_rad_toa = ts_brightness.expression(
        'k1 / (exp(k2 / ts_brightness) - 1)',
        {'ts_brightness': ts_brightness, 'k1': k1, 'k2': k2})

    rc = thermal_rad_toa.expression(
        '((thermal_rad_toa - rp) / tnb) - ((1 - emiss) * rsky)',
        {
            'thermal_rad_toa': thermal_rad_toa,
            'emiss': emissivity_img,
            'rp': 0.91, 'tnb': 0.866, 'rsky': 1.32,
        })
    lst = rc.expression(
        'k2 / log(emiss * k1 / rc + 1)',
        {'emiss': emissivity_img, 'rc': rc, 'k1': k1, 'k2': k2})

    return lst.rename(['lst'])


def ndvi(landsat_image):
    """Normalized difference vegetation index

    Parameters
    ----------
    landsat_image : ee.Image
        "Prepped" Landsat image with standardized band names.

    Returns
    -------
    ee.Image

    """
    return ee.Image(landsat_image).normalizedDifference(['nir', 'red'])\
        .rename(['ndvi'])
