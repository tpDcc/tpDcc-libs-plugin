#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
Module that contains general tests for tpDcc-libs-plugin
"""

from tpDcc.libs.plugin import __version__

import pytest


def test_version():
    assert __version__.get_version()
