import numpy as np
from Classifier.AKA1A import AKA1A
from Detekcja_VMDv3.Detekcja_VMDv3 import run_detection
from ctdoa.tdoa_cython import compute_tdoa_1hz
from calculation.tdoa_position_solver import position_estimation_TDOA_6

class AKA1AAlgorithm:
    """
    Single-channel classifier.
    run(data, fs) -> dict
    """
    def run(self, data, fs):
        pred_class, class_prob = AKA1A(data, fs)
        return {"pred_class": int(pred_class), "class_prob": class_prob.tolist()}


class VMDv2Algorithm:
    """
    Single-channel detection.
    """
    def __init__(self):
        self.params = {
            "alpha": 2000, "tau": 0.0, "K": 5, "DC": 0, "init": 1, "tol": 1e-8,
            "band_th": -10.0, "tot_th": -15.0,
            "fr_len": 0.1, "fr_start": 0, "ignore_1_band": 1
        }

    def run(self, data, fs):
        
        p = self.params
        det = run_detection(
            data, fs,
            p["alpha"], p["tau"], p["K"], p["DC"], p["init"], p["tol"],
            p["band_th"], p["tot_th"],
            p["fr_len"], p["fr_start"], p["ignore_1_band"]
        )
        return {"det_VMD": det, "params": dict(p)}


class TDOAAlgorithm:
    """
    Two-channel TDOA.
    """
    def __init__(self):
        #self.tdoa = TDOA()
        self.params = {
            "c": 1461.0,
            "epsilon": 0.055,
            "sigma": 0.1314,
            "window_sec": 0.85,
            "window_jump_sec": 0.23,
            "lowcut": 177,
            "highcut": 750.0,
        }

    def run(self, x1, x2, fs):
        p = self.params
        #self.tdoa.vel_sound = float(p["vel_sound"])

        res = compute_tdoa_1hz(
            x1, x2, fs, 
            int(p["c"]),
            float(p["epsilon"]),
            float(p["sigma"]),
            float(p["window_sec"]),
            float(p["window_jump_sec"]),
            int(p["lowcut"]),
            int(p["highcut"])
        )
        return {"tdoa": res, "params": dict(p)}


class TDOAPositionAlgorithm:
    """
    Position based on TDOA and Receivers' position.
    """
    def run(self, tdoa_result):

        H1 = np.matrix([[-200.0], [200.0], [-2.5]])
        H2 = np.matrix([[200.0], [200.0], [-2.5]])
        H3 = np.matrix([[200.0], [-200.0], [-2.5]])
        H4 = np.matrix([[-200.0], [-200.0], [-2.5]])

        OP = np.matrix([[70], [120], [-2.5]])

        Vd = 1500.0
        t1 = np.linalg.norm(OP - H1) / Vd
        t2 = np.linalg.norm(OP - H2) / Vd
        t3 = np.linalg.norm(OP - H3) / Vd
        t4 = np.linalg.norm(OP - H4) / Vd

        bt = 800
        dt12 = t1 - t2 + np.random.normal(0, bt) / 1000000.0
        dt13 = t1 - t3 + np.random.normal(0, bt) / 1000000.0
        dt14 = t1 - t4 + np.random.normal(0, bt) / 1000000.0
        dt23 = t2 - t3 + np.random.normal(0, bt) / 1000000.0
        dt24 = t2 - t4 + np.random.normal(0, bt) / 1000000.0
        dt34 = t3 - t4 + np.random.normal(0, bt) / 1000000.0

        dSH12 = dt12 * Vd
        dSH13 = dt13 * Vd
        dSH14 = dt14 * Vd
        dSH23 = dt23 * Vd
        dSH24 = dt24 * Vd
        dSH34 = dt34 * Vd

        B12 = 0.5
        B13 = 0.5
        B14 = 0.5
        B23 = 0.5
        B24 = 0.5
        B34 = 0.5

        Po = np.matrix([[0.0], [0.0], [-2.5]])

        return position_estimation_TDOA_6(
            Po, [H1, H2, H3, H4],
            dSH12, dSH13, dSH14, dSH23, dSH24, dSH34,
            B12, B13, B14, B23, B24, B34
        )