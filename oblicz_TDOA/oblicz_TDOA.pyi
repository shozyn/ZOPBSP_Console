
import numpy as np

type Signal = np.NDarray[np.int]

def compute_tdoa_1hz(
    s1: Signal,
    s2: Signal,
    fs: int,
    c: float = 1470,
    epsilon: float= 0.001,
    sigma: float = 0.05,
    window_sec: float = 0.5,
    window_jump_sec: float = 0.5,
    lowcut: int = 100,
    highcut: int = 2000,
) -> list[float]:
    ...
