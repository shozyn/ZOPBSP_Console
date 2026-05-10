from scipy.io import wavfile
import numpy as np

# ===================== IMPORT DANYCH =====================

def load_gps_txt_unique_seconds(filename):
    def convert_dm(v):
        """Konwersja ddmm.mmmm → stopnie dziesiętne."""
        v = float(v)
        deg = int(v // 100)
        minutes = v - deg * 100
        return deg + minutes / 60

    result = []
    seen_seconds = set()  # zapisane sekundy

    with open(filename, "r") as f:
        for line in f:
            parts = line.strip().split(",")

            # czas może mieć ułamki sekund → pobieramy sekundę jako int
            time_full = float(parts[0])
            time_sec = int(time_full)

            # jeżeli ta sekunda już była – pomijamy
            if time_sec in seen_seconds:
                continue

            seen_seconds.add(time_sec)

            lat_raw = parts[1]
            lon_raw = parts[3]

            lat = convert_dm(lat_raw)
            lon = convert_dm(lon_raw)

            result.append([time_sec, lat, lon])

    return result



def import_data(gps1_path,gps2_path,gps3_path,wav1_path,wav2_path,wav3_path):
    # GPS 3×RPI
    GPS1 = load_gps_txt_unique_seconds(gps1_path)
    GPS2 = load_gps_txt_unique_seconds(gps2_path)
    GPS3 = load_gps_txt_unique_seconds(gps3_path)

    # # OP (LAUV Server) — -2h
    # op_ts = int(time_point)-20000# time shift 
    # # next bierze kolejny element path
    # GPS_OP = load_gps_txt_unique_seconds(f"trajektoria_LAUV 20251015__20251015_{op_ts}_UTC__WIN00_19.txt")

    # WAV
    fs, s1_raw = wavfile.read(wav1_path)
    _,  s2_raw = wavfile.read(wav2_path)
    _,  s3_raw = wavfile.read(wav3_path)

    s1_raw = np.asarray(s1_raw, dtype=float)
    s2_raw = np.asarray(s2_raw, dtype=float)
    s3_raw = np.asarray(s3_raw, dtype=float)

    return GPS1, GPS2, GPS3, s1_raw, s2_raw, s3_raw, fs