

def _c_to_k(image):
    """Convert temperature image from C to K

    Parameters
    ----------
    image : ee.Image

    Returns
    -------
    ee.Image

    """
    return image.add(273.15) \
        .copyProperties(image, ['system:index', 'system:time_start'])


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