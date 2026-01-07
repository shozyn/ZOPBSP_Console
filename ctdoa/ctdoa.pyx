import numpy as np
cimport numpy as np
import logging
from datetime import datetime
import os
from libc.math cimport sqrt, fabs
from scipy.signal import bessel, sosfilt, windows
from numpy.fft import fft, ifft

cdef class TDOA:
    
    cdef public double vel_sound
    cdef double target_rms
    cdef double threshold_percent
    cdef public str log_file
    cdef public str dir_log
    

    def __init__(self, str log_directory="", poziom=logging.ERROR, double vel_sound=1500.0, double threshold_percent=99.0, double target_rms=1.0):
        
        """
        Inicjalizacja klasy TDOA.
        """
        self.vel_sound = vel_sound
        self.threshold_percent = threshold_percent
        self.target_rms = target_rms

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
    cpdef check_signal(self, np.ndarray[np.float64_t, ndim=1] signal, str name, str step):
        if np.any(np.isnan(signal)) or np.any(np.isinf(signal)):
            raise ValueError(f"Sygnał {name} zawiera NaN lub Inf w kroku: {step}.")
        if np.all(signal == 0):
            raise ValueError(f"Sygnał {name} jest całkowicie zerowy w kroku: {step}.")

    cpdef np.ndarray[np.float64_t, ndim=1] bessel_filter(self, np.ndarray[np.float64_t, ndim=1] s, 
                                                         double lowcut, double highcut, double sample_rate, int order):
        """
        Filtr Bessela dla przetwarzania sygnału.
        """
        cdef double nyquist = 0.5 * sample_rate
        cdef double low = lowcut / nyquist
        cdef double high = highcut / nyquist
        sos = bessel(N=order, Wn=[low, high], btype='band', analog=False, output='sos', norm='phase')
        return sosfilt(sos, s)

    cpdef np.ndarray[np.float64_t, ndim=1] clip_outliers(self, np.ndarray[np.float64_t, ndim=1] signal):
        """
        Obcinanie wartości odstających w sygnale.
        """
        cdef double threshold = np.percentile(np.abs(signal), self.threshold_percent)
        return np.clip(signal, -threshold, threshold)

    cpdef np.ndarray[np.float64_t, ndim=1] normalize_rms(self, np.ndarray[np.float64_t, ndim=1] signal):
        """
        Normalizacja RMS dla sygnału.
        """
        cdef double rms_value = sqrt(np.mean(np.square(signal)))
        if rms_value > 0:
            return signal * (self.target_rms / rms_value)
        return signal

    cpdef np.ndarray[np.float64_t, ndim=1] trim_signal(self, np.ndarray[np.float64_t, ndim=1] signal, 
                                                       double sample_rate, double start_time, double end_time):
        """
        Przycinanie sygnału do zadanego zakresu czasowego.
        """
        cdef int start_sample = int(start_time * sample_rate)
        cdef int end_sample = int(end_time * sample_rate)
        return signal[start_sample:end_sample]

    cpdef double gcc_phat(self, np.ndarray[np.float64_t, ndim=1] sig, 
                          np.ndarray[np.float64_t, ndim=1] refsig, double epsilon, double fs):
        """
        Algorytm GCC-PHAT do estymacji TDOA.
        """
        cdef int i, n
        cdef np.ndarray[np.float64_t, ndim=1] window = windows.hann(sig.shape[0])
        sig *= window
        refsig *= window

        n = sig.shape[0] + refsig.shape[0]
        SIG = fft(sig, n=n)
        REFSIG = fft(refsig, n=n)

        cdef np.ndarray[np.float64_t, ndim=1] abs_REF = np.abs(REFSIG)
        valid_indices = abs_REF > epsilon
        cdef np.ndarray[np.complex128_t, ndim=1] R = np.zeros_like(SIG, dtype=np.complex128)

        R[valid_indices] = (SIG[valid_indices] * np.conj(REFSIG[valid_indices])) / abs_REF[valid_indices]

        cdef np.ndarray[np.float64_t, ndim=1] cc = np.real(ifft(R))
        cdef int max_shift = int(n / 2)
        cc = np.concatenate((cc[-max_shift:], cc[:max_shift]))

        cdef np.ndarray[np.float64_t, ndim=1] lags = np.arange(-max_shift, max_shift) / float(fs)

        cdef int shift = np.argmax(np.abs(cc))
        cdef double tdoa = lags[shift]

        return tdoa

    cpdef np.ndarray[np.float64_t, ndim=1] wyznaczTDOA(self, 
                                                        np.ndarray[np.float64_t, ndim=1] s1, 
                                                        np.ndarray[np.float64_t, ndim=1] s2, 
                                                        double fs1, double fs2, 
                                                        double epsilon, double sigma, 
                                                        double window, double overlap, 
                                                        double lowcut, double highcut):
        """
        Obliczanie różnic czasu dojścia (TDOA) między dwoma sygnałami.
        """
        # Sprawdzenie sygnałów
        if fs1 != fs2:
            logging.error("Różne częstotliwości próbkowania obu sygnałów.")
            return
        #if s1.shape == s2.shape:
        #    pass
        #else:
        #    logging.error("Wektory s1 i s2 mają różne wielkości.")
        
        try:
            self.check_signal(s1,"s1","przed przetwarzaniem")
            self.check_signal(s2,"s2","przed przetwarzaniem")
        except ValueError as e:
            logging.error(str(e))
            return

        cdef np.ndarray[np.float64_t, ndim=1] filtered_s1 = self.bessel_filter(s1, lowcut, highcut, fs1, order=4)
        cdef np.ndarray[np.float64_t, ndim=1] filtered_s2 = self.bessel_filter(s2, lowcut, highcut, fs2, order=4)

        try:
            self.check_signal(filtered_s1, "s1","po filtracji")
            self.check_signal(filtered_s2, "s2","po filtracji")
        except ValueError as e:
            logging.error(str(e))
            return

        cdef np.ndarray[np.float64_t, ndim=1] clipped_s1 = self.clip_outliers(filtered_s1)
        cdef np.ndarray[np.float64_t, ndim=1] clipped_s2 = self.clip_outliers(filtered_s2)

        try:
            self.check_signal(clipped_s1, "s1","po usunięciu wartości odstających")
            self.check_signal(clipped_s2, "s2","po usunięciu wartości odstających")
        except ValueError as e:
            logging.error(str(e))
            return

        cdef np.ndarray[np.float64_t, ndim=1] normalized_s1 = self.normalize_rms(clipped_s1)
        cdef np.ndarray[np.float64_t, ndim=1] normalized_s2 = self.normalize_rms(clipped_s2)

        try:
            self.check_signal(normalized_s1, "s1","po normalizacji")
            self.check_signal(normalized_s2, "s2","po normalizacji")
        except ValueError as e:
            logging.error(str(e))
            return

        cdef double current_time = 0
        cdef double window_step = window * (1 - overlap)

        cdef double total_duration = min(len(normalized_s1), len(normalized_s2)) / fs1

        cdef np.ndarray[np.float64_t, ndim=1] s1_window
        cdef np.ndarray[np.float64_t, ndim=1] s2_window
        cdef double tdoa_value

        cdef list tdoa_res = []        

        while current_time + window <= total_duration:
            s1_window = self.trim_signal(normalized_s1, fs1, current_time, current_time + window)
            s2_window = self.trim_signal(normalized_s2, fs2, current_time, current_time + window)

            tdoa_value = self.gcc_phat(s1_window, s2_window, epsilon, fs1)

            tdoa_res.append(tdoa_value * self.vel_sound)
            current_time += window_step

        logging.info(f"Wyniki TDOA: {tdoa_res}")
        return np.array(tdoa_res, dtype=np.float64)
