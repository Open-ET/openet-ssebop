import argparse
from builtins import input
from collections import defaultdict
import datetime
import json
import logging
import math
import pprint
import sys

import ee

import openet.ssebop as ssebop
import utils
# from . import utils


def main(ini_path=None, overwrite_flag=False, delay_time=0, gee_key_file=None,
         max_ready=-1, cron_flag=False, reverse_flag=False):
    """Compute daily Tcorr images

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
        Maximum number of queued "READY" tasks.  The default is -1 which is
        implies no limit to the number of tasks that will be submitted.
    cron_flag : bool, optional
        If True, only compute Tcorr daily image if existing image does not have
        all available image (using the 'wrs2_tiles' property) and limit the
        date range to the last 64 days (~2 months).
    reverse_flag : bool, optional
        If True, process dates in reverse order.
    """
    logging.info('\nCompute daily Tcorr images')

    ini = utils.read_ini(ini_path)

    model_name = 'SSEBOP'
    # model_name = ini['INPUTS']['et_model'].upper()

    if (ini[model_name]['tmax_source'].upper() == 'CIMIS' and
            ini['INPUTS']['end_date'] < '2003-10-01'):
        logging.error(
            '\nCIMIS is not currently available before 2003-10-01, exiting\n')
        sys.exit()
    elif (ini[model_name]['tmax_source'].upper() == 'DAYMET' and
            ini['INPUTS']['end_date'] > '2018-12-31'):
        logging.warning(
            '\nDAYMET is not currently available past 2018-12-31, '
            'using median Tmax values\n')
        # sys.exit()
    # elif (ini[model_name]['tmax_source'].upper() == 'TOPOWX' and
    #         ini['INPUTS']['end_date'] > '2017-12-31'):
    #     logging.warning(
    #         '\nDAYMET is not currently available past 2017-12-31, '
    #         'using median Tmax values\n')
    #     # sys.exit()

    logging.info('\nInitializing Earth Engine')
    if gee_key_file:
        logging.info('  Using service account key file: {}'.format(gee_key_file))
        # The "EE_ACCOUNT" parameter is not used if the key file is valid
        ee.Initialize(ee.ServiceAccountCredentials('deadbeef', key_file=gee_key_file),
                      use_cloud_api=True)
    else:
        ee.Initialize(use_cloud_api=True)

    # Output Tcorr daily image collection
    tcorr_daily_coll_id = '{}/{}_daily'.format(
        ini['EXPORT']['export_coll'], ini[model_name]['tmax_source'].lower())

    # Get a Tmax image to set the Tcorr values to
    logging.debug('\nTmax properties')
    tmax_name = ini[model_name]['tmax_source']
    tmax_source = tmax_name.split('_', 1)[0]
    tmax_version = tmax_name.split('_', 1)[1]
    tmax_coll_id = 'projects/earthengine-legacy/assets/' \
                   'projects/usgs-ssebop/tmax/{}'.format(tmax_name.lower())
    tmax_coll = ee.ImageCollection(tmax_coll_id)
    tmax_mask = ee.Image(tmax_coll.first()).select([0]).multiply(0)
    logging.debug('  Collection: {}'.format(tmax_coll_id))
    logging.debug('  Source: {}'.format(tmax_source))
    logging.debug('  Version: {}'.format(tmax_version))

    logging.debug('\nExport properties')
    export_info = utils.get_info(ee.Image(tmax_mask))
    if 'daymet' in ini[model_name]['tmax_source'].lower():
        # Custom smaller extent for DAYMET
        export_extent = [-2099750, -3090500, 2900250, 1909500]
        export_shape = [5000, 5000]
        export_geo = [1000, 0, -2200750, 0, -1000, 1910500]
        # # DAYMET grid from user guide
        # export_extent = [-4560750, -3090500, 3253250, 4984500]
        # export_shape = [7814, 8075]
        # export_geo = [1000, 0, -4560750, 0, -1000, 4984500]
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
    logging.debug('  CRS: {}'.format(export_crs))
    logging.debug('  Extent: {}'.format(export_extent))
    logging.debug('  Geo: {}'.format(export_geo))
    logging.debug('  Shape: {}'.format(export_shape))


    # This extent will limit the WRS2 tiles that are included
    if 'daymet' in ini[model_name]['tmax_source'].lower():
        export_geom = ee.Geometry.Rectangle(
            [-125, 15, -65, 55], proj='EPSG:4326', geodesic=False)
    elif 'cimis' in ini[model_name]['tmax_source'].lower():
        export_geom = ee.Geometry.Rectangle(
            [-124, 35, -119, 42], proj='EPSG:4326', geodesic=False)
    else:
        export_geom = tmax_mask.geometry()


    # If cell_size parameter is set in the INI,
    # adjust the output cellsize and recompute the transform and shape
    try:
        export_cs = float(ini['EXPORT']['cell_size'])
        export_shape = [
            int(math.ceil(abs((export_shape[0] * export_geo[0]) / export_cs))),
            int(math.ceil(abs((export_shape[1] * export_geo[4]) / export_cs)))]
        export_geo = [export_cs, 0.0, export_geo[2], 0.0, -export_cs, export_geo[5]]
        logging.debug('  Custom export cell size: {}'.format(export_cs))
        logging.debug('  Geo: {}'.format(export_geo))
        logging.debug('  Shape: {}'.format(export_shape))
    except KeyError:
        pass

    if not ee.data.getInfo(tcorr_daily_coll_id):
        logging.info('\nExport collection does not exist and will be built'
                     '\n  {}'.format(tcorr_daily_coll_id))
        input('Press ENTER to continue')
        ee.data.createAsset({'type': 'IMAGE_COLLECTION'}, tcorr_daily_coll_id)

    # Get current asset list
    logging.debug('\nGetting GEE asset list')
    asset_list = utils.get_ee_assets(tcorr_daily_coll_id)
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        pprint.pprint(asset_list[:10])

    # Get current running tasks
    tasks = utils.get_ee_tasks()
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        logging.debug('  Tasks: {}\n'.format(len(tasks)))
        input('ENTER')


    collections = [x.strip() for x in ini['INPUTS']['collections'].split(',')]

    # Limit by year and month
    try:
        month_list = sorted(list(utils.parse_int_set(ini['TCORR']['months'])))
    except:
        logging.info('\nTCORR "months" parameter not set in the INI,'
                     '\n  Defaulting to all months (1-12)\n')
        month_list = list(range(1, 13))
    try:
        year_list = sorted(list(utils.parse_int_set(ini['TCORR']['years'])))
    except:
        logging.info('\nTCORR "years" parameter not set in the INI,'
                     '\n  Defaulting to all available years\n')
        year_list = []

    # Key is cycle day, value is a reference date on that cycle
    # Data from: https://landsat.usgs.gov/landsat_acq
    # I only need to use 8 cycle days because of 5/7 and 7/8 are offset
    cycle_dates = {
        7: '1970-01-01',
        8: '1970-01-02',
        1: '1970-01-03',
        2: '1970-01-04',
        3: '1970-01-05',
        4: '1970-01-06',
        5: '1970-01-07',
        6: '1970-01-08',
    }
    # cycle_dates = {
    #     1:  '2000-01-06',
    #     2:  '2000-01-07',
    #     3:  '2000-01-08',
    #     4:  '2000-01-09',
    #     5:  '2000-01-10',
    #     6:  '2000-01-11',
    #     7:  '2000-01-12',
    #     8:  '2000-01-13',
    #     # 9:  '2000-01-14',
    #     # 10: '2000-01-15',
    #     # 11: '2000-01-16',
    #     # 12: '2000-01-01',
    #     # 13: '2000-01-02',
    #     # 14: '2000-01-03',
    #     # 15: '2000-01-04',
    #     # 16: '2000-01-05',
    # }
    cycle_base_dt = datetime.datetime.strptime(cycle_dates[1], '%Y-%m-%d')

    if cron_flag:
        # CGM - This seems like a silly way of getting the date as a datetime
        #   Why am I doing this and not using the commented out line?
        iter_end_dt = datetime.date.today().strftime('%Y-%m-%d')
        iter_end_dt = datetime.datetime.strptime(iter_end_dt, '%Y-%m-%d')
        iter_end_dt = iter_end_dt + datetime.timedelta(days=-4)
        # iter_end_dt = datetime.datetime.today() + datetime.timedelta(days=-1)
        iter_start_dt = iter_end_dt + datetime.timedelta(days=-64)
    else:
        iter_start_dt = datetime.datetime.strptime(
            ini['INPUTS']['start_date'], '%Y-%m-%d')
        iter_end_dt = datetime.datetime.strptime(
            ini['INPUTS']['end_date'], '%Y-%m-%d')
    logging.debug('Start Date: {}'.format(iter_start_dt.strftime('%Y-%m-%d')))
    logging.debug('End Date:   {}\n'.format(iter_end_dt.strftime('%Y-%m-%d')))


    for export_dt in sorted(utils.date_range(iter_start_dt, iter_end_dt),
                            reverse=reverse_flag):
        export_date = export_dt.strftime('%Y-%m-%d')
        next_date = (export_dt + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        if month_list and export_dt.month not in month_list:
            logging.debug(f'Date: {export_date} - month not in INI - skipping')
            continue
        elif year_list and export_dt.year not in year_list:
            logging.debug(f'Date: {export_date} - year not in INI - skipping')
            continue
        elif export_date >= datetime.datetime.today().strftime('%Y-%m-%d'):
            logging.debug(f'Date: {export_date} - unsupported date - skipping')
            continue
        elif export_date < '1984-03-23':
            logging.debug(f'Date: {export_date} - no Landsat 5+ images before '
                         '1984-03-16 - skipping')
            continue
        logging.info(f'Date: {export_date}')

        export_id = ini['EXPORT']['export_id_fmt'] \
            .format(
                product=tmax_name.lower(),
                date=export_dt.strftime('%Y%m%d'),
                export=datetime.datetime.today().strftime('%Y%m%d'))
        logging.debug('  Export ID: {}'.format(export_id))

        asset_id = '{}/{}_{}'.format(
            tcorr_daily_coll_id, export_dt.strftime('%Y%m%d'),
            datetime.datetime.today().strftime('%Y%m%d'))
        logging.debug('  Asset ID: {}'.format(asset_id))

        if overwrite_flag:
            if export_id in tasks.keys():
                logging.debug('  Task already submitted, cancelling')
                ee.data.cancelTask(tasks[export_id])
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

        # Build and merge the Landsat collections
        model_obj = ssebop.Collection(
            collections=collections,
            start_date=export_dt.strftime('%Y-%m-%d'),
            end_date=(export_dt + datetime.timedelta(days=1)).strftime(
                '%Y-%m-%d'),
            cloud_cover_max=float(ini['INPUTS']['cloud_cover']),
            geometry=export_geom,
            # model_args=model_args,
            # filter_args=filter_args,
        )
        landsat_coll = model_obj.overpass(variables=['ndvi'])
        # wrs2_tiles_all = model_obj.get_image_ids()
        # pprint.pprint(landsat_coll.aggregate_array('system:id').getInfo())
        # input('ENTER')

        logging.debug('  Getting available WRS2 tile list')
        landsat_id_list = utils.get_info(landsat_coll.aggregate_array('system:id'))
        if not landsat_id_list:
            logging.info('  No available images - skipping')
            continue
        wrs2_tiles_all = set([id.split('_')[-2] for id in landsat_id_list])
        # print(wrs2_tiles_all)
        # print('\n')

        def tile_set_2_str(tiles):
            """Trying to build a more compact version of the WRS2 tile list"""
            tile_dict = defaultdict(list)
            for tile in tiles:
                tile_dict[int(tile[:3])].append(int(tile[3:]))
            tile_dict = {k: sorted(v) for k, v in tile_dict.items()}
            tile_str = json.dumps(tile_dict, sort_keys=True) \
                .replace('"', '').replace(' ', '')\
                .replace('{', '').replace('}', '')
            return tile_str
        wrs2_tiles_all_str = tile_set_2_str(wrs2_tiles_all)
        # pprint.pprint(wrs2_tiles_all_str)
        # print('\n')

        def tile_str_2_set(tile_str):
            # tile_dict = eval(tile_str)

            tile_set = set()
            for t in tile_str.replace('[', '').split('],'):
                path = int(t.split(':')[0])
                for row in t.split(':')[1].replace(']', '').split(','):
                    tile_set.add('{:03d}{:03d}'.format(path, int(row)))
            return tile_set
        # wrs2_tiles_all_dict = tile_str_2_set(wrs2_tiles_all_str)
        # pprint.pprint(wrs2_tiles_all_dict)


        # If overwriting, start a new export no matter what
        # The default is to no overwrite, so this mode will not be used often
        if not overwrite_flag:
            # Check if there are any previous images for this date
            # If so, only build a new Tcorr image if there are new wrs2_tiles
            #   that were not used in the previous image.
            # Should this code only be run in cron mode or is this the expected
            #   operation when (re)running for any date range?
            # Should we only test the last image
            # or all previous images for the date?
            logging.debug('  Checking for previous exports/versions of daily image')
            tcorr_daily_coll = ee.ImageCollection(tcorr_daily_coll_id)\
                .filterDate(export_date, next_date)\
                .limit(1, 'date_ingested', False)
            tcorr_daily_info = utils.get_info(tcorr_daily_coll)
            # pprint.pprint(tcorr_daily_info)
            # input('ENTER')

            if tcorr_daily_info['features']:
                # Assume we won't be building a new image and only set flag
                #   to True if the WRS2 tile lists are different
                export_flag = False

                # The ".limit(1, ..." on the tcorr_daily_coll above makes this
                # for loop and break statement unnecessary, but leaving for now
                for tcorr_img in tcorr_daily_info['features']:
                    # If the full WRS2 list is not present, rebuild the image
                    # This should only happen for much older Tcorr images
                    if 'wrs2_available' not in tcorr_img['properties'].keys():
                        logging.debug(
                            '    "wrs2_available" property not present in '
                            'previous export')
                        export_flag = True
                        break

                    # DEADBEEF - The wrs2_available property is now a string
                    # wrs2_tiles_old = set(tcorr_img['properties']['wrs2_available'].split(','))

                    # Convert available dict str to a list of path/rows
                    wrs2_tiles_old_str = tcorr_img['properties']['wrs2_available']
                    wrs2_tiles_old = tile_str_2_set(wrs2_tiles_old_str)

                    if wrs2_tiles_all != wrs2_tiles_old:
                        logging.debug('  Tile Lists')
                        logging.debug('  Previous: {}'.format(
                            ', '.join(sorted(wrs2_tiles_old))))
                        logging.debug('  Available: {}'.format(
                            ', '.join(sorted(wrs2_tiles_all))))
                        logging.debug('  New: {}'.format(
                            ', '.join(sorted(wrs2_tiles_all.difference(wrs2_tiles_old)))))
                        logging.debug('  Dropped: {}'.format(
                            ', '.join(sorted(wrs2_tiles_old.difference(wrs2_tiles_all)))))

                        export_flag = True
                        break

                if not export_flag:
                    logging.debug('  No new WRS2 tiles/images - skipping')
                    continue
                # else:
                #     logging.debug('    Building new version')
            else:
                logging.debug('    No previous exports')

        def tcorr_img_func(image):
            t_stats = ssebop.Image.from_landsat_c1_toa(ee.Image(image)) \
                .tcorr_stats
            t_stats = ee.Dictionary(t_stats) \
                .combine({'tcorr_p5': 0, 'tcorr_count': 0}, overwrite=False)
            tcorr = ee.Number(t_stats.get('tcorr_p5'))
            count = ee.Number(t_stats.get('tcorr_count'))

            # Remove the merged collection indices from the system:index
            scene_id = ee.List(
                ee.String(image.get('system:index')).split('_')).slice(-3)
            scene_id = ee.String(scene_id.get(0)).cat('_') \
                .cat(ee.String(scene_id.get(1))).cat('_') \
                .cat(ee.String(scene_id.get(2)))

            return tmax_mask.add(tcorr) \
                .rename(['tcorr']) \
                .clip(image.geometry()) \
                .set({
                    'system:time_start': image.get('system:time_start'),
                    'scene_id': scene_id,
                    'wrs2_path': ee.Number.parse(scene_id.slice(5, 8)),
                    'wrs2_row': ee.Number.parse(scene_id.slice(8, 11)),
                    'wrs2_tile': scene_id.slice(5, 11),
                    'spacecraft_id': image.get('SPACECRAFT_ID'),
                    'tcorr': tcorr,
                    'count': count,
                })
        # Test for one image
        # pprint.pprint(tcorr_img_func(ee.Image(landsat_coll \
        #     .filterMetadata('WRS_PATH', 'equals', 36) \
        #     .filterMetadata('WRS_ROW', 'equals', 33).first())).getInfo())
        # input('ENTER')

        # (Re)build the Landsat collection from the image IDs
        landsat_coll = ee.ImageCollection(landsat_id_list)
        tcorr_img_coll = ee.ImageCollection(landsat_coll.map(tcorr_img_func)) \
            .filterMetadata('count', 'not_less_than',
                            float(ini['TCORR']['min_pixel_count']))

        # If there are no Tcorr values, return an empty image
        tcorr_img = ee.Algorithms.If(
            tcorr_img_coll.size().gt(0),
            tcorr_img_coll.median(),
            tmax_mask.updateMask(0))


        # Build the tile list as a string of a dictionary of paths and rows
        def tile_dict(path):
            # Get the row list for each path
            rows = tcorr_img_coll\
                .filterMetadata('wrs2_path', 'equals', path)\
                .aggregate_array('wrs2_row')
            # Convert rows to integers (otherwise they come back as floats)
            rows = ee.List(rows).sort().map(lambda row: ee.Number(row).int())
            return ee.Number(path).format('%d').cat(':[')\
                .cat(ee.List(rows).join(',')).cat(']')

        path_list = ee.List(tcorr_img_coll.aggregate_array('wrs2_path'))\
            .distinct().sort()
        wrs2_tile_str = ee.List(path_list.map(tile_dict)).join(',')
        # pprint.pprint(wrs2_tile_str.getInfo())
        # input('ENTER')

        # # DEADBEEF - This works but is really slow because of the getInfo
        # logging.debug('  Getting Tcorr collection tile list')
        # wrs2_tile_list = utils.get_info(
        #     tcorr_img_coll.aggregate_array('wrs2_tile'))
        # wrs2_tile_str = tile_set_2_str(wrs2_tile_list)
        # pprint.pprint(wrs2_tile_list)
        # pprint.pprint(wrs2_tile_str)
        # input('ENTER')

        # DEADBEEF - Old approach, tile lists for big areas are too long
        # def unique_properties(coll, property):
        #     return ee.String(ee.List(ee.Dictionary(
        #         coll.aggregate_histogram(property)).keys()).join(','))
        # wrs2_tile_list = ee.String('').cat(unique_properties(
        #     tcorr_img_coll, 'wrs2_tile'))
        # wrs2_tile_list = set([id.split('_')[-2] for id in wrs2_tile_list])


        def unique_properties(coll, property):
            return ee.String(ee.List(ee.Dictionary(
                coll.aggregate_histogram(property)).keys()).join(','))
        landsat_list = ee.String('').cat(unique_properties(
            tcorr_img_coll, 'spacecraft_id'))


        # Cast to float and set properties
        tcorr_img = ee.Image(tcorr_img).rename(['tcorr']).double() \
            .set({
                'system:time_start': utils.millis(export_dt),
                'date_ingested': datetime.datetime.today().strftime('%Y-%m-%d'),
                'date': export_dt.strftime('%Y-%m-%d'),
                'year': int(export_dt.year),
                'month': int(export_dt.month),
                'day': int(export_dt.day),
                'doy': int(export_dt.strftime('%j')),
                'cycle_day': ((export_dt - cycle_base_dt).days % 8) + 1,
                'landsat': landsat_list,
                'model_name': model_name,
                'model_version': ssebop.__version__,
                'tmax_source': tmax_source.upper(),
                'tmax_version': tmax_version.upper(),
                'wrs2_tiles': wrs2_tile_str,
                'wrs2_available': wrs2_tiles_all_str,
            })
        # pprint.pprint(tcorr_img.getInfo()['properties'])
        # input('ENTER')

        logging.debug('  Building export task')
        task = ee.batch.Export.image.toAsset(
            image=ee.Image(tcorr_img),
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
        description='Compute/export daily Tcorr images',
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
        '--cron', default=False, action='store_true',
        help='Cron mode')
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

    # Prompt user to select an INI file if not set at command line
    # if not args.ini:
    #     args.ini = utils.get_ini_path(os.getcwd())

    return args


if __name__ == "__main__":
    args = arg_parse()

    logging.basicConfig(level=args.loglevel, format='%(message)s')
    logging.getLogger('googleapiclient').setLevel(logging.ERROR)

    main(ini_path=args.ini, overwrite_flag=args.overwrite,
         delay_time=args.delay, gee_key_file=args.key, max_ready=args.ready,
         cron_flag=args.cron, reverse_flag=args.reverse)
