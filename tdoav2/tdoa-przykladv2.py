import numpy as np
from scipy.io import wavfile
import time
import logging
import os
from datetime import datetime
#from tdoav2 import TDOA          #klasa TDOA w Python
from ctdoav2 import TDOA          #klasa TDOA w Cython
import re
from collections import defaultdict
from pathlib import Path
import wave
#
epsilon = float(1e-6)
sigma = float(2)
window = float(2)
overlap = float(0.5)
lowcut = float(20)
highcut = float(5000)
c = 1461


####### Ustawienia dla logowania #########################
dir_log = "c:\Projekty\TDOA"
if dir_log:
    pass
else: 
    dir_log = os.getcwd() # Przypisanie aktualnego katalogu
    
# Generowanie nazwy pliku logu z datą i czasem
current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_filename = f"LOG_TDOA_{current_time}.log"

# Tworzenie katalogu logów, jeśli nie istnieje
if not os.path.exists(dir_log):
    os.makedirs(dir_log)

# Pełna ścieżka do pliku logów
log_path = os.path.join(dir_log, log_filename)

# Konfiguracja loggera
logging.basicConfig(
            filename=log_path,
            level=logging.ERROR,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            encoding="utf-8"
        )
log_file = log_path  # Zapisujemy ścieżkę pliku logów w razie potrzeby
#####################################################################

### Znalezienie plików wav do odczytu ###################
# Ścieżka do katalogu
folder = Path(os.getcwd()) # Przypisanie aktualnego katalogu

# Wzorzec np. mic1_20230408_120000.wav
wzorzec = re.compile(r'.*?_(\d{8}_\d{6})\.wav$')

# Grupujemy pliki po dacie i czasie
pliki_po_dacie_czasie = defaultdict(list)

for plik in folder.glob("*.wav"):
    dopasowanie = wzorzec.match(plik.name)
    if dopasowanie:
        klucz = dopasowanie.group(1)  # np. 20230408_120000
        pliki_po_dacie_czasie[klucz].append(plik)

# Przetwarzanie parami
for klucz, pliki in pliki_po_dacie_czasie.items():
    if len(pliki) >= 2:
        plik1, plik2 = pliki[:2]
        print(f"Przetwarzam pliki z {klucz}:")
        print(f" - {plik1.name}")
        print(f" - {plik2.name}")

        # Możesz tu dodać dalsze przetwarzanie
        with wave.open(str(plik1), 'rb') as w1, wave.open(str(plik2), 'rb') as w2:
            print(f"    {plik1.name}: {w1.getnchannels()} kanałów, {w1.getframerate()} Hz")
            print(f"    {plik2.name}: {w2.getnchannels()} kanałów, {w2.getframerate()} Hz")
    else:
        print(f"Pominięto {klucz} – mniej niż dwa pliki.")


########## Odczyt ##############################
fs1, data1 = wavfile.read("RBW6675_20240918_141600.wav")
fs2, data2 = wavfile.read("RBW6676_20240918_141600.wav")

sample_duration = 10

blad = 1    #celowy błąd dla sprawdzenia logowania
s1 = np.array(data1[0:sample_duration*fs1], dtype=np.float64)
s2 = np.array(data2[0:(sample_duration+blad)*fs2], dtype=np.float64)


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

#Inicjacja obiektu TDOA
tdoa1 = TDOA()


#Wyznaczenie TDOA dla próbek o zadanej długości, szerokości okna i stopnia nałożenia
t1 = time.time()
tdoa_res = tdoa1.wyznaczTDOA(s1, s2, fs1, c, epsilon, sigma, window, overlap, lowcut, highcut)
t2 = time.time()

print(f"Czas wykonywania się metody 'wyznaczTDOA' dla próbek o czasie {sample_duration} s równy {t2-t1} s")
print("  ")
print(f"Plik logów: {log_file}")
print(" ")
print(f"Wyniki TDOA: {tdoa_res}")