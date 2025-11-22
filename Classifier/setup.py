# -*- coding: utf-8 -*-
"""
Created on Fri Apr 18 13:45:55 2025

@author: stann
"""
from setuptools import setup
from Cython.Build import cythonize

setup(
    ext_modules=cythonize("classifier.pyx", language_level=3)
    )
