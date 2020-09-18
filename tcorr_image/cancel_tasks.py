import argparse
import logging
import pprint
import re

import ee

import utils


def main(key=None, state='READY', regex=None):
    """Cancel Earth Engine tasks

    Parameters
    ----------
    key : str, optional
        File path to an Earth Engine json key file.
    state : str, {'ALL', 'READY', 'RUNNING'}
        Task state (the default is to only cancel 'READY' tasks).
    regex : str, optional

    """
    logging.info('\nCancelling {} tasks'.format(state.lower()))

    if state == 'ALL':
        states = ['READY', 'RUNNING']
    else:
        states = [state]

    logging.info('\nInitializing Earth Engine')
    if key:
        logging.info('  Using service account key file: {}'.format(key))
        # The "EE_ACCOUNT" parameter is not used if the key file is valid
        ee.Initialize(ee.ServiceAccountCredentials('deadbeef', key_file=key))
    else:
        ee.Initialize()

    # Get current task list
    tasks = utils.get_ee_tasks(states=states)

    if regex:
        logging.info('\nFiltering tasks:')
        logging.info('{}'.format(regex))
        tasks = {task_desc: task_info for task_desc, task_info in tasks.items()
                 if re.match(regex, task_desc)}

    logging.info('\nCancelling tasks:')
    for task_desc, task_info in tasks.items():
        logging.info(task_desc)
        logging.debug(task_info)
        try:
            ee.data.cancelTask(task_info['id'])
            # ee.data.cancelOperation(tasks[export_id]['id'])
        except Exception as e:
            logging.info('  Exception: {}\n  Skipping'.format(e))


def arg_parse():
    """"""
    parser = argparse.ArgumentParser(
        description='Cancel Earth Engine tasks',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--key', type=utils.arg_valid_file,
        help='JSON key file', metavar='FILE')
    parser.add_argument(
        '--state', default='READY', choices=['ALL', 'READY', 'RUNNING'],
        help='Task state')
    parser.add_argument(
        '--regex', help='Regular expression for filtering task IDs ')
    parser.add_argument(
        '-d', '--debug', default=logging.INFO, const=logging.DEBUG,
        help='Debug level logging', action='store_const', dest='loglevel')
    args = parser.parse_args()

    return args


if __name__ == "__main__":
    args = arg_parse()

    logging.basicConfig(level=args.loglevel, format='%(message)s')
    logging.getLogger('googleapiclient').setLevel(logging.ERROR)

    main(key=args.key, state=args.state, regex=args.regex)
