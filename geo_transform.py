import math
from qgis.core import QgsPointXY, QgsPoint

class GeoTransform:
    m_PI = 3.14159265
    deg2rad = m_PI / 180.0
    rad2deg = 180.0 / m_PI
    m_originLatLon = QgsPointXY(53.83648542, 17.64690432)  # Default origin

    @staticmethod
    def latLong2LocalGrid(pointLatLon: QgsPointXY) -> QgsPointXY:
        a = 6378137
        b = 6356752

        tan_lat2 = math.tan(pointLatLon.y() * GeoTransform.deg2rad) ** 2
        radius = b * math.sqrt(1 + tan_lat2) / math.sqrt((b**2 / a**2) + tan_lat2)

        dx_arc = (pointLatLon.x() - GeoTransform.m_originLatLon.y()) * GeoTransform.deg2rad
        dx = radius * math.sin(dx_arc) * math.cos(pointLatLon.y() * GeoTransform.deg2rad)

        dy_arc = (pointLatLon.y() - GeoTransform.m_originLatLon.x()) * GeoTransform.deg2rad
        dy = radius * math.sin(dy_arc)

        pointMetersNorthEast = QgsPointXY()
        pointMetersNorthEast.setX(dy)
        pointMetersNorthEast.setY(dx)
        return pointMetersNorthEast

    @staticmethod
    def localGrid2LatLong(dfGridNorthEast: QgsPointXY) -> QgsPointXY:
        a = 6378137
        b = 6356752

        tan_lat2 = math.tan(GeoTransform.m_originLatLon.x() * GeoTransform.deg2rad) ** 2
        radius = b * math.sqrt(1 + tan_lat2) / math.sqrt((b**2 / a**2) + tan_lat2)

        dy_arc_rad = math.asin(dfGridNorthEast.x() / radius)
        dy_arc_deg = dy_arc_rad * GeoTransform.rad2deg

        dx_arc_rad = math.asin(dfGridNorthEast.y() / (radius * math.cos(GeoTransform.m_originLatLon.x() * GeoTransform.deg2rad)))
        dx_arc_deg = dx_arc_rad * GeoTransform.rad2deg

        dfLatLon = QgsPointXY()
        dfLatLon.setY(dy_arc_deg + GeoTransform.m_originLatLon.x())
        dfLatLon.setX(dx_arc_deg + GeoTransform.m_originLatLon.y())
        return dfLatLon

    @staticmethod
    def latLong2LocalGrid_QgsPoint(pointLatLon: QgsPoint) -> QgsPoint:
        a = 6378137
        b = 6356752

        tan_lat2 = math.tan(pointLatLon.y() * GeoTransform.deg2rad) ** 2
        radius = b * math.sqrt(1 + tan_lat2) / math.sqrt((b**2 / a**2) + tan_lat2)

        dx_arc = (pointLatLon.x() - GeoTransform.m_originLatLon.y()) * GeoTransform.deg2rad
        dx = radius * math.sin(dx_arc) * math.cos(pointLatLon.y() * GeoTransform.deg2rad)

        dy_arc = (pointLatLon.y() - GeoTransform.m_originLatLon.x()) * GeoTransform.deg2rad
        dy = radius * math.sin(dy_arc)

        pointMetersNorthEast = QgsPoint()
        pointMetersNorthEast.setX(dy)
        pointMetersNorthEast.setY(dx)
        return pointMetersNorthEast

    @staticmethod
    def localGrid2LatLong_QgsPoint(dfGridNorthEast: QgsPoint) -> QgsPoint:
        a = 6378137
        b = 6356752

        tan_lat2 = math.tan(GeoTransform.m_originLatLon.x() * GeoTransform.deg2rad) ** 2
        radius = b * math.sqrt(1 + tan_lat2) / math.sqrt((b**2 / a**2) + tan_lat2)

        dy_arc_rad = math.asin(dfGridNorthEast.x() / radius)
        dy_arc_deg = dy_arc_rad * GeoTransform.rad2deg

        dx_arc_rad = math.asin(dfGridNorthEast.y() / (radius * math.cos(GeoTransform.m_originLatLon.x() * GeoTransform.deg2rad)))
        dx_arc_deg = dx_arc_rad * GeoTransform.rad2deg

        dfLatLon = QgsPoint()
        dfLatLon.setY(dy_arc_deg + GeoTransform.m_originLatLon.x())
        dfLatLon.setX(dx_arc_deg + GeoTransform.m_originLatLon.y())
        return True

    @staticmethod
    def setOriginLocalisationFromString(loc: str):
        parts = loc.split(',')
        if len(parts) != 2:
            raise ValueError("Invalid location string: expected 'lat,lon'")
        lat = float(parts[0].strip())
        lon = float(parts[1].strip())
        GeoTransform.m_originLatLon = QgsPointXY(lat, lon)

    @staticmethod
    def setOriginLocalisationFromPoint(qgsLoc: QgsPointXY):
        GeoTransform.m_originLatLon = qgsLoc

    @staticmethod
    def getOriginLocalisation() -> QgsPointXY:
        return GeoTransform.m_originLatLon
