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



def import_data(time_point=133400):
    # GPS 3×RPI
    GPS1 = load_gps_txt_unique_seconds(f"GPS_RPI1_20251015_{time_point}_Hydro_6673.txt")
    GPS2 = load_gps_txt_unique_seconds(f"GPS_RPI2_20251015_{time_point}_Hydro_6676.txt")
    GPS3 = load_gps_txt_unique_seconds(f"GPS_RPI3_20251015_{time_point}_Hydro_6675.txt")

    # OP (LAUV Server) — -2h
    op_ts = int(time_point)-20000# time shift 
    # next bierze kolejny element path
    GPS_OP = load_gps_txt_unique_seconds(f"trajektoria_LAUV 20251015__20251015_{op_ts}_UTC__WIN00_19.txt")

    # WAV
    fs, s1_raw = wavfile.read(f"RBW6673_20251015_{str(time_point).zfill(6)}.wav")
    _,  s2_raw = wavfile.read(f"RBW6676_20251015_{str(time_point).zfill(6)}.wav")
    _,  s3_raw = wavfile.read(f"RBW6675_20251015_{str(time_point).zfill(6)}.wav")

    s1_raw = np.asarray(s1_raw, dtype=float)
    s2_raw = np.asarray(s2_raw, dtype=float)
    s3_raw = np.asarray(s3_raw, dtype=float)

    return GPS1, GPS2, GPS3, GPS_OP, s1_raw, s2_raw, s3_raw, fs