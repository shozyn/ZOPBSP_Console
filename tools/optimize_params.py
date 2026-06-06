"""
optimize_params.py

Quantitatively tune the post-processing parameters (TDOA closure tolerance,
hydrophone-triangle margin, Kalman process/measurement noise) against the
ground-truth reference tracks, instead of guessing.

Approach:
  1. Run the (slow) TDOA estimation ONCE per session/job and cache the RAW
     per-step output [time, lat, lon, closure] + the hydrophone triangle.
  2. Grid-search the parameters purely on the cached data: for each combo apply
     closure filter -> geometric margin -> Kalman, then measure the distance to
     the reference position at each timestamp.
  3. Report the best parameters (low median error with decent coverage).

Run:  python tools/optimize_params.py
Re-run is instant after the first pass (cache on disk). Use --refresh to redo.
"""

from __future__ import annotations

import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")  # avoid OpenMP clash (torch+MKL)

import json
import math
import re
import sys
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils import reference_track as rt
from utils.kalman import ConstantVelocityKalman2D

LA = Path(r"C:\Pi_loc\LA")
CACHE = ROOT / "tools" / "_optim_cache.json"

# Representative sessions (one per object type) with complete data + reference.
SESSIONS = [
    "20260520_Otter1",
    "20260520_LAUV1",
    "20260520_Ponton1",
]

RPIS = ["RPI1", "RPI2", "RPI3"]
_TS = re.compile(r"(\d{8}_\d{6})")

# Parameter grid
GRID_CLOSURE = [10.0, 15.0, 20.0]
GRID_MARGIN = [100.0, 200.0]
GRID_PSTD = [0.02, 0.05, 0.1]
GRID_MSTD = [10.0, 25.0, 40.0, 60.0, 100.0]

EARTH_R = 6378137.0


def _index_by_ts(folder: Path, ext: str) -> dict:
    out = {}
    if not folder.is_dir():
        return out
    for f in folder.glob(f"*{ext}"):
        m = _TS.search(f.name)
        if m:
            out[m.group(1)] = str(f)
    return out


def _enumerate_jobs(session_dir: Path):
    wav = {r: _index_by_ts(session_dir / r / "streaming", ".wav") for r in RPIS}
    gps = {r: _index_by_ts(session_dir / r / "gps", ".txt") for r in RPIS}

    common = None
    for r in RPIS:
        keys = set(wav[r]) & set(gps[r])
        common = keys if common is None else (common & keys)
    common = sorted(common or [])

    jobs = []
    for ts in common:
        jobs.append({
            "ts": ts,
            "wav": [wav[r][ts] for r in RPIS],
            "gps": [gps[r][ts] for r in RPIS],
        })
    return jobs


def collect_raw(refresh: bool = False) -> dict:
    if CACHE.exists() and not refresh:
        print(f"[optim] using cache {CACHE}")
        return json.loads(CACHE.read_text(encoding="utf-8"))

    from calculation.algorithms import ESTPOSAlgorithm
    algo = ESTPOSAlgorithm()

    cache = {}
    for sess in SESSIONS:
        sdir = LA / sess
        jobs = _enumerate_jobs(sdir)
        print(f"[optim] {sess}: {len(jobs)} jobs")
        sess_jobs = []
        for j in jobs:
            g1, g2, g3 = j["gps"]
            w1, w2, w3 = j["wav"]
            try:
                raw = algo.run(g1, g2, g3, w1, w2, w3)
            except Exception as e:
                print(f"   ! job {j['ts']} failed: {e}")
                raw = []
            tri = []
            ok = True
            for g in (g1, g2, g3):
                pos = rt.parse_receiver_gps_position(g)
                if pos is None:
                    ok = False
                    break
                tri.append([pos[1], pos[0]])  # (lon, lat)
            sess_jobs.append({"ts": j["ts"], "raw": raw, "tri": tri if ok else None})
            print(f"   job {j['ts']}: {len(raw) if isinstance(raw, list) else 0} raw pts")
        cache[sess] = {"jobs": sess_jobs}

    CACHE.write_text(json.dumps(cache), encoding="utf-8")
    print(f"[optim] cached -> {CACHE}")
    return cache


def _ll_to_m(lat, lon, lat0, lon0):
    x = math.radians(lon - lon0) * EARTH_R * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * EARTH_R
    return x, y


def _m_to_ll(x, y, lat0, lon0):
    lat = lat0 + math.degrees(y / EARTH_R)
    lon = lon0 + math.degrees(x / (EARTH_R * math.cos(math.radians(lat0))))
    return lat, lon


def _haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_R * math.asin(min(1.0, math.sqrt(a)))


def simulate(cache: dict, ref_indexes: dict, closure_tol, margin, pstd, mstd,
             max_gap_s=20.0):
    errs = []
    jitters = []  # smoothness: deviation of each smoothed point from the line of its neighbours
    kept = 0
    total = 0

    for sess, data in cache.items():
        ref_index = ref_indexes.get(sess) or {}
        kf = ConstantVelocityKalman2D(process_std=pstd, meas_std=mstd, max_gap_s=max_gap_s)
        frame = None
        last_sec = None
        smoothed_xy = []  # (x, y) metres of the smoothed track for this session

        for job in data["jobs"]:
            tri = job["tri"]
            for item in job["raw"]:
                if not isinstance(item, (list, tuple)) or len(item) < 3:
                    continue
                total += 1
                t = item[0]
                lat = float(item[1])
                lon = float(item[2])
                closure = float(item[3]) if len(item) > 3 else 0.0

                if abs(closure) > closure_tol:
                    continue
                if tri is not None and not rt.point_in_triangle_with_margin(
                    (lon, lat), tri[0], tri[1], tri[2], margin_m=margin
                ):
                    continue

                sec = rt.hhmmss_to_sec(t)
                if frame is None:
                    frame = (lat, lon)
                mx, my = _ll_to_m(lat, lon, frame[0], frame[1])
                dt = None if (last_sec is None or sec is None) else (sec - last_sec)
                last_sec = sec
                fx, fy = kf.update(mx, my, dt)
                f_lat, f_lon = _m_to_ll(fx, fy, frame[0], frame[1])
                kept += 1
                smoothed_xy.append((fx, fy))

                rp = rt.lookup_nearest(ref_index, sec)
                if rp is not None:
                    errs.append(_haversine_m(f_lat, f_lon, rp[0], rp[1]))

        # Jitter: distance of each interior smoothed point from the midpoint of
        # its neighbours (0 for a perfectly straight/smooth track).
        for i in range(1, len(smoothed_xy) - 1):
            x0, y0 = smoothed_xy[i - 1]
            x1, y1 = smoothed_xy[i]
            x2, y2 = smoothed_xy[i + 1]
            mxp, myp = (x0 + x2) / 2.0, (y0 + y2) / 2.0
            jitters.append(math.hypot(x1 - mxp, y1 - myp))

    if not errs:
        return None
    errs.sort()
    jitters.sort()
    n = len(errs)
    median = errs[n // 2]
    p90 = errs[min(n - 1, int(0.9 * n))]
    jitter = jitters[len(jitters) // 2] if jitters else 0.0
    coverage = kept / total if total else 0.0
    return {"median": median, "p90": p90, "coverage": coverage, "n": n, "jitter": jitter}


def main():
    refresh = "--refresh" in sys.argv
    cache = collect_raw(refresh=refresh)

    ref_indexes = {}
    for sess in cache:
        track = rt.load_reference_track(LA / sess)
        ref_indexes[sess] = rt.build_second_index(track)
        print(f"[optim] reference {sess}: {len(track)} pts -> {len(ref_indexes[sess])} sec")

    results = []
    for closure_tol, margin, pstd, mstd in product(
        GRID_CLOSURE, GRID_MARGIN, GRID_PSTD, GRID_MSTD
    ):
        m = simulate(cache, ref_indexes, closure_tol, margin, pstd, mstd)
        if m is None or m["coverage"] < 0.20:
            continue
        results.append((closure_tol, margin, pstd, mstd, m))

    if not results:
        print("[optim] no configs passed the coverage gate")
        return

    best_median = min(r[4]["median"] for r in results)
    # Goal: SMOOTH first, while keeping accuracy within 30% of the best median.
    acc_cap = best_median * 1.30
    smooth = [r for r in results if r[4]["median"] <= acc_cap]
    smooth.sort(key=lambda r: r[4]["jitter"])

    print(f"\n[optim] best achievable median = {best_median:.1f} m; "
          f"accuracy cap for smoothness ranking = {acc_cap:.1f} m")
    print("\n==== TOP 15 (smoothest within accuracy cap) ====")
    print(f"{'closure':>8} {'margin':>7} {'pstd':>6} {'mstd':>6} | "
          f"{'jitter':>7} {'median':>7} {'p90':>7} {'cover':>6}")
    for closure_tol, margin, pstd, mstd, m in smooth[:15]:
        print(f"{closure_tol:8.0f} {margin:7.0f} {pstd:6.2f} {mstd:6.0f} | "
              f"{m['jitter']:7.2f} {m['median']:7.1f} {m['p90']:7.1f} {m['coverage']:6.2f}")

    best = smooth[0]
    print("\n==== BEST (smooth + accurate) ====")
    print(f"closure_tol_m = {best[0]}")
    print(f"geo_margin_m  = {best[1]}")
    print(f"process_std   = {best[2]}")
    print(f"meas_std      = {best[3]}")
    print(f"jitter        = {best[4]['jitter']:.2f} m   median = {best[4]['median']:.1f} m   "
          f"p90 = {best[4]['p90']:.1f} m   coverage = {best[4]['coverage']:.2f}")


if __name__ == "__main__":
    main()
