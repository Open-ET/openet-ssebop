#--------------------------------
# Name:         tcorr_export_monthly_image.py
# Purpose:      Compute/Export monthly Tcorr images
#--------------------------------

import argparse
from builtins import input
import datetime
import logging
import math
import os
import pprint
import sys

import ee

import openet.ssebop as ssebop
import utils


def main(ini_path=None, overwrite_flag=False, delay=0,
         key=None):
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

    # Output Tcorr monthly image collection
    tcorr_monthly_coll_id = '{}/{}_monthly'.format(
        ini['EXPORT']['export_path'], ini['SSEBOP']['tmax_source'].lower())

    # Get the Tcorr daily image collection properties
    logging.debug('\nTcorr properties')
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

    # Get current asset list
    if ini['EXPORT']['export_dest'].upper() == 'ASSET':
        logging.debug('\nGetting asset list')
        # DEADBEEF - monthly is hardcoded in the asset_id for now
        asset_list = utils.get_ee_assets('{}/{}_monthly'.format(
            ini['EXPORT']['export_path'], ini['SSEBOP']['tmax_source'].lower()))
    else:
        raise ValueError('invalid export destination: {}'.format(
            ini['EXPORT']['export_dest']))

    # Get current running tasks
    tasks = utils.get_ee_tasks()
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        logging.debug('  Tasks: {}\n'.format(len(tasks)))
        # input('ENTER')

    # iter_start_dt = datetime.datetime.strptime(
    #     ini['INPUTS']['start_date'], '%Y-%m-%d')
    # iter_end_dt = datetime.datetime.strptime(
    #     ini['INPUTS']['end_date'], '%Y-%m-%d')
    #
    # # Monthly date ranges
    # iter_dates = [
    #     datetime.datetime(y, m, 1)
    #     for y in range(iter_start_dt.year, iter_end_dt.year + 2)
    #     for m in range(1, 13)
    #     if datetime.datetime(y, m, 1) >= iter_start_dt]
    # iter_dates = [
    #     [dt, (iter_dates[i + 1] - datetime.timedelta(days=1))]
    #     for i, dt in enumerate(iter_dates[:-1])
    #     if (iter_dates[i + 1] - datetime.timedelta(days=1)) <= iter_end_dt]

    month_list = sorted(list(utils.parse_int_set(ini['TCORR']['months'])))
    year_list = sorted(list(utils.parse_int_set(ini['TCORR']['years'])))
    if not month_list:
        raise ValueError('TCORR "months" parameter must be set in the INI')
        # month_list = list(range(1, 12))
    if not year_list:
        raise ValueError('TCORR "years" parameter must be set in the INI')
        # month_list = list(range(1984, 2018))

    # Iterate over date ranges
    for month in month_list:
        logging.info('\nMonth: {}'.format(month))
        # iter_start_date = iter_start_dt.strftime('%Y-%m-%d')
        # iter_end_date = iter_end_dt.strftime('%Y-%m-%d')
        # iter_next_date = (iter_end_dt + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        # logging.info('\nStart Date: {}'.format(iter_start_date))
        # logging.info('End Date:   {}'.format(iter_end_date))

        # Output name
        export_id = ini['EXPORT']['export_id_fmt'] \
            .format(
                product=ini['SSEBOP']['tmax_source'].lower(),
                date='month{:02d}'.format(month),
                export=ini['EXPORT']['export_dest'].lower())
        logging.debug('  Export ID: {0}'.format(export_id))

        if ini['EXPORT']['export_dest'] == 'ASSET':
            # DEADBEEF - monthly is hardcoded in the asset_id for now
            asset_id = '{}/{}'.format(
                tcorr_monthly_coll_id, '{:02d}'.format(month))
            logging.debug('  Asset ID: {}'.format(asset_id))

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

        tcorr_img_coll = ee.ImageCollection(tcorr_daily_coll_id)\
            .filterMetadata('MONTH', 'equals', month)\
            .filter(ee.Filter.inList('YEAR', year_list))
        # pprint.pprint(tcorr_img_coll.aggregate_histogram('system:index').getInfo())
        # pprint.pprint(ee.Image(tcorr_img_coll.first()).getInfo())
        # input('ENTER')

        #
        count_img = tcorr_img_coll.select(['tcorr']).count()
        count_mask = count_img.gte(int(ini['TCORR']['min_scene_count']))
        tcorr_img = tcorr_img_coll.select(['tcorr']).median()\
            .where(count_mask.Not(), float(ini['TCORR']['tcorr_default']))
        index_img = count_img.multiply(0).add(1) \
            .where(count_mask.Not(), 2)

        # Mask pixels with counts below threshold
        output_img = ee.Image([tcorr_img, count_img, index_img])\
            .rename(['tcorr', 'count', 'index'])\
            .setMulti({
                # 'system:time_start': utils.millis(iter_start_dt),
                'SSEBOP_VERSION': ssebop.__version__,
                'TMAX_SOURCE': tmax_source.upper(),
                'TMAX_VERSION': tmax_version.upper(),
                'EXPORT_DATE': datetime.datetime.today().strftime('%Y-%m-%d'),
                'MONTH': int(month),
                'YEARS': ','.join(map(str, year_list)),
            })
        # pprint.pprint(tcorr_img.getInfo())
        # input('ENTER')

        # Mask pixels with counts below threshold
        output_img

        # Build export tasks
        if ini['EXPORT']['export_dest'] == 'ASSET':
            logging.debug('    Building export task')
            task = ee.batch.Export.image.toAsset(
                image=ee.Image(output_img),
                description=export_id,
                assetId=asset_id,
                crs=tcorr_crs,
                crsTransform='[' + ','.join(list(map(str, tcorr_geo))) + ']',
                dimensions='{0}x{1}'.format(*tcorr_shape),
            )
            logging.debug('    Starting export task')
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
