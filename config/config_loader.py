import yaml
from pathlib import Path

class Config:
    def __init__(self, path="config/config.yaml"):
        self.path = Path(path)
        print(f"Config path: {self.path.resolve()}")
        self._data = {}
        self._load()
        self.log_cfg: dict = {}

    def _load(self):
        with self.path.open("r") as f:
            self._data = yaml.safe_load(f)

        self.receivers = self._data.get("receivers", [])
        self.targets = self._data.get("targets", [])
        self.map = self._data.get("map",[])
        self.logging_cfg = (self._data.get("logging") or {})
        self.log_cfg = self.get_logging_config()


    def get_logging_config(self):
        lc = self.logging_cfg
        return {
            "file": lc.get("file", "logs/app.log"),
            "file_level": lc.get("file_level", "DEBUG"),
            "gui_level": lc.get("gui_level", "INFO"),
            "ring_capacity": int(lc.get("ring_capacity", 2000)),
            "rotate": bool(lc.get("rotate", True)),
            "max_bytes": int(lc.get("max_bytes", 5_000_000)),
            "backup_count": int(lc.get("backup_count", 5)),
        }

    def get_target_config(self, target_id):
        for t in self.targets:
            if t.get("id") == target_id:
                return t
        raise KeyError(f"Target config '{target_id}' not found")

    def get_receiver_config(self, receiver_id):
        for r in self.receivers:
            if r.get("id") == receiver_id:
                return r
        raise KeyError(f"Receiver config '{receiver_id}' not found")
    
    def get_layer(self):
        return self.map[0].get("layer",None)

    
    