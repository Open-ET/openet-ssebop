import argparse
import calendar
import configparser
import datetime
import logging
import os
import subprocess
import sys
import time

import ee


def arg_valid_file(file_path):
    """Argparse specific function for testing if file exists

    Convert relative paths to absolute paths
    """
    if os.path.isfile(os.path.abspath(os.path.realpath(file_path))):
        return os.path.abspath(os.path.realpath(file_path))
        # return file_path
    else:
        raise argparse.ArgumentTypeError('{} does not exist'.format(file_path))


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


def delay_task(delay_time):
    """"""
    if delay_time and delay_time > 0:
        time.sleep(delay_time)
    elif delay_time and delay_time <= -1:
        # Don't continue to the next export until all tasks are RUNNING
        # Make an initial pause before checking tasks lists to allow
        #   for previous export to start up.
        delay_time = abs(delay_time)
        logging.debug('  Pausing {} seconds'.format(delay_time))
        time.sleep(delay_time)

        # Don't continue until all there are no "READY" tasks
        while True:
            ready_tasks = get_ee_tasks(states=['READY'], verbose=True)
            logging.debug('  Ready tasks: {}'.format(
                ', '.join(sorted(ready_tasks.keys()))))

            # Try to keep 2 tasks queued
            if len(ready_tasks.keys()) >= 2:
                logging.debug(
                    '  Waiting {} seconds to start more tasks'.format(delay_time))
                time.sleep(delay_time)
            else:
                logging.debug('  All tasks running, continuing iteration')
                break


def ee_task_start(task, n=10):
    """Make an exponential backoff Earth Engine request"""
    output = None
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
        # asset_list = ee.data.listImages(asset_id)
        # logging.debug(asset_list)
    except Exception as e:
        logging.error('\n  Unknown error, returning False')
        logging.error(e)
        sys.exit()
    # except ValueError as e:
    #     logging.info('  Collection doesn\'t exist')
    #     logging.debug('  {}'.format(str(e)))
    #     asset_list = []
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


def image_exists(asset_id):
    try:
        ee.Image(asset_id).getInfo()
        return True
    except Exception as e:
        # print(e)
        return False


def millis(input_dt):
    """Convert datetime to milliseconds since epoch"""
    # Python 3 (or 2 with future module)
    return 1000 * int(calendar.timegm(input_dt.timetuple()))
    # Python 2
    # return 1000 * long(calendar.timegm(input_dt.timetuple()))
    # return 1000 * long(time.mktime(input_dt.timetuple()))


def parse_int_set(nputstr=""):
    """Return list of numbers given a string of ranges

    http://thoughtsbyclayg.blogspot.com/2008/10/parsing-list-of-numbers-in-python.html
    """
    selection = set()
    invalid = set()
    # tokens are comma seperated values
    tokens = [x.strip() for x in nputstr.split(',')]
    for i in tokens:
        try:
            # typically tokens are plain old integers
            selection.add(int(i))
        except:
            # if not, then it might be a range
            try:
                token = [int(k.strip()) for k in i.split('-')]
                if len(token) > 1:
                    token.sort()
                    # we have items seperated by a dash
                    # try to build a valid range
                    first = token[0]
                    last = token[len(token) - 1]
                    for x in range(first, last + 1):
                        selection.add(x)
            except:
                # not an int and not a range...
                invalid.add(i)
    # Report invalid tokens before returning valid selection
    # print "Invalid set: " + str(invalid)
    return selection


def read_ini(ini_path):
    logging.debug('\nReading Input File')
    # Open config file
    config = configparser.ConfigParser()
    try:
        config.read(ini_path)
    except Exception as e:
        logging.error(
            '\nERROR: Input file could not be read, '
            'is not an input file, or does not exist\n'
            '  ini_path={}\n\nException: {}'.format(ini_path, e))
        sys.exit()

    # Force conversion of unicode to strings
    ini = dict()
    for section in config.keys():
        ini[str(section)] = {}
        for k, v in config[section].items():
            ini[str(section)][str(k)] = v
    return ini
