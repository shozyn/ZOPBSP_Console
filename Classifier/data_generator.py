# -*- coding: utf-8 -*-
"""
Created on Sat Mar 29 13:50:45 2025

@author: stann273
"""
import csv
import numpy as np
import torch

def get_data(file_path):
    with open(file_path, 'r') as f_signal:
        reader_signal = csv.reader(f_signal)
        data_signal = list(reader_signal)
        data_array = np.array(data_signal, dtype=np.float32)
        if data_array.shape[0] > 0 and data_array.shape[1] > 7500:
            data_array = data_array[0,:-1]
            #return torch.from_numpy(data_array).float()
            return data_array

