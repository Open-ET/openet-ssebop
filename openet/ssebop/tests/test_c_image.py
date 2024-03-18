import datetime
# import pprint

import ee
import pytest

import openet.ssebop as ssebop
import openet.ssebop.utils as utils
# TODO: import utils from openet.core
# import openet.core.utils as utils


COLL_ID = 'LANDSAT/LC08/C02/T1_L2'
SCENE_ID = 'LC08_042035_20150713'
SCENE_DT = datetime.datetime.strptime(SCENE_ID[-8:], '%Y%m%d')
SCENE_DATE = SCENE_DT.strftime('%Y-%m-%d')
SCENE_DOY = int(SCENE_DT.strftime('%j'))
# SCENE_TIME = utils.millis(SCENE_DT)
SCENE_TIME = 1436812419150
SCENE_POINT = (-119.5, 36.0)
TEST_POINT = (-119.44252382373145, 36.04047742246546)

# SCENE_TIME = utils.getinfo(ee.Date(SCENE_DATE).millis())
# SCENE_POINT = (-119.44252382373145, 36.04047742246546)
# SCENE_POINT = utils.getinfo(
#     ee.Image(f'{COLL_ID}/{SCENE_ID}').geometry().centroid())['coordinates']


# # Should these be test fixtures instead?
# # I'm not sure how to make them fixtures and allow input parameters
# def sr_image(red=0.1, nir=0.9, bt=305):
#     """Construct a fake Landsat 8 TOA image with renamed bands"""
#     mask_img = ee.Image(f'{COLL_ID}/{SCENE_ID}').select(['SR_B3']).multiply(0)
#     return ee.Image([mask_img.add(red), mask_img.add(nir), mask_img.add(bt)]) \
#         .rename(['red', 'nir', 'tir'])\
#         .set({
#             'system:time_start': SCENE_TIME,
#             'k1_constant': ee.Number(607.76),
#             'k2_constant': ee.Number(1260.56),
#         })
#     # return ee.Image.constant([red, nir, bt])\
#     #     .rename(['red', 'nir', 'lst']) \
#     #     .set({
#     #         'system:time_start': ee.Date(SCENE_DATE).millis(),
#     #         'k1_constant': ee.Number(607.76),
#     #         'k2_constant': ee.Number(1260.56),
#     #     })


def default_image(lst=305, ndvi=0.8, qa_water=0):
    # First construct a fake 'prepped' input image
    mask_img = ee.Image(f'{COLL_ID}/{SCENE_ID}').select(['SR_B3']).multiply(0)
    return ee.Image([mask_img.add(lst), mask_img.add(ndvi), mask_img.add(qa_water)]) \
        .rename(['lst', 'ndvi', 'qa_water']) \
        .set({
            'system:index': SCENE_ID,
            'system:time_start': SCENE_TIME,
            'system:id': f'{COLL_ID}/{SCENE_ID}',
        })
    # return ee.Image.constant([lst, ndvi]).rename(['lst', 'ndvi']) \
    #     .set({
    #         'system:index': SCENE_ID,
    #         'system:time_start': ee.Date(SCENE_DATE).millis(),
    #         'system:id': f'{COLL_ID}/{SCENE_ID}',
    #     })


# Setting et_reference_source and et_reference_band on the default image to
#   simplify testing but these do not have defaults in the Image class init
def default_image_args(
        lst=305, ndvi=0.85,
        # et_reference_source='IDAHO_EPSCOR/GRIDMET',
        et_reference_source=9.5730,
        et_reference_band='etr',
        et_reference_factor=1,
        et_reference_resample='nearest',
        et_reference_date_type=None,
        dt_source=18,
        tcorr_source=0.9744,
        tmax_source=310.15,
        elev_source=67,
        elr_flag=False,
        et_fraction_type='alfalfa',
        et_fraction_grass_source=None,
        dt_resample='nearest',
        tmax_resample='nearest',
        tcorr_resample='nearest',
        ):
    return {
        'image': default_image(lst=lst, ndvi=ndvi),
        'et_reference_source': et_reference_source,
        'et_reference_band': et_reference_band,
        'et_reference_factor': et_reference_factor,
        'et_reference_resample': et_reference_resample,
        'et_reference_date_type': et_reference_date_type,
        'dt_source': dt_source,
        'tcorr_source': tcorr_source,
        'tmax_source': tmax_source,
        'elev_source': elev_source,
        'elr_flag': elr_flag,
        'et_fraction_type': et_fraction_type,
        'et_fraction_grass_source': et_fraction_grass_source,
        'dt_resample': dt_resample,
        'tmax_resample': tmax_resample,
        'tcorr_resample': tcorr_resample,
    }


def default_image_obj(
        lst=305, ndvi=0.85,
        # et_reference_source='IDAHO_EPSCOR/GRIDMET',
        et_reference_source=9.5730,
        et_reference_band='etr',
        et_reference_factor=1,
        et_reference_resample='nearest',
        et_reference_date_type=None,
        dt_source=18,
        tcorr_source=0.9744,
        tmax_source=310.15,
        elev_source=67,
        elr_flag=False,
        et_fraction_type='alfalfa',
        et_fraction_grass_source=None,
        dt_resample='nearest',
        tmax_resample='nearest',
        tcorr_resample='nearest',
        ):
    return ssebop.Image(**default_image_args(
        lst=lst, ndvi=ndvi,
        et_reference_source=et_reference_source,
        et_reference_band=et_reference_band,
        et_reference_factor=et_reference_factor,
        et_reference_resample=et_reference_resample,
        et_reference_date_type=et_reference_date_type,
        dt_source=dt_source,
        tcorr_source=tcorr_source,
        tmax_source=tmax_source,
        elev_source=elev_source,
        elr_flag=elr_flag,
        et_fraction_type=et_fraction_type,
        et_fraction_grass_source=et_fraction_grass_source,
        dt_resample=dt_resample,
        tmax_resample=tmax_resample,
        tcorr_resample=tcorr_resample,
    ))


def test_Image_init_default_parameters():
    m = ssebop.Image(default_image())
    assert m.et_reference_source is None
    assert m.et_reference_band is None
    assert m.et_reference_factor is None
    assert m.et_reference_resample is None
    assert m.et_reference_date_type is None
    assert m._dt_source == 'projects/earthengine-legacy/assets/projects/usgs-ssebop/dt/daymet_median_v6'
    assert m._tcorr_source == 'FANO'
    assert m._tmax_source == 'projects/earthengine-legacy/assets/projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010'
    assert m._elev_source is None
    assert m._elr_flag is False
    assert m.et_fraction_type == 'alfalfa'
    assert m.et_fraction_grass_source is None
    assert m._dt_resample == 'bilinear'
    assert m._tmax_resample == 'bilinear'
    assert m._tcorr_resample == 'bilinear'
    assert m._C2_LST_CORRECT is True


# Todo: Break these up into separate functions?
def test_Image_init_calculated_properties():
    m = default_image_obj()
    assert utils.getinfo(m._time_start) == SCENE_TIME
    assert utils.getinfo(m._scene_id) == SCENE_ID
    assert utils.getinfo(m._wrs2_tile) == 'p{}r{}'.format(
        SCENE_ID.split('_')[1][:3], SCENE_ID.split('_')[1][3:])


def test_Image_init_date_properties():
    m = default_image_obj()
    assert utils.getinfo(m._date)['value'] == SCENE_TIME
    assert utils.getinfo(m._year) == int(SCENE_DATE.split('-')[0])
    assert utils.getinfo(m._month) == int(SCENE_DATE.split('-')[1])
    assert utils.getinfo(m._start_date)['value'] == utils.millis(SCENE_DT)
    assert utils.getinfo(m._end_date)['value'] == (
        utils.millis(SCENE_DT) + 24 * 3600 * 1000)
    # assert utils.getinfo(m._end_date)['value'] == utils.millis(
    #     SCENE_DT + datetime.timedelta(days=1))
    assert utils.getinfo(m._doy) == SCENE_DOY


def test_Image_init_scene_id_property():
    """Test that the system:index from a merged collection is parsed"""
    input_img = default_image()
    m = ssebop.Image(input_img.set('system:index', '1_2_' + SCENE_ID))
    assert utils.getinfo(m._scene_id) == SCENE_ID


def test_Image_init_elr_flag_str():
    """Test that the elr_flag can be read as a string"""
    assert default_image_obj(elr_flag='FALSE')._elr_flag is False
    assert default_image_obj(elr_flag='true')._elr_flag is True
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj(elr_flag='FOO')._elr_flag)


def test_Image_ndvi_properties():
    """Test if properties are set on the NDVI image"""
    output = utils.getinfo(default_image_obj().ndvi)
    assert output['bands'][0]['id'] == 'ndvi'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


def test_Image_lst_properties():
    """Test if properties are set on the LST image"""
    output = utils.getinfo(default_image_obj().lst)
    assert output['bands'][0]['id'] == 'lst'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


@pytest.mark.parametrize(
    'elev_source',
    [None],
    # TODO: Non-image strings should raise an exception
    # ['', 'DEADBEEF']
    # TODO: Check what happens if source is an image collection
    # [None, '', 'DEADBEEF']
)
def test_Image_elev_source_exception(elev_source):
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj(elev_source=elev_source).elev)


@pytest.mark.parametrize(
    'elev_source, xy, expected',
    [
        # Check string/float constant values
        ['2364.351', [-106.03249, 37.17777], 2364.351],
        [2364.351, [-106.03249, 37.17777], 2364.351],
        # Check custom images
        ['projects/usgs-ssebop/srtm_1km', [-106.03249, 37.17777], 2369.0],
        ['projects/earthengine-legacy/assets/projects/usgs-ssebop/srtm_1km',
         [-106.03249, 37.17777], 2369.0],
        ['USGS/NED', [-106.03249, 37.17777], 2364.351],
    ]
)
def test_Image_elev_source(elev_source, xy, expected, tol=0.001):
    """Test getting elevation values for a single date at a real point"""
    output = utils.point_image_value(default_image_obj(
        elev_source=elev_source).elev, xy)
    assert abs(output['elev'] - expected) <= tol


def test_Image_elev_band_name():
    output = utils.getinfo(default_image_obj().elev)['bands'][0]['id']
    assert output == 'elev'


@pytest.mark.parametrize(
    'dt_source, doy, xy, expected',
    [
        ['projects/usgs-ssebop/dt/daymet_median_v6', SCENE_DOY, TEST_POINT, 20.77],
        ['projects/earthengine-legacy/assets/projects/usgs-ssebop/dt/daymet_median_v6',
         SCENE_DOY, TEST_POINT, 20.77],
    ]
)
def test_Image_dt_source_values(dt_source, doy, xy, expected, tol=0.001):
    """Test getting dT values for a single date at a real point"""
    m = default_image_obj(dt_source=dt_source)
    m._doy = doy
    output = utils.point_image_value(ee.Image(m.dt), xy)
    assert abs(output['dt'] - expected) <= tol


@pytest.mark.parametrize(
    'dt_source, xy, expected',
    [
        ['19.262', [-120.113, 36.336], 19.262],
        [19.262, [-120.113, 36.336], 19.262],
    ]
)
def test_Image_dt_source_constant(dt_source, xy, expected, tol=0.001):
    """Test getting constant dT values for a single date at a real point"""
    m = default_image_obj(dt_source=dt_source)
    output = utils.point_image_value(ee.Image(m.dt), xy)
    assert abs(output['dt'] - expected) <= tol


def test_Image_dt_source_exception():
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj(dt_source='').dt)


@pytest.mark.parametrize(
    'dt_source, doy, xy, expected',
    [
        ['projects/usgs-ssebop/dt/daymet_median_v6', SCENE_DOY, TEST_POINT, 20.77],
    ]
)
def test_Image_dt_scale_factor(dt_source, doy, xy, expected, tol=0.001):
    """Test that dT scale factor property is being applied for daymet_median_v6"""
    m = default_image_obj(dt_source=dt_source)
    m._doy = doy
    output = utils.point_image_value(ee.Image(m.dt), xy)
    assert abs(output['dt'] - expected) <= tol


@pytest.mark.parametrize(
    'tmax_source',
    [
        'projects/usgs-ssebop/tmax/daymet_v3_median_1980_2018',
        'projects/earthengine-legacy/assets/projects/usgs-ssebop/tmax/daymet_v3_median_1980_2018',
        'projects/usgs-ssebop/tmax/daymet_v4_median_1980_2019',
        'projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010',
        '305',
        305,
    ]
)
def test_Image_tmax_source(tmax_source):
    """Test that the tmax source is valid enough to instantiate the class"""
    assert default_image_obj(tmax_source=tmax_source).tmax


@pytest.mark.parametrize(
    'tmax_source, xy, expected',
    [
        ['projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010', TEST_POINT, 310.0847],
        ['projects/earthengine-legacy/assets/projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010',
         TEST_POINT, 310.0847],
        ['projects/usgs-ssebop/tmax/daymet_v3_median_1980_2018', TEST_POINT, 310.15],
        ['projects/usgs-ssebop/tmax/daymet_v4_median_1980_2019', TEST_POINT, 310.155],
        # ['projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010', TEST_POINT, 310.155],
        # Check string/float constant values
        ['305', [-120.113, 36.336], 305],
        [305, [-120.113, 36.336], 305],
    ]
)
def test_Image_tmax_source_values(tmax_source, xy, expected, tol=0.001):
    """Test getting Tmax values for a single date at a real point"""
    m = default_image_obj(tmax_source=tmax_source)
    output = utils.point_image_value(ee.Image(m.tmax), xy)
    assert abs(output['tmax'] - expected) <= tol


@pytest.mark.parametrize(
    'tmax_source',
    [
        'projects/usgs-ssebop/tmax/daymet_v3_max_1980_2018',   # Unsupported statistic
        'projects/usgs-ssebop/dt/daymet_v3_median_1980_2018',  # "tmax" must be in the ID
        'deadbeef',
        '',
    ]
)
def test_Image_tmax_source_exception(tmax_source):
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj(tmax_source=tmax_source).tmax)


@pytest.mark.parametrize(
    'tmax_source, expected',
    [
        ['projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010', {}],
        ['projects/earthengine-legacy/assets/projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010', {}],
        ['projects/usgs-ssebop/tmax/daymet_v3_median_1980_2018', {}],
        ['projects/usgs-ssebop/tmax/daymet_v4_median_1980_2019', {}],
        ['305', {'tmax_source': 'custom_305'}],
        [305, {'tmax_source': 'custom_305'}],
    ]
)
def test_Image_tmax_properties(tmax_source, expected):
    """Test if properties are set on the Tmax image"""
    output = utils.getinfo(default_image_obj(tmax_source=tmax_source).tmax)
    if expected:
        assert output['properties']['tmax_source'] == expected['tmax_source']
    else:
        assert output['properties']['tmax_source'] == tmax_source


# CGM - Test the from_landsat and from_image methods before testing the
#   rest of Image class methods.
# We might want to add a better test for the ndvi method.
def test_Image_from_landsat_c2_sr_default_image():
    """Test that the classmethod is returning a class object"""
    output = ssebop.Image.from_landsat_c2_sr(ee.Image(f'{COLL_ID}/{SCENE_ID}'))
    assert type(output) == type(default_image_obj())


@pytest.mark.parametrize(
    'image_id',
    [
        # 'LANDSAT/LT05/C02/T1_L2/LT05_044033_20110716',
        'LANDSAT/LE07/C02/T1_L2/LE07_044033_20170708',
        'LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716',
        'LANDSAT/LC09/C02/T1_L2/LC09_044033_20220127',
    ]
)
def test_Image_from_landsat_c2_sr_image_id(image_id):
    """Test instantiating the class from a Landsat SR image ID"""
    output = utils.getinfo(ssebop.Image.from_landsat_c2_sr(image_id).ndvi)
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_from_landsat_c2_sr_image():
    """Test instantiating the class from a Landsat SR ee.Image"""
    image_id = 'LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716'
    output = utils.getinfo(ssebop.Image.from_landsat_c2_sr(ee.Image(image_id)).ndvi)
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_from_landsat_c2_sr_exception():
    """Test instantiating the class for an invalid image ID"""
    with pytest.raises(Exception):
        # Intentionally using .getInfo() instead of utils.getinfo()
        ssebop.Image.from_landsat_c2_sr(ee.Image('FOO')).ndvi.getInfo()


def test_Image_from_landsat_c2_sr_scaling():
    """Test if Landsat SR images images are being scaled"""
    sr_img = ee.Image('LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716')
    # CGM - These reflectances should correspond to 0.1 for RED and 0.2 for NIR
    input_img = (
        ee.Image.constant([10909, 10909, 10909, 14545, 10909, 10909, 44177.6, 21824, 0])
        .rename(['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7',
                 'ST_B10', 'QA_PIXEL', 'QA_RADSAT'])
        .set({'SPACECRAFT_ID': ee.String(sr_img.get('SPACECRAFT_ID')),
              'system:id': ee.String(sr_img.get('system:id')),
              'system:index': ee.String(sr_img.get('system:index')),
              'system:time_start': ee.Number(sr_img.get('system:time_start'))})
    )

    # LST correction and cloud score masking do not work with a constant image
    #   and must be explicitly set to False
    output = utils.constant_image_value(ssebop.Image.from_landsat_c2_sr(
        input_img, c2_lst_correct=False,
        cloudmask_args={'cloud_score_flag': False, 'filter_flag': False}).ndvi)
    assert abs(output['ndvi'] - 0.333) <= 0.01

    output = utils.constant_image_value(ssebop.Image.from_landsat_c2_sr(
        input_img, c2_lst_correct=False,
        cloudmask_args={'cloud_score_flag': False, 'filter_flag': False}).lst)
    assert abs(output['lst'] - 300) <= 0.1


def test_Image_from_landsat_c2_sr_cloud_mask_args():
    """Test if the cloud_mask_args parameter can be set (not if it works)"""
    image_id = 'LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716'
    output = ssebop.Image.from_landsat_c2_sr(
        image_id, cloudmask_args={'snow_flag': True, 'cirrus_flag': True})
    assert type(output) == type(default_image_obj())


def test_Image_from_landsat_c2_sr_cloud_score_mask_arg():
    """Test if the cloud_score_flag parameter can be set in cloudmask_args"""
    image_id = 'LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716'
    output = ssebop.Image.from_landsat_c2_sr(
        image_id, cloudmask_args={'cloud_score_flag': True})
    assert type(output) == type(default_image_obj())


def test_Image_from_landsat_c2_sr_c2_lst_correct_arg():
    """Test if the c2_lst_correct parameter can be set (not if it works)"""
    image_id = 'LANDSAT/LC08/C02/T1_L2/LC08_031034_20160702'
    output = ssebop.Image.from_landsat_c2_sr(image_id, c2_lst_correct=True)
    assert type(output) == type(default_image_obj())


def test_Image_from_landsat_c2_sr_c2_lst_correct_fill():
    """Test if the c2_lst_correct fills the LST holes in Nebraska"""
    image_id = 'LANDSAT/LC08/C02/T1_L2/LC08_031034_20160702'
    xy = (-102.08284, 37.81728)
    # CGM - Is the uncorrected test needed?
    uncorrected = utils.point_image_value(
        ssebop.Image.from_landsat_c2_sr(image_id, c2_lst_correct=False).lst, xy)
    assert uncorrected['lst'] is None
    corrected = utils.point_image_value(
        ssebop.Image.from_landsat_c2_sr(image_id, c2_lst_correct=True).lst, xy)
    assert corrected['lst'] > 0
    # # Exact test values copied from openet-core
    # assert abs(corrected['lst'] - 306.83) <= 0.25


@pytest.mark.parametrize(
    'image_id',
    [
        'LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716',
        'LANDSAT/LC09/C02/T1_L2/LC09_044033_20220127',
    ]
)
def test_Image_from_image_id(image_id):
    """Test instantiating the class using the from_image_id method"""
    output = utils.getinfo(ssebop.Image.from_image_id(image_id).ndvi)
    assert output['properties']['system:index'] == image_id.split('/')[-1]
    assert output['properties']['image_id'] == image_id


def test_Image_from_method_kwargs():
    """Test that the init parameters can be passed through the helper methods"""
    assert ssebop.Image.from_landsat_c2_sr(
        'LANDSAT/LC08/C02/T1_L2/LC08_042035_20150713',
        elev_source='DEADBEEF')._elev_source == 'DEADBEEF'


# CGM - Test tcorr_image since it is called by tcorr_stats
def test_Image_tcorr_image_values(lst=300, ndvi=0.85, tmax=306, expected=0.9804, tol=0.0001):
    output_img = default_image_obj(lst=lst, ndvi=ndvi, tmax_source=tmax).tcorr_image
    output = utils.point_image_value(output_img, TEST_POINT)
    assert abs(output['tcorr'] - expected) <= tol


@pytest.mark.parametrize(
    # Note: These are made up values
    'lst, ndvi, tmax, expected',
    [
        [300, 0.74, 306, None],  # NDVI < 0.75
        [269, 0.69, 306, None],  # LST < 270
        # TODO: Add a test for the NDVI smoothing
    ]
)
def test_Image_tcorr_image_nodata(lst, ndvi, tmax, expected):
    output = utils.constant_image_value(default_image_obj(
        lst=lst, ndvi=ndvi, tmax_source=tmax).tcorr_image)
    assert output['tcorr'] is None and expected is None


def test_Image_tcorr_image_band_name():
    output = utils.getinfo(default_image_obj().tcorr_image)
    assert output['bands'][0]['id'] == 'tcorr'


def test_Image_tcorr_image_properties():
    """Test if properties are set on the tcorr image"""
    tmax_source = 'projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010'
    output = utils.getinfo(default_image_obj(tmax_source=tmax_source).tcorr_image)
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['tmax_source'] == tmax_source


# CGM - Then test tcorr_stats since it is called by the other tcorr functions
def test_Image_tcorr_stats_constant(tcorr=0.993548387, count=40564857, tol=0.00000001):
    output = utils.getinfo(default_image_obj(
        ndvi=0.85, lst=308, dt_source=10, elev_source=50,
        tcorr_source=0.98, tmax_source=310).tcorr_stats)
    assert abs(output['tcorr_value'] - tcorr) <= tol
    assert output['tcorr_count'] == count


# NOTE: These values seem to change by small amounts for no reason
@pytest.mark.parametrize(
    'image_id, tmax_source, expected',
    [
        # DEADBEEF
        # ['LANDSAT/LC08/C02/T1_L2/LC08_042035_20150713',
        #  'projects/usgs-ssebop/tmax/daymet_v3_median_1980_2018',
        #  {'tcorr_value': 0.9757137560969104, 'tcorr_count': 221975}],
        # projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010
        ['LANDSAT/LC08/C02/T1_L2/LC08_042035_20150713',
         'projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010',
         {'tcorr_value': 0.974979476478202, 'tcorr_count': 221975}],
        ['LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716',
         'projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010',
         {'tcorr_value': 0.9851211164517142, 'tcorr_count': 1365750}],
        ['LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716',
         'projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010_elr',
         {'tcorr_value': 0.9851211164517142, 'tcorr_count': 1365750}],
    ]
)
def test_Image_tcorr_stats_landsat(image_id, tmax_source, expected, tol=0.000001):
    output = utils.getinfo(ssebop.Image.from_image_id(
        image_id, tmax_source=tmax_source, tmax_resample='nearest',
        c2_lst_correct=False).tcorr_stats)
    assert abs(output['tcorr_value'] - expected['tcorr_value']) <= tol
    assert abs(output['tcorr_count'] - expected['tcorr_count']) <= 10
    # assert output['tcorr_count'] == expected['tcorr_count']
    # assert (abs(output['tcorr_count'] == expected['tcorr_count']) /
    #         expected['tcorr_count']) <= 0.0000001


@pytest.mark.parametrize(
    'tcorr_src, tmax_src, image_id, xy, expected',
    [
        ['FANO', 'projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010',
         'LANDSAT/LC08/C02/T1_L2/LC08_042035_20150713', SCENE_POINT, 0.9803095962281566],
        ['FANO',
         'projects/earthengine-legacy/assets/projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010',
         'LANDSAT/LC08/C02/T1_L2/LC08_042035_20150713', SCENE_POINT, 0.9803095962281566],
    ]
)
def test_Image_tcorr_fano_source(tcorr_src, tmax_src, image_id, xy, expected, tol=0.000001):
    """Test getting Tcorr value and index for a single date at a real point"""
    tcorr_img = ssebop.Image.from_image_id(
        image_id, tcorr_source=tcorr_src, tmax_source=tmax_src, tmax_resample='nearest',
        c2_lst_correct=False).tcorr
    tcorr = utils.point_image_value(tcorr_img, xy)
    assert abs(tcorr['tcorr'] - expected) <= tol


@pytest.mark.parametrize(
    'tcorr_src',
    [
        '',
        'DEADBEEF',
        'SCENE_DEADBEEF',
    ]
)
def test_Image_tcorr_source_exception(tcorr_src):
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj(tcorr_source=tcorr_src).tcorr)


@pytest.mark.parametrize(
    'tcorr_src, tmax_src',
    [
        ['FANO', 'DEADBEEF'],
    ]
)
def test_Image_tcorr_tmax_source_exception(tcorr_src, tmax_src):
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj(tcorr_source=tcorr_src, tmax_source=tmax_src).tcorr)


def test_Image_et_fraction_properties():
    """Test if properties are set on the ETf image"""
    output = utils.getinfo(default_image_obj().et_fraction)
    assert output['bands'][0]['id'] == 'et_fraction'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME


@pytest.mark.parametrize(
    'dt, elev, tcorr, tmax, expected', [[10, 50, 0.98, 310, 0.88]]
)
def test_Image_et_fraction_values(dt, elev, tcorr, tmax, expected, tol=0.0001):
    output_img = default_image_obj(
        dt_source=dt, elev_source=elev,
        tcorr_source=tcorr, tmax_source=tmax).et_fraction
    output = utils.point_image_value(ee.Image(output_img), TEST_POINT)
    assert abs(output['et_fraction'] - expected) <= tol
    # assert output['et_fraction'] > 0


@pytest.mark.parametrize(
    # Note: These are made up values
    'lst, ndvi, dt, elev, tcorr, tmax, elr_flag, expected',
    [
        # Test ELR flag
        [305, 0.80, 15, 2000, 0.98, 310, False, 0.9200],
        [305, 0.80, 15, 2000, 0.98, 310, True, 0.8220],
        [315, 0.10, 15, 2000, 0.98, 310, True, 0.1553],
    ]
)
def test_Image_et_fraction_elr_param(lst, ndvi, dt, elev, tcorr, tmax, elr_flag,
                                     expected, tol=0.0001):
    """Test that elr_flag works and changes ETf values"""
    output_img = default_image_obj(
        lst=lst, ndvi=ndvi, dt_source=dt, elev_source=elev,
        tcorr_source=tcorr, tmax_source=tmax, elr_flag=elr_flag).et_fraction
    output = utils.point_image_value(ee.Image(output_img), TEST_POINT)
    assert abs(output['et_fraction'] - expected) <= tol


def test_Image_from_landsat_c2_sr_et_fraction():
    """Test if ETf can be built for a Landsat SR image"""
    image_id = 'LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716'
    output = utils.getinfo(ssebop.Image.from_landsat_c2_sr(image_id).et_fraction)
    assert output['properties']['system:index'] == image_id.split('/')[-1]


# # Testing for the source not being set will be needed in a future version
# #   when NLDAS is not set as the default source
# def test_Image_et_fraction_type_grass_source_not_set():
#     """Raise an exception if fraction type is grass but source is not set"""
#     with pytest.raises(ValueError):
#         utils.getinfo(default_image_obj(et_fraction_type='grass').et_fraction)
#
#
# # Testing for the source not being set will be needed in a future version
# #   when NLDAS is not set as the default source
# def test_Image_et_fraction_type_grass_source_empty():
#     """Raise an exception if fraction type is grass but source is not set"""
#     with pytest.raises(ValueError):
#         utils.getinfo(default_image_obj(
#             et_fraction_type='grass', et_fraction_grass_source='').et_fraction)


# # Checking if the source is "supported" is currently handled in the model.py function
# #   and is probably redundant here, but leaving commented out code for now
# def test_Image_et_fraction_type_grass_source_exception():
#     """Raise an exception if fraction type is grass but source is not supported"""
#     with pytest.raises(ValueError):
#         utils.getinfo(default_image_obj(
#             et_fraction_type='grass', et_fraction_grass_source='deadbeef').et_fraction)


@pytest.mark.parametrize(
    'et_fraction_type, etf_grass_source, expected',
    [
        ['alfalfa', None, 0.88],
        ['grass', 'NASA/NLDAS/FORA0125_H002', 0.88 * 1.24],
        # Check that mixed case fraction types are supported
        ['Grass', 'NASA/NLDAS/FORA0125_H002', 0.88 * 1.24],
        # Check that number sources are supported
        ['grass', 1.24, 0.88 * 1.24],
        # Currently checking all other supported sources in model.py test
        # ['grass', 'ECMWF/ERA5_LAND/HOURLY', 0.88 * 1.15],
    ]
)
def test_Image_et_fraction_type(et_fraction_type, etf_grass_source, expected, tol=0.01):
    output_img = default_image_obj(
        dt_source=10, elev_source=50, tcorr_source=0.98, tmax_source=310,
        et_fraction_type=et_fraction_type,
        et_fraction_grass_source=etf_grass_source).et_fraction
    output = utils.point_image_value(ee.Image(output_img), TEST_POINT)
    assert abs(output['et_fraction'] - expected) <= tol


def test_Image_et_reference_properties():
    """Test if properties are set on the ETr image"""
    output = utils.getinfo(default_image_obj().et_reference)
    assert output['bands'][0]['id'] == 'et_reference'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


@pytest.mark.parametrize(
    'source, band, factor, xy, expected',
    [
        ['IDAHO_EPSCOR/GRIDMET', 'etr', 1, TEST_POINT, 9.5730],
        ['IDAHO_EPSCOR/GRIDMET', 'etr', 0.85, TEST_POINT, 9.5730 * 0.85],
        ['projects/openet/assets/reference_et/california/cimis/daily/v1',
         'etr', 1, TEST_POINT, 10.0760],
        ['projects/openet/reference_et/california/cimis/daily/v1',
         'etr', 1, TEST_POINT, 10.0760],
        # DEADBEEF
        # ['projects/earthengine-legacy/assets/projects/climate-engine/cimis/daily',
        #  'ETr_ASCE', 1, TEST_POINT, 10.0220],
        # CGM - Why are these not the same?
        # ['projects/earthengine-legacy/assets/projects/openet/reference_et/cimis/daily',
        #  'etr_asce', 1, TEST_POINT, 10.0760],
        [10, 'FOO', 1, TEST_POINT, 10.0],
        [10, 'FOO', 0.85, TEST_POINT, 8.5],
    ]
)
def test_Image_et_reference_source(source, band, factor, xy, expected, tol=0.001):
    """Test getting reference ET values for a single date at a real point"""
    output = utils.point_image_value(default_image_obj(
        et_reference_source=source, et_reference_band=band,
        et_reference_factor=factor).et_reference, xy)
    assert abs(output['et_reference'] - expected) <= tol


@pytest.mark.parametrize(
    'date_type, source, band, xy, expected',
    [
        ['doy', 'projects/usgs-ssebop/pet/gridmet_median_v1',
         'etr', TEST_POINT, 10.2452],
        # Check that date_type parameter is not case sensitive
        ['DOY', 'projects/usgs-ssebop/pet/gridmet_median_v1',
         'eto', TEST_POINT, 7.7345],
        # None or "daily" is the default behavior of pulling the target date
        [None, 'IDAHO_EPSCOR/GRIDMET', 'etr', TEST_POINT, 9.5730],
        ['daily', 'IDAHO_EPSCOR/GRIDMET', 'etr', TEST_POINT, 9.5730],
    ]
)
def test_Image_et_reference_date_type(date_type, source, band, xy, expected, tol=0.001):
    """Test if the date_type parameter works"""
    output = utils.point_image_value(default_image_obj(
        et_reference_source=source, et_reference_band=band,
        et_reference_date_type=date_type).et_reference, xy)
    assert abs(output['et_reference'] - expected) <= tol


# TODO: Write a test to check that an exception is raise if the source collection
#   doesn't have a DOY property when the date type is "DOY"


# TODO: Exception should be raised if source is not named like a collection
#   Currently an exception is only raise if not a string or number
def test_Image_et_reference_source_exception():
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj(
            et_reference_source=ee.Image.constant(10)).et_reference)


def test_Image_et_properties():
    """Test if properties are set on the ET image"""
    output = utils.getinfo(default_image_obj().et)
    assert output['bands'][0]['id'] == 'et'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


def test_Image_et_values(tol=0.0001):
    output_img = default_image_obj(
        ndvi=0.5, lst=308, dt_source=10, elev_source=50,
        tcorr_source=0.98, tmax_source=310, et_reference_source=10).et
    output = utils.point_image_value(output_img, TEST_POINT)
    assert abs(output['et'] - 5.8) <= tol


def test_Image_from_landsat_c2_sr_et():
    """Test if ET can be built for a Landsat image"""
    image_id = 'LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716'
    output = utils.getinfo(ssebop.Image.from_landsat_c2_sr(
        image_id, et_reference_source='IDAHO_EPSCOR/GRIDMET',
        et_reference_band='etr').et)
    assert output['properties']['system:index'] == image_id.split('/')[-1]


def test_Image_mask_properties():
    """Test if properties are set on the time image"""
    output = utils.getinfo(default_image_obj().mask)
    assert output['bands'][0]['id'] == 'mask'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


def test_Image_mask_values():
    output_img = default_image_obj(
        ndvi=0.5, lst=308, dt_source=10, elev_source=50,
        tcorr_source=0.98, tmax_source=310).mask
    output = utils.point_image_value(output_img, TEST_POINT)
    assert output['mask'] == 1


def test_Image_time_properties():
    """Test if properties are set on the time image"""
    output = utils.getinfo(default_image_obj().time)
    assert output['bands'][0]['id'] == 'time'
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


@pytest.mark.parametrize(
    'image_id, xy, expected',
    [
        ['LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716', (-122.15, 38.6153), 0],
        ['LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716', (-122.2571, 38.6292), 1],
    ]
)
def test_Image_qa_water_mask(image_id, xy, expected):
    """Test if qa pixel waterband exists"""
    output_img = ssebop.Image.from_image_id(image_id)
    mask_img = output_img.qa_water_mask
    output = utils.point_image_value(mask_img, xy)
    assert output['qa_water'] == expected


def test_Image_time_values():
    # The time band should be the 0 UTC datetime, not the system:time_start
    # The time image is currently being built from the et_fraction image, so all
    #   the ancillary values must be set.
    output_img = default_image_obj(
        ndvi=0.5, lst=308, dt_source=10, elev_source=50,
        tcorr_source=0.98, tmax_source=310).time
    output = utils.point_image_value(output_img, TEST_POINT)
    assert output['time'] == utils.millis(SCENE_DT)


def test_Image_calculate_properties():
    """Test if properties are set on the output image"""
    output = utils.getinfo(default_image_obj().calculate(['ndvi']))
    assert output['properties']['system:index'] == SCENE_ID
    assert output['properties']['system:time_start'] == SCENE_TIME
    assert output['properties']['image_id'] == f'{COLL_ID}/{SCENE_ID}'


def test_Image_calculate_variables_default():
    output = utils.getinfo(default_image_obj().calculate())
    assert {x['id'] for x in output['bands']} == {'et', 'et_reference', 'et_fraction'}


def test_Image_calculate_variables_custom():
    variables = {'ndvi'}
    output = utils.getinfo(default_image_obj().calculate(variables))
    assert {x['id'] for x in output['bands']} == variables


def test_Image_calculate_variables_all():
    variables = {'et', 'et_fraction', 'et_reference', 'mask', 'ndvi', 'time'}
    output = utils.getinfo(default_image_obj().calculate(variables=variables))
    assert {x['id'] for x in output['bands']} == variables


def test_Image_calculate_values(tol=0.0001):
    """Test if the calculate method returns ET, ETr, and ETf values"""
    output_img = default_image_obj(
            ndvi=0.5, lst=308, dt_source=10, elev_source=50,
            tcorr_source=0.98, tmax_source=310, et_reference_source=10)\
        .calculate(['et', 'et_reference', 'et_fraction'])
    output = utils.point_image_value(output_img, TEST_POINT)
    assert abs(output['et'] - 5.8) <= tol
    assert abs(output['et_reference'] - 10) <= tol
    assert abs(output['et_fraction'] - 0.58) <= tol


def test_Image_calculate_variables_valueerror():
    """Test if calculate method raises a valueerror for invalid variables"""
    with pytest.raises(ValueError):
        utils.getinfo(default_image_obj().calculate(['FOO']))


@pytest.mark.parametrize(
    'image_id, xy',
    [
        ['LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716', (-122.2571, 38.6292)],
    ]
)
def test_Image_et_reference_water_nodata(image_id, xy):
    """Test if water pixels are being masked in the et_reference band"""
    output = utils.point_image_value(ssebop.Image.from_image_id(
        image_id, et_reference_source='IDAHO_EPSCOR/GRIDMET',
        et_reference_band='etr').et_reference, xy)
    assert output['et_reference'] is not None


# def test_Image_et_fraction_properties():
#     """Test if properties are set on the ETf image"""
#     output = utils.getinfo(default_image_obj().et_fraction)
#     assert output['bands'][0]['id'] == 'et_fraction'
#     assert output['properties']['system:index'] == SCENE_ID
#     assert output['properties']['system:time_start'] == SCENE_TIME
#
#
# @pytest.mark.parametrize(
#     'dt, elev, tcorr, tmax, expected', [[10, 50, 0.98, 310, 0.88]]
# )
# def test_Image_et_fraction_values(dt, elev, tcorr, tmax, expected, tol=0.0001):
#     output_img = default_image_obj(
#         dt_source=dt, elev_source=elev,
#         tcorr_source=tcorr, tmax_source=tmax).et_fraction
#     output = utils.point_image_value(ee.Image(output_img), TEST_POINT)
#     assert abs(output['et_fraction'] - expected) <= tol
#     # assert output['et_fraction'] > 0
