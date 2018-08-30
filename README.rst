===============
OpenET - SSEBop
===============

|version| |build|

This repository provides an Earth Engine Python API based implementation of the SSEBop ET model.

Installation
============

To install the OpenET SSEBop python module:

.. code-block:: console

    pip install openet-ssebop

Dependencies
============

Modules needed to run the model:

 * `earthengine-api <https://github.com/google/earthengine-api>`__

Modules needed to run the test suite:

 * `pytest <https://docs.pytest.org/en/latest/>`__

Running Testing
===============

.. code-block:: console

    python -m pytest

Namespace Packages
==================

Each OpenET model should be stored in the "openet" folder (namespace).  The benefit of the namespace package is that each ET model can be tracked in separate repositories but called as a "dot" submodule of the main openet module,

.. code-block:: console

    import openet.ssebop as ssebop

.. |build| image:: https://travis-ci.org/Open-ET/openet-ssebop.svg?branch=master
   :alt: Build status
   :target: https://travis-ci.org/Open-ET/openet-ssebop
.. |version| image:: https://badge.fury.io/py/openet-ssebop.svg
   :alt: Latest version on PyPI
   :target: https://badge.fury.io/py/openet-ssebop