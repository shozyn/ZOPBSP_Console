from PyQt5.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QDialogButtonBox
from PyQt5.QtCore import Qt, pyqtSignal

class ParameterDialog(QDialog):
    """
    Dialog to display and edit receiver parameters dynamically.
    """
    # control_params_set = pyqtSignal(dict)
    
    def __init__(self, parameters, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Parameters")
        
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.editors = {} 

        layout = QFormLayout(self)
        for name, info in parameters.get("param_control", {}).items():
            value = info.get("value", "")
            editable = info.get("readable", True)
            label = QLabel(name)
            editor = QLineEdit(str(value))
            editor.setReadOnly(not editable)
            if not editable:
                editor.setDisabled(True)  # This will grey out the field and prevent all edits/focus
            self.editors[name] = editor
            layout.addRow(label, editor)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addRow(self.button_box)

    def get_new_parameters(self):
        """Return updated parameter values as a dict {name: value, ...}"""
        return {name: editor.text() for name, editor in self.editors.items()}
    