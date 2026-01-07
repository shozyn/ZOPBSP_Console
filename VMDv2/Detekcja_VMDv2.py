import numpy as np
from vmdpy import VMD
import logging
import time

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

BAND_EDGES = np.array([
    0, 10, 100, 500, 1000, 2000, 4000, 6000, 8000,
    10000, 12000, 14000, 16000, 18000, 20000, 30000,
    40000, 50000
], dtype=float)

def find_dominant_band_spectrum(imf_spectrum: np.ndarray,
                                freq_axis: np.ndarray,
                                band_edges: np.ndarray,
                                ignore_first_band: bool = False):

    power_spectrum = np.abs(imf_spectrum) ** 2
    num_bands = len(band_edges) - 1
    band_energy = np.zeros(num_bands)
    for b in range(num_bands):
        f_low, f_high = band_edges[b], band_edges[b+1]
        idx = np.where((freq_axis >= f_low) & (freq_axis < f_high))[0]
        band_energy[b] = np.sum(power_spectrum[idx])
    if ignore_first_band and num_bands > 0:
        band_energy[0] = -np.inf
    best_idx = int(np.argmax(band_energy))
    return best_idx, band_energy

def detect_bands_imfs(band_info: list,
                      band_edges: np.ndarray,
                      band_th: float = -10.0,
                      tot_th: float = -20.0):

    detected = set()
    for best_idx, _, best_db, tot_db in band_info:
        if best_db >= band_th or tot_db >= tot_th:
            detected.add(best_idx)
    return detected

def run_detection(
    s_i_cut: np.ndarray,
    fs_i: int,
    alpha: float = 2000.0,
    tau: float = 0.0,
    K: int = 5,
    DC: int = 0,
    init: int = 1,
    tol: float = 1e-8,
    band_th: float = -10.0,
    tot_th: float = -15.0,
    fr_len: float = 0.1,
    fr_start: float = 0.0,
    ignore_1_band: bool = True
) -> np.ndarray:

    sig = s_i_cut.astype(float) / np.iinfo(s_i_cut.dtype).max
    start_idx = int(fr_start * fs_i)
    end_idx = int((fr_start + fr_len) * fs_i)
    chunk = sig[start_idx:end_idx]
    if chunk.size < 2:
        logger.warning("Fragment sygnału zbyt krótki")
        return np.empty((0, 2), dtype=float)

    logger.info(f"Uruchamianie VMD: K={K}, alpha={alpha}, tau={tau}")
    u, u_hat, omega = VMD(
        chunk,
        alpha=alpha, tau=tau, K=K,
        DC=DC, init=init, tol=tol
    )

    freq_axis = np.fft.rfftfreq(chunk.size, d=1/fs_i)
    band_info = []
    for k in range(K):
        spectrum = np.fft.rfft(u[k, :])
        ign = (k == 0 and ignore_1_band)
        best_idx, band_energy = find_dominant_band_spectrum(
            spectrum, freq_axis, BAND_EDGES, ignore_first_band=ign
        )
        best_lin = band_energy[best_idx]
        best_db = 10*np.log10(best_lin) if best_lin>0 else -np.inf
        tot_lin = np.sum(np.abs(spectrum)**2)
        tot_db = 10*np.log10(tot_lin) if tot_lin>0 else -np.inf
        if ign:
            tot_db = -np.inf
        band_info.append((best_idx, band_energy, best_db, tot_db))

    det_idxs = detect_bands_imfs(band_info, BAND_EDGES,
                                 band_th=band_th, tot_th=tot_th)

    det_ranges = [
        (BAND_EDGES[i], BAND_EDGES[i+1]) for i in sorted(det_idxs)
    ]
    return np.array(det_ranges, dtype=float)
