from PyQt5.QtCore import QObject, pyqtSignal
from qgis.core import QgsPointXY
from typing import Any, Optional
import inspect

class TargetModel(QObject):
    """
    Model representing a single target (real and predicted positions).
    """
    actual_position_updated = pyqtSignal(QgsPointXY)
    predicted_position_updated = pyqtSignal(QgsPointXY)

    def __init__(self, target_id, ip, port, parent=None):
        super().__init__(parent)
        self.target_id = target_id
        self.ip = ip
        self.port = port
        self.actual_position = None
        self.predicted_position = None

        self.actual_position_updated.connect(lambda p: print(f"Actual: {p}"))
        #target.predicted_position_updated.connect(lambda p: print(f"Predicted: {p}"))

    def update_actual_position(self, lat, lon):
        #self.actual_position = QgsPointXY(lon, lat)
        print(f"[{self.__class__.__name__}] Slot activated: {inspect.currentframe().f_code.co_name}; {lat, lon}")
        self.actual_position = QgsPointXY(18.54534607666666801, 54.5435800300000011)
        self.actual_position_updated.emit(self.actual_position)

    def update_predicted_position(self, point: QgsPointXY):
        self.predicted_position = point
        self.predicted_position_updated.emit(self.predicted_position)

class ReceiverModel(QObject): 
    def __init__(self, receiver_id, parameters,sftp_cfg, parent=None):
        super().__init__(parent)
        self.receiver_id = receiver_id
        self.parameters = parameters
        self.sftp_cfg = sftp_cfg

    def set_parameter_control(self, name: str, value: Any) -> None:
        """Update the parameter value (for dialog/UI update)."""
        if name in self.parameters["param_control"]:
            self.parameters["param_control"][name]['value'] = value

            
    def set_parameter_monitor(self, name: str, value: Any) -> None:
        """Update the parameter value (for dialog/UI update)."""
        if name in self.parameters["param_monitor"]:
            self.parameters["param_monitor"][name]['value'] = value

            
    def get_sftp_cfg(self, name: str) -> Optional[any]:
        """Return the parameter's value for a given name."""
        if name in self.sftp_cfg:
            return self.sftp_cfg.get(name)
        else:
            return None

    def set_sftp_cfg(self, name: str, value: Any) -> None:
        """Update the parameter value (for dialog/UI update)."""
        if name in self.parameters:
            self.parasftp_cfgmeters[name]['value'] = value

class ProjectModel(QObject):
    """
    Model representing project/global state.
    """
    project_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_data = {}

    def update_project(self, new_data):
        self.project_data = new_data
        self.project_changed.emit(new_data)
class MapModel(QObject):
    """
    Model holding the state of the map (layers, selections, etc.).
    """
    layers_changed = pyqtSignal(list)  # Emit the full list of layers

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layers = []  # List of QgsMapLayer objects

    def add_layer(self, layer):
        self.layers.append(layer)
        self.layers_changed.emit(self.layers[:])

    def remove_layer(self, layer):
        self.layers.remove(layer)
        self.layers_changed.emit(self.layers[:])

    def select_feature(self, feature_id):
        self.selected_features.append(feature_id)
        self.selection_changed.emit()

