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


def main(ini_path=None, overwrite_flag=False, delay_time=0, gee_key_file=None,
         max_ready=-1):
    """Compute default Tcorr image asset

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

    """
    logging.info('\nCompute default Tcorr image asset')

    ini = utils.read_ini(ini_path)

    model_name = 'SSEBOP'
    # model_name = ini['INPUTS']['et_model'].upper()

    tmax_name = ini[model_name]['tmax_source']

    export_id_fmt = 'tcorr_image_{product}_default'

    tcorr_daily_coll_id = '{}/{}_daily'.format(
        ini['EXPORT']['export_coll'], tmax_name.lower())
    tcorr_default_img_id = '{}/{}_default'.format(
        ini['EXPORT']['export_coll'], tmax_name.lower())

    try:
        tcorr_default = ini[model_name]['tcorr_default']
    except:
        tcorr_default = 0.978

    if (tmax_name.upper() == 'CIMIS' and
            ini['INPUTS']['end_date'] < '2003-10-01'):
        logging.error(
            '\nCIMIS is not currently available before 2003-10-01, exiting\n')
        sys.exit()
    elif (tmax_name.upper() == 'DAYMET' and
            ini['INPUTS']['end_date'] > '2018-12-31'):
        logging.warning(
            '\nDAYMET is not currently available past 2018-12-31, '
            'using median Tmax values\n')
        # sys.exit()
    # elif (tmax_name.upper() == 'TOPOWX' and
    #         ini['INPUTS']['end_date'] > '2017-12-31'):
    #     logging.warning(
    #         '\nDAYMET is not currently available past 2017-12-31, '
    #         'using median Tmax values\n')
    #     # sys.exit()

    logging.info('\nInitializing Earth Engine')
    if gee_key_file:
        logging.info('  Using service account key file: {}'.format(gee_key_file))
        # The "EE_ACCOUNT" parameter is not used if the key file is valid
        ee.Initialize(ee.ServiceAccountCredentials('x', key_file=gee_key_file),
                      use_cloud_api=True)
    else:
        ee.Initialize(use_cloud_api=True)

    logging.debug('\nTmax properties')
    tmax_source = tmax_name.split('_', 1)[0]
    tmax_version = tmax_name.split('_', 1)[1]
    # tmax_coll_id = 'projects/earthengine-legacy/assets/' \
    #                'projects/usgs-ssebop/tmax/{}'.format(tmax_name.lower())
    # tmax_coll = ee.ImageCollection(tmax_coll_id)
    # tmax_mask = ee.Image(tmax_coll.first()).select([0]).multiply(0)
    # logging.debug('  Collection: {}'.format(tmax_coll_id))
    logging.debug('  Source: {}'.format(tmax_source))
    logging.debug('  Version: {}'.format(tmax_version))

    # Get the Tcorr daily image collection properties
    logging.debug('\nTcorr Image properties')
    tcorr_img = ee.Image(ee.ImageCollection(tcorr_daily_coll_id).first())
    tcorr_info = utils.get_info(ee.Image(tcorr_img))
    tcorr_geo = tcorr_info['bands'][0]['crs_transform']
    tcorr_crs = tcorr_info['bands'][0]['crs']
    tcorr_shape = tcorr_info['bands'][0]['dimensions']
    # tcorr_geo = ee.Image(tcorr_img).projection().getInfo()['transform']
    # tcorr_crs = ee.Image(tcorr_img).projection().getInfo()['crs']
    # tcorr_shape = ee.Image(tcorr_img).getInfo()['bands'][0]['dimensions']
    tcorr_extent = [tcorr_geo[2], tcorr_geo[5] + tcorr_shape[1] * tcorr_geo[4],
                    tcorr_geo[2] + tcorr_shape[0] * tcorr_geo[0], tcorr_geo[5]]
    logging.debug('  Shape: {}'.format(tcorr_shape))
    logging.debug('  Extent: {}'.format(tcorr_extent))
    logging.debug('  Geo: {}'.format(tcorr_geo))
    logging.debug('  CRS: {}'.format(tcorr_crs))

    # Get current running tasks
    tasks = utils.get_ee_tasks()
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        logging.debug('  Tasks: {}\n'.format(len(tasks)))
        input('ENTER')

    # # Limit by year
    # try:
    #     year_list = sorted(list(utils.parse_int_set(ini['TCORR']['years'])))
    # except:
    #     logging.info('\nTCORR "years" parameter not set in the INI,'
    #                  '\n  Defaulting to all available years\n')
    #     year_list = []

    export_id = export_id_fmt.format(product=tmax_name.lower())
    logging.info('  Export ID: {}'.format(export_id))
    logging.info('  Asset ID: {}'.format(tcorr_default_img_id))

    if overwrite_flag:
        if export_id in tasks.keys():
            logging.debug('  Task already submitted, cancelling')
            ee.data.cancelTask(tasks[export_id]['id'])
        # This is intentionally not an "elif" so that a task can be
        # cancelled and an existing image/file/asset can be removed
        if ee.data.getInfo(tcorr_default_img_id):
            logging.debug('  Asset already exists, removing')
            ee.data.deleteAsset(tcorr_default_img_id)
    else:
        if export_id in tasks.keys():
            logging.debug('  Task already submitted, exiting')
            return False
        elif ee.data.getInfo(tcorr_default_img_id):
            logging.debug('  Asset already exists, exiting')
            return False

    tcorr_daily_coll = ee.ImageCollection(tcorr_daily_coll_id)

    output_img = tcorr_daily_coll.mosaic().multiply(0).add(tcorr_default)\
        .updateMask(1).rename(['tcorr'])\
        .set({
            # 'system:time_start': utils.millis(iter_start_dt),
            'date_ingested': datetime.datetime.today().strftime('%Y-%m-%d'),
            'model_name': model_name,
            'model_version': ssebop.__version__,
            'tmax_source': tmax_source.upper(),
            'tmax_version': tmax_version.upper(),
        })

    logging.debug('  Building export task')
    task = ee.batch.Export.image.toAsset(
        image=ee.Image(output_img),
        description=export_id,
        assetId=tcorr_default_img_id,
        crs=tcorr_crs,
        crsTransform='[' + ','.join(list(map(str, tcorr_geo))) + ']',
        dimensions='{0}x{1}'.format(*tcorr_shape),
    )

    logging.debug('  Starting export task')
    utils.ee_task_start(task)

    # Pause before starting the next export task
    utils.delay_task(delay_time, max_ready)
    logging.debug('')


def arg_parse():
    """"""
    parser = argparse.ArgumentParser(
        description='Compute/export default Tcorr image asset',
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
         delay_time=args.delay, gee_key_file=args.key, max_ready=args.ready)
