import argparse
from builtins import input
from collections import defaultdict
import datetime
import logging
import os
import pprint
import re
import sys

import ee

import utils
# from . import utils


def main(ini_path=None):
    """Remove earlier versions of daily tcorr images

    Parameters
    ----------
    ini_path : str
        Input file path.

    """
    logging.info('\nRemove earlier versions of daily tcorr images')

    ini = utils.read_ini(ini_path)

    model_name = 'SSEBOP'
    # model_name = ini['INPUTS']['et_model'].upper()

    start_dt = datetime.datetime.strptime(
        ini['INPUTS']['start_date'], '%Y-%m-%d')
    end_dt = datetime.datetime.strptime(
        ini['INPUTS']['end_date'], '%Y-%m-%d')
    logging.debug('Start Date: {}'.format(start_dt.strftime('%Y-%m-%d')))
    logging.debug('End Date:   {}\n'.format(end_dt.strftime('%Y-%m-%d')))

    tcorr_source = 'IMAGE'

    try:
        tmax_source = str(ini[model_name]['tmax_source']).upper()
        logging.debug('\ntmax_source:\n  {}'.format(tmax_source))
    except KeyError:
        logging.error('  tmax_source: must be set in INI')
        sys.exit()

    # This check is limited to TOPOWX_MEDIAN_V0 because Tcorr images have only
    #   been built for that dataset
    if tmax_source.upper() not in ['TOPOWX_MEDIAN_V0']:
        raise ValueError('tmax_source must be TOPOWX')

    if (tmax_source.upper() == 'CIMIS' and
            ini['INPUTS']['end_date'] < '2003-10-01'):
        logging.error(
            '\nCIMIS is not currently available before 2003-10-01, exiting\n')
        sys.exit()
    elif (tmax_source.upper() == 'DAYMET' and
            ini['INPUTS']['end_date'] > '2017-12-31'):
        logging.warning(
            '\nDAYMET is not currently available past 2017-12-31, '
            'using median Tmax values\n')

    # Output tcorr daily image collection
    tcorr_daily_coll_id = '{}/{}_daily'.format(
        ini['EXPORT']['export_coll'], tmax_source.lower())
    logging.debug('  {}'.format(tcorr_daily_coll_id))


    if os.name == 'posix':
        shell_flag = False
    else:
        shell_flag = True


    logging.info('\nInitializing Earth Engine')
    ee.Initialize()
    utils.get_info(ee.Number(1))


    # Get list of existing images/files
    logging.debug('\nGetting GEE asset list')
    asset_list = utils.get_ee_assets(tcorr_daily_coll_id, shell_flag=shell_flag)
    logging.debug('Displaying first 10 images in collection')
    logging.debug(asset_list[:10])


    # Filter asset list by INI start_date and end_date
    logging.debug('\nFiltering by INI start_date and end_date')
    asset_re = re.compile('(\d{8})_\d{8}')
    asset_list = [
        asset_id for asset_id in asset_list
        if (asset_re.match(asset_id.split('/')[-1]) and
            start_dt <= datetime.datetime.strptime(asset_re.findall(asset_id.split('/')[-1])[0], '%Y%m%d') and
            datetime.datetime.strptime(asset_re.findall(asset_id.split('/')[-1])[0], '%Y%m%d') <= end_dt)]
    if not asset_list:
        logging.info('Empty asset ID list after filter by start/end date, '
                     'exiting')
        return True
    logging.debug('Displaying first 10 images in collection')
    logging.debug(asset_list[:10])


    # Group asset IDs by image date
    asset_id_dict = defaultdict(list)
    for asset_id in asset_list:
        asset_dt = datetime.datetime.strptime(
            asset_id.split('/')[-1].split('_')[0], '%Y%m%d')
        asset_id_dict[asset_dt.strftime('%Y-%m-%d')].append(asset_id)
    # pprint.pprint(asset_id_dict)


    # Remove all but the last image when sorted by export date
    logging.info('\nRemoving assets')
    for key, asset_list in asset_id_dict.items():
        # logging.debug('{}'.format(key))
        if len(asset_list) >=2:
            # logging.debug('\n  Keep: {}'.format(sorted(asset_list)[-1]))
            for asset_id in sorted(asset_list)[:-1]:
                logging.info('  Delete: {}'.format(asset_id))
                try:
                    ee.data.deleteAsset(asset_id)
                except Exception as e:
                    logging.info('  Unhandled exception, skipping')
                    logging.debug(e)
                    continue


def arg_parse():
    """"""
    parser = argparse.ArgumentParser(
        description='Remove earlier versions of daily tcorr images',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-i', '--ini', type=utils.arg_valid_file,
        help='Input file', metavar='FILE')
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
    logging.info('\n{0}'.format('#' * 80))
    logging.info('{0:<20s} {1}'.format(
        'Run Time Stamp:', datetime.datetime.now().isoformat(' ')))
    logging.info('{0:<20s} {1}'.format('Current Directory:', os.getcwd()))
    logging.info('{0:<20s} {1}'.format(
        'Script:', os.path.basename(sys.argv[0])))

    main(ini_path=args.ini)
