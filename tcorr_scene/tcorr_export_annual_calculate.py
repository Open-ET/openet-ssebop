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

ANNUAL_TCORR_INDEX = 6
NODATA_TCORR_INDEX = 9


def main(ini_path=None, overwrite_flag=False, delay_time=0, gee_key_file=None,
         max_ready=-1, reverse_flag=False):
    """Compute monthly Tcorr images by WRS2 tile

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
    logging.info('\nCompute annual Tcorr images by WRS2 tile')

    ini = utils.read_ini(ini_path)

    model_name = 'SSEBOP'
    # model_name = ini['INPUTS']['et_model'].upper()

    tmax_name = ini[model_name]['tmax_source']

    export_id_fmt = 'tcorr_scene_{product}_{wrs2}_annual'
    asset_id_fmt = '{coll_id}/{wrs2}'

    tcorr_annual_coll_id = '{}/{}_annual'.format(
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

    # TODO: Add try/except blocks and default values?
    collections = [x.strip() for x in ini['INPUTS']['collections'].split(',')]
    cloud_cover = float(ini['INPUTS']['cloud_cover'])
    min_pixel_count = float(ini['TCORR']['min_pixel_count'])
    min_scene_count = float(ini['TCORR']['min_scene_count'])

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


    # Extract the model keyword arguments from the INI
    # Set the property name to lower case and try to cast values to numbers
    model_args = {
        k.lower(): float(v) if utils.is_number(v) else v
        for k, v in dict(ini[model_name]).items()}
    # et_reference_args = {
    #     k: model_args.pop(k)
    #     for k in [k for k in model_args.keys() if k.startswith('et_reference_')]}


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
            study_area_extent = [-125, 25, -65, 49]
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


    if not ee.data.getInfo(tcorr_annual_coll_id):
        logging.info('\nExport collection does not exist and will be built'
                     '\n  {}'.format(tcorr_annual_coll_id))
        input('Press ENTER to continue')
        ee.data.createAsset({'type': 'IMAGE_COLLECTION'}, tcorr_annual_coll_id)

    # Get current asset list
    logging.debug('\nGetting GEE asset list')
    asset_list = utils.get_ee_assets(tcorr_annual_coll_id)
    # if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
    #     pprint.pprint(asset_list[:10])

    # Get current running tasks
    tasks = utils.get_ee_tasks()
    if logging.getLogger().getEffectiveLevel() == logging.DEBUG:
        logging.debug('  Tasks: {}\n'.format(len(tasks)))
        input('ENTER')


    # if cron_flag:
    #     # CGM - This seems like a silly way of getting the date as a datetime
    #     #   Why am I doing this and not using the commented out line?
    #     end_dt = datetime.date.today().strftime('%Y-%m-%d')
    #     end_dt = datetime.datetime.strptime(end_dt, '%Y-%m-%d')
    #     end_dt = end_dt + datetime.timedelta(days=-4)
    #     # end_dt = datetime.datetime.today() + datetime.timedelta(days=-1)
    #     start_dt = end_dt + datetime.timedelta(days=-64)
    # else:
    start_dt = datetime.datetime.strptime(
        ini['INPUTS']['start_date'], '%Y-%m-%d')
    end_dt = datetime.datetime.strptime(
        ini['INPUTS']['end_date'], '%Y-%m-%d')
    start_date = start_dt.strftime('%Y-%m-%d')
    end_date = end_dt.strftime('%Y-%m-%d')
    next_date = (end_dt + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    logging.debug('Start Date: {}'.format(start_date))
    logging.debug('End Date:   {}\n'.format(end_date))


    # Limit by year and month
    # try:
    #     month_list = sorted(list(utils.parse_int_set(ini['TCORR']['months'])))
    # except:
    #     logging.info('\nTCORR "months" parameter not set in the INI,'
    #                  '\n  Defaulting to all months (1-12)\n')
    #     month_list = list(range(1, 13))
    try:
        year_list = sorted(list(utils.parse_int_set(ini['TCORR']['years'])))
    except:
        logging.info('\nTCORR "years" parameter not set in the INI,'
                     '\n  Defaulting to all available years\n')
        year_list = []

    # Get the list of WRS2 tiles that intersect the data area and study area
    wrs2_coll = ee.FeatureCollection(wrs2_coll_id) \
        .filterBounds(export_geom) \
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
        # wrs2_path = wrs2_ftr['properites']['PATH']
        # wrs2_row = wrs2_ftr['properites']['ROW']

        export_id = export_id_fmt.format(
            product=tmax_name.lower(), wrs2=wrs2_tile)
        logging.debug('  Export ID: {}'.format(export_id))

        asset_id = asset_id_fmt.format(
            coll_id=tcorr_annual_coll_id, wrs2=wrs2_tile)
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

        # CGM: I couldn't find a way to build this from the Collection class
        # TODO: Will need to be changed/updated for SR collection
        # TODO: Add code to handle real time collections
        landsat_coll = ee.ImageCollection([])
        if 'LANDSAT/LC08/C01/T1_TOA' in collections:
            l8_coll = ee.ImageCollection('LANDSAT/LC08/C01/T1_TOA') \
                .filterMetadata('WRS_PATH', 'equals', wrs2_path) \
                .filterMetadata('WRS_ROW', 'equals', wrs2_row) \
                .filterMetadata('CLOUD_COVER_LAND', 'less_than', cloud_cover) \
                .filterMetadata('DATA_TYPE', 'equals', 'L1TP') \
                .filter(ee.Filter.gt('system:time_start',
                                     ee.Date('2013-03-24').millis()))
            #     .filterDate(start_date, next_date)
            landsat_coll = landsat_coll.merge(l8_coll)
        if 'LANDSAT/LE07/C01/T1_TOA' in collections:
            l7_coll = ee.ImageCollection('LANDSAT/LE07/C01/T1_TOA') \
                .filterMetadata('WRS_PATH', 'equals', wrs2_path) \
                .filterMetadata('WRS_ROW', 'equals', wrs2_row) \
                .filterMetadata('CLOUD_COVER_LAND', 'less_than', cloud_cover) \
                .filterMetadata('DATA_TYPE', 'equals', 'L1TP')
            #     .filterDate(start_date, next_date)
            landsat_coll = landsat_coll.merge(l7_coll)
        if 'LANDSAT/LT05/C01/T1_TOA' in collections:
            l5_coll = ee.ImageCollection('LANDSAT/LT05/C01/T1_TOA') \
                .filterMetadata('WRS_PATH', 'equals', wrs2_path) \
                .filterMetadata('WRS_ROW', 'equals', wrs2_row) \
                .filterMetadata('CLOUD_COVER_LAND', 'less_than', cloud_cover) \
                .filterMetadata('DATA_TYPE', 'equals', 'L1TP') \
                .filter(ee.Filter.lt('system:time_start',
                                     ee.Date('2011-12-31').millis()))
            #     .filterDate(start_date, next_date)
            landsat_coll = landsat_coll.merge(l5_coll)
        # if 'LANDSAT/LT04/C01/T1_TOA' in collections:
        #     l4_coll = ee.ImageCollection('LANDSAT/LT04/C01/T1_TOA') \
        #         .filterMetadata('WRS_PATH', 'equals', wrs2_path) \
        #         .filterMetadata('WRS_ROW', 'equals', wrs2_row) \
        #         .filterMetadata('CLOUD_COVER_LAND', 'less_than', cloud_cover) \
        #         .filterMetadata('DATA_TYPE', 'equals', 'L1TP')
        #         #     .filterDate(start_date, next_date)
        #     landsat_coll = landsat_coll.merge(l4_coll)

        def tcorr_img_func(landsat_img):
            # TODO: Will need to be changed for SR
            t_obj = ssebop.Image.from_landsat_c1_toa(landsat_img, **model_args)
            t_stats = ee.Dictionary(t_obj.tcorr_stats) \
                .combine({'tcorr_value': 0, 'tcorr_count': 0}, overwrite=False)
            tcorr = ee.Number(t_stats.get('tcorr_value'))
            count = ee.Number(t_stats.get('tcorr_count'))

            return tmax_mask.add(tcorr) \
                .rename(['tcorr']) \
                .set({
                'system:time_start': ee.Image(landsat_img).get('system:time_start'),
                'tcorr_value': tcorr,
                'tcorr_pixel_count': count,
            })

        # Filter the Tcorr image collection based on the pixel counts
        tcorr_coll = ee.ImageCollection(landsat_coll.map(tcorr_img_func)) \
            .filterMetadata('tcorr_pixel_count', 'not_less_than', min_pixel_count)

        # Use a common reducer for the image and property stats
        reducer = ee.Reducer.median() \
            .combine(ee.Reducer.count(), sharedInputs=True)

        # Compute stats from the collection images
        # This might be used when Tcorr is spatial
        # tcorr_img = tcorr_coll.reduce(reducer).rename(['tcorr', 'count'])

        # Compute stats from the image properties
        tcorr_stats = ee.List(tcorr_coll.aggregate_array('tcorr_value')) \
            .reduce(reducer)
        tcorr_stats = ee.Dictionary(tcorr_stats) \
            .combine({'median': 0, 'count': 0}, overwrite=False)
        tcorr = ee.Number(tcorr_stats.get('median'))
        count = ee.Number(tcorr_stats.get('count'))
        index = count.lt(min_scene_count)\
            .multiply(NODATA_TCORR_INDEX - ANNUAL_TCORR_INDEX)\
            .add(ANNUAL_TCORR_INDEX)
        # index = ee.Algorithms.If(count.gte(min_scene_count), 6, 9)

        # Clip the mask image to the Landsat footprint
        # Change mask values to 1 if count >= threshold
        # Mask values of 0 will be set to nodata
        mask_img = tmax_mask.add(count.gte(min_scene_count)) \
            .clip(ee.Geometry(wrs2_ftr['geometry']))
        output_img = ee.Image(
                [mask_img.multiply(tcorr), mask_img.multiply(count)]) \
            .rename(['tcorr', 'count']) \
            .updateMask(mask_img.unmask(0))

        # # Write an empty image if the pixel count is too low
        # # CGM: Check/test if this can be combined into a single If()
        # tcorr_img = ee.Algorithms.If(
        #     count.gte(min_scene_count),
        #     tmax_mask.add(tcorr), tmax_mask.updateMask(0))
        # count_img = ee.Algorithms.If(
        #     count.gte(min_scene_count),
        #     tmax_mask.add(count), tmax_mask.updateMask(0))
        #
        # # Clip to the Landsat image footprint
        # output_img = ee.Image([tcorr_img, count_img]) \
        #     .rename(['tcorr', 'count']) \
        #     .clip(ee.Geometry(wrs2_ftr['geometry']))
        # # Clear the transparency mask
        # output_img = output_img.updateMask(output_img.unmask(0))

        output_img = output_img.set({
            'date_ingested': datetime.datetime.today().strftime('%Y-%m-%d'),
            'model_name': model_name,
            'model_version': ssebop.__version__,
            # 'system:time_start': utils.millis(start_dt),
            'tcorr_value': tcorr,
            'tcorr_index': index,
            'tcorr_scene_count': count,
            'tmax_source': tmax_source.upper(),
            'tmax_version': tmax_version.upper(),
            'wrs2_path': wrs2_path,
            'wrs2_row': wrs2_row,
            'wrs2_tile': wrs2_tile,
            'years': ','.join(map(str, year_list)),
            # 'year_start': year_list[0],
            # 'year_end': year_list[-1],
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
        description='Compute/export annual Tcorr images by WRS2 tile',
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
        help='Process tiles in reverse order')
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
