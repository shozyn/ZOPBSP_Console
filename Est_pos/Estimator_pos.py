#from datetime import datetime
#import numpy as np
#import pandas as pd
#import matplotlib
#matplotlib.use("Agg")  # headless (bez okna GUI)
from geopy.distance import geodesic
from pyproj import Transformer, CRS
#from plotowanie import plot_final_results, save_folium_map
#from odleglosci_wg_GPS import  GPS_dist_Vincenty
#from importowanie import import_data
# scytonizowane funkcje
# from Est_pos.tdoa_cython import compute_tdoa_1hz  # pierwszy człon nazwy pliku 
from oblicz_TDOA import compute_tdoa_1hz
from Est_pos.tdoa_solver_30_11_2025 import tdoa_estimate_mode_6
from Est_pos.importowanie import import_data


"""
DANE:
Trzy pliki *wav, nagrane za pomocą hydrofonów.
Trzy pliki .txt z współrzędnymi GPS (w czasie).
Jeden plik .txt z położeniem imitatora OP - do weryfikacji i oceny dokladności opracowanego algorytmu. 

SZUKANE:
Położenie imitatora OP.

ROZWIAZANIE:
Na podstawie plików .wav i plików .txt z GPS (docelowo BSP) wyznaczana jest wartość różnic odległości 
dla każdej pary hydrofonów. 

Wyznaczyć położenie źródła dźwięku.
Realizacja w krokach:
1) import danych z bieżącego folderu
2) wyznaczenie TDOA w metrach dla par hydrofonów 12, 13, 23
3) estymacja pozycji źródła dźwięku
4) zobrazowanie wyników

"""
# ===================== KONFIG / STAŁE =====================
c: int = 1470        # prędkość dźwięku w wodzie [m/s]

# parametry wyznaczone na podstawie wykonanych pomiarów w Czernicy przez GA

### 3 m/s
# epsilon = 0.055
# k = 0.1314      # lub sigma
# jump_sig = 0.23 # przesunięcie pomiędzy kolejnymi oknami analizy
# len_sig = 0.85  # długość okna
# low_cut = 177
# band_width = 573
# high_cut = low_cut + band_width

#### 1 m/s
epsilon = 0.25
k = 0.55     # lub sigma
jump_sig = 0.15 # przesunięcie pomiędzy kolejnymi oknami analizy
len_sig = 0.73  # długość okna
low_cut = 187
band_width = 2170
high_cut = low_cut + band_width

# ===== zmiana współrzędnych =====
def make_local_transformer(ref_lat: float, ref_lon: float):
    print(f"ref_lat:  {ref_lat}") 
    print(f"ref_lon:  {ref_lon}") 
    aeqd = CRS.from_proj4(f"+proj=aeqd +lat_0={ref_lat} +lon_0={ref_lon} +datum=WGS84 +units=m +no_defs")
    print(f"aeqd: {aeqd}")
    wgs84 = CRS.from_epsg(4326)
    fwd = Transformer.from_crs(wgs84, aeqd, always_xy=True)   # lon,lat -> x,y
    print(f"fwd: {fwd}")
    inv = Transformer.from_crs(aeqd, wgs84, always_xy=True)   # x,y -> lon,lat
    print(f"inv: {inv}")
    return fwd, inv

# funkcja do posptocesingu - usuwamy estymowane polozenie źródła dzwieku 
def filter_est_track_by_radius(est_track, lat0, lon0, radius_m=300.0):
    keep = []
    for rec in est_track:
        try:
            _, la, lo = rec
            if geodesic((lat0, lon0), (la, lo)).meters <= radius_m:
                keep.append(rec)
        except Exception:
            pass
    #print(f"[tdoa] filtr promienia: zachowano {len(keep)}/{len(est_track)} ≤ {radius_m:.0f} m.")
    return keep

# ===================== ZAPIS WYNIKOW do pliku txt =====================
"""Zapis w pliku detailed.txt połozenia wszystkich RPi oraz TDOA w metrach"""
def save_detailed_results(GPS1, GPS2, GPS3, GPS_OP,
                          tdoa12_1hz, tdoa13_1hz, tdoa23_1hz):
    n = min(len(GPS1), len(GPS2), len(GPS3), len(GPS_OP),
            len(tdoa12_1hz), len(tdoa13_1hz), len(tdoa23_1hz))
    out_details = "detailed.txt"
    with open(out_details, "w", encoding="utf-8") as f:
        f.write("time\tGPS1_lat\tGPS1_lon\tGPS2_lat\tGPS2_lon\tGPS3_lat\tGPS3_lon\tGPS_OP_lat\tGPS_OP_lon\tTDOA12\tTDOA13\tTDOA23\n")
        for i in range(n):
            czas_str = str(GPS1[i][0])
            g1_lat, g1_lon = GPS1[i][1], GPS1[i][2]
            g2_lat, g2_lon = GPS2[i][1], GPS2[i][2]
            g3_lat, g3_lon = GPS3[i][1], GPS3[i][2]
            go_lat, go_lon = GPS_OP[i][1], GPS_OP[i][2]
            f.write(
                f"{czas_str}\t"
                f"{g1_lat:.11f}\t{g1_lon:.11f}\t"
                f"{g2_lat:.11f}\t{g2_lon:.11f}\t"
                f"{g3_lat:.11f}\t{g3_lon:.11f}\t"
                f"{go_lat:.11f}\t{go_lon:.11f}\t"
                f"{tdoa12_1hz[i]:.6f}\t{tdoa13_1hz[i]:.6f}\t{tdoa23_1hz[i]:.6f}\n"
            )
# ===================== GŁÓWNA PĘTLA - POCZĄTEK ===================================

def estimate_pos(gps1_path, gps2_path, gps3_path, wav1_path, wav2_path, wav3_path):

    GPS1, GPS2, GPS3, s1_raw, s2_raw, s3_raw, fs = import_data(gps1_path, gps2_path, gps3_path, wav1_path, wav2_path, wav3_path)

    # wczytanie danych:
    # pomiarowych (GPS1, GPS2, GPS3, s1_raw, s2_raw, s3_raw, fs)
    # do weryfikacji (GPS_OP) 
   
    # sprawdzenie minimalnej liczby danych pomiarowych z GPS (do TDOA i weryfikacji)
    #n_gps = min(len(GPS1), len(GPS2), len(GPS3))

    # PIERWSZA FUNKCJA SCYTONIZOWANA - wyznaczenie TDOA;
    """
    funkcję compute_tdoa_1hz wywołujemy, dla każdej pary hydrofonów.
    można wywołać na dwa sposoby, pierwszy:
    
    tdoa12_1hz_m = compute_tdoa_1hz(s1_raw, s2_raw, fs, c, epsilon, k, len_sig, jump_sig, low_cut, high_cut)
    tdoa13_1hz_m = compute_tdoa_1hz(s1_raw, s3_raw, fs, c, epsilon, k, len_sig, jump_sig, low_cut, high_cut)
    tdoa23_1hz_m = compute_tdoa_1hz(s2_raw, s3_raw, fs, c, epsilon, k, len_sig, jump_sig, low_cut, high_cut)
    
    lub drugi sposób, za pomoca wrapera:
    
    def tdoa(s1,s2):
        return compute_tdoa_1hz(s1, s2, fs, c, epsilon, k, len_sig, jump_sig, low_cut, high_cut)

    tdoa12_1hz_m = tdoa(s1_raw, s2_raw)
    tdoa13_1hz_m = tdoa(s1_raw, s3_raw)
    tdoa23_1hz_m = tdoa(s2_raw, s3_raw)
    """

    def tdoa(s1,s2):
        return compute_tdoa_1hz(s1, s2, fs, c, epsilon, k, len_sig, jump_sig, low_cut, high_cut)

    tdoa12_1hz_m = tdoa(s1_raw, s2_raw)
    tdoa13_1hz_m = tdoa(s1_raw, s3_raw)
    tdoa23_1hz_m = tdoa(s2_raw, s3_raw)

    print(f"GPS1: {GPS1}")
    print(f"GPS2: {GPS2}")
    print(f"GPS3: {GPS3}")
    
    # Estymacja toru źródła dźwięku z TDOA (1 Hz) 
    # początek układu współrzędnych (Tylko 3 — solver sam wygeneruje 4-ty w centroidzie)
    ref_lat = GPS1[0][1] 
    ref_lon = GPS1[0][2] 
    fwd,inv = make_local_transformer(ref_lat,ref_lon)   

    # współrzędne hydrofonów
    H_coord=[
    [*fwd.transform(*GPS1[0][1:3]),-1], # lista x,y,z RPI1
    [*fwd.transform(*GPS2[0][1:3]),-1], # lista x,y,z RPI2
    [*fwd.transform(*GPS3[0][1:3]),-1] # lista x,y,z RPI3
    ]

    # Niepewności (metry)
    B = [1.0, 1.0, 1.0]
            
    est_track=[]
    for *dSH,czas_gps1 in zip(tdoa12_1hz_m,tdoa13_1hz_m,tdoa23_1hz_m,GPS1): # do dSH podajemy 3xtdoa, a z GPS1 podajemy czas do czas_gps1
        res_1hz = tdoa_estimate_mode_6(
            H_coord = H_coord,
            dSH     = dSH,
            B       = B,
            mode_po = 0,   # centroid
            )  

        pos_est = inv.transform(*res_1hz['Pe'][0:2]) # Pe - position estomation 
        est_track.append([czas_gps1[0],*pos_est])

    print(f"pos_est: {pos_est}")

    # Weryfikacja dokładności estymacji pozycji poprzez porównanie do danych z GPS -> MAE (1Hz)
    # gps12_m = GPS_dist_Vincenty(GPS1, GPS2, GPS_OP)[:n_gps]
    # gps13_m = GPS_dist_Vincenty(GPS1, GPS3, GPS_OP)[:n_gps]
    # gps23_m = GPS_dist_Vincenty(GPS2, GPS3, GPS_OP)[:n_gps]
    # mae12 = float(np.mean(np.abs(tdoa12_1hz_m - gps12_m)))  # zamiana na float bo json nie  przyjmuje numpy
    # mae13 = float(np.mean(np.abs(tdoa13_1hz_m - gps13_m)))
    # mae23 = float(np.mean(np.abs(tdoa23_1hz_m - gps23_m)))
    # mae = (mae12 + mae13 + mae23) / 3.0 # średni błąd estymacji pozycji w odniesieniu do GPS
    # print(f"MAE (1Hz): 12={mae12:.2f} 13={mae13:.2f} 23={mae23:.2f} | mean_{mae=:.2f}")

    # # zapis szczegółów (1Hz) -> opcjonalnie
    # save_detailed_results(GPS1, GPS2, GPS3, GPS_OP,
    #                         tdoa12_1hz_m, tdoa13_1hz_m, tdoa23_1hz_m)
    
    # filtrowanie estymowanych pozycji, akceptujemy tylko pozycje w odległości do radius_m=300m od RPi1 (opcjonalnie)
    if GPS1:
        est_track = filter_est_track_by_radius(est_track, GPS1[0][1], GPS1[0][2], radius_m=300.0)

    print(f"est_track: {est_track}")

    return est_track

    # zapis śladu (opcjonalnie) 
    # out_est = f"TDOA_track.txt"
    # with open(out_est, "w", encoding="utf-8") as f:
    #     f.write("time\tlat\tlon\n")
    #     for t, la, lo in est_track:
    #         f.write(f"{t}\t{la:.8f}\t{lo:.8f}\n")

    # rysowanie — stabilne wykresy + tor TDOA-EST na mapie
#     try:
#         plot_final_results(
#             s1_raw, s2_raw, s3_raw,   # sygnały z *.wav do wykresu
#             GPS1, GPS2, GPS3, GPS_OP, fs,
#             tdoa12_1hz_m, tdoa13_1hz_m, tdoa23_1hz_m,   # w miejsce TDOAs*_raw, ale i tak używasz trybu 1Hz
#             "time_point", mae, ".",
#             est_track=est_track,
#             TDOAs12_1hz=tdoa12_1hz_m, TDOAs13_1hz=tdoa13_1hz_m, TDOAs23_1hz=tdoa23_1hz_m,
#             use_1hz=True
#         )

#         # HTML mapa (folium) z TDOA-EST
#         html_out = "mapa_.html"
#         save_folium_map(GPS1, GPS2, GPS3, GPS_OP, html_out, tdoa_track=est_track)
#     except Exception as e:
#         print(f"Błąd rysowania: {e}")

# if __name__ == "__main__":
#     main()
