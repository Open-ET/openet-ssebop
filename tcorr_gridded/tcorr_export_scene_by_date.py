import argparse
from builtins import input
import configparser
import datetime
import logging
import math
import os
import pprint
import re
import time

import ee

import openet.ssebop as ssebop
import openet.core
import openet.core.utils as utils

TOOL_NAME = 'tcorr_export_scene_by_date'
TOOL_VERSION = '0.1.6'

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
         max_ready=3000, reverse_flag=False, tiles=None, update_flag=False,
         log_tasks=True, recent_days=0, start_dt=None, end_dt=None):
    """Compute gridded Tcorr images by date

    Parameters
    ----------
    ini_path : str
        Input file path.
    overwrite_flag : bool, optional
        If True, overwrite existing files if the export dates are the same and
        generate new images (but with different export dates) even if the tile
        lists are the same.  The default is False.
    delay_time : float, optional
        Delay time in seconds between starting export tasks (or checking the
        number of queued tasks, see "max_ready" parameter).  The default is 0.
    gee_key_file : str, None, optional
        Earth Engine service account JSON key file (the default is None).
    max_ready: int, optional
        Maximum number of queued "READY" tasks.
    reverse_flag : bool, optional
        If True, process WRS2 tiles in reverse order (the default is False).
    tiles : str, None, optional
        List of MGRS tiles to process (the default is None).
    update_flag : bool, optional
        If True, only overwrite scenes with an older model version.
        recent_days : int, optional
        Limit start/end date range to this many days before the current date
        (the default is 0 which is equivalent to not setting the parameter and
         will use the INI start/end date directly).
    start_dt : datetime, optional
        Override the start date in the INI file
        (the default is None which will use the INI start date).
    end_dt : datetime, optional
        Override the (inclusive) end date in the INI file
        (the default is None which will use the INI end date).

    """
    logging.info('\nCompute gridded Tcorr images by date')

    # CGM - Which format should we use for the WRS2 tile?
    wrs2_tile_fmt = 'p{:03d}r{:03d}'
    # wrs2_tile_fmt = '{:03d}{:03d}'
    wrs2_tile_re = re.compile('p?(\d{1,3})r?(\d{1,3})')

    # List of path/rows to skip
    wrs2_skip_list = [
        'p038r038', 'p039r038', 'p040r038',  # Mexico (by CA)
        'p042r037',  # San Nicholas Island
        'p049r026',  # Vancouver Island
        # 'p041r037', 'p042r037', 'p047r031',  # CA Coast
        'p033r039', 'p032r040', # Mexico (by TX)
        'p029r041', 'p028r042', 'p027r043', 'p026r043',  # Mexico (by TX)
        # 'p019r040', # Florida west
        # 'p016r043', 'p015r043', # Florida south
        # 'p014r041', 'p014r042', 'p014r043', # Florida east
        # 'p013r035', 'p013r036', # NC Outer Banks
        # 'p011r032', # RI
        # 'p013r026', 'p012r026', # Canada (by ME)
    ]
    wrs2_path_skip_list = [9, 49]
    wrs2_row_skip_list = [25, 24, 43]

    mgrs_skip_list = []

    export_id_fmt = 'tcorr_gridded_{product}_{scene_id}'
    asset_id_fmt = '{coll_id}/{scene_id}'

    # TODO: Move to INI or function input parameter
    clip_ocean_flag = True

    # Read config file
    ini = configparser.ConfigParser(interpolation=None)
    ini.read_file(open(ini_path, 'r'))
    # ini = utils.read_ini(ini_path)

    model_name = 'SSEBOP'

    try:
        study_area_coll_id = str(ini['INPUTS']['study_area_coll'])
    except KeyError:
        raise ValueError('"study_area_coll" parameter was not set in INI')
    except Exception as e:
        raise e

    try:
        start_date = str(ini['INPUTS']['start_date'])
    except KeyError:
        raise ValueError('"start_date" parameter was not set in INI')
    except Exception as e:
        raise e

    try:
        end_date = str(ini['INPUTS']['end_date'])
    except KeyError:
        raise ValueError('"end_date" parameter was not set in INI')
    except Exception as e:
        raise e

    try:
        collections = str(ini['INPUTS']['collections'])
        collections = sorted([x.strip() for x in collections.split(',')])
    except KeyError:
        raise ValueError('"collections" parameter was not set in INI')
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
        wrs2_tiles = sorted([x.strip() for x in wrs2_tiles.split(',')])
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
        logging.debug('  mgrs_tiles: {}'.format(mgrs_tiles))
    except KeyError:
        mgrs_tiles = []
        logging.debug('  mgrs_tiles: not set in INI, defaulting to []')
    except Exception as e:
        raise e

    try:
        utm_zones = str(ini['EXPORT']['utm_zones'])
        utm_zones = sorted([int(x.strip()) for x in utm_zones.split(',')])
        logging.debug('  utm_zones: {}'.format(utm_zones))
    except KeyError:
        utm_zones = []
        logging.debug('  utm_zones: not set in INI, defaulting to []')
    except Exception as e:
        raise e

    # TODO: Add try/except blocks and default values?
    cloud_cover = float(ini['INPUTS']['cloud_cover'])

    # Model specific parameters
    # Set the property name to lower case and try to cast values to numbers
    model_args = {
        k.lower(): float(v) if utils.is_number(v) else v
        for k, v in dict(ini[model_name]).items()}
    filter_args = {}

    tmax_name = ini[model_name]['tmax_source']
    tcorr_source = ini[model_name]['tcorr_source']

    tcorr_scene_coll_id = '{}/{}_scene'.format(
        ini['EXPORT']['export_coll'], tmax_name.lower())

    if tcorr_source.upper() not in ['GRIDDED_COLD', 'GRIDDED']:
        raise ValueError('unsupported tcorr_source for these tools')

    # For now only support reading specific Tmax sources
    if tmax_name.upper() not in ['DAYMET_MEDIAN_V2']:
        raise ValueError('unsupported tmax_source: {}'.format(tmax_name))
    # if (tmax_name.upper() == 'CIMIS' and
    #         ini['INPUTS']['end_date'] < '2003-10-01'):
    #     raise ValueError('CIMIS is not currently available before 2003-10-01')
    # elif (tmax_name.upper() == 'DAYMET' and
    #         ini['INPUTS']['end_date'] > '2018-12-31'):
    #     logging.warning('\nDAYMET is not currently available past 2018-12-31, '
    #                     'using median Tmax values\n')


    # If the user set the tiles argument, use these instead of the INI values
    if tiles:
        logging.info('\nOverriding INI mgrs_tiles and utm_zones parameters')
        logging.info('  user tiles: {}'.format(tiles))
        mgrs_tiles = sorted([y.strip() for x in tiles for y in x.split(',')])
        mgrs_tiles = [x.upper() for x in mgrs_tiles if x]
        logging.info('  mgrs_tiles: {}'.format(', '.join(mgrs_tiles)))
        utm_zones = sorted(list(set([int(x[:2]) for x in mgrs_tiles])))
        logging.info('  utm_zones:  {}'.format(', '.join(map(str, utm_zones))))

    today_dt = datetime.datetime.now()
    today_dt = today_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if recent_days:
        logging.info('\nOverriding INI "start_date" and "end_date" parameters')
        logging.info('  Recent days: {}'.format(recent_days))
        end_dt = today_dt - datetime.timedelta(days=1)
        start_dt = today_dt - datetime.timedelta(days=recent_days)
        start_date = start_dt.strftime('%Y-%m-%d')
        end_date = end_dt.strftime('%Y-%m-%d')
    elif start_dt and end_dt:
        # Attempt to use the function start/end dates
        logging.info('\nOverriding INI "start_date" and "end_date" parameters')
        logging.info('  Custom date range')
        start_date = start_dt.strftime('%Y-%m-%d')
        end_date = end_dt.strftime('%Y-%m-%d')
    else:
        # Parse the INI start/end dates
        logging.info('\nINI date range')
        try:
            start_dt = datetime.datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.datetime.strptime(end_date, '%Y-%m-%d')
        except Exception as e:
            raise e
    logging.info('  Start: {}'.format(start_date))
    logging.info('  End:   {}'.format(end_date))

    # TODO: Add a few more checks on the dates
    if end_dt < start_dt:
        raise ValueError('end date can not be before start date')

    # logging.info('\nIteration date range')
    # iter_start_dt = start_dt
    # iter_end_dt = end_dt + datetime.timedelta(days=1)
    # # iter_start_dt = start_dt - datetime.timedelta(days=interp_days)
    # # iter_end_dt = end_dt + datetime.timedelta(days=interp_days+1)
    # logging.info('  Start: {}'.format(iter_start_dt.strftime('%Y-%m-%d')))
    # logging.info('  End:   {}'.format(iter_end_dt.strftime('%Y-%m-%d')))


    logging.info('\nInitializing Earth Engine')
    if gee_key_file:
        logging.info('  Using service account key file: {}'.format(gee_key_file))
        # The "EE_ACCOUNT" parameter is not used if the key file is valid
        ee.Initialize(ee.ServiceAccountCredentials('x', key_file=gee_key_file))
    else:
        ee.Initialize()


    # Get a Tmax image to set the Tcorr values to
    logging.debug('\nTmax properties')
    tmax_source = tmax_name.split('_', 1)[0]
    tmax_version = tmax_name.split('_', 1)[1]
    if 'MEDIAN' in tmax_name.upper():
        tmax_coll_id = 'projects/earthengine-legacy/assets/' \
                       'projects/usgs-ssebop/tmax/{}'.format(tmax_name.lower())
        tmax_coll = ee.ImageCollection(tmax_coll_id)
        tmax_mask = ee.Image(tmax_coll.first()).select([0]).multiply(0)
    # else:
    #     raise ValueError('unsupported tmax_source: {}'.format(tmax_name))
    logging.debug('  Collection: {}'.format(tmax_coll_id))
    logging.debug('  Source:  {}'.format(tmax_source))
    logging.debug('  Version: {}'.format(tmax_version))


    if not ee.data.getInfo(tcorr_scene_coll_id.rsplit('/', 1)[0]):
        logging.info('\nExport folder does not exist and will be built'
                     '\n  {}'.format(tcorr_scene_coll_id.rsplit('/', 1)[0]))
        input('Press ENTER to continue')
        ee.data.createAsset({'type': 'FOLDER'}, tcorr_scene_coll_id.rsplit('/', 1)[0])
    if not ee.data.getInfo(tcorr_scene_coll_id):
        logging.info('\nExport collection does not exist and will be built'
                     '\n  {}'.format(tcorr_scene_coll_id))
        input('Press ENTER to continue')
        ee.data.createAsset({'type': 'IMAGE_COLLECTION'}, tcorr_scene_coll_id)


    # Get current asset list
    logging.debug('\nGetting GEE asset list')
    asset_list = utils.get_ee_assets(tcorr_scene_coll_id)
    # if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
    #     pprint.pprint(asset_list[:10])


    # Get current running tasks
    tasks = utils.get_ee_tasks()
    ready_task_count = sum(1 for t in tasks.values() if t['state'] == 'READY')
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        logging.debug('  Tasks: {}\n'.format(len(tasks)))
        input('ENTER')
    # ready_task_count = delay_task(ready_task_count, delay_time, max_ready)


    # Get list of MGRS tiles that intersect the study area
    logging.debug('\nMGRS Tiles/Zones')
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


    # Build the complete WRS2 list for filtering the image list
    wrs2_tile_list = sorted(list(set(
        wrs2 for tile_info in export_list
        for wrs2 in tile_info['wrs2_tiles'])))
    if wrs2_skip_list:
        wrs2_tile_list = [wrs2 for wrs2 in wrs2_tile_list
                          if wrs2 not in wrs2_skip_list]
    if wrs2_row_skip_list:
        wrs2_tile_list = [wrs2 for wrs2 in wrs2_tile_list
                          if wrs2 not in wrs2_row_skip_list]
    if wrs2_path_skip_list:
        wrs2_tile_list = [wrs2 for wrs2 in wrs2_tile_list
                          if wrs2 not in wrs2_path_skip_list]


    # CGM - This is kind of backwards, but rebuild the MGRS geometry in order
    #   to filter the model collection object
    mgrs_tile_list = sorted(list(set(
        tile_info['index'] for tile_info in export_list)))
    mgrs_geom = ee.FeatureCollection(mgrs_ftr_coll_id)\
        .filter(ee.Filter.inList('mgrs', mgrs_tile_list))\
        .geometry()


    for export_dt in sorted(utils.date_range(start_dt, end_dt),
                            reverse=reverse_flag):
        export_date = export_dt.strftime('%Y-%m-%d')
        next_date = (export_dt + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        logging.info(f'Date: {export_date}')

        model_obj = ssebop.Collection(
            collections=collections,
            start_date=export_date,
            end_date=next_date,
            cloud_cover_max=cloud_cover,
            geometry=mgrs_geom,
            model_args=model_args,
            # filter_args=filter_args,
        )
        landsat_coll = model_obj.overpass(variables=['ndvi'])
        # pprint.pprint(landsat_coll.aggregate_array('system:id').getInfo())
        # input('ENTER')

        try:
            image_id_list = landsat_coll.aggregate_array('system:id').getInfo()
        except Exception as e:
            logging.warning('  Error getting image ID list, skipping date')
            logging.debug(f'  {e}')
            continue
        # pprint.pprint(image_id_list)
        # input('ENTER')

        # Get list of existing images for the target date
        logging.debug('  Getting GEE asset list')
        asset_coll = ee.ImageCollection(tcorr_scene_coll_id) \
            .filterDate(export_date, next_date) \
            .filter(ee.Filter.inList('wrs2_tile', wrs2_tile_list))
        asset_props = {f'{tcorr_scene_coll_id}/{x["properties"]["system:index"]}':
                           x['properties']
                       for x in utils.get_info(asset_coll)['features']}
        # asset_props = {x['id']: x['properties']
        #                for x in assets_info['features']}

        # Sort image ID list by path/row
        image_id_list = sorted(image_id_list,
                               key=lambda k: k.split('/')[-1].split('_')[-2],
                               reverse=True)

        for image_id in image_id_list:
            coll_id, scene_id = image_id.rsplit('/', 1)

            wrs2_path = int(scene_id[5:8])
            wrs2_row = int(scene_id[8:11])
            wrs2_tile = 'p{:03d}r{:03d}'.format(wrs2_path, wrs2_row)
            if wrs2_tile not in wrs2_tile_list:
                logging.debug(f'{scene_id} - not in wrs2 tile list, skipping')
                continue
            else:
                logging.info(f'{scene_id}')

            export_id = export_id_fmt.format(
                product=tmax_name.lower(), scene_id=scene_id)
            logging.debug(f'  Export ID: {export_id}')

            asset_id = asset_id_fmt.format(
                coll_id=tcorr_scene_coll_id, scene_id=scene_id)
            logging.debug(f'    Collection: {os.path.dirname(asset_id)}')
            logging.debug(f'    Image ID:   {os.path.basename(asset_id)}')

            if update_flag:
                def version_number(version_str):
                    return list(map(int, version_str.split('.')))

                if export_id in tasks.keys():
                    logging.info('  Task already submitted, skipping')
                    continue
                # In update mode only overwrite if the version is old
                if asset_props and asset_id in asset_props.keys():
                    model_ver = version_number(ssebop.__version__)
                    asset_ver = version_number(
                        asset_props[asset_id]['model_version'])

                    if asset_ver < model_ver:
                        logging.info('    Existing asset model version is old, '
                                     'removing')
                        logging.debug(f'    asset: {asset_ver}\n'
                                      f'    model: {model_ver}')
                        try:
                            ee.data.deleteAsset(asset_id)
                        except:
                            logging.info('    Error removing asset, skipping')
                            continue
                    # elif ((('T1_RT_TOA' in asset_props[asset_id]['coll_id']) and
                    #            ('T1_RT_TOA' not in image_id)) or
                    #           (('T1_RT' in asset_props[asset_id]['coll_id']) and
                    #            ('T1_RT' not in image_id))):
                    #         logging.info(
                    #             '    Existing asset is from realtime Landsat '
                    #             'collection, removing')
                    #         try:
                    #             ee.data.deleteAsset(asset_id)
                    #         except:
                    #             logging.info('    Error removing asset, skipping')
                    #             continue
                    else:
                        logging.info('  Asset is up to date, skipping')
                        continue
            elif overwrite_flag:
                if export_id in tasks.keys():
                    logging.info('  Task already submitted, cancelling')
                    ee.data.cancelTask(tasks[export_id]['id'])
                # This is intentionally not an "elif" so that a task can be
                # cancelled and an existing image/file/asset can be removed
                if asset_id in asset_list:
                    logging.info('  Asset already exists, removing')
                    ee.data.deleteAsset(asset_id)
            else:
                if export_id in tasks.keys():
                    logging.debug('  Task already submitted, exiting')
                    continue
                elif asset_id in asset_list:
                    logging.debug('  Asset already exists, skipping')
                    continue

            # Get the input image grid and spatial reference
            image_info = ee.Image(image_id).select(['B3']).getInfo()
            image_geo = image_info['bands'][0]['crs_transform']
            image_crs = image_info['bands'][0]['crs']
            image_shape = image_info['bands'][0]['dimensions']
            # Transform format: [30, 0, 591285, 0, -30, 4256115]
            image_extent = [
                image_geo[2], image_geo[5] + image_shape[1] * image_geo[4],
                image_geo[2] + image_shape[0] * image_geo[0], image_geo[5]]
            logging.debug('    Image CRS: {}'.format(image_crs))
            logging.debug('    Image Extent: {}'.format(image_extent))
            logging.debug('    Image Geo: {}'.format(image_geo))
            logging.debug('    Image Shape: {}'.format(image_shape))

            # Adjust the image extent to the coarse resolution grid
            # EXPORT_GEO = [5000, 0, 15, 0, -5000, 15]
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
            logging.debug('    Export CRS: {}'.format(image_crs))
            logging.debug('    Export Extent: {}'.format(export_extent))
            logging.debug('    Export Geo: {}'.format(export_geo))
            logging.debug('    Export Shape: {}'.format(export_shape))

            # CGM - Why are we not using the from_image_id() method?
            # t_obj = ssebop.Image.from_image_id(ee.Image(image_id), **model_args)
            if coll_id.endswith('_SR'):
                t_obj = ssebop.Image.from_landsat_c1_sr(
                    ee.Image(image_id), **model_args)
            elif coll_id.endswith('_TOA'):
                t_obj = ssebop.Image.from_landsat_c1_toa(
                    ee.Image(image_id), **model_args)
            else:
                raise ValueError('Could not determine Landsat type')

            # CGM - Intentionally not calling the tcorr method directly since
            #   there may be compositing with climos or the scene average
            if tcorr_source == 'GRIDDED':
                tcorr_img = t_obj.tcorr_gridded
            elif tcorr_source == 'GRIDDED_COLD':
                tcorr_img = t_obj.tcorr_gridded_cold
            # tcorr_img = t_obj.tcorr

            # Clip to the Landsat image footprint
            tcorr_img = ee.Image(tcorr_img).clip(ee.Image(image_id).geometry())
            # Clear the transparency mask (from clipping)
            tcorr_img = tcorr_img.updateMask(tcorr_img.unmask(0))

            if clip_ocean_flag:
                tcorr_img = tcorr_img\
                    .updateMask(ee.Image('projects/openet/ocean_mask'))
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
                    'model_name': model_name,
                    'model_version': ssebop.__version__,
                    'month': int(export_dt.month),
                    'scene_id': scene_id,
                    'system:time_start': image_info['properties']['system:time_start'],
                    'tcorr_index': TCORR_INDICES[tcorr_source.upper()],
                    'tcorr_source': tcorr_source.upper(),
                    'tmax_source': tmax_source.upper(),
                    'tmax_version': tmax_version.upper(),
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

            logging.info('  Starting export task')
            utils.ee_task_start(task)

            ready_task_count += 1
            # logging.debug(f'  Ready tasks: {ready_task_count}')

            # Pause before starting the next date (not export task)
            ready_task_count = delay_task(ready_task_count, delay_time, max_ready)
            # utils.delay_task(delay_time, max_ready)
            # logging.debug('')


# CGM - This is a modified copy of openet.utils.delay_task()
#   It was changed to take and return the number of ready tasks
#   This change may eventually be pushed to openet.utils.delay_task()
def delay_task(ready_task_count, delay_time=0, max_ready=3000):
    """Delay script execution based on number of READY tasks

    Parameters
    ----------
    ready_task_count : int
    delay_time : float, int
        Delay time in seconds between starting export tasks or checking the
        number of queued tasks if "max_ready" is > 0.  The default is 0.
        The delay time will be set to a minimum of 10 seconds if max_ready > 0.
    max_ready : int, optional
        Maximum number of queued "READY" tasks.

    Returns
    -------
    ready_task_count

    """
    # Force delay time to be a positive value
    # (since parameter used to support negative values)
    if delay_time < 0:
        delay_time = abs(delay_time)

    if (max_ready <= 0 or max_ready >= 3000) and delay_time > 0:
        # Assume max_ready was not set and just wait the delay time
        logging.debug(f'  Pausing {delay_time} seconds')
        time.sleep(delay_time)
        ready_task_count = 0
    elif ready_task_count < max_ready:
        # Skip waiting if the number of ready tasks is below the max
        logging.debug(f'  Ready tasks: {ready_task_count}')
    else:
        # Don't continue to the next export until the number of READY tasks
        # is greater than or equal to "max_ready"

        # Force delay_time to be at least 10 seconds if max_ready is set
        #   to avoid excessive EE calls
        delay_time = max(delay_time, 10)

        # Make an initial pause before checking tasks lists to allow
        #   for previous export to start up.
        logging.debug(f'  Pausing {delay_time} seconds')
        time.sleep(delay_time)

        while True:
            ready_task_count = len(utils.get_ee_tasks(
                states=['READY'], verbose=False).keys())
            logging.debug(f'  Ready tasks: {ready_task_count}')
            if ready_task_count >= max_ready:
                logging.debug(f'  Pausing {delay_time} seconds')
                time.sleep(delay_time)
            else:
                logging.debug('  Continuing iteration')
                break
    return ready_task_count


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
    logging.debug('  {}'.format(study_area_coll_id))
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
        logging.debug('  Property: {}'.format(study_area_property))
        logging.debug('  Features: {}'.format(','.join(study_area_features)))
        study_area_coll = study_area_coll.filter(
            ee.Filter.inList(study_area_property, study_area_features))

    logging.debug('Building MGRS tile list')
    tiles_coll = ee.FeatureCollection(mgrs_coll_id) \
        .filterBounds(study_area_coll.geometry())

    # Filter collection by user defined lists
    if utm_zones:
        logging.debug('  Filter user UTM Zones:    {}'.format(utm_zones))
        tiles_coll = tiles_coll.filter(ee.Filter.inList(utm_property, utm_zones))
    if mgrs_skip_list:
        logging.debug('  Filter MGRS skip list:    {}'.format(mgrs_skip_list))
        tiles_coll = tiles_coll.filter(
            ee.Filter.inList(mgrs_property, mgrs_skip_list).Not())
    if mgrs_tiles:
        logging.debug('  Filter MGRS tiles/zones:  {}'.format(mgrs_tiles))
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
        logging.debug('  Filter WRS2 tiles: {}'.format(wrs2_tiles))
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
        description='Compute/export gridded Tcorr images by date',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-i', '--ini', type=utils.arg_valid_file,
        help='Input file', metavar='FILE')
    parser.add_argument(
        '--debug', default=logging.INFO, const=logging.DEBUG,
        help='Debug level logging', action='store_const', dest='loglevel')
    parser.add_argument(
        '--delay', default=0, type=float,
        help='Delay (in seconds) between each export tasks')
    parser.add_argument(
        '--key', type=utils.arg_valid_file, metavar='FILE',
        help='JSON key file')
    parser.add_argument(
        '--overwrite', default=False, action='store_true',
        help='Force overwrite of existing files')
    parser.add_argument(
        '--ready', default=3000, type=int,
        help='Maximum number of queued READY tasks')
    parser.add_argument(
        '--recent', default=0, type=int,
        help='Number of days to process before current date '
             '(ignore INI start_date and end_date')
    parser.add_argument(
        '--reverse', default=False, action='store_true',
        help='Process dates/scenes in reverse order')
    parser.add_argument(
        '--tiles', default='', nargs='+',
        help='Comma/space separated list of tiles to process')
    parser.add_argument(
        '--update', default=False, action='store_true',
        help='Update images with older model version numbers')
    parser.add_argument(
        '--start', type=utils.arg_valid_date, metavar='DATE', default=None,
        help='Start date (format YYYY-MM-DD)')
    parser.add_argument(
        '--end', type=utils.arg_valid_date, metavar='DATE', default=None,
        help='End date (format YYYY-MM-DD)')
    args = parser.parse_args()

    return args


if __name__ == "__main__":
    args = arg_parse()

    logging.basicConfig(level=args.loglevel, format='%(message)s')
    logging.getLogger('googleapiclient').setLevel(logging.ERROR)

    main(ini_path=args.ini, overwrite_flag=args.overwrite,
         delay_time=args.delay, gee_key_file=args.key, max_ready=args.ready,
         reverse_flag=args.reverse, tiles=args.tiles, update_flag=args.update,
         recent_days=args.recent, start_dt=args.start, end_dt=args.end,
    )
