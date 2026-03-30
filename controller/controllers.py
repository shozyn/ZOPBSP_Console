from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal, QTimer, QMetaObject
from PyQt5.QtGui import QColor, QBrush
import inspect
from pathlib import Path, PureWindowsPath
from PyQt5.QtWidgets import QDialog, QMessageBox, QFileDialog, QWidget
from view.parameter_dialog import ParameterDialog
from PyQt5.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
from qgis.core import QgsRasterLayer, QgsCoordinateReferenceSystem
from utils.receiver_client_worker import ReceiverClientWorker  
from utils.math_worker import CalculationWorker, start_calculation_thread, stop_calculation_thread
from model.models import CalculationModel, FileMeta, CalcJob, parse_wav_ts_key
from view.parameter_dialog import FolderNameDialog 
from view.dock_widgets import DockResultWidget
#from utils.server_comm_sftp import ServerCommSFTP
from utils.sftp_worker import _SftpWorker
import inspect
import logging
from pathlib import Path
import string
from typing import List, Optional

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from view.widgets import MenuBar



logger = logging.getLogger(__name__)
def current_func_name() -> str:
    frame = inspect.currentframe()
    return frame.f_code.co_name if frame else "<unknown>"


class TargetController(QObject):
    stopRequested = pyqtSignal()

    def __init__(self, model, view, menu_bar, parent=None):
        super().__init__(parent)
        self.model = model
        self.view = view
        self.menu_bar = menu_bar

        self.thread: QThread | None = None
        self.worker: ReceiverClientWorker | None = None

        self.model.actual_position_updated.connect(self.view.display_actual_position)
        self.menu_bar.command_triggered.connect(self.handle_command)

        self.connected = False
        self.tracking_enabled = False
        self.display_enabled = False

    def handle_new_gps(self, lat, lon):
        #print(f"[{self.__class__.__name__}] Slot activated: [{current_func_name()}]; {lat, lon}")
        self.model.update_actual_position(lat, lon)

        if self.display_enabled:
            self.update_display()
    
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
            self.update_display()
        elif command == "hide":
            self.display_enabled = False
            self.view.clear_track()
        elif command == "track":
            self.tracking_enabled = True
        elif command == "stop_tracking":
            self.tracking_enabled = False
        elif command == "clear_track":
            self.view.clear_track()

    def update_display(self):
        if not self.display_enabled:
            return

        if self.model.actual_position:
            self.view.display_actual_position(self.model.actual_position)
    
    def connect_target(self):
        if self.connected:
            return

        self.thread = QThread(self)
        self.worker = ReceiverClientWorker(self.model.ip, self.model.port)
        self.worker.moveToThread(self.thread)
        if self.thread is None: #For Pylance
            return
        self.thread.started.connect(self.worker.start)
        self.stopRequested.connect(self.worker.stop, type=Qt.QueuedConnection)
        self.worker.finished.connect(self.thread.quit)
        self.worker.new_gps.connect(self.handle_new_gps)

        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        self.connected = True
        self.menu_bar.set_target_connection_text(self.model.target_id, True)

    def disconnect_target(self):
        if not self.connected:
            return
        
        if self.thread is None:
            return
        self.stopRequested.emit()  # queued into worker thread
        self.thread.wait(2000)       
        self.connected = False
        self.menu_bar.set_target_connection_text(self.model.target_id, False)
        self.thread = None
        self.worker = None

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

    def __init__(self, receiver_model, receiver_view, menu_bar, status_widget, parent=None):
        super().__init__(parent)

        self.model = receiver_model
        self.view = receiver_view
        self.menu_bar = menu_bar
        self.status_widget = status_widget
        self.receiver_id = receiver_model.receiver_id

        self.thread: QThread | None = None
        self.worker: _SftpWorker | None = None
        self.connected = False
        self.local_reader = None

        menu_bar.command_triggered.connect(self.handle_command)

        self.model.actual_position_updated.connect(self.view.display_actual_position)
        
    def read_local_files(self):
        """
        Offline replay from already-downloaded files.
        Uses current paths in self.model.sftp_cfg["local_dirs"], so changes in the GUI apply immediately.
        """
        from utils.local_folder_reader import LocalFolderReader

        # Optional safety: avoid mixing live downloads and offline replay
        # If you prefer, remove this guard.
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

        
        # Keep reference so object is not garbage-collected mid-emission
        self.local_reader = LocalFolderReader(self.receiver_id, batch=100, parent=self)

        # forward local-reader events exactly like the SFTP pipeline
        self.local_reader.files_arrived.connect(self.files_arrived.emit)

        # optional: route status to logs/UI
        self.local_reader.status.connect(lambda msg: logger.info(msg))

        # cleanup
        self.local_reader.finished.connect(self.local_reader.deleteLater)
        self.local_reader.finished.connect(lambda: setattr(self, "local_reader", None))

        self.local_reader.start(hydro_dir, gps_dir)
        
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
        # 4) Ensure the directory exists
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

    @pyqtSlot(str)
    def on_status_sftp_changed(self,status : str) -> None:
        self.model.set_parameter_status("Status", status)
        self.update_status_widget()
        #print(status)

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

        self.thread = None
        self.worker = None

    @pyqtSlot(str, str, list)
    def _on_worker_files_arrived(self, worker_id: str, role: str, files: list) -> None:
        """
        Relay incoming files from sftp_worker
        """
        ## self.files_arrived.emit(receiver_id, role, files)
        self.files_arrived.emit(self.receiver_id, role, files)

    def __del__(self):
        # best-effort cleanup
        try:
            self._stop_sftp()
        except Exception:
            pass
    
    def on_model_updated(self):
        self.model.update_actual_position()
        self.update_status_widget()
        self.model_changed.emit(self.receiver_id,self.model.parameters)
        
    
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
    def __init__(self, main_window, menu_bar, tool_bar=None, receiver_controllers=None):
        super().__init__()
        self.main_window = main_window
        self.menu_bar = menu_bar
        self.tool_bar = tool_bar
        self.receiver_controllers = receiver_controllers or []

        self.menu_bar.command_triggered.connect(self.handle_menu_command)
        if self.tool_bar is not None:
            self.tool_bar.bulk_action.connect(self.handle_bulk_action)

    def handle_menu_command(self, sender_id, command):
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
    def __init__(self, model: CalculationModel, menu_bar: MenuBar, dock_result: DockResultWidget,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.model = model

        # Runtime state for the calculation pipeline
        self._calc_worker: Optional[CalculationWorker] = None
        self._calc_thread = None
        self._calc_running: bool = False
        self.menu_bar = menu_bar
        self.menu_bar.command_triggered.connect(self.handle_command)
        self.print_res.connect(dock_result.add_result)

# ----------------- Lifecycle slots (bind to GUI) -----------------

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

        # Optional: observe worker signals (to update a View or logs)
        worker.job_started.connect(lambda jid: logger.info("[Calc] job_started %s", jid))
        ##worker.job_finished.connect(lambda jid, res: logger.info("[Calc] job_finished %s → %s", jid, res))
        # worker.job_finished.connect(
        #     lambda jid, res: logger.info(
        #         "[Calc] job_finished %s\n%s",
        #         jid,
        #         "\n".join(
        #             f"  {name}: {(res.get('results', res)).get(name)}"
        #             for name in ("AKA1A", "VMDv2", "TDOA", "TDOA_POS")
        #             if isinstance(res, dict) and name in (res.get("results", res))
        #         ) or f"  {res}"
        #     )
        # )

        worker.job_finished.connect(self.print_results)
        worker.job_failed.connect(lambda jid, info: logger.error("[Calc] job_failed %s\n%s", jid, info))

        # Keep references
        self._calc_worker = worker
        self._calc_thread = thread
        self._calc_running = True
        logger.info("[CalculationController] Calculation started.")
        # Enable "Receiver X / Read files" while calculation is running.
        if hasattr(self.menu_bar, "set_receiver_read_files_enabled"):
            self.menu_bar.set_receiver_read_files_enabled(True)

    def print_results(self, jid, res) -> None:
        self.print_res.emit(res)


    @pyqtSlot()
    def stop_calculation(self) -> None:
        """
        Cooperatively stop and tear down the worker thread. Idempotent.
        """
        if not self._calc_running:
            logger.info("[CalculationController] Calculation is not running.")
            if hasattr(self.menu_bar, "set_receiver_read_files_enabled"):
                self.menu_bar.set_receiver_read_files_enabled(False)
            return

        assert self._calc_worker is not None and self._calc_thread is not None

        # Disconnect model→worker to avoid late deliveries during teardown
        try:
            self.model.job_ready.disconnect(self._calc_worker.enqueue_job)
        except Exception:
            pass
        
        try:
            QMetaObject.invokeMethod(self._calc_worker, "clear_pending", Qt.QueuedConnection)
        except Exception:
            pass
        
        
        # Stop gracefully
        stopped = stop_calculation_thread(self._calc_worker, self._calc_thread, timeout_ms=3000)

        if not stopped:
            # IMPORTANT: keep references so PyQt/Qt do not destroy objects while thread is still running.
            logger.warning("[CalculationController] Stop requested but thread still running; keeping references.")
            return

        # Safe to release references now (thread finished will deleteLater both worker and thread)
        self._calc_worker = None
        self._calc_thread = None
        self._calc_running = False
        logger.info("[CalculationController] Calculation stopped.")
        # Disable "Receiver X / Read files" once calculation is stopped.
        if hasattr(self.menu_bar, "set_receiver_read_files_enabled"):
            self.menu_bar.set_receiver_read_files_enabled(False)
            
            # This makes Stop→Start act like a "simulation reset".
        try:
            self.model.reset_processed(clear_file_meta=True)
        except Exception:
            pass



    # This signature matches the suggested SFTP worker signal:
    #   files_arrived(receiver_id: str, role: str, files: list[str])
    @pyqtSlot(str, str, list)
    def on_files_arrived(self, receiver_id: str, role: str, files: List[str]) -> None:
        """
        Slot called whenever the SFTP finishes downloads.
        It creates FileMeta for the Calculation Model
        """
        if not self._calc_running:
            return
        
        for f in files:
            p = Path(f)
            if p.suffix.lower() != ".wav": #Continue
                continue  # ignore TXT and others
            if not p.exists():
                continue
            ts_key = parse_wav_ts_key(p)
            if not ts_key:
                logger.warning("[CalculationController] Could not parse ts from %s", p.name)
                continue
            meta = FileMeta(
                receiver_id=receiver_id,
                path=str(p),
                ts_key=ts_key,
                mtime_ns=p.stat().st_mtime_ns,
            )
            self.model.update_latest(meta) #The model is updated for each file separately


    @pyqtSlot(str, str)
    def handle_command(self, sender_id, command):
        if sender_id != "Calculation":
            return   
        if command == "Start":
            self.start_calculation()
        elif command == "Stop":
            self.stop_calculation()

    # @pyqtSlot(object)
    # def _on_job_ready(self, job: CalcJob) -> None:
    #     """Forward ready jobs to the calculation worker queue."""
    #     self.calc_worker.enqueue_job(job)