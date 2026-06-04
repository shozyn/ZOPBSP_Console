"""
reference_track.py

Load ground-truth (reference) GPS tracks of measured objects (LAUV, Otter,
Ponton) and align them with a measurement session so they can be drawn on the
map next to the TDOA estimation (Est_pos).

Three on-disk formats are supported:

1) LAUV / Otter  ("L-AUV 20260520.txt", "Otter 20260520.txt")
   CSV with decimal degrees, UTC:
       #date and time (UTC), data and time(UNIX), lat, NS, lon, EW, depth
       2026-05-20T08:09:30.507, 1779264570.507, 53.83711119, N, 17.64738829, E, 0.12

2) Ponton  ("Server2_data_2026-05-20_12-00.txt")
   Raw NMEA GGA sentences (UTC, ddmm.mmmm):
       $GNGGA,100000.00,5350.2037785,N,01738.8650760,E,4,...

3) Receiver GPS  ("GPS_RPI1_20260520_120500_Hydro_6675.txt") - used only to
   determine the real UTC time window of a session:
       100500.00, 5350.1803075, N, 01738.8665480, E, Satellites: 25, ...

IMPORTANT time note:
   Session folder/file NAMES use local time (CEST = UTC+2), while file CONTENTS
   and the reference files use UTC. The session window is therefore read from
   the GPS file *contents* (UTC), never from the file names.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

import logging

logger = logging.getLogger(__name__)


@dataclass
class TrackPoint:
    utc: datetime          # timezone-aware UTC
    lat: float             # decimal degrees
    lon: float             # decimal degrees


# ---------------------------------------------------------------------------
# Coordinate / time helpers
# ---------------------------------------------------------------------------

def dm_to_deg(dm: str, hemisphere: str) -> float:
    """
    Convert NMEA-style 'ddmm.mmmm' (lat) or 'dddmm.mmmm' (lon) to decimal
    degrees. The integer-degrees part is everything left of the last two digits
    before the decimal point.

    Example: '5350.2037785','N' -> 53 + 50.2037785/60 = 53.836729...
             '01738.8650760','E' -> 17 + 38.8650760/60 = 17.647751...
    """
    dm = dm.strip()
    dot = dm.index(".")
    deg = int(dm[: dot - 2])
    minutes = float(dm[dot - 2:])
    value = deg + minutes / 60.0

    if hemisphere.strip().upper() in ("S", "W"):
        value = -value

    return value


def _hhmmss_to_time(tok: str):
    """Parse an NMEA time-of-day token 'HHMMSS.ss' -> (h, m, s, micros)."""
    tok = tok.strip()
    h = int(tok[0:2])
    m = int(tok[2:4])
    s = int(tok[4:6])
    frac = float("0" + tok[6:]) if len(tok) > 6 else 0.0
    return h, m, s, int(round(frac * 1_000_000))


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_object_decimal_file(path: Path) -> List[TrackPoint]:
    """Parse LAUV / Otter CSV files (decimal degrees, explicit UTC datetime)."""
    points: List[TrackPoint] = []

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 6:
                continue

            try:
                # parts[0] = '2026-05-20T08:09:30.507000'
                iso = parts[0].replace("Z", "")
                dt = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)

                lat = float(parts[2])
                if parts[3].upper() == "S":
                    lat = -lat

                lon = float(parts[4])
                if parts[5].upper() == "W":
                    lon = -lon

            except (ValueError, IndexError):
                continue

            points.append(TrackPoint(dt, lat, lon))

    return points


def parse_server2_gga_file(path: Path, date: datetime) -> List[TrackPoint]:
    """
    Parse a Server2 ponton file containing NMEA GGA sentences.

    GGA gives only a UTC time-of-day, so the date is supplied by the caller
    (taken from the file name / session date).
    """
    points: List[TrackPoint] = []
    base = date.astimezone(timezone.utc)

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if "GGA" not in line:
                continue

            # Drop a possible checksum and split.
            body = line.split("*")[0]
            f = body.split(",")
            # $xxGGA, time, lat, NS, lon, EW, fix, ...
            if len(f) < 6 or not f[1] or not f[2] or not f[4]:
                continue

            try:
                h, m, s, micros = _hhmmss_to_time(f[1])
                dt = base.replace(
                    hour=h, minute=m, second=s, microsecond=micros
                )

                lat = dm_to_deg(f[2], f[3])
                lon = dm_to_deg(f[4], f[5])

            except (ValueError, IndexError):
                continue

            points.append(TrackPoint(dt, lat, lon))

    return points


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

_OBJECT_PATTERNS = [
    ("LAUV", re.compile(r"LAUV", re.IGNORECASE)),
    ("Otter", re.compile(r"Otter", re.IGNORECASE)),
    ("Ponton", re.compile(r"Ponton", re.IGNORECASE)),
]


def session_object_and_date(session_dir: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    From a session folder name like '20260520_Otter1' return ('Otter','20260520').
    Returns (None, date) for sessions without a tracked object (e.g. Cisza).
    """
    name = session_dir.name
    m = re.match(r"(\d{8})_", name)
    date = m.group(1) if m else None

    for obj, pat in _OBJECT_PATTERNS:
        if pat.search(name):
            return obj, date

    return None, date


def session_utc_window(
    session_dir: Path,
    date: str,
) -> Optional[Tuple[datetime, datetime]]:
    """
    Determine the real UTC [start, end] of a session by reading the *contents*
    (UTC time-of-day) of all receiver GPS files. 'date' is 'YYYYMMDD'.
    """
    try:
        base = datetime.strptime(date, "%Y%m%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None

    times: List[datetime] = []

    for gps_file in session_dir.glob("RPI*/gps/*.txt"):
        try:
            with open(gps_file, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    tok = line.split(",")[0].strip()
                    if not re.match(r"^\d{6}", tok):
                        continue
                    h, m, s, micros = _hhmmss_to_time(tok)
                    times.append(
                        base.replace(hour=h, minute=m, second=s, microsecond=micros)
                    )
        except OSError:
            continue

    if not times:
        return None

    return min(times), max(times)


def find_reference_file(la_root: Path, obj: str, date: str) -> Optional[Path]:
    """
    Locate the reference file for an object/date.

    LAUV  -> 'L-AUV <YYYYMMDD>.txt'
    Otter -> 'Otter <YYYYMMDD>.txt'
    Ponton-> 'Server2_data_<YYYY-MM-DD>_*.txt'  (hourly files; all candidates)
    """
    if obj in ("LAUV", "Otter"):
        prefix = "L-AUV" if obj == "LAUV" else "Otter"
        cand = la_root / f"{prefix} {date}.txt"
        return cand if cand.exists() else None

    if obj == "Ponton":
        iso_date = f"{date[0:4]}-{date[4:6]}-{date[6:8]}"
        matches = sorted(la_root.glob(f"Server2_data_{iso_date}_*.txt"))
        return matches[0] if matches else None

    return None


def load_reference_track(session_dir: Path, la_root: Optional[Path] = None) -> List[TrackPoint]:
    """
    Top-level entry point: for a given session folder return the reference track
    of the measured object, restricted to the session's UTC time window.
    """
    session_dir = Path(session_dir)
    if la_root is None:
        la_root = session_dir.parent

    obj, date = session_object_and_date(session_dir)
    if obj is None or date is None:
        logger.info("[reference_track] No tracked object for session %s", session_dir.name)
        return []

    window = session_utc_window(session_dir, date)
    if window is None:
        logger.warning("[reference_track] Could not determine UTC window for %s", session_dir.name)
        return []

    t0, t1 = window
    # Small margin so the track slightly brackets the recordings.
    t0 -= timedelta(seconds=2)
    t1 += timedelta(seconds=2)

    if obj == "Ponton":
        iso_date = f"{date[0:4]}-{date[4:6]}-{date[6:8]}"
        files = sorted(la_root.glob(f"Server2_data_{iso_date}_*.txt"))
        base = datetime.strptime(date, "%Y%m%d").replace(tzinfo=timezone.utc)
        raw: List[TrackPoint] = []
        for f in files:
            raw.extend(parse_server2_gga_file(f, base))
    else:
        ref = find_reference_file(la_root, obj, date)
        if ref is None:
            logger.warning("[reference_track] No reference file for %s %s", obj, date)
            return []
        raw = parse_object_decimal_file(ref)

    track = [p for p in raw if t0 <= p.utc <= t1]
    logger.info(
        "[reference_track] %s: %d/%d points in window %s..%s",
        obj, len(track), len(raw), t0.time(), t1.time(),
    )
    return track


# ---------------------------------------------------------------------------
# Matching reference points to estimation timestamps
# ---------------------------------------------------------------------------

def build_second_index(points: List[TrackPoint]) -> dict:
    """
    Map UTC second-of-day -> (lat, lon), keeping one point per whole second.
    Used to look up the true object position at an estimation timestamp.
    """
    index: dict = {}
    for p in points:
        sec = p.utc.hour * 3600 + p.utc.minute * 60 + p.utc.second
        if sec not in index:
            index[sec] = (p.lat, p.lon)
    return index


def hhmmss_to_sec(value) -> Optional[int]:
    """
    Convert an Est_pos time field 'HHMMSS' (int/float/str, UTC) to seconds of
    day. Returns None if it cannot be parsed.
    """
    try:
        v = int(float(value))
    except (TypeError, ValueError):
        return None

    h, m, s = v // 10000, (v // 100) % 100, v % 100
    if h > 23 or m > 59 or s > 59:
        return None
    return h * 3600 + m * 60 + s


def lookup_nearest(index: dict, sec: int, tol: int = 3):
    """Return (lat, lon) for second-of-day `sec`, searching +/- `tol` seconds."""
    if sec is None:
        return None
    if sec in index:
        return index[sec]
    for d in range(1, tol + 1):
        if (sec - d) in index:
            return index[sec - d]
        if (sec + d) in index:
            return index[sec + d]
    return None


# ---------------------------------------------------------------------------
# Receiver (hydrophone) geometry helpers
# ---------------------------------------------------------------------------

def parse_receiver_gps_position(path) -> Optional[Tuple[float, float]]:
    """
    Return (lat, lon) in decimal degrees from the first valid line of a
    receiver GPS file:
        '100500.00, 5350.1803075, N, 01738.8665480, E, Satellites: 25, ...'
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                f = [x.strip() for x in line.split(",")]
                if len(f) < 5:
                    continue
                try:
                    lat = dm_to_deg(f[1], f[2])
                    lon = dm_to_deg(f[3], f[4])
                    return (lat, lon)
                except (ValueError, IndexError):
                    continue
    except OSError:
        return None
    return None


def point_in_triangle(p, a, b, c) -> bool:
    """
    Planar point-in-triangle test (inclusive of edges). Each argument is an
    (x, y) tuple. Degrees are used directly as planar coordinates, which is fine
    over the small hydrophone area.
    """
    def sign(o, u, v):
        return (o[0] - v[0]) * (u[1] - v[1]) - (u[0] - v[0]) * (o[1] - v[1])

    d1 = sign(p, a, b)
    d2 = sign(p, b, c)
    d3 = sign(p, c, a)

    has_neg = (d1 < 0) or (d2 < 0) or (d3 < 0)
    has_pos = (d1 > 0) or (d2 > 0) or (d3 > 0)
    return not (has_neg and has_pos)


def _ll_to_local_m(lon, lat, lon0, lat0):
    """Equirectangular lon/lat (deg) -> local metres around (lon0, lat0)."""
    R = 6378137.0
    x = math.radians(lon - lon0) * R * math.cos(math.radians(lat0))
    y = math.radians(lat - lat0) * R
    return (x, y)


def _point_segment_dist(p, a, b):
    """Distance from point p to segment a-b (planar (x, y))."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / seg2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def point_in_triangle_with_margin(p, a, b, c, margin_m: float = 50.0) -> bool:
    """
    Accept point p if it lies inside triangle abc OR within `margin_m` metres of
    it. p, a, b, c are (lon, lat) in degrees. The margin is applied in metres by
    converting to a local planar frame around the triangle centroid.
    """
    lon0 = (a[0] + b[0] + c[0]) / 3.0
    lat0 = (a[1] + b[1] + c[1]) / 3.0

    pm = _ll_to_local_m(p[0], p[1], lon0, lat0)
    am = _ll_to_local_m(a[0], a[1], lon0, lat0)
    bm = _ll_to_local_m(b[0], b[1], lon0, lat0)
    cm = _ll_to_local_m(c[0], c[1], lon0, lat0)

    if point_in_triangle(pm, am, bm, cm):
        return True

    if margin_m <= 0:
        return False

    d = min(
        _point_segment_dist(pm, am, bm),
        _point_segment_dist(pm, bm, cm),
        _point_segment_dist(pm, cm, am),
    )
    return d <= margin_m


# ---------------------------------------------------------------------------
# Self-test against the real data on disk.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    la = Path(r"C:\Pi_loc\LA")

    for sess in ["20260520_Otter1", "20260520_LAUV1", "20260520_Ponton1"]:
        sdir = la / sess
        obj, date = session_object_and_date(sdir)
        win = session_utc_window(sdir, date) if date else None
        print(f"\n### {sess}  obj={obj} date={date}")
        if win:
            print(f"   UTC window: {win[0].isoformat()} .. {win[1].isoformat()}")
        track = load_reference_track(sdir, la)
        print(f"   reference points in window: {len(track)}")
        for p in track[:3]:
            print(f"     {p.utc.time()}  lat={p.lat:.7f} lon={p.lon:.7f}")
