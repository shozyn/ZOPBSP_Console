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
    gps_rpis: dict[str, str]


# -----------------------------------------------------------------------------
# Utilities: filename timestamp parsing
# -----------------------------------------------------------------------------

# Matches: <anything>_<YYYYMMDD>_<HHMMSS>.wav  (case-insensitive .wav)
_WAV_TS_RE = re.compile(r".*_(\d{8})_(\d{6})\.(?i:wav)$")
_FILE_TS_RE = re.compile(r"(\d{8})_(\d{6})", re.IGNORECASE)

def parse_file_ts_key(p: Path) -> Optional[str]:
    """
    Extract 'YYYYMMDD_HHMMSS' from anywhere in the filename.

    Examples
    --------
    SJW6937_20250822_125320.wav
        -> 20250822_125320

    GPS_RPI3_20251015_125830_Hydro_6675.txt
        -> 20251015_125830
    """
    m = _FILE_TS_RE.search(p.name)
    if not m:
        return None

    ymd, hms = m.groups()
    return f"{ymd}_{hms}"

# def parse_wav_ts_key(p: Path) -> Optional[str]:
#     """
#     Extract 'YYYYMMDD_HHMMSS' from a WAV filename.
#     Returns None if the pattern is not found.

#     SJW6937_20250822_125320.wav  ->  '20250822_125320'
#     """
#     m = _WAV_TS_RE.match(p.name)
#     if not m:
#         return None
#     ymd, hms = m.groups()
#     # Normalize to a consistent format to allow lexical ordering:
#     # 'YYYYMMDD_HHMMSS' (zero-padded already)
#     return f"{ymd}_{hms}"
def parse_wav_ts_key(p: Path) -> Optional[str]:
    if p.suffix.lower() != ".wav":
        return None
    return parse_file_ts_key(p)

def parse_gps_ts_key(p: Path) -> Optional[str]:
    if p.suffix.lower() != ".txt":
        return None
    return parse_file_ts_key(p)

# class TargetModel(QObject):
#     """
#     Model representing a single target (real and predicted positions).
#     """
#     actual_position_updated = pyqtSignal(QgsPointXY)
#     predicted_position_updated = pyqtSignal(QgsPointXY)

#     def __init__(self, target_id, ip, port, parent=None):
#         super().__init__(parent)
#         self.target_id = target_id
#         self.ip = ip
#         self.port = port
#         self.actual_position = None
#         self.predicted_position = None

#         #self.actual_position_updated.connect(lambda p: print(f"Actual: {p}"))
#         #target.predicted_position_updated.connect(lambda p: print(f"Predicted: {p}"))

#     def update_actual_position(self, lat, lon):
#         self.actual_position = QgsPointXY(lon, lat)
#         #print(f"[{self.__class__.__name__}] Slot activated: {inspect.currentframe().f_code.co_name}; {lat, lon}")
#         #self.actual_position = QgsPointXY(18.54534607666666801, 54.5435800300000011)
#         self.actual_position_updated.emit(self.actual_position)

#     def update_predicted_position(self, point: QgsPointXY):
#         self.predicted_position = point
#         self.predicted_position_updated.emit(self.predicted_position)

class TargetModel(QObject):
    """
    Model representing one physical Target.

    The model stores data only. It does not draw anything and it does not
    communicate over the network.
    """

    actual_position_updated = pyqtSignal(QgsPointXY, str)
    predicted_position_updated = pyqtSignal(QgsPointXY, str)
    status_changed = pyqtSignal(str)

    def __init__(self, target_id, ip, port, parent=None):
        super().__init__(parent)

        self.target_id = str(target_id)
        self.ip = ip
        self.port = port

        self.actual_position: QgsPointXY | None = None
        self.predicted_position: QgsPointXY | None = None

        self.actual_timestamp: str = ""
        self.predicted_timestamp: str = ""
        self.status: str = "DISCONNECTED"

    def update_actual_position(self, lat, lon, timestamp: str = "") -> None:
        """
        Store the latest measured target position.

        GPS data is naturally expressed as (latitude, longitude). QGIS points
        are expressed as (x, y). For EPSG:4326:

            x = longitude
            y = latitude

        Therefore the correct construction is QgsPointXY(lon, lat).
        """
        self.actual_position = QgsPointXY(float(lon), float(lat))
        self.actual_timestamp = str(timestamp)

        self.actual_position_updated.emit(
            self.actual_position,
            self.actual_timestamp,
        )

    def update_predicted_position(self, point: QgsPointXY, timestamp: str = "") -> None:
        """
        Store the latest predicted target position.
        """
        self.predicted_position = point
        self.predicted_timestamp = str(timestamp)

        self.predicted_position_updated.emit(
            self.predicted_position,
            self.predicted_timestamp,
        )

    def set_status(self, status: str) -> None:
        """
        Store target communication/display status and notify observers.
        """
        status = str(status)

        if self.status == status:
            return

        self.status = status
        self.status_changed.emit(self.status)


class ReceiverModel(QObject): 
    actual_position_updated = pyqtSignal(QgsPointXY)
    def __init__(self, receiver_id, parameters,sftp_cfg, parent=None):
        super().__init__(parent)
        self.receiver_id = receiver_id
        self.parameters = parameters
        self.sftp_cfg = sftp_cfg
        self.actual_position: QgsPointXY  | None = None
        #self.xxx_pos: QgsPointXY = QgsPointXY(17.64695232, 53.83649398)

    # def update_actual_position(self) -> None:
    #     #act_pos = "5432.6659792,01832.7680816"
    #     act_pos = self.parameters.get("param_monitor",{}).get("ACT_Pos",{}).get("value","")
    #     # step = 1e-5
    #     # self.xxx_pos.setX(self.xxx_pos.x() + step)
    #     # self.xxx_pos.setY(self.xxx_pos.y() + step)
    #     if not act_pos or act_pos == "xxx":
    #         return
    #     pos = ReceiverModel.parse_act_pos(act_pos)
    #     if pos is None:
    #         return
    #     self.actual_position = pos
    #     self.actual_position_updated.emit(self.actual_position)
    
    def set_actual_position(self, point: QgsPointXY) -> None:
        """
        Set the receiver's actual position explicitly.

        This method does not read ACT_Pos, monitor.txt, or any file.
        It only stores an already parsed point and emits the update signal.

        Expected coordinate convention:
            QgsPointXY(longitude, latitude)
        if the map is displayed in EPSG:4326.
        """
        self.actual_position = point
        self.actual_position_updated.emit(self.actual_position)
        
    def update_position_from_gps_file(self, gps_path: str) -> bool:
        """
        Read a downloaded GPS file, extract the newest valid position,
        and update the receiver marker.

        Returns
        -------
        bool
            True if a valid position was found and emitted.
            False otherwise.
        """
        try:
            text = Path(gps_path).read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(
                "[ReceiverModel][%s] Could not read GPS file %s: %s",
                self.receiver_id,
                gps_path,
                e,
            )
            return False

        lines = [line.strip() for line in text.splitlines() if line.strip()]

        # Prefer the last valid line, because GPS files often contain chronological logs.
        for line in reversed(lines):
            point = self.parse_gps_line(line)
            if point is not None:
                self.set_actual_position(point)
                logger.info(
                    "[ReceiverModel][%s] Position updated from GPS file %s: lon=%.8f, lat=%.8f",
                    self.receiver_id,
                    gps_path,
                    point.x(),
                    point.y(),
                )
                return True

        logger.warning(
            "[ReceiverModel][%s] No valid GPS position found in %s",
            self.receiver_id,
            gps_path,
        )
        return False
        
            
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

    # def set_sftp_cfg(self, name: str, value: Any) -> None:
    #     """Update the parameter value (for dialog/UI update)."""
    #     if name in self.parameters:
    #         self.parasftp_cfgmeters[name]['value'] = value
    
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
    
    # @staticmethod
    # def parse_act_pos(act_pos: str) -> Optional[QgsPointXY]:
    #     """
    #     Convert ACT_Pos string "lat,lon" (NMEA format) into QgsPointXY(decimal_lat, decimal_lon).
    #     Returns None if the input is invalid.
    #     """
    #     try:
    #         # Check format
    #         parts = act_pos.split(",")
    #         if len(parts) != 2:
    #             raise ValueError(f"Invalid NMEA format: {act_pos!r}")

    #         lat_str, lon_str = parts

    #         # Check numeric
    #         if not (lat_str.replace(".", "", 1).isdigit() and lon_str.replace(".", "", 1).isdigit()):
    #             raise ValueError(f"No GPS position in NMEA, current value: {act_pos!r}")

    #         # Convert using NMEA rules
    #         lat = ReceiverModel.nmea_to_decimal(lat_str, 2)
    #         lon = ReceiverModel.nmea_to_decimal(lon_str, 3)

    #         return QgsPointXY(lon, lat)

    #     except Exception as e:
    #         logger.warning(f"[ReceiverModel] parse_act_pos failed: {e}") 
    #         return None
    
    @staticmethod
    def parse_gps_record_line(line: str) -> Optional[QgsPointXY]:
        """
        Parse project-specific GPS record:

            time, lat_nmea, N/S, lon_nmea, E/W, Satellites: ..., HDOP: ...

        Example:
            105849.00, 5350.0894387, N, 01738.7878200, E, Satellites: 20, ...
        """
        try:
            parts = [p.strip() for p in line.split(",")]

            if len(parts) < 5:
                return None

            # Expected:
            # parts[0] = time, e.g. 105849.00
            # parts[1] = latitude in NMEA DDMM.MMMMM
            # parts[2] = N/S
            # parts[3] = longitude in NMEA DDDMM.MMMMM
            # parts[4] = E/W
            lat_raw = parts[1]
            lat_hemi = parts[2].upper()
            lon_raw = parts[3]
            lon_hemi = parts[4].upper()

            if lat_hemi not in ("N", "S") or lon_hemi not in ("E", "W"):
                return None

            lat = ReceiverModel.nmea_to_decimal_with_hemisphere(
                lat_raw,
                lat_hemi,
                deg_len=2,
            )
            lon = ReceiverModel.nmea_to_decimal_with_hemisphere(
                lon_raw,
                lon_hemi,
                deg_len=3,
            )

            if lat is None or lon is None:
                return None

            return QgsPointXY(lon, lat)

        except Exception as e:
            logger.warning("[ReceiverModel] parse_gps_record_line failed: %s", e)
            return None
    
    
    @staticmethod
    def parse_gps_line(line: str) -> Optional[QgsPointXY]:
        """
        Parse one GPS text line.
        """
        s = line.strip()
        if not s:
            return None

        # Full NMEA GGA sentence.
        if s.startswith(("$GNGGA", "$GPGGA")):
            return ReceiverModel.parse_gga_sentence(s)

        # Project-specific GPS record:
        # time, lat, N/S, lon, E/W, ...
        point = ReceiverModel.parse_gps_record_line(s)
        if point is not None:
            return point

        # Key-value form.
        if "=" in s:
            key, value = s.split("=", 1)
            if key.strip() in ("ACT_Pos", "GPS", "GPS_Pos", "Position"):
                return ReceiverModel.parse_coordinate_pair(value.strip())

        if ":" in s:
            key, value = s.split(":", 1)
            if key.strip() in ("ACT_Pos", "GPS", "GPS_Pos", "Position"):
                return ReceiverModel.parse_coordinate_pair(value.strip())

        # Bare coordinate pair.
        if "," in s:
            return ReceiverModel.parse_coordinate_pair(s)

        return None


    @staticmethod
    def parse_coordinate_pair(value: str) -> Optional[QgsPointXY]:
        """
        Parse either:
            decimal latitude, decimal longitude
        or:
            NMEA latitude, NMEA longitude

        Returns QgsPointXY(lon, lat).
        """
        try:
            parts = [p.strip() for p in value.split(",")]
            if len(parts) != 2:
                return None

            lat_raw, lon_raw = parts
            lat_val = float(lat_raw)
            lon_val = float(lon_raw)

            # Decimal degrees case.
            if abs(lat_val) <= 90.0 and abs(lon_val) <= 180.0:
                return QgsPointXY(lon_val, lat_val)

            # NMEA pair without hemisphere:
            # latitude:  DDMM.MMMM
            # longitude: DDDMM.MMMM
            lat = ReceiverModel.nmea_to_decimal(lat_raw, deg_len=2)
            lon = ReceiverModel.nmea_to_decimal(lon_raw, deg_len=3)

            return QgsPointXY(lon, lat)

        except Exception as e:
            logger.warning("[ReceiverModel] parse_coordinate_pair failed: %s", e)
            return None


    @staticmethod
    def parse_gga_sentence(sentence: str) -> Optional[QgsPointXY]:
        """
        Parse NMEA GGA sentence:
            $GNGGA,time,ddmm.mmmm,N,dddmm.mmmm,E,...
        """
        try:
            parts = sentence.split(",")

            if len(parts) < 6:
                return None

            lat_raw = parts[2].strip()
            lat_hemi = parts[3].strip().upper()
            lon_raw = parts[4].strip()
            lon_hemi = parts[5].strip().upper()

            lat = ReceiverModel.nmea_to_decimal_with_hemisphere(
                lat_raw,
                lat_hemi,
                deg_len=2,
            )
            lon = ReceiverModel.nmea_to_decimal_with_hemisphere(
                lon_raw,
                lon_hemi,
                deg_len=3,
            )

            if lat is None or lon is None:
                return None

            return QgsPointXY(lon, lat)

        except Exception as e:
            logger.warning("[ReceiverModel] parse_gga_sentence failed: %s", e)
            return None


    @staticmethod
    def nmea_to_decimal_with_hemisphere(
        coord: str,
        hemisphere: str,
        deg_len: int,
    ) -> Optional[float]:
        try:
            decimal = ReceiverModel.nmea_to_decimal(coord, deg_len)

            if hemisphere in ("S", "W"):
                decimal = -decimal

            return decimal

        except Exception:
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
    """

    job_ready = pyqtSignal(object)  # emits CalcJob

    def __init__(self,
                 required_receivers: tuple[str] = ("RPI1",),
                 org: str = "AMW",
                 app: str = "ZOPBSP_Console",
                 parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.required_receivers: tuple[str, ...] = required_receivers
        # per-receiver dictionary: receiver_id -> { ts_key -> FileMeta }
        self.receivers_wav_meta: Dict[str, Dict[str, FileMeta]] = {
            rid: {} for rid in required_receivers
        }

        self.receivers_gps_meta: Dict[str, Dict[str, FileMeta]] = {
            rid: {} for rid in required_receivers
        }

        self._settings = QSettings(org, app)
        self._processed: Set[str] = set(self._load_processed())

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

    # @pyqtSlot(object)
    # def update_latest(self, meta: FileMeta) -> None:
    #     """
    #     Push a newly arrived WAV into the model.
    #     The Controller calls this per-file when an SFTP worker reports a download.
    #     """
        
    #     if meta.receiver_id not in self.receivers_fileMeta:
    #         logger.warning("[CalculationModel] Unknown receiver_id=%s; ignoring", meta.receiver_id)
    #         return

    #     # Insert/replace newest instance for that ts_key
    #     stored_files = self.receivers_fileMeta[meta.receiver_id] 
    #     #print(f"Stored_metafiles for {meta.receiver_id}:\n{stored_files}")
    #     existing = stored_files.get(meta.ts_key)
    #     if (existing is None) or (meta.mtime_ns >= existing.mtime_ns):
    #         stored_files[meta.ts_key] = meta
    #         logger.debug("[Calc ulationModel] Stored %s for %s: %s",
    #                      meta.ts_key, meta.receiver_id, meta.path)

    #     self._test_if_ready_calc()
        
        
        
    @pyqtSlot(object)
    def update_wav(self, meta: FileMeta) -> None:
        self._store_meta(self.receivers_wav_meta, meta, role="wav")
        self._test_if_ready_calc()


    @pyqtSlot(object)
    def update_gps(self, meta: FileMeta) -> None:
        self._store_meta(self.receivers_gps_meta, meta, role="gps")
        self._test_if_ready_calc()


    # Compatibility with the previous name.
    @pyqtSlot(object)
    def update_latest(self, meta: FileMeta) -> None:
        self.update_wav(meta)


    def _store_meta(
        self,
        store: Dict[str, Dict[str, FileMeta]],
        meta: FileMeta,
        role: str,
    ) -> None:
        if meta.receiver_id not in store:
            logger.warning(
                "[CalculationModel] Unknown receiver_id=%s for role=%s; ignoring",
                meta.receiver_id,
                role,
            )
            return

        stored_files = store[meta.receiver_id]
        existing = stored_files.get(meta.ts_key)

        if existing is None or meta.mtime_ns >= existing.mtime_ns:
            stored_files[meta.ts_key] = meta
            logger.debug(
                "[CalculationModel] Stored %s for %s/%s: %s",
                meta.ts_key,
                meta.receiver_id,
                role,
                meta.path,
            )
        
        

    # def reset_session(self):
    #     """
    #     Start a fresh calculation session:
    #     - forget all collected FileMeta
    #     - forget all processed ts_keys
    #     """
    #     for rid in self.receivers_fileMeta:
    #         self.receivers_fileMeta[rid].clear()

    #     self._processed.clear()
    #     self._save_processed()  # keep QSettings consistent with reset
    
    def reset_session(self):
        for rid in self.required_receivers:
            self.receivers_wav_meta[rid].clear()
            self.receivers_gps_meta[rid].clear()

        self._processed.clear()
        self._save_processed()       
        
    # ------------------------ Core matching logic ----------------------------

    # def _test_if_ready_calc(self) -> None:
    #     """
    #     If all receivers share at least one common ts_key, pick the
    #     newest (max) common key that hasn't been processed and emit a CalcJob.
    #     """
    #     # 1) Build the intersection of ts_keys across required receivers
    #     key_sets: List[Set[str]] = []
    #     for rid in self.required_receivers:
    #         keys = set(self.receivers_fileMeta[rid].keys())
    #         if not keys:
    #             return  # some receiver has not provided anything yet
    #         key_sets.append(keys)

    #     common = set.intersection(*key_sets) if key_sets else set()

    #     if not common:
    #         return

    #     for ts_key in sorted(common, reverse=False):
    #         if ts_key not in self._processed:
    #             self._emit_job_for(ts_key)
    #             break  # emit only one job per update (policy)

    def _test_if_ready_calc(self) -> None:
        """
        Emit a CalcJob only when every required receiver has both:
            - WAV file
            - GPS file

        with the same timestamp key.
        """
        key_sets: List[Set[str]] = []

        for rid in self.required_receivers:
            wav_keys = set(self.receivers_wav_meta[rid].keys())
            gps_keys = set(self.receivers_gps_meta[rid].keys())

            if not wav_keys or not gps_keys:
                return

            key_sets.append(wav_keys)
            key_sets.append(gps_keys)

        common = set.intersection(*key_sets) if key_sets else set()

        if not common:
            return

        # Chronological processing. Use reverse=True if you want newest-first.
        for ts_key in sorted(common, reverse=False):
            if ts_key not in self._processed:
                self._emit_job_for(ts_key)
                break

    # def _emit_job_for(self, ts_key: str) -> None:
    #     """Create a CalcJob from the three FileMeta entries and emit job_ready."""
    #     # Must exist for every required receiver by definition of 'common'
    #     rpis = dict()
    #     for k, v in self.receivers_fileMeta.items():
    #         rpis[k] = self.receivers_fileMeta[k][ts_key].path
    #         print(f"[CalculationModel] _emit_job_for receiver {k}, wav: {rpis[k]}")
            # # rpi1 = self.receivers_fileMeta["RPI1"][ts_key].path
        # # rpi2 = self.receivers_fileMeta["RPI2"][ts_key].path
        # # rpi3 = self.receivers_fileMeta["RPI3"][ts_key].path
        # job = CalcJob(job_id=ts_key, wav_rpis=rpis)
        # self._processed.add(ts_key)
        # self._save_processed()
        # logger.info("[CalculationModel] Job ready: %s", ts_key)
        # self.job_ready.emit(job) #sent to the worker
    def _emit_job_for(self, ts_key: str) -> None:
        wav_rpis = {}
        gps_rpis = {}

        for rid in self.required_receivers:
            wav_rpis[rid] = self.receivers_wav_meta[rid][ts_key].path
            gps_rpis[rid] = self.receivers_gps_meta[rid][ts_key].path

            logger.info(
                "[CalculationModel] Job %s receiver %s: wav=%s gps=%s",
                ts_key,
                rid,
                wav_rpis[rid],
                gps_rpis[rid],
            )

        job = CalcJob(
            job_id=ts_key,
            wav_rpis=wav_rpis,
            gps_rpis=gps_rpis,
        )

        self._processed.add(ts_key)
        self._save_processed()

        logger.info("[CalculationModel] Job ready: %s", ts_key)
        self.job_ready.emit(job)
        
            

        
    # def reset_processed(self, clear_file_meta=True):
    #     """
    #     Allow recomputation by clearing 'already processed' memory.

    #     clear_file_meta=True additionally forgets the seen FileMeta per receiver,
    #     which makes the next replay behave like a fresh session.
    #     """
    #     if hasattr(self, "_processed"):
    #         self._processed.clear()

    #     if clear_file_meta and hasattr(self, "receivers_fileMeta"):
    #         for rid in self.receivers_fileMeta:
    #             self.receivers_fileMeta[rid].clear()

    def reset_processed(self, clear_file_meta=True):
        if hasattr(self, "_processed"):
            self._processed.clear()
            self._save_processed()

        if clear_file_meta:
            for rid in self.required_receivers:
                self.receivers_wav_meta[rid].clear()
                self.receivers_gps_meta[rid].clear()

class ObjectModel(QObject):
    """
    Model representing a calculated object position.
    """

    position_updated = pyqtSignal(QgsPointXY, str)  # point, timestamp label

    def __init__(self, object_id: str = "Object1", parent=None):
        super().__init__(parent)
        self.object_id = object_id
        self.position: QgsPointXY | None = None
        self.timestamp: str = ""

    def update_position(self, lat: float, lon: float, timestamp: str) -> None:
        """
        Store and emit the calculated object position.

        Parameters
        ----------
        lat:
            Latitude in decimal degrees.

        lon:
            Longitude in decimal degrees.

        timestamp:
            Text displayed next to the object marker. In our case, it is
            derived from job_id.
        """
        self.position = QgsPointXY(float(lon), float(lat))
        self.timestamp = str(timestamp)

        self.position_updated.emit(self.position, self.timestamp)