#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Mar  2 19:26:56 2025

@author: sh
"""
import data_generator as dg
from AKA1A import AKA1A
s_i_cut = dg.get_data('C:\\Code\\ZOPBSP_25_05_11\\sensorData1.csv')
fs_i = 256000

pred_class, class_prob = AKA1A(s_i_cut, fs_i)
print(f"pred_class: {pred_class}")
print(f"class_prob: {class_prob}")

