import base64
import logging
import os

import ee
import pytest


def pytest_configure():
    # Called before tests are collected
    # https://docs.pytest.org/en/latest/reference.html#_pytest.hookspec.pytest_sessionstart
    logging.basicConfig(level=logging.DEBUG, format='%(message)s')
    logging.debug('Test Setup')

    # On Travis-CI authenticate using private key environment variable
    if 'EE_PRIVATE_KEY_B64' in os.environ:
        print('Writing privatekey.json from environmental variable ...')
        content = base64.b64decode(os.environ['EE_PRIVATE_KEY_B64']).decode('ascii')
        EE_PRIVATE_KEY_FILE = 'privatekey.json'
        with open(EE_PRIVATE_KEY_FILE, 'w') as f:
            f.write(content)
        EE_CREDENTIALS = ee.ServiceAccountCredentials(
            '', key_file=EE_PRIVATE_KEY_FILE)
        ee.Initialize(EE_CREDENTIALS)
    else:
        ee.Initialize()


@pytest.fixture(scope="session", autouse=True)
def test_init():
    # Make a simple EE request
    ee.Number(1).getInfo()
