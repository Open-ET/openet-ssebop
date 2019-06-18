#--------------------------------
# Name:         dt_export_daily_image.py
# Purpose:      Compute/Export daily dT images
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
# from . import utils


def main(ini_path=None, overwrite_flag=False, delay=0, key=None,
         cron_flag=False, reverse_flag=False):
    """Compute daily dT images

    Parameters
    ----------
    ini_path : str
        Input file path.
    overwrite_flag : bool, optional
        If True, overwrite existing files if the export dates are the same and
        generate new images (but with different export dates) even if the tile
        lists are the same.  The default is False.
    delay : float, optional
        Delay time between each export task (the default is 0).
    key : str, optional
        File path to an Earth Engine json key file (the default is None).
    reverse_flag : bool, optional
        If True, process dates in reverse order.
    """
    logging.info('\nCompute daily dT images')

    ini = utils.read_ini(ini_path)

    model_name = 'SSEBOP'
    # model_name = ini['INPUTS']['et_model'].upper()

    if ini[model_name]['dt_source'].upper() == 'CIMIS':
        daily_coll_id = 'projects/climate-engine/cimis/daily'
    elif ini[model_name]['dt_source'].upper() == 'DAYMET':
        daily_coll_id = 'NASA/ORNL/DAYMET_V3'
    elif ini[model_name]['dt_source'].upper() == 'GRIDMET':
        daily_coll_id = 'IDAHO_EPSCOR/GRIDMET'
    else:
        raise ValueError('dt_source must be CIMIS, DAYMET, or GRIDMET')

    # Check dates
    if (ini[model_name]['dt_source'].upper() == 'CIMIS' and
            ini['INPUTS']['end_date'] < '2003-10-01'):
        logging.error(
            '\nCIMIS is not currently available before 2003-10-01, exiting\n')
        sys.exit()
    elif (ini[model_name]['dt_source'].upper() == 'DAYMET' and
            ini['INPUTS']['end_date'] > '2017-12-31'):
        logging.warning(
            '\nDAYMET is not currently available past 2017-12-31, '
            'using median Tmax values\n')
        # sys.exit()
    # elif (ini[model_name]['tmax_source'].upper() == 'TOPOWX' and
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

    # Output dT daily image collection
    dt_daily_coll_id = '{}/{}_daily'.format(
        ini['EXPORT']['export_coll'], ini[model_name]['dt_source'].lower())


    # Get an input image to set the dT values to
    logging.debug('\nInput properties')
    dt_name = ini[model_name]['dt_source']
    dt_source = dt_name.split('_', 1)[0]
    # dt_version = dt_name.split('_', 1)[1]
    daily_coll = ee.ImageCollection(daily_coll_id)
    dt_mask = ee.Image(daily_coll.first()).select([0]).multiply(0)
    logging.debug('  Collection: {}'.format(daily_coll_id))
    logging.debug('  Source: {}'.format(dt_source))
    # logging.debug('  Version: {}'.format(dt_version))

    logging.debug('\nExport properties')
    export_geo = ee.Image(dt_mask).projection().getInfo()['transform']
    export_crs = ee.Image(dt_mask).projection().getInfo()['crs']
    export_shape = ee.Image(dt_mask).getInfo()['bands'][0]['dimensions']
    export_extent = [
        export_geo[2], export_geo[5] + export_shape[1] * export_geo[4],
        export_geo[2] + export_shape[0] * export_geo[0], export_geo[5]]
    logging.debug('  CRS:    {}'.format(export_crs))
    logging.debug('  Extent: {}'.format(export_extent))
    logging.debug('  Geo:    {}'.format(export_geo))
    logging.debug('  Shape:  {}'.format(export_shape))

    # # Limit export to a user defined study area or geometry?
    # export_geom = ee.Geometry.Rectangle(
    #     [-125, 24, -65, 50], proj='EPSG:4326', geodesic=False)  # CONUS
    # export_geom = ee.Geometry.Rectangle(
    #     [-124, 35, -119, 42], proj='EPSG:4326', geodesic=False)  # California

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

    # Get current asset list
    if ini['EXPORT']['export_dest'].upper() == 'ASSET':
        logging.debug('\nGetting asset list')
        # DEADBEEF - daily is hardcoded in the asset_id for now
        asset_list = utils.get_ee_assets(dt_daily_coll_id)
    else:
        raise ValueError('invalid export destination: {}'.format(
            ini['EXPORT']['export_dest']))

    # Get current running tasks
    tasks = utils.get_ee_tasks()
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        logging.debug('  Tasks: {}\n'.format(len(tasks)))
        input('ENTER')

    collections = [x.strip() for x in ini['INPUTS']['collections'].split(',')]

    # Limit by year and month
    try:
        month_list = sorted(list(utils.parse_int_set(ini['INPUTS']['months'])))
    except:
        logging.info('\nINPUTS "months" parameter not set in the INI,'
                     '\n  Defaulting to all months (1-12)\n')
        month_list = list(range(1, 13))
    # try:
    #     year_list = sorted(list(utils.parse_int_set(ini['INPUTS']['years'])))
    # except:
    #     logging.info('\nINPUTS "years" parameter not set in the INI,'
    #                  '\n  Defaulting to all available years\n')
    #     year_list = []


    iter_start_dt = datetime.datetime.strptime(
        ini['INPUTS']['start_date'], '%Y-%m-%d')
    iter_end_dt = datetime.datetime.strptime(
        ini['INPUTS']['end_date'], '%Y-%m-%d')
    logging.debug('Start Date: {}'.format(iter_start_dt.strftime('%Y-%m-%d')))
    logging.debug('End Date:   {}\n'.format(iter_end_dt.strftime('%Y-%m-%d')))


    for export_dt in sorted(utils.date_range(iter_start_dt, iter_end_dt),
                            reverse=reverse_flag):
        export_date = export_dt.strftime('%Y-%m-%d')

        # if ((month_list and export_dt.month not in month_list) or
        #         (year_list and export_dt.year not in year_list)):
        if month_list and export_dt.month not in month_list:
            logging.debug(f'Date: {export_date} - month not in INI - skipping')
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
                product=dt_name.lower(),
                date=export_dt.strftime('%Y%m%d'),
                export=datetime.datetime.today().strftime('%Y%m%d'),
                dest=ini['EXPORT']['export_dest'].lower())
        logging.debug('  Export ID: {}'.format(export_id))

        if ini['EXPORT']['export_dest'] == 'ASSET':
            asset_id = '{}/{}_{}'.format(
                dt_daily_coll_id, export_dt.strftime('%Y%m%d'),
                datetime.datetime.today().strftime('%Y%m%d'))
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

        # Compute dT using a fake Landsat image
        # The system:time_start property is the only needed value
        model_obj = ssebop.Image(
            ee.Image.constant([0, 0]).rename(['ndvi', 'lst'])
                .set({
                    'system:time_start': utils.millis(export_dt),
                    'system:index': 'LC08_043033_20170716',
                    'system:id': 'LC08_043033_20170716'}),
            dt_source='DAYMET_MEDIAN_V1',
            elev_source='SRTM',
        )

        # Cast to float and set properties
        dt_img = model_obj.dt().float() \
            .set({
                'system:time_start': utils.millis(export_dt),
                'date_ingested': datetime.datetime.today().strftime('%Y-%m-%d'),
                'date': export_dt.strftime('%Y-%m-%d'),
                'year': int(export_dt.year),
                'month': int(export_dt.month),
                'day': int(export_dt.day),
                'doy': int(export_dt.strftime('%j')),
                'model_name': model_name,
                'model_version': ssebop.__version__,
                'dt_source': dt_source.upper(),
                # 'dt_version': dt_version.upper(),
            })

        # Build export tasks
        if ini['EXPORT']['export_dest'] == 'ASSET':
            logging.debug('  Building export task')
            task = ee.batch.Export.image.toAsset(
                image=ee.Image(dt_img),
                description=export_id,
                assetId=asset_id,
                crs=export_crs,
                crsTransform='[' + ','.join(list(map(str, export_geo))) + ']',
                dimensions='{0}x{1}'.format(*export_shape),
            )
            logging.info('  Starting export task')
            utils.ee_task_start(task)

        # Pause before starting next task
        utils.delay_task(delay)
        logging.debug('')


def arg_parse():
    """"""
    parser = argparse.ArgumentParser(
        description='Compute/export daily dT images',
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
    logging.info('\n{0}'.format('#' * 80))
    logging.info('{0:<20s} {1}'.format(
        'Run Time Stamp:', datetime.datetime.now().isoformat(' ')))
    logging.info('{0:<20s} {1}'.format('Current Directory:', os.getcwd()))
    logging.info('{0:<20s} {1}'.format(
        'Script:', os.path.basename(sys.argv[0])))

    main(ini_path=args.ini, overwrite_flag=args.overwrite, delay=args.delay,
         key=args.key, cron_flag=args.cron, reverse_flag=args.reverse)
