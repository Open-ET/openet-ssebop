import argparse
import datetime
import logging
import math
import pprint
import re
import time

import ee
from flask import abort, Response
from google.cloud import tasks_v2

import openet.ssebop as ssebop
import openet.core.utils as utils

logging.getLogger('googleapiclient').setLevel(logging.ERROR)

TOOL_NAME = 'tcorr_gridded_cloud_function'
TOOL_VERSION = '0.1.0'

# TODO: Move all of these to config.py?
FUNCTION_URL = 'https://us-central1-ssebop.cloudfunctions.net'
FUNCTION_NAME = 'tcorr-gridded-worker'
GEE_KEY_FILE = 'privatekey.json'
PROJECT_NAME = 'ssebop'
TASK_LOCATION = 'us-central1'
TASK_QUEUE = 'default'
START_DAY_OFFSET = 60
END_DAY_OFFSET = 0

STUDY_AREA_COLL_ID = 'TIGER/2018/States'
STUDY_AREA_PROPERTY = 'STUSPS'
STUDY_AREA_FEATURES = ['CONUS']
MGRS_FTR_COLL_ID = 'projects/earthengine-legacy/assets/projects/openet/mgrs/conus_gridmet/zones'
COLLECTIONS = ['LANDSAT/LC08/C02/T1_L2', 'LANDSAT/LE07/C02/T1_L2']
# COLLECTIONS_RT = ['LANDSAT/LC08/C01/T1_RT_TOA', 'LANDSAT/LE07/C01/T1_RT_TOA']
CLOUD_COVER = 70
TMAX_SOURCE = 'projects/earthengine-legacy/assets/projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010_elr'
TCORR_SOURCE = 'GRIDDED_COLD'
CLIP_OCEAN_FLAG = True
FILL_CLIMO_FLAG = True
# MGRS_TILES = []
# UTM_ZONES = list(range(10, 20))
# WRS2_TILES = []
# STUDY_AREA_EXTENT = [-125, 25, -65, 49]

ASSET_ID_FMT = '{coll_id}/{scene_id}'

ASSET_COLL_ID = f'projects/earthengine-legacy/assets/' \
                f'projects/usgs-ssebop/tcorr_gridded/c02/{TMAX_SOURCE.split("/")[-1]}'
EXPORT_ID_FMT = 'tcorr_gridded_{product}_{scene_id}'
EXPORT_GEO = [5000, 0, 15, 0, -5000, 15]
TCORR_INDICES = {
    'GRIDDED': 0,
    'GRIDDED_COLD': 1,
    'GRIDDED_HOT': 2,
    'SCENE': 3,
    'MONTH': 4,
    'SEASON': 5,
    'ANNUAL': 6,
    'DEFAULT': 7,
    'USER': 8,
    'NODATA': 9,
}
WRS2_SKIP_LIST = [
    'p049r026',  # Vancouver Island, Canada
    # 'p047r031', # North California coast
    'p042r037',  # San Nicholas Island, California
    # 'p041r037', # South California coast
    'p040r038', 'p039r038', 'p038r038', # Mexico (by California)
    'p037r039', 'p036r039', 'p035r039', # Mexico (by Arizona)
    'p034r039', 'p033r039', # Mexico (by New Mexico)
    'p032r040',  # Mexico (West Texas)
    'p029r041', 'p028r042', 'p027r043', 'p026r043',  # Mexico (South Texas)
    'p019r040', 'p018r040', # West Florida coast
    'p016r043', 'p015r043', # South Florida coast
    'p014r041', 'p014r042', 'p014r043', # East Florida coast
    'p013r035', 'p013r036', # North Carolina Outer Banks
    'p013r026', 'p012r026', # Canada (by Maine)
    'p011r032', # Rhode Island coast
]
WRS2_PATH_SKIP_LIST = [9, 49]
WRS2_ROW_SKIP_LIST = [25, 24, 43]


def tcorr_gridded_asset_ingest(image_id, overwrite_flag=True,
                               gee_key_file=None):
    """Generate gridded Tcorr asset for a single Landsat image

    Parameters
    ----------
    image_id : str
    overwrite_flag : bool, optional
        If True, overwrite existing assets (the default is True).
    gee_key_file : str, optional
        If not set, will attempt to initialize using the user credentials.

    Returns
    -------
    str : response string

    """
    logging.info(f'Gridded Tcorr - {image_id}')

    model_args = {'tmax_source': TMAX_SOURCE}

    coll_id, scene_id = image_id.rsplit('/', 1)
    logging.debug(f'  Scene: {scene_id}')
    logging.debug(f'  Collection: {coll_id}')

    wrs2_path = int(scene_id[5:8])
    wrs2_row = int(scene_id[8:11])
    wrs2_tile = 'p{:03d}r{:03d}'.format(wrs2_path, wrs2_row)
    logging.debug(f'  WRS2: {wrs2_tile}')

    export_dt = datetime.datetime.strptime(scene_id[12:20], '%Y%m%d')
    # export_date = export_dt.strftime('%Y-%m-%d')
    logging.debug(f'  Date: {export_dt.strftime("%Y-%m-%d")}')

    export_id = EXPORT_ID_FMT.format(
        product=TMAX_SOURCE.split("/")[-1].lower(), scene_id=scene_id)
    logging.debug(f'  Export ID: {export_id}')

    asset_id = f'{ASSET_COLL_ID}/{scene_id}'
    logging.debug(f'  Asset ID: {asset_id}')

    # TODO: Move to config.py?
    logging.debug('\nInitializing Earth Engine')
    if gee_key_file:
        logging.debug(f'  Using service account key file: {gee_key_file}')
        # The "EE_ACCOUNT" parameter is not used if the key file is valid
        ee.Initialize(ee.ServiceAccountCredentials('', key_file=gee_key_file))
    else:
        ee.Initialize()

    # Remove the asset if it already exists
    if ee.data.getInfo(asset_id):
        if not overwrite_flag:
            return f'{export_id} - Asset already exists and overwrite is False\n'
        try:
            ee.data.deleteAsset(asset_id)
        except:
            # logging.info('  Error removing existing asset')
            return f'{export_id} - Error removing existing asset'

    # CGM - These checks are probably not necessary since they are hardcoded above
    if TCORR_SOURCE.upper() not in ['GRIDDED', 'GRIDDED_COLD']:
        logging.error(f'Unsupported tcorr_source: {TCORR_SOURCE}')
        return f'{export_id} - Unsupported tcorr_source: {TCORR_SOURCE}'

    if (TMAX_SOURCE.upper() not in ['DAYMET_MEDIAN_V2'] and
            not re.match('^projects/.+/tmax/.+_(mean|median)_\d{4}_\d{4}(_\w+)?',
                         TMAX_SOURCE)):
        logging.error(f'Unsupported tmax_source: {TMAX_SOURCE}')
        input('ENTER')
        return f'{export_id} - Unsupported tmax_source: {TMAX_SOURCE}'
    logging.debug(f'  Tmax Source:  {TMAX_SOURCE}')

    # Get a Tmax image to set the Tcorr values to
    # logging.debug('  Tmax')
    # if 'MEDIAN' in TMAX_SOURCE.upper():
    #     tmax_coll_id = 'projects/earthengine-legacy/assets/' \
    #                    'projects/usgs-ssebop/tmax/{}'.format(TMAX_SOURCE.lower())
    #     tmax_coll = ee.ImageCollection(tmax_coll_id)
    #     tmax_mask = ee.Image(tmax_coll.first()).select([0]).multiply(0)
    # else:
    #     # TODO: Add support for other tmax sources
    #     logging.error(f'Unsupported tmax_source: {TMAX_SOURCE}')
    #     return f'{export_id} - Unsupported tmax_source: {TMAX_SOURCE}'

    # Get the input image grid and spatial reference
    image_info = ee.Image(image_id).select([2]).getInfo()
    image_geo = image_info['bands'][0]['crs_transform']
    image_crs = image_info['bands'][0]['crs']
    image_shape = image_info['bands'][0]['dimensions']
    # Transform format: [30, 0, 591285, 0, -30, 4256115]
    image_extent = [
        image_geo[2], image_geo[5] + image_shape[1] * image_geo[4],
        image_geo[2] + image_shape[0] * image_geo[0], image_geo[5]]
    logging.debug(f'  Image CRS:    {image_crs}')
    logging.debug(f'  Image Geo:    {image_geo}')
    logging.debug(f'  Image Extent: {image_extent}')
    logging.debug(f'  Image Shape:  {image_shape}')

    # Adjust the image extent to the coarse resolution grid
    export_cs = EXPORT_GEO[0]
    export_extent = [
        round(math.floor((image_extent[0] - EXPORT_GEO[2]) / export_cs) *
              export_cs + EXPORT_GEO[2], 8),
        round(math.floor((image_extent[1] - EXPORT_GEO[5]) / export_cs) *
              export_cs + EXPORT_GEO[5], 8),
        round(math.ceil((image_extent[2] - EXPORT_GEO[2]) / export_cs) *
              export_cs + EXPORT_GEO[2], 8),
        round(math.ceil((image_extent[3] - EXPORT_GEO[5]) / export_cs) *
              export_cs + EXPORT_GEO[5], 8),
    ]
    export_geo = [export_cs, 0, export_extent[0], 0,
                  -export_cs, export_extent[3]]
    export_shape = [
        int(abs(export_extent[2] - export_extent[0]) / EXPORT_GEO[0]),
        int(abs(export_extent[3] - export_extent[1]) / EXPORT_GEO[0])]
    logging.debug(f'  Export CRS:    {image_crs}')
    logging.debug(f'  Export Geo:    {export_geo}')
    logging.debug(f'  Export Extent: {export_extent}')
    logging.debug(f'  Export Shape:  {export_shape}')

    # CGM - Why are we not using the from_image_id() method?
    # t_obj = ssebop.Image.from_image_id(ee.Image(image_id), **model_args)
    if coll_id.endswith('_L2'):
        t_obj = ssebop.Image.from_landsat_c2_sr(
            sr_image=ee.Image(image_id),
            cloudmask_args={'cirrus_flag': True, 'dilate_flag': True,
                            'shadow_flag': True, 'snow_flag': True},
            **model_args)
    elif coll_id.endswith('_SR'):
        t_obj = ssebop.Image.from_landsat_c1_sr(ee.Image(image_id), **model_args)
    elif coll_id.endswith('_TOA'):
        t_obj = ssebop.Image.from_landsat_c1_toa(ee.Image(image_id), **model_args)
    else:
        logging.error('Unsupported Landsat collection')
        return f'{export_id} - Unsupported Landsat collection'

    # CGM - Intentionally not calling the tcorr method directly since
    #   there may be compositing with climos or the scene average
    # if TCORR_SOURCE.upper() == 'GRIDDED':
    tcorr_img = t_obj.tcorr_gridded
    # tcorr_img = t_obj.tcorr

    # Properties that the climo tcorr image might change need to be set
    #   before the climo is used
    # It would probably make more sense to move all of the property
    #   setting to right here instead of down below
    tcorr_img = tcorr_img.set({
        'tcorr_index': TCORR_INDICES[TCORR_SOURCE],
    })

    if FILL_CLIMO_FLAG:
        logging.debug('    Checking if monthly climo should be applied')
        # The climo collection names are hardcoded this way in the export scripts
        tcorr_month_coll_id = ASSET_COLL_ID + '_monthly'
        tcorr_month_coll = ee.ImageCollection(tcorr_month_coll_id)\
            .filterMetadata('wrs2_tile', 'equals', wrs2_tile)\
            .filterMetadata('month', 'equals', export_dt.month)\
            .select(['tcorr'])
        # Setting the quality to 0 here causes it to get masked below
        #   We might want to have it actually be 0 instead
        tcorr_month_img = tcorr_month_coll.first()\
            .addBands([tcorr_month_coll.first().multiply(0).rename(['quality'])])\
            .set({'tcorr_coarse_count': None})
        tcorr_img = ee.Algorithms.If(
            ee.Number(tcorr_img.get('tcorr_coarse_count')).eq(0)
                .And(tcorr_month_coll.size().gt(0)),
            tcorr_month_img,
            tcorr_img)

    # Clip to the Landsat image footprint
    # Clear the transparency mask (from clipping)
    tcorr_img = ee.Image(tcorr_img).clip(ee.Image(image_id).geometry())
    tcorr_img = tcorr_img.updateMask(tcorr_img.unmask(0))

    if CLIP_OCEAN_FLAG:
        tcorr_img = tcorr_img.updateMask(ee.Image('projects/openet/ocean_mask'))
        # # CGM - The NLCD mask will only work for CONUS
        # output_img = output_img.updateMask(
        #     ee.Image('USGS/NLCD/NLCD2016').select(['landcover']).mask())

    tcorr_img = tcorr_img\
        .set({
            'CLOUD_COVER': image_info['properties']['CLOUD_COVER'],
            'CLOUD_COVER_LAND': image_info['properties']['CLOUD_COVER_LAND'],
            # 'SPACECRAFT_ID': image.get('SPACECRAFT_ID'),
            'coll_id': coll_id,
            'date_ingested': datetime.datetime.today().strftime('%Y-%m-%d'),
            'date': export_dt.strftime('%Y-%m-%d'),
            'doy': int(export_dt.strftime('%j')),
            'model_name': 'SSEBOP',
            'model_version': ssebop.__version__,
            'month': int(export_dt.month),
            'realtime': 'true' if '/T1_RT' in coll_id else 'false',
            'scene_id': scene_id,
            'system:time_start': image_info['properties']['system:time_start'],
            'tcorr_index': TCORR_INDICES[TCORR_SOURCE.upper()],
            # 'tcorr_source': TCORR_SOURCE,
            'tmax_source': TMAX_SOURCE,
            # 'tmax_source': TMAX_SOURCE.replace(
            #     'projects/earthengine-legacy/assets/', ''),
            'tool_name': TOOL_NAME,
            'tool_version': TOOL_VERSION,
            'wrs2_path': wrs2_path,
            'wrs2_row': wrs2_row,
            'wrs2_tile': wrs2_tile,
            'year': int(export_dt.year),
        })
    # pprint.pprint(output_img.getInfo()['properties'])
    # input('ENTER')

    logging.debug('  Building export task')
    task = ee.batch.Export.image.toAsset(
        image=tcorr_img,
        description=export_id,
        assetId=asset_id,
        crs=image_crs,
        crsTransform='[' + ','.join(list(map(str, export_geo))) + ']',
        dimensions='{0}x{1}'.format(*export_shape),
    )

    logging.debug('  Starting export task')
    utils.ee_task_start(task)

    return f'{export_id} - {task.id}\n'


def tcorr_gridded_images(start_dt, end_dt, overwrite_flag=False,
                         gee_key_file=None, realtime_flag=False):
    """Identify missing gridded Tcorr assets

    Parameters
    ----------
    start_dt : datetime
    end_dt : datetime
    overwrite_flag : bool, optional
    gee_key_file : str, optional
        If not set, will attempt to initialize using the user credentials
    realtime_flag : bool, optional
        If True, build the image list using the Landsat realtime collections
        If False, allow existing realtime images to be overwritten

    Returns
    -------
    list : Landsat image IDs

    """
    logging.info('Building gridded Tcorr image list')

    model_args = {'tmax_source': 'DAYMET_MEDIAN_V2'}

    start_date = start_dt.strftime('%Y-%m-%d')
    end_date = end_dt.strftime('%Y-%m-%d')
    next_date = (end_dt + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    logging.info(f'  Start Date: {start_date}')
    logging.info(f'  End Date:   {end_date}')

    # TODO: Add a check for dates before 2013, since L5 isn't in collections

    # logging.info(f'  Realtime:   {realtime_flag}')
    # if realtime_flag:
    #     collections = COLLECTIONS_RT[:]
    # else:
    #     collections = COLLECTIONS[:]
    collections = COLLECTIONS[:]

    # TODO: Move to config.py?
    logging.debug('\nInitializing Earth Engine')
    if gee_key_file:
        logging.debug(f'  Using service account key file: {gee_key_file}')
        # The "EE_ACCOUNT" parameter is not used if the key file is valid
        ee.Initialize(ee.ServiceAccountCredentials('', key_file=gee_key_file))
    else:
        ee.Initialize()

    if not ee.data.getInfo(ASSET_COLL_ID):
        logging.error('Export collection does not exist')
        logging.error(f'  {ASSET_COLL_ID}')
        return []

    # Get list of MGRS tiles that intersect the study area
    logging.debug('\nMGRS Tiles/Zones')
    export_list = mgrs_export_tiles(
        study_area_coll_id=STUDY_AREA_COLL_ID,
        mgrs_coll_id=MGRS_FTR_COLL_ID,
        study_area_property=STUDY_AREA_PROPERTY,
        study_area_features=STUDY_AREA_FEATURES,
        # mgrs_tiles=MGRS_TILES,
        # mgrs_skip_list=mgrs_skip_list,
        # utm_zones=UTM_ZONES,
        # wrs2_tiles=WRS2_TILES,
    )
    if not export_list:
        logging.warning('Empty export list')
        return []
    mgrs_tile_list = sorted(list(set(
        tile_info['index'] for tile_info in export_list)))
    logging.debug(f'  MGRS Tiles: {",".join(mgrs_tile_list)}')

    # Build the complete WRS2 list for filtering the image list
    wrs2_tile_list = sorted(list(set(
        wrs2 for tile_info in export_list
        for wrs2 in tile_info['wrs2_tiles'])))
    if WRS2_SKIP_LIST:
        wrs2_tile_list = [wrs2 for wrs2 in wrs2_tile_list
                          if wrs2 not in WRS2_SKIP_LIST]
    if WRS2_PATH_SKIP_LIST:
        wrs2_tile_list = [wrs2 for wrs2 in wrs2_tile_list
                          if int(wrs2[1:4]) not in WRS2_PATH_SKIP_LIST]
    if WRS2_ROW_SKIP_LIST:
        wrs2_tile_list = [wrs2 for wrs2 in wrs2_tile_list
                          if int(wrs2[5:8]) not in WRS2_ROW_SKIP_LIST]
    # logging.debug(f'  WRS2 Tiles: {",".join(wrs2_tile_list)}')

    # CGM - This is kind of backwards, but rebuild the MGRS geometry in order
    #   to filter the model collection object
    mgrs_geom = ee.FeatureCollection(MGRS_FTR_COLL_ID)\
        .filter(ee.Filter.inList('mgrs', mgrs_tile_list))\
        .geometry()
    # study_area_geom = ee.Geometry.BBox(**STUDY_AREA_EXTENT)

    logging.debug('\nRequesting image ID list')
    model_obj = ssebop.Collection(
        collections=collections,
        start_date=start_date,
        end_date=next_date,
        cloud_cover_max=CLOUD_COVER,
        geometry=mgrs_geom,
        model_args=model_args,
        # filter_args=filter_args,
    )
    landsat_coll = model_obj.overpass(variables=['ndvi'])

    try:
        image_id_list = landsat_coll.aggregate_array('system:id').getInfo()
    except Exception as e:
        logging.error(f'Error requesting image ID list\n{e}')
        return []
    # pprint.pprint(image_id_list)
    # input('ENTER')

    # Filter the image ID list to the WRS2 tile list
    image_id_list = [
        x for x in image_id_list
        if f'p{x.split("/")[-1][5:8]}r{x.split("/")[-1][8:11]}' in wrs2_tile_list]
    # pprint.pprint(sorted(image_id_list))
    # input('ENTER')

    # Get list of existing images for the target date
    logging.debug('\nRequesting existing asset list')
    logging.debug(f'  {ASSET_COLL_ID}')
    asset_coll = ee.ImageCollection(ASSET_COLL_ID) \
        .filterDate(start_date, next_date) \
        .filter(ee.Filter.inList('wrs2_tile', wrs2_tile_list))
    # pprint.pprint(asset_coll.getInfo())
    # pprint.pprint(asset_coll.aggregate_array('system:index').getInfo())
    # input('ENTER')

    if realtime_flag:
        # Keep all image IDs in the existing asset list
        pass
    else:
        # Only keep non-realtime image IDs in the existing asset list
        # This will allow existing realtime images to be overwritten
        logging.info('  Removing realtime image IDs from existing asset list')
        asset_coll = asset_coll.filter(ee.Filter.inList('coll_id', COLLECTIONS))
        # asset_coll = asset_coll.filterMetadata('realtime', 'equals', 'false'))
        # pprint.pprint(asset_coll.aggregate_array('system:index').getInfo())
        # input('ENTER')

    # Only keep the scene ID component for filtering the image ID list
    try:
        asset_id_list = asset_coll.aggregate_array('system:index').getInfo()
        # asset_id_list = [f'{ASSET_COLL_ID}/{asset_id}'
        #                  for asset_id in asset_id_list]
    except Exception as e:
        logging.error(f'Error requesting asset ID list\n{e}')
        return []
    # print('Asset ID List')
    # pprint.pprint(sorted(asset_id_list))
    # input('ENTER')

    # Skip image IDs that are already built
    image_id_list = [
        image_id for image_id in image_id_list
        if image_id.split('/')[-1].upper() not in asset_id_list]
    # print('Final image ID List')
    # pprint.pprint(sorted(image_id_list))
    # input('ENTER')

    # Get current running tasks
    logging.debug('\nRequesting task list')
    tasks = utils.get_ee_tasks()

    # Skip image IDs that are already in the task queue
    image_id_list = [
        image_id for image_id in image_id_list
        if EXPORT_ID_FMT.format(product=TMAX_SOURCE.split('/')[-1].lower(),
                                scene_id=image_id.split('/')[-1])
           not in tasks.keys()
    ]
    # pprint.pprint(image_id_list)
    # input('ENTER')

    # Limit the image ID list to avoid exceeding the maximum number of tasks
    task_limit = 2500 - len(tasks.keys())
    if len(image_id_list) > task_limit:
        logging.warning(f'Limiting list to {task_limit} images to avoid '
                        f'exceeding the maximum number of tasks')
        image_id_list = image_id_list[:task_limit]

    # Sort image ID list by path/row
    # image_id_list = sorted(image_id_list, reverse=True,
    #                        key=lambda k: k.split('/')[-1].split('_')[-2])
    # Sort image ID list by date
    image_id_list = sorted(image_id_list, reverse=False,
                           key=lambda k: k.split('/')[-1].split('_')[-1])
    # pprint.pprint(image_id_list)
    # input('ENTER')

    return image_id_list


def mgrs_export_tiles(study_area_coll_id, mgrs_coll_id,
                      study_area_property=None, study_area_features=[],
                      mgrs_tiles=[], mgrs_skip_list=[],
                      utm_zones=[], wrs2_tiles=[],
                      mgrs_property='mgrs', utm_property='utm',
                      wrs2_property='wrs2'):
    """Select MGRS tiles and metadata that intersect the study area geometry

    Parameters
    ----------
    study_area_coll_id : str
        Study area feature collection asset ID.
    mgrs_coll_id : str
        MGRS feature collection asset ID.
    study_area_property : str, optional
        Property name to use for inList() filter call of study area collection.
        Filter will only be applied if both 'study_area_property' and
        'study_area_features' parameters are both set.
    study_area_features : list, optional
        List of study area feature property values to filter on.
    mgrs_tiles : list, optional
        User defined MGRS tile subset.
    mgrs_skip_list : list, optional
        User defined list MGRS tiles to skip.
    utm_zones : list, optional
        User defined UTM zone subset.
    wrs2_tiles : list, optional
        User defined WRS2 tile subset.
    mgrs_property : str, optional
        MGRS property in the MGRS feature collection (the default is 'mgrs').
    utm_property : str, optional
        UTM zone property in the MGRS feature collection (the default is 'wrs2').
    wrs2_property : str, optional
        WRS2 property in the MGRS feature collection (the default is 'wrs2').

    Returns
    ------
    list of dicts: export information

    """
    # Build and filter the study area feature collection
    logging.debug('Building study area collection')
    logging.debug(f'  {study_area_coll_id}')
    study_area_coll = ee.FeatureCollection(study_area_coll_id)
    if (study_area_property == 'STUSPS' and
            'CONUS' in [x.upper() for x in study_area_features]):
        # Exclude AK, HI, AS, GU, PR, MP, VI, (but keep DC)
        study_area_features = [
            'AL', 'AR', 'AZ', 'CA', 'CO', 'CT', 'DC', 'DE', 'FL', 'GA',
            'IA', 'ID', 'IL', 'IN', 'KS', 'KY', 'LA', 'MA', 'MD', 'ME',
            'MI', 'MN', 'MO', 'MS', 'MT', 'NC', 'ND', 'NE', 'NH', 'NJ',
            'NM', 'NV', 'NY', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD',
            'TN', 'TX', 'UT', 'VA', 'VT', 'WA', 'WI', 'WV', 'WY']
    # elif (study_area_property == 'STUSPS' and
    #         'WESTERN11' in [x.upper() for x in study_area_features]):
    #     study_area_features = [
    #         'AZ', 'CA', 'CO', 'ID', 'MT', 'NM', 'NV', 'OR', 'UT', 'WA', 'WY']
    study_area_features = sorted(list(set(study_area_features)))

    if study_area_property and study_area_features:
        logging.debug('  Filtering study area collection')
        logging.debug(f'  Property: {study_area_property}')
        logging.debug(f'  Features: {",".join(study_area_features)}')
        study_area_coll = study_area_coll.filter(
            ee.Filter.inList(study_area_property, study_area_features))

    logging.debug('Building MGRS tile list')
    tiles_coll = ee.FeatureCollection(mgrs_coll_id) \
        .filterBounds(study_area_coll.geometry())

    # Filter collection by user defined lists
    if utm_zones:
        logging.debug(f'  Filter user UTM Zones:    {utm_zones}')
        tiles_coll = tiles_coll.filter(ee.Filter.inList(utm_property, utm_zones))
    if mgrs_skip_list:
        logging.debug(f'  Filter MGRS skip list:    {mgrs_skip_list}')
        tiles_coll = tiles_coll.filter(
            ee.Filter.inList(mgrs_property, mgrs_skip_list).Not())
    if mgrs_tiles:
        logging.debug(f'  Filter MGRS tiles/zones:  {mgrs_tiles}')
        # Allow MGRS tiles to be subsets of the full tile code
        #   i.e. mgrs_tiles = 10TE, 10TF
        mgrs_filters = [
            ee.Filter.stringStartsWith(mgrs_property, mgrs_id.upper())
            for mgrs_id in mgrs_tiles]
        tiles_coll = tiles_coll.filter(ee.call('Filter.or', mgrs_filters))

    def drop_geometry(ftr):
        return ee.Feature(None).copyProperties(ftr)

    logging.debug('  Requesting tile/zone info')
    tiles_info = utils.get_info(tiles_coll.map(drop_geometry))

    # Constructed as a list of dicts to mimic other interpolation/export tools
    tiles_list = []
    for tile_ftr in tiles_info['features']:
        tiles_list.append({
            'index': tile_ftr['properties']['mgrs'].upper(),
            'wrs2_tiles': sorted(utils.wrs2_str_2_set(
                tile_ftr['properties'][wrs2_property])),
        })

    # Apply the user defined WRS2 tile list
    if wrs2_tiles:
        logging.debug(f'  Filter WRS2 tiles: {wrs2_tiles}')
        for tile in tiles_list:
            tile['wrs2_tiles'] = sorted(list(
                set(tile['wrs2_tiles']) & set(wrs2_tiles)))

    # Only return export tiles that have intersecting WRS2 tiles
    export_list = [
        tile for tile in sorted(tiles_list, key=lambda k: k['index'])
        if tile['wrs2_tiles']]

    return export_list


def cron_scheduler(request):
    """Parse JSON/request arguments and queue ingest tasks for a date range"""
    args = {
        'gee_key_file': GEE_KEY_FILE,
    }

    request_json = request.get_json(silent=True)
    request_args = request.args

    # TODO: Add type and value checking to days parameter
    if request_json and 'days' in request_json:
        days = int(request_json['days'])
    elif request_args and 'days' in request_args:
        days = int(request_args['days'])
    else:
        days = START_DAY_OFFSET
        # abort(400, description='"days" parameter not set')

    if request_json and 'start' in request_json:
        start_date = request_json['start']
    elif request_args and 'start' in request_args:
        start_date = request_args['start']
    else:
        start_date = None
        # abort(400, description='"start" parameter not set')

    if request_json and 'end' in request_json:
        end_date = request_json['end']
    elif request_args and 'end' in request_args:
        end_date = request_args['end']
    else:
        end_date = None
        # abort(400, description='"end" parameter not set')

    if start_date is None and end_date is None:
        today_dt = datetime.datetime.today()
        start_date = (today_dt - datetime.timedelta(days=days)).strftime('%Y-%m-%d')
        end_date = (today_dt - datetime.timedelta(days=0)).strftime('%Y-%m-%d')
        # start_date = (today_dt - datetime.timedelta(days=START_DAY_OFFSET))\
        #     .strftime('%Y-%m-%d')
        # end_date = (today_dt - datetime.timedelta(days=END_DAY_OFFSET))\
        #     .strftime('%Y-%m-%d')

    if start_date and end_date:
        # Parse the start/end date strings
        try:
            args['start_dt'] = datetime.datetime.strptime(start_date, '%Y-%m-%d')
        except:
            abort(400, description=f'Start date {start_date} could not be parsed')
        try:
            args['end_dt'] = datetime.datetime.strptime(end_date, '%Y-%m-%d')
        except:
            abort(400, description=f'End date {end_date} could not be parsed')
    else:
        abort(400, description='Both start and end date must be specified')

    if request_json and 'realtime' in request_json:
        realtime_flag = request_json['realtime']
    elif request_args and 'realtime' in request_args:
        realtime_flag = request_args['realtime']
    else:
        realtime_flag = 'false'

    if realtime_flag.lower() in ['true', 't']:
        args['realtime_flag'] = True
    elif realtime_flag.lower() in ['false', 'f']:
        args['realtime_flag'] = False
    else:
        abort(400, description=f'realtime="{realtime_flag}" could not be parsed')

    response = queue_ingest_tasks(tcorr_gridded_images(**args))
    return Response(response, mimetype='text/plain')


def cron_worker(request):
    """Parse JSON/request arguments and start ingest for a single date export"""
    request_json = request.get_json(silent=True)
    request_args = request.args

    if request_json and 'image' in request_json:
        image_id = request_json['image']
    elif request_args and 'image' in request_args:
        image_id = request_args['image']
    else:
        abort(400, description='"image" parameter not set')

    # TODO: Add additional image ID format checking
    if not re.match('L[TEC]0[4578]_\d{6}_\d{8}', image_id.split('/')[-1], re.I):
        abort(400, description=f'Image ID {image_id} could not be parsed')
    elif not re.match('LANDSAT/L[TEC]0[4578]/C0[12]/T1\w+', image_id, re.I):
        abort(400, description=f'Image ID {image_id} could not be parsed')

    if request_json and 'overwrite' in request_json:
        overwrite_flag = request_json['overwrite']
    elif request_args and 'overwrite' in request_args:
        overwrite_flag = request_args['overwrite']
    else:
        overwrite_flag = 'true'

    if overwrite_flag.lower() in ['true', 't']:
        overwrite_flag = True
    elif overwrite_flag.lower() in ['false', 'f']:
        overwrite_flag = False
    else:
        abort(400, description=f'overwrite="{overwrite_flag}" could not be parsed')

    response = tcorr_gridded_asset_ingest(
        image_id=image_id, gee_key_file=GEE_KEY_FILE,
        overwrite_flag=overwrite_flag)

    return Response(response, mimetype='text/plain')


def queue_ingest_tasks(image_id_list, overwrite_flag=True):
    """Submit ingest tasks to the queue

    Parameters
    ----------
    image_id_list : list of Landsat image IDs

    Returns
    -------
    str : response string

    """
    logging.info('Queuing gridded Tcorr asset ingest tasks')
    response = 'Queue gridded Tcorr asset ingest tasks\n'

    TASK_CLIENT = tasks_v2.CloudTasksClient()
    parent = TASK_CLIENT.queue_path(PROJECT_NAME, TASK_LOCATION, TASK_QUEUE)

    for image_id in image_id_list:
        logging.info(f'Image: {image_id}')
        # response += f'Image: {image_id}\n'

        # Using the default name in the request can create duplicate tasks
        # Trying out adding the timestamp to avoid this for testing/debug
        name = f'{parent}/tasks/tcorr_gridded_asset_{image_id.split("/")[-1].lower()}_' \
               f'{datetime.datetime.today().strftime("%Y%m%d%H%M%S")}'
        # name = f'{parent}/tasks/tcorr_gridded_asset_{image_id.split("/")[-1].lower()}'
        response += name + '\n'
        logging.info(name)

        # Using the json body wasn't working, switching back to URL
        # Couldn't get authentication with oidc_token to work
        # payload = {'image': image_id}
        task = {
            'http_request': {
                'http_method': tasks_v2.HttpMethod.POST,
                'url': '{}/{}?image={}&overwrite=true'.format(
                    FUNCTION_URL, FUNCTION_NAME, image_id,
                    str(overwrite_flag).lower()),
                # 'url': '{}/{}?image={}'.format(
                #     FUNCTION_URL, FUNCTION_NAME, image_id),
                # 'url': '{}/{}'.format(FUNCTION_URL, FUNCTION_NAME),
                # 'headers': {'Content-type': 'application/json'},
                # 'body': json.dumps(payload).encode(),
                # 'oidc_token': {
                #     'service_account_email': SERVICE_ACCOUNT,
                #     'audience': '{}/{}'.format(FUNCTION_URL, FUNCTION_NAME)},
                # 'relative_uri': ,
            },
            'name': name,
        }
        TASK_CLIENT.create_task(request={'parent': parent, 'task': task})
        # time.sleep(0.1)

    return response


# Using this version until date filtering is added to openet-core version
# def get_ee_assets(asset_id, start_dt=None, end_dt=None):
#     """Return assets IDs in a collection
#
#     Parameters
#     ----------
#     asset_id : str
#         A folder or image collection ID.
#     start_dt : datetime, optional
#         Start date (inclusive).
#     end_dt : datetime, optional
#         End date (exclusive, similar to .filterDate()).
#
#     Returns
#     -------
#     list : Asset IDs
#
#     """
#     params = {'parent': asset_id}
#     if start_dt and end_dt:
#         # CGM - Do both start and end need to be set to apply filtering?
#         params['startTime'] = start_dt.isoformat() + '.000000000Z'
#         params['endTime'] = end_dt.isoformat() + '.000000000Z'
#
#     asset_id_list = []
#     for i in range(1, 6):
#         try:
#             asset_id_list = [x['id'] for x in ee.data.listImages(params)['images']]
#             break
#         except ValueError:
#             logging.info('  Collection or folder doesn\'t exist')
#             raise sys.exit()
#         except Exception as e:
#             logging.error(
#                 '  Error getting asset list, retrying ({}/10)\n'
#                 '  {}'.format(i, e))
#             time.sleep(i ** 2)
#
#     return asset_id_list


# DEADBEEF - Using equivalent function in openet.core.utils
# def get_ee_tasks(states=['RUNNING', 'READY']):
#     """Return current active tasks
#
#     Parameters
#     ----------
#     states : list
#
#     Returns
#     -------
#     dict : Task descriptions (key) and task IDs (value).
#
#     """
#
#     logging.debug('  Active Tasks')
#     tasks = {}
#     for i in range(1, 6):
#         try:
#             # task_list = ee.data.listOperations()
#             task_list = ee.data.getTaskList()
#             task_list = sorted([
#                 [t['state'], t['description'], t['id']]
#                 for t in task_list if t['state'] in states])
#             tasks = {t_desc: t_id for t_state, t_desc, t_id in task_list}
#             break
#         except Exception as e:
#             logging.info(
#                 '  Error getting active task list, retrying ({}/10)\n'
#                 '  {}'.format(i, e))
#             time.sleep(i ** 2)
#     return tasks


def arg_parse():
    """"""
    parser = argparse.ArgumentParser(
        description='Compute/export gridded Tcorr images by date',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--start', type=utils.arg_valid_date, metavar='DATE',
        default=(datetime.datetime.today().date() -
                 datetime.timedelta(days=START_DAY_OFFSET)),
        help='Start date (format YYYY-MM-DD)')
    parser.add_argument(
        '--end', type=utils.arg_valid_date, metavar='DATE',
        default=(datetime.datetime.today().date() -
                 datetime.timedelta(days=END_DAY_OFFSET)),
        help='End date (format YYYY-MM-DD)')
    parser.add_argument(
        '--realtime', default=False, action='store_true',
        help='Use realtime Landsat collections')
    parser.add_argument(
        '--key', type=utils.arg_valid_file, metavar='FILE',
        help='JSON key file')
    parser.add_argument(
        '--debug', default=logging.INFO, const=logging.DEBUG,
        help='Debug level logging', action='store_const', dest='loglevel')
    # parser.add_argument(
    #     '--overwrite', default=False, action='store_true',
    #     help='Force overwrite of existing files')
    # parser.add_argument(
    #     '--ready', default=3000, type=int,
    #     help='Maximum number of queued READY tasks')
    # parser.add_argument(
    #     '--recent', default=0, type=int,
    #     help='Number of days to process before current date '
    #          '(ignore INI start_date and end_date')
    # parser.add_argument(
    #     '--reverse', default=False, action='store_true',
    #     help='Process dates/scenes in reverse order')
    # parser.add_argument(
    #     '--tiles', default='', nargs='+',
    #     help='Comma/space separated list of tiles to process')
    # parser.add_argument(
    #     '--update', default=False, action='store_true',
    #     help='Update images with older model version numbers')

    args = parser.parse_args()

    return args


if __name__ == "__main__":
    args = arg_parse()

    logging.basicConfig(level=args.loglevel, format='%(message)s')
    logging.getLogger('googleapiclient').setLevel(logging.ERROR)

    # # Build the image collection if it doesn't exist
    # logging.debug(f'Image Collection: {EXPORT_COLL_ID}')
    # ee.Initialize()
    # if not ee.data.getInfo(EXPORT_COLL_ID):
    #     logging.info('\nImage collection does not exist and will be built'
    #                  '\n  {}'.format(EXPORT_COLL_ID))
    #     input('Press ENTER to continue')
    #     ee.data.createAsset({'type': 'IMAGE_COLLECTION'}, EXPORT_COLL_ID)

    image_id_list = tcorr_gridded_images(
        start_dt=args.start, end_dt=args.end, gee_key_file=args.key,
        realtime_flag=args.realtime
    )

    for image_id in image_id_list:
        response = tcorr_gridded_asset_ingest(image_id, gee_key_file=args.key)
        logging.info(f'{response}')
