from PyQt5.QtCore import QObject
from qgis.gui import QgsVertexMarker, QgsRubberBand
from qgis.core import QgsPointXY, QgsWkbTypes
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QMessageBox
from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QColor, QBrush, QFont
from PyQt5.QtWidgets import QWidget, QMessageBox, QGraphicsSimpleTextItem

import logging
logger = logging.getLogger(__name__)

class TargetView(QObject):
    """
    Draws the target's actual and predicted positions on the map.
    """
    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas

        self.actual_marker = QgsVertexMarker(self.canvas)
        self.actual_marker.setColor(QColor(0, 0, 0))
        self.actual_marker.setIconType(QgsVertexMarker.ICON_DOUBLE_TRIANGLE)
        self.actual_marker.setIconSize(8)
        self.actual_marker.setPenWidth(2)
        self.actual_marker.hide()

        self.predicted_marker = QgsVertexMarker(self.canvas)
        self.predicted_marker.setColor(QColor(255, 0, 0))
        self.predicted_marker.setIconType(QgsVertexMarker.ICON_X)
        self.predicted_marker.setIconSize(8)
        self.predicted_marker.setPenWidth(2)
        self.predicted_marker.hide()

    def display_actual_position(self, point: QgsPointXY):
        self.actual_marker.setCenter(point)
        self.actual_marker.show()
        self.canvas.refresh()

    def display_predicted_position(self, point: QgsPointXY):
        self.predicted_marker.setCenter(point)
        self.predicted_marker.show()
        self.canvas.refresh()

    def clear_track(self):
        self.actual_marker.hide()
        self.predicted_marker.hide()
        self.canvas.refresh()


class ReceiverView(QWidget):
    """
    View for displaying a receiver (marker, info) on the map.
    """
    def __init__(self, canvas, colour="red",parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.actual_marker = QgsVertexMarker(self.canvas)
        self.actual_marker.setColor(QColor(colour))
        self.actual_marker.setIconType(QgsVertexMarker.ICON_CIRCLE)
        self.actual_marker.setIconSize(8)
        self.actual_marker.setPenWidth(2)
        self.actual_marker.hide()
        
    def display_actual_position(self, point: QgsPointXY):
        self.actual_marker.setCenter(point)
        self.actual_marker.show()
        self.canvas.refresh()
        ##print(f"[{self.__class__.__name__}] Current position was displayed on the map: {point.x()}, {point.y()}")
    
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

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas

        self.current_marker = QgsVertexMarker(self.canvas)
        self.current_marker.setColor(QColor(0, 0, 0))
        self.current_marker.setIconType(QgsVertexMarker.ICON_BOX)
        self.current_marker.setIconSize(9)
        self.current_marker.setPenWidth(3)
        self.current_marker.hide()

        self.label_item = QGraphicsSimpleTextItem()
        self.label_item.setBrush(QBrush(QColor(0, 0, 0)))
        self.label_item.setFont(QFont("Arial", 9))
        self.label_item.hide()
        self.canvas.scene().addItem(self.label_item)

        self.track_markers = []
        self.track_points = []

        self.track_line = QgsRubberBand(self.canvas, QgsWkbTypes.LineGeometry)
        self.track_line.setColor(QColor(0, 0, 0))
        self.track_line.setWidth(1)
        self.track_line.hide()

        self._latest_point = None
        self._latest_timestamp = ""

        # Keep the text close to the marker after panning/zooming.
        self.canvas.extentsChanged.connect(self._update_label_position)

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
        self._latest_point = point
        self._latest_timestamp = timestamp

        if add_to_track:
            self._add_track_marker(point)

        self.current_marker.setCenter(point)
        self.current_marker.show()

        self.label_item.setText(timestamp)
        self.label_item.show()
        self._update_label_position()

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

        self.canvas.refresh()

    def hide_object(self) -> None:
        """
        Hide the current object marker and timestamp.
        The stored track is not deleted.
        """
        self.current_marker.hide()
        self.label_item.hide()
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

        self.canvas.refresh()

    def _add_track_marker(self, point: QgsPointXY) -> None:
        """
        Add a small historical marker and extend the tracking polyline.
        """
        marker = QgsVertexMarker(self.canvas)
        marker.setColor(QColor(0, 0, 0))
        marker.setIconType(QgsVertexMarker.ICON_BOX)
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
        Rebuild the polyline connecting all tracked object positions.
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
