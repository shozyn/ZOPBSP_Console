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
        self._busy = False
        self._last_monitor_check = 0
        self._pending_control_text: str | None = None
        self._pending_control_file: str | None = None
        # stability cache: (dir_key, name) -> (size, mtime, stable_count)
        self._seen: dict[tuple[str, str], tuple[int, int, int]] = {}

        for k in ("streaming", "gps", "config"):
            Path(self.cfg["local_dirs"][k]).mkdir(parents=True, exist_ok=True)

    # ---- thread entry/exit ----
    def start(self):
        if self._running:
            return
        logger.info(f"[{self.__class__.__name__}] In function: {inspect.currentframe().f_code.co_name}; Worker sftp started")
        self._running = True
        print(f"self.cfg:\n): {self.cfg}")
        self.status.emit(f"SFTP poller start host={self.cfg.get('host')}")
        self._timer = QTimer(self)
        self._timer.setInterval(int(self.cfg.get("poll_interval_ms", 3000)))
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        self._disconnect()
        self.status.emit("SFTP poller stopped")
        self.finished.emit()

    # ---- external requests (queued from controller) ----
    def request_control_text(self, text: str):
        self._pending_control_text = text

    def request_control_file(self, local_path: str):
        self._pending_control_file = local_path

    # ---- main tick ----
    def _tick(self):
        if not self._running or self._busy:
            return
        self._busy = True

        logger.info(f"[{self.__class__.__name__}] In function: {inspect.currentframe().f_code.co_name}; In tick")

        try:
            self._ensure_connected()

            # 0) handle pending control.txt upload (write-once)
            if self._pending_control_text is not None:
                self._upload_control_text(self._pending_control_text)
                self._pending_control_text = None
            if self._pending_control_file is not None:
                self._upload_control_file(self._pending_control_file)
                self._pending_control_file = None

            # 1) streaming (wav)
            self._scan_dir("streaming", self.cfg["patterns"]["streaming"])
            # 2) gps (txt)
            self._scan_dir("gps", self.cfg["patterns"]["gps"])
            # 3) monitor.txt (read-only every N seconds)
            now = time.time()
            if (now - self._last_monitor_check) >= int(self.cfg.get("monitor_poll_s", 10)):
                self._fetch_monitor()
                self._last_monitor_check = now

        except Exception as e:
            self.error.emit(str(e))
            self._disconnect()
        finally:
            self._busy = False

    # ---- SFTP helpers ----
    def _ensure_connected(self):
        if self._sftp and self._transport and self._transport.is_active():
            return

        self._disconnect()
        host = self.cfg.get("host")
        port = int(self.cfg.get("port", 22))
        user = self.cfg.get("user", "pi")
        pwd = self.cfg.get("password", "raspberry")

        client = paramiko.SSHClient()
        policy = (self.cfg.get("host_key_policy") or "auto_add").lower()
        if policy == "reject":
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        elif policy == "system":
            client.load_system_host_keys()
        else:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        client.connect(hostname=host, port=port, username=user, password=pwd, timeout=30)

        logger.info(f"[{self.__class__.__name__}] In function: {inspect.currentframe().f_code.co_name}; connecting...")

        self._client = client
        self._transport = client.get_transport()
        keep = int(self.cfg.get("keepalive_s", 30))
        if keep > 0 and self._transport:
            self._transport.set_keepalive(keep)
        self._sftp = client.open_sftp()
        self.status.emit("SFTP connected")

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

    # ---- directory scan/downloads ----
    def _scan_dir(self, key: str, glob_pat: str):
        rdir = self.cfg["remote_dirs"][key]
        ldir = Path(self.cfg["local_dirs"][key])
        try:
            entries = self._sftp.listdir_attr(rdir)
        except FileNotFoundError:
            self._sftp.mkdir(rdir)
            entries = []

        for a in entries:
            name = a.filename
            if glob_pat and not Path(name).match(glob_pat):
                continue
            if self._is_dir(a.st_mode):  # skip subdirs
                continue

            size, mtime = int(a.st_size or 0), int(a.st_mtime or 0)
            k = (key, name)
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
                    if (self.cfg.get("delete_after_download", {}) or {}).get(key, False):
                        self._sftp.remove(remote_path)
                    self._seen.pop(k, None)
                except Exception as e:
                    self.error.emit(f"Download failed {remote_path}: {e}")

    def _fetch_monitor(self):
        rdir = self.cfg["remote_dirs"]["config"]
        mname = self.cfg["patterns"]["monitor_file"]
        rpath = posixpath.join(rdir, mname)
        lpath = Path(self.cfg["local_dirs"]["config"]) / mname
        try:
            attr = self._sftp.stat(rpath)
        except FileNotFoundError:
            return
        r_mtime = int(getattr(attr, "st_mtime", 0) or 0)
        if not lpath.exists() or int(lpath.stat().st_mtime) < r_mtime:
            self._download_atomic(rpath, lpath, expected_size=int(getattr(attr, "st_size", 0) or 0))
            try:
                os.utime(lpath, (time.time(), r_mtime))
            except Exception:
                pass
            self.monitor_downloaded.emit(str(lpath))
            self.status.emit(f"monitor.txt updated -> {lpath}")

    # ---- uploads (control.txt) ----
    def _upload_control_text(self, text: str):
        rdir = self.cfg["remote_dirs"]["config"]
        ctrl = self.cfg["patterns"]["control_file"]
        remote = posixpath.join(rdir, ctrl)
        tmp = remote + ".tmp"
        with self._sftp.file(tmp, "w") as f:
            f.write(text)
            f.flush()
        self._sftp.rename(tmp, remote)
        self.control_uploaded.emit(remote)
        self.status.emit(f"Uploaded control.txt -> {remote}")

    def _upload_control_file(self, local_path: str):
        rdir = self.cfg["remote_dirs"]["config"]
        ctrl = self.cfg["patterns"]["control_file"]
        remote = posixpath.join(rdir, ctrl)
        tmp = remote + ".tmp"
        self._sftp.put(local_path, tmp)
        self._sftp.rename(tmp, remote)
        self.control_uploaded.emit(remote)
        self.status.emit(f"Uploaded {local_path} -> {remote}")

    # ---- IO helpers ----
    @staticmethod
    def _is_dir(st_mode: int) -> bool:
        import stat as _st
        return _st.S_ISDIR(st_mode or 0)

    def _download_atomic(self, remote_path: str, local_final: Path, expected_size: int = 0):
        local_final.parent.mkdir(parents=True, exist_ok=True)
        fd, tmpname = tempfile.mkstemp(prefix=f".{local_final.name}.part-", dir=str(local_final.parent))
        os.close(fd)
        tmp = Path(tmpname)
        try:
            self._sftp.get(remote_path, str(tmp))
            if expected_size and tmp.stat().st_size != expected_size:
                raise IOError(f"Size mismatch: got={tmp.stat().st_size} expected={expected_size}")
            tmp.replace(local_final)  # atomic on same FS
            self.status.emit(f"Downloaded {remote_path} -> {local_final}")
        except Exception as e:
            try:
                if tmp.exists() and not local_final.exists():
                    tmp.unlink()
            finally:
                raise e