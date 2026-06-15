import os
from PyQt5.QtCore import QObject, QPointF, Qt
from PyQt5.QtGui import QColor, QBrush, QFont, QPixmap
from PyQt5.QtWidgets import QWidget, QMessageBox, QGraphicsSimpleTextItem, QGraphicsPixmapItem

from qgis.gui import QgsVertexMarker, QgsRubberBand
from qgis.core import (
    QgsPointXY,
    QgsWkbTypes,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject,
)

import logging

logger = logging.getLogger(__name__)


def wgs84_to_canvas(canvas, point: QgsPointXY) -> QgsPointXY:
    """
    Transform a point from WGS84 (EPSG:4326, x=lon, y=lat in degrees) to the
    canvas destination CRS. If the canvas is already in WGS84 the point is
    returned unchanged, so this is safe to call regardless of the map CRS.
    """
    try:
        dst_crs = canvas.mapSettings().destinationCrs()
        src_crs = QgsCoordinateReferenceSystem("EPSG:4326")

        if not dst_crs.isValid() or dst_crs == src_crs:
            return point

        xform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
        return xform.transform(point)

    except Exception:
        logger.exception("[view] CRS transform WGS84 -> canvas failed; using raw point")
        return point

OUTPUT_CLASSES = [
    "Cisza",
    "Cargo_47",
    "LAUV",
    "Otter",
    "Passengership_109",
    "Ponton_2",
    "Ponton_3",
    "INNE",
]

# Icons for the detected object, matched by substring of the class name.
_OBJECT_ICON_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "OP_figures_png"
)
_OBJECT_ICON_FILES = {
    "LAUV": "LAUV-Bez_napisow.png",
    "Otter": "otter.png",
    "Ponton": "ponton.png",
}


class TargetView(QObject):
    """
    Draws the target position on the QGIS map.

    This class follows the same strategy as ObjectView:
        - one current marker,
        - one timestamp label,
        - optional historical track markers,
        - one polyline connecting historical target positions.

    The controller decides when this view should display, hide or track points.
    """

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas

        # Current measured target marker.
        self.current_marker = QgsVertexMarker(self.canvas)
        self.current_marker.setColor(QColor(0, 0, 0))
        self.current_marker.setIconType(QgsVertexMarker.ICON_DOUBLE_TRIANGLE)
        self.current_marker.setIconSize(9)
        self.current_marker.setPenWidth(3)
        self.current_marker.hide()

        # Optional predicted marker. It is not yet used by the UDP worker,
        # but the interface is ready for future estimators.
        self.predicted_marker = QgsVertexMarker(self.canvas)
        self.predicted_marker.setColor(QColor(255, 0, 0))
        self.predicted_marker.setIconType(QgsVertexMarker.ICON_X)
        self.predicted_marker.setIconSize(9)
        self.predicted_marker.setPenWidth(2)
        self.predicted_marker.hide()

        # Text label placed close to the current marker.
        self.label_item = QGraphicsSimpleTextItem()
        self.label_item.setBrush(QBrush(QColor(0, 0, 0)))
        self.label_item.setFont(QFont("Arial", 9))
        self.label_item.hide()
        self.canvas.scene().addItem(self.label_item)

        # Historical target markers and points.
        self.track_markers = []
        self.track_points = []

        # Polyline connecting tracked points.
        self.track_line = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.track_line.setColor(QColor(0, 0, 0))
        self.track_line.setWidth(1)
        self.track_line.hide()

        self._latest_point = None
        self._latest_timestamp = ""

        # Keep text close to marker after map pan/zoom.
        self.canvas.extentsChanged.connect(self._update_label_position)

    def display_actual_position(
        self,
        point: QgsPointXY,
        timestamp: str = "",
        add_to_track: bool = False,
    ) -> None:
        """
        Display the current target position.

        Parameters
        ----------
        point:
            Target position in map coordinates.

        timestamp:
            Text label displayed next to the marker.

        add_to_track:
            If True, the point is stored as a historical track point.
        """
        self._latest_point = point
        self._latest_timestamp = str(timestamp)

        if add_to_track:
            self._add_track_marker(point)

        self.current_marker.setCenter(point)
        self.current_marker.show()

        if self._latest_timestamp:
            self.label_item.setText(self._latest_timestamp)
            self.label_item.show()
            self._update_label_position()
        else:
            self.label_item.hide()

        self.canvas.refresh()

    def display_predicted_position(
        self,
        point: QgsPointXY,
        timestamp: str = "",
    ) -> None:
        """
        Display the predicted target position.
        """
        self.predicted_marker.setCenter(point)
        self.predicted_marker.show()

        if timestamp:
            logger.info("[TargetView] Predicted target timestamp: %s", timestamp)

        self.canvas.refresh()

    def show_latest(self) -> None:
        """
        Show the latest known target position again.
        """
        if self._latest_point is None:
            return

        self.current_marker.setCenter(self._latest_point)
        self.current_marker.show()

        if self._latest_timestamp:
            self.label_item.setText(self._latest_timestamp)
            self.label_item.show()
            self._update_label_position()

        self.canvas.refresh()

    def hide_target(self) -> None:
        """
        Hide the current target marker, predicted marker and timestamp label.

        The historical track is not deleted.
        """
        self.current_marker.hide()
        self.predicted_marker.hide()
        self.label_item.hide()
        self.canvas.refresh()

    def clear_track(self) -> None:
        """
        Remove all historical target markers and clear the connecting line.

        For consistency with ObjectView, this also hides the current marker and
        timestamp label.
        """
        for marker in self.track_markers:
            marker.hide()
            try:
                self.canvas.scene().removeItem(marker)
            except Exception:
                pass

        self.track_markers.clear()
        self.track_points.clear()

        self.track_line.reset(QgsWkbTypes.LineGeometry)
        self.track_line.hide()

        self.current_marker.hide()
        self.predicted_marker.hide()
        self.label_item.hide()

        self.canvas.refresh()

    def _add_track_marker(self, point: QgsPointXY) -> None:
        """
        Add a small historical target marker and update the target track line.
        """
        marker = QgsVertexMarker(self.canvas)
        marker.setColor(QColor(0, 0, 0))
        marker.setIconType(QgsVertexMarker.ICON_DOUBLE_TRIANGLE)
        marker.setIconSize(5)
        marker.setPenWidth(1)
        marker.setCenter(point)
        marker.show()

        self.track_markers.append(marker)
        self.track_points.append(point)

        self._update_track_line()

    def _update_label_position(self) -> None:
        """
        Keep the timestamp label close to the current marker after pan/zoom.
        """
        if self._latest_point is None:
            return

        try:
            screen_point = self.canvas.getCoordinateTransform().transform(
                self._latest_point.x(),
                self._latest_point.y(),
            )

            self.label_item.setPos(
                QPointF(screen_point.x() + 10, screen_point.y() - 10)
            )

        except Exception:
            # Do not crash the GUI if QGIS coordinate transformation is
            # temporarily unavailable.
            pass

    def _update_track_line(self) -> None:
        """
        Rebuild the polyline connecting all tracked target positions.
        """
        self.track_line.reset(QgsWkbTypes.LineGeometry)

        if len(self.track_points) < 2:
            self.track_line.hide()
            return

        for point in self.track_points:
            self.track_line.addPoint(point, False)

        self.track_line.show()
        self.track_line.updatePosition()
        self.canvas.refresh()


class ReceiverView(QWidget):
    """
    View for displaying a receiver marker on the map.

    Additionally, it can display the latest AKA1A predicted class close to the
    receiver marker.
    """

    def __init__(self, canvas, colour="red", icon_path=None, icon_size=80, parent=None):
        super().__init__(parent)
        self.canvas = canvas

        # Fallback marker (coloured circle) used when no PNG icon is configured
        # or the icon file cannot be loaded.
        self.actual_marker = QgsVertexMarker(self.canvas)
        self.actual_marker.setColor(QColor(colour))
        self.actual_marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
        self.actual_marker.setIconSize(8)
        self.actual_marker.setPenWidth(2)
        self.actual_marker.hide()

        # Optional PNG icon drawn at the receiver position instead of the circle.
        self._icon_size = int(icon_size)
        self.icon_item = QGraphicsPixmapItem()
        self.icon_item.setZValue(15)
        self.icon_item.hide()
        self.canvas.scene().addItem(self.icon_item)
        self._icon_pixmap = self._load_icon(icon_path)

        self.class_label_item = QGraphicsSimpleTextItem()
        self.class_label_item.setBrush(QBrush(QColor(0, 0, 0)))
        self.class_label_item.setFont(QFont("Arial", 9))
        self.class_label_item.hide()
        self.canvas.scene().addItem(self.class_label_item)

        self._latest_point: QgsPointXY | None = None
        self._latest_class_text: str = ""

        self.canvas.extentsChanged.connect(self._update_class_label_position)
        self.canvas.extentsChanged.connect(self._update_icon_position)

    def _load_icon(self, icon_path):
        """
        Load and scale the receiver PNG icon. Relative paths are resolved
        against the project root. Returns a scaled QPixmap, or None if no icon
        is configured or the file is missing/invalid (caller falls back to the
        coloured circle).
        """
        if not icon_path:
            return None

        path = icon_path
        if not os.path.isabs(path):
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            path = os.path.join(base, icon_path)

        pix = QPixmap(path)
        if pix.isNull():
            logger.warning("[ReceiverView] Nie udalo sie wczytac ikony: %s", path)
            return None

        return pix.scaled(
            self._icon_size, self._icon_size,
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )

    def display_actual_position(self, point: QgsPointXY):
        self._latest_point = point

        if self._icon_pixmap is not None:
            self.icon_item.setPixmap(self._icon_pixmap)
            self.icon_item.show()
            self._update_icon_position()
            self.actual_marker.hide()
        else:
            self.actual_marker.setCenter(point)
            self.actual_marker.show()

        if self._latest_class_text:
            self.class_label_item.show()
            self._update_class_label_position()

        self.canvas.refresh()

    def _update_icon_position(self) -> None:
        """Keep the PNG icon centred on the receiver point after pan/zoom."""
        if self._latest_point is None or self._icon_pixmap is None:
            return
        if not self.icon_item.isVisible():
            return
        try:
            sp = self.canvas.getCoordinateTransform().transform(
                self._latest_point.x(), self._latest_point.y()
            )
            pm = self.icon_item.pixmap()
            self.icon_item.setPos(
                QPointF(sp.x() - pm.width() / 2.0, sp.y() - pm.height() / 2.0)
            )
        except Exception:
            pass

    def display_classification_result(self, pred_class: int) -> None:
        """
        Display the latest predicted class close to the receiver marker.

        The text is updated after every completed calculation job.
        """
        #self._latest_class_text = str(int(pred_class))
        self._latest_class_text = OUTPUT_CLASSES[pred_class]
        self.class_label_item.setText(f"Detect: {self._latest_class_text}")

        if self._latest_point is not None:
            self.class_label_item.show()
            self._update_class_label_position()

        self.canvas.refresh()

    def _update_class_label_position(self) -> None:
        """
        Keep the classification label close to the receiver marker after map
        panning or zooming.
        """
        if self._latest_point is None:
            return

        try:
            screen_point = self.canvas.getCoordinateTransform().transform(
                self._latest_point.x(),
                self._latest_point.y(),
            )

            self.class_label_item.setPos(
                QPointF(
                    screen_point.x() - self.icon_item.pixmap().width()/2, 
                    screen_point.y() - self.icon_item.pixmap().height()/2 - 12
                )
            )

        except Exception:
            pass

    def show_warning(self, title: str, message: str):
        m = QMessageBox(self)
        m.setIcon(QMessageBox.Warning)
        m.setWindowTitle(title)
        m.setText(message)
        m.exec_()


class ObjectView(QObject):
    """
    Draws the calculated object position on the map.
    """

    _MARKER_ICONS = {
        "box": QgsVertexMarker.ICON_BOX,
        "cross": QgsVertexMarker.ICON_CROSS,
        "x": QgsVertexMarker.ICON_X,
        "circle": QgsVertexMarker.ICON_CIRCLE,
    }

    def __init__(self, canvas, colour=QColor(255, 0, 0), marker_icon="box", parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self._colour = QColor(colour)
        self._marker_icon = self._MARKER_ICONS.get(marker_icon, QgsVertexMarker.ICON_BOX)

        self.current_marker = QgsVertexMarker(self.canvas)
        self.current_marker.setColor(self._colour)
        self.current_marker.setIconType(self._marker_icon)
        self.current_marker.setIconSize(9)
        self.current_marker.setPenWidth(3)
        self.current_marker.hide()

        self.label_item = QGraphicsSimpleTextItem()
        self.label_item.setBrush(QBrush(self._colour))
        self.label_item.setFont(QFont("Arial", 9))
        self.label_item.hide()
        self.canvas.scene().addItem(self.label_item)

        self.track_markers = []
        self.track_points = []

        self.track_line = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.track_line.setColor(self._colour)
        self.track_line.setWidth(1)
        self.track_line.hide()

        # Small icon (LAUV/Otter/Ponton) shown at the object position.
        self.icon_item = QGraphicsPixmapItem()
        self.icon_item.setZValue(20)
        self.icon_item.hide()
        self.canvas.scene().addItem(self.icon_item)
        self._icon_cache = {}
        self._icon_size = 72  # px

        self._latest_point = None
        self._latest_timestamp = ""

        # Keep the text/icon close to the marker after panning/zooming.
        self.canvas.extentsChanged.connect(self._update_label_position)
        self.canvas.extentsChanged.connect(self._update_icon_position)

    def set_object_icon(self, pred_class: int) -> None:
        """
        Set the object icon from the detected class (index into OUTPUT_CLASSES).
        Classes without a matching icon (e.g. 'Cisza') hide the icon.
        """
        try:
            name = OUTPUT_CLASSES[pred_class] if 0 <= pred_class < len(OUTPUT_CLASSES) else ""
        except Exception:
            name = ""

        key = None
        for k in _OBJECT_ICON_FILES:
            if k.lower() in name.lower():
                key = k
                break

        if key is None:
            self.icon_item.hide()
            return

        pix = self._icon_cache.get(key)
        if pix is None:
            path = os.path.join(_OBJECT_ICON_DIR, _OBJECT_ICON_FILES[key])
            p = QPixmap(path)
            if not p.isNull():
                p = p.scaled(
                    self._icon_size, self._icon_size,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
            pix = p
            self._icon_cache[key] = pix

        if pix.isNull():
            self.icon_item.hide()
            return

        self.icon_item.setPixmap(pix)
        # Only show once we have an object position (Object1 displayed); avoids a
        # stray icon at the map origin when Object1 display is off.
        if self._latest_point is not None:
            self.icon_item.show()
            self._update_icon_position()
        else:
            self.icon_item.hide()

    def _update_icon_position(self) -> None:
        if self._latest_point is None:
            return
        pm = self.icon_item.pixmap()
        if pm.isNull() or not self.icon_item.isVisible():
            return
        try:
            sp = self.canvas.getCoordinateTransform().transform(
                self._latest_point.x(), self._latest_point.y()
            )
            # Centre the icon above the marker so it does not cover the point.
            self.icon_item.setPos(
                QPointF(sp.x() - pm.width() / 2.0, sp.y() - pm.height() - 6)
            )
        except Exception:
            pass

    def display_position(
        self,
        point: QgsPointXY,
        timestamp: str,
        add_to_track: bool = False,
    ) -> None:
        """
        Display the current object position and timestamp.

        If add_to_track is True, the point is also stored as a historical
        track marker.
        """
        point = wgs84_to_canvas(self.canvas, point)
        self._latest_point = point
        self._latest_timestamp = timestamp

        if add_to_track:
            self._add_track_marker(point)

        self.current_marker.setCenter(point)
        self.current_marker.show()

        self.label_item.setText(timestamp)
        self.label_item.show()
        self._update_label_position()
        self._update_icon_position()

        self.canvas.refresh()

    def show_latest(self) -> None:
        """
        Show the last known object position again.
        """
        if self._latest_point is None:
            return

        self.current_marker.setCenter(self._latest_point)
        self.current_marker.show()

        self.label_item.setText(self._latest_timestamp)
        self.label_item.show()
        self._update_label_position()
        self._update_icon_position()

        self.canvas.refresh()

    def hide_object(self) -> None:
        """
        Hide the current object marker and timestamp.
        The stored track is not deleted.
        """
        self.current_marker.hide()
        self.label_item.hide()
        self.icon_item.hide()
        self.canvas.refresh()

    def clear_track(self) -> None:
        """
        Remove all historical track markers, clear the connecting line,
        and hide the current marker and timestamp.
        """
        for marker in self.track_markers:
            marker.hide()
            try:
                self.canvas.scene().removeItem(marker)
            except Exception:
                pass

        self.track_markers.clear()
        self.track_points.clear()

        self.track_line.reset(QgsWkbTypes.LineGeometry)
        self.track_line.hide()

        self.current_marker.hide()
        self.label_item.hide()
        self.icon_item.hide()

        self.canvas.refresh()

    def _add_track_marker(self, point: QgsPointXY) -> None:
        """
        Add a small historical marker and extend the tracking polyline.
        """
        marker = QgsVertexMarker(self.canvas)
        marker.setColor(self._colour)
        marker.setIconType(self._marker_icon)
        marker.setIconSize(5)
        marker.setPenWidth(1)
        marker.setCenter(point)
        marker.show()

        self.track_markers.append(marker)
        self.track_points.append(point)

        self._update_track_line()

    def _update_label_position(self) -> None:
        """
        Reposition the timestamp label near the current marker.
        """
        if self._latest_point is None:
            return

        try:
            screen_point = self.canvas.getCoordinateTransform().transform(
                self._latest_point.x(),
                self._latest_point.y(),
            )

            self.label_item.setPos(
                QPointF(screen_point.x() + 10, screen_point.y() - 10)
            )

        except Exception:
            # If coordinate transformation fails, do not crash the GUI.
            pass

    def _update_track_line(self) -> None:
        """
        Object track shows markers only (no connecting line) — for noisy TDOA
        estimates a polyline exaggerates the zigzag, so it is kept hidden.
        """
        self.track_line.reset(QgsWkbTypes.LineGeometry)
        self.track_line.hide()
        self.canvas.refresh()


class ReferenceTrackView(QObject):
    """
    Draws the ground-truth (reference) track of a measured object
    (LAUV / Otter / Ponton) as a polyline, for visual comparison with the
    estimated object position (ObjectView / Est_pos).

    Points are provided in WGS84 degrees (lat, lon) and transformed to the
    canvas CRS before drawing.
    """

    def __init__(self, canvas, colour=QColor(0, 100, 255), parent=None):
        super().__init__(parent)
        self.canvas = canvas

        self.track_line = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.track_line.setColor(colour)
        self.track_line.setWidth(2)
        self.track_line.hide()

        # Start marker + object label.
        self.start_marker = QgsVertexMarker(self.canvas)
        self.start_marker.setColor(colour)
        self.start_marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
        self.start_marker.setIconSize(7)
        self.start_marker.setPenWidth(2)
        self.start_marker.hide()

        self.label_item = QGraphicsSimpleTextItem()
        self.label_item.setBrush(QBrush(colour))
        self.label_item.setFont(QFont("Arial", 9))
        self.label_item.hide()
        self.canvas.scene().addItem(self.label_item)

        self._first_point = None
        self._label_text = ""
        self._colour = colour
        self._point_markers = []

        self.canvas.extentsChanged.connect(self._update_label_position)

    def _clear_point_markers(self) -> None:
        for m in self._point_markers:
            m.hide()
            try:
                self.canvas.scene().removeItem(m)
            except Exception:
                pass
        self._point_markers.clear()

    def draw_track(self, object_name: str, points: list) -> None:
        """
        points: list of (lat, lon) tuples in WGS84 degrees.
        """
        self.track_line.reset(QgsWkbTypes.LineGeometry)
        self._clear_point_markers()

        if not points:
            self.clear()
            return

        first = None
        for lat, lon in points:
            p = wgs84_to_canvas(self.canvas, QgsPointXY(lon, lat))
            if first is None:
                first = p

            # Markers only (no connecting line) at each estimation-time point.
            m = QgsVertexMarker(self.canvas)
            m.setColor(self._colour)
            m.setIconType(QgsVertexMarker.ICON_CROSS)
            m.setIconSize(6)
            m.setPenWidth(2)
            m.setCenter(p)
            m.show()
            self._point_markers.append(m)

        # Connecting line intentionally not drawn (markers only).
        self.track_line.hide()

        self._first_point = first
        self._label_text = f"{object_name} (ref)"
        if first is not None:
            self.start_marker.setCenter(first)
            self.start_marker.show()
            self.label_item.setText(self._label_text)
            self.label_item.show()
            self._update_label_position()

        self.canvas.refresh()

    def clear(self) -> None:
        self.track_line.reset(QgsWkbTypes.LineGeometry)
        self.track_line.hide()
        self.start_marker.hide()
        self.label_item.hide()
        self._clear_point_markers()
        self._first_point = None
        self.canvas.refresh()

    def _update_label_position(self) -> None:
        if self._first_point is None:
            return
        try:
            screen_point = self.canvas.getCoordinateTransform().transform(
                self._first_point.x(),
                self._first_point.y(),
            )
            self.label_item.setPos(
                QPointF(screen_point.x() + 10, screen_point.y() - 10)
            )
        except Exception:
            pass


# from PyQt5.QtCore import QObject
# from qgis.gui import QgsVertexMarker, QgsRubberBand
# from qgis.core import QgsPointXY, QgsWkbTypes
# from PyQt5.QtGui import QColor
# from PyQt5.QtWidgets import QWidget, QMessageBox
# from PyQt5.QtCore import QPointF
# from PyQt5.QtGui import QColor, QBrush, QFont
# from PyQt5.QtWidgets import QWidget, QMessageBox, QGraphicsSimpleTextItem

# import logging
# logger = logging.getLogger(__name__)

# class TargetView(QObject):
#     """
#     Draws the target's actual and predicted positions on the map.
#     """
#     def __init__(self, canvas, parent=None):
#         super().__init__(parent)
#         self.canvas = canvas

#         self.actual_marker = QgsVertexMarker(self.canvas)
#         self.actual_marker.setColor(QColor(0, 0, 0))
#         self.actual_marker.setIconType(QgsVertexMarker.ICON_DOUBLE_TRIANGLE)
#         self.actual_marker.setIconSize(8)
#         self.actual_marker.setPenWidth(2)
#         self.actual_marker.hide()

#         self.predicted_marker = QgsVertexMarker(self.canvas)
#         self.predicted_marker.setColor(QColor(255, 0, 0))
#         self.predicted_marker.setIconType(QgsVertexMarker.ICON_X)
#         self.predicted_marker.setIconSize(8)
#         self.predicted_marker.setPenWidth(2)
#         self.predicted_marker.hide()

#     def display_actual_position(self, point: QgsPointXY):
#         self.actual_marker.setCenter(point)
#         self.actual_marker.show()
#         self.canvas.refresh()

#     def display_predicted_position(self, point: QgsPointXY):
#         self.predicted_marker.setCenter(point)
#         self.predicted_marker.show()
#         self.canvas.refresh()

#     def clear_track(self):
#         self.actual_marker.hide()
#         self.predicted_marker.hide()
#         self.canvas.refresh()


# class ReceiverView(QWidget):
#     """
#     View for displaying a receiver (marker, info) on the map.
#     """
#     def __init__(self, canvas, colour="red",parent=None):
#         super().__init__(parent)
#         self.canvas = canvas
#         self.actual_marker = QgsVertexMarker(self.canvas)
#         self.actual_marker.setColor(QColor(colour))
#         self.actual_marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
#         self.actual_marker.setIconSize(8)
#         self.actual_marker.setPenWidth(2)
#         self.actual_marker.hide()
        
#     def display_actual_position(self, point: QgsPointXY):
#         self.actual_marker.setCenter(point)
#         self.actual_marker.show()
#         self.canvas.refresh()
#         ##print(f"[{self.__class__.__name__}] Current position was displayed on the map: {point.x()}, {point.y()}")
    
#     def show_warning(self, title: str, message: str):
#         m = QMessageBox(self)
#         m.setIcon(QMessageBox.Warning)
#         m.setWindowTitle(title)
#         m.setText(message)
#         m.exec_()

# class ObjectView(QObject):
#     """
#     Draws the calculated object position on the map.
#     """

#     def __init__(self, canvas, parent=None):
#         super().__init__(parent)
#         self.canvas = canvas

#         self.current_marker = QgsVertexMarker(self.canvas)
#         self.current_marker.setColor(QColor(0, 0, 0))
#         self.current_marker.setIconType(QgsVertexMarker.ICON_BOX)
#         self.current_marker.setIconSize(9)
#         self.current_marker.setPenWidth(3)
#         self.current_marker.hide()

#         self.label_item = QGraphicsSimpleTextItem()
#         self.label_item.setBrush(QBrush(QColor(0, 0, 0)))
#         self.label_item.setFont(QFont("Arial", 9))
#         self.label_item.hide()
#         self.canvas.scene().addItem(self.label_item)

#         self.track_markers = []
#         self.track_points = []

#         self.track_line = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
#         self.track_line.setColor(QColor(0, 0, 0))
#         self.track_line.setWidth(1)
#         self.track_line.hide()

#         self._latest_point = None
#         self._latest_timestamp = ""

#         # Keep the text close to the marker after panning/zooming.
#         self.canvas.extentsChanged.connect(self._update_label_position)

#     def display_position(
#         self,
#         point: QgsPointXY,
#         timestamp: str,
#         add_to_track: bool = False,
#     ) -> None:
#         """
#         Display the current object position and timestamp.

#         If add_to_track is True, the point is also stored as a historical
#         track marker.
#         """
#         self._latest_point = point
#         self._latest_timestamp = timestamp

#         if add_to_track:
#             self._add_track_marker(point)

#         self.current_marker.setCenter(point)
#         self.current_marker.show()

#         self.label_item.setText(timestamp)
#         self.label_item.show()
#         self._update_label_position()

#         self.canvas.refresh()

#     def show_latest(self) -> None:
#         """
#         Show the last known object position again.
#         """
#         if self._latest_point is None:
#             return

#         self.current_marker.setCenter(self._latest_point)
#         self.current_marker.show()

#         self.label_item.setText(self._latest_timestamp)
#         self.label_item.show()
#         self._update_label_position()

#         self.canvas.refresh()

#     def hide_object(self) -> None:
#         """
#         Hide the current object marker and timestamp.
#         The stored track is not deleted.
#         """
#         self.current_marker.hide()
#         self.label_item.hide()
#         self.canvas.refresh()

#     def clear_track(self) -> None:
#         """
#         Remove all historical track markers, clear the connecting line,
#         and hide the current marker and timestamp.
#         """
#         for marker in self.track_markers:
#             marker.hide()
#             try:
#                 self.canvas.scene().removeItem(marker)
#             except Exception:
#                 pass

#         self.track_markers.clear()
#         self.track_points.clear()

#         self.track_line.reset(QgsWkbTypes.LineGeometry)
#         self.track_line.hide()

#         self.current_marker.hide()
#         self.label_item.hide()

#         self.canvas.refresh()

#     def _add_track_marker(self, point: QgsPointXY) -> None:
#         """
#         Add a small historical marker and extend the tracking polyline.
#         """
#         marker = QgsVertexMarker(self.canvas)
#         marker.setColor(QColor(0, 0, 0))
#         marker.setIconType(QgsVertexMarker.ICON_BOX)
#         marker.setIconSize(5)
#         marker.setPenWidth(1)
#         marker.setCenter(point)
#         marker.show()

#         self.track_markers.append(marker)
#         self.track_points.append(point)

#         self._update_track_line()

#     def _update_label_position(self) -> None:
#         """
#         Reposition the timestamp label near the current marker.
#         """
#         if self._latest_point is None:
#             return

#         try:
#             screen_point = self.canvas.getCoordinateTransform().transform(
#                 self._latest_point.x(),
#                 self._latest_point.y(),
#             )

#             self.label_item.setPos(
#                 QPointF(screen_point.x() + 10, screen_point.y() - 10)
#             )

#         except Exception:
#             # If coordinate transformation fails, do not crash the GUI.
#             pass

#     def _update_track_line(self) -> None:
#         """
#         Rebuild the polyline connecting all tracked object positions.
#         """
#         self.track_line.reset(QgsWkbTypes.LineGeometry)

#         if len(self.track_points) < 2:
#             self.track_line.hide()
#             return

#         for point in self.track_points:
#             self.track_line.addPoint(point, False)

#         self.track_line.show()
#         self.track_line.updatePosition()
#         self.canvas.refresh()
