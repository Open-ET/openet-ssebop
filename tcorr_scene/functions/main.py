import base64
import datetime
import logging
import time

import ee
from flask import abort, Response

import openet.ssebop as ssebop

logging.getLogger('googleapiclient').setLevel(logging.ERROR)


# DAYMET v2 Median Tcorr Export Input File
MODEL_NAME = 'SSEBOP'
COLLECTIONS = ['LANDSAT/LC08/C01/T1_TOA', 'LANDSAT/LE07/C01/T1_TOA']
CLOUD_COVER = 70
STUDY_AREA_EXTENT = [-125, 25, -65, 49]
EXPORT_COLL = 'projects/earthengine-legacy/assets/projects/usgs-ssebop/tcorr_scene'
TMAX_SOURCE = 'DAYMET_MEDIAN_V2'
MIN_PIXEL_COUNT = 1000
TCORR_DEFAULT = 0.978


def main(request):
    """Compute scene Tcorr images by date

    Parameters
    ----------
    start_date : str, optional
    end_date : str, optional

    Returns
    -------
    str : ?

    """
    logging.info('\nCompute scene Tcorr images by date')

    export_id_fmt = 'tcorr_scene_{product}_{scene_id}'
    asset_id_fmt = '{coll_id}/{scene_id}'
    tcorr_scene_coll_id = '{}/{}_scene'.format(EXPORT_COLL, TMAX_SOURCE.lower())
    model_args = {'tmax_source': 'DAYMET_MEDIAN_V2'}

    # Default start and end date to None if not set
    try:
        start_date = request.args['start']
    except:
        start_date = None
    try:
        end_date = request.args['end']
    except:
        end_date = None

    if not start_date and not end_date:
        # Process the last 60 days by default
        start_dt = datetime.datetime.today() - datetime.timedelta(days=60)
        end_dt = datetime.datetime.today() - datetime.timedelta(days=1)
    elif start_date and end_date:
        # Only process custom range if start and end are both set
        # Limit the end date to the current date
        try:
            start_dt = datetime.datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = min(
                datetime.datetime.strptime(end_date, '%Y-%m-%d'),
                datetime.datetime.today() - datetime.timedelta(days=1))
            # end_dt = end_dt + datetime.timedelta(days=1)
        except ValueError as e:
            response = 'Error parsing start and end dates\n'
            response += str(e)
            abort(404, description=response)
        # if start_dt < datetime.datetime(1984, 3, 23):
        #     logging.debug('Start Date: {} - no Landsat 5+ images before '
        #                   '1984-03-23'.format(start_dt.strftime('%Y-%m-%d')))
        #     start_dt = datetime.datetime(1984, 3, 23)
        if start_dt > end_dt:
            return abort(404, description='Start date must be before end date')
    else:
        response = 'Both start and end date must be specified'
        abort(404, description=response)
    logging.info('Start Date: {}'.format(start_dt.strftime('%Y-%m-%d')))
    logging.info('End Date:   {}'.format(end_dt.strftime('%Y-%m-%d')))

    # if (TMAX_SOURCE.upper() == 'CIMIS' and end_date < '2003-10-01'):
    #     logging.error(
    #         '\nCIMIS is not currently available before 2003-10-01, exiting\n')
    #     abort()
    # elif (TMAX_SOURCE.upper() == 'DAYMET' and end_date > '2018-12-31'):
    #     logging.warning(
    #         '\nDAYMET is not currently available past 2018-12-31, '
    #         'using median Tmax values\n')


    logging.debug('\nInitializing Earth Engine')
    ee.Initialize(ee.ServiceAccountCredentials('', key_file='privatekey.json'),
                  use_cloud_api=True)

    if not ee.data.getInfo(tcorr_scene_coll_id):
        return abort(404, description='Export collection does not exist')


    # Get a Tmax image to set the Tcorr values to
    logging.debug('\nTmax properties')
    tmax_source = TMAX_SOURCE.split('_', 1)[0]
    tmax_version = TMAX_SOURCE.split('_', 1)[1]
    if 'MEDIAN' in TMAX_SOURCE.upper():
        tmax_coll_id = 'projects/earthengine-legacy/assets/' \
                       'projects/usgs-ssebop/tmax/{}'.format(TMAX_SOURCE.lower())
        tmax_coll = ee.ImageCollection(tmax_coll_id)
        tmax_mask = ee.Image(tmax_coll.first()).select([0]).multiply(0)
    else:
        # TODO: Add support for non-median tmax sources
        raise ValueError('unsupported tmax_source: {}'.format(TMAX_SOURCE))
    logging.debug('  Collection: {}'.format(tmax_coll_id))
    logging.debug('  Source:  {}'.format(tmax_source))
    logging.debug('  Version: {}'.format(tmax_version))


    logging.debug('\nExport properties')
    export_info = get_info(ee.Image(tmax_mask))
    if 'daymet' in TMAX_SOURCE.lower():
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


    if STUDY_AREA_EXTENT is None:
        if 'daymet' in TMAX_SOURCE.lower():
            # CGM - For now force DAYMET to a slightly smaller "CONUS" extent
            study_area_extent = [-125, 25, -65, 49]
            # study_area_extent =  [-125, 25, -65, 52]
        elif 'cimis' in TMAX_SOURCE.lower():
            study_area_extent = [-124, 35, -119, 42]
        else:
            # TODO: Make sure output from bounds is in WGS84
            study_area_extent = tmax_mask.geometry().bounds().getInfo()
        logging.debug(f'\nStudy area extent not set, '
                      f'default to {STUDY_AREA_EXTENT}')
    study_area_geom = ee.Geometry.Rectangle(
        STUDY_AREA_EXTENT, proj='EPSG:4326', geodesic=False)

    # Intersect study area with export extent
    export_geom = export_geom.intersection(study_area_geom, 1)
    # logging.debug('Extent: {}'.format(export_geom.bounds().getInfo()))

    # # If cell_size parameter is set in the INI,
    # # adjust the output cellsize and recompute the transform and shape
    # try:
    #     export_cs = CELL_SIZE
    #     export_shape = [
    #         int(math.ceil(abs((export_shape[0] * export_geo[0]) / export_cs))),
    #         int(math.ceil(abs((export_shape[1] * export_geo[4]) / export_cs)))]
    #     export_geo = [export_cs, 0.0, export_geo[2], 0.0, -export_cs, export_geo[5]]
    #     logging.debug('  Custom export cell size: {}'.format(export_cs))
    #     logging.debug('  Geo: {}'.format(export_geo))
    #     logging.debug('  Shape: {}'.format(export_shape))
    # except KeyError:
    #     pass


    # Get current asset list
    logging.debug('\nGetting GEE asset list')
    asset_list = get_ee_assets(tcorr_scene_coll_id)

    # Get current running tasks
    logging.debug('\nGetting GEE task list')
    tasks = get_ee_tasks()


    # if update_flag:
    #     assets_info = utils.get_info(ee.ImageCollection(
    #         tcorr_scene_coll_id).filterDate(start_date, end_date))
    #     asset_props = {f'{scene_coll_id}/{x["properties"]["system:index"]}':
    #                        x['properties']
    #                    for x in assets_info['features']}
    # else:
    #     asset_props = {}

    response = 'Tcorr scene export tasks\n'

    for export_dt in sorted(date_range(start_dt, end_dt)):
        export_date = export_dt.strftime('%Y-%m-%d')
        next_date = (export_dt + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

        logging.debug(f'Date: {export_date}')

        model_obj = ssebop.Collection(
            collections=COLLECTIONS,
            start_date=export_date,
            end_date=next_date,
            cloud_cover_max=CLOUD_COVER,
            geometry=export_geom,
            model_args=model_args,
            # filter_args=filter_args,
        )
        landsat_coll = model_obj.overpass(variables=['ndvi'])

        try:
            image_id_list = landsat_coll.aggregate_array('system:id').getInfo()
        except Exception as e:
            logging.warning('  Error getting image ID list, skipping date')
            logging.debug(f'  {e}')
            continue

        # Sort by path/row
        for image_id in sorted(image_id_list,
                               key=lambda k: k.split('/')[-1].split('_')[-2],
                               reverse=True):
            scene_id = image_id.split('/')[-1]

            wrs2_path = int(scene_id[5:8])
            wrs2_row = int(scene_id[8:11])
            wrs2_tile = 'p{:03d}r{:03d}'.format(wrs2_path, wrs2_row)
            logging.debug(f'{scene_id}')

            export_id = export_id_fmt.format(
                product=TMAX_SOURCE.lower(), scene_id=scene_id)
            logging.debug(f'  Export ID: {export_id}')

            asset_id = asset_id_fmt.format(
                coll_id=tcorr_scene_coll_id, scene_id=scene_id)
            logging.debug(f'  Asset ID: {asset_id}')

            if export_id in tasks.keys():
                logging.debug('  Task already submitted, skipping')
                continue
            elif asset_id in asset_list:
                logging.debug('  Asset already exists, skipping')
                continue

            image = ee.Image(image_id)
            # TODO: Will need to be changed for SR or use from_image_id()
            t_obj = ssebop.Image.from_landsat_c1_toa(image_id, **model_args)
            t_stats = ee.Dictionary(t_obj.tcorr_stats) \
                .combine({'tcorr_p5': 0, 'tcorr_count': 0}, overwrite=False)
            tcorr = ee.Number(t_stats.get('tcorr_p5'))
            count = ee.Number(t_stats.get('tcorr_count'))
            index = ee.Algorithms.If(count.gte(MIN_PIXEL_COUNT), 0, 9)

            # Write an empty image if the pixel count is too low
            tcorr_img = ee.Algorithms.If(
                count.gte(MIN_PIXEL_COUNT),
                tmax_mask.add(tcorr), tmax_mask.updateMask(0))

            # Clip to the Landsat image footprint
            output_img = ee.Image(tcorr_img).clip(image.geometry())

            # Clear the transparency mask
            output_img = output_img.updateMask(output_img.unmask(0)) \
                .rename(['tcorr']) \
                .set({
                    'CLOUD_COVER': image.get('CLOUD_COVER'),
                    'CLOUD_COVER_LAND': image.get('CLOUD_COVER_LAND'),
                    # 'SPACECRAFT_ID': image.get('SPACECRAFT_ID'),
                    'coll_id': image_id.split('/')[0],
                    # 'cycle_day': ((export_dt - cycle_base_dt).days % 8) + 1,
                    'date_ingested': datetime.datetime.today().strftime('%Y-%m-%d'),
                    'date': export_dt.strftime('%Y-%m-%d'),
                    'doy': int(export_dt.strftime('%j')),
                    'model_name': MODEL_NAME,
                    'model_version': ssebop.__version__,
                    'month': int(export_dt.month),
                    'scene_id': image_id.split('/')[-1],
                    'system:time_start': image.get('system:time_start'),
                    'tcorr_value': tcorr,
                    'tcorr_index': index,
                    'tcorr_pixel_count': count,
                    'tmax_source': tmax_source.upper(),
                    'tmax_version': tmax_version.upper(),
                    'wrs2_path': wrs2_path,
                    'wrs2_row': wrs2_row,
                    'wrs2_tile': wrs2_tile,
                    'year': int(export_dt.year),
                })

            # logging.debug('  Building export task')
            task = ee.batch.Export.image.toAsset(
                image=output_img,
                description=export_id,
                assetId=asset_id,
                crs=export_crs,
                crsTransform='[' + ','.join(list(map(str, export_geo))) + ']',
                dimensions='{0}x{1}'.format(*export_shape),
                # crsTransform=list(map(str, export_geo)),
                # dimensions=export_shape,
            )

            # logging.debug('  Starting export task')
            ee_task_start(task)

            response += '{}\n'.format(export_id)

    response += 'End\n'
    return Response(response, mimetype='text/plain')


def date_range(start_dt, end_dt, days=1, skip_leap_days=True):
    """Generate dates within a range (inclusive)

    Parameters
    ----------
    start_dt : datetime
        start date.
    end_dt : datetime
        end date.
    days : int, optional
        Step size (the default is 1).
    skip_leap_days : bool, optional
        If True, skip leap days while incrementing (the default is True).

    Yields
    ------
    datetime

    """
    import copy
    curr_dt = copy.copy(start_dt)
    while curr_dt <= end_dt:
        if not skip_leap_days or curr_dt.month != 2 or curr_dt.day != 29:
            yield curr_dt
        curr_dt += datetime.timedelta(days=days)


def ee_task_start(task, n=10):
    """Make an exponential backoff Earth Engine request"""
    for i in range(1, n):
        try:
            task.start()
            break
        except Exception as e:
            logging.info('    Resending query ({}/{})'.format(i, n))
            logging.debug('    {}'.format(e))
            time.sleep(i ** 2)
    return task


def get_ee_assets(asset_id):
    """Return Google Earth Engine assets

    Parameters
    ----------
    asset_id : str
        A folder or image collection ID.

    Returns
    -------
    list of asset names

    """
    try:
        asset_list = ee.data.getList({'id': asset_id})
        asset_list = [x['id'] for x in asset_list if x['type'] == 'Image']
    except Exception as e:
        logging.error('\n  Unknown error, returning False')
        logging.error(e)
        asset_list = []
    return asset_list


def get_ee_tasks(states=['RUNNING', 'READY']):
    """Return current active tasks

    Parameters
    ----------
    states : list, optional
        List of task states to check (the default is ['RUNNING', 'READY']).

    Returns
    -------
    dict : task descriptions (key) and full task info dictionary (value)

    """
    logging.debug('\nActive Tasks')
    for i in range(1, 10):
        try:
            task_list = ee.data.getTaskList()
            # task_list = ee.data.listOperations()
            break
        except Exception as e:
            logging.warning('  Exception retrieving task list, retrying')
            logging.debug('    {}'.format(e))
            time.sleep(i ** 2)
            # return {}
    task_list = sorted(
        [task for task in task_list if task['state'] in states],
        key=lambda t: (t['state'], t['description'], t['id']))
    tasks = {}
    for task in task_list:
        tasks[task['description']] = task
    return tasks


def get_info(ee_obj, max_retries=2):
    """Make an exponential back off getInfo call on an Earth Engine object"""
    output = None
    for i in range(1, max_retries):
        try:
            output = ee_obj.getInfo()
        except ee.ee_exception.EEException as e:
            if ('Earth Engine memory capacity exceeded' in str(e) or
                    'Earth Engine capacity exceeded' in str(e)):
                logging.info('    Resending query ({}/{})'.format(i, max_retries))
                logging.debug('    {}'.format(e))
                time.sleep(i ** 2)
            else:
                logging.debug('Unhandled Earth Engine exception, exiting')
                raise e
        except Exception as e:
            logging.info('    Resending query ({}/{})'.format(i, max_retries))
            logging.debug('    {}'.format(e))
            time.sleep(i ** 2)

        if output:
            break

    return output
