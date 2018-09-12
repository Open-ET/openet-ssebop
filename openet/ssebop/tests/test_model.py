import ee
import pytest

import openet.ssebop as ssebop


def test_ee_init():
    assert ee.Number(1).getInfo() == 1
