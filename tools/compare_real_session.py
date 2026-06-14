"""
compare_real_session.py

Run a REAL recorded session through BOTH position solvers and compare the
resulting tracks - headless (no GUI), in-process.

  * mode6  : production solver (4-hydrophone / 6-pair, virtual 4th hydrophone
             at the centroid, centroid-seeded).
  * 3hydro : Est_pos/tdoa_solver_3hydro.py (genuine 3-hydrophone estimator).

For each 15 s job the same .wav -> TDOA is computed once per solver (TDOA is
deterministic, so both solvers see identical range differences); only the
position step differs. We then compare, per matched 1 Hz timestamp:
  - separation between the two solvers' estimates [m],
  - whether each estimate falls inside the hydrophone triangle,
  - each estimate's distance to the triangle centroid (centroid-pull indicator).

Requires the app's Python 3.12 env (compiled oblicz_TDOA / mode6 solver):
    C:\\Users\\User\\miniconda3\\envs\\zopbsp_konsola\\python.exe tools/compare_real_session.py
    ... --session "C:\\Pi_loc\\20260609-12 Czernica (AMW)\\20260612 Otter" --csv out.csv

Read-only w.r.t. the recorded data; nothing in the pipeline is modified.
"""

from __future__ import annotations

import argparse
import io
import math
import os
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

RPIS = ["RPI1", "RPI2", "RPI3"]
_TS = re.compile(r"(\d{8}_\d{6})")
EARTH_R = 6378137.0

DEFAULT_SESSION = r"C:\Pi_loc\20260609-12 Czernica (AMW)\20260612 Otter"


def index_by_ts(folder: Path, ext: str) -> dict:
    out = {}
    if folder.is_dir():
        for f in folder.glob(f"*{ext}"):
            m = _TS.search(f.name)
            if m:
                out[m.group(1)] = str(f)
    return out


def enumerate_jobs(session_dir: Path):
    wav = {r: index_by_ts(session_dir / r / "streaming", ".wav") for r in RPIS}
    gps = {r: index_by_ts(session_dir / r / "gps", ".txt") for r in RPIS}
    common = None
    for r in RPIS:
        keys = set(wav[r]) & set(gps[r])
        common = keys if common is None else (common & keys)
    jobs = []
    for ts in sorted(common or []):
        jobs.append({"ts": ts,
                     "gps": [gps[r][ts] for r in RPIS],
                     "wav": [wav[r][ts] for r in RPIS]})
    return jobs


def ll_to_m(lat, lon, lat0, lon0):
    x = math.radians(lon - lon0) * EARTH_R * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * EARTH_R
    return x, y


def dist_ll(lat_a, lon_a, lat_b, lon_b):
    """Approx. distance [m] between two WGS84 points (equirectangular)."""
    x = math.radians(lon_a - lon_b) * EARTH_R * math.cos(math.radians(lat_b))
    y = math.radians(lat_a - lat_b) * EARTH_R
    return math.hypot(x, y)


def point_in_triangle(p, a, b, c):
    v0 = (c[0] - a[0], c[1] - a[1])
    v1 = (b[0] - a[0], b[1] - a[1])
    v2 = (p[0] - a[0], p[1] - a[1])
    den = v0[0] * v1[1] - v1[0] * v0[1]
    if abs(den) < 1e-9:
        return False
    u = (v2[0] * v1[1] - v1[0] * v2[1]) / den
    v = (v0[0] * v2[1] - v2[0] * v0[1]) / den
    return (u >= -1e-9) and (v >= -1e-9) and (u + v <= 1.0 + 1e-9)


def run_solver(estimate_pos, gps, wav, solver):
    """Call estimate_pos for one job with the chosen solver, muting its verbose
    prints. Returns list of [time, lon, lat, closure] (or [] on failure)."""
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            track = estimate_pos(gps[0], gps[1], gps[2], wav[0], wav[1], wav[2],
                                 solver=solver)
        return track or []
    except Exception as e:
        print(f"   ! {solver} job failed: {e}")
        return []


def main():
    ap = argparse.ArgumentParser(description="Porownanie mode6 vs 3hydro na realnej sesji.")
    ap.add_argument("--session", default=DEFAULT_SESSION, help="Katalog sesji (z RPI1/2/3).")
    ap.add_argument("--limit", type=int, default=0, help="Maks. liczba jobow (0 = wszystkie).")
    ap.add_argument("--csv", default="", help="Opcjonalny plik CSV z punktami obu solverow.")
    args = ap.parse_args()

    from Est_pos.Estimator_pos import estimate_pos
    from utils.reference_track import (
        parse_receiver_gps_position,
        load_reference_track,
        build_second_index,
        hhmmss_to_sec,
    )

    session_dir = Path(args.session)
    jobs = enumerate_jobs(session_dir)
    if args.limit > 0:
        jobs = jobs[:args.limit]

    # Ground-truth (reference) track, if available for this session.
    ref_pts = load_reference_track(session_dir, la_root=session_dir.parent)
    ref_idx = build_second_index(ref_pts) if ref_pts else {}
    err_old, err_new = [], []
    if ref_idx:
        print(f"Trasa referencyjna: {len(ref_pts)} punktow ({len(ref_idx)} sekund) -> liczę blad bezwzgledny.")
    else:
        print("Brak trasy referencyjnej dla tej sesji -> tylko porownanie mode6 vs 3hydro.")

    print("=" * 80)
    print(f"Sesja: {session_dir}")
    print(f"Jobow do policzenia: {len(jobs)}")
    print("=" * 80)
    if not jobs:
        print("Brak dopasowanych trojek wav+gps - sprawdz sciezke sesji.")
        return

    seps = []                 # separacja mode6 vs 3hydro [m] na wspolnych znacznikach
    cen_old, cen_new = [], []  # odleglosc estymaty do centroidu [m]
    inside_old = inside_new = 0
    n_old = n_new = 0
    csv_rows = []

    lat0 = lon0 = None

    for j in jobs:
        # Trojkat hydrofonow z pierwszego fixu GPS kazdego odbiornika.
        tri = []
        ok = True
        for g in j["gps"]:
            pos = parse_receiver_gps_position(g)  # (lat, lon)
            if pos is None:
                ok = False
                break
            tri.append(pos)
        if not ok:
            print(f"   job {j['ts']}: brak pozycji odbiornika -> pomijam")
            continue

        if lat0 is None:
            lat0, lon0 = tri[0]
        tri_m = [ll_to_m(la, lo, lat0, lon0) for (la, lo) in tri]
        cen_m = (sum(p[0] for p in tri_m) / 3.0, sum(p[1] for p in tri_m) / 3.0)

        track_old = run_solver(estimate_pos, j["gps"], j["wav"], "mode6")
        track_new = run_solver(estimate_pos, j["gps"], j["wav"], "3hydro")
        n_old += len(track_old)
        n_new += len(track_new)

        by_t_new = {str(it[0]): it for it in track_new}

        for it in track_old:
            t = str(it[0])
            lat_o, lon_o = float(it[1]), float(it[2])  # est_track = [time, lat, lon, closure]
            po_m = ll_to_m(lat_o, lon_o, lat0, lon0)
            cen_old.append(math.hypot(po_m[0] - cen_m[0], po_m[1] - cen_m[1]))
            if point_in_triangle(po_m, *tri_m):
                inside_old += 1
            sec = hhmmss_to_sec(it[0])
            if sec in ref_idx:
                rlat, rlon = ref_idx[sec]
                err_old.append(dist_ll(lat_o, lon_o, rlat, rlon))

            jt = by_t_new.get(t)
            row = [j["ts"], t, lat_o, lon_o, "", ""]
            if jt is not None:
                lat_n, lon_n = float(jt[1]), float(jt[2])
                pn_m = ll_to_m(lat_n, lon_n, lat0, lon0)
                seps.append(math.hypot(po_m[0] - pn_m[0], po_m[1] - pn_m[1]))
                row[4], row[5] = lat_n, lon_n
            csv_rows.append(row)

        for it in track_new:
            lat_n, lon_n = float(it[1]), float(it[2])
            pn_m = ll_to_m(lat_n, lon_n, lat0, lon0)
            cen_new.append(math.hypot(pn_m[0] - cen_m[0], pn_m[1] - cen_m[1]))
            if point_in_triangle(pn_m, *tri_m):
                inside_new += 1
            sec = hhmmss_to_sec(it[0])
            if sec in ref_idx:
                rlat, rlon = ref_idx[sec]
                err_new.append(dist_ll(lat_n, lon_n, rlat, rlon))

        print(f"   job {j['ts']}: mode6={len(track_old):2d} pkt, 3hydro={len(track_new):2d} pkt")

    def stats(xs):
        if not xs:
            return "brak"
        xs = sorted(xs)
        n = len(xs)
        med = xs[n // 2]
        mean = sum(xs) / n
        p90 = xs[min(n - 1, int(0.9 * n))]
        return f"median={med:7.2f}  mean={mean:7.2f}  p90={p90:7.2f}  max={xs[-1]:8.2f}  (n={n})"

    print("\n" + "=" * 80)
    print("WYNIKI")
    print("=" * 80)
    print(f"Punkty wyemitowane:        mode6={n_old}   3hydro={n_new}")
    print(f"Separacja mode6 vs 3hydro [m]:  {stats(seps)}")
    print(f"Odleglosc do centroidu, mode6  [m]: {stats(cen_old)}")
    print(f"Odleglosc do centroidu, 3hydro [m]: {stats(cen_new)}")
    if n_old:
        print(f"Wewnatrz trojkata: mode6  {inside_old}/{n_old} ({100.0*inside_old/n_old:.0f}%)")
    if n_new:
        print(f"Wewnatrz trojkata: 3hydro {inside_new}/{n_new} ({100.0*inside_new/n_new:.0f}%)")
    if ref_idx:
        print("\n--- BLAD WZGLEDEM TRASY REFERENCYJNEJ (ground truth) ---")
        print(f"mode6  [m]: {stats(err_old)}")
        print(f"3hydro [m]: {stats(err_new)}")

    if args.csv:
        out = Path(args.csv)
        with out.open("w", encoding="utf-8") as f:
            f.write("job_ts,time,mode6_lat,mode6_lon,3hydro_lat,3hydro_lon\n")
            for r in csv_rows:
                f.write(",".join(str(x) for x in r) + "\n")
        print(f"\nCSV zapisany: {out.resolve()}")


if __name__ == "__main__":
    main()
