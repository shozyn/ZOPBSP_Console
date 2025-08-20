from PyQt5.QtWidgets import QDockWidget, QTreeView, QPlainTextEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem

class StatusWidget(QDockWidget):
    """
    Dock widget for receiver/target parameters.
    """
    default_area = Qt.RightDockWidgetArea

    def __init__(self, parent=None):
        super().__init__("Status Panel", parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.tree = QTreeView(self)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setEditTriggers(QTreeView.DoubleClicked | QTreeView.EditKeyPressed)

        #from view.parameter_delegate import ParameterDelegate
        #self.tree.setItemDelegate(ParameterDelegate(schema_lookup=self._schema_for_index))


        self.setWidget(self.tree)

        # 2-column model: Name | Value
        self.model = QStandardItemModel(self)
        self.model.setHorizontalHeaderLabels(["Name", "Value"])
        self.tree.setModel(self.model)

    def get_model(self):
        return self.model

    def clear(self):
        self.model.removeRows(0, self.model.rowCount())

    def _schema_for_index(self, index):
        # You can precompute {("Receiver", id, "ParamName"): meta} and look it up here.
        # For brevity return {} -> line edit fallback.
        return {}


class DockInformationWidget(QDockWidget):
    """
    Dock widget for application logs/info.
    """
    default_area = Qt.BottomDockWidgetArea

    def __init__(self, parent=None):
        super().__init__("Log", parent)
        self.setAllowedAreas(Qt.BottomDockWidgetArea)

        text_edit = QPlainTextEdit()
        text_edit.setReadOnly(True)
        # Optional: limit blocks to guard memory; this is an extra safety
        # The GUI handler also keeps a ring buffer (authoritative).
        text_edit.setMaximumBlockCount(10000)  # tweak via config later if desired

        self.setWidget(text_edit)
        self.text_edit = text_edit

    def add_text(self, text):
        self.text_edit.appendPlainText(text)
