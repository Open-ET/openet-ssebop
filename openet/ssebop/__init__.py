# try:
#     from importlib import metadata
# except ImportError:  # for Python<3.8
#     import importlib_metadata as metadata

from .image import Image
from .collection import Collection
from . import interpolate

MODEL_NAME = 'SSEBOP'

# __version__ = metadata.version(__package__ or __name__)
