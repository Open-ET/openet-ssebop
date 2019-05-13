#--------------------------------
# Name:         tcorr_rt_test.py
# Purpose:      Test for differences in Tcorr from real-time and Collection 1
#--------------------------------

import argparse
from builtins import input
import datetime
import logging
import os
import pprint
import sys

import ee
import pandas as pd

import openet.ssebop as ssebop
import utils
# from . import utils


def main(ini_path=None, overwrite_flag=False, delay=0, key=None):
    """Test for differences in Tcorr from real-time and Collection 1

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
    logging.info('\nTest Real Time Tcorr')

    # Hardcoding for now...
    tcorr_stats_path = r'C:\Users\mortonc\Google Drive\SSEBop\tcorr_realtime\tcorr_stats.csv'
    # tcorr_stats_path = r'C:\Projects\openet-ssebop-beta\tcorr\tcorr_stats.csv'

    ini = utils.read_ini(ini_path)

    model_name = 'SSEBOP'
    # model_name = ini['INPUTS']['et_model'].upper()

    logging.info('\nInitializing Earth Engine')
    if key:
        logging.info('  Using service account key file: {}'.format(key))
        # The "EE_ACCOUNT" parameter is not used if the key file is valid
        ee.Initialize(ee.ServiceAccountCredentials('deadbeef', key_file=key))
    else:
        ee.Initialize()

    # Get a Tmax image to set the Tcorr values to
    logging.debug('\nTmax properties')
    tmax_name = ini[model_name]['tmax_source']
    tmax_source = tmax_name.split('_', 1)[0]
    tmax_version = tmax_name.split('_', 1)[1]
    tmax_coll_id = 'projects/usgs-ssebop/tmax/{}'.format(tmax_name.lower())
    tmax_coll = ee.ImageCollection(tmax_coll_id)
    tmax_mask = ee.Image(tmax_coll.first()).select([0]).multiply(0)
    logging.debug('  Collection: {}'.format(tmax_coll_id))
    logging.debug('  Source:  {}'.format(tmax_source))
    logging.debug('  Version: {}'.format(tmax_version))

    if not os.path.isfile(tcorr_stats_path):
        logging.debug('\nBuilding new Tcorr dataframe')
        tcorr_df = pd.DataFrame(
            columns=['IMAGE_ID', 'IMAGE_DATE', 'COLLECTION', 'TCORR', 'COUNT', 'EXPORT_DATE'])
        c1_id_set = set()
        rt_id_set = set()
    else:
        logging.debug('\nLoading exist Tcorr dataframe')
        logging.debug('  {}'.format(tcorr_stats_path))
        tcorr_df = pd.read_csv(tcorr_stats_path)
        c1_id_set = set(tcorr_df.loc[tcorr_df['COLLECTION'] == 'C1', 'IMAGE_ID'])
        rt_id_set = set(tcorr_df.loc[tcorr_df['COLLECTION'] == 'RT', 'IMAGE_ID'])
        logging.debug(tcorr_df.head())


    # CGM - This seems like a silly way of getting the date as a datetime
    iter_end_dt = datetime.date.today().strftime('%Y-%m-%d')
    iter_end_dt = datetime.datetime.strptime(iter_end_dt, '%Y-%m-%d')
    iter_end_dt = iter_end_dt + datetime.timedelta(days=-1)
    # iter_end_dt = datetime.datetime.today() + datetime.timedelta(days=-1)
    iter_start_dt = iter_end_dt + datetime.timedelta(days=-64)
    logging.debug('Start Date: {}'.format(iter_start_dt.strftime('%Y-%m-%d')))
    logging.debug('End Date:   {}\n'.format(iter_end_dt.strftime('%Y-%m-%d')))


    # Iterate over date ranges
    for iter_dt in reversed(list(utils.date_range(iter_start_dt, iter_end_dt))):
        logging.info('Date: {}'.format(iter_dt.strftime('%Y-%m-%d')))


        # Build and merge the Real-Time Landsat collections
        l8_rt_coll = ee.ImageCollection('LANDSAT/LC08/C01/T1_RT_TOA') \
            .filterDate(iter_dt, iter_dt + datetime.timedelta(days=1)) \
            .filterBounds(tmax_mask.geometry()) \
            .filterMetadata('CLOUD_COVER_LAND', 'less_than',
                            float(ini['INPUTS']['cloud_cover'])) \
            .filterMetadata('DATA_TYPE', 'equals', 'L1TP')
        l7_rt_coll = ee.ImageCollection('LANDSAT/LE07/C01/T1_RT_TOA') \
            .filterDate(iter_dt, iter_dt + datetime.timedelta(days=1)) \
            .filterBounds(tmax_mask.geometry()) \
            .filterMetadata('CLOUD_COVER_LAND', 'less_than',
                            float(ini['INPUTS']['cloud_cover'])) \
            .filterMetadata('DATA_TYPE', 'equals', 'L1TP')
        rt_coll = ee.ImageCollection(l8_rt_coll.merge(l7_rt_coll))


        # Build and merge the final Collection 1 collections
        l8_c1_coll = ee.ImageCollection('LANDSAT/LC08/C01/T1_TOA') \
            .filterDate(iter_dt, iter_dt + datetime.timedelta(days=1)) \
            .filterBounds(tmax_mask.geometry()) \
            .filterMetadata('CLOUD_COVER_LAND', 'less_than',
                            float(ini['INPUTS']['cloud_cover'])) \
            .filterMetadata('DATA_TYPE', 'equals', 'L1TP')
        l7_c1_coll = ee.ImageCollection('LANDSAT/LE07/C01/T1_TOA') \
            .filterDate(iter_dt, iter_dt + datetime.timedelta(days=1)) \
            .filterBounds(tmax_mask.geometry()) \
            .filterMetadata('CLOUD_COVER_LAND', 'less_than',
                            float(ini['INPUTS']['cloud_cover'])) \
            .filterMetadata('DATA_TYPE', 'equals', 'L1TP')
        c1_coll = ee.ImageCollection(l8_c1_coll.merge(l7_c1_coll))


        # Get the Image IDs that haven't been processed
        logging.info('  Getting Missing Asset IDs')
        rt_id_list = [
            id for id in rt_coll.aggregate_array('system:id').getInfo()
            if id.split('/')[-1] not in rt_id_set]
        c1_id_list = [
            id for id in c1_coll.aggregate_array('system:id').getInfo()
            if id.split('/')[-1] not in c1_id_set]


        if not rt_id_list and not c1_id_list:
            logging.info('  No new images, skipping date')
            continue


        logging.info('  Real-time')
        for asset_id in rt_id_list:
            logging.info('  {}'.format(asset_id))
            t_stats = ssebop.Image.from_landsat_c1_toa(
                    ee.Image(asset_id),
                    tdiff_threshold=float(ini[model_name]['tdiff_threshold']))\
                .tcorr_stats\
                .getInfo()
            if t_stats['tcorr_p5'] is None:
                t_stats['tcorr_p5'] = ''
            image_id = asset_id.split('/')[-1]
            tcorr_df = tcorr_df.append(
                {'IMAGE_ID': image_id,
                 'IMAGE_DATE': datetime.datetime.strptime(image_id.split('_')[2], '%Y%m%d')
                     .strftime('%Y-%m-%d'),
                 'COLLECTION': 'RT',
                 'TCORR': t_stats['tcorr_p5'],
                 'COUNT': t_stats['tcorr_count'],
                 'EXPORT_DATE': datetime.datetime.today().strftime('%Y-%m-%d')},
                ignore_index=True)


        logging.info('  Collection 1')
        for asset_id in c1_id_list:
            logging.info('  {}'.format(asset_id))
            t_stats = ssebop.Image.from_landsat_c1_toa(
                    ee.Image(asset_id),
                    tdiff_threshold=float(ini[model_name]['tdiff_threshold']))\
                .tcorr_stats\
                .getInfo()
            if t_stats['tcorr_p5'] is None:
                t_stats['tcorr_p5'] = ''
            image_id = asset_id.split('/')[-1]
            tcorr_df = tcorr_df.append(
                {'IMAGE_ID': asset_id.split('/')[-1],
                 'IMAGE_DATE': datetime.datetime.strptime(image_id.split('_')[2], '%Y%m%d')
                     .strftime('%Y-%m-%d'),
                 'COLLECTION': 'C1',
                 'TCORR': t_stats['tcorr_p5'],
                 'COUNT': t_stats['tcorr_count'],
                 'EXPORT_DATE': datetime.datetime.today().strftime('%Y-%m-%d')},
                ignore_index=True)


        # Export the current dataframe to disk
        logging.info('  Writing CSV')
        tcorr_df.sort_values(by=['IMAGE_ID', 'COLLECTION'], inplace=True)
        # tcorr_df.sort_values(by=['COLLECTION', 'IMAGE_ID'], inplace=True)
        tcorr_df.to_csv(tcorr_stats_path, index=None)


def arg_parse():
    """"""
    parser = argparse.ArgumentParser(
        description='Tcorr real time test',
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
