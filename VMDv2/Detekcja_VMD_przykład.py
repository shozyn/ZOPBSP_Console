from Detekcja_VMDv2 import run_detection
import numpy as np
from vmdpy import VMD
import logging
import time


data = np.load("RBW6675_20240917_085600_segments.npz")
#Dane wejściowe
s_i_cut = data["s_6675_cut_59"]
fs_i = data["fs_6675"]

# Parametry
alpha = 2000
tau = 0.0
K = 5
DC = 0
init = 1
tol = 1e-8

band_th = -10.0
tot_th = -15.0

fr_len = 0.1
fr_start = 0
ignore_1_band = 1


det_VMD_i = run_detection(
    s_i_cut, fs_i,
    alpha, tau, K, DC, init, tol,
    band_th, tot_th,
    fr_len, fr_start, ignore_1_band
)
print(det_VMD_i)
