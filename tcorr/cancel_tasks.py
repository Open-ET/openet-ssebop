import argparse
import datetime
import logging
import os
import sys

import ee

import utils


def main(key=None, state='READY'):
    """Cancel Earth Engine tasks

    Parameters
    ----------
    key : str, optional
        File path to an Earth Engine json key file.
    state : str, {'ALL', 'READY', 'RUNNING'}
        Task state (the default is to only cancel 'READY' tasks).

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
        ee.Initialize(ee.ServiceAccountCredentials('deadbeef', key_file=key),
                      use_cloud_api=False)
    else:
        ee.Initialize(use_cloud_api=False)

    # Get current task list
    tasks = utils.get_ee_tasks(states=states)

    logging.info('\nCancelling tasks:')
    for k, v in tasks.items():
        logging.info(k)
        ee.data.cancelTask(v)


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

    main(key=args.key, state=args.state)
