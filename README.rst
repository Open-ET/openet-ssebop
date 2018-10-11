===============
OpenET - SSEBop
===============

|version| |build|

This repository provides an Earth Engine Python API based implementation of the SSEBop ET model.

The Operational Simplified Surface Energy Balance (SSEBop) model computes daily total actual evapotranspiration (ETa) using land surface temperature (Ts), maximum air temperature (Ta) and reference ET (ETo).
The SSEBop model does not solve all the energy balance terms explicitly; rather, it defines the limiting conditions based on clear-sky net radiation balance principles.
This approach predefines unique sets of "hot/dry" and "cold/wet" limiting values for each pixel and is designed to reduce model operator errors when estimating ET routinely.

Basic SSEBop model architecture in Earth Engine:

![Diagram Version 1](https://raw.githubusercontent.com/Open-ET/openet-ssebop-beta/master/SSEBop_GEE_flow.PNG)

Input Collections
=================

Currently SSEBop ET can only be computed for Landsat Collection 1 TOA images.

Examples
========

Jupyter notebooks are provided in the "examples" folder that show various approaches for calling the OpenET SSEBop model.

Model Structure
===============

The SSEBop model is composed of two primary classes: Image() and Collection().

Image
-----

.. code-block:: console
    import openet.ssebop as ssebop

    landsat_img = ee.Image('LANDSAT/LC08/C01/T1_RT_TOA/LC08_044033_20170716')
    etf_img = ssebop.Image().from_landsat_c1_toa(landsat_img).etf

Collection
----------



Ancillary Datasets
==================

Maximum Daily Air Temperature (Tmax)
------------------------------------
The daily maximum air temperature (Tmax) is essential for establishing the maximum ET limit (cold boundary) as explained in Senay et al. (2017) 

Default Asset ID: projects/usgs-ssebop/tmax/topowx_median_v0

Land Surface Temperature
------------------------
Land Surface Temperature (LST) is currently calculated in the SSEBop approach from Landsat Top-of-Atmosphere images by including commonly used calibration steps and atmospheric correction techniques. These include calculations for: (1) spectral radiance conversion to the at-sensor brightness temperature; (2) atmospheric absorption and re-emission value; (3) surface emissivity; and (4) land surface temperature. For additional information, users can refer to section 3.2 of the Methodology here: http://www.sciencedirect.com/science/article/pii/S0034425715302650. 

(add equation graphic?)

dT
--
The SSEBop ET model uses dT as a predefined temperature difference between Thot and Tcold for each pixel.
In SSEBop formulation, hot and cold limits are defined on the same pixel; therefore, dT actually represents the vertical temperature difference between the surface temperature of a theoretical bare/dry condition of a given pixel and the air temperature at the canopy level of the same pixel as explained in Senay et al. (2013). The input dT is calculated under average-sky conditions and assumed not to change from year to year, but is unique for each day and location.


Default Asset ID: projects/usgs-ssebop/dt/daymet_median_v1_scene

Elevation
---------
The default elevation dataset is a custom SRTM based CONUS wide 1km resolution raster.

Default Asset ID: projects/usgs-ssebop/srtm_1km

The elevation parameter will accept any Earth Engine image.

Tcorr (C-factor)
----------------
In order to correspond the maximum air temperature with cold/wet limiting environmental conditions, the SSEBop model uses a correction coefficient (C-factor) uniquely calculated for each Landsat scene from well-watered/vegetated pixels. This temperature correction component is based on a ratio of Tmax and Land Surface Temperature (LST) that has passed through several conditions such as NDVI limits.

(add parameterization table here)

The Tcorr value is read from precomputed Earth Engine feature collections based on the Landsat scene ID (from the system:index property).  If the target Landsat scene ID is not found in the feature collection, a median monthly value for the WRS2 path/row is used.  If median monthly values have not been computed for the target path/row, a default value of 0.978 will be used.

The Tcorr is a function of the maximum air temperature dataset, so separate Tcorr collections have been generated for each of the following air temperature datasets: CIMIS, DAYMET, GRIDMET, TopoWX.  The data source of the Tcorr collection needs to match the data source of the air temperature.

The Tcorr collections were last updated through 2017 but will eventually be updated daily.

Default Asset IDs
Scene ID: projects/usgs-ssebop/tcorr/topowx_median_v0_scene
Monthly ID: projects/usgs-ssebop/tcorr/topowx_median_v0_monthly

Installation
============

The OpenET SSEBop python module can be installed via pip:

.. code-block:: console

    pip install openet-ssebop

Dependencies
============

Modules needed to run the model:

 * `earthengine-api <https://github.com/google/earthengine-api>`__
 * `openet <https://github.com/Open-ET/openet-core-beta>`__

Modules needed to run the test suite:

 * `pytest <https://docs.pytest.org/en/latest/>`__

Running Tests
=============

.. code-block:: console

    python -m pytest

OpenET Namespace Package
========================

Each OpenET model should be stored in the "openet" folder (namespace).  The benefit of the namespace package is that each ET model can be tracked in separate repositories but called as a "dot" submodule of the main openet module,

.. code-block:: console

    import openet.ssebop as ssebop


References
==========

 * `Senay et al., 2013 <http://onlinelibrary.wiley.com/doi/10.1111/jawr.12057/abstract>`__
 * `Senay et al., 2016 <http://www.sciencedirect.com/science/article/pii/S0034425715302650>`__

.. |build| image:: https://travis-ci.org/Open-ET/openet-ssebop-beta.svg?branch=master
   :alt: Build status
   :target: https://travis-ci.org/Open-ET/openet-ssebop-beta
.. |version| image:: https://badge.fury.io/py/openet-ssebop.svg
   :alt: Latest version on PyPI
   :target: https://badge.fury.io/py/openet-ssebop
