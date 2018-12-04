import calendar
import datetime
import logging
import subprocess
import sys

import ee


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


def get_ee_assets(asset_id, shell_flag=False):
    """Return Google Earth Engine assets

    Parameters
    ----------
    asset_id : str
        A folder or image collection ID.
    shell_flag : bool, optional
        If True, execute the command through the shell (the default is True).

    Returns
    -------
    list of asset names

    """
    try:
        asset_list = subprocess.check_output(
            ['earthengine', 'ls', asset_id],
            universal_newlines=True, shell=shell_flag)
        asset_list = [x.strip() for x in asset_list.split('\n') if x]
        # logging.debug(asset_list)
    except ValueError as e:
        logging.info('  Collection doesn\'t exist')
        logging.debug('  {}'.format(str(e)))
        asset_list = []
    except Exception as e:
        logging.error('\n  Unknown error, returning False')
        logging.error(e)
        sys.exit()
    return asset_list


def get_ee_tasks(states=['RUNNING', 'READY'], verbose=True):
    """Return current active tasks

    Parameters
    ----------
    states : list, optional
        List of task states to check (the default is ['RUNNING', 'READY']).
    verbose : boolean, optional
        If True, print list of all active tasks (the default is True).

    Returns
    -------
    dict : task descriptions (key) and IDs (value)

    """
    logging.debug('\nActive Tasks')
    for i in range(1, 10):
        try:
            task_list = ee.data.getTaskList()
            break
        except Exception as e:
            logging.warning(
                '  Exception retrieving task list {} retrying'.format(e))
            time.sleep(i ** 2)
            # return {}

    task_list = sorted([
        [t['state'], t['description'], t['id']] for t in task_list
        if t['state'] in states])
    if verbose:
        if task_list:
            logging.debug('  {:8s} {}'.format('STATE', 'DESCRIPTION'))
            logging.debug('  {:8s} {}'.format('=====', '==========='))
        else:
            logging.debug('  None')

    tasks = {}
    for t_state, t_desc, t_id in task_list:
        if verbose:
            logging.debug('  {:8s} {}'.format(t_state, t_desc))
            # logging.debug('  {:8s} {} {}'.format(t_state, t_desc, t_id))
        tasks[t_desc] = t_id
        # tasks[t_id] = t_desc
    return tasks


def millis(input_dt):
    """Convert datetime to milliseconds since epoch"""
    # Python 3 (or 2 with future module)
    return 1000 * int(calendar.timegm(input_dt.timetuple()))
    # Python 2
    # return 1000 * long(calendar.timegm(input_dt.timetuple()))
    # return 1000 * long(time.mktime(input_dt.timetuple()))
