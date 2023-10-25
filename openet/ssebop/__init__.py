# try:
#     from importlib import metadata
# except ImportError:  # for Python<3.8
#     import importlib_metadata as metadata

from .image import Image
from .collection import Collection
from . import interpolate

MODEL_NAME = 'SSEBOP'

# # __version__ = metadata.version(__package__ or __name__)
# __version__ = metadata.version(__package__.replace('.', '-') or __name__.replace('.', '-'))
# # __version__ = metadata.version('openet-ssebop')
