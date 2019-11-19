#--------------------------------
# Name:         dt_cleanup_daily_image.py
# Purpose:      Remove earlier versions of daily dT images
#--------------------------------

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
    """Remove earlier versions of daily dT images

    Parameters
    ----------
    ini_path : str
        Input file path.

    """
    logging.info('\nRemove earlier versions of daily dT images')

    ini = utils.read_ini(ini_path)

    model_name = 'SSEBOP'
    # model_name = ini['INPUTS']['et_model'].upper()

    start_dt = datetime.datetime.strptime(
        ini['INPUTS']['start_date'], '%Y-%m-%d')
    end_dt = datetime.datetime.strptime(
        ini['INPUTS']['end_date'], '%Y-%m-%d')
    logging.debug('Start Date: {}'.format(start_dt.strftime('%Y-%m-%d')))
    logging.debug('End Date:   {}\n'.format(end_dt.strftime('%Y-%m-%d')))

    try:
        dt_source = str(ini[model_name]['dt_source'])
        logging.debug('\ndt_source:\n  {}'.format(dt_source))
    except KeyError:
        logging.error('  dt_source: must be set in INI')
        sys.exit()
    if dt_source.upper() not in ['CIMIS', 'DAYMET', 'GRIDMET']:
        raise ValueError('dt_source must be CIMIS, DAYMET, or GRIDMET')

    # Output dT daily image collection
    dt_daily_coll_id = '{}/{}_daily'.format(
        ini['EXPORT']['export_coll'], ini[model_name]['dt_source'].lower())
    logging.debug('  {}'.format(dt_daily_coll_id))


    if os.name == 'posix':
        shell_flag = False
    else:
        shell_flag = True


    logging.info('\nInitializing Earth Engine')
    ee.Initialize(use_cloud_api=False)
    ee.Number(1).getInfo()


    # Get list of existing images/files
    logging.debug('\nGetting GEE asset list')
    asset_list = utils.get_ee_assets(dt_daily_coll_id, shell_flag=shell_flag)
    logging.debug('Displaying first 10 images in collection')
    logging.debug(asset_list[:10])


    # Filter asset list by INI start_date and end_date
    logging.debug('\nFiltering by INI start_date and end_date')
    asset_re = re.compile('[\w_]+/(\d{8})_\d{8}')
    asset_list = [
        asset_id for asset_id in asset_list
        if (start_dt <= datetime.datetime.strptime(asset_re.findall(asset_id)[0], '%Y%m%d') and
            datetime.datetime.strptime(asset_re.findall(asset_id)[0], '%Y%m%d') <= end_dt)]
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
        description='Remove earlier versions of daily dT images',
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
