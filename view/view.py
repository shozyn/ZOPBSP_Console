from PyQt5.QtCore import QObject
from qgis.gui import QgsVertexMarker
from qgis.core import QgsPointXY
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget

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
        print(f"[{self.__class__.__name__}] triggered. Point: {point}")
        self.actual_marker.setCenter(point)
        self.actual_marker.show()
        self.canvas.refresh()
