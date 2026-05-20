import sys
from PyQt5.QtWidgets import QMessageBox
from config.config_loader import Config, ConfigError, DataError
from qgis.core import QgsApplication
from view.mainwindow import MainWindow
from view.widgets import MapView, ToolBar, make_coord_label
from controller.controllers import MapController, MainController, ReceiverController, TargetController, ObjectController, CalculationController
from view.widgets import MenuBar
from model.models import ReceiverModel, TargetModel, ObjectModel, MapModel, CalculationModel
from view.view import ReceiverView, TargetView, ObjectView
from utils.loggings import setup_logging_for_app, LoggingConfig
from utils.status_builder import populate_status_panel
from utils.math_worker import CalculationWorker
import logging

from view.dock_widgets import StatusWidget, DockInformationWidget, DockResultWidget
import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

def main():
    qgs = QgsApplication([], True)
    qgs.initQgis()

    CONFIG_PATH = "config/configPi.yaml"
    #CONFIG_PATH = "config/configWin.yaml"

    try:
     config = Config(CONFIG_PATH)
    except Exception as e:
        if isinstance(Exception,ConfigError):           
            QMessageBox.critical(None, "Conif file cannot be read", str(e)) 
        if isinstance(Exception,DataError):
            QMessageBox.critical(None, "Data cannot be read", str(e))  
        else:
            QMessageBox.critical(None, "Unknown error while loading YAML file", str(e))  
                
        qgs.exitQgis()
        sys.exit(1)  

    log_cfg_dict = config.log_cfg 
    receivers_cfg = config.receivers
    targets_cfg = config.targets

    map_layer = config.get_layer()
    map_view = MapView()
    map_model = MapModel()

    # tool_bar = ToolBar()
    tool_bar = ToolBar(receivers=receivers_cfg)
    menu_bar = MenuBar(receivers=receivers_cfg, targets=targets_cfg)
    map_controller = MapController(map_view, map_model, map_layer, tool_bar,menu_bar)
    coord_label = make_coord_label() #GUI label
    status_widget = StatusWidget()
    dock_info = DockInformationWidget() #GUI logs
    dock_result = DockResultWidget()

    #RECEIVERS
    receiver_models = []
    receiver_views = []
    receiver_controllers = []

    for rx_cfg in receivers_cfg:
        parameters = {"status": rx_cfg.get("status",{}),"param_monitor": rx_cfg.get("param_monitor", {}),"param_control": \
                     rx_cfg.get("param_control", {})}
        receiver_id = rx_cfg.get("id")
        sftp_cfg = rx_cfg.get("sftp", {})
        rx_model = ReceiverModel(receiver_id=receiver_id, parameters=parameters,sftp_cfg=sftp_cfg)
        rx_colour = rx_cfg.get("status",{}).get("Colour",{}).get("value","red")
        rx_view = ReceiverView(map_view.m_MapCanvas,rx_colour) 
        # rx_controller = ReceiverController(rx_model, rx_view, menu_bar,status_widget)
        rx_controller = ReceiverController(
                                            rx_model,
                                            rx_view,
                                            menu_bar,
                                            status_widget,
                                            tool_bar=tool_bar,
                                        )

        receiver_models.append(rx_model)
        receiver_views.append(rx_view)
        receiver_controllers.append(rx_controller)


    # TARGET
    target_models = []
    target_views = []
    target_controllers = []

    for target_cfg in targets_cfg:
        target_id = target_cfg.get("id", "TargetUnknown")
        parameters = target_cfg.get("parameters", {}) or {}

        ip_meta = parameters.get("IP") or {}
        port_meta = parameters.get("Port") or {}

        target_ip = ip_meta.get("value")
        target_port_raw = port_meta.get("value")

        if not target_ip:
            # logger.warning(
            #     "[Target] Missing IP address for %s. Target skipped.",
            #     target_id,
            # )
            continue

        try:
            target_port = int(target_port_raw)
        except (TypeError, ValueError):
            # logger.warning(
            #     "[Target] Invalid UDP port for %s: %r. Target skipped.",
            #     target_id,
            #     target_port_raw,
            # )
            continue

        target_model = TargetModel(target_id, target_ip, target_port)
        target_view = TargetView(map_view.m_MapCanvas)
        target_controller = TargetController(
            target_model,
            target_view,
            menu_bar,
        )

        target_models.append(target_model)
        target_views.append(target_view)
        target_controllers.append(target_controller)

    # OBJECT
    object_model = ObjectModel("Object1")
    object_view = ObjectView(map_view.m_MapCanvas)
    object_controller = ObjectController(object_model, object_view, menu_bar)


    #populate_from_yaml(status_widget.get_model(), receivers_cfg, targets_cfg)
    populate_status_panel(
    status_widget.get_model(),
    receivers_cfg,
    targets_cfg
)
    status_widget.tree.expandAll()
    status_widget.tree.resizeColumnToContents(0)
    status_widget.tree.resizeColumnToContents(1)

    #target_controller.connect_target()
    main_window = MainWindow(map_view=map_view,menu_bar=menu_bar,
                        tool_bar=tool_bar,coord_label=coord_label,status_widget=status_widget,
                        dock_info=dock_info,dock_result=dock_result)
    
    root_logger, log_listener, gui_handler = setup_logging_for_app(
    main_window.dock_info.add_text,
    LoggingConfig(
        file_path=log_cfg_dict["file"],
        file_level=log_cfg_dict["file_level"],
        gui_level=log_cfg_dict["gui_level"],
        ring_capacity=log_cfg_dict["ring_capacity"],
        rotate=log_cfg_dict["rotate"],
        max_bytes=log_cfg_dict["max_bytes"],
        backup_count=log_cfg_dict["backup_count"],
    ),
    )

    receiver_ids = []
    receiver_ids = tuple(rc.receiver_id for rc in receiver_controllers)
    calc_model = CalculationModel(required_receivers=receiver_ids)
    calc_controller = CalculationController(calc_model, menu_bar=menu_bar, dock_result=dock_result)
    
    main_controller = MainController(main_window=main_window, menu_bar = menu_bar,tool_bar=tool_bar,
                                     receiver_controllers=receiver_controllers)
    
    calc_controller.object_position_ready.connect(object_model.update_position)
    calc_controller.object_position_ready.connect(object_model.update_position)

    for rc in receiver_controllers:
        rc.files_arrived.connect(calc_controller.on_files_arrived)
        calc_controller.receiver_classification_ready.connect(rc.on_classification_ready)


    map_controller.coordinates_changed.connect(main_window.on_coordinates_changed)
    main_window.show()
    exit_code = qgs.exec()
    qgs.exitQgis()
    sys.exit(exit_code)

if __name__ == "__main__":
    main()