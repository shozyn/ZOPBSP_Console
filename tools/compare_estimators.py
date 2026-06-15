"""
compare_estimators.py

Side-by-side comparison of two TDOA position estimators on SYNTHETIC data
(known source -> exact range differences -> recovered position):

  * OLD : the production solver `tdoa_estimate_mode_6` (4-hydrophone / 6-pair
          scheme, virtual 4th hydrophone at the centroid, centroid-seeded).
  * NEW : `estimate_position_3hydro` from Est_pos/tdoa_solver_3hydro.py
          (genuine 3-hydrophone closed form + LS on the 3 real pairs, no
          virtual hydrophone, no centroid seed).

Synthetic data is used on purpose: it needs neither the .wav files nor the
missing `oblicz_TDOA` module, and lets us measure the exact position error of
each estimator against ground truth - in particular INSIDE vs OUTSIDE the
hydrophone triangle, which is where the centroid bias shows up.

Run from the project root:
    python tools/compare_estimators.py
    python tools/compare_estimators.py --noise 1.0 --plot

Nothing in the existing pipeline is imported for writing; this is read-only.
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np

# Make the project root importable when run as a script.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from Est_pos.tdoa_solver_3hydro import estimate_position_3hydro

try:
    from Est_pos.tdoa_solver_30_11_2025 import tdoa_estimate_mode_6
    _HAVE_OLD = True
except Exception as e:  # compiled module missing / wrong Python ABI
    _HAVE_OLD = False
    _OLD_IMPORT_ERR = e


# Hydrophone triangle in local metres, derived from the real RPI GPS in the logs
# (RPI1 as origin; equirectangular approximation at lat ~= 53.835 deg).
H1 = np.array([0.0, 0.0])
H2 = np.array([60.8, -65.7])
H3 = np.array([-30.5, -26.5])
CENTROID = (H1 + H2 + H3) / 3.0


def exact_range_diffs(p, noise=0.0, rng=None):
    """Exact (optionally noisy) D12, D13, D23 for a source at p."""
    d1 = np.hypot(p[0] - H1[0], p[1] - H1[1])
    d2 = np.hypot(p[0] - H2[0], p[1] - H2[1])
    d3 = np.hypot(p[0] - H3[0], p[1] - H3[1])
    D12, D13, D23 = d1 - d2, d1 - d3, d2 - d3
    if noise > 0.0:
        rng = rng or np.random
        D12 += rng.normal(0.0, noise)
        D13 += rng.normal(0.0, noise)
        D23 += rng.normal(0.0, noise)
    return D12, D13, D23


def point_in_triangle(p, a=H1, b=H2, c=H3):
    """Barycentric inside-test (edges count as inside)."""
    v0 = c - a
    v1 = b - a
    v2 = np.asarray(p, float) - a
    den = v0[0] * v1[1] - v1[0] * v0[1]
    if abs(den) < 1e-12:
        return False
    u = (v2[0] * v1[1] - v1[0] * v2[1]) / den
    v = (v0[0] * v2[1] - v2[0] * v0[1]) / den
    return (u >= -1e-9) and (v >= -1e-9) and (u + v <= 1.0 + 1e-9)


def run_old(D12, D13, D23):
    """Call the production solver the same way Estimator_pos.py does."""
    if not _HAVE_OLD:
        return None
    H_coord = [[H1[0], H1[1], -1], [H2[0], H2[1], -1], [H3[0], H3[1], -1]]
    try:
        res = tdoa_estimate_mode_6(H_coord=H_coord, dSH=(D12, D13, D23),
                                   B=[1.0, 1.0, 1.0], mode_po=0)
        pe = res["Pe"]
        return np.array([float(pe[0]), float(pe[1])])
    except Exception:
        return None


def run_new(D12, D13, D23):
    p = estimate_position_3hydro(H1, H2, H3, D12, D13, D23, refine=True)
    return None if p is None else np.array(p)


_FAIL_M = 500.0  # estymata dalej niz to od prawdy = razaca porazka (rozbieg/wybuch)


def summarise(label, errs, to_centroid):
    errs = np.asarray(errs, float)
    if errs.size == 0:
        print(f"  {label:<6} brak wynikow")
        return
    ok = errs[errs <= _FAIL_M]
    n_fail = int(np.sum(errs > _FAIL_M))
    mean_ok = np.mean(ok) if ok.size else float("nan")
    print(f"  {label:<6} n={errs.size:3d}  "
          f"median={np.median(errs):6.2f} m  "
          f"p90={np.percentile(errs, 90):7.2f} m  "
          f"mean(|err|<={_FAIL_M:.0f}m)={mean_ok:7.2f} m  "
          f"porazki(>{_FAIL_M:.0f}m)={n_fail:3d}/{errs.size}")


def main():
    ap = argparse.ArgumentParser(description="Porownanie estymatorow TDOA (synthetic).")
    ap.add_argument("--noise", type=float, default=0.0,
                    help="Odchylenie std szumu TDOA [m] dodawane do D12/D13/D23 (domyslnie 0).")
    ap.add_argument("--step", type=float, default=20.0, help="Krok siatki zrodel [m].")
    ap.add_argument("--seed", type=int, default=0, help="Ziarno RNG dla szumu.")
    ap.add_argument("--plot", action="store_true", help="Zapisz PNG z mapa bledow.")
    args = ap.parse_args()

    rng = np.random.RandomState(args.seed)

    xs = np.arange(-150.0, 210.0 + 1e-9, args.step)
    ys = np.arange(-220.0, 80.0 + 1e-9, args.step)

    rows = []  # (true_xy, inside, old_xy, new_xy)
    for x in xs:
        for y in ys:
            p = np.array([x, y])
            D12, D13, D23 = exact_range_diffs(p, noise=args.noise, rng=rng)
            rows.append((p, point_in_triangle(p), run_old(D12, D13, D23), run_new(D12, D13, D23)))

    def collect(inside_only, outside_only):
        old_e, new_e, old_c, new_c = [], [], [], []
        for p, inside, po, pn in rows:
            if inside_only and not inside:
                continue
            if outside_only and inside:
                continue
            if po is not None:
                old_e.append(np.hypot(*(po - p)))
                old_c.append(np.hypot(*(po - CENTROID)))
            if pn is not None:
                new_e.append(np.hypot(*(pn - p)))
                new_c.append(np.hypot(*(pn - CENTROID)))
        return old_e, new_e, old_c, new_c

    n_inside = sum(1 for _, ins, _, _ in rows if ins)
    print("=" * 78)
    print(f"Porownanie estymatorow TDOA  |  szum={args.noise:.2f} m  |  "
          f"zrodel={len(rows)} (wew. trojkata={n_inside}, na zewnatrz={len(rows) - n_inside})")
    print(f"Hydrofony: H1={H1.tolist()} H2={H2.tolist()} H3={H3.tolist()}  centroid={CENTROID.round(1).tolist()}")
    if not _HAVE_OLD:
        print(f"UWAGA: nie udalo sie zaladowac starego solvera (tdoa_solver_30_11_2025): {_OLD_IMPORT_ERR}")
        print("       -> pokazany bedzie tylko NEW. Uruchom w Pythonie 3.12 z numpy, by porownac.")
    print("=" * 78)

    for title, io, oo in [("WSZYSTKIE zrodla", False, False),
                          ("WEWNATRZ trojkata", True, False),
                          ("NA ZEWNATRZ trojkata", False, True)]:
        old_e, new_e, old_c, new_c = collect(io, oo)
        print(f"\n[{title}]")
        summarise("OLD", old_e, old_c)
        summarise("NEW", new_e, new_c)

    if args.plot:
        _make_plot(rows, args)


def _make_plot(rows, args):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"[plot] pomijam (matplotlib niedostepny): {e}")
        return

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    tri = np.array([H1, H2, H3, H1])
    for ax, key, name in [(axes[0], 2, "OLD (6-par, centroid)"),
                          (axes[1], 3, "NEW (3-par)")]:
        ax.plot(tri[:, 0], tri[:, 1], "k-", lw=1.5, alpha=0.7)
        ax.scatter(CENTROID[0], CENTROID[1], c="k", marker="+", s=120, label="centroid")
        tx, ty, te = [], [], []
        for p, _ins, po, pn in rows:
            est = po if key == 2 else pn
            if est is None:
                continue
            tx.append(p[0]); ty.append(p[1]); te.append(min(np.hypot(*(est - p)), 200.0))
        sc = ax.scatter(tx, ty, c=te, cmap="viridis", s=18, vmin=0, vmax=200)
        ax.set_title(name)
        ax.set_aspect("equal")
        ax.set_xlabel("x [m]"); ax.set_ylabel("y [m]")
        ax.legend(loc="upper right", fontsize="small")
        fig.colorbar(sc, ax=ax, label="blad pozycji [m] (clip 200)")

    out = os.path.join(_ROOT, "tools", f"compare_estimators_noise{args.noise:.1f}.png")
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    print(f"\n[plot] zapisano: {out}")


if __name__ == "__main__":
    main()
