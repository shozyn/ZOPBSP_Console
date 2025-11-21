from PyQt5.QtCore import QObject, pyqtSignal, QSettings, pyqtSlot
from qgis.core import QgsPointXY
from typing import Any, Optional
import logging
from typing import Optional
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


logger = logging.getLogger(__name__)
# -----------------------------------------------------------------------------
# Data structures (part of Model)
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class FileMeta:
    """Metadata for a single local WAV file."""
    receiver_id: str      # e.g., '172.0.0.0'
    path: str             # absolute local file path
    ts_key: str           # normalized key 'YYYYMMDD_HHMMSS'
    mtime_ns: int         # tie-breaker for equal keys (nanoseconds)


@dataclass(frozen=True)
class CalcJob:
    """A single calculation job formed from a synchronized WAV triplet."""
    job_id: str           # use the ts_key as a unique id
    wav_rpis: dict[str,str]


# -----------------------------------------------------------------------------
# Utilities: filename timestamp parsing
# -----------------------------------------------------------------------------

# Matches: <anything>_<YYYYMMDD>_<HHMMSS>.wav  (case-insensitive .wav)
_WAV_TS_RE = re.compile(r".*_(\d{8})_(\d{6})\.(?i:wav)$")

def parse_wav_ts_key(p: Path) -> Optional[str]:
    """
    Extract 'YYYYMMDD_HHMMSS' from a WAV filename.
    Returns None if the pattern is not found.

    SJW6937_20250822_125320.wav  ->  '20250822_125320'
    """
    m = _WAV_TS_RE.match(p.name)
    if not m:
        return None
    ymd, hms = m.groups()
    # Normalize to a consistent format to allow lexical ordering:
    # 'YYYYMMDD_HHMMSS' (zero-padded already)
    return f"{ymd}_{hms}"

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
            
    # def get_sftp_cfg(self, name: str) -> Optional[any]:
    #     """Return the parameter's value for a given name."""
    #     if name in self.sftp_cfg:
    #         return self.sftp_cfg.get(name)
    #     else:
    #         return None

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

class CalculationModel(QObject):
    """
    Aggregates new WAV arrivals per receiver and forms jobs when a 'newest'
    common timestamp exists across all required receivers.

    Design:
    - For each receiver, keep a mapping: ts_key -> FileMeta
    - On each arrival, recompute the intersection of keys across receivers.
    - Pick the LATEST (lexicographically max) ts_key in the intersection that
      has NOT been processed yet -> form a CalcJob and emit job_ready.

    Persistence:
    - Uses QSettings to store a set of 'processed' job_ids (ts_keys), so that
      on app restarts we don't recompute the same triplet.
    """

    job_ready = pyqtSignal(object)  # emits CalcJob

    def __init__(self,
                 required_receivers: tuple[str] = ("172.0.0.1",),
                 org: str = "AMW",
                 app: str = "ZOPBSP_Console",
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.required_receivers: tuple[str, ...] = required_receivers
        # per-receiver dictionary: receiver_id -> { ts_key -> FileMeta }
        self.receivers_fileMeta: Dict[str, Dict[str, FileMeta]] = {
            rid: {} for rid in required_receivers
        }

        self._settings = QSettings(org, app)
        self._processed: Set[str] = set(self._load_processed())
        print(f"_processed in init(): {self._processed}")

    # ------------------------ Persistence helpers ----------------------------

    def _load_processed(self) -> List[str]:
        """Load processed job ids (ts_keys) from QSettings."""
        self._settings.beginGroup("calc/processed")
        self._settings.setValue("job_ids", list())
        ids = self._settings.value("job_ids", [], type=list)
        self._settings.endGroup()
        return ids

    def _save_processed(self) -> None:
        """Persist processed job ids to QSettings."""
        self._settings.beginGroup("calc/processed")
        self._settings.setValue("job_ids", list(self._processed))
        self._settings.endGroup()
        self._settings.sync()

    # ------------------------ Public API used by the Controller --------------

    @pyqtSlot(object)
    def update_latest(self, meta: FileMeta) -> None:
        """
        Push a newly arrived WAV into the model.
        The Controller calls this per-file when an SFTP worker reports a download.
        """
        
        if meta.receiver_id not in self.receivers_fileMeta:
            logger.warning("[CalculationModel] Unknown receiver_id=%s; ignoring", meta.receiver_id)
            return

        # Insert/replace newest instance for that ts_key
        stored_files = self.receivers_fileMeta[meta.receiver_id] 
        #print(f"Stored_metafiles for {meta.receiver_id}:\n{stored_files}")
        existing = stored_files.get(meta.ts_key)
        if (existing is None) or (meta.mtime_ns >= existing.mtime_ns):
            stored_files[meta.ts_key] = meta
            logger.debug("[CalculationModel] Stored %s for %s: %s",
                         meta.ts_key, meta.receiver_id, meta.path)

        self._test_if_ready_calc()

    # ------------------------ Core matching logic ----------------------------

    def _test_if_ready_calc(self) -> None:
        """
        If all receivers share at least one common ts_key, pick the
        newest (max) common key that hasn't been processed and emit a CalcJob.
        """
        # 1) Build the intersection of ts_keys across required receivers
        key_sets: List[Set[str]] = []
        for rid in self.required_receivers:
            keys = set(self.receivers_fileMeta[rid].keys())
            if not keys:
                return  # some receiver has not provided anything yet
            key_sets.append(keys)

        print(f"[CalculationModel] key_sets to test appearance in rcs:\n{key_sets}\n")

        common = set.intersection(*key_sets) if key_sets else set()
        print(f"[CalculationModel] common keys: {common}")

        if not common:
            return

        for ts_key in sorted(common, reverse=False):
            if ts_key not in self._processed:
                print(f"[CalculationModel] ts_key to process:\n{ts_key}\n")
                self._emit_job_for(ts_key)
                break  # emit only one job per update (policy)

    def _emit_job_for(self, ts_key: str) -> None:
        """Create a CalcJob from the three FileMeta entries and emit job_ready."""
        # Must exist for every required receiver by definition of 'common'
        rpis = dict()
        for k, v in self.receivers_fileMeta.items():
            rpis[k] = self.receivers_fileMeta[k][ts_key].path
            print(f"[CalculationModel] _emit_job_for receiver {k}, wav: {rpis[k]}")

        
            
        # rpi1 = self.receivers_fileMeta["RPI1"][ts_key].path
        # rpi2 = self.receivers_fileMeta["RPI2"][ts_key].path
        # rpi3 = self.receivers_fileMeta["RPI3"][ts_key].path
        job = CalcJob(job_id=ts_key, wav_rpis=rpis)
        self._processed.add(ts_key)
        print(f"self._processed: {self._processed}")
        self._save_processed()
        logger.info("[CalculationModel] Job ready: %s", ts_key)
        self.job_ready.emit(job) #sent to the worker