from PyQt5.QtWidgets import QMainWindow


class MainWindow(QMainWindow):
    """
    Main application window (View).
    """
    def __init__(self, map_view, menu_bar, tool_bar, coord_label, status_widget,
                 dock_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ZOPBSP Console")
        self.resize(1200, 800)

        self.map_view = map_view
        self.setCentralWidget(self.map_view.m_MapCanvas)
        
        self.addToolBar(tool_bar)
        self.setMenuBar(menu_bar)  # Use the passed-in menu_bar



        # Status Dock
        self.status_widget = status_widget
        self.addDockWidget(self.status_widget.default_area, self.status_widget)

        # Information Dock
        self.dock_info = dock_info
        self.addDockWidget(self.dock_info.default_area, self.dock_info)

        # Status bar
        self.status = self.statusBar()
        self.coord_label = coord_label
        self.status.addWidget(self.coord_label)

        
    def on_coordinates_changed(self, lat, lon):
        self.coord_label.setText(f"lat: {lat:.8f}; lon: {lon:.8f}")
