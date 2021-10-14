import argparse
from builtins import input
import configparser
import datetime
import logging
import math
import pprint
import re
import sys

import ee

import openet.ssebop as ssebop
import openet.core.utils as utils

# TODO: This could be a property or method of SSEBop or the Image class
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
EXPORT_GEO = [5000, 0, 15, 0, -5000, 15]


def main(ini_path=None, overwrite_flag=False, delay_time=0, gee_key_file=None,
         max_ready=-1, reverse_flag=False):
    """Compute monthly Tcorr images from gridded images

    Parameters
    ----------
    ini_path : str
        Input file path.
    overwrite_flag : bool, optional
        If True, overwrite existing files (the default is False).
    delay_time : float, optional
        Delay time in seconds between starting export tasks (or checking the
        number of queued tasks, see "max_ready" parameter).  The default is 0.
    gee_key_file : str, None, optional
        Earth Engine service account JSON key file (the default is None).
    max_ready: int, optional
        Maximum number of queued "READY" tasks.  The default is -1 which is
        implies no limit to the number of tasks that will be submitted.
    reverse_flag : bool, optional
        If True, process WRS2 tiles in reverse order.

    """
    logging.info('\nCompute monthly Tcorr images from gridded images')

    wrs2_coll_id = 'projects/earthengine-legacy/assets/' \
                   'projects/usgs-ssebop/wrs2_descending_custom'
    wrs2_tile_field = 'WRS2_TILE'

    # CGM - Which format should we use for the WRS2 tile?
    wrs2_tile_fmt = 'p{:03d}r{:03d}'
    # wrs2_tile_fmt = '{:03d}{:03d}'
    wrs2_tile_re = re.compile('p?(\d{1,3})r?(\d{1,3})')

    # List of path/rows to skip
    wrs2_skip_list = [
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
    wrs2_path_skip_list = [9, 49]
    wrs2_row_skip_list = [25, 24, 43]

    mgrs_skip_list = []

    export_id_fmt = 'tcorr_gridded_{product}_{wrs2}_month{month:02d}'
    asset_id_fmt = '{coll_id}/{wrs2}_month{month:02d}'


    # Read config file
    ini = configparser.ConfigParser(interpolation=None)
    ini.read_file(open(ini_path, 'r'))
    # ini = utils.read_ini(ini_path)

    # try:
    model_name = 'SSEBOP'
    #     # model_name = ini['INPUTS']['et_model'].upper()
    # except KeyError:
    #     raise ValueError('"et_model" parameter was not set in INI')
    # except Exception as e:
    #     raise e

    try:
        tmax_source = ini[model_name]['tmax_source']
    except KeyError:
        raise ValueError('"tmax_source" parameter was not set in INI')
    except Exception as e:
        raise e

    try:
        tcorr_source = ini[model_name]['tcorr_source']
    except KeyError:
        raise ValueError('"tcorr_source" parameter was not set in INI')
    except Exception as e:
        raise e

    try:
        tcorr_monthly_coll_id = '{}_monthly'.format(ini['EXPORT']['export_coll'])
    except KeyError:
        raise ValueError('"export_coll" parameter was not set in INI')
    except Exception as e:
        raise e

    try:
        study_area_coll_id = str(ini['INPUTS']['study_area_coll'])
    except KeyError:
        raise ValueError('"study_area_coll" parameter was not set in INI')
    except Exception as e:
        raise e

    try:
        mgrs_ftr_coll_id = str(ini['EXPORT']['mgrs_ftr_coll'])
    except KeyError:
        raise ValueError('"mgrs_ftr_coll" parameter was not set in INI')
    except Exception as e:
        raise e

    # Optional parameters
    try:
        study_area_property = str(ini['INPUTS']['study_area_property'])
    except KeyError:
        study_area_property = None
        logging.debug('  study_area_property: not set in INI, defaulting to None')
    except Exception as e:
        raise e

    try:
        study_area_features = str(ini['INPUTS']['study_area_features'])
        study_area_features = sorted([
            x.strip() for x in study_area_features.split(',')])
    except KeyError:
        study_area_features = []
        logging.debug('  study_area_features: not set in INI, defaulting to []')
    except Exception as e:
        raise e

    try:
        wrs2_tiles = str(ini['INPUTS']['wrs2_tiles'])
        wrs2_tiles = [x.strip() for x in wrs2_tiles.split(',')]
        wrs2_tiles = sorted([x.lower() for x in wrs2_tiles if x])
    except KeyError:
        wrs2_tiles = []
        logging.debug('  wrs2_tiles: not set in INI, defaulting to []')
    except Exception as e:
        raise e

    try:
        mgrs_tiles = str(ini['EXPORT']['mgrs_tiles'])
        mgrs_tiles = sorted([x.strip() for x in mgrs_tiles.split(',')])
        # CGM - Remove empty strings caused by trailing or extra commas
        mgrs_tiles = [x.upper() for x in mgrs_tiles if x]
        logging.debug(f'  mgrs_tiles: {mgrs_tiles}')
    except KeyError:
        mgrs_tiles = []
        logging.debug('  mgrs_tiles: not set in INI, defaulting to []')
    except Exception as e:
        raise e

    try:
        utm_zones = str(ini['EXPORT']['utm_zones'])
        utm_zones = sorted([int(x.strip()) for x in utm_zones.split(',')])
        logging.debug(f'  utm_zones: {utm_zones}')
    except KeyError:
        utm_zones = []
        logging.debug('  utm_zones: not set in INI, defaulting to []')
    except Exception as e:
        raise e

    # TODO: Add try/except blocks and default values?
    # TODO: Filter Tcorr scene collection based on collections parameter
    # collections = [x.strip() for x in ini['INPUTS']['collections'].split(',')]
    # cloud_cover = float(ini['INPUTS']['cloud_cover'])
    # min_pixel_count = float(ini['TCORR']['min_pixel_count'])
    min_scene_count = float(ini['TCORR']['min_scene_count'])

    # Limit by year
    month_list = list(range(1, 13))
    # try:
    #     month_list = sorted(list(utils.parse_int_set(ini['TCORR']['months'])))
    # except:
    #     logging.info('\nTCORR "months" parameter not set in the INI,'
    #                  '\n  Defaulting to all months (1-12)\n')
    #     month_list = list(range(1, 13))
    try:
        year_list = sorted(list(utils.parse_int_set(ini['TCORR']['years'])))
    except:
        logging.info('\nTCORR "years" parameter not set in the INI,'
                     '\n  Defaulting to all available years\n')
        year_list = []


    # For now only support reading specific Tmax sources
    if (tmax_source.upper() not in ['DAYMET_MEDIAN_V2'] and
            not re.match('^projects/.+/tmax/.+_(mean|median)_\d{4}_\d{4}(_\w+)?',
                         tmax_source)):
        raise ValueError(f'unsupported tmax_source: {tmax_source}')
    # if (tmax_name.upper() == 'CIMIS' and
    #         ini['INPUTS']['end_date'] < '2003-10-01'):
    #     logging.error(
    #         '\nCIMIS is not currently available before 2003-10-01, exiting\n')
    #     sys.exit()
    # elif (tmax_name.upper() == 'DAYMET' and
    #         ini['INPUTS']['end_date'] > '2020-12-31'):
    #     logging.warning(
    #         '\nDAYMET is not currently available past 2020-12-31, '
    #         'using median Tmax values\n')
    #     # sys.exit()
    # # elif (tmax_name.upper() == 'TOPOWX' and
    # #         ini['INPUTS']['end_date'] > '2017-12-31'):
    # #     logging.warning(
    # #         '\nDAYMET is not currently available past 2017-12-31, '
    # #         'using median Tmax values\n')
    # #     # sys.exit()


    logging.info('\nInitializing Earth Engine')
    if gee_key_file:
        logging.info(f'  Using service account key file: {gee_key_file}')
        # The "EE_ACCOUNT" parameter is not used if the key file is valid
        ee.Initialize(ee.ServiceAccountCredentials('x', key_file=gee_key_file))
    else:
        ee.Initialize()


    logging.debug('\nTmax properties')
    tmax_coll = ee.ImageCollection(tmax_source)
    tmax_mask = ee.Image(tmax_coll.first()).select([0]).multiply(0)
    logging.debug(f'  {tmax_source}')

    # Get the Tcorr image collection properties
    logging.debug('\nTcorr scene collection')
    tcorr_coll_id = '{}'.format(ini['EXPORT']['export_coll'])


    # if not ee.data.getInfo(tcorr_monthly_coll_id.rsplit('/', 1)[0]):
    #     logging.info('\nExport collection does not exist and will be built'
    #                  '\n  {}'.format(tcorr_monthly_coll_id.rsplit('/', 1)[0]))
    #     input('Press ENTER to continue')
    #     ee.data.createAsset({'type': 'FOLDER'},
    #                         tcorr_monthly_coll_id.rsplit('/', 1)[0])
    if not ee.data.getInfo(tcorr_monthly_coll_id):
        logging.info('\nExport collection does not exist and will be built'
                     '\n  {}'.format(tcorr_monthly_coll_id))
        input('Press ENTER to continue')
        ee.data.createAsset({'type': 'IMAGE_COLLECTION'}, tcorr_monthly_coll_id)


    # Get current running tasks
    tasks = utils.get_ee_tasks()
    ready_task_count = sum(1 for t in tasks.values() if t['state'] == 'READY')
    # ready_task_count = delay_task(ready_task_count, delay_time, max_ready)
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        utils.print_ee_tasks(tasks)
        input('ENTER')


    # Get current asset list
    logging.debug('\nGetting GEE asset list')
    asset_list = utils.get_ee_assets(tcorr_monthly_coll_id)
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        pprint.pprint(asset_list[:10])


    # Get list of MGRS tiles that intersect the study area
    logging.info('\nBuilding export list')
    export_list = mgrs_export_tiles(
        study_area_coll_id=study_area_coll_id,
        mgrs_coll_id=mgrs_ftr_coll_id,
        study_area_property=study_area_property,
        study_area_features=study_area_features,
        mgrs_tiles=mgrs_tiles,
        mgrs_skip_list=mgrs_skip_list,
        utm_zones=utm_zones,
        wrs2_tiles=wrs2_tiles,
    )
    if not export_list:
        logging.error('\nEmpty export list, exiting')
        return False
    # pprint.pprint(export_list)
    # input('ENTER')


    # Build the complete/filtered WRS2 list
    wrs2_tile_list = list(set(
        wrs2 for tile_info in export_list
        for wrs2 in tile_info['wrs2_tiles']))
    if wrs2_skip_list:
        wrs2_tile_list = [wrs2 for wrs2 in wrs2_tile_list
                          if wrs2 not in wrs2_skip_list]
    if wrs2_path_skip_list:
        wrs2_tile_list = [wrs2 for wrs2 in wrs2_tile_list
                          if int(wrs2[1:4]) not in wrs2_path_skip_list]
    if wrs2_row_skip_list:
        wrs2_tile_list = [wrs2 for wrs2 in wrs2_tile_list
                          if int(wrs2[5:8]) not in wrs2_row_skip_list]
    wrs2_tile_list = sorted(wrs2_tile_list, reverse=not(reverse_flag))
    # wrs2_tile_count = len(wrs2_tile_list)


    # Get the list of WRS2 tiles that intersect the data area and study area
    wrs2_coll = ee.FeatureCollection(wrs2_coll_id) \
        .filter(ee.Filter.inList(wrs2_tile_field, wrs2_tile_list))
    wrs2_info = wrs2_coll.getInfo()['features']


    for wrs2_ftr in sorted(wrs2_info,
                           key=lambda k: k['properties']['WRS2_TILE'],
                           reverse=reverse_flag):
        wrs2_tile = wrs2_ftr['properties'][wrs2_tile_field]
        wrs2_path, wrs2_row = map(int, wrs2_tile_re.findall(wrs2_tile)[0])
        logging.info('{}'.format(wrs2_tile))

        for month in month_list:
            logging.info(f'Month: {month}')

            export_id = export_id_fmt.format(
                product=tmax_source.split('/')[-1], wrs2=wrs2_tile, month=month)
            logging.debug(f'  Export ID: {export_id}')

            asset_id = asset_id_fmt.format(
                coll_id=tcorr_monthly_coll_id, wrs2=wrs2_tile, month=month)
            asset_short_id = asset_id.replace(
                'projects/earthengine-legacy/assets/', '')
            logging.debug(f'  Asset ID: {asset_id}')

            if overwrite_flag:
                if export_id in tasks.keys():
                    logging.info('  Task already submitted, cancelling')
                    ee.data.cancelTask(tasks[export_id]['id'])
                # This is intentionally not an "elif" so that a task can be
                # cancelled and an existing image/file/asset can be removed
                if asset_id in asset_list or asset_short_id in asset_list:
                    logging.info('  Asset already exists, removing')
                    ee.data.deleteAsset(asset_id)
            else:
                if export_id in tasks.keys():
                    logging.info('  Task already submitted, exiting')
                    continue
                elif asset_id in asset_list or asset_short_id in asset_list:
                    logging.info('  Asset already exists, skipping')
                    continue


            # TODO: Move to separate function or outside loop
            export_crs = 'EPSG:{}'.format(wrs2_ftr['properties']['EPSG'])
            wrs2_extent = ee.Geometry(wrs2_ftr['geometry'])\
                .bounds(1, ee.Projection(export_crs))\
                .coordinates().get(0).getInfo()
            wrs2_extent = [
                min([x[0] for x in wrs2_extent]),
                min([x[1] for x in wrs2_extent]),
                max([x[0] for x in wrs2_extent]),
                max([x[1] for x in wrs2_extent])]
            logging.debug(f'    WRS2 Extent: {wrs2_extent}')

            # Adjust the image extent to the coarse resolution grid
            # EXPORT_GEO = [5000, 0, 15, 0, -5000, 15]
            export_cs = EXPORT_GEO[0]
            export_extent = [
                round(math.floor((wrs2_extent[0] - EXPORT_GEO[2]) / export_cs) *
                      export_cs + EXPORT_GEO[2], 8),
                round(math.floor((wrs2_extent[1] - EXPORT_GEO[5]) / export_cs) *
                      export_cs + EXPORT_GEO[5], 8),
                round(math.ceil((wrs2_extent[2] - EXPORT_GEO[2]) / export_cs) *
                      export_cs + EXPORT_GEO[2], 8),
                round(math.ceil((wrs2_extent[3] - EXPORT_GEO[5]) / export_cs) *
                      export_cs + EXPORT_GEO[5], 8),
            ]
            export_geo = [export_cs, 0, export_extent[0], 0,
                          -export_cs, export_extent[3]]
            export_shape = [
                int(abs(export_extent[2] - export_extent[0]) / EXPORT_GEO[0]),
                int(abs(export_extent[3] - export_extent[1]) / EXPORT_GEO[0])]
            logging.debug(f'    Export CRS: {export_crs}')
            logging.debug(f'    Export Geo: {export_geo}')
            logging.debug(f'    Export Extent: {export_extent}')
            logging.debug(f'    Export Shape:  {export_shape}')

            tcorr_coll = ee.ImageCollection(tcorr_coll_id) \
                .filterMetadata('wrs2_tile', 'equals', wrs2_tile) \
                .filter(ee.Filter.calendarRange(month, month, 'month')) \
                .filter(ee.Filter.inList('year', year_list)) \
                .filterMetadata('tcorr_index', 'equals', 1) \
                .filterMetadata('tcorr_coarse_count', 'greater_than', 0) \
                .select(['tcorr'])
            #     .filterMetadata('tcorr_pixel_count', 'not_less_than', min_pixel_count) \
            # TODO: Should CLOUD_COVER_LAND filter should be re-applied here?
            #     .filterMetadata('CLOUD_COVER_LAND', 'less_than', cloud_cover) \
            #     .filterDate(start_date, end_date)
            #     .filterBounds(ee.Geometry(wrs2_ftr['geometry']))

            tcorr_count = tcorr_coll.size()

            # mask_img = ee.Image.constant(0).reproject(export_crs, export_geo)

            # Compute the gridded Tcorr climo image and count
            reducer = ee.Reducer.mean() \
                .combine(ee.Reducer.count(), sharedInputs=True)
            tcorr_img = tcorr_coll.reduce(reducer).rename(['tcorr', 'count'])
            count_img = tcorr_img.select(['count'])

            output_img = tcorr_img.updateMask(count_img.gte(min_scene_count))

            # # Compute stats from the image properties
            # tcorr_stats = ee.List(tcorr_coll.aggregate_array('tcorr_value')) \
            #     .reduce(reducer)
            # tcorr_stats = ee.Dictionary(tcorr_stats) \
            #     .combine({'median': 0, 'count': 0}, overwrite=False)
            # tcorr = ee.Number(tcorr_stats.get('median'))
            # count = ee.Number(tcorr_stats.get('count'))
            # index = count.lt(min_scene_count)\
            #     .multiply(TCORR_INDICES['NODATA'] - TCORR_INDICES['ANNUAL'])\
            #     .add(TCORR_INDICES['ANNUAL'])
            # # index = ee.Algorithms.If(count.gte(min_scene_count), 6, 9)

            # # Clip the mask image to the Landsat footprint
            # # Change mask values to 1 if count >= threshold
            # # Mask values of 0 will be set to nodata
            # mask_img = tmax_mask.add(count.gte(min_scene_count)) \
            #     .clip(ee.Geometry(wrs2_ftr['geometry']))
            # output_img = ee.Image(
            #         [mask_img.multiply(tcorr), mask_img.multiply(count)]) \
            #     .rename(['tcorr', 'count']) \
            #     .updateMask(mask_img.unmask(0))

            # # Write an empty image if the pixel count is too low
            # # CGM: Check/test if this can be combined into a single If()
            # tcorr_img = ee.Algorithms.If(
            #     count.gte(min_scene_count),
            #     tmax_mask.add(tcorr), mask_img.updateMask(0))
            # count_img = ee.Algorithms.If(
            #     count.gte(min_scene_count),
            #     tmax_mask.add(count), mask_img.updateMask(0))
            #
            # # Clip to the Landsat image footprint
            # output_img = ee.Image([tcorr_img, count_img]) \
            #     .rename(['tcorr', 'count'])

            # Clip to the Landsat image footprint
            # output_img = output_img.clip(ee.Geometry(wrs2_ftr['geometry']))

            # Clear the transparency mask
            # output_img = output_img.updateMask(output_img.unmask(0))

            output_img = output_img.set({
                'date_ingested': datetime.datetime.today().strftime('%Y-%m-%d'),
                'model_name': model_name,
                'model_version': ssebop.__version__,
                'month': int(month),
                # 'system:time_start': utils.millis(start_dt),
                # 'tcorr_value': tcorr,
                'tcorr_index': TCORR_INDICES['MONTH'],
                'tcorr_scene_count': tcorr_count,
                'tcorr_source': tcorr_source,
                'tmax_source': tmax_source,
                'wrs2_path': wrs2_path,
                'wrs2_row': wrs2_row,
                'wrs2_tile': wrs2_tile,
                'years': ','.join(map(str, year_list)),
                # 'year_start': year_list[0],
                # 'year_end': year_list[-1],
            })
            # pprint.pprint(output_img.getInfo())
            # input('ENTER')

            logging.debug('  Building export task')
            task = ee.batch.Export.image.toAsset(
                image=output_img,
                description=export_id,
                assetId=asset_id,
                crs=export_crs,
                crsTransform='[' + ','.join(list(map(str, export_geo))) + ']',
                dimensions='{0}x{1}'.format(*export_shape),
            )

            logging.info('  Starting export task')
            utils.ee_task_start(task)

            # Pause before starting the next export task
            utils.delay_task(delay_time, max_ready)
            logging.debug('')


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


def arg_parse():
    """"""
    parser = argparse.ArgumentParser(
        description='Compute/export monthly Tcorr images from gridded images',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-i', '--ini', type=utils.arg_valid_file,
        help='Input file', metavar='FILE')
    parser.add_argument(
        '--delay', default=0, type=float,
        help='Delay (in seconds) between each export tasks')
    parser.add_argument(
        '--key', type=utils.arg_valid_file, metavar='FILE',
        help='JSON key file')
    parser.add_argument(
        '--ready', default=-1, type=int,
        help='Maximum number of queued READY tasks')
    parser.add_argument(
        '--reverse', default=False, action='store_true',
        help='Process tiles in reverse order')
    parser.add_argument(
        '-o', '--overwrite', default=False, action='store_true',
        help='Force overwrite of existing files')
    parser.add_argument(
        '-d', '--debug', default=logging.INFO, const=logging.DEBUG,
        help='Debug level logging', action='store_const', dest='loglevel')
    args = parser.parse_args()

    return args


if __name__ == "__main__":
    args = arg_parse()

    logging.basicConfig(level=args.loglevel, format='%(message)s')
    logging.getLogger('googleapiclient').setLevel(logging.ERROR)

    main(ini_path=args.ini, overwrite_flag=args.overwrite,
         delay_time=args.delay, gee_key_file=args.key, max_ready=args.ready,
         reverse_flag=args.reverse)
