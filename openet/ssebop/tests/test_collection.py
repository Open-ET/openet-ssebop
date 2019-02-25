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
SCENE_POINT = (-121.9, 39)
VARIABLES = sorted(['et', 'etf', 'etr'])
TEST_POINT = (-121.5265, 38.7399)


def default_coll_args():
    # Defining inside a function since this uses an ee.Geometry(),
    # but ee.Initialize() isn't called until after all tests are collected.
    return {
        'collections': COLLECTIONS,
        'start_date': START_DATE,
        'end_date': END_DATE,
        'geometry': ee.Geometry.Point(SCENE_POINT),
        'variables': VARIABLES,
        'etr_source': 'IDAHO_EPSCOR/GRIDMET',
        'etr_band': 'etr'}


# CGM - Should this be a fixture?
def parse_scene_id(output_info):
    output = [x['properties']['system:index'] for x in output_info['features']]
    # Strip merge indices (this works for Landsat image IDs
    return sorted(['_'.join(x.split('_')[-3:]) for x in output])


def test_ee_init():
    """Check that Earth Engine was initialized"""
    assert ee.Number(1).getInfo() == 1


def test_Collection_init_default_parameters():
    """Test if init sets default parameters"""
    args = default_coll_args()

    # These values are being set above but have defaults that need to be checked
    del args['etr_source']
    del args['etr_band']
    del args['variables']

    n = ssebop.Collection(**args)

    assert n.variables == None
    assert n.cloud_cover_max == 70
    assert n.etr_source == 'IDAHO_EPSCOR/GRIDMET'
    assert n.etr_band == 'etr'
    assert n._interp_vars == ['ndvi', 'etf']


def test_Collection_init_collection_str(coll_id='LANDSAT/LC08/C01/T1_TOA'):
    """Test if a single coll_id str is converted to a single item list"""
    args = default_coll_args()
    args['collections'] = coll_id
    assert ssebop.Collection(**args).collections == [coll_id]


def test_Image_init_cloud_cover_max_str():
    """Test if cloud_cover_max strings are converted to float"""
    args = default_coll_args()
    args['cloud_cover_max'] = '70'
    assert ssebop.Collection(**args).cloud_cover_max == 70


@pytest.mark.parametrize(
    'coll_id, start_date, end_date',
    [
        # ['LANDSAT/LT04/C01/T1_TOA', '1981-01-01', '1982-01-01'],
        # ['LANDSAT/LT04/C01/T1_TOA', '1994-01-01', '1995-01-01'],
        ['LANDSAT/LT05/C01/T1_TOA', '1983-01-01', '1984-01-01'],
        ['LANDSAT/LT05/C01/T1_TOA', '2012-01-01', '2013-01-01'],
        ['LANDSAT/LE07/C01/T1_TOA', '1998-01-01', '1999-01-01'],
        ['LANDSAT/LC08/C01/T1_TOA', '2012-01-01', '2013-01-01'],
    ]
)
def test_Collection_init_collection_filter(coll_id, start_date, end_date):
    """Test that collection IDs are filtered based on start/end dates"""
    # The target collection ID should be removed from the collections lists
    args = default_coll_args()
    args['collections'] = [coll_id]
    args['start_date'] = start_date
    args['end_date'] = end_date
    assert ssebop.Collection(**args).collections == []


def test_Collection_init_startdate_exception():
    """Test if Exception is raised for invalid start date formats"""
    args = default_coll_args()
    args['start_date'] = '1/1/2000'
    args['end_date'] = '2000-01-02'
    with pytest.raises(ValueError):
        ssebop.Collection(**args)


def test_Collection_init_enddate_exception():
    """Test if Exception is raised for invalid end date formats"""
    args = default_coll_args()
    args['start_date'] = '2000-01-01'
    args['end_date'] = '1/2/2000'
    with pytest.raises(ValueError):
        ssebop.Collection(**args)


def test_Collection_init_swapped_date_exception():
    """Test if Exception is raised when start_date == end_date"""
    args = default_coll_args()
    args['start_date'] = '2017-01-01'
    args['end_date'] = '2017-01-01'
    with pytest.raises(ValueError):
        ssebop.Collection(**args)


def test_Collection_init_invalid_collections_exception():
    """Test if Exception is raised for an invalid collection ID"""
    args = default_coll_args()
    args['collections'] = ['FOO']
    with pytest.raises(ValueError):
        ssebop.Collection(**args)


def test_Collection_init_duplicate_collections_exception():
    """Test if Exception is raised for duplicate Landsat types"""
    args = default_coll_args()
    args['collections'] = ['LANDSAT/LC08/C01/T1_RT_TOA',
                           'LANDSAT/LC08/C01/T1_TOA']
    with pytest.raises(ValueError):
        ssebop.Collection(**args)
    args['collections'] = ['LANDSAT/LC08/C01/T1_SR', 'LANDSAT/LC08/C01/T1_TOA']
    with pytest.raises(ValueError):
        ssebop.Collection(**args)


def test_Collection_init_cloud_cover_exception():
    """Test if Exception is raised for an invalid cloud_cover_max"""
    args = default_coll_args()
    args['cloud_cover_max'] = 'A'
    with pytest.raises(TypeError):
        ssebop.Collection(**args)
    args['cloud_cover_max'] = -1
    with pytest.raises(ValueError):
        ssebop.Collection(**args)
    args['cloud_cover_max'] = 101
    with pytest.raises(ValueError):
        ssebop.Collection(**args)


# # TODO: Test for Error if geometry is not ee.Geometry
# def test_Collection_init_geometry_exception():
#     """Test if Exception is raised for an invalid geometry"""
#     args = default_coll_args()
#     args['geometry'] = 'DEADBEEF'
#     s = ssebop.Collection(**args)
#     assert utils.getinfo(s.geometry) ==


# TODO: Test if a geojson string can be passed for the geometry
# def test_Collection_init_geometry_geojson():
#     """Test that the system:index from a merged collection is parsed"""
#     args = default_coll_args()
#     s = ssebop.Collection(**args)
#     assert utils.getinfo(s._scene_id) == SCENE_ID


def test_Collection_build_default():
    output = utils.getinfo(ssebop.Collection(**default_coll_args())._build())
    assert output['type'] == 'ImageCollection'
    assert parse_scene_id(output) == SCENE_ID_LIST
    assert VARIABLES == sorted(list(set([
        y['id'] for x in output['features'] for y in x['bands']])))


def test_Collection_build_variables():
    output = utils.getinfo(
        ssebop.Collection(**default_coll_args())._build(variables=['ndvi']))
    assert ['ndvi'] == sorted(list(set([
        y['id'] for x in output['features'] for y in x['bands']])))


def test_Collection_build_dates():
    args = default_coll_args()
    args['start_date'] = '2017-07-24'
    output = utils.getinfo(ssebop.Collection(**args)._build(
        start_date='2017-07-16', end_date='2017-07-17'))
    assert parse_scene_id(output) == ['LC08_044033_20170716']


def test_Collection_build_landsat_toa():
    """Test if the Landsat TOA (non RT) collections can be built"""
    args = default_coll_args()
    args['collections'] = ['LANDSAT/LC08/C01/T1_TOA', 'LANDSAT/LE07/C01/T1_TOA']
    output = utils.getinfo(ssebop.Collection(**args)._build())
    assert parse_scene_id(output) == SCENE_ID_LIST
    assert VARIABLES == sorted(list(set([
        y['id'] for x in output['features'] for y in x['bands']])))


def test_Collection_build_landsat_sr():
    """Test if the Landsat SR collections can be built"""
    args = default_coll_args()
    args['collections'] = ['LANDSAT/LC08/C01/T1_SR', 'LANDSAT/LE07/C01/T1_SR']
    output = utils.getinfo(ssebop.Collection(**args)._build())
    assert parse_scene_id(output) == SCENE_ID_LIST
    assert VARIABLES == sorted(list(set([
        y['id'] for x in output['features'] for y in x['bands']])))


def test_Collection_build_exclusive_enddate():
    """Test if the end_date is exclusive"""
    args = default_coll_args()
    args['end_date'] = '2017-07-24'
    output = utils.getinfo(ssebop.Collection(**args)._build())
    assert [x for x in parse_scene_id(output) if int(x[-8:]) >= 20170724] == []


def test_Collection_build_cloud_cover():
    """Test if the cloud cover max parameter is being applied"""
    # CGM - The filtered images should probably be looked up programmatically
    args = default_coll_args()
    args['cloud_cover_max'] = 0.5
    output = utils.getinfo(ssebop.Collection(**args)._build(variables=['et']))
    assert 'LE07_044033_20170724' not in parse_scene_id(output)


# DEADBEEF - I'm not sure what this test was supposed to do
#   It appears to be identical to the exclusive_enddate test above
# def test_Collection_build_model_args():
#     """Test if the end_date is exclusive"""
#     args = default_coll_args()
#     args['end_date'] = '2017-07-24'
#     output = utils.getinfo(ssebop.Collection(**args)._build(variables=['et']))
#     assert [x for x in parse_scene_id(output) if int(x[-8:]) >= 20170724] == []


def test_Collection_build_filter_args():
    args = default_coll_args()
    coll_id = 'LANDSAT/LC08/C01/T1_SR'
    args['collections'] = [coll_id]
    args['geometry'] = ee.Geometry.Rectangle(-125, 35, -120, 40)
    args['filter_args'] = {coll_id: [
        {'type': 'equals', 'leftField': 'WRS_PATH', 'rightValue': 44},
        {'type': 'equals', 'leftField': 'WRS_ROW', 'rightValue': 33}]}
    output = utils.getinfo(ssebop.Collection(**args)._build(variables=['et']))
    assert set([x[5:11] for x in parse_scene_id(output)]) == set(['044033'])


def test_Collection_build_variable_valueerror():
    """Test if Exception is raised for an invalid variable"""
    args = default_coll_args()
    with pytest.raises(ValueError):
        utils.getinfo(ssebop.Collection(**args)._build(variables=['FOO']))


def test_Collection_overpass_default():
    """Test overpass method with default values (variables from Class init)"""
    output = utils.getinfo(ssebop.Collection(**default_coll_args()).overpass())
    assert VARIABLES == sorted(list(set([
        y['id'] for x in output['features'] for y in x['bands']])))
    assert parse_scene_id(output) == SCENE_ID_LIST


def test_Collection_overpass_class_variables():
    """Test that custom class variables are passed through to build function"""
    args = default_coll_args()
    args['variables'] = ['et']
    output = utils.getinfo(ssebop.Collection(**args).overpass())
    assert args['variables'] == sorted(list(set([
        y['id'] for x in output['features'] for y in x['bands']])))


def test_Collection_overpass_method_variables():
    """Test that custom method variables are passed through to build function"""
    output = utils.getinfo(ssebop.Collection(**default_coll_args())
        .overpass(variables=['et']))
    assert ['et'] == sorted(list(set([
        y['id'] for x in output['features'] for y in x['bands']])))


def test_Collection_overpass_no_variables_valueerror():
    """Test if Exception is raised if variables is not set in init or method"""
    args = default_coll_args()
    del args['variables']
    with pytest.raises(ValueError):
        ssebop.Collection(**args).overpass().getInfo()


def test_Collection_interpolate_default():
    """Default t_interval should be custom"""
    output = utils.getinfo(ssebop.Collection(**default_coll_args())
        .interpolate())
    assert output['type'] == 'ImageCollection'
    assert parse_scene_id(output) == ['20170701']
    assert VARIABLES == sorted(list(set([
        y['id'] for x in output['features'] for y in x['bands']])))


def test_Collection_interpolate_variables_custom():
    output = utils.getinfo(ssebop.Collection(**default_coll_args())
        .interpolate(variables=['et']))
    assert ['et'] == sorted(list(set([
        y['id'] for x in output['features'] for y in x['bands']])))


def test_Collection_interpolate_t_interval_daily():
    """Test if the daily time interval parameter works"""
    output = utils.getinfo(ssebop.Collection(**default_coll_args())
        .interpolate(t_interval='daily'))
    assert output['type'] == 'ImageCollection'
    assert parse_scene_id(output)[0] == '20170701'
    assert parse_scene_id(output)[-1] == '20170731'
    assert VARIABLES == sorted(list(set([
        y['id'] for x in output['features'] for y in x['bands']])))


def test_Collection_interpolate_t_interval_monthly():
    """Test if the monthly time interval parameter works"""
    output = utils.getinfo(ssebop.Collection(**default_coll_args())
        .interpolate(t_interval='monthly'))
    assert output['type'] == 'ImageCollection'
    assert parse_scene_id(output) == ['201707']
    assert VARIABLES == sorted(list(set([
        y['id'] for x in output['features'] for y in x['bands']])))


# CGM - Commenting out since it takes a really long time to run
#   This function could probably be be tested for a shorter time period
# def test_Collection_interpolate_t_interval_annual():
#     """Test if the annual time interval parameter works"""
#     args = default_coll_args()
#     args['start_date'] = '2017-01-01'
#     args['end_date'] = '2018-01-01'
#     output = utils.getinfo(ssebop.Collection(**args)
#         .interpolate(t_interval='annual'))
#     assert output['type'] == 'ImageCollection'
#     assert parse_scene_id(output) == ['2017']
#     assert VARIABLES == sorted(list(set([
#         y['id'] for x in output['features'] for y in x['bands']])))


def test_Collection_interpolate_t_interval_custom():
    """Test if the custom time interval parameter works"""
    output = utils.getinfo(ssebop.Collection(**default_coll_args())
        .interpolate(t_interval='custom'))
    assert output['type'] == 'ImageCollection'
    assert parse_scene_id(output) == ['20170701']
    assert VARIABLES == sorted(list(set([
        y['id'] for x in output['features'] for y in x['bands']])))


# TODO: Write test for annual interpolation with a date range that is too short


# def test_Collection_interpolate_interp_days():
#     """Test if the interpolate interp_days parameter works"""
#     # Is there any way to test this without pulling values at a point?


def test_Collection_interpolate_etr_source_exception():
    """Test if Exception is raised if etr_source is not a string"""
    args = default_coll_args()
    args['etr_source'] = []
    with pytest.raises(ValueError):
        utils.getinfo(ssebop.Collection(**args).interpolate())


def test_Collection_interpolate_t_interval_exception():
    """Test if Exception is raised for an invalid t_interval parameter"""
    with pytest.raises(ValueError):
        utils.getinfo(ssebop.Collection(**default_coll_args()) \
            .interpolate(t_interval='DEADBEEF'))


def test_Collection_interpolate_interp_method_exception():
    """Test if Exception is raised for an invalid interp_method parameter"""
    with pytest.raises(ValueError):
        utils.getinfo(ssebop.Collection(**default_coll_args()) \
            .interpolate(interp_method='DEADBEEF'))


def test_Collection_interpolate_interp_days_exception():
    """Test if Exception is raised for an invalid interp_days parameter"""
    with pytest.raises(ValueError):
        utils.getinfo(ssebop.Collection(**default_coll_args()) \
            .interpolate(interp_days=0))


def test_Collection_interpolate_no_variables_exception():
    """Test if Exception is raised if variables is not set in init or method"""
    args = default_coll_args()
    del args['variables']
    with pytest.raises(ValueError):
        utils.getinfo(ssebop.Collection(**args).interpolate())
