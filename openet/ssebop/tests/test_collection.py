import pprint

import ee
import pytest

import openet.ssebop as ssebop
import openet.ssebop.utils as utils
# TODO: import utils from openet.core
# import openet.core.utils as utils


COLLECTIONS = ['LANDSAT/LC08/C01/T1_RT_TOA', 'LANDSAT/LE07/C01/T1_RT_TOA']
SCENE_ID_LIST = sorted(['LC08_044033_20170716', 'LE07_044033_20170708',
                        'LE07_044033_20170724'])
START_DATE = '2017-07-01'
END_DATE = '2017-08-01'
POINT = (-122, 39)
VARIABLES = sorted(['et', 'etf', 'etr'])

def default_coll_args():
    # Defining inside a function since ee.Initialize() isn't called until after
    # all tests are collected.
    # It might make more sense if this accepted kwargs to overwrite the values.
    return {
        'collections': COLLECTIONS,
        'start_date': START_DATE,
        'end_date': END_DATE,
        'geometry': ee.Geometry.Point(POINT),
        'etr_source': 'IDAHO_EPSCOR/GRIDMET',
        'etr_band': 'etr',
    }


def parse_scene_id(output_info):
    output = [x['properties']['system:index'] for x in output_info['features']]
    # Strip merge indices (this works for Landsat and Sentinel image IDs
    return sorted(['_'.join(x.split('_')[-3:]) for x in output])


# Write test to see if end date is inclusive or exclusive


def test_ee_init():
    """Check that Earth Engine was initialized"""
    assert ee.Number(1).getInfo() == 1


def test_Collection_init_default_parameters():
    """Test if init sets default parameters"""
    args = default_coll_args()
    del args['etr_source']
    del args['etr_band']
    n = ssebop.Collection(**args)
    assert n.variables == None
    assert n.cloud_cover_max == 70
    assert n.etr_source == 'IDAHO_EPSCOR/GRIDMET'
    assert n.etr_band == 'etr'
    assert n._interp_vars == ['ndvi', 'etf']
