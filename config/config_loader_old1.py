# config_loader.py
import sys
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


class Config:
    """
    Load parameters from config.yaml
    """
    def __init__(self, path: str = "config/config.yaml", app_root: Optional[Path] = None):
        if app_root is None:
            main_file = Path(sys.modules["__main__"].__file__).resolve()
            
            app_root = main_file.parent
        self.app_root = Path(app_root)
        self.path = (self.app_root / path).resolve()

        print(f"[Config] Using config: {self.path}")
        self._data: Dict[str, Any] = {}
        self.receivers: List[Dict[str, Any]] = []
        self.targets: List[Dict[str, Any]] = []
        self.map: List[Dict[str, Any]] = []
        self.logging_cfg: Dict[str, Any] = {}

        self._load()

    # ------------------------ internal helpers ------------------------

    @staticmethod
    def _val(x: Any) -> Any:
        """
        Unwraps objects like {'value': ...} -> value; otherwise returns x.
        Useful for parameters and sftp fields that follow the {value: ...} shape.
        """
        if isinstance(x, dict) and "value" in x and len(x) in (1, 2):  # allow {'value':..., 'editable':...}
            return x.get("value")
        return x

    def _resolve_path(self, p: Optional[str]) -> Optional[str]:
        if not p:
            return p
        return str((self.app_root / str(p)).resolve())

    def _resolve_dir_dict(self, d: Optional[Dict[str, str]]) -> Dict[str, str]:
        d = d or {}
        out = {}
        for k, v in d.items():
            out[k] = self._resolve_path(self._val(v))
        return out

    # ------------------------ load & sections -------------------------

    def _load(self) -> None:
        with self.path.open("r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f) or {}

        self.receivers = self._data.get("receivers", []) or []
        self.targets = self._data.get("targets", []) or []
        self.map = self._data.get("map", []) or []
        self.logging_cfg = (self._data.get("logging") or {})

    # ------------------------ public API ------------------------------

    def get_logging_config(self) -> Dict[str, Any]:
        lc = self.logging_cfg or {}
        return {
            "file": self._resolve_path(lc.get("file", "logs/app.log")),
            "file_level": lc.get("file_level", "DEBUG"),
            "gui_level": lc.get("gui_level", "INFO"),
            "ring_capacity": int(self._val(lc.get("ring_capacity", 2000))),
            "rotate": bool(self._val(lc.get("rotate", True))),
            "max_bytes": int(self._val(lc.get("max_bytes", 5_000_000))),
            "backup_count": int(self._val(lc.get("backup_count", 5))),
        }

    def get_receiver_ids(self) -> List[str]:
        return [r.get("id") for r in self.receivers if r.get("id")]

    def get_receiver_config(self, receiver_id: str) -> Dict[str, Any]:
        for r in self.receivers:
            if r.get("id") == receiver_id:
                return r
        raise KeyError(f"Receiver config '{receiver_id}' not found")

    def get_receiver_parameters(self, receiver_id: str) -> Dict[str, Any]:
        """
        Returns the 'parameters' block exactly as in YAML (for dialogs/UI).
        """
        rx = self.get_receiver_config(receiver_id)
        return (rx.get("parameters") or {}).copy()

    def get_receiver_sftp_config(self, receiver_id: str) -> Dict[str, Any]:
        """
        Returns a flattened SFTP config dict ready for the SFTP worker:
          host, port, user, password, host_key_policy, keepalive_s,
          poll_interval_ms, stability_checks, monitor_poll_s,
          remote_dirs, local_dirs (absolute), patterns, delete_after_download
        Reads host/user/pw/port from 'sftp:' (sftp_IP/sftp_user/...),
        unwrapping {value: ...} as needed.
        """
        rx = self.get_receiver_config(receiver_id)
        sftp = (rx.get("sftp") or {}).copy()

        host = self._val(sftp.get("sftp_IP"))
        user = self._val(sftp.get("sftp_user", "pi"))
        password = self._val(sftp.get("sftp_password", "raspberry"))
        port = int(self._val(sftp.get("sftp_port", 22)))

        cfg = {
            "host": host,
            "user": user,
            "password": password,
            "port": port,
            "host_key_policy": self._val(sftp.get("host_key_policy", "auto_add")),
            "keepalive_s": int(self._val(sftp.get("keepalive_s", 30))),
            "poll_interval_ms": int(self._val(sftp.get("poll_interval_ms", 3000))),
            "stability_checks": int(self._val(sftp.get("stability_checks", 2))),
            "monitor_poll_s": int(self._val(sftp.get("monitor_poll_s", 10))),
            "remote_dirs": {
                **(sftp.get("remote_dirs") or {})
            },
            "local_dirs": self._resolve_dir_dict(sftp.get("local_dirs")),
            "patterns": {
                **(sftp.get("patterns") or {})
            },
            "delete_after_download": {
                **(sftp.get("delete_after_download") or {})
            },
        }
        # sanity
        if not cfg["host"]:
            raise ValueError(f"SFTP host (sftp_IP) is missing for receiver '{receiver_id}'")
        return cfg

    # def get_map_layers(self):
    #     """
    #     Normalize map entries into:
    #     [{'path': <abs>, 'crs': 'EPSG:4326'?, ...}, ...]
    #     Accepts any of:
    #     - { layer: { path: "...", crs: "..." } }
    #     - { path: "...", crs: "..." }
    #     - "path/to/file"
    #     """
    #     out = []
    #     for entry in (self.map or []):
    #         layer_obj = None

    #         if isinstance(entry, dict) and "layer" in entry:
    #             # legacy nested form
    #             layer_obj = entry.get("layer")
    #         else:
    #             # flat dict or string
    #             layer_obj = entry

    #         # Now parse layer_obj
    #         if isinstance(layer_obj, str):
    #             # just a path string
    #             path = self._resolve_path(self._val(layer_obj))
    #             if path:
    #                 out.append({"path": path})
    #             continue

    #         if isinstance(layer_obj, dict):
    #             raw_path = layer_obj.get("path") or layer_obj.get("file") or layer_obj.get("source")
    #             path = self._resolve_path(self._val(raw_path))
    #             if not path:
    #                 continue
    #             item = {"path": path}
    #             crs = self._val(layer_obj.get("crs"))
    #             if crs:
    #                 item["crs"] = crs
    #             # copy through any other keys you might add later
    #             for k, v in layer_obj.items():
    #                 if k in ("path", "crs"):
    #                     continue
    #                 item[k] = self._val(v)
    #             out.append(item)
    #             continue

    #         # Unknown shape -> skip silently or log if you prefer
    #         # logging.warning("Unknown map entry shape: %r", entry)

    #     return out

    def get_layer(self):
        """Keep backward-compat single-layer accessor."""
        return self.map[0].get("layer",None)

        # layers = self.get_map_layers()
        # return layers[0] if layers else None
