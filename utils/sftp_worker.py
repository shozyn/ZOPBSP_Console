import string
from PyQt5.QtCore import QObject,  QTimer, pyqtSignal
import paramiko
from pathlib import Path
import logging
from typing import Optional
from threading import Lock

logger = logging.getLogger(__name__)

class RemoteFolderWatcher:
    def __init__(self, sftp, remote_dir: str, local_dir: str):
        self.sftp = sftp
        self.remote_dir = Path(remote_dir).as_posix()
        self.local_dir = Path(local_dir)
        self.local_dir.mkdir(parents=True, exist_ok=True)
        self.old_files = set()

        #Mark all existing remote files as already seen
        try:
            initial_files = [attr.filename for attr in self.sftp.listdir_attr(self.remote_dir)]
            self.old_files.update(initial_files)
            logger.info(f"Initially stored files for {self.remote_dir}: {len(initial_files)} files")
        except Exception as e:
            logger.error(f"Error reading initially stored files of {self.remote_dir}: {e}")     

    def check_and_download(self):
        new_files = []
        try:
            for attr in self.sftp.listdir_attr(self.remote_dir):
                fname = attr.filename
                if fname not in self.old_files:
                    remote_path = f"{self.remote_dir}/{fname}"
                    local_path = self.local_dir / fname
                    try:
                        self.sftp.get(remote_path,local_path)
                        self.old_files.add(fname)
                        new_files.append(str(local_path))
                        logger.info(f"Downloaded {remote_path} -> {local_path}")
                    except Exception as e:
                        logger.error(f"Failed to download {remote_path}: {e}")
        except Exception as e:
            logger.error(f"Error listing {self.remote_dir}: {e}")
        return new_files

class _SftpWorker(QObject):
    status_changed = pyqtSignal(str)
    monitor_read =  pyqtSignal(str)
    control_param_updated = pyqtSignal(dict)

    finished = pyqtSignal()

    def __init__(self, sftp_cfg: dict, parent=None):
        super().__init__(parent)
        self.cfg = sftp_cfg
        self._timer: Optional[QTimer] = None
        self._client: paramiko.SSHClient | None = None
        self._transport: paramiko.Transport | None = None
        self._sftp_control: paramiko.SFTPClient | None = None
        self._sftp_monitor: paramiko.SFTPClient | None = None
        self._sftp_gps: paramiko.SFTPClient | None = None
        self._sftp_hydro: paramiko.SFTPClient | None = None
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
        control_folder = self.cfg.get("remote_dirs",{}).get("config")
        control_file = self.cfg.get("remote_dirs",{}).get("control_file")

        self.remote_gps_folder = self.cfg.get("remote_dirs",{}).get("gps") 
        self.remote_hydro_folder = self.cfg.get("remote_dirs",{}).get("streaming") 
        self.local_gps_folder = self.cfg.get("local_dirs",{}).get("gps") 
        self.local_hydro_folder = self.cfg.get("local_dirs",{}).get("streaming") 
        self.monitor_path = (Path(monitor_folder) / monitor_file).as_posix()
        self.control_path = (Path(control_folder) / control_file).as_posix()
        self.status_changed.emit(self._state)
        self.initial_ctr_params_dict: Optional[dict] = None
        self._lock = Lock()
        self.gps_watcher: Optional[RemoteFolderWatcher] = None
        self.hydro_watcher: Optional[RemoteFolderWatcher] = None

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
            return 

        if not self.gps_watcher:
            self.gps_watcher = RemoteFolderWatcher(self._sftp_gps,self.remote_gps_folder,self.local_gps_folder)
        if not self.hydro_watcher:
            self.hydro_watcher = RemoteFolderWatcher(self._sftp_hydro,self.remote_hydro_folder,self.local_hydro_folder)

        if self.gps_watcher: self.gps_watcher.check_and_download()
        if self.hydro_watcher: self.hydro_watcher.check_and_download()

        if (content := self._read_monitor_file()):
            logger.info(f"[{self.__class__.__name__}][{self.host}]; Monitor file read successfully.") 
            self.monitor_read.emit(content)
        else:
            logger.warning(f"[{self.__class__.__name__}][{self.host}]; Monitor file read failed.") 

        

    def _connect(self):
        if self._state in ("CONNECTING","CONNECTING"):
            return

        self._disconnect()
        self._state = "CONNECTING"
        self.status_changed.emit(self._state)
        logger.info(f"[{self.__class__.__name__}][{self.host}]; Connecting...")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(hostname=self.host, port=self.port, username=self.user, password=self.pwd, timeout=10)
            transport = client.get_transport()
            if transport is not None and transport.is_active():
                logger.info(f"[{self.__class__.__name__}][{self.host}]; SSH connection established.")
                print(f"[{self.host}]; trasport layer is active")
                self._client = client
                self._transport = transport
                self._transport.set_keepalive(30)
                self._sftp_control = client.open_sftp()
                self._sftp_monitor = client.open_sftp()
                self._sftp_gps = client.open_sftp()
                self._sftp_hydro = client.open_sftp()

                self._is_connected = True
                self._state = "CONNECTED"
                self.status_changed.emit(self._state)
                logger.info(f"[{self.__class__.__name__}][{self.host}]; Connected.")
        except Exception as e:
            print(e) 
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
        self.sftp_monitor = None
        self._sftp_gps = None
        self._sftp_hydro = None
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

    def _check_connected(self):
            if self._client and self._transport and self._transport.is_active():
                self._is_connected = True
                self._state = "CONNECTED"
                self.status_changed.emit(self._state)
                logger.info(f"[{self.__class__.__name__}][{self.host}]; Connected")
            else:
                self._is_connected = False
                self._state = "DISCONNECTED"
                self.status_changed.emit(self._state)
                logger.info(f"[{self.__class__.__name__}][{self.host}]; Disconnected")

    def _read_monitor_file(self) -> str | None:
        assert self._sftp_monitor is not None
        print(f"[{self.host}]; Before reading the monitor file")
        with self._lock:
            try:
                self._sftp_monitor.stat(self.monitor_path)
            except Exception as e:
                logger.error(f"[{self.__class__.__name__}][{self.host}]; Monitor file not found!!!")
                return None
            
            for attempt in range(1, self.max_retries + 1):
                try:
                    with self._sftp_monitor.open(self.monitor_path, mode="rb", bufsize=32768) as f: 
                        # try:
                        #     print(f"[{self.host}]; before prefetch")
                        #     f.prefetch()
                        #     print(f"[{self.host}]; after prefetch")
                        # except Exception:
                        #     pass
                        try:
                            size = self._sftp_monitor.stat(self.monitor_path).st_size
                            print(f"[{self.host}]; before read(size)")
                            data = f.read(size)  
                            print(f"[{self.host}]; after read(size)")
                            return data.decode("utf-8", errors="replace")
                        except Exception:
                            print(f"[{self.host}]; before read()")
                            data = f.read() 
                            return data.decode("utf-8", errors="replace")
                            print(f"[{self.host}]; after read())")   
                except Exception as e:
                    logger.warning(f"[{self.__class__.__name__}] Read attempt {attempt}/{self.max_retries} failed for {self.monitor_path}:\n{e}")
                    return None
    

    def _read_control_file(self) -> Optional[str]:
        assert self._sftp_control is not None
        with self._lock:
            try:
                self._sftp_control.stat(self.control_path)
            except Exception as e:
                logger.error(f"[{self.__class__.__name__}][{self.host}]; Control file not found!!!")
                return None
            print(f"[{self.host}]; Before reading control file")
            for attempt in range(1, self.max_retries + 1):
                try:
                    print(f"[{self.host}]; Before opening control file")
                    with self._sftp_control.open(self.control_path, mode="rb", bufsize=32768) as f: 
                        print(f"[{self.host}]; After opening control file")
                        try:
                            print(f"[{self.host}]; Before fetch control")
                            f.prefetch()
                            print(f"[{self.host}]; After fetch control")
                        except Exception:
                            pass
                        try:
                            size = self._sftp_control.stat(self.control_path).st_size
                            print(f"[{self.host}]; Before read(size) control")
                            data = f.read(size)  
                            print(f"[{self.host}]; After read(size) control")
                            data = data.decode("utf-8", errors="replace")
                            return data
                        except Exception:
                            print(f"[{self.host}]; Before read() control")
                            data = f.read()      
                            print(f"[{self.host}]; After read() control")
                            data = data.decode("utf-8", errors="replace")
                            print(f"[{self.host}]; After reading control file")
                            return data
                except Exception as e:
                    logger.warning(f"[{self.__class__.__name__}][{self.host}]; Read attempt {attempt}/{self.max_retries} failed for {self.control_path}:\n{e}")
                    return None

    def set_initial_control_params(self):
        print(f"[{self.host}]; set_initial_control_params")
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
    
    
    def on_control_param_changed(self,new_ctr_param_dict: dict, streaming_path: str) -> None:
        print(f"[{self.host}]; entering on_control_param_changed()")
        print(f"streaming_path: {streaming_path}")
        
        if streaming_path:
            self.hydro_watcher.local_dir = Path(streaming_path)
            self.gps_watcher.local_dir = Path(streaming_path.replace("streaming","gps"))
            self.gps_watcher.local_dir.mkdir(parents=True, exist_ok=True)
            
        
        assert self._sftp_control is not None
        if not (old_ctr_params_str := self._read_control_file()):
            logger.warning(f"[{self.__class__.__name__}][{self.host}]; Read data is None")
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

        print(f"[{self.host}]; the new variable dictionary was created")

        for attempt in range(1, self.max_retries + 1):
            try:
                with self._sftp_control.open(tmp_path, mode="wb", bufsize=32768) as f:
                    f.write(new_file_content.encode("utf-8"))
                    print(f"[{self.host}]; temporary file was written")

                self._sftp_control.posix_rename(tmp_path, self.control_path)
                print(f"[{self.host}]; rename was performed")
                logger.info(f"[{self.__class__.__name__}][{self.host}]; Control file updated successfully on attempt {attempt}.")
                self.control_param_updated.emit(old_ctr_param_dict)
                break 

            except Exception as e:
                logger.warning(f"[{self.__class__.__name__}][{self.host}]; Write attempt {attempt}/{self.max_retries} failed: {e}")

                try:
                    self._sftp_control.remove(tmp_path)
                except Exception:
                    pass

                if attempt == self.max_retries:
                    logger.error(f"[{self.__class__.__name__}][{self.host}]; Failed to update control file after {self.max_retries} attempts.")




            
            
        

        
