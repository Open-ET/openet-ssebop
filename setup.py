import codecs
import os
import re

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

# Single sourcing code from here:
#   https://packaging.python.org/guides/single-sourcing-package-version/
here = os.path.abspath(os.path.dirname(__file__))

def read(*parts):
    with codecs.open(os.path.join(here, *parts), 'r') as fp:
        return fp.read()

def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError('Unable to find version string.')

model_name = 'SSEBop'
version = find_version('openet', model_name.lower(), '__init__.py')

# Get the long description from the README file
here = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='openet-{}'.format(model_name.lower()),
    version=version,
    description='Earth Engine based {} Model'.format(model_name),
    long_description=long_description,
    long_description_content_type='text/x-rst',
    license='Apache',
    author='Charles Morton',
    author_email='charles.morton@dri.edu',
    url='https://github.com/Open-ET/openet-{}-beta'.format(model_name.lower()),
    download_url='https://github.com/Open-ET/openet-{}-beta/archive/v{}.tar.gz'.format(
		model_name.lower(), version),
    install_requires=['earthengine-api', 'openet-core', 'python-dateutil'],
    setup_requires=['pytest-runner'],
    tests_require=['pytest', 'pytest-cov'],
    packages=['openet.{}'.format(model_name.lower())],
    keywords='{} OpenET Evapotranspiration Earth Engine'.format(model_name),
    classifiers = [
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 3.6'],
    zip_safe=False,
)
