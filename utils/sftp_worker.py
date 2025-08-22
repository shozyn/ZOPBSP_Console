from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal
import paramiko
import os, posixpath, tempfile, time
from pathlib import Path
#from pathlib import PurePosixPath
import inspect
import logging

logger = logging.getLogger(__name__)
logger.debug("low-level details you only want in the file")
#logger.info("user-visible status you want in the dock")
#logger.info(f"[{self.__class__.__name__}][{inspect.currentframe().f_code.co_name}][{self.host}]; Worker sftp started")

class _SftpWorker(QObject):
    file_downloaded = pyqtSignal(str, str)
    status_changed = pyqtSignal(str)
    monitor_read =  pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, sftp_cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = sftp_cfg
        self._timer: QTimer | None = None
        self._client: paramiko.SSHClient | None = None
        self._transport: paramiko.Transport | None = None
        self._sftp: paramiko.SFTPClient | None = None
        self._running = False
        self.path_gps = Path(self.cfg["remote_dirs"]["gps"])
        self._state = "DISCONNECTED"
        self.host = self.cfg.get("host","192.168.0.210")
        self.port = int(self.cfg.get("port", 22))
        self.user = self.cfg.get("user", "pi")
        self.pwd = self.cfg.get("password", "raspberry")
        self.max_retries = self.cfg.get("remote_dirs",{}).get("max_retries",1)
        monitor_folder = self.cfg.get("remote_dirs",{}).get("config")
        monitor_file = self.cfg.get("remote_dirs",{}).get("monitor_file")
        self.monitor_path = (Path(monitor_folder) / monitor_file).as_posix()
        self.status_changed.emit(self._state)
        self.monitor_read.connect(lambda a: print(a))

    def start(self):
        if self._running:
            return
        logger.debug(f"[{inspect.currentframe().f_code.co_name}][{self.host}]; Worker sftp started")
        self._running = True
        self._timer = QTimer(self)
        self._timer.setInterval(int(self.cfg.get("poll_interval_ms", 2000)))
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._connect()

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        self._disconnect()
        self.finished.emit()

    def _tick(self):
        logger.debug(f"[{inspect.currentframe().f_code.co_name}][{self.host}]; In tick")
        if self._state == "CONNECTING":
            return
        self._check_connected()

        if self._state == "DISCONNECTED":
            logger.debug(f"[{inspect.currentframe().f_code.co_name}][{self.host}]; Disconnected")
            self._connect()
            return

        logger.debug(f"[{inspect.currentframe().f_code.co_name}][{self.host}]; Working...")
        
        if self._read_monitor() is not None:
            self.monitor_read.emit(self._read_monitor())


    def _connect(self):
        if self._state in ("CONNECTING","CONNECTING"):
            return

        self._disconnect()
        self._state = "CONNECTING"
        self.status_changed.emit(self._state)
        logger.debug(f"[{inspect.currentframe().f_code.co_name}][{self.host}]; Connecting...")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(hostname=self.host, port=self.port, username=self.user, password=self.pwd, timeout=10)
            transport = client.get_transport()
            if transport is not None and transport.is_active():
                logger.debug(f"[{inspect.currentframe().f_code.co_name}][{self.host}]; SSH connection established.")
                print("trasport layer is active")
                self._client = client
                self._transport = transport
                self._transport.set_keepalive(30)
                self._sftp = client.open_sftp()
                self._is_connected = True
                self._state = "CONNECTED"
                self.status_changed.emit(self._state)
                logger.debug(f"[{inspect.currentframe().f_code.co_name}][{self.host}]; Connected!")
        except Exception as e:
            print(e) 
            self._state = "DISCONNECTED"
            self.status_changed.emit(self._state)
            logger.info(f"[{inspect.currentframe().f_code.co_name}][{self.host}]; Connecting problem!!!\n{e}")

        
    def _disconnect(self):
        try:
            if self._sftp: self._sftp.close()
        except Exception:
            pass
        self._sftp = None
        try:
            if self._transport: self._transport.close()
        except Exception:
            pass
        self._transport = None
        try:
            if self._client: self._client.close()
        except Exception:
            pass
        self._client = None
        self._state = "DISCONNECTED"
        self.status_changed.emit(self._state)
        logger.info(f"[{inspect.currentframe().f_code.co_name}][{self.host}]; Disconnected")

    def _check_connected(self):
            if self._client and self._transport and self._transport.is_active():
                self._is_connected = True
                self._state = "CONNECTED"
                self.status_changed.emit(self._state)
                logger.info(f"[{inspect.currentframe().f_code.co_name}][{self.host}]; Connected")
            else:
                self._is_connected = False
                self._state = "DISCONNECTED"
                self.status_changed.emit(self._state)
                logger.info(f"[{inspect.currentframe().f_code.co_name}][{self.host}]; Disconnected")

    def _read_monitor(self) -> str | None:
        try:
            self._sftp.stat(self.monitor_path)
            print("Path exists")
        except Exception as e:
            print(f"Monitor file not found!!!\n{e}")
            return None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                with self._sftp.open(self.monitor_path, mode="rb", bufsize=32768) as f: 
                    try:
                        f.prefetch()
                    except Exception:
                        pass
                    try:
                        size = self._sftp.stat(self.monitor_path).st_size
                        data = f.read(size)  
                    except Exception:
                        data = f.read()      
                return data.decode("utf-8", errors="replace")
        
            except Exception as e:
                logger.warning(f"[{self.__class__.__name__}] Read attempt {attempt}/{self.max_retries} failed for {self.monitor_path}:\n{e}")
                return None
            

        

        
