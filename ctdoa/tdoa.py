import numpy as np
import logging
import os
from datetime import datetime
from scipy.signal import bessel,sosfilt, windows
from numpy.fft import fft, ifft

class TDOA:
    def __init__(self, log_directory="", poziom=logging.ERROR):
        self.typ = 'ps'
        self.vel_sound = 1500
        self.target_rms = 1.0
        self.threshold_percent=99
        self.fs=1
        #self.interp_factor=1        

        # Jeśli log_directory jest puste lub nie zostało przekazane, przypisz bieżący katalog roboczy
        self.dir_log = log_directory if log_directory else os.getcwd()  # Przypisanie domyślne


        # Generowanie nazwy pliku logu z datą i czasem
        current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_filename = f"LOG_TDOA_{current_time}.log"

        # Tworzenie katalogu logów, jeśli nie istnieje
        if not os.path.exists(self.dir_log):
            os.makedirs(self.dir_log)

        # Pełna ścieżka do pliku logów
        log_path = os.path.join(self.dir_log, log_filename)

        # Konfiguracja loggera
        logging.basicConfig(
            filename=log_path,
            level=poziom,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            encoding="utf-8"
        )
        self.log_file = log_path  # Zapisujemy ścieżkę pliku logów w razie potrzeby

    ######## METODY POMOCNICZE ##################################################
    # 
    # Funkcja do sprawdzania poprawności sygnału
    def check_signal(self, signal, name, step):
        if np.any(np.isnan(signal)) or np.any(np.isinf(signal)):
            raise ValueError(f"Sygnał {name} zawiera NaN lub Inf w kroku: {step}.")
        if np.all(signal == 0):
            raise ValueError(f"Sygnał {name} jest całkowicie zerowy w kroku: {step}.")

    # Funkcja do filtrowania sygnału
    def bessel_filter(self, s, lowcut, highcut, sample_rate, order):
        nyquist = 0.5 * sample_rate
        low = lowcut / nyquist
        high = highcut / nyquist
        # Projektowanie filtru Bessela w formacie sekcji drugiego rzędu (SOS)
        sos = bessel(N=order, Wn=[low, high], btype='band', analog=False, output='sos', norm='phase')
        return sosfilt(sos,s)

    # Funkcja do obcinania wartości odstających
    def clip_outliers(self,signal):
        threshold = np.percentile(np.abs(signal), self.threshold_percent)
        signal_clipped = np.clip(signal, -threshold, threshold)
        return signal_clipped

    # Funkcja do normalizacji RMS
    def normalize_rms(self, signal):
        rms_value = np.sqrt(np.mean(np.square(signal)))
        if rms_value > 0:
            normalized_signal = signal * (self.target_rms / rms_value)
        else:
            normalized_signal = signal
        return normalized_signal

    # Funkcja do przycinania sygnału
    def trim_signal(self, signal, sample_rate, start_time, end_time):
        start_sample = int(start_time * sample_rate)
        end_sample = int(end_time * sample_rate)
        trimmed_signal = signal[start_sample:end_sample]
        return trimmed_signal

    # Funkcja GCC-PHAT (Generalized Cross-Correlation with Phase Transform)
    def gcc_phat(self, sig, refsig, epsilon, fs):
        window = windows.hann(len(sig))
        sig = sig * window
        refsig = refsig * window

        n = sig.shape[0] + refsig.shape[0]
        SIG = fft(sig, n=n)
        REFSIG = fft(refsig, n=n)

        #epsilon = 1e-6
        abs_REF = np.abs(REFSIG)
        valid_indices = abs_REF > epsilon
        R = np.zeros_like(SIG)

        R[valid_indices] = (SIG[valid_indices] * np.conj(REFSIG[valid_indices])) / abs_REF[valid_indices]

        cc = np.real(ifft(R))
        max_shift = int(n / 2)
        cc = np.concatenate((cc[-max_shift:], cc[:max_shift]))

        lags = np.arange(-max_shift, max_shift) / float(fs)
        #interp_lags = np.linspace(lags[0], lags[-1], len(lags) * self.interp_factor)

        #f_interp = interp1d(lags, cc, kind='cubic')
        #cc_interp = f_interp(interp_lags)

        #shift = np.argmax(np.abs(cc_interp))
        shift = np.argmax(np.abs(cc))
        #tdoa = interp_lags[shift]
        tdoa = lags[shift]

        return tdoa #, cc_interp, interp_lags


    # GŁÓWNA METODA       
    # Metoda do wyznaczania TDOA
    def wyznaczTDOA(self, s1, s2, fs1, fs2, epsilon, sigma, window, overlap, lowcut, highcut):
        # Sprawdzenie sygnałów
        if fs1 != fs2:
            logging.error("Różne częstotliwości próbkowania obu sygnałów.")
            return
        if s1.shape == s2.shape:
            pass
        else:
            logging.error("Wektory s1 i s2 mają różne wielkości.")
        
        try:
            self.check_signal(s1,"s1","przed przetwarzaniem")
            self.check_signal(s2,"s2","przed przetwarzaniem")
        except ValueError as e:
            logging.error(str(e))
            return

        filtered_s1 = self.bessel_filter(s1, lowcut, highcut, fs1, order=4)
        filtered_s2 = self.bessel_filter(s2, lowcut, highcut, fs2, order=4)

        try:
            self.check_signal(filtered_s1, "s1","po filtracji")
            self.check_signal(filtered_s2, "s2","po filtracji")
        except ValueError as e:
            logging.error(str(e))
            return

        clipped_s1 = self.clip_outliers(filtered_s1)
        clipped_s2 = self.clip_outliers(filtered_s2)

        try:
            self.check_signal(clipped_s1, "s1","po usunięciu wartości odstających")
            self.check_signal(clipped_s2, "s2","po usunięciu wartości odstających")
        except ValueError as e:
            logging.error(str(e))
            return
        
        normalized_s1 = self.normalize_rms(clipped_s1)
        normalized_s2 = self.normalize_rms(clipped_s2)

        try:
            self.check_signal(normalized_s1, "s1","po normalizacji")
            self.check_signal(normalized_s2, "s2","po normalizacji")
        except ValueError as e:
            logging.error(str(e))
            return

        current_time = 0
        window_step = window * (1 - overlap)

        time_diffs = []
        tdoa_res = []

        total_duration = min(len(normalized_s1), len(normalized_s2)) / fs1

        while current_time + window <= total_duration:
            s1_window = self.trim_signal(normalized_s1, fs1, current_time, current_time + window)
            s2_window = self.trim_signal(normalized_s2, fs2, current_time, current_time + window)

            #tdoa, cc_interp, interp_lags = self.gcc_phat(s1_window, s2_window, epsilon, fs1)
            tdoa = self.gcc_phat(s1_window, s2_window, epsilon, fs1)

            window_center_time = current_time + window / 2

            time_diffs.append(window_center_time)
            tdoa_res.append(tdoa * self.vel_sound)
            current_time += window_step
        
        logging.info(f"Wyniki TDOA: {tdoa_res}")
        return tdoa_res


