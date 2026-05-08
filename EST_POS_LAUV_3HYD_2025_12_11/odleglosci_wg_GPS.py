from geopy.distance import geodesic
import numpy as np

# ===================== Dane do weryfikacji estymacji pozycji =====================
def vincenty_distance(latA, lonA, latB, lonB):
    return geodesic((latA, lonA), (latB, lonB)).meters

def GPS_dist_Vincenty(GPSA, GPSB, GPS_OP):
    """Różnice odległości względem OP: (OP->A) - (OP->B)"""
    dist_GPS = []
    n = min(len(GPSA), len(GPSB), len(GPS_OP))
    for i in range(n):
        _, lat1, lon1 = GPSA[i]
        _, lat2, lon2 = GPSB[i]
        _, lat3, lon3 = GPS_OP[i]
        d31 = vincenty_distance(lat3, lon3, lat1, lon1)
        d32 = vincenty_distance(lat3, lon3, lat2, lon2)
        dist_GPS.append(d31 - d32)
    return np.asarray(dist_GPS, dtype=float)