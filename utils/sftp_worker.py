from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal
import paramiko
import os, posixpath, tempfile, time
from pathlib import Path
import inspect
import logging

logger = logging.getLogger(__name__)
logger.debug("low-level details you only want in the file")
logger.info("user-visible status you want in the dock")

class _SftpWorker(QObject):
    file_downloaded = pyqtSignal(str, str)
    monitor_downloaded = pyqtSignal(str)
    control_uploaded = pyqtSignal(str)
    status = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, sftp_cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = sftp_cfg
        self._timer: QTimer | None = None
        self._client: paramiko.SSHClient | None = None
        self._transport: paramiko.Transport | None = None
        self._sftp: paramiko.SFTPClient | None = None
        self._running = False
        self._is_connected = False
        self.path_gps = Path(self.cfg["remote_dirs"]["gps"])
        self._state = "DISCONNECTED"

        self.host = self.cfg.get("host")
        self.port = int(self.cfg.get("port", 22))
        self.user = self.cfg.get("user", "pi")
        self.pwd = self.cfg.get("password", "raspberry")
        print(f"selfpath_gps: {str(self.path_gps)}")
        

    # ---- thread entry/exit ----
    def start(self):
        if self._running:
            return
        logger.info(f"[{self.__class__.__name__}][{inspect.currentframe().f_code.co_name}][{self.host}]; Worker sftp started")
        self._running = True
        print(f"self.cfg:\n): {self.cfg}")
        self.status.emit(f"SFTP poller start host={self.cfg.get('host')}")
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
        self.status.emit("SFTP poller stopped")
        self.finished.emit()

    def _tick(self):
        logger.info(f"[{self.__class__.__name__}][{inspect.currentframe().f_code.co_name}][{self.host}]; In tick")
        if self._state == "CONNECTING":
            return
        self._check_connected()

        if self._state == "DISCONNECTED":
            logger.info(f"[{self.__class__.__name__}][{inspect.currentframe().f_code.co_name}][{self.host}]; Disconnected")
            self._connect()
            return

        logger.info(f"[{self.__class__.__name__}][{inspect.currentframe().f_code.co_name}][{self.host}]; Working...")

    def _connect(self):
        if self._state in ("CONNECTING","CONNECTING"):
            return
        
        last_error: Exception | None = None

        self._disconnect()
        self._state = "CONNECTING"
        logger.info(f"[{self.__class__.__name__}][{inspect.currentframe().f_code.co_name}][{self.host}]; Connecting...")


        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(hostname=self.host, port=self.port, username=self.user, password=self.pwd, timeout=10)
            transport = client.get_transport()
            if transport is not None and transport.is_active():
                logger.info(f"[{self.__class__.__name__}][{inspect.currentframe().f_code.co_name}][{self.host}]; SSH connection established.")
                print("trasport layer is active")
                self._client = client
                self._transport = transport
                self._transport.set_keepalive(30)
                self._sftp = client.open_sftp()
                self.status.emit("SFTP connected")
                self._is_connected = True
                self._state = "CONNECTED"
                logger.info(f"[{self.__class__.__name__}][{inspect.currentframe().f_code.co_name}][{self.host}]; Connected!")
        except Exception as e:
            print(e)
            #last_error = e      
            self._state = "DISCONNECTED"
            logger.info(f"[{self.__class__.__name__}][{inspect.currentframe().f_code.co_name}][{self.host}]; Connecting problem!!! \
                    \n{e}")


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

        self._is_connected = False
        self._state = "DISCONNECTED"
        logger.info(f"[{self.__class__.__name__}][{inspect.currentframe().f_code.co_name}][{self.host}]; Disconnected")

    def _check_connected(self):
            if self._client and self._transport and self._transport.is_active():
                self._is_connected = True
                self._state = "CONNECTED"
                logger.info(f"[{self.__class__.__name__}][{inspect.currentframe().f_code.co_name}][{self.host}]; Connected")
            else:
                self._is_connected = False
                self._state = "DISCONNECTED"
                logger.info(f"[{self.__class__.__name__}][{inspect.currentframe().f_code.co_name}][{self.host}]; Disconnected")