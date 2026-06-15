"""
tdoa_solver_3hydro.py

Closed-form 2D TDOA position estimator for EXACTLY 3 hydrophones (3 real pairs,
2 independent range differences), with an optional Gauss-Newton refinement that
uses only the 3 REAL pairs.

Motivation
----------
The production solver (tdoa_solver_30_11_2025 / the *_TDOA_6_* family) works on a
4-hydrophone / 6-pair scheme where the 4th hydrophone is synthesised at the
centroid of the real three, and the iteration is seeded at that centroid. In
weak 3-hydrophone geometry this introduces a pull toward the centre of the
triangle (and on a singular normal matrix it returns the centroid unchanged).

This module avoids both: it solves the genuine 3-receiver problem in closed form
(no virtual hydrophone, no centroid seed). The two hyperbolas of a 3-receiver
system intersect in up to two points; the redundant third pair (D23) is used to
pick the physically consistent one.

Sign convention (matches the existing pipeline / closure = D12 + D23 - D13):
    D12 = d1 - d2,  D13 = d1 - d3,  D23 = d2 - d3      [metres]
where di = |source - Hi|. All coordinates are planar metres (x, y).
"""

from __future__ import annotations

import numpy as np


def _solve_quadratic(A: float, B: float, C: float):
    """Real roots of A x^2 + B x + C = 0. Falls back to the vertex if the
    discriminant is slightly negative (numerical noise)."""
    if abs(A) < 1e-12:
        if abs(B) < 1e-12:
            return []
        return [-C / B]
    disc = B * B - 4.0 * A * C
    if disc < 0.0:
        return [-B / (2.0 * A)]  # tangent / near-degenerate: single best-effort root
    s = float(np.sqrt(disc))
    return [(-B + s) / (2.0 * A), (-B - s) / (2.0 * A)]


def estimate_position_3hydro_closed(H1, H2, H3, D12, D13, D23=None):
    """
    Closed-form source position from 3 hydrophones (reference = H1).

    Parameters
    ----------
    H1, H2, H3 : array-like
        Hydrophone coordinates [x, y] in planar metres (extra components, e.g.
        a z value, are ignored).
    D12, D13 : float
        Independent range differences [m]: D12 = d1 - d2, D13 = d1 - d3.
    D23 : float, optional
        Redundant range difference d2 - d3, used only to disambiguate the two
        hyperbola intersections. If omitted, the first valid root is returned.

    Returns
    -------
    (x, y) tuple in the input frame, or None if the geometry is degenerate
    (collinear hydrophones / no admissible root).
    """
    x1, y1 = np.asarray(H1, float)[:2]
    x2, y2 = np.asarray(H2, float)[:2]
    x3, y3 = np.asarray(H3, float)[:2]

    # r_i = d_i - d_1 (reference receiver 1)
    r2 = -float(D12)   # d2 - d1
    r3 = -float(D13)   # d3 - d1

    K1 = x1 * x1 + y1 * y1
    K2 = x2 * x2 + y2 * y2
    K3 = x3 * x3 + y3 * y3

    # Linear system:  M [x, y]^T = m0 - d1 * mc
    M = np.array([[2.0 * (x2 - x1), 2.0 * (y2 - y1)],
                  [2.0 * (x3 - x1), 2.0 * (y3 - y1)]], float)
    det = M[0, 0] * M[1, 1] - M[0, 1] * M[1, 0]
    if abs(det) < 1e-9:
        return None  # collinear hydrophones -> no unique linearisation

    Minv = np.array([[M[1, 1], -M[0, 1]],
                     [-M[1, 0], M[0, 0]]], float) / det

    m0 = np.array([K2 - K1 - r2 * r2, K3 - K1 - r3 * r3], float)
    mc = np.array([2.0 * r2, 2.0 * r3], float)

    P0 = Minv @ m0     # x,y at d1 = 0
    P1 = Minv @ mc     # d(x,y)/d(d1)

    ex = P0[0] - x1
    ey = P0[1] - y1
    fx = -P1[0]
    fy = -P1[1]

    # d1^2 = (ex + d1 fx)^2 + (ey + d1 fy)^2  ->  A d1^2 + B d1 + C = 0
    A = fx * fx + fy * fy - 1.0
    B = 2.0 * (ex * fx + ey * fy)
    C = ex * ex + ey * ey

    cands = []
    for d1 in _solve_quadratic(A, B, C):
        if d1 is None or d1 < 0.0:
            continue
        x = P0[0] - d1 * P1[0]
        y = P0[1] - d1 * P1[1]
        cands.append((float(x), float(y)))

    if not cands:
        return None
    if len(cands) == 1 or D23 is None:
        return cands[0]

    # Disambiguate the two intersections with the redundant pair D23 = d2 - d3.
    def _d23_residual(p):
        px, py = p
        d2 = np.hypot(px - x2, py - y2)
        d3 = np.hypot(px - x3, py - y3)
        return abs((d2 - d3) - float(D23))

    return min(cands, key=_d23_residual)


def estimate_position_3hydro_ls(H1, H2, H3, D12, D13, D23,
                                p0=None, B=(1.0, 1.0, 1.0),
                                max_iter=100, tol=1e-8):
    """
    Gauss-Newton least squares on the 3 REAL pairs (no virtual hydrophone).

    Seeded from the closed-form solution when available (NOT from the centroid),
    so there is no built-in pull toward the triangle centre. Returns (x, y) or
    None if it cannot be seeded / diverges to a singular step.
    """
    H1 = np.asarray(H1, float)[:2]
    H2 = np.asarray(H2, float)[:2]
    H3 = np.asarray(H3, float)[:2]

    if p0 is None:
        p0 = estimate_position_3hydro_closed(H1, H2, H3, D12, D13, D23)
        if p0 is None:
            # Last resort seed: centroid (only when closed form is degenerate).
            p0 = (H1 + H2 + H3) / 3.0
    p = np.asarray(p0, float)[:2].copy()

    D = np.array([D12, D13, D23], float)
    w = 1.0 / np.asarray(B, float) ** 2  # diagonal weights

    for _ in range(max_iter):
        d1 = np.hypot(p[0] - H1[0], p[1] - H1[1]) or 1e-15
        d2 = np.hypot(p[0] - H2[0], p[1] - H2[1]) or 1e-15
        d3 = np.hypot(p[0] - H3[0], p[1] - H3[1]) or 1e-15

        u1 = (p - H1) / d1
        u2 = (p - H2) / d2
        u3 = (p - H3) / d3

        # Residuals f_k = (model range diff) - (measured)
        f = np.array([(d1 - d2) - D[0],
                      (d1 - d3) - D[1],
                      (d2 - d3) - D[2]], float)

        # Jacobian rows = gradient of each range difference
        J = np.array([u1 - u2,
                      u1 - u3,
                      u2 - u3], float)

        JTW = J.T * w
        N = JTW @ J
        try:
            dp = -np.linalg.solve(N, JTW @ f)
        except np.linalg.LinAlgError:
            return None

        p = p + dp
        if np.max(np.abs(dp)) < tol:
            break

    return (float(p[0]), float(p[1]))


# Convenience default: closed form + LS polish on the 3 real pairs.
def estimate_position_3hydro(H1, H2, H3, D12, D13, D23, refine=True):
    """Default 3-hydrophone estimate. With refine=True (default) the closed-form
    result is polished by Gauss-Newton on the 3 real pairs."""
    if not refine:
        return estimate_position_3hydro_closed(H1, H2, H3, D12, D13, D23)
    return estimate_position_3hydro_ls(H1, H2, H3, D12, D13, D23)
