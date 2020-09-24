import argparse
from builtins import input
import datetime
import logging
import pprint
import sys

import ee

import openet.ssebop as ssebop
import utils
# from . import utils

DEFAULT_TCORR_INDEX = 7
NODATA_TCORR_INDEX = 9


def main(ini_path=None, overwrite_flag=False, delay_time=0, gee_key_file=None,
         max_ready=-1, reverse_flag=False):
    """Compute default Tcorr images by WRS2 tile

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
    logging.info('\nCompute default Tcorr images by WRS2 tile')

    ini = utils.read_ini(ini_path)

    model_name = 'SSEBOP'
    # model_name = ini['INPUTS']['et_model'].upper()

    tmax_name = ini[model_name]['tmax_source']

    export_id_fmt = 'tcorr_scene_{product}_{wrs2}_default'
    asset_id_fmt = '{coll_id}/{wrs2}'

    tcorr_default_coll_id = '{}/{}_default'.format(
        ini['EXPORT']['export_coll'], tmax_name.lower())

    wrs2_coll_id = 'projects/earthengine-legacy/assets/' \
                   'projects/usgs-ssebop/wrs2_descending_custom'
    wrs2_tile_field = 'WRS2_TILE'
    # wrs2_path_field = 'ROW'
    # wrs2_row_field = 'PATH'

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
        study_area_extent = str(ini['INPUTS']['study_area_extent']) \
            .replace('[', '').replace(']', '').split(',')
        study_area_extent = [float(x.strip()) for x in study_area_extent]
    except KeyError:
        study_area_extent = None
        logging.debug('  study_area_extent: not set in INI')
    except Exception as e:
        raise e

    try:
        tcorr_default = ini[model_name]['tcorr_default']
    except:
        tcorr_default = 0.978


    logging.info('\nInitializing Earth Engine')
    if gee_key_file:
        logging.info('  Using service account key file: {}'.format(gee_key_file))
        # The "EE_ACCOUNT" parameter is not used if the key file is valid
        ee.Initialize(ee.ServiceAccountCredentials('x', key_file=gee_key_file))
    else:
        ee.Initialize()


    logging.debug('\nTmax properties')
    tmax_source = tmax_name.split('_', 1)[0]
    tmax_version = tmax_name.split('_', 1)[1]
    tmax_coll_id = 'projects/earthengine-legacy/assets/' \
                   'projects/usgs-ssebop/tmax/{}'.format(tmax_name.lower())
    tmax_coll = ee.ImageCollection(tmax_coll_id)
    tmax_mask = ee.Image(tmax_coll.first()).select([0]).multiply(0)
    logging.debug('  Collection: {}'.format(tmax_coll_id))
    logging.debug('  Source: {}'.format(tmax_source))
    logging.debug('  Version: {}'.format(tmax_version))


    # # Get the Tcorr scene image collection properties
    # logging.debug('\nTcorr scene collection')
    # tcorr_scene_coll_id = '{}/{}_scene'.format(
    #     ini['EXPORT']['export_coll'], tmax_name.lower())


    logging.debug('\nExport properties')
    export_info = utils.get_info(ee.Image(tmax_mask))
    if 'daymet' in tmax_name.lower():
        # Custom smaller extent for DAYMET focused on CONUS
        export_extent = [-1999750, -1890500, 2500250, 1109500]
        export_shape = [4500, 3000]
        export_geo = [1000, 0, -1999750, 0, -1000, 1109500]
        # Custom medium extent for DAYMET of CONUS, Mexico, and southern Canada
        # export_extent = [-2099750, -3090500, 2900250, 1909500]
        # export_shape = [5000, 5000]
        # export_geo = [1000, 0, -2099750, 0, -1000, 1909500]
        export_crs = export_info['bands'][0]['crs']
    else:
        export_crs = export_info['bands'][0]['crs']
        export_geo = export_info['bands'][0]['crs_transform']
        export_shape = export_info['bands'][0]['dimensions']
        # export_geo = ee.Image(tmax_mask).projection().getInfo()['transform']
        # export_crs = ee.Image(tmax_mask).projection().getInfo()['crs']
        # export_shape = ee.Image(tmax_mask).getInfo()['bands'][0]['dimensions']
        export_extent = [
            export_geo[2], export_geo[5] + export_shape[1] * export_geo[4],
            export_geo[2] + export_shape[0] * export_geo[0], export_geo[5]]
    export_geom = ee.Geometry.Rectangle(
        export_extent, proj=export_crs, geodesic=False)
    logging.debug('  CRS: {}'.format(export_crs))
    logging.debug('  Extent: {}'.format(export_extent))
    logging.debug('  Geo: {}'.format(export_geo))
    logging.debug('  Shape: {}'.format(export_shape))


    if study_area_extent is None:
        if 'daymet' in tmax_name.lower():
            # CGM - For now force DAYMET to a slightly smaller "CONUS" extent
            study_area_extent = [-125, 25, -65, 50]
            # study_area_extent = [-125, 25, -65, 49]
            # study_area_extent =  [-125, 25, -65, 52]
        elif 'cimis' in tmax_name.lower():
            study_area_extent = [-124, 35, -119, 42]
        else:
            # TODO: Make sure output from bounds is in WGS84
            study_area_extent = tmax_mask.geometry().bounds().getInfo()
        logging.debug(f'\nStudy area extent not set in INI, '
                      f'default to {study_area_extent}')
    study_area_geom = ee.Geometry.Rectangle(
        study_area_extent, proj='EPSG:4326', geodesic=False)


    if not ee.data.getInfo(tcorr_default_coll_id):
        logging.info('\nExport collection does not exist and will be built'
                     '\n  {}'.format(tcorr_default_coll_id))
        input('Press ENTER to continue')
        ee.data.createAsset({'type': 'IMAGE_COLLECTION'}, tcorr_default_coll_id)

    # Get current asset list
    logging.debug('\nGetting GEE asset list')
    asset_list = utils.get_ee_assets(tcorr_default_coll_id)
    # if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
    #     pprint.pprint(asset_list[:10])

    # Get current running tasks
    tasks = utils.get_ee_tasks()
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        logging.debug('  Tasks: {}\n'.format(len(tasks)))
        input('ENTER')


    # Get the list of WRS2 tiles that intersect the data area and study area
    wrs2_coll = ee.FeatureCollection(wrs2_coll_id)\
        .filterBounds(export_geom)\
        .filterBounds(study_area_geom)
    if wrs2_tiles:
        wrs2_coll = wrs2_coll.filter(ee.Filter.inList(wrs2_tile_field, wrs2_tiles))
    wrs2_info = wrs2_coll.getInfo()['features']


    for wrs2_ftr in sorted(wrs2_info,
                           key=lambda k: k['properties']['WRS2_TILE'],
                           reverse=reverse_flag):
        wrs2_tile = wrs2_ftr['properties'][wrs2_tile_field]
        logging.info('{}'.format(wrs2_tile))

        wrs2_path = int(wrs2_tile[1:4])
        wrs2_row = int(wrs2_tile[5:8])
        # wrs2_path = wrs2_ftr['properties'][wrs2_path_field]
        # wrs2_row = wrs2_ftr['properties'][wrs2_row_field]

        export_id = export_id_fmt.format(
            product=tmax_name.lower(), wrs2=wrs2_tile)
        logging.debug('  Export ID: {}'.format(export_id))

        asset_id = asset_id_fmt.format(
            coll_id=tcorr_default_coll_id, wrs2=wrs2_tile)
        logging.debug('  Asset ID: {}'.format(asset_id))

        if overwrite_flag:
            if export_id in tasks.keys():
                logging.debug('  Task already submitted, cancelling')
                ee.data.cancelTask(tasks[export_id]['id'])
            # This is intentionally not an "elif" so that a task can be
            # cancelled and an existing image/file/asset can be removed
            if asset_id in asset_list:
                logging.debug('  Asset already exists, removing')
                ee.data.deleteAsset(asset_id)
        else:
            if export_id in tasks.keys():
                logging.debug('  Task already submitted, exiting')
                continue
            elif asset_id in asset_list:
                logging.debug('  Asset already exists, skipping')
                continue

        # Clip the mask image to the Landsat footprint
        mask_img = tmax_mask.add(1).clip(ee.Geometry(wrs2_ftr['geometry']))

        # Apply the default Tcorr value and then clear the transparency mask
        output_img = mask_img.multiply(0.978).rename(['tcorr'])\
            .updateMask(mask_img.unmask(0))

        # # Clip to the Landsat image footprint
        # output_img = tmax_mask.add(tcorr_default) \
        #     .rename(['tcorr']) \
        #     .clip(ee.Geometry(wrs2_ftr['geometry']))
        # # Clear the transparency mask
        # output_img = output_img.updateMask(output_img.unmask(0))

        output_img = output_img.set({
            'date_ingested': datetime.datetime.today().strftime('%Y-%m-%d'),
            'model_name': model_name,
            'model_version': ssebop.__version__,
            # 'system:time_start': utils.millis(start_dt),
            'tcorr_value': tcorr_default,
            'tcorr_index': DEFAULT_TCORR_INDEX,
            'tmax_source': tmax_source.upper(),
            'tmax_version': tmax_version.upper(),
            'wrs2_path': wrs2_path,
            'wrs2_row': wrs2_row,
            'wrs2_tile': wrs2_tile,
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


def arg_parse():
    """"""
    parser = argparse.ArgumentParser(
        description='Compute/export default Tcorr images by WRS2 tile',
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
        help='Process dates in reverse order')
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
