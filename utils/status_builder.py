# controller/status_builder.py
from PyQt5.QtGui import QStandardItem

def _add_value_row(parent, name, value):
    """
    Add a simple Name | Value row (both as strings, not editable).
    """
    n_item = QStandardItem(str(name))
    v_item = QStandardItem("" if value is None else str(value))
    n_item.setEditable(False)
    v_item.setEditable(False)
    parent.appendRow([n_item, v_item])


def populate_status_panel(model, receivers_cfg, targets_cfg):
    """
    Fill the QStandardItemModel with parameter values from YAML.
    No type metadata, just strings for display.
    """
    model.clear()
    model.setHorizontalHeaderLabels(["Name", "Value"])

    # Receivers
    if receivers_cfg:
        rx_root = QStandardItem("Receivers")
        rx_root_val = QStandardItem("")
        rx_root.setEditable(False)
        rx_root_val.setEditable(False)
        model.appendRow([rx_root, rx_root_val])

        for rx in receivers_cfg:
            rid = rx.get("id", "unknown")
            group = QStandardItem(f"Receiver {rid}")
            group_val = QStandardItem("")
            group.setEditable(False)
            group_val.setEditable(False)
            rx_root.appendRow([group, group_val])

            for params in [rx.get("param_monitor", {}),rx.get("param_control", {})]:
                for pname, meta in params.items():
                    _add_value_row(group, pname, meta.get("value"))

            # params = rx.get("param_control", {})
            # for pname, meta in params.items():
            #     _add_value_row(group, pname, meta.get("value"))
    # Targets
    if targets_cfg:
        tg_root = QStandardItem("Targets")
        tg_root_val = QStandardItem("")
        tg_root.setEditable(False)
        tg_root_val.setEditable(False)
        model.appendRow([tg_root, tg_root_val])

        for tg in targets_cfg:
            tid = tg.get("id", "unknown")
            group = QStandardItem(f"{tid}")
            group_val = QStandardItem("")
            group.setEditable(False)
            group_val.setEditable(False)
            tg_root.appendRow([group, group_val])

            params = tg.get("parameters", {})
            for pname, meta in params.items():
                _add_value_row(group, pname, meta.get("value"))

def populate_from_yaml(model, receivers_cfg, targets_cfg):
    model.removeRows(0, model.rowCount())

    # Receivers
    if receivers_cfg:
        rx_root = QStandardItem("Receivers")
        rx_root_val = QStandardItem("")
        rx_root.setEditable(False)
        rx_root_val.setEditable(False)
        model.appendRow([rx_root, rx_root_val])
        for rx in receivers_cfg:
            group = QStandardItem(f"{rx.get('id')}")
            group_val = QStandardItem("")
            group.setEditable(False)
            group_val.setEditable(False)
            rx_root.appendRow([group, group_val])
            # for pname, meta in (rx.get("parameters") or {}).items():
            #     add_param_row(group, pname, meta.get("value"), meta.get("editable", True))
            # group.setEditable(False)

    # Targets
    if targets_cfg:
        tg_root = QStandardItem("Targets")
        tg_root_val = QStandardItem("")
        model.appendRow([tg_root, tg_root_val])
        for tg in targets_cfg:
            group = QStandardItem(f"{tg.get('id')}")
            group_val = QStandardItem("")
            group.setEditable(False)
            group_val.setEditable(False)
            tg_root.appendRow([group, group_val])
            # if target also has parameters section
            for pname, meta in (tg.get("parameters") or {}).items():
                _add_value_row(group, pname, meta.get("value"))
            #group.setEditable(False)

    model.sort(0)
