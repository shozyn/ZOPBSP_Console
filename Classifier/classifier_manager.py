# -*- coding: utf-8 -*-
"""
Created on Wed May 14 21:19:45 2025

@author: stann
"""

from classifier import Classifier

_classifier_cache = {}

def get_classifier(fs_i):
    if fs_i not in _classifier_cache:
        _classifier_cache[fs_i] = Classifier(fs_i)
    return _classifier_cache[fs_i]