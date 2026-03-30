import string
from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
#from PyQt5.QtWidgets import QMessageBox
import paramiko
from pathlib import Path 
import posixpath
import logging
from typing import Optional
from threading import Lock
import time

logger = logging.getLogger(__name__)

def _remote_path(path: str | None) -> str: #!!!
    """
    Normalize a remote SFTP path to forward-slash form.
    Works for both:
      - Windows-style paths: C:\\Pi\\RPI2\\bsp\\streaming
      - POSIX-style paths   : /home/pi/bsp/streaming
    """
    return (path or "").replace("\\", "/")

class RemoteFolderWatcher:
    def __init__(
        self,
        sftp,
        host: str,
        remote_dir: str,
        local_dir: str,
        archive_remote_dir: str | None = None,
    ):
        self.sftp = sftp
        self.host = host
        self.remote_dir = _remote_path(remote_dir)
        self.archive_remote_dir = _remote_path(archive_remote_dir) if archive_remote_dir else ""
        self.local_dir = Path(local_dir)
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.old_file_names = set()

        try:
            initial_files = [attr.filename for attr in self.sftp.listdir_attr(self.remote_dir)]
            self.old_file_names.update(initial_files)
            logger.info(
                f"[{self.__class__.__name__}][{self.host}] "
                f"Initially stored files in {self.remote_dir}: {len(initial_files)} files"
            )
        except Exception as e:
            logger.error(
                f"[{self.__class__.__name__}][{self.host}] "
                f"Error reading initially stored files in {self.remote_dir}: {e}"
            )

    def _ensure_remote_dir(self, remote_dir: str) -> None:
        """
        Create the remote directory recursively if it does not exist.
        Handles both:
          - C:/Pi/RPI2/bsp_history/streaming
          - /home/pi/bsp_history/streaming
        """
        remote_dir = _remote_path(remote_dir).rstrip("/")
        if not remote_dir:
            return

        is_abs_posix = remote_dir.startswith("/")
        parts = [p for p in remote_dir.split("/") if p]
        if not parts:
            return

        if is_abs_posix:
            current = ""
        else:
            current = parts.pop(0)  # e.g. 'C:' or first relative segment

        for part in parts:
            if current in ("", "/"):
                current = f"/{part}" if is_abs_posix else part
            else:
                current = posixpath.join(current, part)

            try:
                self.sftp.stat(current)
            except IOError:
                self.sftp.mkdir(current)

    def _move_remote_to_archive(self, remote_path: str, fname: str) -> bool:
        """
        Move the remote file from the active folder to the archive folder.
        Returns True if the move succeeded, False otherwise.
        """
        if not self.archive_remote_dir:
            return True

        try:
            self._ensure_remote_dir(self.archive_remote_dir)
            archive_path = posixpath.join(self.archive_remote_dir, fname)

            try:
                self.sftp.posix_rename(remote_path, archive_path)
            except Exception:
                self.sftp.rename(remote_path, archive_path)

            logger.info(
                f"[{self.__class__.__name__}][{self.host}] Archived remote file:\n"
                f"{remote_path} -> {archive_path}"
            )
            return True

        except Exception as e:
            logger.warning(
                f"[{self.__class__.__name__}][{self.host}] "
                f"Downloaded locally, but could not archive remote file {remote_path}:\n{e}"
            )
            return False

    def check_and_download(self, local_dir):
        new_files_set = set()

        try:
            for attr in self.sftp.listdir_attr(self.remote_dir):
                fname = attr.filename
                if "tmp" in fname or fname in self.old_file_names:
                    continue

                remote_path = posixpath.join(self.remote_dir, fname)
                local_path = Path(local_dir) / fname
                local_path.parent.mkdir(parents=True, exist_ok=True)

                retries = 3
                for attempt in range(1, retries + 1):
                    try:
                        self.sftp.get(remote_path, str(local_path))

                        size_remote = self.sftp.stat(remote_path).st_size
                        size_local = local_path.stat().st_size
                        if size_remote != size_local:
                            raise IOError(
                                f"Size mismatch: local={size_local}, remote={size_remote}"
                            )

                        archive_ok = self._move_remote_to_archive(remote_path, fname)

                        new_files_set.add(fname)
                        if archive_ok:
                            logger.info(
                                f"[{self.__class__.__name__}][{self.host}]:\n"
                                f"Downloaded and archived:\n"
                                f"{remote_path} -> {local_path}"
                            )
                        else:
                            logger.info(
                                f"[{self.__class__.__name__}][{self.host}]:\n"
                                f"Downloaded (archive failed):\n"
                                f"{remote_path} -> {local_path}"
                            )
                        break

                    except Exception as e:
                        local_path.unlink(missing_ok=True)
                        logger.warning(
                            f"[{self.__class__.__name__}][{self.host}]: "
                            f"Attempt {attempt}/{retries} failed for "
                            f"{local_path} <- {remote_path}:\n{e}"
                        )

                        if attempt == retries:
                            continue

                        delay = min(5, 1 * 2 ** (attempt - 1))
                        time.sleep(delay)

        except Exception as e:
            logger.error(
                f"[{self.__class__.__name__}][{self.host}] "
                f"Error reading {self.remote_dir}:\n{e}"
            )

        return new_files_set
# class RemoteFolderWatcher:
#     def __init__(self, sftp, host: str, remote_dir: str, local_dir: str):
#         self.sftp = sftp
#         self.host = host
#         self.remote_dir = Path(remote_dir).as_posix()
#         self.local_dir = Path(local_dir)
#         self.local_dir.mkdir(parents=True, exist_ok=True)
#         self.old_file_names = set()

#         try:
#             initial_files = [attr.filename for attr in self.sftp.listdir_attr(self.remote_dir)]
#             self.old_file_names.update(initial_files)
#             logger.info(f"[{self.__class__.__name__}][{self.host}] Initially stored files in {self.remote_dir}: {len(initial_files)} files")
#         except Exception as e:
#             logger.error(f"[{self.__class__.__name__}][{self.host}] Error reading initially stored files in {self.remote_dir}: {e}")     

#     def check_and_download(self,local_dir):
#         new_files_set = set()
#         try:
#             for attr in self.sftp.listdir_attr(self.remote_dir):
#                 fname = attr.filename
#                 if "tmp" in fname or fname in self.old_file_names:
#                     continue 

#                 remote_path = posixpath.join(self.remote_dir, fname)
#                 local_path = Path(local_dir) / fname
#                 local_path.parent.mkdir(parents=True, exist_ok=True)
#                 retries = 3
#                 for attempt in range(1, retries + 1):
#                     try:
#                         self.sftp.get(remote_path,local_path)
#                         size_remote = self.sftp.stat(remote_path).st_size
#                         size_local  = local_path.stat().st_size
#                         if size_remote != size_local:
#                             raise IOError(f"Size mismatch: local={size_local}, remote={size_remote}")
                        
#                         new_files_set.add(fname)
#                         logger.info(f"[{self.__class__.__name__}][{self.host}]:\nDownloaded:\n{remote_path} -> {local_path}")
#                         break

#                     except Exception as e:
#                         local_path.unlink(missing_ok=True)
#                         logger.warning(f"[{self.__class__.__name__}][{self.host}]:Attempt {attempt}/{retries} failed for {local_path} -> {remote_path}:\n{e}")

#                         if attempt == retries:
#                             continue
#                         else:
#                             delay = min(5, 1 * 2**(attempt-1))
#                             time.sleep(delay)
#                         continue
#         except Exception as e:
#             logger.error(f"[{self.__class__.__name__}][{self.host}] Error reading {self.remote_dir}:\n{e}")
#         return new_files_set

class _SftpWorker(QObject):
    status_changed = pyqtSignal(str)
    monitor_read =  pyqtSignal(str)
    control_param_updated = pyqtSignal(dict)
    warning = pyqtSignal(str, str)  # title, message
    files_arrived = pyqtSignal(str, str, list) #Signal for triggering tha calucation thread
    finished = pyqtSignal()

    def __init__(self, sftp_cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = sftp_cfg
        self._timer: QTimer | None = None 
        self._transport: paramiko.Transport | None = None
        self._sftp_control: paramiko.SFTPClient | None = None
        self._sftp_monitor: paramiko.SFTPClient | None = None
        self._sftp_gps: paramiko.SFTPClient | None = None
        self._sftp_hydro: paramiko.SFTPClient | None = None
        self._running = False
        self._state = "DISCONNECTED"
        self.host = self.cfg.get("host","192.168.0.210")
        self.port = int(self.cfg.get("port", 22))
        self.user = self.cfg.get("user", "pi")
        self.pwd = self.cfg.get("password", "raspberry")
        self.max_retries = self.cfg.get("remote_dirs",{}).get("max_retries",1)
        monitor_folder = self.cfg.get("remote_dirs",{}).get("config")
        monitor_file = self.cfg.get("remote_dirs",{}).get("monitor_file")
        control_folder = self.cfg.get("remote_dirs",{}).get("config")
        control_file = self.cfg.get("remote_dirs",{}).get("control_file")

        # self.remote_gps_folder = self.cfg.get("remote_dirs",{}).get("gps") #!!!
        # self.remote_hydro_folder = self.cfg.get("remote_dirs",{}).get("streaming") 
        # self.local_gps_folder = self.cfg.get("local_dirs",{}).get("gps") 
        # self.local_hydro_folder = self.cfg.get("local_dirs",{}).get("streaming") 
        # self.monitor_path = (Path(monitor_folder) / monitor_file).as_posix()
        # self.control_path = (Path(control_folder) / control_file).as_posix()

        self.remote_gps_folder = _remote_path(self.cfg.get("remote_dirs", {}).get("gps")) #!!!
        self.remote_hydro_folder = _remote_path(self.cfg.get("remote_dirs", {}).get("streaming"))
        self.remote_gps_history_folder = _remote_path(
            self.cfg.get("remote_dirs", {}).get("history_gps")
        )
        self.remote_hydro_history_folder = _remote_path(
            self.cfg.get("remote_dirs", {}).get("history_streaming")
        )

        self.local_gps_folder = self.cfg.get("local_dirs", {}).get("gps")
        self.local_hydro_folder = self.cfg.get("local_dirs", {}).get("streaming")

        self.monitor_path = posixpath.join(
            _remote_path(monitor_folder),
            monitor_file,
        )
        self.control_path = posixpath.join(
            _remote_path(control_folder),
            control_file,
        )

        self.status_changed.emit(self._state)
        self.initial_ctr_params_dict: Optional[dict] = None
        self._lock = Lock()
        self.gps_watcher: RemoteFolderWatcher | None = None
        self.hydro_watcher: RemoteFolderWatcher | None = None
        #self.files_arrived.connect(lambda *args: print("files_arrived:", args))
        self._force_download_all = False

    def __del__(self):
        self._disconnect()

    def start(self):
        if self._running:
            return

        logger.info(f"[{self.__class__.__name__}][{self.host}]; Worker sftp started")
        self._running = True
        
        self._timer = QTimer(self)
        assert self._timer is not None
        self._timer.setInterval(int(self.cfg.get("poll_interval_ms", 5000)))
        self._timer.timeout.connect(self._tick)
        self._connect()
        self._timer.start()

    def stop(self):
        self._running = False
        if self._timer:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None
        self._disconnect()
        self.finished.emit()
        logger.info(f"[{self.__class__.__name__}][{self.host}]; Worker sftp stopped)")

    def _tick(self):
        if self._state == "CONNECTING":
            return
        
        self._check_connected()
        if self._state == "DISCONNECTED":
            self._connect()
            return

        if not self.initial_ctr_params_dict:
            self.set_initial_control_params()
            # If user requested "download all", continue even if params were not read yet.
            if not self._force_download_all:
                return

        # if not self.gps_watcher: #!!!
        #     self.gps_watcher = RemoteFolderWatcher(self._sftp_gps,self.host,self.remote_gps_folder,self.local_gps_folder)
        # if not self.hydro_watcher:
        #     self.hydro_watcher = RemoteFolderWatcher(self._sftp_hydro,self.host,self.remote_hydro_folder,self.local_hydro_folder)

        if not self.gps_watcher:
            self.gps_watcher = RemoteFolderWatcher(
                self._sftp_gps,
                self.host,
                self.remote_gps_folder,
                self.local_gps_folder,
                self.remote_gps_history_folder,
            )

        if not self.hydro_watcher:
            self.hydro_watcher = RemoteFolderWatcher(
                self._sftp_hydro,
                self.host,
                self.remote_hydro_folder,
                self.local_hydro_folder,
                self.remote_hydro_history_folder,
            )

        # if self.gps_watcher: 
        #     self.local_gps_folder = self.cfg.get("local_dirs",{}).get("gps") 
        #     new_set = self.gps_watcher.check_and_download(self.local_gps_folder)

        #     if new_set:
        #         paths = [str(Path(self.local_gps_folder) / fn) for fn in new_set]
        #         self.files_arrived.emit(self.host, "gps", paths)
        #         self.gps_watcher.old_file_names.update(new_set)



        # if self.hydro_watcher: 
        #     self.local_hydro_folder = self.cfg.get("local_dirs",{}).get("streaming") 
        #     new_set = self.hydro_watcher.check_and_download(self.local_hydro_folder)

        #     if new_set:
        #         paths = [str(Path(self.local_hydro_folder) / fn) for fn in new_set]
        #         self.files_arrived.emit(self.host, "hydro", paths) 
        #         self.hydro_watcher.old_file_names.update(new_set)
        force = self._force_download_all
        self._force_download_all = False

        if self.gps_watcher:
            self.local_gps_folder = self.cfg.get("local_dirs", {}).get("gps")
            self._download_from_watcher(self.gps_watcher, "gps", self.local_gps_folder, force)

        if self.hydro_watcher:
            self.local_hydro_folder = self.cfg.get("local_dirs", {}).get("streaming")
            self._download_from_watcher(self.hydro_watcher, "hydro", self.local_hydro_folder, force)              

        if (content := self._read_monitor_file()):
            self.monitor_read.emit(content)
        else:
            logger.warning(f"[{self.__class__.__name__}][{self.host}]; Monitor file read failed.") 

    def _download_from_watcher(self, watcher, role, local_dir, force):
        if not watcher:
            return
        if force:
            watcher.old_file_names.clear()

        new_set = watcher.check_and_download(local_dir)
        if new_set:
            paths = [str(Path(local_dir) / fn) for fn in new_set]
            self.files_arrived.emit(self.host, role, paths)
            watcher.old_file_names.update(new_set)
    

    def _connect(self):
        if self._state == "CONNECTING":
            return

        self._disconnect()
        self._state = "CONNECTING"
        self.status_changed.emit(self._state)
        logger.info(f"[{self.__class__.__name__}][{self.host}]; Connecting...")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(hostname=self.host, port=self.port, username=self.user, password=self.pwd, timeout=5)
            transport = client.get_transport()
            if transport is not None and transport.is_active():
                logger.info(f"[{self.__class__.__name__}][{self.host}]; SSH connection established.")
                self._client = client
                self._transport = transport
                self._transport.set_keepalive(0)
                self._sftp_control = client.open_sftp()
                self._sftp_monitor = client.open_sftp()
                self._sftp_gps = client.open_sftp()
                self._sftp_hydro = client.open_sftp()

                for sftp in (self._sftp_control, self._sftp_monitor, self._sftp_gps, self._sftp_hydro):
                    try:
                        ch = sftp.get_channel()
                        if ch is not None:
                            ch.settimeout(5.0)   # or: sftp.sock.settimeout(5.0)
                    except Exception:
                        pass

                self._is_connected = True
                self._state = "CONNECTED"
                self.status_changed.emit(self._state)
        except Exception as e:
            self._state = "DISCONNECTED"
            self.status_changed.emit(self._state)
            logger.error(f"[{self.__class__.__name__}][{self.host}]; Connection problem!!!\n{e}")

        
    def _disconnect(self):
        try:
            if self._sftp_control: self._sftp_control.close()
            if self._sftp_monitor: self._sftp_monitor.close()
            if self._sftp_gps: self._sftp_gps.close()
            if self._sftp_hydro: self._sftp_hydro.close()
        except Exception:
            pass
        self._sftp_control = None
        self._sftp_monitor = None
        self._sftp_gps = None
        self._sftp_hydro = None
        self.gps_watcher = None
        self.hydro_watcher = None

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
        logger.info(f"[{self.__class__.__name__}][{self.host}]; Disconnected")

    def _is_channels_active(self):
                for sftp_client in (self._sftp_control ,self._sftp_monitor,self._sftp_gps,self._sftp_hydro):
                    if sftp_client is None:
                        continue
                    ch = getattr(sftp_client, "sock", None)
                    if not ch or ch.closed:
                        return False
                    try:
                        sftp_client.listdir(".")
                    except Exception:
                        return False
                return True
                    

    def _check_connected(self):
            if self._client and self._transport and self._transport.is_active():
                if self._is_channels_active():
                    self._is_connected = True
                    self._state = "CONNECTED"
                    self.status_changed.emit(self._state)
                    #logger.info(f"[{self.__class__.__name__}][{self.host}]; Connected")
                else:
                    self._is_connected = False
                    self._state = "DISCONNECTED"
                    self.status_changed.emit(self._state)
                    logger.info(f"[{self.__class__.__name__}][{self.host}]; Channel is not active")

            else:
                self._is_connected = False
                self._state = "DISCONNECTED"
                self.status_changed.emit(self._state)
                logger.info(f"[{self.__class__.__name__}][{self.host}]; Disconnected")

    def _read_monitor_file(self) -> str | None:
        if self._sftp_monitor is None:
            logger.warning(f"[{self.__class__.__name__}][{self.host}]; self._sftp_monitor is None")
            return
        #with self._lock:
        try:
            self._sftp_monitor.stat(self.monitor_path)
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}][{self.host}]; Monitor file not found!!!")
            return None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                with self._sftp_monitor.open(self.monitor_path, mode="rb", bufsize=32768) as f: 
                    size = self._sftp_monitor.stat(self.monitor_path).st_size
                    data = f.read(size)  
                    #logger.info(f"[{self.__class__.__name__}][{self.host}]; Monitor file read successfully on attempt {attempt}.")
                    return data.decode("utf-8", errors="replace")
            except Exception as e:
                logger.warning(f"[{self.__class__.__name__}] Read attempt {attempt}/{self.max_retries} failed for {self.monitor_path}:\n{e}")
                time.sleep(1)
                continue
        return None   

    def _read_control_file(self) -> Optional[str]:
        if self._sftp_control is None:
            return None   
        #with self._lock:
        try:
            self._sftp_control.stat(self.control_path)
        except Exception as e:
            logger.error(f"[{self.__class__.__name__}][{self.host}]; self._sftp_control")
            return None
        for attempt in range(1, self.max_retries + 1):
            try:
                with self._sftp_control.open(self.control_path, mode="rb", bufsize=32768) as f: 
                    try:
                        f.prefetch()
                    except Exception:
                        pass
                    try:
                        size = self._sftp_control.stat(self.control_path).st_size
                        data = f.read(size)  
                        data = data.decode("utf-8", errors="replace")
                        logger.info(f"[{self.__class__.__name__}][{self.host}]; Control file read successfully on attempt {attempt}.")
                        return data
                    except Exception:
                        data = f.read()      
                        data = data.decode("utf-8", errors="replace")
                        logger.info(f"[{self.__class__.__name__}][{self.host}]; Control file read successfully on attempt {attempt}.")
                        return data
            except Exception as e:
                logger.warning(f"[{self.__class__.__name__}][{self.host}]; Read attempt {attempt}/{self.max_retries} failed for {self.control_path}:\n{e}")
                time.sleep(1)
                continue
        return None

    def set_initial_control_params(self):
        assert self._sftp_control is not None
        if not (initial_ctr_params_str := self._read_control_file()): 
            logger.warning(f"[{self.__class__.__name__}][{self.host}]; Read data is None")
            return

        self.initial_ctr_params_dict = {}
        for line in initial_ctr_params_str.splitlines():
            line_stripped = line.strip()
            if not line_stripped or '=' not in line_stripped:
                continue
            key, value = line_stripped.split('=',1)
            printable_value = ''.join(ch for ch in value if ch in string.printable)
            self.initial_ctr_params_dict[key.strip()] = printable_value.strip()   
            self.control_param_updated.emit(self.initial_ctr_params_dict)
    
    
    # def on_control_param_changed(self,new_ctr_param_dict: dict, streaming_path: str) -> None: XXX
    def on_control_param_changed(self,new_ctr_param_dict: dict) -> None:
        if not self.hydro_watcher or not self.gps_watcher:
            self.warning.emit("SFTP server warning",
                              "SFTP server was not initialized completely.\nTry to set parameters later.")
            # msg = QMessageBox() #XXX move to View
            # msg.setIcon(QMessageBox.Warning)
            # msg.setWindowTitle("SFTP serwer warning")
            # msg.setText("SFTP serwer was not intiliased completely")
            # msg.setInformativeText("Try to set parameters later")
            # msg.setStandardButtons(QMessageBox.Ok)
            # result = msg.exec_()
            return

        
        # if streaming_path: XXX
        #     self.hydro_watcher.local_dir = Path(streaming_path)
        #     self.gps_watcher.local_dir = Path(streaming_path.replace("streaming","gps"))
        #     self.gps_watcher.local_dir.mkdir(parents=True, exist_ok=True)
            
        
        assert self._sftp_control is not None
        if not (old_ctr_params_str := self._read_control_file()):
            logger.warning(f"[{self.__class__.__name__}][{self.host}]; Read data in control file is None")
            return

        old_ctr_param_dict = {}
        for line in old_ctr_params_str.splitlines():
            line_stripped = line.strip()
            if not line_stripped or '=' not in line_stripped:
                continue
            key, value = line_stripped.split('=',1)
            printable_value = ''.join(ch for ch in value if ch in string.printable)
            old_ctr_param_dict[key.strip()] = printable_value.strip()   

        for key in old_ctr_param_dict:
            if key in new_ctr_param_dict:
                old_ctr_param_dict[key] = new_ctr_param_dict[key]

        new_file_content = "\n".join(f"{k}={v}" for k, v in old_ctr_param_dict.items()) + "\n"
        tmp_path = self.control_path + ".tmp"

        for attempt in range(1, self.max_retries + 1):
            try:
                with self._sftp_control.open(tmp_path, mode="wb", bufsize=32768) as f:
                    f.write(new_file_content.encode("utf-8"))

                self._sftp_control.posix_rename(tmp_path, self.control_path)
                logger.info(f"[{self.__class__.__name__}][{self.host}]; Control file updated successfully on attempt {attempt}.")
                self.control_param_updated.emit(old_ctr_param_dict)
                return None 
            except Exception as e:
                logger.warning(f"[{self.__class__.__name__}][{self.host}]; Write control file attempt {attempt}/{self.max_retries} failed: {e}")
                try:
                    self._sftp_control.remove(tmp_path)
                except Exception:
                    pass
                time.sleep(1)
                continue
        logger.error(f"[{self.__class__.__name__}][{self.host}]; Failed to update control file after {self.max_retries} attempts.")
        return None
    
    def request_download_all(self):
        """
        Treat all remote files as 'new' once and download them immediately.
        Executed in the worker thread (queued connection from ReceiverController).
        """
        self._force_download_all = True
        QTimer.singleShot(0, self._tick)




            
            
        

        
