import yaml
from pathlib import Path

class ConfigError(Exception): pass

class Config:
    def __init__(self, path="config/config.yaml"):
        self.path = Path(path)
        print(f"Config path: {self.path.resolve()}")
        self._data = {}
        self.log_cfg: dict = {}
        self._load()
        

    def _load(self):

        try:
            with self.path.open("r") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ConfigError("Config root must be a mapping.")
            self._data = data
        except (FileNotFoundError, OSError, yaml.YAMLError) as e:
            raise ConfigError(f"Failed to load YAML '{self.path.resolve()}': {e}") from e

        self.receivers = self._data.get("receivers", [])
        self.targets = self._data.get("targets", [])
        self.map = self._data.get("map",[])
        self.logging_cfg = (self._data.get("logging") or {})
        print(f"self.logging_cfg:\n{self.logging_cfg}")
        self.log_cfg = self.get_logging_config()
        print(f"self.log_cfg:\n{self.log_cfg}")


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

    
    