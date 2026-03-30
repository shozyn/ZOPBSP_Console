import numpy as np
from vmdpy import VMD
import logging
import math
from scipy.signal import resample_poly
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


BAND_EDGES = np.array([
    0, 500, 1000, 1500, 2000, 2500, 3000,
    3500, 4000, 4500, 5000, 5500, 6000, 6500,
    7000, 7500, 8000
], dtype=float)


def find_dominant_band_spectrum(imf_spectrum: np.ndarray,
                                freq_axis: np.ndarray,
                                band_edges: np.ndarray,
                                ignore_first_band: bool = False):

    power_spectrum = np.abs(imf_spectrum) ** 2
    num_bands = len(band_edges) - 1
    band_energy = np.zeros(num_bands)
    for b in range(num_bands):
        f_low, f_high = band_edges[b], band_edges[b + 1]
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
    alpha: float = 2456.6410054204975,
    tau: float = 0.0,
    K: int = 4,
    DC: int = 0,
    init: int = 1,
    tol: float = 0.00081,
    band_th: float = 357.9328,
    tot_th: float = 0.0,
    fr_len: float = 0.9857,
    fr_start: float = 0.0,
    ignore_1_band: bool = True,
    min_presence: float = 0.689,
) -> np.ndarray:

    if np.issubdtype(s_i_cut.dtype, np.integer):
        sig = s_i_cut.astype(float) / np.iinfo(s_i_cut.dtype).max
    else:
        sig = s_i_cut.astype(float)

    if sig.size < 2:
        return np.empty((0, 2), dtype=float)

    start_idx = int(fr_start * fs_i)
    if start_idx < 0:
        start_idx = 0
    if start_idx >= sig.size:
        return np.empty((0, 2), dtype=float)

    sig = sig[start_idx:]
    if sig.size < 2:
        return np.empty((0, 2), dtype=float)

    target_fs = 16_000
    fs_work = int(fs_i)

    if fs_work != target_fs:
        g = math.gcd(int(fs_work), int(target_fs))
        up = target_fs // g
        down = fs_work // g
        sig = resample_poly(sig, up=up, down=down)
        fs_work = target_fs

    if sig.size < 2:
        return np.empty((0, 2), dtype=float)

    fr_samp = int(round(fr_len * fs_work))
    if fr_samp < 2:
        return np.empty((0, 2), dtype=float)

    num_bands = len(BAND_EDGES) - 1
    band_counts = np.zeros(num_bands, dtype=int)
    frame_masks: list[int] = []
    n_used = 0

    n_frames = int(math.ceil(sig.size / fr_samp))
    for fr in range(n_frames):
        st = fr * fr_samp
        en = min((fr + 1) * fr_samp, sig.size)
        chunk = sig[st:en]

        if chunk.size < 2:
            continue
        n_used += 1

        try:
            u, u_hat, omega = VMD(
                chunk,
                alpha=alpha, tau=tau, K=K,
                DC=DC, init=init, tol=tol
            )
        except Exception:
            det_idxs = set()
        else:
            freq_axis = np.fft.rfftfreq(chunk.size, d=1 / fs_work)
            band_info = []
            for k in range(K):
                spectrum = np.fft.rfft(u[k, :])
                ign = (k == 0 and ignore_1_band)
                best_idx, band_energy = find_dominant_band_spectrum(
                    spectrum, freq_axis, BAND_EDGES, ignore_first_band=ign
                )
                best_lin = band_energy[best_idx]
                best_db = 10 * np.log10(best_lin) if best_lin > 0 else -np.inf
                tot_lin = np.sum(np.abs(spectrum) ** 2)
                tot_db = 10 * np.log10(tot_lin) if tot_lin > 0 else -np.inf
                if ign:
                    tot_db = -np.inf
                band_info.append((best_idx, band_energy, best_db, tot_db))

            det_idxs = detect_bands_imfs(
                band_info, BAND_EDGES,
                band_th=band_th, tot_th=tot_th
            )

        mask = 0
        for idx in det_idxs:
            if 0 <= idx < num_bands:
                band_counts[idx] += 1
                mask |= (1 << int(idx))
        frame_masks.append(mask)

    if n_used == 0:
        return np.empty((0, 2), dtype=float)

    ratio = float(min_presence)
    if ratio > 1.0:
        ratio = ratio / 100.0
    ratio = max(0.0, min(1.0, ratio))

    if ratio <= 0.0:
        thr_count = 1
    else:
        thr_count = int(math.ceil(ratio * n_used - 1e-12))
        thr_count = max(thr_count, 1)

    selected = [i for i, c in enumerate(band_counts) if c >= thr_count]
    det_ranges = [(BAND_EDGES[i], BAND_EDGES[i + 1]) for i in selected]
    det_arr = np.array(det_ranges, dtype=np.float32)
    return det_arr
