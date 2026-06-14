from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QMetaObject
from PyQt5.QtGui import QColor, QBrush
import inspect
from pathlib import Path, PureWindowsPath
from PyQt5.QtWidgets import QDialog, QMessageBox, QFileDialog, QWidget
from view.parameter_dialog import ParameterDialog
from PyQt5.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
from qgis.core import QgsRasterLayer, QgsCoordinateReferenceSystem, QgsPointXY
from utils.receiver_client_worker import ReceiverClientWorker  
from utils.math_worker import CalculationWorker, start_calculation_thread
from model.models import (
    CalculationModel,
    FileMeta,
    CalcJob,
    parse_wav_ts_key,
    parse_gps_ts_key,
)
from view.parameter_dialog import FolderNameDialog 
from view.dock_widgets import DockResultWidget
from utils.sftp_worker import _SftpWorker
import inspect
import logging
import math
from pathlib import Path
import string
from typing import List, Optional
import time

from utils.kalman import ConstantVelocityKalman2D

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from view.widgets import MenuBar



logger = logging.getLogger(__name__)
def current_func_name() -> str:
    frame = inspect.currentframe()
    return frame.f_code.co_name if frame else "<unknown>"

class TargetController(QObject):
    """
    Controller for one Target.
    """

    stopRequested = pyqtSignal()

    def __init__(self, model, view, menu_bar, parent=None):
        super().__init__(parent)

        self.model = model
        self.view = view
        self.menu_bar = menu_bar

        self.thread: QThread | None = None
        self.worker: ReceiverClientWorker | None = None

        self.connected = False
        self.tracking_enabled = False
        self.display_enabled = False

        # Model -> Controller. The controller decides if/how to draw.
        self.model.actual_position_updated.connect(self.on_actual_position_updated)
        self.model.predicted_position_updated.connect(self.on_predicted_position_updated)
        self.model.status_changed.connect(self.on_target_status_changed)

        # Menu -> Controller.
        self.menu_bar.command_triggered.connect(self.handle_command)

    # ------------------------------------------------------------------
    # Menu command handling
    # ------------------------------------------------------------------

    @pyqtSlot(str, str)
    def handle_command(self, sender_id, command):
        if sender_id != self.model.target_id:
            return

        if command == "connect":
            self.connect_target()

        elif command == "disconnect":
            self.disconnect_target()

        elif command == "display":
            self.display_enabled = True
            self.view.show_latest()

        elif command == "hide":
            self.display_enabled = False
            self.view.hide_target()

        elif command == "track":
            self.tracking_enabled = True
            self.display_enabled = True
            self.view.show_latest()

        elif command == "stop_tracking":
            self.tracking_enabled = False

        elif command == "clear_track":
            self.view.clear_track()

    # ------------------------------------------------------------------
    # Worker -> Model
    # ------------------------------------------------------------------

    @pyqtSlot(float, float, str)
    def handle_new_gps(self, lat, lon, timestamp):
        """
        Receive a new GPS position from the UDP worker and store it in the model.
        """
        self.model.update_actual_position(lat, lon, timestamp)

    @pyqtSlot(str)
    def handle_worker_status(self, status: str):
        """
        Receive communication status from the UDP worker.
        """
        self.model.set_status(status)

    @pyqtSlot(str)
    def handle_worker_error(self, message: str):
        """
        Receive communication error from the UDP worker.
        """
        logger.error(
            "[TargetController][%s] Worker error: %s",
            self.model.target_id,
            message,
        )
        self.model.set_status("ERROR")

    # ------------------------------------------------------------------
    # Model -> View
    # ------------------------------------------------------------------

    @pyqtSlot(QgsPointXY, str)
    def on_actual_position_updated(self, point: QgsPointXY, timestamp: str):
        """
        Display and/or track the new target position.

        The point is drawn only if display or tracking is enabled.
        """
        if not self.display_enabled and not self.tracking_enabled:
            return

        self.view.display_actual_position(
            point,
            timestamp,
            add_to_track=self.tracking_enabled,
        )

    @pyqtSlot(QgsPointXY, str)
    def on_predicted_position_updated(self, point: QgsPointXY, timestamp: str):
        """
        Display predicted target position if display mode is active.
        """
        if not self.display_enabled:
            return

        self.view.display_predicted_position(point, timestamp)

    @pyqtSlot(str)
    def on_target_status_changed(self, status: str):
        """
        Currently logs target status. Later, this can also update the status
        panel.
        """
        logger.info(
            "[TargetController][%s] status=%s",
            self.model.target_id,
            status,
        )

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect_target(self):
        """
        Start UDP polling in a worker thread.
        """
        if self.connected:
            logger.info(
                "[TargetController][%s] Target already connected.",
                self.model.target_id,
            )
            return

        self.thread = QThread(self)
        self.worker = ReceiverClientWorker(self.model.ip, self.model.port)

        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.start)

        self.stopRequested.connect(
            self.worker.stop,
            type=Qt.QueuedConnection,
        )

        self.worker.new_gps.connect(self.handle_new_gps)
        self.worker.status_changed.connect(self.handle_worker_status)
        self.worker.error_occurred.connect(self.handle_worker_error)

        self.worker.finished.connect(self.thread.quit)

        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self._on_thread_finished)

        self.thread.start()

        self.connected = True
        self.model.set_status("STARTING")
        self.menu_bar.set_target_connection_text(self.model.target_id, True)

        logger.info(
            "[TargetController][%s] UDP polling started for %s:%s",
            self.model.target_id,
            self.model.ip,
            self.model.port,
        )

    def disconnect_target(self):
        """
        Stop UDP polling safely.

        If the thread does not stop in time, references are kept alive.
        This avoids the dangerous situation where a QThread is destroyed while
        still running.
        """
        if not self.connected:
            return

        if self.thread is None or self.worker is None:
            self.connected = False
            self.model.set_status("DISCONNECTED")
            self.menu_bar.set_target_connection_text(self.model.target_id, False)
            return

        self.model.set_status("STOPPING")
        self.stopRequested.emit()

        stopped = self.thread.wait(3000)

        if not stopped:
            logger.warning(
                "[TargetController][%s] Worker thread did not stop within timeout.",
                self.model.target_id,
            )
            self.model.set_status("ERROR")
            return

        logger.info(
            "[TargetController][%s] UDP polling stopped.",
            self.model.target_id,
        )

    @pyqtSlot()
    def _on_thread_finished(self):
        """
        Called when QThread really finishes.
        """
        self.connected = False
        self.worker = None
        self.thread = None

        self.model.set_status("DISCONNECTED")
        self.menu_bar.set_target_connection_text(self.model.target_id, False)

    def __del__(self):
        try:
            self.disconnect_target()
        except Exception:
            pass

class ReceiverController(QObject):
    """
    Controller for receiver interactions.
    """
    _last_folder_token: str = "XXX"     
    
    stopRequested = pyqtSignal()  
    model_changed = pyqtSignal(str,dict)
    #control_param_changed = pyqtSignal(dict,str)
    control_param_changed = pyqtSignal(dict)
    files_arrived = pyqtSignal(str, str, list)   
    download_files_requested = pyqtSignal()

    # def __init__(self, receiver_model, receiver_view, menu_bar, status_widget, parent=None):
    #     super().__init__(parent)

    #     self.model = receiver_model
    #     self.view = receiver_view
    #     self.menu_bar = menu_bar
    #     self.status_widget = status_widget
    #     self.receiver_id = receiver_model.receiver_id
    def __init__(self, receiver_model, receiver_view, menu_bar, status_widget, tool_bar=None, parent=None):
        super().__init__(parent)

        self.model = receiver_model
        self.view = receiver_view
        self.menu_bar = menu_bar
        self.status_widget = status_widget
        self.tool_bar = tool_bar
        self.receiver_id = receiver_model.receiver_id
        self.thread: QThread | None = None
        self.worker: _SftpWorker | None = None
        self.connected = False
        self.local_reader = None

        menu_bar.command_triggered.connect(self.handle_command)

        self.model.actual_position_updated.connect(self.view.display_actual_position)
        self.model.classification_updated.connect(self.view.display_classification_result)
        
    def read_local_files(self):
        """
        Offline replay from already-downloaded files.
        Uses current paths in self.model.sftp_cfg["local_dirs"], so changes in the GUI apply immediately.
        """
        from utils.local_folder_reader import LocalFolderReader

        if self.connected:
            self.disconnect_receiver()
            
        token, ok = ReceiverController.ask_for_token_static(parent=self.view,initial_text=ReceiverController._last_folder_token)
        if ok:
            ReceiverController._last_folder_token = token
            chosen_folder = self._set_folder()
            self.model.sftp_cfg["local_dirs"]["streaming"] = chosen_folder
            chosen_folder_gps = str(Path(chosen_folder).with_name("gps"))
            self.model.sftp_cfg["local_dirs"]["gps"] = chosen_folder_gps            
            try:
                Path(chosen_folder_gps).mkdir(parents=True, exist_ok=True)
                self.model.sftp_cfg["local_dirs"]["gps"] = chosen_folder_gps
            except Exception as e:
                self.view.show_warning("Folder", f"GPS folder could not be created:\n{chosen_folder_gps}\n{e}")

        local_dirs = self.model.sftp_cfg.get("local_dirs", {})
        hydro_dir = local_dirs.get("streaming", "")
        gps_dir = local_dirs.get("gps", "")

        if not hydro_dir and not gps_dir:
            self.view.show_warning("Local read", "No local_dirs configured for this receiver.")
            return

        self.local_reader = LocalFolderReader(self.receiver_id, batch=100, parent=self)
        self.local_reader.files_arrived.connect(self._on_worker_files_arrived)
        self.local_reader.status.connect(lambda msg: logger.info(msg))
        # cleanup
        self.local_reader.finished.connect(self.local_reader.deleteLater)
        self.local_reader.finished.connect(lambda: setattr(self, "local_reader", None))

        self.local_reader.start(hydro_dir, gps_dir)

    def read_local_session(self, session_dir: str) -> bool:
        """
        Offline replay for this receiver from an explicit session folder
        (no token dialog). Expects '<session_dir>/<RPIx>/streaming' and
        '<session_dir>/<RPIx>/gps'. Returns True if a reader was started.
        """
        from utils.local_folder_reader import LocalFolderReader

        if self.connected:
            self.disconnect_receiver()

        rpi_dir = Path(session_dir) / str(self.receiver_id)
        streaming = str(rpi_dir / "streaming")
        gps = str(rpi_dir / "gps")

        if not Path(streaming).is_dir() and not Path(gps).is_dir():
            self.view.show_warning(
                "Wczytaj sesję",
                f"Brak danych dla {self.receiver_id} w:\n{rpi_dir}",
            )
            return False

        self.model.sftp_cfg["local_dirs"]["streaming"] = streaming
        self.model.sftp_cfg["local_dirs"]["gps"] = gps

        self.local_reader = LocalFolderReader(self.receiver_id, batch=100, parent=self)
        self.local_reader.files_arrived.connect(self._on_worker_files_arrived)
        self.local_reader.status.connect(lambda msg: logger.info(msg))
        self.local_reader.finished.connect(self.local_reader.deleteLater)
        self.local_reader.finished.connect(lambda: setattr(self, "local_reader", None))

        self.local_reader.start(streaming, gps)
        logger.info(
            "[ReceiverController][%s] Reading local session: %s",
            self.receiver_id,
            rpi_dir,
        )
        return True

    def download_all_files(self):
        if not self.connected or not self.worker:
            self.view.show_warning("Download files", "Receiver is not connected. Connect first.")
            return
        
        token, ok = ReceiverController.ask_for_token_static(parent=self.view,initial_text=ReceiverController._last_folder_token)
        if ok:
            ReceiverController._last_folder_token = token
            chosen_folder = self._set_folder()
            self.model.sftp_cfg["local_dirs"]["streaming"] = chosen_folder
            chosen_folder_gps = str(Path(chosen_folder).with_name("gps"))
            self.model.sftp_cfg["local_dirs"]["gps"] = chosen_folder_gps            
            try:
                Path(chosen_folder_gps).mkdir(parents=True, exist_ok=True)
                self.model.sftp_cfg["local_dirs"]["gps"] = chosen_folder_gps
            except Exception as e:
                self.view.show_warning("Folder", f"GPS folder could not be created:\n{chosen_folder_gps}\n{e}")
        
            self.download_files_requested.emit()
    
    @staticmethod
    def ask_for_token_static(parent, initial_text: str = "XXX") -> tuple[str, bool]:
        return FolderNameDialog.get_folder_token(parent=parent, initial_text=initial_text)
    
    def _set_folder(self) -> str:
        base = PureWindowsPath(r"C:\Pi_loc") / ReceiverController._last_folder_token / str(self.receiver_id) / "streaming" 

        try:
            Path(str(base)).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.view.show_warning(
                "Create folder failed",
                f"Couldn't create: {base} {e}"
            )
            return ""
        

        chosen_folder = str(base)
        return chosen_folder      
        
    @pyqtSlot(str)
    def on_monitor_read(self,param_monitor):
        if not param_monitor:
            return
        
        param_dict = {}
        for line in param_monitor.splitlines():
            s = line.strip()
            if not s:
                continue
            delim = '=' if '=' in s else (':' if ':' in s else None)
            if not delim:
                continue

            key, value = s.split(delim, 1)
            key = key.strip()
            # Keep only printable chars and strip whitespace around the value
            value = ''.join(ch for ch in value if ch in string.printable).strip()

            if key:
                param_dict[key] = {"value": value}

        if not param_dict:
            return
        
        # Update the model 
        for name, pair in param_dict.items():
            self.model.set_parameter_monitor(name, pair["value"])

        self.on_model_updated()
    
    @pyqtSlot(str, str)
    def handle_command(self, sender_id, command):
        if sender_id != self.model.receiver_id:
            return

        if command == "connect":
            self.connect_receiver()
        elif command == "disconnect":
            self.disconnect_receiver()
            
        elif command == "set_parameters":
            dialog = ParameterDialog(self.model.parameters)
            if dialog.exec_() == QDialog.Accepted:
                new_params = dialog.get_new_parameters()

                chosen_folder = ""
                if new_params.get("AktStreaming","False") == "True":
                    token, ok = ReceiverController.ask_for_token_static(parent=self.view,initial_text=ReceiverController._last_folder_token)
                    if ok:
                        ReceiverController._last_folder_token = token
                        chosen_folder = self._set_folder()
                        self.model.sftp_cfg["local_dirs"]["streaming"] = chosen_folder
                        chosen_folder_gps = str(Path(chosen_folder).with_name("gps"))
                        try:
                            Path(chosen_folder_gps).mkdir(parents=True, exist_ok=True)
                            self.model.sftp_cfg["local_dirs"]["gps"] = chosen_folder_gps
                        except Exception as e:
                            self.view.show_warning("Folder", f"GPS folder could not be created:\n{chosen_folder_gps}\n{e}")
                        
                        QTimer.singleShot(0,lambda: self.control_param_changed.emit(new_params)) #without value
                        
        elif command == "read_local":
            self.read_local_files()
            
        elif command == "download_files":
            self.download_all_files()

    @pyqtSlot(dict)
    def on_control_param_updated(self,updated_prams):
        if updated_prams:
            for name, value in updated_prams.items():
                self.model.set_parameter_control(name, value)
            self.on_model_updated()

    
    # def on_status_sftp_changed(self,status : str) -> None:
    #     self.model.set_parameter_status("Status", status)
    #     self.update_status_widget()
    #     #print(status)
    @pyqtSlot(str)
    def on_status_sftp_changed(self, status: str) -> None:
        self.model.set_parameter_status("Status", status)
        self.update_status_widget()

        if self.tool_bar is not None:
            self.tool_bar.set_receiver_status(self.receiver_id, status)
            
    def connect_receiver(self):
        self._start_sftp()

    def disconnect_receiver(self):
        self._stop_sftp()

    def _start_sftp(self):
        if self.connected:
            return

        self.thread = QThread(self)
        if self.thread is None:
            return
        
        self.worker = _SftpWorker(self.model.sftp_cfg)
        self.worker.status_changed.connect(self.on_status_sftp_changed)
        self.worker.monitor_read.connect(self.on_monitor_read)
        self.worker.warning.connect(self.view.show_warning)  # slot in view
        self.worker.control_param_updated.connect(self.on_control_param_updated)
        self.control_param_changed.connect(self.worker.on_control_param_changed,type=Qt.QueuedConnection)
        self.download_files_requested.connect(self.worker.request_download_all, type=Qt.QueuedConnection)

        self.worker.files_arrived.connect(self._on_worker_files_arrived)
        
        
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.start)                    # worker creates QTimer inside start()
        self.stopRequested.connect(self.worker.stop, type=Qt.QueuedConnection)  # stop in worker thread
        self.worker.finished.connect(self.thread.quit)

        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        self.connected = True
        self.menu_bar.set_receiver_connection_text(self.receiver_id, True)

    def _stop_sftp(self):
        if not self.connected:
            return
        self.stopRequested.emit()     # queued -> worker.stop() in worker thread
        if self.thread:
            self.thread.wait(2000)

        self.connected = False
        self.menu_bar.set_receiver_connection_text(self.receiver_id, False)
        if self.tool_bar is not None:
            self.tool_bar.set_receiver_status(self.receiver_id, "DISCONNECTED")

        self.thread = None
        self.worker = None

    @pyqtSlot(str, str, list)
    def _on_worker_files_arrived(self, worker_id: str, role: str, files: list) -> None:
        """
        React to files downloaded by the SFTP worker.

        GPS files:
            1. are parsed by ReceiverModel to update the map marker;
            2. are relayed further to the calculation pipeline.

        Hydro/WAV files:
            are relayed to the calculation pipeline.
        """
        if role == "gps":
            for gps_file in sorted(files):
                self.model.update_position_from_gps_file(gps_file)

        self.files_arrived.emit(self.receiver_id, role, files)
        
    @pyqtSlot(str, int)
    def on_classification_ready(self, receiver_id: str, pred_class: int) -> None:
        """
        Receive a classification result from the calculation subsystem.

        Only the controller whose receiver_id matches the result updates its model.
        """
        if receiver_id != self.receiver_id:
            return

        self.model.update_predicted_class(pred_class)
        
        
        

    def __del__(self):
        # best-effort cleanup
        try:
            self._stop_sftp()
        except Exception:
            pass
    
    def on_model_updated(self):
        """
        Update receiver non-geometric state.

        Important:
        This method must not update the receiver's map position.
        Position updates will be handled explicitly from downloaded GPS files.
        """
        self.update_status_widget()
        self.model_changed.emit(self.receiver_id, self.model.parameters)
        
    
    def update_status_widget(self):
        """
        Update the StatusWidget's tree/list with the new parameter values.
        """
        m = self.status_widget.get_model()
        rx_root = None
        for r in range(m.rowCount()):
            if m.item(r, 0).text() == "Receivers":
                rx_root = m.item(r, 0)
                break

        if not rx_root:
            return

        expected_group = f"Receiver {self.model.receiver_id}"
        for i in range(rx_root.rowCount()):
            group = rx_root.child(i, 0)
            if group.text() == expected_group:
                # Update only values
                for j in range(group.rowCount()):
                    name_item = group.child(j, 0)
                    value_item = group.child(j, 1)
                    pname = name_item.text()
                    
                    if pname in self.model.parameters["status"]:
                        new_value = str(self.model.parameters["status"][pname].get("value"))
                        value_item.setText(new_value)
                        if new_value == "DISCONNECTED":
                            value_item.setBackground(QBrush(QColor("red")))
                        elif new_value == "CONNECTING":
                            value_item.setBackground(QBrush(QColor("yellow")))
                        else:
                            value_item.setBackground(QBrush(QColor("white")))
                        
                    if pname in self.model.parameters["param_monitor"]:
                        value_item.setText(str(self.model.parameters["param_monitor"][pname].get("value")))
                    if pname in self.model.parameters["param_control"]:
                        value_item.setText(str(self.model.parameters["param_control"][pname].get("value")))
                        
                break

class MainController(QObject):
    """
    Main application controller (handles user input, updates models and views).
    """
    def __init__(self, main_window, menu_bar, tool_bar=None, receiver_controllers=None,
                 calc_controller=None):
        super().__init__()
        self.main_window = main_window
        self.menu_bar = menu_bar
        self.tool_bar = tool_bar
        self.receiver_controllers = receiver_controllers or []
        self.calc_controller = calc_controller

        self.menu_bar.command_triggered.connect(self.handle_menu_command)
        if self.tool_bar is not None:
            self.tool_bar.bulk_action.connect(self.handle_bulk_action)

    def handle_menu_command(self, sender_id, command):
        if sender_id == "Calculation" and command == "load_session":
            self.load_session()
            return

        if sender_id != "": # Handle only project functions
            return
        """
        Receives the command string from the menu bar and dispatches to the correct logic.
        """
        if command == "open_project":
            self.open_project()
        elif command == "close_project":
            self.close_project()
        elif command == "new_project":
            self.new_project()
        else:
            print(f"[MainController] Unknown command received: {command}")

    @pyqtSlot(str)
    def handle_bulk_action(self, what: str):
        if what == "connect_all":
            for rc in self.receiver_controllers:
                rc.connect_receiver()              # idempotent; guarded inside controller
        elif what == "disconnect_all":
            for rc in self.receiver_controllers:
                rc.disconnect_receiver()
        elif what == "set_params_all":
            self._set_parameters_all()
        elif what == "read_all":
            self._read_all()
                
    def _set_parameters_all(self):
        if not self.receiver_controllers:
            return

        params_for_dialog = self.receiver_controllers[0].model.parameters
        dlg = ParameterDialog(parameters=params_for_dialog, parent=self.main_window)
        if dlg.exec_() != dlg.Accepted:
            return
        new_params = dlg.get_new_parameters()
        if new_params.get("AktStreaming","False") == "True":
            token, ok = ReceiverController.ask_for_token_static(parent=self.main_window,initial_text=ReceiverController._last_folder_token)
            if ok:
                ReceiverController._last_folder_token = token

        for rc in self.receiver_controllers:
            # (a) set model values (so the UI/status panel updates immediately)
            for name, value in new_params.items():
                rc.model.set_parameter_control(name, value)
            rc.on_model_updated()  # uses your existing refresh path
            chosen_folder = rc._set_folder()
            rc.model.sftp_cfg["local_dirs"]["streaming"] = chosen_folder
            chosen_folder_gps = chosen_folder.replace("streaming","gps")
            rc.model.sftp_cfg["local_dirs"]["gps"] = chosen_folder_gps
            #rc.control_param_changed.emit(new_params, chosen_folder) XXX
            
            rc.control_param_changed.emit(new_params)
            
    def _read_all(self):
        if not self.receiver_controllers:
            return

        token, ok = ReceiverController.ask_for_token_static(parent=self.main_window,initial_text=ReceiverController._last_folder_token)
        if ok:
            ReceiverController._last_folder_token = token

        for rc in self.receiver_controllers:
            chosen_folder = rc._set_folder()
            rc.model.sftp_cfg["local_dirs"]["streaming"] = chosen_folder
            chosen_folder_gps = chosen_folder.replace("streaming","gps")
            rc.model.sftp_cfg["local_dirs"]["gps"] = chosen_folder_gps

    def load_session(self):
        """
        Convenience loader: pick one session folder (e.g. '20260520_Otter1'),
        then automatically start the calculation and replay RPI1/2/3 from
        '<session>/RPIx/streaming' and '<session>/RPIx/gps'.
        """
        if not self.receiver_controllers:
            return

        start_dir = r"C:\Pi_loc\LA"
        if not Path(start_dir).is_dir():
            start_dir = r"C:\Pi_loc"

        session_dir = QFileDialog.getExistingDirectory(
            self.main_window,
            "Wybierz folder sesji (np. 20260520_Otter1)",
            start_dir,
        )
        if not session_dir:
            return  # cancelled

        # Calculation must run before files arrive, otherwise jobs are dropped.
        if self.calc_controller is not None:
            self.calc_controller.start_calculation()

        started = 0
        for rc in self.receiver_controllers:
            if rc.read_local_session(session_dir):
                started += 1

        logger.info(
            "[MainController] load_session: started %d/%d receivers from %s",
            started,
            len(self.receiver_controllers),
            session_dir,
        )

    def open_project(self):
        # Implement logic to open a project (dialog, load file, etc.)
        print("[MainController] open_project triggered")
        # Example: self.main_window.statusBar().showMessage("Project opened")

    def close_project(self):
        # Implement logic to close the project (save, cleanup, etc.)
        print("[MainController] Close Project triggered")

    def new_project(self):
        # Implement logic to start a new project (reset state, etc.)
        print("[MainController] New Project triggered")

class MapController(QObject):
    """
    Controller for map interactions.
    """
    coordinates_changed = pyqtSignal(float, float)  # lat, lon

    def __init__(self, map_view, map_model,map_layer, toolbar, menu_bar):
        super().__init__()
        self.map_view = map_view
        self.map_view.map_moved.connect(self.on_map_moved)
        self.map_model = map_model
        self.toolbar = toolbar
        self.map_layer = map_layer
        self.menu_bar = menu_bar

        # Connect the model's signal to the view's slot
        self.map_model.layers_changed.connect(self.map_view.set_layers)
        self.menu_bar.command_triggered.connect(self.on_menu_bar_command_triggered)

        if self.map_layer:
            self.add_raster_layer(self.map_layer)

        if self.toolbar is not None:
            self.toolbar.tool_changed.connect(self.map_view.on_send_tool)

    def on_menu_bar_command_triggered(self,who: str, command: str) -> None:
        if who != "Map":
            return
        if command == "zoom_to_full":
            self.map_view.m_MapCanvas.zoomToFullExtent()
    
    def add_raster_layer(self, path, crs="EPSG:4326"):
        layer = QgsRasterLayer(path)
        if not layer.isValid():
            print(f"Layer failed to load: {path}")
            return
            
        layer.setCrs(QgsCoordinateReferenceSystem(crs))
        self.map_model.add_layer(layer)
        
    
    def on_map_moved(self, point):
        self.coordinates_changed.emit(point.y(), point.x())




class CalculationController(QObject):
    """
    Controller that:
      - Listens to SFTP workers' 'files_arrived(receiver_id, role, files)' signals,
      - Filters to WAVs, parses timestamp keys, builds FileMeta, and
      - Calls model.update_latest(meta).
      - Forwards formed jobs to the CalculationWorker.
    """

    print_res = pyqtSignal(dict)
    object_position_ready = pyqtSignal(float, float, str)  # lat, lon, timestamp
    receiver_classification_ready = pyqtSignal(str, int)  # receiver_id, pred_class
    reference_track_ready = pyqtSignal(str, list)  # object_name, [(lat, lon), ...]
    object_type_detected = pyqtSignal(int)  # pred_class index (nearest hydrophone)

    def __init__(self, model: CalculationModel, menu_bar: MenuBar, dock_result: DockResultWidget,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.model = model
        # Runtime state for the calculation pipeline
        self._calc_worker: Optional[CalculationWorker] = None
        self._calc_thread = None
        self._calc_running: bool = False
        self._calc_stopping: bool = False
        self._job_t0: dict[str, float] = {}
        # Reference (ground-truth) track state.
        # Session whose reference track has already been loaded (avoid reloading).
        self._reference_session: Optional[str] = None
        self._reference_index: dict = {}            # UTC second-of-day -> (lat, lon)
        self._reference_object: Optional[str] = None
        self._reference_matched: list = []          # [(sec, (lat, lon)), ...] at estimation times
        self._reference_matched_secs: set = set()
        # TDOA closure tolerance [m]: |d12 + d23 - d13| above this is rejected
        # (inconsistent triple). Applied here on raw estimates (4th element of
        # each Est_pos item), so it is tunable without re-running the estimator.
        self._closure_tol_m = 20.0
        # Geometric gate margin [m] around the hydrophone triangle. Estimates
        # inside the triangle or within this distance of it are accepted.
        self._geo_margin_m = 100.0
        # Temporal smoothing of the estimated object position with a 2D
        # constant-velocity Kalman filter (object moves at ~0.75-3 m/s).
        # Parametry dostrojone offline na trasach referencyjnych pod GLADKOSC
        # (tools/optimize_params.py): jitter ~0.7 m, mediana ~19 m. Duze meas_std
        # => filtr ufa modelowi stalej predkosci, ignoruje rozrzut TDOA.
        # max_gap_s duze => filtr nie resetuje sie na przerwach miedzy rzadkimi
        # ocalalymi punktami (te resety dawaly "odloty" na mapie); utrzymuje
        # ciaglosc i wygladza przez luki.
        self._kalman = ConstantVelocityKalman2D(
            process_std=0.1, meas_std=60.0, max_gap_s=300.0
        )
        self._kalman_ref = None         # (lat0, lon0) local-frame origin
        self._kalman_last_sec = None    # UTC second-of-day of previous estimate
        self.menu_bar = menu_bar
        self.menu_bar.command_triggered.connect(self.handle_command)
        self.print_res.connect(dock_result.add_result)

    

# ----------------- Lifecycle slots (bind to GUI) -----------------
    # Class indices in OUTPUT_CLASSES:
    # 0 = Cisza / Salience
    # 2 = LAUV
    # 3 = Otter
    # 5 = Ponton_2 / Raft
    OBJECT_THRESHOLD = 0.5
    SALIENCE_CLASS = 0
    OBJECT_CLASSES = (2, 3, 5)

    @staticmethod
    def _threshold_aka1a_result(cls_result: dict, threshold: float = OBJECT_THRESHOLD) -> int:
        """
        Convert raw AKA1A output into thresholded display class.

        The classifier returns external class indices:
            0 = Cisza
            2 = LAUV
            3 = Otter
            5 = Ponton_2 / Raft

        Rule:
            - take the strongest object class among LAUV/Otter/Raft;
            - if its probability >= threshold and is stronger than Salience,
              display that object;
            - otherwise display Cisza.
        """
        probs = cls_result.get("class_prob")

        # Fallback: if probabilities are missing, preserve old behaviour.
        if not probs:
            try:
                return int(cls_result.get("pred_class"))
            except Exception:
                return CalculationController.SALIENCE_CLASS

        try:
            object_scores = {
                cls_id: float(probs[cls_id])
                for cls_id in CalculationController.OBJECT_CLASSES
                if cls_id < len(probs)
            }

            if not object_scores:
                return CalculationController.SALIENCE_CLASS

            best_object_class = max(object_scores, key=object_scores.get)
            best_object_score = object_scores[best_object_class]

            salience_score = (
                float(probs[CalculationController.SALIENCE_CLASS])
                if CalculationController.SALIENCE_CLASS < len(probs)
                else 0.0
            )

            if best_object_score >= threshold and best_object_score > salience_score:
                return int(best_object_class)

            return CalculationController.SALIENCE_CLASS

        except Exception as e:
            logger.warning(
                "[CalculationController] AKA1A thresholding failed for result=%r: %s",
                cls_result,
                e,
            )
            try:
                return int(cls_result.get("pred_class"))
            except Exception:
                return CalculationController.SALIENCE_CLASS


    @staticmethod
    def _threshold_aka1a_details(cls_result: dict, threshold: float = OBJECT_THRESHOLD):
        """
        Threshold one AKA1A result.

        Returns:
            pred_class, object_score, salience_score

        pred_class is an external class index:
            0 = Cisza
            2 = LAUV
            3 = Otter
            5 = Ponton_2 / Raft
        """
        probs = cls_result.get("class_prob")

        # Fallback: preserve old behaviour if probabilities are unavailable.
        if not probs:
            try:
                return int(cls_result.get("pred_class")), None, None
            except Exception:
                return CalculationController.SALIENCE_CLASS, None, None

        try:
            object_scores = {
                cls_id: float(probs[cls_id])
                for cls_id in CalculationController.OBJECT_CLASSES
                if cls_id < len(probs)
            }

            if not object_scores:
                return CalculationController.SALIENCE_CLASS, None, None

            best_object_class = max(object_scores, key=object_scores.get)
            object_score = float(object_scores[best_object_class])

            salience_score = (
                float(probs[CalculationController.SALIENCE_CLASS])
                if CalculationController.SALIENCE_CLASS < len(probs)
                else 0.0
            )

            if object_score >= threshold and object_score > salience_score:
                return int(best_object_class), object_score, salience_score

            return CalculationController.SALIENCE_CLASS, object_score, salience_score

        except Exception as e:
            logger.warning(
                "[CalculationController] AKA1A thresholding failed for result=%r: %s",
                cls_result,
                e,
            )
            try:
                return int(cls_result.get("pred_class")), None, None
            except Exception:
                return CalculationController.SALIENCE_CLASS, None, None

    @staticmethod
    def _threshold_aka1a_result(cls_result: dict, threshold: float = OBJECT_THRESHOLD) -> int:
        pred_class, _object_score, _salience_score = (
            CalculationController._threshold_aka1a_details(cls_result, threshold)
        )
        return pred_class

    @staticmethod
    def _mean_aka1a_probabilities(aka1a: list):
        """
        Average class_prob vectors from all available RPIs.
        """
        rows = []

        for item in aka1a:
            probs = item.get("class_prob") if isinstance(item, dict) else None
            if not probs:
                continue

            try:
                rows.append([float(v) for v in probs])
            except Exception:
                continue

        if not rows:
            return None

        n = min(len(row) for row in rows)
        if n <= 0:
            return None

        return [
            sum(row[i] for row in rows) / len(rows)
            for i in range(n)
        ]

    def _add_average_classification_to_result(self, res: dict) -> None:
        """
        Add one averaged 3-RPI AKA1A result to the result dictionary.

        New field:
            res["AKA1A_avg"]
        """
        aka1a = res.get("AKA1A") or []
        avg_probs = self._mean_aka1a_probabilities(aka1a)

        if avg_probs is None:
            return

        avg_item = {
            "class_prob": avg_probs,
        }

        pred_class, object_score, salience_score = self._threshold_aka1a_details(
            avg_item,
            threshold=self.OBJECT_THRESHOLD,
        )

        avg_item["pred_class"] = pred_class
        avg_item["object_score"] = object_score
        avg_item["salience_score"] = salience_score
        avg_item["threshold"] = self.OBJECT_THRESHOLD
        avg_item["source"] = "average_3_rpi"

        res["AKA1A_avg"] = avg_item


    def _emit_receiver_classifications_from_result(self, res: dict) -> None:
        """
        Emit one classification result per receiver.

        Expected result structure:
            res["receivers"] = ["RPI1", "RPI2", "RPI3"]
            res["AKA1A"] = [
                {"pred_class": ...},
                {"pred_class": ...},
                {"pred_class": ...},
            ]
        """
        receivers = res.get("receivers") or []
        aka1a = res.get("AKA1A") or []

        if not receivers or not aka1a:
            return

        # for receiver_id, cls_result in zip(receivers, aka1a):
        #     try:
        #         pred_class = int(cls_result.get("pred_class"))
        #     except Exception as e:
        #         logger.warning(
        #             "[CalculationController] Invalid AKA1A result for receiver %s: %s",
        #             receiver_id,
        #             e,
        #         )
        #         continue

        #     self.receiver_classification_ready.emit(str(receiver_id), pred_class)
        for receiver_id, cls_result in zip(receivers, aka1a):
            try:
                pred_class = self._threshold_aka1a_result(cls_result)
            except Exception as e:
                logger.warning(
                    "[CalculationController] Invalid AKA1A result for receiver %s: %s",
                    receiver_id,
                    e,
                )
                continue

            self.receiver_classification_ready.emit(str(receiver_id), pred_class)

    @pyqtSlot()
    def start_calculation(self) -> None:
        """
        Create worker + thread and wire model → worker. Idempotent.
        """
        if self._calc_running:
            logger.info("[CalculationController] Calculation already running.")
            if hasattr(self.menu_bar, "set_receiver_read_files_enabled"):
                self.menu_bar.set_receiver_read_files_enabled(True)
            return
        
        self.model.reset_session()
        # Create worker and thread
        worker = CalculationWorker()
        thread = start_calculation_thread(worker)

        # Wire signals: Model → Worker (queued across threads)
        self.model.job_ready.connect(worker.enqueue_job)

        worker.job_started.connect(self._on_calc_job_started)
        worker.job_finished.connect(self._on_calc_job_finished)
        worker.job_failed.connect(self._on_calc_job_failed)
        
        # NEW: cleanup only after the thread is really finished.
        thread.finished.connect(self._on_calc_thread_finished)

        # Keep references
        self._calc_worker = worker
        self._calc_thread = thread
        self._calc_running = True
        self._calc_stopping = False
        self._reference_session = None
        self._reference_index = {}
        self._reference_object = None
        self._reference_matched = []
        self._reference_matched_secs = set()
        self._kalman.reset()
        self._kalman_ref = None
        self._kalman_last_sec = None

        logger.info("[CalculationController] Calculation started.")
        # Enable "Receiver X / Read files" while calculation is running.
        if hasattr(self.menu_bar, "set_receiver_read_files_enabled"):
            self.menu_bar.set_receiver_read_files_enabled(True)

    def print_results(self, jid, res) -> None:
        self.print_res.emit(res)


    @pyqtSlot()
    def stop_calculation(self) -> None:
        """
        Request calculation shutdown.

        The worker is stopped asynchronously in its own thread. The controller
        releases references only after QThread.finished is emitted.
        """
        if not self._calc_running:
            logger.info("[CalculationController] Calculation is not running.")

            if hasattr(self.menu_bar, "set_receiver_read_files_enabled"):
                self.menu_bar.set_receiver_read_files_enabled(False)

            return

        if self._calc_stopping:
            logger.info("[CalculationController] Calculation stop already requested.")
            return

        if self._calc_worker is None or self._calc_thread is None:
            logger.warning("[CalculationController] Inconsistent calculation state during stop.")
            self._calc_running = False
            self._calc_stopping = False
            return

        self._calc_stopping = True

        logger.info("[CalculationController] Calculation stop requested.")

        # Do not accept new jobs during shutdown.
        try:
            self.model.job_ready.disconnect(self._calc_worker.enqueue_job)
        except Exception:
            pass

        # Immediately disable local reading actions in the GUI.
        if hasattr(self.menu_bar, "set_receiver_read_files_enabled"):
            self.menu_bar.set_receiver_read_files_enabled(False)

        # IMPORTANT:
        # Queue the stop call into the worker thread.
        # Do not call self._calc_worker.stop() directly.
        ok = QMetaObject.invokeMethod(
            self._calc_worker,
            "stop",
            Qt.QueuedConnection,
        )

        if not ok:
            logger.error("[CalculationController] Could not queue CalculationWorker.stop().")



    # This signature matches the suggested SFTP worker signal:
    #   files_arrived(receiver_id: str, role: str, files: list[str])
    @pyqtSlot(str, str, list)
    def on_files_arrived(self, receiver_id: str, role: str, files: List[str]) -> None:
        """
        Slot called whenever receiver files arrive.

        role == "hydro":
            register WAV files for calculation.

        role == "gps":
            register GPS TXT files for calculation.

        A calculation job is emitted only when all required receivers have
        both WAV and GPS files for the same timestamp key.
        """
        if not self._calc_running or self._calc_stopping:
            return

        if role == "hydro" and files:
            self._maybe_load_reference_track(files[0])

        for f in files:
            p = Path(f)

            if not p.exists():
                logger.warning("[CalculationController] File does not exist: %s", p)
                continue

            if role == "hydro":
                if p.suffix.lower() != ".wav":
                    continue

                ts_key = parse_wav_ts_key(p)

                if not ts_key:
                    logger.warning(
                        "[CalculationController] Could not parse WAV timestamp from %s",
                        p.name,
                    )
                    continue

                meta = FileMeta(
                    receiver_id=receiver_id,
                    path=str(p),
                    ts_key=ts_key,
                    mtime_ns=p.stat().st_mtime_ns,
                )

                self.model.update_wav(meta)

            elif role == "gps":
                if p.suffix.lower() != ".txt":
                    continue

                ts_key = parse_gps_ts_key(p)

                if not ts_key:
                    logger.warning(
                        "[CalculationController] Could not parse GPS timestamp from %s",
                        p.name,
                    )
                    continue

                meta = FileMeta(
                    receiver_id=receiver_id,
                    path=str(p),
                    ts_key=ts_key,
                    mtime_ns=p.stat().st_mtime_ns,
                )

                self.model.update_gps(meta)

            else:
                logger.debug(
                    "[CalculationController] Ignoring unknown role=%s files=%s",
                    role,
                    files,
                )

    def _maybe_load_reference_track(self, sample_file: str) -> None:
        """
        Detect the measurement session from an incoming file path and, once per
        session, load the matching object reference track (LAUV/Otter/Ponton)
        restricted to the session UTC window, then emit it for display.

        The session is the folder two levels above the file:
            <...>/<session>/RPIx/streaming/<file>
        Flat folders (e.g. .../LA/RPI1/streaming) do not match a session name,
        so no reference is loaded and nothing breaks.
        """
        try:
            p = Path(sample_file)
            if len(p.parents) < 3:
                return

            session_dir = p.parents[2]
            if session_dir.name == self._reference_session:
                return  # already handled this session

            # Mark as handled regardless of outcome to avoid repeated work.
            self._reference_session = session_dir.name

            from utils.reference_track import (
                session_object_and_date,
                load_reference_track,
                build_second_index,
            )

            obj, _date = session_object_and_date(session_dir)
            if obj is None:
                logger.info(
                    "[CalculationController] No reference object for session '%s'",
                    session_dir.name,
                )
                return

            track = load_reference_track(session_dir)
            if not track:
                logger.warning(
                    "[CalculationController] No reference track points for session '%s'",
                    session_dir.name,
                )
                return

            # Index by UTC second; the reference is drawn only at estimation
            # timestamps (added per finished job), not as the full dense track.
            self._reference_index = build_second_index(track)
            self._reference_object = obj
            self._reference_matched = []
            self._reference_matched_secs = set()

            logger.info(
                "[CalculationController] Reference '%s': %d points indexed "
                "(shown only at estimation timestamps)",
                obj,
                len(track),
            )
            # Clear any previous reference drawing.
            self.reference_track_ready.emit(obj, [])

        except Exception:
            logger.exception("[CalculationController] Failed to load reference track")

    @pyqtSlot(str, str)
    def handle_command(self, sender_id, command):
        if sender_id != "Calculation":
            return
        if command == "Start":
            self.start_calculation()
        elif command == "Stop":
            self.stop_calculation()

    @pyqtSlot(str)
    def _on_calc_job_started(self, jid: str) -> None:
        """
        Log the beginning of one calculation job and store the start time.
        """
        self._job_t0[jid] = time.perf_counter()
        logger.info("[Calc] job_started %s", jid)


    @pyqtSlot(str, dict)
    def _on_calc_job_finished(self, jid: str, res: dict) -> None:
        """
        Log successful completion of one calculation job, forward the result
        to the result dock, and update Object1 if Est_pos is available.
        """
        t0 = self._job_t0.pop(jid, None)

        if t0 is None:
            logger.info("[Calc] job_finished %s", jid)
        else:
            dt = time.perf_counter() - t0
            logger.info("[Calc] job_finished %s in %.3f s", jid, dt)

        self._emit_receiver_classifications_from_result(res)
        self._add_average_classification_to_result(res)
        self._emit_object_position_from_result(jid, res)
        self._emit_reference_for_result(res)
        self.print_results(jid, res)

    def _emit_reference_for_result(self, res: dict) -> None:
        """
        Add reference (ground-truth) positions only at the timestamps present in
        this job's Est_pos result, accumulate them chronologically, and redraw.

        Est_pos items are [time(HHMMSS, UTC), lat, lon]; the reference index is
        keyed by UTC second, so both align directly.
        """
        if not self._reference_index:
            return

        est_pos = res.get("Est_pos")
        if not est_pos:
            return

        from utils.reference_track import hhmmss_to_sec, lookup_nearest

        added = False
        for item in est_pos:
            try:
                sec = hhmmss_to_sec(item[0])
            except (IndexError, TypeError):
                continue

            if sec is None or sec in self._reference_matched_secs:
                continue

            pos = lookup_nearest(self._reference_index, sec)
            if pos is None:
                continue

            self._reference_matched_secs.add(sec)
            self._reference_matched.append((sec, pos))
            added = True

        if not added:
            return

        self._reference_matched.sort(key=lambda x: x[0])
        points = [pos for _sec, pos in self._reference_matched]
        self.reference_track_ready.emit(self._reference_object or "", points)


    @pyqtSlot(str, str)
    def _on_calc_job_failed(self, jid: str, info: str) -> None:
        """
        Log failed completion of one calculation job.
        """
        t0 = self._job_t0.pop(jid, None)

        if t0 is None:
            logger.error("[Calc] job_failed %s\n%s", jid, info)
        else:
            dt = time.perf_counter() - t0
            logger.error("[Calc] job_failed %s after %.3f s\n%s", jid, dt, info)

    @staticmethod
    def _extract_last_est_pos(est_pos):
        """
        Extract the last object position from Est_pos.

        Expected Est_pos structure:
            [
                [gps_time_1, lat_1, lon_1],
                [gps_time_2, lat_2, lon_2],
                ...
            ]

        Returns
        -------
        tuple[float, float] | None
            (lat, lon), or None if the result is invalid.
        """
        if not est_pos:
            return None

        try:
            last_pos = est_pos[-1]

            if len(last_pos) < 3:
                return None

            lat = float(last_pos[1])
            lon = float(last_pos[2])

            return lat, lon

        except Exception as e:
            logger.warning("[CalculationController] Invalid Est_pos format: %s", e)
            return None

    @staticmethod
    def _format_job_id_as_time(job_id: str) -> str:
        """
        Convert job_id from 'YYYYMMDD_HHMMSS' to 'HH:MM:SS'.

        If parsing fails, return the original job_id.
        """
        try:
            from datetime import datetime

            dt = datetime.strptime(job_id, "%Y%m%d_%H%M%S")
            return dt.strftime("%H:%M:%S")

        except Exception:
            return str(job_id)


    def _emit_object_position_from_result(self, jid: str, res: dict) -> None:
        """
        Emit all estimated object positions returned by Est_pos.

        Expected Est_pos structure:
            [
                [gps_time_1, lat_1, lon_1],
                [gps_time_2, lat_2, lon_2],
                ...
            ]

        Each valid point is emitted through the already existing
        object_position_ready(lat, lon, timestamp) signal.
        """
        if res.get("Est_pos_status") != "OK":
            logger.warning(
                "[CalculationController] Object1 not updated for job %s because Est_pos_status=%s",
                jid,
                res.get("Est_pos_status"),
            )
            return

        est_pos = res.get("Est_pos")

        if not est_pos:
            logger.warning(
                "[CalculationController] Object1 not updated for job %s because Est_pos is empty.",
                jid,
            )
            return

        # Geometric gate: accept estimates inside the hydrophone triangle, plus
        # a metre margin around it (small baseline -> many near-edge points).
        from utils.reference_track import point_in_triangle_with_margin
        triangle = self._hydrophone_triangle(res)

        emitted_points = []
        rejected = 0

        for item in est_pos:
            try:
                if len(item) < 3:
                    continue

                est_time = str(item[0])
                lat = float(item[1])
                lon = float(item[2])
                closure = float(item[3]) if len(item) > 3 else 0.0

            except Exception as e:
                logger.warning(
                    "[CalculationController] Invalid Est_pos item for job %s: %r; error=%s",
                    jid,
                    item,
                    e,
                )
                continue

            # Reject inconsistent triples (TDOA closure too large).
            if abs(closure) > self._closure_tol_m:
                rejected += 1
                continue

            # Reject estimates that fall outside the hydrophone triangle
            # (geometrically unreliable TDOA). Point/vertices are (lon, lat).
            if triangle is not None and not point_in_triangle_with_margin(
                (lon, lat), triangle[0], triangle[1], triangle[2],
                margin_m=self._geo_margin_m,
            ):
                rejected += 1
                continue

            # Temporal smoothing with the constant-velocity Kalman filter.
            sm_lat, sm_lon = self._kalman_step(est_time, lat, lon)

            emitted_points.append(
                {
                    "timestamp": est_time,
                    "lat": sm_lat,
                    "lon": sm_lon,
                }
            )

            self.object_position_ready.emit(sm_lat, sm_lon, est_time)

        if rejected:
            logger.info(
                "[CalculationController] Job %s: rejected %d/%d estimates outside hydrophone triangle.",
                jid,
                rejected,
                len(est_pos),
            )

        if emitted_points:
            res["Object1"] = emitted_points
            self._emit_object_icon(res, emitted_points[-1], triangle)

    def _emit_object_icon(self, res: dict, last_point: dict, triangle) -> None:
        """
        Pick the detected object class from the hydrophone NEAREST to the
        estimated position and emit it, so the view can show the matching icon.
        """
        if triangle is None:
            return
        aka1a = res.get("AKA1A") or []
        if not aka1a:
            return

        ox, oy = last_point["lon"], last_point["lat"]   # vertices are (lon, lat)
        best_i, best_d = None, None
        for i, v in enumerate(triangle):
            d = (v[0] - ox) ** 2 + (v[1] - oy) ** 2
            if best_d is None or d < best_d:
                best_d, best_i = d, i

        if best_i is None or best_i >= len(aka1a):
            return
        
        try:
            pred_class = self._threshold_aka1a_result(aka1a[best_i])
        except Exception:
            return

        self.object_type_detected.emit(pred_class)

    def _hydrophone_triangle(self, res: dict):
        """
        Build the hydrophone triangle for this job from the receivers' GPS
        files. Returns three (lon, lat) vertices, or None if positions for all
        three receivers are not available (then no geometric filtering).
        """
        gps_files = res.get("gps_files") or {}
        if len(gps_files) < 3:
            return None

        from utils.reference_track import parse_receiver_gps_position

        verts = []
        for path in gps_files.values():
            pos = parse_receiver_gps_position(path)
            if pos is None:
                return None
            lat, lon = pos
            verts.append((lon, lat))

        if len(verts) != 3:
            return None
        return verts

    def _kalman_step(self, est_time: str, lat: float, lon: float):
        """
        Smooth one estimated position with the constant-velocity Kalman filter.
        Works in a local metric frame anchored at the first accepted estimate;
        dt is derived from the UTC timestamps. Returns filtered (lat, lon),
        falling back to the raw point on error.
        """
        try:
            from utils.reference_track import hhmmss_to_sec

            if self._kalman_ref is None:
                self._kalman_ref = (lat, lon)

            lat0, lon0 = self._kalman_ref
            R = 6378137.0  # earth radius [m]
            mx = math.radians(lon - lon0) * R * math.cos(math.radians(lat0))
            my = math.radians(lat - lat0) * R

            sec = hhmmss_to_sec(est_time)
            if sec is None or self._kalman_last_sec is None:
                dt = None
            else:
                dt = sec - self._kalman_last_sec
            self._kalman_last_sec = sec

            fx, fy = self._kalman.update(mx, my, dt)

            f_lat = lat0 + math.degrees(fy / R)
            f_lon = lon0 + math.degrees(fx / (R * math.cos(math.radians(lat0))))
            return f_lat, f_lon

        except Exception:
            logger.exception("[CalculationController] Kalman step failed; using raw point")
            return lat, lon


    # def _emit_object_position_from_result(self, jid: str, res: dict) -> None:
    #     if res.get("Est_pos_status") != "OK":
    #         logger.warning(
    #             "[CalculationController] Object1 not updated for job %s because Est_pos_status=%s",
    #             jid,
    #             res.get("Est_pos_status"),
    #         )
    #         return

    #     est_pos = res.get("Est_pos")
    #     pos = self._extract_last_est_pos(est_pos)

    #     if pos is None:
    #         return

    #     lat, lon = pos
    #     timestamp = self._format_job_id_as_time(jid)

    #     res["Object1"] = {
    #         "timestamp": timestamp,
    #         "lat": lat,
    #         "lon": lon,
    #     }

    #     self.object_position_ready.emit(lat, lon, timestamp)
        
    @pyqtSlot()
    def _on_calc_thread_finished(self) -> None:
        """
        Final cleanup after the calculation thread has really stopped.

        This slot runs after QThread.finished, so it is safe to release Python
        references here.
        """
        logger.info("[CalculationController] Calculation thread finished.")

        self._calc_worker = None
        self._calc_thread = None
        self._calc_running = False
        self._calc_stopping = False

        try:
            self.model.reset_processed(clear_file_meta=True)
        except Exception:
            logger.exception("[CalculationController] Could not reset calculation model after stop.")

        logger.info("[CalculationController] Calculation stopped.")


class ObjectController(QObject):
    """
    Controller for Object1.
    """

    def __init__(self, model, view, menu_bar, parent=None):
        super().__init__(parent)

        self.model = model
        self.view = view
        self.menu_bar = menu_bar

        self.display_enabled = False
        self.tracking_enabled = False

        self.model.position_updated.connect(self.on_position_updated)
        self.menu_bar.command_triggered.connect(self.handle_command)

    @pyqtSlot(str, str)
    def handle_command(self, sender_id: str, command: str) -> None:
        if sender_id != self.model.object_id:
            return

        if command == "display":
            self.display_enabled = True
            self.view.show_latest()

        elif command == "hide":
            self.display_enabled = False
            self.view.hide_object()

        elif command == "track":
            self.tracking_enabled = True
            self.display_enabled = True
            self.view.show_latest()

        elif command == "stop_tracking":
            self.tracking_enabled = False

        elif command == "clear_track":
            self.view.clear_track()

    @pyqtSlot(QgsPointXY, str)
    def on_position_updated(self, point: QgsPointXY, timestamp: str) -> None:
        """
        Receive a new calculated object position.
        """
        if not self.display_enabled and not self.tracking_enabled:
            return

        self.view.display_position(
            point,
            timestamp,
            add_to_track=self.tracking_enabled,
        )