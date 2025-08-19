from .image import Image
from .collection import Collection
from . import interpolate

MODEL_NAME = 'SSEBOP'

from importlib import metadata

__version__ = metadata.version(__package__.replace('.', '-') or __name__.replace('.', '-'))
# __version__ = metadata.version('openet-ssebop')
