from PyQt5.QtWidgets import QDockWidget, QTreeView, QPlainTextEdit, QTextEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from html import escape
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

def _format_result_html(text: str) -> str:
    """
    Convert plain calculation-result text into simple HTML.

    Only the line:
        Predicted class: XXX

    is emphasized:
        - whole line is bigger;
        - class name XXX is bold.
    """
    html_lines = []

    for line in text.splitlines():
        stripped = line.strip()

        if stripped.startswith("Predicted class:"):
            _label, value = stripped.split(":", 1)
            class_name = value.strip()

            html_lines.append(
                '<span style="font-size: 14pt;">'
                f'Predicted class: <b>{escape(class_name)}</b>'
                '</span>'
            )
        else:
            html_lines.append(escape(line))

    return "<br>".join(html_lines)

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

    # fs = result.get("fs")
    # if isinstance(fs, list):
    #     lines.append("Sampling rates:")
    #     for i, v in enumerate(fs, start=1):
    #         lines.append(f"  Receiver {i}: {v} Hz")
    # elif fs is not None:
    #     lines.append(f"Sampling rate: {fs} Hz")

    # receivers = result.get("receivers", [])
    # if receivers:
    #     lines.append("Receivers:")
    #     for i, rid in enumerate(receivers, start=1):
    #         lines.append(f"  {i}. {rid}")

    # ==============================================================
    # AKA1A
    # ==============================================================
    aka1a_avg = result.get("AKA1A_avg")

    if aka1a_avg:
        lines.append("")
        lines.append("=== AKA1A ===")
        lines.append("Average 3-RPI prediction:")

        pred_class_nb = aka1a_avg.get("pred_class", -1)
        pred_class_name = (
            OUTPUT_CLASSES[pred_class_nb]
            if isinstance(pred_class_nb, int) and 0 <= pred_class_nb < len(OUTPUT_CLASSES)
            else "N/A"
        )

        lines.append(f" Predicted class: {pred_class_name}")

        object_score = aka1a_avg.get("object_score")
        salience_score = aka1a_avg.get("salience_score")
        threshold = aka1a_avg.get("threshold")

        if object_score is not None:
            lines.append(f" Object score: {_fmt_float(object_score, digits=3)}")

        if salience_score is not None:
            lines.append(f" Salience score: {_fmt_float(salience_score, digits=3)}")

        lines.append("")
            # probs = item.get("class_prob", [])
            # if probs:
            #     lines.append("  Class probabilities:")
            #     lines.append(_fmt_prob_list(probs, digits=6, indent="    "))

    # # ==============================================================
    # # Est_pos
    # # ==============================================================
    # lines.append("")
    # lines.append("=== Est_pos ===")
    # est_pos = result.get("Est_pos")
    # if est_pos:
    #     for positions in est_pos:
    #         lines.append(", ".join(str(x) for x in positions))
            
    # else:
    #     lines.append("Estimation position error")

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

        # QTextEdit is needed because QPlainTextEdit cannot display bold / larger text.
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)

        self.setWidget(text_edit)
        self.text_edit = text_edit

    def add_result(self, res):
        text = format_calculation_result(res)
        html = _format_result_html(text)

        self.text_edit.append(html)
        self.text_edit.append("<br>")