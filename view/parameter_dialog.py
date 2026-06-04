from PyQt5.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QDialogButtonBox, QCheckBox
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5 import QtCore, QtGui, QtWidgets
from pathlib import PureWindowsPath

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
            if editable:
                editor = QLineEdit(str(value))
            else:
                editor = QCheckBox()
                if value == "True":
                    editor.setChecked(True)
            #editor.setReadOnly(not editable)
            # if not editable:
            #     editor.setDisabled(True)  # This will grey out the field and prevent all edits/focus
            self.editors[name] = editor
            layout.addRow(label, editor)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addRow(self.button_box)

    def get_new_parameters(self):
        """Return updated parameter values as a dict {name: value, ...}"""
        #return {name: editor.text() for name, editor in self.editors.items()}
        result = {}
        for name, editor in self.editors.items():
            if isinstance(editor, QCheckBox):
                result[name] = "True" if editor.isChecked() else "False"
            else:  # QLineEdit (or other text widgets)
                result[name] = editor.text()
        return result

class FolderNameDialog(QtWidgets.QDialog):
    """
    A minimal dialog with one QLineEdit to collect a folder 'token' (e.g., 'Run_001').
    Validates Windows folder name rules and returns (text, accepted?).
    """
    def __init__(self, parent=None, initial_text="XXX"):
        super().__init__(parent)
        self.setWindowTitle("Folder name")
        self.setModal(True)
        self.initial_text = initial_text
        self._edit = QtWidgets.QLineEdit(self)
        self._edit.setText(self.initial_text)
        self._edit.setPlaceholderText("Enter folder name (e.g., Run_001)")

        # Validator: disallow characters invalid on Windows, EXCEPT the path
        # separators '/' and '\\'. The token may be a relative subpath such as
        # 'LA\\20260520_Otter1', which _set_folder joins under C:\Pi_loc.
        # Remaining invalid chars <>:"|?* and ASCII control chars are blocked;
        # trailing dots/spaces and reserved names are refined in _on_accept.
        invalid_chars = r'<>:"|?*\x00-\x1F'
        # Accept anything that does NOT contain these characters (validation is refined on accept).
        rx = QtCore.QRegularExpression(f'^[^{invalid_chars}]+$')
        self._edit.setValidator(QtGui.QRegularExpressionValidator(rx, self))

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel,
            QtCore.Qt.Horizontal, self
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self._on_reject)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("Folder name:"))
        lay.addWidget(self._edit)
        lay.addWidget(btns)

        self._edit.setFocus()
        self._edit.selectAll()
    def _on_reject(self):
        self._edit.setText(self.initial_text)
        self.reject()
        
    def _on_accept(self):
        token = self._edit.text()

        # Basic final checks (Windows rules)
        # - not empty after stripping
        # - no trailing dot or space
        # - not a reserved device name like 'CON', 'NUL', 'PRN', 'COM1'...'LPT9'
        token_stripped = token.strip()
        if not token_stripped:
            QtWidgets.QMessageBox.warning(self, "Invalid name", "Please enter a non-empty name.")
            return

        if token_stripped.endswith('.') or token_stripped.endswith(' '):
            QtWidgets.QMessageBox.warning(self, "Invalid name", "Folder names must not end with a dot or space.")
            return

        # Check Windows reserved names using PureWindowsPath.is_reserved()
        # (works even on non-Windows hosts)
        if PureWindowsPath(token_stripped).is_reserved():
            QtWidgets.QMessageBox.warning(self, "Invalid name", f"'{token_stripped}' is a reserved name on Windows.")
            return

        # Passed checks → accept
        self._edit.setText(token_stripped)
        self.accept()

    @staticmethod
    def get_folder_token(parent=None, initial_text="XXX"):
        dlg = FolderNameDialog(parent=parent, initial_text=initial_text)
        ok = dlg.exec_() == QtWidgets.QDialog.Accepted
        return dlg._edit.text(), ok
