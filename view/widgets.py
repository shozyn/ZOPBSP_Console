from PyQt5.QtWidgets import QLabel, QToolBar, QAction, QActionGroup, QMenuBar
from qgis.gui import QgsMapCanvas, QgsMapTool, QgsMapToolPan, QgsMapToolZoom, QgsVertexMarker
from qgis.core import QgsRasterLayer, QgsCoordinateReferenceSystem, QgsPointXY, QgsCoordinateTransform, QgsProject
from PyQt5.QtWidgets import QWidget, QSizePolicy
from PyQt5.QtGui import QMouseEvent, QColor, QCursor, QWheelEvent
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QSize
from typing import  Optional

def make_coord_label() -> QLabel:
    return QLabel("Coordinates: ")

class ToolBar(QToolBar):
    """
    Custom toolbar for the application.
    """
    tool_changed = pyqtSignal(str)
    bulk_action = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__("Tools", parent)
        self._setup_actions()

    def _setup_actions(self):
        self.action_group = QActionGroup(self)
        self.action_group.setExclusive(True)

        self.action_show = QAction("Show", self)
        self.action_show.setCheckable(True)
        self.action_show.triggered.connect(lambda: self.tool_changed.emit("Show"))
        self.addAction(self.action_show)

        self.action_pan = QAction("Pan", self)
        self.action_pan.setCheckable(True)
        self.action_pan.triggered.connect(lambda: self.tool_changed.emit("Pan"))
        self.addAction(self.action_pan)

        self.action_zoom_in = QAction("Zoom In", self)
        self.action_zoom_in.setCheckable(True)
        self.action_zoom_in.triggered.connect(lambda: self.tool_changed.emit("zoomIn"))
        self.addAction(self.action_zoom_in)

        self.action_zoom_out = QAction("Zoom Out", self)
        self.action_zoom_out.setCheckable(True)
        self.action_zoom_out.triggered.connect(lambda: self.tool_changed.emit("zoomOut"))
        self.addAction(self.action_zoom_out)

        self.action_group.addAction(self.action_show)
        self.action_group.addAction(self.action_pan)
        self.action_group.addAction(self.action_zoom_in)
        self.action_group.addAction(self.action_zoom_out)

        self.action_show.setChecked(True)
        self.addSeparator()
        act_set_all = QAction("Set Parameters All", self)
        act_set_all.triggered.connect(lambda: self.bulk_action.emit("set_params_all"))
        self.addAction(act_set_all)

        act_connect_all = QAction("Connect All", self)
        act_connect_all.triggered.connect(lambda: self.bulk_action.emit("connect_all"))
        self.addAction(act_connect_all)

        act_disconnect_all = QAction("Disconnect All", self)
        act_disconnect_all.triggered.connect(lambda: self.bulk_action.emit("disconnect_all"))
        self.addAction(act_disconnect_all)
        
        #act_read_all = QAction("Read All", self)
        #act_read_all.triggered.connect(lambda: self.bulk_action.emit("read_all"))
        #self.addAction(act_read_all)

class MenuBar(QMenuBar):
    """
    Menu bar for the main window. 
    """
    command_triggered = pyqtSignal(str, str)  # e.g., ("RPI1", "connect")

    def __init__(self, receivers, targets=None,  parent=None):
        super().__init__(parent)
        self.receiver_connect_actions = {}
        self.target_connect_actions = {}
        self.target_display_actions = {}
        self.target_track_actions = {}
        self.object_display_actions = {}
        self.object_track_actions = {}
        self.receiver_read_actions = {}  # ReceiverID -> QAction("Read files")
        self.calc_action:  Optional[QAction] = None

        self._setup_menu(receivers, targets or [])

    def set_receiver_read_files_enabled(self, enabled: bool) -> None:
        """Enable/disable *all* Receiver/Read files actions."""
        for act in self.receiver_read_actions.values():
            act.setEnabled(enabled)
            
    def _setup_menu(self, receivers,targets):
        # Define your menus and commands here
        project_menu = self.addMenu("Project")
        commands = [
            ("Open Project", "open_project"),
            ("Close Project", "close_project"),
            ("New Project", "new_project"),
        ]
        for display_name, command_name in commands:
            action = QAction(display_name, self) # self -> parent
            action.triggered.connect(lambda checked=False, name=command_name: self.command_triggered.emit("", name)) #checked -> optional, True if teh action is checkable
            project_menu.addAction(action)
            
        map_menu = self.addMenu("Map")
        act_zoom_to_full = QAction("Zoom to Full Size",self)
        act_zoom_to_full.triggered.connect(lambda: self.command_triggered.emit("Map","zoom_to_full"))
        map_menu.addAction(act_zoom_to_full)
        #self.send_zoom_to_full.connect(self.m_map.on_zoom_to_full)

        calc_menu = self.addMenu("Calculation")
        self.calc_action = QAction("Start",self)
        if self.calc_action is not None:
            self.calc_action.triggered.connect(lambda: self._toggle_calculation())
            calc_menu.addAction(self.calc_action)


        # Target Menus with toggle logic
        for tgt in targets:
            tgt_id = tgt["id"]
            menu = self.addMenu(f"{tgt_id}")

            # Connect / Disconnect toggle
            connect_action = QAction("Connect", self)
            connect_action.triggered.connect(lambda _, tid=tgt_id: self._toggle_connection(tid))
            menu.addAction(connect_action)
            self.target_connect_actions[tgt_id] = connect_action

            # Display / Hide toggle
            display_action = QAction("Display", self)
            display_action.triggered.connect(lambda _, tid=tgt_id: self._toggle_display(tid))
            menu.addAction(display_action)
            self.target_display_actions[tgt_id] = display_action

            # Track / Stop Tracking toggle
            track_action = QAction("Track", self)
            track_action.triggered.connect(lambda _, tid=tgt_id: self._toggle_tracking(tid))
            menu.addAction(track_action)
            self.target_track_actions[tgt_id] = track_action

            menu.addAction(self._make_action("Clear Track", tgt_id, "clear_track"))

        # Object Menus with toggle logic
        object_id = "Object1"
        object_menu = self.addMenu(object_id)

        display_action = QAction("Display", self)
        display_action.triggered.connect(
            lambda _, oid=object_id: self._toggle_object_display(oid)
        )
        object_menu.addAction(display_action)
        self.object_display_actions[object_id] = display_action

        track_action = QAction("Track", self)
        track_action.triggered.connect(
            lambda _, oid=object_id: self._toggle_object_tracking(oid)
        )
        object_menu.addAction(track_action)
        self.object_track_actions[object_id] = track_action

        object_menu.addAction(
            self._make_action("Clear Track", object_id, "clear_track")
        )




        for rx in receivers:
            rx_id = rx["id"]
            #print(f"rx_id\n{rx_id}")
            receiver_menu = self.addMenu(f"Receiver {rx_id}")

            # Connect / Disconnect toggle (like targets)
            connect_action = QAction("Connect", self)
            connect_action.setCheckable(False)
            # capture rid now; QAction.triggered(bool) passes a bool arg -> use placeholder "_"
            connect_action.triggered.connect(lambda _, rid=rx_id: self._toggle_receiver_connection(rid))
            receiver_menu.addAction(connect_action)
            self.receiver_connect_actions[rx_id] = connect_action

            # Set Parameters action (unchanged)
            set_params_action = QAction("Set Parameters", self)
            set_params_action.setCheckable(False)
            set_params_action.triggered.connect(lambda _, rid=rx_id: self.command_triggered.emit(rid, "set_parameters"))
            receiver_menu.addAction(set_params_action)
            
            read_local_action = QAction("Calculate Files", self)
            read_local_action.setCheckable(False)
            read_local_action.setEnabled(False)  # <-- key requirement
            read_local_action.triggered.connect(lambda _, rid=rx_id: self.command_triggered.emit(rid, "read_local"))
            receiver_menu.addAction(read_local_action)
            self.receiver_read_actions[rx_id] = read_local_action
            
            download_action = QAction("Download files", self)
            download_action.setCheckable(False)
            download_action.triggered.connect(lambda _, rid=rx_id: self.command_triggered.emit(rid, "download_files"))
            receiver_menu.addAction(download_action)

    def _toggle_calculation(self):
        """
        Flip Calculation 'Start' <-> 'Stop' and emit the corresponding command.
        """
        if self.calc_action is not None:
            is_calculating = self.calc_action.text().lower() == "stop"
            self.calc_action.setText("Start" if is_calculating else "Stop")
            self.command_triggered.emit("Calculation","Stop" if is_calculating else "Start")

    def _toggle_receiver_connection(self, receiver_id: str):
        """
        Flip Receiver menu 'Connect' <-> 'Disconnect' and emit the corresponding command.
        """
        action = self.receiver_connect_actions[receiver_id]
        is_connecting = action.text().lower() == "connect"
        action.setText("Disconnect" if is_connecting else "Connect")
        # notify controllers
        self.command_triggered.emit(receiver_id, "connect" if is_connecting else "disconnect")

    def set_receiver_connection_text(self, receiver_id: str, connected: bool):
        """
        External setter for controllers to sync menu text with actual state.
        Example: menu_bar.set_receiver_connection_text("R1", connected=True)
        """
        action = self.receiver_connect_actions.get(receiver_id)
        if action:
            action.setText("Disconnect" if connected else "Connect")
    
    def _make_action(self, label, object_id, command):
        action = QAction(label, self)
        action.triggered.connect(lambda _, oid=object_id, cmd=command: self.command_triggered.emit(oid, cmd))
        return action

    def _toggle_connection(self, target_id):
        action = self.target_connect_actions[target_id]
        is_connecting = action.text().lower() == "connect"
        action.setText("Disconnect" if is_connecting else "Connect")
        self.command_triggered.emit(target_id, "connect" if is_connecting else "disconnect")

    def _toggle_display(self, target_id):
        action = self.target_display_actions[target_id]
        is_displaying = action.text().lower() == "display"
        action.setText("Hide" if is_displaying else "Display")
        self.command_triggered.emit(target_id, "display" if is_displaying else "hide")

    def _toggle_tracking(self, target_id):
        action = self.target_track_actions[target_id]
        is_tracking = action.text().lower() == "track"
        action.setText("Stop Tracking" if is_tracking else "Track")
        self.command_triggered.emit(target_id, "track" if is_tracking else "stop_tracking")

    def set_target_connection_text(self, target_id, connected: bool):
        action = self.target_connect_actions.get(target_id)
        if action:
            action.setText("Disconnect" if connected else "Connect")


    def _toggle_object_display(self, object_id: str):
        action = self.object_display_actions[object_id]
        is_displaying = action.text().lower() == "display"

        action.setText("Hide" if is_displaying else "Display")

        self.command_triggered.emit(
            object_id,
            "display" if is_displaying else "hide",
        )


    def _toggle_object_tracking(self, object_id: str):
        action = self.object_track_actions[object_id]
        is_tracking = action.text().lower() == "track"

        action.setText("Stop Tracking" if is_tracking else "Track")

        self.command_triggered.emit(
            object_id,
            "track" if is_tracking else "stop_tracking",
        )

class MyQgsMapCanvas(QgsMapCanvas):
    map_moved = pyqtSignal(QgsPointXY)
    map_clicked = pyqtSignal(QgsPointXY)

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        def sizeHint(self):
            return QSize(800, 600)

    def mouseMoveEvent(self, event: QMouseEvent):
        point = self.getCoordinateTransform().toMapCoordinates(event.pos().x(), event.pos().y()) # type: ignore
        self.map_moved.emit(point)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        point = self.getCoordinateTransform().toMapCoordinates(event.pos().x(), event.pos().y()) # type: ignore
 
        # src_crs = QgsCoordinateReferenceSystem.fromEpsgId(32634)
        # dst_crs = QgsCoordinateReferenceSystem.fromEpsgId(4326)  # WGS84 lon/lat
        # xform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
        # point = xform.transform(point)
        self.map_clicked.emit(point)
        super().mousePressEvent(event)

class ShowMapTool(QgsMapTool):
    def __init__(self, canvas: QgsMapCanvas):
        super().__init__(canvas)
        self.canvas = canvas
        self.setCursor(QCursor(Qt.ArrowCursor))

class DrawReceiver(QObject):
    """
    Handles drawing and updating receiver markers on the map.
    """
    def __init__(self, canvas: QgsMapCanvas, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.markers = dict()  # {receiver_nb: QgsVertexMarker}

    def _draw_receiver(self,center: QgsPointXY, receiver_nb: int):
        pass
    
    def on_to_map_draw_receiver(self,pos: QgsPointXY):
        pass

class WheelBlocker(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QWheelEvent.Wheel:
            return True
        return False

class MapView(QObject):
    """
    MVC 'View' for the map. Handles all map display and interaction.
    """
    map_moved = pyqtSignal(QgsPointXY)
    def __init__(self, parent=None):
        super().__init__(parent)
        self.m_MapCanvas = MyQgsMapCanvas()
        self.m_MapCanvas.map_moved.connect(self.map_moved)
        self.wheel_blocker = WheelBlocker()
        self.m_MapCanvas.viewport().installEventFilter(self.wheel_blocker)
        self.m_MapCanvas.setCanvasColor(QColor('white'))
        self.m_MapCanvas.freeze(False)
        self.m_MapCanvas.setVisible(True)
        #self.m_MapCanvas.setDestinationCrs(QgsCoordinateReferenceSystem.fromEpsgId(4326))
        self.m_MapCanvas.refresh()
        self.m_MapCanvas.show()

        
    def set_layers(self, layers):
        """Slot to update displayed layers (called by controller)."""

        self.m_MapCanvas.setLayers(layers)
        if layers:
            self.m_MapCanvas.setExtent(layers[0].extent())

        #self.m_MapCanvas.setDestinationCrs(QgsCoordinateReferenceSystem.fromEpsgId(4326))
        self.m_MapCanvas.refresh()

        # self.mapLayers = []
        # layer_path = "C:\\Code\\Console\\kosobudno.tif"  # TODO: make configurable
        # layer = QgsRasterLayer(layer_path)
        # if not layer.isValid():
        #     print("Layer failed to load!")
        # else:
        #     print("Layer loaded successfully.")
        #     layer.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
        # self.mapLayers.append(layer)
        # self.m_MapCanvas.setExtent(layer.extent())
        # self.m_MapCanvas.setLayers(self.mapLayers)
        # self.m_MapCanvas.refresh()

        self.showTool = ShowMapTool(self.m_MapCanvas)
        self.panTool = QgsMapToolPan(self.m_MapCanvas)
        self.zoomInTool = QgsMapToolZoom(self.m_MapCanvas, False)
        self.zoomOutTool = QgsMapToolZoom(self.m_MapCanvas, True)
        self.drawReceiver = DrawReceiver(self.m_MapCanvas)


    def on_send_tool(self, tool: str):
        #print(f"In class {self.__class__.__name__}: tool = {tool}")
        if tool == "Show":
            self.m_MapCanvas.setMapTool(self.showTool)
        elif tool == "Pan":
            self.m_MapCanvas.setMapTool(self.panTool)
        elif tool == "zoomIn":
            self.m_MapCanvas.setMapTool(self.zoomInTool)
        elif tool == "zoomOut":
            self.m_MapCanvas.setMapTool(self.zoomOutTool)

    def on_zoom_to_full(self):
        self.m_MapCanvas.zoomToFullExtent()
