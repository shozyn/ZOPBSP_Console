from PyQt5.QtCore import QObject, pyqtSignal
from qgis.core import QgsPointXY
from typing import Any, Optional
import logging
from typing import Optional

logger = logging.getLogger(__name__)

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

        #self.actual_position_updated.connect(lambda p: print(f"Actual: {p}"))
        #target.predicted_position_updated.connect(lambda p: print(f"Predicted: {p}"))

    def update_actual_position(self, lat, lon):
        self.actual_position = QgsPointXY(lon, lat)
        #print(f"[{self.__class__.__name__}] Slot activated: {inspect.currentframe().f_code.co_name}; {lat, lon}")
        #self.actual_position = QgsPointXY(18.54534607666666801, 54.5435800300000011)
        self.actual_position_updated.emit(self.actual_position)

    def update_predicted_position(self, point: QgsPointXY):
        self.predicted_position = point
        self.predicted_position_updated.emit(self.predicted_position)

class ReceiverModel(QObject): 
    actual_position_updated = pyqtSignal(QgsPointXY)
    def __init__(self, receiver_id, parameters,sftp_cfg, parent=None):
        super().__init__(parent)
        self.receiver_id = receiver_id
        self.parameters = parameters
        self.sftp_cfg = sftp_cfg
        self.actual_position: QgsPointXY  | None = None
        #self.xxx_pos: QgsPointXY = QgsPointXY(17.64695232, 53.83649398)

    def update_actual_position(self) -> None:
        #act_pos = "5432.6659792,01832.7680816"
        act_pos = self.parameters.get("param_monitor",{}).get("ACT_Pos",{}).get("value","")
        # step = 1e-5
        # self.xxx_pos.setX(self.xxx_pos.x() + step)
        # self.xxx_pos.setY(self.xxx_pos.y() + step)
        if not act_pos or act_pos == "xxx":
            return
        pos = ReceiverModel.parse_act_pos(act_pos)
        if pos is None:
            return
        self.actual_position = pos
        self.actual_position_updated.emit(self.actual_position)
        
    def set_parameter_control(self, name: str, value: Any) -> None:
        """Update the parameter value (for dialog/UI update)."""
        if name in self.parameters["param_control"]:
            self.parameters["param_control"][name]['value'] = value

            
    def set_parameter_monitor(self, name: str, value: Any) -> None:
        """Update the parameter value (for dialog/UI update)."""
        if name in self.parameters["param_monitor"]:
            self.parameters["param_monitor"][name]['value'] = value
            
    def set_parameter_status(self, name: str, value: Any) -> None:
        """Update the parameter value (for dialog/UI update)."""
        if name in self.parameters["status"]:
            self.parameters["status"][name]['value'] = value
            
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
    
    @staticmethod       
    def nmea_to_decimal(coord: str, deg_len: int) -> float:
        """
        Convert NMEA coordinate (DDMM.MMMM or DDDMM.MMMM) to decimal degrees.
        deg_len = 2 for latitude, 3 for longitude
        """
        coord = coord.strip()
        degrees = int(coord[:deg_len])
        minutes = float(coord[deg_len:])
        return degrees + minutes / 60.0
    
    @staticmethod
    def parse_act_pos(act_pos: str) -> Optional[QgsPointXY]:
        """
        Convert ACT_Pos string "lat,lon" (NMEA format) into QgsPointXY(decimal_lat, decimal_lon).
        Returns None if the input is invalid.
        """
        try:
            # Check format
            parts = act_pos.split(",")
            if len(parts) != 2:
                raise ValueError(f"Invalid NMEA format: {act_pos!r}")

            lat_str, lon_str = parts

            # Check numeric
            if not (lat_str.replace(".", "", 1).isdigit() and lon_str.replace(".", "", 1).isdigit()):
                raise ValueError(f"No GPS position in NMEA, current value: {act_pos!r}")

            # Convert using NMEA rules
            lat = ReceiverModel.nmea_to_decimal(lat_str, 2)
            lon = ReceiverModel.nmea_to_decimal(lon_str, 3)

            return QgsPointXY(lon, lat)

        except Exception as e:
            logger.warning(f"[ReceiverModel] parse_act_pos failed: {e}") 
            return None

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
        


