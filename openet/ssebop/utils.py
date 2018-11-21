import calendar

import ee


# TODO: Import from common.utils
# Should these be test fixtures instead?
# I'm not sure how to make them fixtures and allow input parameters
def constant_image_value(image, crs='EPSG:32613', scale=1):
    """Extract the output value from a calculation done with constant images"""
    return ee.Image(image).rename(['output'])\
        .reduceRegion(
            reducer=ee.Reducer.first(), scale=scale,
            geometry=ee.Geometry.Rectangle([0, 0, 10, 10], crs, False))\
        .getInfo()['output']


def point_image_value(image, xy, scale=1):
    """Extract the output value from a calculation at a point"""
    return ee.Image(image).rename(['output'])\
        .reduceRegion(
            reducer=ee.Reducer.first(), geometry=ee.Geometry.Point(xy),
            scale=scale)\
        .getInfo()['output']


def _c_to_k(image):
    """Convert temperature image from C to K

    Parameters
    ----------
    image : ee.Image

    Returns
    -------
    ee.Image

    """
    return image.add(273.15)


def _date_to_time_0utc(date):
    """Get the 0 UTC time_start for a date

    Parameters
    ----------
    date : ee.Date

    Returns
    -------
    ee.Number

    Notes
    -----
    Extra operations are needed since update() does not set milliseconds to 0.

    """
    return date.update(hour=0, minute=0, second=0).millis()\
        .divide(1000).floor().multiply(1000)


def _is_number(x):
    try:
        float(x)
        return True
    except:
        return False


def millis(input_dt):
    """Convert datetime to milliseconds since epoch

    Parameters
    ----------
    input_dt : datetime

    Returns
    -------
    int

    """
    return 1000 * int(calendar.timegm(input_dt.timetuple()))
