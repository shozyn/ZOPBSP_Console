"""
kalman.py

Simple 2D constant-velocity Kalman filter for smoothing the estimated object
track. State = [x, y, vx, vy] in metres / (metres per second), so process and
measurement noise are expressed in physical units.

Intended for an object moving at a roughly constant speed (here ~0.75-3 m/s):
keep the process (acceleration) noise small so the filter trusts the
constant-velocity model and smooths out the TDOA scatter, while still following
gentle turns.
"""

from __future__ import annotations

import numpy as np


class ConstantVelocityKalman2D:
    """
    Constant-velocity Kalman filter operating on planar metres.

    Parameters
    ----------
    process_std:
        Acceleration noise std [m/s^2]. Smaller -> smoother / more inertia.
    meas_std:
        Measurement position noise std [m]. Larger -> trust measurements less.
    max_gap_s:
        If the time since the last update exceeds this, the filter is
        reinitialised at the new measurement (e.g. after a long rejection gap).
    init_speed_std:
        Initial velocity uncertainty [m/s] (use the expected max speed).
    """

    def __init__(self, process_std: float = 0.2, meas_std: float = 15.0,
                 max_gap_s: float = 10.0, init_speed_std: float = 3.0):
        self.q = float(process_std)
        self.r = float(meas_std)
        self.max_gap_s = float(max_gap_s)
        self.init_speed_std = float(init_speed_std)
        self.reset()

    def reset(self) -> None:
        self.x = None   # 4x1 state
        self.P = None   # 4x4 covariance

    def _init_state(self, mx: float, my: float) -> None:
        self.x = np.array([[mx], [my], [0.0], [0.0]], dtype=float)
        self.P = np.diag([
            self.r ** 2, self.r ** 2,
            self.init_speed_std ** 2, self.init_speed_std ** 2,
        ]).astype(float)

    def update(self, mx: float, my: float, dt) -> tuple:
        """
        Feed a new measurement (mx, my) [m] separated by dt [s] from the
        previous one. Returns the filtered (x, y) [m].
        """
        if self.x is None or dt is None or dt <= 0 or dt > self.max_gap_s:
            self._init_state(mx, my)
            return float(self.x[0, 0]), float(self.x[1, 0])

        F = np.array([
            [1, 0, dt, 0],
            [0, 1, 0, dt],
            [0, 0, 1, 0],
            [0, 0, 0, 1],
        ], dtype=float)

        q = self.q ** 2
        Q = q * np.array([
            [dt ** 4 / 4, 0, dt ** 3 / 2, 0],
            [0, dt ** 4 / 4, 0, dt ** 3 / 2],
            [dt ** 3 / 2, 0, dt ** 2, 0],
            [0, dt ** 3 / 2, 0, dt ** 2],
        ], dtype=float)

        H = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
        R = (self.r ** 2) * np.eye(2)

        # Predict
        x_pred = F @ self.x
        P_pred = F @ self.P @ F.T + Q

        # Update
        z = np.array([[mx], [my]], dtype=float)
        y = z - H @ x_pred
        S = H @ P_pred @ H.T + R
        K = P_pred @ H.T @ np.linalg.inv(S)
        self.x = x_pred + K @ y
        self.P = (np.eye(4) - K @ H) @ P_pred

        return float(self.x[0, 0]), float(self.x[1, 0])

    def speed(self) -> float:
        """Current estimated speed [m/s] (0 if not initialised)."""
        if self.x is None:
            return 0.0
        return float(np.hypot(self.x[2, 0], self.x[3, 0]))
