from PyQt5.QtWidgets import QDockWidget, QTreeView, QPlainTextEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem
import numpy as np

OUTPUT_CLASSES = [
    "Cisza",
    "Cargo_47",
    "LAUV",
    "Otter",
    "Passengership_109",
    "Ponton_2",
    "Ponton_3",
    "INNE",
]

def _to_python_scalar(x):
    """
    Convert NumPy scalar to native Python scalar if needed.
    """
    if isinstance(x, np.generic):
        return x.item()
    return x


def _fmt_float(x, digits=6):
    """
    Format float-like values in a readable way.
    """
    x = _to_python_scalar(x)

    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


# def _fmt_value(x, digits=6):
#     """
#     Generic formatter for scalar values.
#     """
#     x = _to_python_scalar(x)

#     if isinstance(x, float):
#         return f"{x:.{digits}f}"
#     return str(x)


def _fmt_prob_list(values, digits=6, indent="    "):
    """
    Format class probabilities line by line.
    """
    lines = []
    for cls_id, prob in enumerate(values):
        lines.append(f"{indent}class {cls_id}: {_fmt_float(prob, digits)}")
    return "\n".join(lines)


# def _fmt_numeric_list(values, digits=6, indent="    ", label="value"):
#     """
#     Format numeric list line by line.
#     """
#     lines = []
#     for i, v in enumerate(values):
#         lines.append(f"{indent}{label}[{i}]: {_fmt_float(v, digits)}")
#     return "\n".join(lines)


# def _fmt_params(params, indent="    ", digits=6):
#     """
#     Format parameter dictionary line by line.
#     """
#     lines = []
#     for key, value in params.items():
#         value = _to_python_scalar(value)
#         if isinstance(value, float):
#             value_str = f"{value:.{digits}f}"
#         else:
#             value_str = str(value)
#         lines.append(f"{indent}{key}: {value_str}")
#     return "\n".join(lines)


# def _fmt_vmd_detection(det_vmd, indent="    ", digits=6):
#     """
#     Format VMD detection output.
#     """
#     if det_vmd is None:
#         return f"{indent}Detection: None"

#     if isinstance(det_vmd, np.ndarray):
#         if det_vmd.size == 0:
#             return f"{indent}Detection: []"
#         values = det_vmd.tolist()
#     else:
#         try:
#             values = list(det_vmd)
#         except TypeError:
#             return f"{indent}Detection: {det_vmd}"

#     lines = [f"{indent}Detection:"]
#     lines.append(_fmt_numeric_list(values, digits=digits, indent=indent + "    ", label="det"))
#     return "\n".join(lines)


# def _extract_xyz_from_matrix(pos_matrix):
#     """
#     Try to extract x, y, z from a NumPy matrix / array / list-like structure.
#     Returns (x, y, z) or (None, None, None) if not possible.
#     """
#     try:
#         arr = np.asarray(pos_matrix, dtype=float).reshape(-1)
#         if arr.size >= 3:
#             return arr[0], arr[1], arr[2]
#     except Exception:
#         pass

#     return None, None, None


# def _fmt_position_tuple(pos_tuple, indent="    ", digits=6):
#     """
#     Format one TDOA_POS tuple.

#     Expected structure:
#     (
#         position_matrix,
#         M,
#         Mx,
#         My,
#         a_e,
#         b_e,
#         fi_e,
#         er
#     )
#     """
#     if not isinstance(pos_tuple, (tuple, list)) or len(pos_tuple) < 8:
#         return f"{indent}{pos_tuple}"

#     pos_matrix, M, Mx, My, a_e, b_e, fi_e, er = pos_tuple[:8]
#     x, y, z = _extract_xyz_from_matrix(pos_matrix)

#     lines = []
#     lines.append(f"{indent}Estimated position:")

#     if x is not None:
#         lines.append(f"{indent}    x: {_fmt_float(x, digits)}")
#         lines.append(f"{indent}    y: {_fmt_float(y, digits)}")
#         lines.append(f"{indent}    z: {_fmt_float(z, digits)}")
#     else:
#         lines.append(f"{indent}    raw: {pos_matrix}")

#     lines.append(f"{indent}Uncertainty / quality:")
#     lines.append(f"{indent}    M   : {_fmt_float(M, digits)}")
#     lines.append(f"{indent}    Mx  : {_fmt_float(Mx, digits)}")
#     lines.append(f"{indent}    My  : {_fmt_float(My, digits)}")
#     lines.append(f"{indent}    a_e : {_fmt_float(a_e, digits)}")
#     lines.append(f"{indent}    b_e : {_fmt_float(b_e, digits)}")
#     lines.append(f"{indent}    fi_e: {_fmt_float(fi_e, digits)}")
#     lines.append(f"{indent}Status code: {er}")

#     return "\n".join(lines)


def format_calculation_result(result: dict) -> str:
    """
    Convert a calculation result dictionary into a readable multi-line string.
    Suitable for QPlainTextEdit, QTextEdit, logs, or other text widgets.

    Works with both the previous and the updated result formats.
    """
    lines = []

    # ==============================================================
    # HEADER
    # ==============================================================
    lines.append("=== Calculation Result ===")

    job_id = result.get("job_id", "N/A")
    lines.append(f"Job ID: {job_id}")

    fs = result.get("fs")
    if isinstance(fs, list):
        lines.append("Sampling rates:")
        for i, v in enumerate(fs, start=1):
            lines.append(f"  Receiver {i}: {v} Hz")
    elif fs is not None:
        lines.append(f"Sampling rate: {fs} Hz")

    receivers = result.get("receivers", [])
    if receivers:
        lines.append("Receivers:")
        for i, rid in enumerate(receivers, start=1):
            lines.append(f"  {i}. {rid}")

    # ==============================================================
    # AKA1A
    # ==============================================================
    aka1a = result.get("AKA1A")
    if aka1a:
        lines.append("")
        lines.append("=== AKA1A ===")

        for i, item in enumerate(aka1a, start=1):
            lines.append(f"Receiver {i}:")
            pred_class_nb = item.get('pred_class', -1)
            pred_class_nb = OUTPUT_CLASSES[pred_class_nb] if pred_class_nb > -1 else 'N/A'
            lines.append(f"  Predicted class: {pred_class_nb}")
            #lines.append(f"  Predicted class: {item.get('pred_class', 'N/A')}")

            probs = item.get("class_prob", [])
            if probs:
                lines.append("  Class probabilities:")
                lines.append(_fmt_prob_list(probs, digits=6, indent="    "))

    # ==============================================================
    # Est_pos
    # ==============================================================
    est_pos = result.get("Est_pos")
    if est_pos:
        lines.append("")
        lines.append("=== Est_pos ===")
        for positions in est_pos:
            lines.append(", ".join(str(x) for x in positions))

    est_pos_error = result.get("Est_pos_error")
    if est_pos_error:
        lines.append("Error:")
        lines.append(str(est_pos_error))

    return "\n".join(lines)

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


class DockResultWidget(QDockWidget):
    """
    Dock widget for result display.
    """
    default_area = Qt.LeftDockWidgetArea

    def __init__(self, parent=None):
        super().__init__("Calculations", parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea)

        text_edit = QPlainTextEdit()
        text_edit.setReadOnly(True)
        # Optional: limit blocks to guard memory; this is an extra safety
        # The GUI handler also keeps a ring buffer (authoritative).
        text_edit.setMaximumBlockCount(10000)  # tweak via config later if desired

        self.setWidget(text_edit)
        self.text_edit = text_edit

    def add_result(self, res):
        text = format_calculation_result(res)
        self.text_edit.appendPlainText(text)