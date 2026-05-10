# utils/server_comm_sftp.py
from __future__ import annotations
import os, posixpath, tempfile, time, traceback
from pathlib import Path
from typing import Dict, Tuple, Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
import paramiko  # pip install paramiko
import logging
log = logging.getLogger(__name__)


class ServerCommSFTP(QObject):
    """
    Per-receiver SFTP poller:

      - Polls streaming (wav) & gps (txt) dirs for new files; downloads when stable
      - Periodically downloads config/monitor.txt (read-only; never modify)
      - Provides methods to upload config/control.txt (write-once on demand)

    Signals:
      - file_downloaded(remote_path, local_path)
      - monitor_downloaded(local_path)
      - control_uploaded(remote_path)
      - status(text), error(text), finished()
    """
    file_downloaded = pyqtSignal(str, str)
    monitor_downloaded = pyqtSignal(str)
    control_uploaded = pyqtSignal(str)
    status = pyqtSignal(str)
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, sftp_cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = sftp_cfg
        self._timer: Optional[QTimer] = None
        self._transport: Optional[paramiko.Transport] = None
        self._client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None
        self._running = False

    # ---------- lifecycle ----------
    def start(self):
        if self._running:
            return
        self._running = True
        self.status.emit(f"SFTP poller starting for {self.cfg.get('host')}")
        self._timer = QTimer(self)
        self._timer.setInterval(int(self.cfg.get("poll_interval_ms", 3000)))
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def stop(self):
        if not self._running:
            self.finished.emit()
            return
        self._running = False
        if self._timer:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        self._disconnect()
        self.status.emit("SFTP poller stopped.")
        self.finished.emit()

    def _connect(self):
        self.close()

    # ---------- API to upload control.txt (write-once, on demand) ----------
    

    # ---------- polling core ----------
    def _tick(self):
        if not self._running or self._busy:
            return
        self._busy = True
        try:
            self._ensure_connected()

            # 1) streaming (wav)
            self._scan_and_download("streaming", self.cfg["patterns"]["streaming"])
            # 2) gps (txt)
            self._scan_and_download("gps", self.cfg["patterns"]["gps"])
            # 3) monitor.txt (read-only)
            now = time.time()
            if (now - self._last_monitor_check) >= int(self.cfg.get("monitor_poll_s", 10)):
                self._fetch_monitor()
                self._last_monitor_check = now

        except Exception as e:
            self.error.emit(str(e))
            log.exception("SFTP tick error: %s", e)
            self._disconnect()
        finally:
            self._busy = False

        # ---------- SFTP plumbing ----------


        host = self.cfg.get("host")
        port = int(self.cfg.get("port", 22))
        user = self.cfg.get("user", "pi")
        password = self.cfg.get("password", "raspberry")

        client = paramiko.SSHClient()
        policy = (self.cfg.get("host_key_policy") or "auto_add").lower()
        if policy == "reject":
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        elif policy == "system":
            client.load_system_host_keys()
        else:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        client.connect(hostname=host, port=port, username=user, password=password, timeout=30)
        self._client = client
        self._transport = client.get_transport()
        keep = int(self.cfg.get("keepalive_s", 30))
        if keep > 0 and self._transport:
            self._transport.set_keepalive(keep)

        self._sftp = client.open_sftp()
        self.status.emit("SFTP connected")

    def _disconnect(self):
        try:
            if self._sftp:
                self._sftp.close()
        except Exception:
            pass
        self._sftp = None
        try:
            if self._transport:
                self._transport.close()
        except Exception:
            pass
        self._transport = None
        try:
            if self._client:
                self._client.close()
        except Exception:
            pass
        self._client = None

    def _safe_listdir_attr(self, remote_dir: str):
        try:
            return self._sftp.listdir_attr(remote_dir)
        except FileNotFoundError:
            # if device doesn't have the dir yet, create it to be friendly
            self._sftp.mkdir(remote_dir)
            return []
        except Exception:
            raise


