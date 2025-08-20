from PyQt5.QtCore import QObject, pyqtSignal
from qgis.core import QgsPointXY
from typing import Any
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
    status_changed = pyqtSignal(object)  # For UI/status updates
    def __init__(self, receiver_id, parameters,sftp_cfg, parent=None):
        super().__init__(parent)
        self.receiver_id = receiver_id
        self.parameters = parameters
        self.sftp_cfg = sftp_cfg
    def get_parameter(self, name: str) -> Any:
        """Return the parameter's dict or value for a given name."""
        return self.parameters.get(name)

    def set_parameter(self, name: str, value: Any) -> None:
        """Update the parameter value (for dialog/UI update)."""
        if name in self.parameters:
            self.parameters[name]['value'] = value
            self.status_changed.emit(self.parameters)
        else:
            # Optionally: support new parameters added at runtime
            self.parameters[name] = {'value': value}
            self.status_changed.emit(self.sftp_cfg)

    def get_sftp_cfg(self, name: str) -> Any:
        """Return the parameter's dict or value for a given name."""
        return self.sftp_cfg.get(name)

    def set_sftp_cfg(self, name: str, value: Any) -> None:
        """Update the parameter value (for dialog/UI update)."""
        if name in self.parameters:
            self.parasftp_cfgmeters[name]['value'] = value
            self.status_changed.emit(self.parameters)
        else:
            # Optionally: support new parameters added at runtime
            self.parameters[name] = {'value': value}
            self.status_changed.emit(self.sftp_cfg)

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

