# import datetime
import pprint
import re
import warnings

# from deprecated import deprecated
import ee
import openet.core.common
# TODO: import utils from common
# import openet.core.utils as utils

from openet.ssebop import landsat
from openet.ssebop import model
from openet.ssebop import utils

PROJECT_FOLDER = 'projects/earthengine-legacy/assets/projects/usgs-ssebop'
# PROJECT_FOLDER = 'projects/usgs-ssebop'


def lazy_property(fn):
    """Decorator that makes a property lazy-evaluated

    https://stevenloria.com/lazy-properties/
    """
    attr_name = '_lazy_' + fn.__name__

    @property
    def _lazy_property(self):
        if not hasattr(self, attr_name):
            setattr(self, attr_name, fn(self))
        return getattr(self, attr_name)
    return _lazy_property


class Image:
    """Earth Engine based SSEBop Image"""

    _C2_LST_CORRECT = True  # C2 LST correction to recalculate LST default value

    def __init__(
            self, image,
            et_reference_source=None,
            et_reference_band=None,
            et_reference_factor=None,
            et_reference_resample=None,
            et_reference_date_type=None,
            dt_source='projects/earthengine-legacy/assets/projects/usgs-ssebop/dt/daymet_median_v6',
            tcorr_source='FANO',
            tmax_source='projects/earthengine-legacy/assets/projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010',
            elr_flag=False,
            et_fraction_type='alfalfa',
            et_fraction_grass_source=None,
            lst_source=None,
            **kwargs,
    ):
        """Construct a generic SSEBop Image

        Parameters
        ----------
        image : ee.Image
            A 'prepped' SSEBop input image.
            Image must have bands: 'ndvi', 'ndwi', 'lst', 'qa_water'.
            Image must have properties: 'system:id', 'system:index', 'system:time_start'.
        et_reference_source : str, float, optional
            Reference ET source (the default is None).
            Parameter is required if computing 'et' or 'et_reference'.
        et_reference_band : str, optional
            Reference ET band name (the default is None).
            Parameter is required if computing 'et' or 'et_reference'.
        et_reference_factor : float, None, optional
            Reference ET scaling factor.  The default is None which is
            equivalent to 1.0 (or no scaling).
        et_reference_resample : {'nearest', 'bilinear', 'bicubic', None}, optional
            Reference ET resampling.  The default is None which is equivalent
            to nearest neighbor resampling.
        dt_source : str or float, optional
            dT source image collection ID.
            The default is 'projects/usgs-ssebop/dt/daymet_median_v6'.
        tcorr_source : 'FANO' or float, optional
            Tcorr source keyword.  The default is 'FANO' which will compute Tcorr
            using the 'Forcing And Normalizing Operation' process.
        tmax_source : collection ID or float, optional
            Maximum air temperature source image collection ID.
            The default is 'projects/usgs-ssebop/tmax/daymet_v4_mean_1981_2010'.
        elr_flag : bool, str, optional
            If True, apply Elevation Lapse Rate (ELR) adjustment (the default is False).
            The 'elev_source' keyword argument will need to be set to a valid
            elevation asset image ID.
        et_fraction_type : {'alfalfa', 'grass'}, optional
            ET fraction reference type.  The default is 'alfalfa'.
            If set to "grass", the et_fraction_grass_source parameter must also be set.
        et_fraction_grass_source : {'NASA/NLDAS/FORA0125_H002',
                                    'ECMWF/ERA5_LAND/HOURLY'}, float, optional
            Reference ET source for alfalfa to grass reference adjustment.
            Parameter must be set if et_fraction_type is 'grass'.
            The default is currently the NLDAS hourly collection,
            but having a default will likely be removed in a future version.
        lst_source : str, optional
            Land surface temperature source image collection ID.
            CGM - Add text detailing any properties, image names, band names, etc
              that are required for the source image collection
        kwargs : dict, optional
            dt_resample : {'nearest', 'bilinear'}
            tcorr_resample : {'nearest', 'bilinear'}
            tmax_resample : {'nearest', 'bilinear'}
            elev_source : str or float
            min_pixels_per_image : int

        Notes
        -----
        Input image must have an uppercase Landsat style 'system:index'
        (i.e. LC08_043033_20150805)

        """
        self.image = ee.Image(image)

        # Set as "lazy_property" below in order to return custom properties
        # self.lst = self.image.select('lst')
        # self.ndvi = self.image.select('ndvi')

        # Copy system properties
        self._id = self.image.get('system:id')
        self._index = self.image.get('system:index')
        self._time_start = self.image.get('system:time_start')
        self._properties = {
            'system:index': self._index,
            'system:time_start': self._time_start,
            'image_id': self._id,
        }

        # Build SCENE_ID from the (possibly merged) system:index
        scene_id = ee.List(ee.String(self._index).split('_')).slice(-3)
        self._scene_id = (
            ee.String(scene_id.get(0)).cat('_')
            .cat(ee.String(scene_id.get(1))).cat('_')
            .cat(ee.String(scene_id.get(2)))
        )

        # Build WRS2_TILE from the scene_id
        self._wrs2_tile = ee.String('p').cat(self._scene_id.slice(5, 8))\
            .cat('r').cat(self._scene_id.slice(8, 11))

        # Set server side date/time properties using the 'system:time_start'
        self._date = ee.Date(self._time_start)
        self._year = ee.Number(self._date.get('year'))
        self._month = ee.Number(self._date.get('month'))
        self._start_date = ee.Date(utils.date_to_time_0utc(self._date))
        self._end_date = self._start_date.advance(1, 'day')
        self._doy = ee.Number(self._date.getRelative('day', 'year')).add(1).int()

        # Reference ET parameters
        self.et_reference_source = et_reference_source
        self.et_reference_band = et_reference_band
        self.et_reference_factor = et_reference_factor
        self.et_reference_resample = et_reference_resample
        self.et_reference_date_type = et_reference_date_type

        # Check reference ET parameters
        if et_reference_factor and not utils.is_number(et_reference_factor):
            raise ValueError('et_reference_factor must be a number')
        if et_reference_factor and (self.et_reference_factor < 0):
            raise ValueError('et_reference_factor must be greater than zero')
        et_reference_resample_methods = ['nearest', 'bilinear', 'bicubic']
        if (et_reference_resample and
                (et_reference_resample.lower() not in et_reference_resample_methods)):
            raise ValueError('unsupported et_reference_resample method')
        et_reference_date_type_methods = ['doy', 'daily']
        if (et_reference_date_type and
                (et_reference_date_type.lower() not in et_reference_date_type_methods)):
            raise ValueError('unsupported et_reference_date_type method')

        # Model input parameters
        self._dt_source = dt_source
        self._tcorr_source = tcorr_source
        self._tmax_source = tmax_source
        self._lst_source = lst_source

        # TODO: Move into keyword args section below
        self._elr_flag = elr_flag

        # TODO: Move into keyword args section below
        # Convert elr_flag from string to bool IF necessary
        if type(self._elr_flag) is str:
            if self._elr_flag.upper() in ['TRUE']:
                self._elr_flag = True
            elif self._elr_flag.upper() in ['FALSE']:
                self._elr_flag = False
            else:
                raise ValueError(f'elr_flag "{self._elr_flag}" could not be interpreted as bool')
        # assert isinstance(self._elr_flag, bool), "selection type must be a boolean"

        # ET fraction type
        if et_fraction_type.lower() not in ['alfalfa', 'grass']:
            raise ValueError('et_fraction_type must "alfalfa" or "grass"')
        self.et_fraction_type = et_fraction_type.lower()

        # ET fraction alfalfa to grass reference adjustment
        # The NLDAS hourly collection will be used if a source value is not set
        if self.et_fraction_type.lower() == 'grass' and not et_fraction_grass_source:
            warnings.warn(
                'NLDAS is being set as the default ET fraction grass adjustment source.  '
                'In a future version the parameter will need to be set explicitly as: '
                'et_fraction_grass_source="NASA/NLDAS/FORA0125_H002".',
                FutureWarning
            )
            et_fraction_grass_source = 'NASA/NLDAS/FORA0125_H002'
        self.et_fraction_grass_source = et_fraction_grass_source
        # if self.et_fraction_type.lower() == 'grass' and not et_fraction_grass_source:
        #     raise ValueError(
        #         'et_fraction_grass_source parameter must be set if et_fraction_type==\'grass\''
        #     )
        # # Should the supported source values be checked here instead of in model.py?
        # if et_fraction_grass_source not in et_fraction_grass_sources:
        #     raise ValueError('unsupported et_fraction_grass_source')

        # Image projection and geotransform
        self.crs = image.projection().crs()
        self.transform = ee.List(
            ee.Dictionary(ee.Algorithms.Describe(image.projection())).get('transform')
        )
        # self.crs = image.select([0]).projection().getInfo()['crs']
        # self.transform = image.select([0]).projection().getInfo()['transform']

        """Keyword arguments"""
        # CGM - What is the right way to process kwargs with default values?
        self.kwargs = kwargs

        if 'elev_source' in kwargs.keys():
            self._elev_source = kwargs['elev_source']
        else:
            self._elev_source = None

        # CGM - Should these be checked in the methods they are used in instead?
        # Set the resample method as properties so they can be modified
        if 'dt_resample' in kwargs.keys():
            self._dt_resample = kwargs['dt_resample'].lower()
        else:
            self._dt_resample = 'bilinear'

        if 'tmax_resample' in kwargs.keys():
            self._tmax_resample = kwargs['tmax_resample'].lower()
        else:
            self._tmax_resample = 'bilinear'

        if 'tcorr_resample' in kwargs.keys():
            self._tcorr_resample = kwargs['tcorr_resample'].lower()
        else:
            self._tcorr_resample = 'bilinear'

    def calculate(self, variables=['et', 'et_reference', 'et_fraction']):
        """Return a multiband image of calculated variables

        Parameters
        ----------
        variables : list

        Returns
        -------
        ee.Image

        """
        output_images = []
        for v in variables:
            if v.lower() == 'et':
                output_images.append(self.et.float())
            elif v.lower() == 'et_fraction':
                output_images.append(self.et_fraction.float())
            elif v.lower() == 'et_reference':
                output_images.append(self.et_reference.float())
            elif v.lower() == 'lst':
                output_images.append(self.lst.float())
            elif v.lower() == 'mask':
                output_images.append(self.mask)
            elif v.lower() == 'ndvi':
                output_images.append(self.ndvi.float())
            # elif v.lower() == 'qa':
            #     output_images.append(self.qa)
            elif v.lower() == 'quality':
                output_images.append(self.quality)
            elif v.lower() == 'time':
                output_images.append(self.time)
            else:
                raise ValueError(f'unsupported variable: {v}')

        return ee.Image(output_images).set(self._properties)

    @lazy_property
    def et_fraction(self):
        """Fraction of reference ET"""

        # Adjust air temperature based on elevation (Elevation Lapse Rate)
        # TODO: Eventually point this at the model.elr_adjust() function instead
        # =========================================================
        if self._elr_flag:
            tmax = ee.Image(model.lapse_adjust(self.tmax, ee.Image(self.elev)))
        else:
            tmax = self.tmax

        if type(self._tcorr_source) is str and self._tcorr_source.upper() == 'FANO':
            # bilinearly resample tmax at 1km (smoothed).
            tmax = tmax.resample('bilinear')

        if (self._dt_resample and type(self._dt_resample) is str and
                self._dt_resample.lower() in ['bilinear', 'bicubic']):
            dt = self.dt.resample(self._dt_resample)
        else:
            dt = self.dt

        et_fraction = model.et_fraction(lst=self.lst, tmax=tmax, tcorr=self.tcorr, dt=dt)

        # Convert the ET fraction to a grass reference fraction
        if self.et_fraction_type.lower() == 'grass' and self.et_fraction_grass_source:
            if utils.is_number(self.et_fraction_grass_source):
                et_fraction = et_fraction.multiply(self.et_fraction_grass_source)
            else:
                et_fraction = model.etf_grass_type_adjust(
                    etf=et_fraction,
                    src_coll_id=self.et_fraction_grass_source,
                    time_start=self._time_start,
                )

        return et_fraction.set(self._properties)\
            .set({
                'tcorr_index': self.tcorr.get('tcorr_index'),
                'et_fraction_type': self.et_fraction_type.lower()
            })

    @lazy_property
    def et_reference(self):
        """Reference ET for the image date"""
        if utils.is_number(self.et_reference_source):
            # Interpret numbers as constant images
            # CGM - Should we use the ee_types here instead?
            #   i.e. ee.ee_types.isNumber(self.et_reference_source)
            et_reference_img = ee.Image.constant(self.et_reference_source)
        elif type(self.et_reference_source) is str:
            # Assume a string source is an image collection ID (not an image ID)
            if (self.et_reference_date_type is None or
                    self.et_reference_date_type.lower() == 'daily'):
                # Assume the collection is daily with valid system:time_start values
                et_reference_coll = (
                    ee.ImageCollection(self.et_reference_source)
                    .filterDate(self._start_date, self._end_date)
                    .select([self.et_reference_band])
                )
            elif self.et_reference_date_type.lower() == 'doy':
                # Assume the image collection is a climatology with a "DOY" property
                et_reference_coll = (
                    ee.ImageCollection(self.et_reference_source)
                    .filter(ee.Filter.rangeContains('DOY', self._doy, self._doy))
                    .select([self.et_reference_band])
                )
            else:
                raise ValueError(
                    f'unsupported et_reference_date_type: {self.et_reference_date_type}'
                )

            et_reference_img = ee.Image(et_reference_coll.first())
            if self.et_reference_resample in ['bilinear', 'bicubic']:
                et_reference_img = et_reference_img.resample(self.et_reference_resample)
        # elif type(self.et_reference_source) is list:
        #     # Interpret as list of image collection IDs to composite/mosaic
        #     #   i.e. Spatial CIMIS and GRIDMET
        #     # CGM - Need to check the order of the collections
        #     et_reference_coll = ee.ImageCollection([])
        #     for coll_id in self.et_reference_source:
        #         coll = ee.ImageCollection(coll_id)\
        #             .select([self.et_reference_band])\
        #             .filterDate(self.start_date, self.end_date)
        #         et_reference_img = et_reference_coll.merge(coll)
        #     et_reference_img = et_reference_coll.mosaic()
        # elif isinstance(self.et_reference_source, computedobject.ComputedObject):
        #     # Interpret computed objects as image collections
        #     et_reference_coll = ee.ImageCollection(self.et_reference_source)\
        #         .select([self.et_reference_band])\
        #         .filterDate(self.start_date, self.end_date)
        else:
            raise ValueError(f'unsupported et_reference_source: {self.et_reference_source}')

        if self.et_reference_factor:
            et_reference_img = et_reference_img.multiply(self.et_reference_factor)

        # Map ETr values directly to the input (i.e. Landsat) image pixels
        # The benefit of this is the ETr image is now in the same crs as the
        #   input image.  Not all models may want this though.
        # CGM - Should the output band name match the input ETr band name?
        return self.qa_water_mask.float().multiply(0).add(et_reference_img)\
            .rename(['et_reference']).set(self._properties)

    @lazy_property
    def et(self):
        """Actual ET as fraction of reference times"""
        return self.et_fraction.multiply(self.et_reference)\
            .rename(['et']).set(self._properties)

    @lazy_property
    def lst(self):
        """Input land surface temperature (LST) [K]"""
        lst_img = self.image.select(['lst'])

        if ((type(self._lst_source) is str) and (
                self._lst_source.lower().startswith('projects/') or
                self._lst_source.lower().startswith('users/'))):
            # Use a custom LST image from a separate LST source collection
            # LST source assumptions (for now)
            #   String lst_source is an image collection ID
            #   Images in LST source collection are single band
            #   Images have a "scene_id" property with an upper case ID in the
            #     system:index format (LXSS_PPPRRR_YYYYMMDD)
            #   If a "scale_factor" property is present it will be applied by multiplying
            # A masked LST image will be used if scene is not in LST source
            # TODO: Consider adding support for setting some sort of "lst_source_index"
            #   parameter to allow for joining on a property other than "scene_id"
            mask_img = lst_img.multiply(0).selfMask().set({'lst_source_id': 'None'})
            lst_img = ee.Image(
                ee.ImageCollection(self._lst_source)
                .filter(ee.Filter.eq('scene_id', self._index))
                .select([0], ['lst'])
                .map(lambda img: img.set({'lst_source_id': img.get('system:id')}))
                .merge(ee.ImageCollection([mask_img]))
                .first()
            )
            # # Switching to this merge line (above) would allow for the input LST
            # # image to be used as a fallback if the scene is missing from LST source
            # # instead of returning a masked image
            # .merge(ee.ImageCollection([lst_img.set({'lst_source_id': self._id})]))

            # The scale_factor multiply call below drops the lst_source property
            lst_source_id = lst_img.get('lst_source_id')

            # The OpenET LST images are scaled, so assume the image need to be unscaled
            lst_scale_factor = (
                ee.Dictionary({'scale_factor': lst_img.get('scale_factor')})
                .combine({'scale_factor': 1.0}, overwrite=False)
            )
            lst_img = lst_img.multiply(ee.Number(lst_scale_factor.get('scale_factor')))

            # Save the actual LST source image ID as a property on the lst image
            # Source ID could also be added to general properties
            lst_img = lst_img.set('lst_source_id', lst_source_id)
            self._properties['lst_source_id'] = lst_source_id

        # TODO: Consider adding support for setting lst_source with a computed object
        #   like an ee.ImageCollection (and/or ee.Image, ee.Number)
        # elif isinstance(self._lst_source, ee.computedobject.ComputedObject):
        #     lst_img = self.lst_source

        return lst_img.set(self._properties)

    @lazy_property
    def mask(self):
        """Mask of all active pixels (based on the final et_fraction)"""
        return (
            self.et_fraction.multiply(0).add(1).updateMask(1)
            .rename(['mask']).set(self._properties).uint8()
        )

    @lazy_property
    def ndvi(self):
        """Input normalized difference vegetation index (NDVI)"""
        return self.image.select(['ndvi']).set(self._properties)

    @lazy_property
    def ndwi(self):
        """Input normalized difference water index (NDWI) to mask water features"""
        return self.image.select(['ndwi']).set(self._properties)

    @lazy_property
    def qa_water_mask(self):
        """Landsat Collection 2 QA_PIXEL water mask"""
        return self.image.select(['qa_water']).set(self._properties)

    @lazy_property
    def quality(self):
        """Set quality to 1 for all active pixels (for now)"""
        return self.mask.rename(['quality']).set(self._properties)

    @lazy_property
    def tcorr_not_water_mask(self):
        """Mask of pixels that have a high confidence of not being water

        The purpose for this mask is to ensure that water pixels are not used in
            the Tcorr FANO calculation.

        Output image will be 1 for pixels that are not-water and 0 otherwise

        NDWI in landsat.py is defined as "green - swir1", which is "flipped"
            compared to NDVI and other NDWI calculations,
            so water will be positive and land will be negative

        """
        ndwi_threshold = -0.15

        # TODO: Check if .multiply() is the same as .And() here
        #   The .And() seems more readable
        not_water_mask = (
            ee.Image(self.ndwi).lt(ndwi_threshold)
            .multiply(self.qa_water_mask.eq(0))
            # .And(self.qa_water_mask.eq(0))
        )

        return not_water_mask.rename(['tcorr_not_water']).set(self._properties).uint8()

    @lazy_property
    def time(self):
        """Return an image of the 0 UTC time (in milliseconds)"""
        return (
            self.mask
            .double().multiply(0).add(utils.date_to_time_0utc(self._date))
            .rename(['time']).set(self._properties)
        )

    @lazy_property
    def dt(self):
        """

        Returns
        -------
        ee.Image

        Raises
        ------
        ValueError
            If `self._dt_source` is not supported.

        """
        if utils.is_number(self._dt_source):
            dt_img = ee.Image.constant(float(self._dt_source))
        elif (self._dt_source.lower().startswith('projects/') or
              self._dt_source.lower().startswith('users/')):
            # Use precomputed dT median assets
            # Assumes a string source is an image collection ID (not an image ID),
            #   MF: and currently only supports a climatology 'DOY-based' dataset filter
            dt_coll = (
                ee.ImageCollection(self._dt_source)
                .filter(ee.Filter.calendarRange(self._doy, self._doy, 'day_of_year'))
            )
            # MF: scale factor property only applied for string ID dT collections, and
            #  no clamping used for string ID dT collections.
            dt_img = ee.Image(dt_coll.first())
            dt_scale_factor = (
                ee.Dictionary({'scale_factor': dt_img.get('scale_factor')})
                .combine({'scale_factor': 1.0}, overwrite=False)
            )
            dt_img = dt_img.multiply(ee.Number.parse(dt_scale_factor.get('scale_factor')))
        else:
            raise ValueError(f'Invalid dt_source: {self._dt_source}\n')

        # # MF: moved this resample to happen at the et_fraction function
        # if self._dt_resample and self._dt_resample.lower() in ['bilinear', 'bicubic']:
        #     dt_img = dt_img.resample(self._dt_resample)
        # # TODO: A reproject call may be needed here also
        # # dt_img = dt_img.reproject(self.crs, self.transform)

        return dt_img.rename('dt')

    @lazy_property
    def elev(self):
        """Elevation [m]

        Returns
        -------
        ee.Image

        Raises
        ------
        ValueError
            If `self._elev_source` is not supported.

        """
        if self._elev_source is None:
            raise ValueError('elev_source was not set')
        elif utils.is_number(self._elev_source):
            elev_image = ee.Image.constant(float(self._elev_source))
        elif type(self._elev_source) is str:
            elev_image = ee.Image(self._elev_source)
        # elif (self._elev_source.lower().startswith('projects/') or
        #       self._elev_source.lower().startswith('users/')):
        #     elev_image = ee.Image(self._elev_source)
        else:
            raise ValueError(f'Unsupported elev_source: {self._elev_source}\n')

        return elev_image.select([0], ['elev'])

    @lazy_property
    def tcorr(self):
        """Compute Tcorr

        Returns
        -------
        ee.Image

        Raises
        ------
        ValueError
            If `self._tcorr_source` is not supported.

        """
        if utils.is_number(self._tcorr_source):
            return (
                ee.Image.constant(float(self._tcorr_source)).rename(['tcorr'])
                .set({'tcorr_source': f'custom_{self._tcorr_source}'})
            )
        elif 'FANO' == self._tcorr_source.upper():
            return (
                ee.Image(self.tcorr_FANO).select(['tcorr'])
                .updateMask(1)
                .set({'tcorr_source': 'FANO'})
            )
        else:
            raise ValueError(f'Unsupported tcorr_source: {self._tcorr_source}\n')

    @lazy_property
    def tmax(self):
        """Get Tmax image from precomputed climatology collections or dynamically

        Returns
        -------
        ee.Image

        Raises
        ------
        ValueError
            If `self._tmax_source` is not supported.

        """
        if utils.is_number(self._tmax_source):
            # Allow Tmax source to be set as a number for testing
            tmax_image = (
                ee.Image.constant(float(self._tmax_source)).rename(['tmax'])
                .set({'tmax_source': 'custom_{}'.format(self._tmax_source)})
            )
        elif re.match(r'^projects/.+/tmax/.+_(mean|median)_\d{4}_\d{4}(_\w+)?', self._tmax_source):
            # Process Tmax source as a collection ID
            # The Tmax collections do not have a time_start so filter use the "doy" property instead
            tmax_coll = (
                ee.ImageCollection(self._tmax_source)
                .filterMetadata('doy', 'equals', self._doy)
                #.filterMetadata('doy', 'equals', self._doy.format('%03d'))
            )
            tmax_image = ee.Image(tmax_coll.first()).set({'tmax_source': self._tmax_source})
        else:
            raise ValueError(f'Unsupported tmax_source: {self._tmax_source}\n')

        if self._tmax_resample and (self._tmax_resample.lower() in ['bilinear', 'bicubic']):
            tmax_image = tmax_image.resample(self._tmax_resample)

        # TODO: A reproject call may be needed here also
        # tmax_image = tmax_image.reproject(self.crs, self.transform)

        return tmax_image

    @classmethod
    def from_image_id(cls, image_id, **kwargs):
        """Constructs an SSEBop Image instance from an image ID

        Parameters
        ----------
        image_id : str
            An earth engine image ID.
            (i.e. 'LANDSAT/LC08/C02/T1_L2/LC08_044033_20170716')
        kwargs
            Keyword arguments to pass through to model init.

        Returns
        -------
        new instance of Image class

        """
        collection_methods = {
            'LANDSAT/LT04/C02/T1_L2': 'from_landsat_c2_sr',
            'LANDSAT/LT05/C02/T1_L2': 'from_landsat_c2_sr',
            'LANDSAT/LE07/C02/T1_L2': 'from_landsat_c2_sr',
            'LANDSAT/LC08/C02/T1_L2': 'from_landsat_c2_sr',
            'LANDSAT/LC09/C02/T1_L2': 'from_landsat_c2_sr',
        }

        try:
            method_name = collection_methods[image_id.rsplit('/', 1)[0]]
        except KeyError:
            raise ValueError(f'unsupported collection ID: {image_id}')
        except Exception as e:
            raise Exception(f'unhandled exception: {e}')

        method = getattr(Image, method_name)

        return method(ee.Image(image_id), **kwargs)

    @classmethod
    def from_landsat_c2_sr(cls, sr_image, cloudmask_args={}, **kwargs):
        """Returns a SSEBop Image instance from a Landsat C02 level 2 (SR) image

        Parameters
        ----------
        sr_image : ee.Image, str
            A raw Landsat Collection 2 level 2 (SR) SR image or image ID.
        cloudmask_args : dict
            keyword arguments to pass through to cloud mask function.
        kwargs : dict
            Keyword arguments to pass through to Image init function.
            c2_lst_correct : boolean, optional
                Apply the Landsat Collection 2 LST emissivity correction.

        Returns
        -------
        Image

        """
        sr_image = ee.Image(sr_image)

        # Use the SPACECRAFT_ID property identify each Landsat type
        spacecraft_id = ee.String(sr_image.get('SPACECRAFT_ID'))

        # Rename bands to generic names
        # Include QA_RADSAT and SR_CLOUD_QA bands to apply additional cloud masking
        #   in openet.core.common.landsat_c2_sr_cloud_mask()
        input_bands = ee.Dictionary({
            'LANDSAT_4': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7',
                          'ST_B6', 'QA_PIXEL', 'QA_RADSAT'],
            'LANDSAT_5': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7',
                          'ST_B6', 'QA_PIXEL', 'QA_RADSAT'],
            'LANDSAT_7': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7',
                          'ST_B6', 'QA_PIXEL', 'QA_RADSAT'],
            'LANDSAT_8': ['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7',
                          'ST_B10', 'QA_PIXEL', 'QA_RADSAT'],
            'LANDSAT_9': ['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7',
                          'ST_B10', 'QA_PIXEL', 'QA_RADSAT'],
        })
        output_bands = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2',
                        'lst', 'QA_PIXEL', 'QA_RADSAT']
        band_scale = [0.0000275, 0.0000275, 0.0000275, 0.0000275, 0.0000275, 0.0000275,
                      0.00341802, 1, 1]
        band_offset = [-0.2, -0.2, -0.2, -0.2, -0.2, -0.2, 149.0, 0, 0]
        prep_image = (
            sr_image.select(input_bands.get(spacecraft_id), output_bands)
            .multiply(band_scale).add(band_offset)
        )

        # Default the cloudmask flags to True if they were not
        # Eventually these will probably all default to True in openet.core
        if 'cirrus_flag' not in cloudmask_args.keys():
            cloudmask_args['cirrus_flag'] = True
        if 'dilate_flag' not in cloudmask_args.keys():
            cloudmask_args['dilate_flag'] = True
        if 'shadow_flag' not in cloudmask_args.keys():
            cloudmask_args['shadow_flag'] = True
        if 'snow_flag' not in cloudmask_args.keys():
            cloudmask_args['snow_flag'] = True
        if 'cloud_score_flag' not in cloudmask_args.keys():
            cloudmask_args['cloud_score_flag'] = False
        if 'cloud_score_pct' not in cloudmask_args.keys():
            cloudmask_args['cloud_score_pct'] = 100
        if 'filter_flag' not in cloudmask_args.keys():
            cloudmask_args['filter_flag'] = False
        if 'saturated_flag' not in cloudmask_args.keys():
            cloudmask_args['saturated_flag'] = False

        cloud_mask = openet.core.common.landsat_c2_sr_cloud_mask(sr_image, **cloudmask_args)

        if 'c2_lst_correct' in kwargs.keys():
            assert isinstance(kwargs['c2_lst_correct'], bool), "selection type must be a boolean"
            # Remove from kwargs since it is not a valid argument for Image init
            c2_lst_correct = kwargs.pop('c2_lst_correct')
        else:
            c2_lst_correct = cls._C2_LST_CORRECT

        if c2_lst_correct:
            lst = openet.core.common.landsat_c2_sr_lst_correct(sr_image, landsat.ndvi(prep_image))
        else:
            lst = prep_image.select(['lst'])

        # Build the input image
        input_image = ee.Image([
            lst,
            landsat.ndvi(prep_image),
            landsat.ndwi(prep_image),
            landsat.landsat_c2_qa_water_mask(prep_image),
        ])

        # Apply the cloud mask and add properties
        input_image = (
            input_image
            .updateMask(cloud_mask)
            .set({'system:index': sr_image.get('system:index'),
                  'system:time_start': sr_image.get('system:time_start'),
                  'system:id': sr_image.get('system:id'),
            })
        )

        # Instantiate the class
        return cls(input_image, **kwargs)

    @lazy_property
    def tcorr_image(self):
        """Compute the scene wide Tcorr for the current image

        Returns
        -------
        ee.Image of Tcorr values

        """
        lst = ee.Image(self.lst)
        ndvi = ee.Image(self.ndvi)
        tmax = ee.Image(self.tmax)

        # Compute Tcorr
        tcorr = lst.divide(tmax)

        # Adjust NDVI
        ndvi_threshold = 0.85
        # Changed for tcorr at 1000m resolution also includes making NDVI more 'strict'
        # ndvi_threshold = 0.75

        # Select high NDVI pixels that are also surrounded by high NDVI
        ndvi_smooth_mask = (
            ndvi.focal_mean(radius=90, units='meters')
            .reproject(crs=self.crs, crsTransform=self.transform)
            .gte(ndvi_threshold)
        )
        ndvi_buffer_mask = (
            ndvi.gte(ndvi_threshold)
            .reduceNeighborhood(reducer=ee.Reducer.min(),
                                kernel=ee.Kernel.square(radius=60, units='meters'))
        )

        # Remove low LST and low NDVI
        tcorr_mask = lst.gt(270).And(ndvi_smooth_mask).And(ndvi_buffer_mask)

        return tcorr.updateMask(tcorr_mask).rename(['tcorr'])\
            .set({'system:index': self._index,
                  'system:time_start': self._time_start,
                  'tmax_source': tmax.get('tmax_source'),
                  'tmax_version': tmax.get('tmax_version')})

    @lazy_property
    def tcorr_FANO(self):
        """Compute the scene wide Tcorr for the current image adjusting tcorr
            temps based on NDVI thresholds to simulate true cold cfactor

        FANO: Forcing And Normalizing Operation

        Returns
        -------
        ee.Image of Tcorr values

        """
        coarse_transform = [1000, 0, 15, 0, -1000, 15]
        coarse_transform100 = [100000, 0, 15, 0, -100000, 15]
        dt_coeff = 0.125
        high_ndvi_threshold = 0.9
        water_pct = 50
        # max pixels argument for .reduceResolution()
        m_pixels = 65535

        lst = ee.Image(self.lst)
        ndvi = ee.Image(self.ndvi)
        tmax = ee.Image(self.tmax)
        dt = ee.Image(self.dt)

        # Setting NDVI to negative values where Landsat QA Pixel detects water.
        # TODO: We may want to switch "qa_watermask" to "not_water_mask.eq(0)"
        qa_watermask = ee.Image(self.qa_water_mask)
        ndvi = ndvi.where(qa_watermask.eq(1).And(ndvi.gt(0)), ndvi.multiply(-1))

        # Mask with not_water pixels set to 1 and other (likely water) pixels set to 0
        not_water_mask = self.tcorr_not_water_mask

        # Count not-water pixels and the total number of pixels
        # TODO: Rename "watermask_coarse_count" here to "not_water_pixels_count"
        watermask_coarse_count = (
            self.qa_water_mask.updateMask(not_water_mask)
            .reduceResolution(ee.Reducer.count(), False, m_pixels)
            .reproject(self.crs, coarse_transform)
            .updateMask(1).select([0], ['count'])
        )

        # TODO: Maybe chance ndvi to self.qa_water_mask?
        total_pixels_count = (
            ndvi
            .reduceResolution(ee.Reducer.count(), False, m_pixels)
            .reproject(self.crs, coarse_transform)
            .updateMask(1).select([0], ['count'])
        )

        # Doing a layering mosaic check to fill any remaining Null watermask coarse pixels with valid mask data.
        #   This can happen if the reduceResolution count contained exclusively water pixels from 30 meters.
        watermask_coarse_count = (
            ee.Image([watermask_coarse_count, total_pixels_count.multiply(0).add(1)])
            .reduce(ee.Reducer.firstNonNull())
        )

        percentage_bad = watermask_coarse_count.divide(total_pixels_count)
        pct_value = (1 - (water_pct / 100))
        wet_region_mask_5km = percentage_bad.lte(pct_value)

        ndvi_avg_masked = (
            ndvi
            .updateMask(not_water_mask)
            .reduceResolution(ee.Reducer.mean(), False, m_pixels)
            .reproject(self.crs, coarse_transform)
        )
        ndvi_avg_masked100 = (
            ndvi
            .updateMask(not_water_mask)
            .reduceResolution(ee.Reducer.mean(), True, m_pixels)
            .reproject(self.crs, coarse_transform100)
        )
        ndvi_avg_unmasked = (
            ndvi
            .reduceResolution(ee.Reducer.mean(), False, m_pixels)
            .reproject(self.crs, coarse_transform)
            .updateMask(1)
        )
        lst_avg_masked = (
            lst
            .updateMask(not_water_mask)
            .reduceResolution(ee.Reducer.mean(), False, m_pixels)
            .reproject(self.crs, coarse_transform)
        )
        lst_avg_masked100 = (
            lst
            .updateMask(not_water_mask)
            .reduceResolution(ee.Reducer.mean(), True, m_pixels)
            .reproject(self.crs, coarse_transform100)
        )
        lst_avg_unmasked = (
            lst
            .reduceResolution(ee.Reducer.mean(), False, m_pixels)
            .reproject(self.crs, coarse_transform)
            .updateMask(1)
        )

        # Here we don't need the reproject.reduce.reproject sandwich bc these are coarse data-sets
        dt_avg = dt.reproject(self.crs, coarse_transform)
        dt_avg100 = dt.reproject(self.crs, coarse_transform100).updateMask(1)
        tmax_avg = tmax.reproject(self.crs, coarse_transform)

        # FANO expression as a function of dT, calculated at the coarse resolution(s)
        Tc_warm = lst_avg_masked.expression(
            '(lst - (dt_coeff * dt * (ndvi_threshold - ndvi) * 10))',
            {
                'dt_coeff': dt_coeff, 'ndvi_threshold': high_ndvi_threshold,
                'ndvi': ndvi_avg_masked, 'dt': dt_avg, 'lst': lst_avg_masked,
            }
        )

        Tc_warm100 = lst_avg_masked100.expression(
            '(lst - (dt_coeff * dt * (ndvi_threshold - ndvi) * 10))',
            {
                'dt_coeff': dt_coeff, 'ndvi_threshold': high_ndvi_threshold,
                'ndvi': ndvi_avg_masked100, 'dt': dt_avg100, 'lst': lst_avg_masked100,
            }
        )

        # In places where NDVI is really high, use the masked original lst at those places.
        # In places where NDVI is really low (water) use the unmasked original lst.
        # Everywhere else, use the FANO adjusted  Tc_warm, ignoring masked water pixels.
        # In places where there is too much land covered by water 10% or greater,
        #   use a FANO adjusted Tc_warm from a coarser resolution (100km) that ignored masked water pixels.
        Tc_cold = (
            lst_avg_unmasked
            .where((ndvi_avg_masked.gte(0).And(ndvi_avg_masked.lte(high_ndvi_threshold))), Tc_warm)
            .where(ndvi_avg_masked.gt(high_ndvi_threshold), lst_avg_masked)
            .where(wet_region_mask_5km, Tc_warm100)
            .where(ndvi_avg_unmasked.lt(0), Tc_warm100)
        )

        c_factor = Tc_cold.divide(tmax_avg)

        # bilinearly smooth the gridded c factor
        c_factor_bilinear = c_factor.resample('bilinear')

        return c_factor_bilinear.rename(['tcorr'])\
            .set({'system:index': self._index,
                  'system:time_start': self._time_start,
                  'tmax_source': tmax.get('tmax_source'),
                  'tmax_version': tmax.get('tmax_version')})

    @lazy_property
    def tcorr_stats(self):
        """Compute the Tcorr 2.5 percentile and count statistics

        Returns
        -------
        dictionary

        """
        return ee.Image(self.tcorr_image).reduceRegion(
            reducer=ee.Reducer.percentile([2.5], outputNames=['value'])
                .combine(ee.Reducer.count(), '', True),
            crs=self.crs,
            crsTransform=self.transform,
            geometry=self.image.geometry().buffer(1000),
            bestEffort=False,
            maxPixels=2*10000*10000,
            tileScale=1,
        )
