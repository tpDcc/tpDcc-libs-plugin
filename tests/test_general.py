#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""
Module that contains general tests for tpDcc-libs-plugin
"""

from tpDcc.libs.plugin import __version__

from tpDcc.libs.unittests.core import unittestcase


class TestGeneral(unittestcase.UnitTestCase()):

    def test_version(self):
        assert __version__.get_version()

