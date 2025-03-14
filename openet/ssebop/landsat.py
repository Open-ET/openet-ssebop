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
    pv = ndvi_img.expression('((ndvi - 0.2) / 0.3) ** 2', {'ndvi': ndvi_img})

    # Assuming typical Soil Emissivity of 0.97 and Veg Emissivity of 0.99
    #   and shape Factor mean value of 0.553
    de = pv.expression('(1 - 0.97) * (1 - Pv) * (0.55 * 0.99)', {'Pv': pv})
    range_emis = de.expression('(0.99 * Pv) + (0.97 * (1 - Pv)) + dE', {'Pv': pv, 'dE': de})

    return (
        ndvi_img
        .where(ndvi_img.lt(0), 0.985)
        .where(ndvi_img.gte(0).And(ndvi_img.lt(0.2)), 0.977)
        .where(ndvi_img.gt(0.5), 0.99)
        .where(ndvi_img.gte(0.2).And(ndvi_img.lte(0.5)), range_emis)
        .clamp(0.977, 0.99)
        .rename(['emissivity'])
    )


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
        {'ts_brightness': ts_brightness, 'k1': k1, 'k2': k2}
    )

    rc = thermal_rad_toa.expression(
        '((thermal_rad_toa - rp) / tnb) - ((1 - emiss) * rsky)',
        {
            'thermal_rad_toa': thermal_rad_toa,
            'emiss': emissivity_img,
            'rp': 0.91, 'tnb': 0.866, 'rsky': 1.32,
        }
    )
    lst = rc.expression(
        'k2 / log(emiss * k1 / rc + 1)',
        {'emiss': emissivity_img, 'rc': rc, 'k1': k1, 'k2': k2}
    )

    return lst.rename(['lst'])


def ndvi(landsat_image, gsw_extent_flag=True):
    """Normalized difference vegetation index

    Parameters
    ----------
    landsat_image : ee.Image
        "Prepped" Landsat image with standardized band names.
    gsw_extent_flag : boolean
        If True, apply the global surface water extent mask to the QA_PIXEL water mask
        The default is True.

    Returns
    -------
    ee.Image

    """
    # Force the input values to be at greater than or equal to zero
    #   since C02 surface reflectance values can be negative
    #   but the normalizedDifference function will return nodata
    ndvi_img = landsat_image.max(0).normalizedDifference(['nir', 'red'])

    b1 = landsat_image.select(['nir'])
    b2 = landsat_image.select(['red'])

    # Assume that very high reflectance values are unreliable for computing the index
    #   and set the output value to 0
    # Threshold value could be set lower, but for now only trying to catch saturated pixels
    ndvi_img = ndvi_img.where(b1.gte(1).Or(b2.gte(1)), 0)

    # Including the global surface water maximum extent to help remove shadows that
    #   are misclassified as water
    # The flag is needed so that the image can be bypassed during testing with constant images
    qa_water_mask = landsat_c2_qa_water_mask(landsat_image)
    if gsw_extent_flag:
        gsw_mask = ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select(['max_extent']).gte(1)
        qa_water_mask = qa_water_mask.And(gsw_mask)

    # Assume that low reflectance values are unreliable for computing the index
    # If both reflectance values are below the threshold,
    #   and if the pixel is flagged as water, set the output to -0.1 (should this be -1?)
    #   otherwise set the output to 0
    ndvi_img = ndvi_img.where(b1.lt(0.01).And(b2.lt(0.01)), 0)
    ndvi_img = ndvi_img.where(b1.lt(0.01).And(b2.lt(0.01)).And(qa_water_mask), -0.1)
    # Should there be an additional check for if either value was negative?
    # ndvi_img = ndvi_img.where(b1.lt(0).Or(b2.lt(0)), 0)

    return ndvi_img.clamp(-1.0, 1.0).rename(['ndvi'])


def ndwi(landsat_image):
    """Normalized difference water index

    Parameters
    ----------
    landsat_image : ee.Image
        "Prepped" Landsat image with standardized band names.

    Returns
    -------
    ee.Image

    """
    # Force the input values to be at greater than or equal to zero
    #   since C02 surface reflectance values can be negative
    #   but the normalizedDifference function will return nodata
    ndwi_img = landsat_image.max(0).normalizedDifference(['swir1', 'green'])

    b1 = landsat_image.select(['swir1'])
    b2 = landsat_image.select(['green'])

    # Assume that very high reflectance values are unreliable for computing the index
    #   and set the output value to 0
    # Threshold value could be set lower, but for now only trying to catch saturated pixels
    ndwi_img = ndwi_img.where(b1.gte(1).Or(b2.gte(1)), 0)

    # Assume that low reflectance values are unreliable for computing the index
    # If both reflectance values are below the threshold set the output to 0
    # May want to check the QA water mask here also, similar to the NDVI calculation
    ndwi_img = ndwi_img.where(b1.lt(0.01).And(b2.lt(0.01)), 0)

    return ndwi_img.clamp(-1.0, 1.0).rename(['ndwi'])


def landsat_c2_qa_water_mask(landsat_image):
    """Extract water mask from the Landsat Collection 2 SR QA_PIXEL band.

    Parameters
    ----------
    landsat_image : ee.Image
        Landsat C02 image with a QA_PIXEL band.

    Returns
    -------
    ee.Image

    """
    return (
        ee.Image(landsat_image)
        .select(['QA_PIXEL'])
        .rightShift(7).bitwiseAnd(1).neq(0)
        .rename(['qa_water'])
    )
