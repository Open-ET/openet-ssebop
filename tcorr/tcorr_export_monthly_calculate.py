#--------------------------------
# Name:         tcorr_export_monthly_image.py
# Purpose:      Compute/Export monthly Tcorr images
#--------------------------------

import argparse
from builtins import input
import datetime
import logging
import os
import pprint
import sys

import ee

import openet.ssebop as ssebop
import utils


def main(ini_path=None, overwrite_flag=False, delay=0, key=None):
    """Compute monthly Tcorr images

    Parameters
    ----------
    ini_path : str
        Input file path.
    overwrite_flag : bool, optional
        If True, overwrite existing files (the default is False).
    delay : float, optional
        Delay time between each export task (the default is 0).
    key : str, optional
        File path to an Earth Engine json key file (the default is None).

    """
    logging.info('\nCompute monthly Tcorr images')

    ini = utils.read_ini(ini_path)

    if (ini['SSEBOP']['tmax_source'].upper() == 'CIMIS' and
            ini['INPUTS']['end_date'] < '2003-10-01'):
        logging.error(
            '\nCIMIS is not currently available before 2003-10-01, exiting\n')
        sys.exit()
    elif (ini['SSEBOP']['tmax_source'].upper() == 'DAYMET' and
            ini['INPUTS']['end_date'] > '2017-12-31'):
        logging.warning(
            '\nDAYMET is not currently available past 2017-12-31, '
            'using median Tmax values\n')
        # sys.exit()
    # elif (ini['SSEBOP']['tmax_source'].upper() == 'TOPOWX' and
    #         ini['INPUTS']['end_date'] > '2017-12-31'):
    #     logging.warning(
    #         '\nDAYMET is not currently available past 2017-12-31, '
    #         'using median Tmax values\n')
    #     # sys.exit()

    logging.info('\nInitializing Earth Engine')
    if key:
        logging.info('  Using service account key file: {}'.format(key))
        # The "EE_ACCOUNT" parameter is not used if the key file is valid
        ee.Initialize(ee.ServiceAccountCredentials('deadbeef', key_file=key))
    else:
        ee.Initialize()

    logging.debug('\nTmax properties')
    tmax_name = ini['SSEBOP']['tmax_source']
    tmax_source = tmax_name.split('_', 1)[0]
    tmax_version = tmax_name.split('_', 1)[1]
    tmax_coll_id = 'projects/usgs-ssebop/tmax/{}'.format(tmax_name.lower())
    tmax_coll = ee.ImageCollection(tmax_coll_id)
    tmax_mask = ee.Image(tmax_coll.first()).select([0]).multiply(0)
    logging.debug('  Collection: {}'.format(tmax_coll_id))
    logging.debug('  Source: {}'.format(tmax_source))
    logging.debug('  Version: {}'.format(tmax_version))

    # Get the Tcorr daily image collection properties
    logging.debug('\nTcorr Image properties')
    tcorr_daily_coll_id = '{}/{}_daily'.format(
        ini['EXPORT']['export_path'], ini['SSEBOP']['tmax_source'].lower())
    tcorr_img = ee.Image(ee.ImageCollection(tcorr_daily_coll_id).first())
    tcorr_geo = ee.Image(tcorr_img).projection().getInfo()['transform']
    tcorr_crs = ee.Image(tcorr_img).projection().getInfo()['crs']
    tcorr_shape = ee.Image(tcorr_img).getInfo()['bands'][0]['dimensions']
    tcorr_extent = [tcorr_geo[2], tcorr_geo[5] + tcorr_shape[1] * tcorr_geo[4],
                    tcorr_geo[2] + tcorr_shape[0] * tcorr_geo[0], tcorr_geo[5]]
    logging.debug('  Shape: {}'.format(tcorr_shape))
    logging.debug('  Extent: {}'.format(tcorr_extent))
    logging.debug('  Geo: {}'.format(tcorr_geo))
    logging.debug('  CRS: {}'.format(tcorr_crs))

    # Output Tcorr monthly image collection
    tcorr_monthly_coll_id = '{}/{}_monthly_test'.format(
        ini['EXPORT']['export_path'], ini['SSEBOP']['tmax_source'].lower())
    # tcorr_monthly_coll_id = '{}/{}_monthly'.format(
    #     ini['EXPORT']['export_path'], ini['SSEBOP']['tmax_source'].lower())

    # Get current asset list
    if ini['EXPORT']['export_dest'].upper() == 'ASSET':
        logging.debug('\nGetting asset list')
        # DEADBEEF - "monthly" is hardcoded in the asset_id for now
        asset_list = utils.get_ee_assets(tcorr_monthly_coll_id)
    else:
        raise ValueError('invalid export destination: {}'.format(
            ini['EXPORT']['export_dest']))

    # Get current running tasks
    tasks = utils.get_ee_tasks()
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        logging.debug('  Tasks: {}\n'.format(len(tasks)))
    #     input('ENTER')

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
        1:  '2000-01-06',
        2:  '2000-01-07',
        3:  '2000-01-08',
        4:  '2000-01-09',
        5:  '2000-01-10',
        6:  '2000-01-11',
        7:  '2000-01-12',
        8:  '2000-01-13',
        # 9:  '2000-01-14',
        # 10: '2000-01-15',
        # 11: '2000-01-16',
        # 12: '2000-01-01',
        # 13: '2000-01-02',
        # 14: '2000-01-03',
        # 15: '2000-01-04',
        # 16: '2000-01-05',
    }

    # Key is cycle day, values are list of paths
    # First list is Landsat 8 paths, second list is Landsat 7 paths
    cycle_paths = {
        5:  [ 1, 17, 33, 49, 65,  81,  97, 106, 122, 138, 154, 170, 186, 202, 218] +
            [ 9, 25, 41, 57, 73,  89,  98, 114, 130, 146, 162, 178, 194, 210, 226],
        # 12: [ 2, 18, 34, 50, 66,  82, 107, 123, 139, 155, 171, 187, 203, 219] +
        #     [10, 26, 42, 58, 74,  99, 115, 131, 147, 163, 179, 195, 211, 227],
        3:  [ 3, 19, 35, 51, 67,  83, 108, 124, 140, 156, 172, 188, 204, 220] +
            [11, 27, 43, 59, 75, 100, 116, 132, 148, 164, 180, 196, 212, 228],
        # 10: [ 4, 20, 36, 52, 68,  84, 109, 125, 141, 157, 171, 189, 205, 221] +
        #     [12, 28, 44, 60, 76, 101, 117, 133, 149, 165, 181, 197, 213, 229],
        1:  [ 5, 21, 37, 53, 69,  85, 110, 126, 142, 158, 174, 190, 206, 222] +
            [13, 29, 45, 61, 77, 102, 118, 134, 150, 166, 182, 198, 214, 230],
        8:  [ 6, 22, 38, 54, 70,  86, 111, 127, 143, 159, 175, 191, 207, 223] +
            [14, 30, 46, 62, 78, 103, 119, 135, 151, 167, 183, 199, 215, 231],
        # 15: [ 7, 23, 39, 55, 71,  87, 112, 128, 144, 160, 176, 192, 208, 224] +
        #     [15, 31, 47, 63, 79, 104, 120, 136, 152, 168, 184, 200, 216, 232],
        6:  [ 8, 24, 40, 56, 72,  88, 113, 129, 145, 161, 177, 193, 209, 225] +
            [16, 32, 48, 64, 80, 105, 121, 137, 153, 169, 185, 201, 217, 233],
        # 13: [ 9, 25, 41, 57, 73,  89,  98, 114, 130, 146, 162, 178, 194, 210, 226] +
        #     [ 1, 17, 33, 49, 65,  81,  90, 106, 122, 138, 154, 170, 186, 202, 218],
        4:  [10, 26, 42, 58, 74,  90,  99, 115, 131, 147, 163, 179, 195, 211, 227] +
            [ 2, 18, 34, 50, 66,  82,  91, 107, 123, 139, 155, 171, 187, 203, 219],
        # 11: [11, 27, 43, 59, 75,  91, 100, 116, 132, 148, 164, 180, 196, 212, 228] +
        #     [ 3, 19, 35, 51, 67,  83,  92, 108, 124, 140, 156, 172, 188, 204, 220],
        2:  [12, 28, 44, 60, 76,  92, 101, 117, 133, 149, 165, 181, 197, 213, 229] +
            [ 4, 20, 36, 52, 68,  84,  93, 109, 125, 141, 157, 173, 189, 205, 221],
        # 9:  [13, 29, 45, 61, 77,  93, 102, 118, 134, 150, 166, 182, 198, 214, 230] +
        #     [ 5, 21, 37, 53, 69,  85,  94, 110, 126, 142, 158, 174, 190, 206, 222],
        # 16: [14, 30, 46, 62, 78,  94, 103, 119, 135, 151, 167, 183, 199, 215, 231] +
        #     [ 6, 22, 38, 54, 70,  86,  95, 111, 127, 143, 159, 175, 191, 207, 223],
        7:  [15, 31, 47, 63, 79,  95, 104, 120, 136, 152, 168, 184, 200, 216, 232] +
            [ 7, 23, 39, 55, 71,  87,  96, 112, 128, 144, 160 ,176, 192, 208, 224],
        # 14: [16, 32, 48, 64, 80,  96, 105, 121, 137, 153, 169, 185, 201, 217, 233] +
        #     [ 8, 24, 40, 56, 72,  88,  97, 113, 129, 145, 161, 177, 193, 209, 225],
    }

    # Iterate over date ranges
    for month in month_list:
        logging.info('\nMonth: {}'.format(month))

        for cycle_day, ref_date in cycle_dates.items():
            logging.info('Cycle Day: {}'.format(cycle_day))
            # # DEADBEEF
            # if cycle_day not in [2]:
            #     continue

            ref_dt = datetime.datetime.strptime(ref_date, '%Y-%m-%d')
            logging.debug('  Reference Date: {}'.format(ref_date))

            date_list = sorted(list(utils.date_range(
                datetime.datetime(year_list[0], 1, 1),
                datetime.datetime(year_list[-1], 12, 31))))
            date_list = [
                d.strftime('%Y-%m-%d') for d in date_list
                if ((abs(d - ref_dt).days % 8 == 0) and
                    (int(d.month) == month) and
                    (int(d.year) in year_list))]
            logging.debug('  Dates: {}'.format(', '.join(date_list)))

            # DEADBEEF - Added "_test" to export ID
            export_id = ini['EXPORT']['export_id_fmt'] \
                .format(
                    product=ini['SSEBOP']['tmax_source'].lower(),
                    date='month{:02d}_cycle{:02d}'.format(month, cycle_day),
                    export=ini['EXPORT']['export_dest'].lower() + '_test',
            )
            logging.info('  Export ID: {}'.format(export_id))

            if ini['EXPORT']['export_dest'] == 'ASSET':
                # DEADBEEF - "monthly" is hardcoded in the asset_id for now
                asset_id = '{}/{}'.format(
                    tcorr_monthly_coll_id,
                    '{:02d}_cycle{:02d}'.format(month, cycle_day))
                #     tcorr_monthly_coll_id, '{:02d}'.format(month))
                logging.info('  Asset ID: {}'.format(asset_id))

            if overwrite_flag:
                if export_id in tasks.keys():
                    logging.debug('  Task already submitted, cancelling')
                    ee.data.cancelTask(tasks[export_id])
                # This is intentionally not an "elif" so that a task can be
                # cancelled and an existing image/file/asset can be removed
                if (ini['EXPORT']['export_dest'].upper() == 'ASSET' and
                        asset_id in asset_list):
                    logging.debug('  Asset already exists, removing')
                    ee.data.deleteAsset(asset_id)
            else:
                if export_id in tasks.keys():
                    logging.debug('  Task already submitted, exiting')
                    continue
                elif (ini['EXPORT']['export_dest'].upper() == 'ASSET' and
                        asset_id in asset_list):
                    logging.debug('  Asset already exists, skipping')
                    continue

            wrs2_coll = ee.FeatureCollection(
                    'projects/usgs-ssebop/wrs2_descending_custom') \
                .filterBounds(tmax_mask.geometry()) \
                .filter(ee.Filter.inList('PATH', cycle_paths[cycle_day]))
            #     .filter(ee.Filter.inList('PATH', [44]))
            #     .filter(ee.Filter.inList('ROW', [32, 33, 34]))
            # pprint.pprint(wrs2_coll.getInfo())
            # input('ENTER')

            def wrs2_tcorr(ftr):
                # Build & merge the Landsat collections for the target path/row
                # Time filters are to remove bad (L5) and pre-op (L8) images
                path = ee.Number(ee.Feature(ftr).get('PATH'))
                row = ee.Number(ee.Feature(ftr).get('ROW'))

                l8_coll = ee.ImageCollection('LANDSAT/LC08/C01/T1_RT_TOA') \
                    .filterMetadata('WRS_PATH', 'equals', path) \
                    .filterMetadata('WRS_ROW', 'equals', row) \
                    .filterMetadata('CLOUD_COVER_LAND', 'less_than',
                                    float(ini['INPUTS']['cloud_cover'])) \
                    .filterMetadata('DATA_TYPE', 'equals', 'L1TP') \
                    .filter(ee.Filter.inList('DATE_ACQUIRED', date_list)) \
                    .filter(ee.Filter.gt('system:time_start',
                                         ee.Date('2013-03-24').millis()))
                l7_coll = ee.ImageCollection('LANDSAT/LE07/C01/T1_RT_TOA') \
                    .filterMetadata('WRS_PATH', 'equals', path) \
                    .filterMetadata('WRS_ROW', 'equals', row) \
                    .filterMetadata('CLOUD_COVER_LAND', 'less_than',
                                    float(ini['INPUTS']['cloud_cover'])) \
                    .filterMetadata('DATA_TYPE', 'equals', 'L1TP') \
                    .filter(ee.Filter.inList('DATE_ACQUIRED', date_list))
                l5_coll = ee.ImageCollection('LANDSAT/LT05/C01/T1_TOA') \
                    .filterMetadata('WRS_PATH', 'equals', path) \
                    .filterMetadata('WRS_ROW', 'equals', row) \
                    .filterMetadata('CLOUD_COVER_LAND', 'less_than',
                                    float(ini['INPUTS']['cloud_cover'])) \
                    .filterMetadata('DATA_TYPE', 'equals', 'L1TP')  \
                    .filter(ee.Filter.inList('DATE_ACQUIRED', date_list)) \
                    .filter(ee.Filter.lt('system:time_start',
                                         ee.Date('2011-12-31').millis()))
                l4_coll = ee.ImageCollection('LANDSAT/LT04/C01/T1_TOA') \
                    .filterMetadata('WRS_PATH', 'equals', path) \
                    .filterMetadata('WRS_ROW', 'equals', row) \
                    .filterMetadata('CLOUD_COVER_LAND', 'less_than',
                                    float(ini['INPUTS']['cloud_cover'])) \
                    .filterMetadata('DATA_TYPE', 'equals', 'L1TP') \
                    .filter(ee.Filter.inList('DATE_ACQUIRED', date_list))
                landsat_coll = ee.ImageCollection(
                    l8_coll.merge(l7_coll).merge(l5_coll))
                # landsat_coll = ee.ImageCollection(
                #     l8_coll.merge(l7_coll).merge(l5_coll).merge(l4_coll))

                # pprint.pprint(landsat_coll.aggregate_histogram('system:index') \
                #     .getInfo())
                # pprint.pprint(ee.Image(landsat_coll.first()).getInfo())
                # input('ENTER')

                def tcorr_img_func(image):
                    t_stats = ssebop.Image.from_landsat_c1_toa(
                            ee.Image(image),
                            tdiff_threshold=float(ini['SSEBOP']['tdiff_threshold'])) \
                        .tcorr_stats
                    t_stats = ee.Dictionary(t_stats) \
                        .combine({'tcorr_p5': 0, 'tcorr_count': 0},
                                 overwrite=False)
                    tcorr = ee.Number(t_stats.get('tcorr_p5'))
                    count = ee.Number(t_stats.get('tcorr_count'))

                    return tmax_mask.add(ee.Image.constant(tcorr)) \
                        .rename(['tcorr']) \
                        .set({
                            'system:time_start': image.get('system:time_start'),
                            'tcorr': tcorr,
                            'count': count
                        })

                # pprint.pprint(ee.Image(landsat_coll.first()).getInfo())
                # input('ENTER')
                # temp = tcorr_img_func(ee.Image(landsat_coll.first()))
                # pprint.pprint(temp.getInfo())
                # input('ENTER')

                reducer = ee.Reducer.median() \
                    .combine(ee.Reducer.count(), sharedInputs=True)

                # Compute median monthly value for all images in the WRS2 tile
                wrs2_tcorr_coll = ee.ImageCollection(
                        landsat_coll.map(tcorr_img_func)) \
                    .filterMetadata('count', 'not_less_than',
                                    float(ini['TCORR']['min_pixel_count']))

                wrs2_tcorr_img = wrs2_tcorr_coll.reduce(reducer) \
                    .rename(['tcorr', 'count'])

                # Compute stats from the properties also
                wrs2_tcorr_stats = ee.Dictionary(ee.List(
                    wrs2_tcorr_coll.aggregate_array('tcorr')).reduce(reducer))
                wrs2_tcorr_stats = wrs2_tcorr_stats \
                    .combine({'median': 0, 'count': 0}, overwrite=False)

                return wrs2_tcorr_img \
                    .clip(ftr.geometry()) \
                    .set({
                        'WRS2_TILE': path.format('%03d').cat(row.format('%03d')),
                        # 'WRS2_TILE': ftr.get('WRS2_TILE'),
                        'TCORR': ee.Number(wrs2_tcorr_stats.get('median')),
                        'COUNT': ee.Number(wrs2_tcorr_stats.get('count')),
                        'INDEX': 1,
                    })

            # # DEADBEEF
            # for row in [35]:
            #     print('\nPATH: 36  ROW: {}'.format(row))
            #     wrs2_test_coll = wrs2_coll \
            #         .filterMetadata('ROW', 'equals', row) \
            #         .filterMetadata('PATH', 'equals', 36)
            #     output_img = ee.Image(wrs2_tcorr(ee.Feature(wrs2_test_coll.first())))
            #     pprint.pprint(output_img.getInfo())
            #     input('ENTER')

            # Combine WRS2 Tcorr monthly images to a single monthly image
            output_img = ee.ImageCollection(wrs2_coll.map(wrs2_tcorr)) \
                .filterMetadata('COUNT', 'not_less_than',
                                float(ini['TCORR']['min_scene_count'])) \
                .mean() \
                .rename(['tcorr', 'count'])
            # pprint.pprint(output_img.getInfo())
            # input('ENTER')

            #     .updateMask(0) \
            output_img = ee.Image([
                    tmax_mask.add(output_img.select(['tcorr'])).double(),
                    tmax_mask.add(output_img.select(['count'])).min(250).uint8()]) \
                .rename(['tcorr', 'count']) \
                .set({
                    # 'system:time_start': utils.millis(iter_start_dt),
                    'SSEBOP_VERSION': ssebop.__version__,
                    'TMAX_SOURCE': tmax_source.upper(),
                    'TMAX_VERSION': tmax_version.upper(),
                    'EXPORT_DATE': datetime.datetime.today().strftime('%Y-%m-%d'),
                    'MONTH': int(month),
                    'YEARS': ','.join(map(str, year_list)),
                    'CYCLE_DAY': int(cycle_day),
                })
            # pprint.pprint(output_img.getInfo())
            # input('ENTER')

            # Build export tasks
            if ini['EXPORT']['export_dest'] == 'ASSET':
                logging.debug('  Building export task')
                task = ee.batch.Export.image.toAsset(
                    image=ee.Image(output_img),
                    description=export_id,
                    assetId=asset_id,
                    crs=tcorr_crs,
                    crsTransform='[' + ','.join(list(map(str, tcorr_geo))) + ']',
                    dimensions='{0}x{1}'.format(*tcorr_shape),
                )
                logging.debug('  Starting export task')
                utils.ee_task_start(task)

            # Pause before starting next task
            utils.delay_task(delay)
            logging.debug('')


def arg_parse():
    """"""
    parser = argparse.ArgumentParser(
        description='Compute/export monthly Tcorr images',
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
        '-o', '--overwrite', default=False, action='store_true',
        help='Force overwrite of existing files')
    parser.add_argument(
        '-d', '--debug', default=logging.INFO, const=logging.DEBUG,
        help='Debug level logging', action='store_const', dest='loglevel')
    args = parser.parse_args()

    # Prompt user to select an INI file if not set at command line
    if not args.ini:
        args.ini = utils.get_ini_path(os.getcwd())
    return args


if __name__ == "__main__":
    args = arg_parse()

    logging.basicConfig(level=args.loglevel, format='%(message)s')
    logging.info('\n{0}'.format('#' * 80))
    logging.info('{0:<20s} {1}'.format(
        'Run Time Stamp:', datetime.datetime.now().isoformat(' ')))
    logging.info('{0:<20s} {1}'.format('Current Directory:', os.getcwd()))
    logging.info('{0:<20s} {1}'.format(
        'Script:', os.path.basename(sys.argv[0])))

    main(ini_path=args.ini, overwrite_flag=args.overwrite, delay=args.delay,
         key=args.key)
