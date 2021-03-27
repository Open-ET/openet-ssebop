import argparse
import datetime
import logging
import os
import pprint

import ee

import openet.core.utils as utils


def main(tmax_source, year_start, year_end, doy_list=range(1, 367),
         gee_key_file=None, delay_time=0, max_ready=-1,
         overwrite_flag=False, reverse_flag=False):
    """

    Parameters
    ----------
    tmax_source : {'CIMIS', 'DAYMET_V3', 'DAYMET_V4', 'GRIDMET'}
        Maximum air temperature source keyword.
    year_start : int
    year_end : int
    doy_list : list(int), optional
        Days of year to process (the default is 1-365).
    gee_key_file : str, None, optional
        File path to a service account json key file.
    delay_time : float, optional
        Delay time in seconds between starting export tasks (or checking the
        number of queued tasks, see "max_ready" parameter).  The default is 0.
    max_ready: int, optional
        Maximum number of queued "READY" tasks.  The default is -1 which is
        implies no limit to the number of tasks that will be submitted.
    overwrite_flag : bool, optional
        If True, overwrite existing files (the default is False).
        key_path : str, None, optional
    reverse_flag : bool, optional
        If True, process days in reverse order (the default is False).

    Returns
    -------
    None

    Notes
    -----
    Collection is built/filtered using "day of year" based on the system:time_start
    The DOY 366 collection is built by selecting only the DOY 365 images
        (so the DOY 366 median image should be a copy of the DOY 365 median)

    Daymet calendar definition
      https://daac.ornl.gov/DAYMET/guides/Daymet_Daily_V4.html
    The Daymet calendar is based on a standard calendar year.
    All Daymet years, including leap years, have 1–365 days.
    For leap years, the Daymet data include leap day (February 29) and
      December 31 is discarded from leap years to maintain a 365-day year.

    """
    logging.info('\nGenerating {} median asset'.format(tmax_source))

    tmax_folder = 'projects/earthengine-legacy/assets/projects/usgs-ssebop/tmax'
    # tmax_folder = 'projects/usgs-ssebop/tmax'

    # CGM - Intentionally not setting the time_start
    # time_start_year = 1980

    logging.info('\nInitializing Earth Engine')
    if gee_key_file and os.path.isfile(gee_key_file):
        logging.info('  Using service account key file: {}'.format(gee_key_file))
        # The "EE_ACCOUNT"  doesn't seem to be used if the key file is valid
        ee.Initialize(ee.ServiceAccountCredentials('', key_file=gee_key_file))
    else:
        ee.Initialize()

    # CGM - Should we set default start/end years if they are not set by the user?
    if tmax_source.upper() in ['DAYMET_V3', 'DAYMET_V4']:
        tmax_coll = ee.ImageCollection('NASA/ORNL/' + tmax_source.upper()) \
            .select(['tmax']).map(c_to_k)
    elif tmax_source.upper() == 'CIMIS':
        tmax_coll = ee.ImageCollection('projects/climate-engine/cimis/daily') \
            .select(['Tx'], ['tmax']).map(c_to_k)
    elif tmax_source.upper() == 'GRIDMET':
        tmax_coll = ee.ImageCollection('IDAHO_EPSCOR/GRIDMET') \
            .select(['tmmx'], ['tmax'])
    # elif tmax_source.upper() == 'TOPOWX':
    #     tmax_coll = ee.ImageCollection('TOPOWX') \
    #         .select(['tmmx'], ['tmax'])
    else:
        logging.error('Unsupported tmax_source: {}'.format(tmax_source))
        return False

    coll_id = f'{tmax_folder}/{tmax_source.lower()}_median_{year_start}_{year_end}'

    tmax_info = ee.Image(tmax_coll.first()).getInfo()
    tmax_proj = ee.Image(tmax_coll.first()).projection().getInfo()
    if 'wkt' in tmax_proj.keys():
        crs = tmax_proj['wkt'].replace(' ', '').replace('\n', '')
    else:
        # TODO: Add support for projection have a "crs" key instead of "wkt"
        raise Exception('unsupported projection type')

    if tmax_source.upper() in ['DAYMET_V3', 'DAYMET_V4']:
        # TODO: Check if the DAYMET_V4 grid is aligned to DAYMET_V3
        # Custom smaller extent for DAYMET focused on CONUS
        extent = [-1999750, -1890500, 2500250, 1109500]
        dimensions = [4500, 3000]
        transform = [1000, 0, -1999750, 0, -1000, 1109500]
        # Custom medium extent for DAYMET of CONUS, Mexico, and southern Canada
        # extent = [-2099750, -3090500, 2900250, 1909500]
        # dimensions = [5000, 5000]
        # transform = [1000, 0, -2099750, 0, -1000, 1909500]
    else:
        transform = tmax_proj['transform']
        dimensions = tmax_info['bands'][0]['dimensions']
    logging.info('  CRS: {}'.format(crs))
    logging.info('  Transform: {}'.format(transform))
    logging.info('  Dimensions: {}\n'.format(dimensions))

    # Build the export collection if it doesn't exist
    if not ee.data.getInfo(coll_id):
        logging.info('\nImage collection does not exist and will be built'
                     '\n  {}'.format(coll_id))
        input('Press ENTER to continue')
        ee.data.createAsset({'type': 'ImageCollection'}, coll_id)
        # # Switch type string if use_cloud_api=True
        # ee.data.createAsset({'type': 'IMAGE_COLLECTION'}, coll_id)

    # Get current running assets
    # CGM: This is currently returning the asset IDs without earthengine-legacy
    assets = utils.get_ee_assets(coll_id)

    # Get current running tasks
    tasks = utils.get_ee_tasks()
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        logging.debug('  Tasks: {}'.format(len(tasks)))
        input('ENTER')


    for doy in sorted(doy_list, reverse=reverse_flag):
        logging.info('DOY: {:03d}'.format(doy))

        # CGM - Intentionally not setting the time_start
        # What year should we use for the system:time_start?
        # time_start_dt = datetime.datetime.strptime(
        #     '{}_{:03d}'.format(time_start_year, doy), '%Y_%j')
        # logging.debug('  Time Start Date: {}'.format(
        #     time_start_dt.strftime('%Y-%m-%d')))

        asset_id = '{}/{:03d}'.format(coll_id, doy)
        asset_short_id = asset_id.replace('projects/earthengine-legacy/assets/', '')
        export_id = 'tmax_{}_median_{}_{}_day{:03d}'.format(
            tmax_source.lower(), year_start, year_end, doy)
        logging.debug('  Asset ID:  {}'.format(asset_id))
        logging.debug('  Export ID: {}'.format(export_id))

        if overwrite_flag:
            if export_id in tasks.keys():
                logging.info('  Task already submitted, cancelling')
                ee.data.cancelTask(tasks[export_id])
            if asset_short_id in assets or asset_id in assets:
                logging.info('  Asset already exists, removing')
                ee.data.deleteAsset(asset_id)
        else:
            if export_id in tasks.keys():
                logging.info('  Task already submitted, skipping')
                continue
            elif asset_id in assets:
                logging.info('  Asset already exists, skipping')
                continue

        # Filter the Tmax collection the target day of year
        if doy < 366:
            tmax_doy_coll = tmax_coll \
                .filter(ee.Filter.calendarRange(doy, doy, 'day_of_year')) \
                .filter(ee.Filter.calendarRange(year_start, year_end, 'year'))
        else:
            # Compute DOY 366 as a copy of the DOY 365 values
            tmax_doy_coll = tmax_coll \
                .filter(ee.Filter.calendarRange(365, 365, 'day_of_year')) \
                .filter(ee.Filter.calendarRange(year_start, year_end, 'year'))

        # Compute the median Tmax
        tmax_img = ee.Image(tmax_doy_coll.median())

        # Fill interior water holes with the mean of the surrounding cells
        # Use the filled image as the source to the where since tmax is nodata
        # CGM - Check if this is needed for DAYMET_V4
        if tmax_source.upper() in ['DAYMET_V3', 'DAYMET_V4']:
            filled_img = tmax_img.focal_mean(4000, 'circle', 'meters') \
                .reproject(crs, transform)
            tmax_img = filled_img.where(tmax_img.gt(0), tmax_img)
            # tmax_img = filled_img.where(tmax_img, tmax_img)

        tmax_img = tmax_img.set({
            'date_ingested': datetime.datetime.today().strftime('%Y-%m-%d'),
            'doy': int(doy),
            # 'doy': ee.String(ee.Number(doy).format('%03d')),
            'year_start': year_start,
            'year_end': year_end,
            'years': tmax_doy_coll.size(),
            # CGM - Intentionally not setting the time_start
            # 'system:time_start': ee.Date(
            #     time_start_dt.strftime('%Y-%m-%d')).millis()
        })

        # Build export tasks
        logging.debug('  Building export task')
        task = ee.batch.Export.image.toAsset(
            tmax_img,
            description=export_id,
            assetId=asset_id,
            dimensions='{0}x{1}'.format(*dimensions),
            crs=crs,
            crsTransform='[' + ','.join(map(str, transform)) + ']',
            maxPixels=int(1E10),
        )
        # task = ee.batch.Export.image.toCloudStorage(
        #     tmax_img,
        #     description=export_id,
        #     bucket='tmax_',
        #     fileNamePrefix=export_id,
        #     dimensions='{0}x{1}'.format(*dimensions),
        #     crs=crs,
        #     crsTransform='[' + ','.join(map(str, transform)) + ']',
        #     maxPixels=int(1E10),
        #     fileFormat='GeoTIFF',
        #     formatOptions={'cloudOptimized': True},
        # )

        logging.info('  Starting export task')
        utils.ee_task_start(task)

        # Pause before starting next task
        utils.delay_task(delay_time, max_ready)


def c_to_k(image):
    """Convert temperature from C to K"""
    return image.add(273.15).copyProperties(image, ['system:time_start'])


def arg_parse():
    """"""
    parser = argparse.ArgumentParser(
        description='Generate Tmax Median Assets',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--tmax', type=str, metavar='TMAX',
        choices=['CIMIS', 'DAYMET_V3', 'DAYMET_V4', 'GRIDMET'],
        help='Maximum air temperature source keyword')
    parser.add_argument(
        '--start', type=int, metavar='YEAR', help='Start year')
    parser.add_argument(
        '--end', type=int, metavar='YEAR', help='End year')
    parser.add_argument(
        '--doy', default='1-366', metavar='DOY', type=utils.parse_int_set,
        help='Day of year (DOY) range to process')
    parser.add_argument(
        '--key', type=utils.arg_valid_file, metavar='FILE',
        help='Earth Engine service account JSON key file')
    parser.add_argument(
        '--delay', default=0, type=float,
        help='Delay (in seconds) between each export tasks')
    parser.add_argument(
        '--ready', default=-1, type=int,
        help='Maximum number of queued READY tasks')
    parser.add_argument(
        '--reverse', default=False, action='store_true',
        help='Process MGRS tiles in reverse order')
    parser.add_argument(
        '-o', '--overwrite', default=False, action='store_true',
        help='Force overwrite of existing files')
    parser.add_argument(
        '-d', '--debug', default=logging.INFO, const=logging.DEBUG,
        help='Debug level logging', action='store_const', dest='loglevel')
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = arg_parse()

    logging.basicConfig(level=args.loglevel, format='%(message)s')
    logging.getLogger('googleapiclient').setLevel(logging.ERROR)

    main(tmax_source=args.tmax, year_start=args.start, year_end=args.end,
         doy_list=args.doy, gee_key_file=args.key,
         delay_time=args.delay, max_ready=args.ready,
         overwrite_flag=args.overwrite, reverse_flag=args.reverse,
    )
