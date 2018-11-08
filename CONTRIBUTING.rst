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
