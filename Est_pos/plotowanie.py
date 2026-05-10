import pandas as pd
import geopandas as gpd
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
from shapely.geometry import LineString, Point
import contextily as cx
import folium
import numpy as np
from odleglosci_wg_GPS import  GPS_dist_Vincenty
# ===================== RYSOWANIE =====================
USE_BASEMAP = True   # podkład OSM; przy błędzie nie przerwie rysowania
def to_linestring(track):
    lats = [lat for _, lat, _ in track]
    lons = [lon for _, _, lon in track]
    return LineString(list(zip(lons, lats)))  # (lon, lat)

def _plot_pair_1hz(ax, t_gps, y_tdoa, y_gps, color, label_gps):
    # linie jako tło
    ax.plot(t_gps, y_tdoa, linestyle="-", linewidth=1.0, color=color, alpha=0.6)
    ax.plot(t_gps, y_gps,  linestyle="-", linewidth=1.0, color="black", alpha=0.6)
    # punkty CO 1 s – scatter gwarantuje marker na każdym punkcie wejściowym
    ax.scatter(t_gps, y_tdoa, s=10, marker="o", color=color, label="TDOA@1Hz")
    ax.scatter(t_gps, y_gps,  s=18, marker="x", color="black", label=label_gps)
    # osie co 1 s
    if len(t_gps) >= 2:
        ax.set_xlim(t_gps[0], t_gps[-1])
        ax.set_xticks(np.arange(int(t_gps[0]), int(t_gps[-1]) + 1, 1))
    ax.grid(True)

def plot_final_results(
    s1, s2, s3, GPS1, GPS2, GPS3, GPS_OP, fs,
    TDOAs12_raw, TDOAs13_raw, TDOAs23_raw,   # surowe TDOA
    godz, min_mae_all, results_folder,
    est_track=None,
    TDOAs12_1hz=None, TDOAs13_1hz=None, TDOAs23_1hz=None,
    use_1hz=False
    ):
    print("start plota [OLD/1Hz]")

    # === UKŁAD FIGURY: mapę rozciągamy na 2 wiersze po lewej ===
    fig = plt.figure(figsize=(15, 9))
    gs = fig.add_gridspec(3, 2)

    ax1 = fig.add_subplot(gs[0, 0])    # sygnały
    ax2 = fig.add_subplot(gs[0, 1])    # TDOA/GPS 1-2
    ax_map = fig.add_subplot(gs[1:, 0])  # DUŻA MAPA (wiersz 2+3, kolumna 0)
    ax4 = fig.add_subplot(gs[1, 1])    # TDOA/GPS 1-3
    ax6 = fig.add_subplot(gs[2, 1])    # TDOA/GPS 2-3

    # 1) sygnały
    dt = 1.0 / fs
    t_wav = np.arange(0, len(s1) / fs, dt)
    ax1.plot(t_wav, s1, label="s1", alpha=0.5, color='red')
    ax1.plot(t_wav, s2, label="s2", alpha=0.5, color='green')
    ax1.plot(t_wav, s3, label="s3", alpha=0.5, color='blue')
    ax1.set_ylabel("s1, s2, s3")
    ax1.set_xlabel("sec")
    ax1.grid()
    ax1.legend()

    # 2) Porównanie TDOA vs GPS
    dist_GPS12 = GPS_dist_Vincenty(GPS1, GPS2, GPS_OP)
    dist_GPS13 = GPS_dist_Vincenty(GPS1, GPS3, GPS_OP)
    dist_GPS23 = GPS_dist_Vincenty(GPS2, GPS3, GPS_OP)

    if use_1hz and (TDOAs12_1hz is not None) and (TDOAs13_1hz is not None) and (TDOAs23_1hz is not None):
        # ---- NOWY TRYB 1 Hz ----
        n_gps = min(len(GPS1), len(GPS2), len(GPS3), len(GPS_OP),
                    len(TDOAs12_1hz), len(TDOAs13_1hz), len(TDOAs23_1hz))
        t_gps = np.arange(n_gps, dtype=float)  # 0..N-1 [s]

        g12 = dist_GPS12[:n_gps]
        g13 = dist_GPS13[:n_gps]
        g23 = dist_GPS23[:n_gps]

        y12 = TDOAs12_1hz[:n_gps]
        y13 = TDOAs13_1hz[:n_gps]
        y23 = TDOAs23_1hz[:n_gps]

        mae12 = float(np.mean(np.abs(y12 - g12))) if n_gps else np.nan
        mae13 = float(np.mean(np.abs(y13 - g13))) if n_gps else np.nan
        mae23 = float(np.mean(np.abs(y23 - g23))) if n_gps else np.nan

        _plot_pair_1hz(ax2, t_gps, y12, g12, "red",  "GPS 1-2")
        ax2.set_ylabel("Δd [m]")
        ax2.set_xlabel("time [s]")
        ax2.set_ylim(-150, 150)
        ax2.legend([f"TDOA@1Hz MAE={mae12:.2f}", "GPS 1-2"], fontsize="small")

        _plot_pair_1hz(ax4, t_gps, y13, g13, "green", "GPS 1-3")
        ax4.set_ylabel("Δd [m]")
        ax4.set_xlabel("time [s]")
        ax4.set_ylim(-150, 150)
        ax4.legend([f"TDOA@1Hz MAE={mae13:.2f}", "GPS 1-3"], fontsize="small")

        _plot_pair_1hz(ax6, t_gps, y23, g23, "blue", "GPS 2-3")
        ax6.set_ylabel("Δd [m]")
        ax6.set_xlabel("time [s]")
        ax6.set_ylim(-150, 150)
        ax6.legend([f"TDOA@1Hz MAE={mae23:.2f}", "GPS 2-3"], fontsize="small")

    else:
        # ---- STARY TRYB (siatka TDOA) ----
        x_tdoa = np.arange(0, len(TDOAs12_raw), 1) * dt

        def _interp_gps(g, target_len):
            if len(g) < 2 or target_len <= 1:
                return np.array(g[:target_len])
            f = interp1d(np.arange(len(g)), g, kind='cubic', fill_value="extrapolate")
            xi = np.linspace(0, len(g)-1, num=target_len)
            return f(xi)

        g12i = _interp_gps(dist_GPS12, len(TDOAs12_raw))
        g13i = _interp_gps(dist_GPS13, len(TDOAs13_raw))
        g23i = _interp_gps(dist_GPS23, len(TDOAs23_raw))

        mean12 = float(np.mean(np.abs(np.array(g12i) - np.array(TDOAs12_raw)))) if len(TDOAs12_raw) else np.nan
        mean13 = float(np.mean(np.abs(np.array(g13i) - np.array(TDOAs13_raw)))) if len(TDOAs13_raw) else np.nan
        mean23 = float(np.mean(np.abs(np.array(g23i) - np.array(TDOAs23_raw)))) if len(TDOAs23_raw) else np.nan

        ax2.plot(x_tdoa, TDOAs12_raw, label=f"TDOA mean {mean12:.2f}", marker="o", markersize=3, color="red")
        ax2.plot(x_tdoa, g12i,        label="GPS 1-2", marker="x", markersize=3, color="black")
        ax2.set_ylabel("Δd [m]")
        ax2.set_ylim(-150, 150)
        ax2.set_xlabel("Sample index (×dt)")
        ax2.grid()
        ax2.legend(fontsize="small")

        ax4.plot(x_tdoa, TDOAs13_raw, label=f"TDOA mean {mean13:.2f}", marker="o", markersize=3, color="green")
        ax4.plot(x_tdoa, g13i,        label="GPS 1-3", marker="x", markersize=3, color="black")
        ax4.set_ylabel("Δd [m]")
        ax4.set_ylim(-150, 150)
        ax4.set_xlabel("Sample index (×dt)")
        ax4.grid()
        ax4.legend(fontsize="small")

        ax6.plot(x_tdoa, TDOAs23_raw, label=f"TDOA mean {mean23:.2f}", marker="o", markersize=3, color="blue")
        ax6.plot(x_tdoa, g23i,        label="GPS 2-3", marker="x", markersize=3, color="black")
        ax6.set_ylabel("Δd [m]")
        ax6.set_ylim(-150, 150)
        ax6.set_xlabel("Sample index (×dt)")
        ax6.grid()
        ax6.legend(fontsize="small")

    # === MAPA – JEDNA, DUŻA, NA ax_map (wiersz 2+3, lewa) ===

    gdfs = []
    for name, track, color in [
        ("GPS1", GPS1, "red"),
        ("GPS2", GPS2, "green"),
        ("GPS3", GPS3, "blue"),
        ("OP",   GPS_OP, "black"),
    ]:
        if not track:
            continue
        gdf = gpd.GeoDataFrame(
            {"name": [name], "color": [color]},
            geometry=[to_linestring(track)],
            crs="EPSG:4326",
        ).to_crs(3857)
        gdf.plot(ax=ax_map, linewidth=4, color=color, label=name)
        gdfs.append(gdf)

    if est_track and len(est_track) > 1:
        gdf_t = gpd.GeoDataFrame(
            {"name": ["TDOA-EST"], "color": ["purple"]},
            geometry=[to_linestring(est_track)],
            crs="EPSG:4326",
        ).to_crs(3857)
        gdf_t.plot(ax=ax_map, linewidth=4, color="purple", label="TDOA-EST")
        gdfs.append(gdf_t)

    if gdfs:
        total = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True), crs=3857)
        xmin, ymin, xmax, ymax = total.total_bounds
        x_margin = (xmax - xmin) * 0.05
        y_margin = (ymax - ymin) * 0.05
        ax_map.set_xlim(xmin - x_margin, xmax + x_margin)
        ax_map.set_ylim(ymin - y_margin, ymax + y_margin)
        if USE_BASEMAP:
            try:
                cx.add_basemap(ax_map, source=cx.providers.OpenStreetMap.Mapnik, zoom=13)
            except Exception as e:
                print(f"[map] pomijam basemap (contextily): {e}")

    ax_map.set_axis_off()
    ax_map.legend(loc="upper left", fontsize="small")
    ax_map.set_box_aspect(0.8)

    # --- MARKERY START/STOP oraz GPS1/GPS2/GPS3 (pierwsze punkty) ---
    try:
        def _to3857(lat, lon):
            g = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").to_crs(3857)
            return float(g.geometry.iloc[0].x), float(g.geometry.iloc[0].y)

        if GPS_OP and len(GPS_OP) > 1:
            lat_s, lon_s = GPS_OP[0][1],  GPS_OP[0][2]
            lat_e, lon_e = GPS_OP[-1][1], GPS_OP[-1][2]
            xs, ys = _to3857(lat_s, lon_s)
            xe, ye = _to3857(lat_e, lon_e)

            ax_map.scatter(xs, ys, marker='*', s=220, color='limegreen',
                           edgecolor='black', linewidth=1.2, zorder=6)
            ax_map.annotate("START", (xs, ys), xytext=(6, 6), textcoords="offset points",
                            fontsize=9, weight="bold", color="black",
                            bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', boxstyle="round,pad=0.3"),
                            zorder=7)

            ax_map.scatter(xe, ye, marker='P', s=220, color='red',
                           edgecolor='black', linewidth=1.2, zorder=6)
            ax_map.annotate("STOP", (xe, ye), xytext=(6, 6), textcoords="offset points",
                            fontsize=9, weight="bold", color="black",
                            bbox=dict(facecolor='white', alpha=0.7, edgecolor='none', boxstyle="round,pad=0.3"),
                            zorder=7)

        for name, track, color in [("GPS1", GPS1, "red"),
                                   ("GPS2", GPS2, "green"),
                                   ("GPS3", GPS3, "blue")]:
            if track:
                lat0, lon0 = track[0][1], track[0][2]
                x0, y0 = _to3857(lat0, lon0)
                ax_map.scatter(x0, y0, s=60, color=color, edgecolor='white', linewidth=1.0, zorder=6)
                ax_map.annotate(name, (x0, y0), xytext=(8, 8), textcoords="offset points",
                                fontsize=10, fontweight="bold", color=color,
                                bbox=dict(facecolor='white', alpha=0.7, edgecolor=color, boxstyle="round,pad=0.3"),
                                zorder=7)
    except Exception as e:
        print(f"[map] pomijam markery START/STOP/GPS na mapie: {e}")

    plt.tight_layout()
    out_png = f"wynik_z_godz{godz}.png"
    plt.savefig(out_png, dpi=300)
    print("[plot_copy] savefig OK:", out_png)
    plt.close(fig)


# ===== HTML (Folium) z warstwą TDOA-EST + markery START/STOP i GPS1-3 =====

def save_folium_map(GPS1, GPS2, GPS3, GPS_server, out_html, tdoa_track=None):
    def center_latlon(tracks):
        lats = [lat for t in tracks for _, lat, _ in (t or [])]
        lons = [lon for t in tracks for _, _, lon in (t or [])]
        return (sum(lats)/len(lats), sum(lons)/len(lons)) if lats and lons else (0,0)

    m = folium.Map(location=center_latlon([GPS1, GPS2, GPS3, GPS_server]), zoom_start=15)

    for name, track, color in [
        ("GPS1", GPS1, "red"),
        ("GPS2", GPS2, "green"),
        ("GPS3", GPS3, "blue"),
        ("OP",   GPS_server, "black")
    ]:
        if track:
            coords = [(lat, lon) for _, lat, lon in track]
            folium.PolyLine(coords, color=color, weight=3, opacity=0.9, tooltip=name).add_to(m)
            # marker pierwszego punktu każdej ścieżki
            folium.Marker(coords[0], icon=folium.Icon(color="gray", icon="info-sign"),
                          tooltip=f"{name} START").add_to(m)

    # START/STOP dla OP (serwer LAUV)
    if GPS_server and len(GPS_server) > 1:
        op_coords = [(lat, lon) for _, lat, lon in GPS_server]
        folium.Marker(op_coords[0], icon=folium.Icon(color="green"), tooltip="OP START").add_to(m)
        folium.Marker(op_coords[-1], icon=folium.Icon(color="red"), tooltip="OP STOP").add_to(m)

    # TDOA-EST
    if tdoa_track and len(tdoa_track) > 1:
        coords = [(lat, lon) for _, lat, lon in tdoa_track]
        folium.PolyLine(coords, color="purple", weight=4, opacity=0.9, tooltip="TDOA-EST").add_to(m)
        folium.Marker(coords[0], icon=folium.Icon(color="green"), tooltip="TDOA START").add_to(m)
        folium.Marker(coords[-1], icon=folium.Icon(color="red"), tooltip="TDOA STOP").add_to(m)

    folium.LayerControl().add_to(m)
    m.save(out_html)
