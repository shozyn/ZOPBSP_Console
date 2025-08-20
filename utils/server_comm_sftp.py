# utils/server_comm_sftp.py
from __future__ import annotations
import os, posixpath, tempfile, time, traceback
from pathlib import Path
from typing import Dict, Tuple, Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
import paramiko  # pip install paramiko
import logging
log = logging.getLogger(__name__)

def _stat_is_dir(st_mode: int) -> bool:
    import stat as _stat
    return _stat.S_ISDIR(st_mode or 0)

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
        self._busy = False
        self._last_monitor_check = 0
        # seen maps: (dir_key, filename) -> (size, mtime, stable_count)
        self._seen: Dict[Tuple[str, str], Tuple[int, int, int]] = {}
        # local dirs must exist
        for key in ("streaming", "gps", "config"):
            Path(self.cfg["local_dirs"][key]).mkdir(parents=True, exist_ok=True)

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

    # ---------- API to upload control.txt (write-once, on demand) ----------
    def send_control_text(self, text: str) -> None:
        """Upload 'control.txt' content to remote config dir (overwrite)."""
        try:
            self._ensure_connected()
            rdir = self.cfg["remote_dirs"]["config"]
            ctrl_name = self.cfg["patterns"]["control_file"]
            remote_path = posixpath.join(rdir, ctrl_name)
            # write via sftp.open for atomic replace: .tmp then rename
            tmp_remote = remote_path + ".tmp"
            with self._sftp.file(tmp_remote, "w") as f:
                f.write(text)
                f.flush()
            # remote atomic-ish: rename tmp -> final
            self._sftp.rename(tmp_remote, remote_path)
            self.control_uploaded.emit(remote_path)
            self.status.emit(f"Uploaded control.txt -> {remote_path}")
        except Exception as e:
            self.error.emit(f"control.txt upload failed: {e}")
            log.exception("control.txt upload failed: %s", e)

    def send_control_file(self, local_path: str | Path) -> None:
        """Upload a local file as 'control.txt' to remote config dir (overwrite)."""
        try:
            self._ensure_connected()
            rdir = self.cfg["remote_dirs"]["config"]
            ctrl_name = self.cfg["patterns"]["control_file"]
            remote_path = posixpath.join(rdir, ctrl_name)
            tmp_remote = remote_path + ".tmp"
            self._sftp.put(str(local_path), tmp_remote)
            self._sftp.rename(tmp_remote, remote_path)
            self.control_uploaded.emit(remote_path)
            self.status.emit(f"Uploaded {local_path} -> {remote_path}")
        except Exception as e:
            self.error.emit(f"control.txt upload failed: {e}")
            log.exception("control.txt upload failed: %s", e)

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

    def _scan_and_download(self, dir_key: str, glob_pattern: str):
        rdir = self.cfg["remote_dirs"][dir_key]
        ldir = Path(self.cfg["local_dirs"][dir_key])
        entries = self._safe_listdir_attr(rdir)
        for attr in entries:
            name = attr.filename
            if glob_pattern and not Path(name).match(glob_pattern):
                continue
            if _stat_is_dir(attr.st_mode):
                continue

            size, mtime = int(attr.st_size or 0), int(attr.st_mtime or 0)
            k = (dir_key, name)
            prev = self._seen.get(k)
            if not prev:
                self._seen[k] = (size, mtime, 1)
                continue
            psize, pmtime, stable = prev
            stable = stable + 1 if (psize == size and pmtime == mtime) else 1
            self._seen[k] = (size, mtime, stable)

            if stable >= int(self.cfg.get("stability_checks", 2)):
                remote_path = posixpath.join(rdir, name)
                local_final = ldir / name
                try:
                    self._download_atomic(remote_path, local_final, expected_size=size)
                    self.file_downloaded.emit(remote_path, str(local_final))
                    if self.cfg.get("delete_after_download", {}).get(dir_key, False):
                        self._sftp.remove(remote_path)
                    self._seen.pop(k, None)  # ready for a future new file with same name
                except Exception as e:
                    self.error.emit(f"Download failed {remote_path}: {e}")
                    log.exception("Download failed for %s: %s", remote_path, e)

    def _fetch_monitor(self):
        rdir = self.cfg["remote_dirs"]["config"]
        mname = self.cfg["patterns"]["monitor_file"]
        rpath = posixpath.join(rdir, mname)
        lpath = Path(self.cfg["local_dirs"]["config"]) / mname
        try:
            rattr = self._sftp.stat(rpath)
            r_mtime = int(getattr(rattr, "st_mtime", 0) or 0)
            if not lpath.exists() or int(lpath.stat().st_mtime) < r_mtime:
                self._download_atomic(rpath, lpath, expected_size=int(getattr(rattr, "st_size", 0) or 0))
                # sync mtime locally to match remote (optional)
                try:
                    os.utime(lpath, (time.time(), r_mtime))
                except Exception:
                    pass
                self.monitor_downloaded.emit(str(lpath))
                self.status.emit(f"monitor.txt updated -> {lpath}")
        except FileNotFoundError:
            # monitor.txt not present yet—ignore
            return

    # ---------- SFTP plumbing ----------
    def _ensure_connected(self):
        if self._sftp and self._transport and self._transport.is_active():
            return
        self._disconnect()

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

    # ---------- IO helpers ----------
    def _download_atomic(self, remote_path, local_final: Path, expected_size: int = 0):
        """
        Local atomic download: write to temporary file in the same directory, then replace.
        On handled errors, the temp is removed; only a hard crash could leave a .part file.
        """
        local_final.parent.mkdir(parents=True, exist_ok=True)
        fd, tmpname = tempfile.mkstemp(prefix=f".{local_final.name}.part-", dir=str(local_final.parent))
        os.close(fd)
        tmp = Path(tmpname)
        try:
            self._sftp.get(remote_path, str(tmp))
            if expected_size and tmp.stat().st_size != expected_size:
                raise IOError(f"Size mismatch: got={tmp.stat().st_size}, expected={expected_size}")
            tmp.replace(local_final)  # atomic on same filesystem
            self.status.emit(f"Downloaded {remote_path} -> {local_final}")
            log.info("Downloaded %s -> %s", remote_path, local_final)
        except Exception as e:
            try:
                if tmp.exists() and not local_final.exists():
                    tmp.unlink()
            finally:
                raise e
