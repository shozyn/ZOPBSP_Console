from PyQt5.QtCore import QObject, pyqtSignal
import inspect
from PyQt5.QtWidgets import QDialog
from view.parameter_dialog import ParameterDialog
from PyQt5.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
from qgis.core import QgsRasterLayer, QgsCoordinateReferenceSystem
from utils.receiver_client_worker import ReceiverClientWorker  # we'll use this from before
#from utils.server_comm_sftp import ServerCommSFTP
from utils.sftp_worker import _SftpWorker
import inspect
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
logger.debug("low-level details you only want in the file")
logger.info("user-visible status you want in the dock")


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
        print(f"[{self.__class__.__name__}] Slot activated: {inspect.currentframe().f_code.co_name}; {lat, lon}")
        self.model.update_actual_position(lat, lon)

        if self.display_enabled:
            self.update_display()
    
    @pyqtSlot(str, str)
    def handle_command(self, sender_id, command):
        logger.info(f"[{self.__class__.__name__}] Slot activated: {inspect.currentframe().f_code.co_name}; {sender_id, command}")
        print(f"[{self.__class__.__name__}] Slot activated: {inspect.currentframe().f_code.co_name}; {sender_id, command}")
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
        # if self.model.predicted_position:
        #     self.view.display_predicted_position(self.model.predicted_position)
    
    def connect_target(self):
        # if not self.connected and not self.thread.isRunning():
        #     self.thread.start()
        if self.connected:
            return
        
        self.thread = QThread(self)
        self.worker = ReceiverClientWorker(self.model.ip, self.model.port)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.start)
        self.stopRequested.connect(self.worker.stop, type=Qt.QueuedConnection)
        self.worker.finished.connect(self.thread.quit)
        self.worker.new_gps.connect(self.handle_new_gps)

        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        self.connected = True
        self.menu_bar.set_target_connection_text(self.model.target_id, True)
        print(f"[{self.__class__.__name__}] Connected to {self.model.target_id}")

    def disconnect_target(self):
        # if self.connected:
        #     self.stopRequested.emit()
        #     self.thread.quit()
        #     self.thread.wait()
        if not self.connected:
            return
        
        self.stopRequested.emit()  # queued into worker thread
        self.thread.wait(2000)         # optional: block briefly for clean join

        self.connected = False
        self.menu_bar.set_target_connection_text(self.model.target_id, False)
        print(f"[{self.__class__.__name__}] Disconnected from {self.model.target_id}")

        self.thread = None
        self.worker = None

    def __del__(self):
        # best-effort cleanup
        try:
            self.disconnect_target()
        except Exception:
            pass

class ReceiverController(QObject):
    """
    Controller for receiver interactions.
    """
    stopRequested = pyqtSignal()  


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


        menu_bar.command_triggered.connect(self.handle_receiver_command)
        menu_bar.command_triggered.connect(self.handle_command)
        self.model.status_changed.connect(self.update_receiver_params)
        self.connected = False
     

    def handle_receiver_command(self, receiver_id, command_name):
        if receiver_id != self.model.receiver_id:
            return

        if command_name == "set_parameters":
            dialog = ParameterDialog(self.model.parameters)
            if dialog.exec_() == QDialog.Accepted:
                new_params = dialog.get_new_parameters()
                for name, value in new_params.items():
                    self.model.set_parameter(name, value)

    @pyqtSlot(str, str)
    def handle_command(self, sender_id, command):
        logger.info(f"[{self.__class__.__name__}] Slot activated: {inspect.currentframe().f_code.co_name}; {sender_id, command}")
        print(f"[{self.__class__.__name__}] Slot activated: {inspect.currentframe().f_code.co_name}; {sender_id, command}")
        if sender_id != self.model.receiver_id:
            return

        if command == "connect":
            self.connect_receiver()
        elif command == "disconnect":
            self.disconnect_receiver()

    @pyqtSlot(str)
    def on_status_sftp_changed(self,status : str) -> None:
        print(status)

    def connect_receiver(self):
        print("Connect_receiver triggered")
        self._start_sftp()

    def disconnect_receiver(self):
        print("Disconnect_receiver triggered")
        self._stop_sftp()

    # ---------------- public API (optional) ----------------
    def send_control_text(self, text: str):
        """Write-once upload of control.txt"""
        if self._sftp_worker:
            self._sftp_worker.request_control_text(text)

    def send_control_file(self, local_path: str | Path):
        if self._sftp_worker:
            self._sftp_worker.request_control_file(str(local_path))

    # ---------------- lifecycle ----------------
    def _start_sftp(self):
        if self.connected:
            return

        self.thread = QThread(self)
        self.worker = _SftpWorker(self.model.sftp_cfg)
        self.worker.status_changed.connect(self.on_status_sftp_changed)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.start)                    # worker creates QTimer inside start()
        self.stopRequested.connect(self.worker.stop, type=Qt.QueuedConnection)  # stop in worker thread
        self.worker.finished.connect(self.thread.quit)

        # (optional UI/log hooks)
        #self.worker.status.connect(self.status_widget.add_text)
        #self.worker.error.connect(self.status_widget.add_text)

        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

        self.connected = True
        self.menu_bar.set_receiver_connection_text(self.receiver_id, True)
        print(f"[{self.__class__.__name__}] Connected to {self.receiver_id}")

    def _stop_sftp(self):
        if not self.connected:
            return
        self.stopRequested.emit()     # queued -> worker.stop() in worker thread
        if self.thread:
            self.thread.wait(2000)    # brief join

        self.connected = False
        self.menu_bar.set_receiver_connection_text(self.receiver_id, False)
        print(f"[{self.__class__.__name__}] Disconnected from {self.receiver_id}")

        self.thread = None
        self.worker = None

    def __del__(self):
        # best-effort cleanup
        try:
            self._stop_sftp()
        except Exception:
            pass

    def update_receiver_params(self, params_dict):
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
                    if pname in params_dict:
                        value_item.setText(str(params_dict[pname].get("value")))
                break

class MainController(QObject):
    """
    Main application controller (handles user input, updates models and views).
    """
    def __init__(self, main_window, menu_bar):
        super().__init__()
        self.main_window = main_window
        self.menu_bar = menu_bar

        self.menu_bar.command_triggered.connect(self.handle_menu_command)

    def handle_menu_command(self, sender_id, command):
        if sender_id != "": # Handle only project functions
            return  
        """
        Receives the command string from the menu bar and dispatches to the correct logic.
        """
        print(f"[{self.__class__.__name__}] Slot activated: {inspect.currentframe().f_code.co_name}; {sender_id, command}")

        if command == "open_project":
            self.open_project()
        elif command == "close_project":
            self.close_project()
        elif command == "new_project":
            self.new_project()
        # Add more commands as needed
        else:
            print(f"[MainController] Unknown command received: {command}")

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

    def __init__(self, map_view, map_model,map_layer, toolbar=None):
        super().__init__()
        self.map_view = map_view
        self.map_view.map_moved.connect(self.on_map_moved)
        self.map_model = map_model
        self.toolbar = toolbar
        self.map_layer = map_layer

        # Connect the model's signal to the view's slot
        self.map_model.layers_changed.connect(self.map_view.set_layers)

        if self.map_layer:
            self.add_raster_layer(self.map_layer)

        if self.toolbar is not None:
            self.toolbar.tool_changed.connect(self.map_view.on_send_tool)

    def add_raster_layer(self, path, crs="EPSG:4326"):
        layer = QgsRasterLayer(path)
        if not layer.isValid():
            print(f"Layer failed to load: {path}")
            return
            
        layer.setCrs(QgsCoordinateReferenceSystem(crs))
        self.map_model.add_layer(layer)
        
    
    def on_map_moved(self, point):
        self.coordinates_changed.emit(point.y(), point.x())
