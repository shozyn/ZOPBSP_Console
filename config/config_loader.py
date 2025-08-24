import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional

class ConfigError(Exception): pass
class DataError(Exception): pass

class Config:
    def __init__(self, path="config/config.yaml"):
        self.path = Path(path)
        #print(f"Config path: {self.path.resolve()}")
        self._data = {}
        self.log_cfg: dict = {}
        
        self._data: Dict[str, Any] = {}
        self.receivers: List[Dict[str, Any]] = []
        self.targets: List[Dict[str, Any]] = []
        self.map: List[Dict[str, Any]] = []
        self.logging_cfg: Dict[str, Any] = {}
        
        self._load()
        

    def _load(self):

        try:
            with self.path.open("r") as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                raise ConfigError("YAML file cannot be read.")
            self._data = data
            self.receivers = self._data.get("receivers", [])
            self.targets = self._data.get("targets", [])
            self.map = self._data.get("map",[])
            self.logging_cfg = (self._data.get("logging") or {})
            self.log_cfg = self.get_logging_config() 
                      
            if not all([self.receivers,self.targets,self.map]):
                raise DataError("Structure of YAML file cannot be read") 
                              
        except (FileNotFoundError, OSError, yaml.YAMLError) as e:
            raise ConfigError(f"Failed to load YAML '{self.path.resolve()}': {e}") from e


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

    
    def get_layer(self) -> Optional[str]:
        return self.map[0].get("layer",None)

    
    