import numpy as np
from scipy.io import wavfile
import time
import logging
#from tdoa import TDOA          #klasa TDOA w Python
from ctdoa import TDOA          #klasa TDOA w Cython

epsilon = float(1e-6)
sigma = float(2)
window = float(2)
overlap = float(0.5)
lowcut = float(20)
highcut = float(5000)
vel_sound = 1461

#file1 = "RBW6675_20240918_141600.wav"   #256kS 
#file2 = "RBW6676_20240918_141600.wav"   #256kS

file1 = "RBW6675_20240508_112400.wav"   #128kS
file2 = "RBW6676_20240508_112400.wav"   #128kS


fs1, data1 = wavfile.read(file1)
fs2, data2 = wavfile.read(file2)

#print(f"fs1: {fs1}, fs2: {fs2}")

sample_duration = 10

s1 = np.array(data1[0:sample_duration*fs1], dtype=np.float64)
s2 = np.array(data2[0:sample_duration*fs2], dtype=np.float64)


#Inicjacja obiektu TDOA
dir_log = "C:\\Projekty\\Logi\\"  #Bieżący katalog (Domyślny)
poziom = logging.INFO             #DEBUG, INFO, WARNING, ERROR (Domyślny), CRITICAL
tdoa1 = TDOA()
tdoa1.vel_sound = vel_sound       #1500 m/s (Domyślna)

#Wyznaczenie TDOA dla próbek o zadanej długości, szerokości okna i stopnia nałożenia
t1 = time.time()
tdoa_res = tdoa1.wyznaczTDOA(s1, s2, fs1, fs2, epsilon, sigma, window, overlap, lowcut, highcut)
t2 = time.time()

print(f"Czas wykonywania się metody 'wyznaczTDOA' dla próbek o czasie {sample_duration} s równy {t2-t1} s")
print("  ")
print(f"Plik logów: {tdoa1.log_file}")
print(" ")
print(f"Wyniki TDOA: {tdoa_res}")