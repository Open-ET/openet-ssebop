=============================
Contributing to OpenET SSEBop
=============================

Thank you for your interesting in support the OpenET SSEBop project.

Versioning
==========

The OpenET SSEBop project is currently in Beta and the version numbers will be "0.0.X" until a non-Beta release is made.

Coding Conventions
==================

OpenET SSEBop was developed for Python 3.6.  The code will likely work on other version of Python 3 but there are no plans to officialy support Python 2.7 at this time.

All code should follow the `PEP8
<https://www.python.org/dev/peps/pep-0008/>`__ style guide.

Docstrings should be written for all functions that follow the `NumPy docstring format <https://numpydoc.readthedocs.io/en/latest/format.html>`__.

Development
===========

Conda Environment
-----------------

For local application, development, and testing, the user is strongly encouraged to create a dedicated "openet" conda environment.

Create the conda environment:

.. code-block:: console

    conda create --name openet python=3.6

Activate the environment:

.. code-block:: console

    conda activate openet

Install additional Python modules using conda (and pip for modules not currently available via conda):

.. code-block:: console

    conda install earthengine-api oauth2client pytest
    pip install openet-core --no-deps

Updating OpenET Module
----------------------

While developing the "ssebop" module, pip can be used to quickly update the module in the "openet" environment if needed.

.. code-block:: console

    pip install . --no-deps

Testing
=======

PyTest
------

Testing is done using `pytest <https://docs.pytest.org/en/latest/>`__.

.. code-block:: console

    python -m pytest

Detailed testing results can be obtained using the "-v" and/or "-s" tags.

.. code-block:: console

    python -m pytest -v -s
