import numpy

def compute_tdoa_1hz(
        s1: numpy.ndarray,
        s2: numpy.ndarray,
        fs: int,
        c: int,
        epsilon: float,
        sigma: float,
        window_sec: float,
        window_jump_sec: float,
        lowcut: int,
        highcut: int,
    ) -> list[int]:  
    """
    Standalone:
    Zwraca TDOA w metrach z próbkowaniem 1 Hz (numpy.array).

    Parametry:
    s1, s2          - sygnały 1D (numpy array-like),
    fs              - częstotliwość próbkowania [Hz],
    c               - prędkość dźwięku [m/s],
    epsilon         - próg dla amplitudy widma,
    sigma           - ile std do detekcji outlierów,
    window_sec      - długość okna w sekundach,
    window_jump_sec - krok przesuwania okna w sekundach,
    lowcut, highcut - pasmo filtru  [Hz],
    """
    ...
    


