from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal
from PyQt5.QtNetwork import QUdpSocket, QHostAddress
#from qgis.core import QgsPointXY
import socket

class ReceiverClientWorker(QObject):
    """
    Worker class that communicates with the GPS server over UDP 
    """
    new_gps = pyqtSignal(float, float)  # latitude, longitude
    finished = pyqtSignal()
    

    def __init__(self, server_ip, server_port, parent=None):
        super().__init__(parent)
        self.server_ip = server_ip
        self.server_port = server_port
        # self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # self.sock.settimeout(2)
        # self.timer = None  # Delay QTimer creation
        self._sock: QUdpSocket | None = None
        self._timer: QTimer | None = None
        self._running = False



    def start(self):
        # This is called inside the worker thread
        print(f"[{self.__class__.__name__}] START called in thread: {QThread.currentThread()}")
        # self.timer = QTimer(self)  # Must be owned by this object
        # self.timer.setInterval(2000)
        # self.timer.timeout.connect(self.fetch_position)
        # self.timer.start()

        if self._running:
            return
        self._running = True

        # QUdpSocket must be used from the thread that owns it.
        self._sock = QUdpSocket(self)
        # Bind to an ephemeral local port so we can receive the reply.
        self._sock.bind(QHostAddress.AnyIPv4, 0)
        self._sock.readyRead.connect(self._on_ready_read)

        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._send_request)
        self._timer.start()
        print("[[{self.__class__.__name__}] Timer started in thread:", QThread.currentThread())

    def stop(self):
        print(f"[{self.__class__.__name__}] STOP called in thread: {QThread.currentThread()}")
        #self.timer.stop()
        if not self._running:
            self.finished.emit()
            return
        self._running = False

        if self._timer:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None

        if self._sock:
            self._sock.close()
            self._sock.deleteLater()
            self._sock = None

        print(f"[{self.__class__.__name__}] stopped")
        self.finished.emit()
        

    def _send_request(self):
        if not (self._running and self._sock):
            return
        self._sock.writeDatagram(
            b"GET",
            QHostAddress(self.server_ip),
            int(self.server_port),
        )

    def _on_ready_read(self):
        if not self._sock:
            return
        while self._sock.hasPendingDatagrams():
            datagram_size = self._sock.pendingDatagramSize()
            data, host, port = self._sock.readDatagram(datagram_size)
            text = data.decode(errors="ignore").strip()
            # Expecting an NMEA-like sentence; handle GGA if present
            latlon = self._parse_latlon_from_nmea(text)
            if latlon:
                lat, lon = latlon
                self.new_gps.emit(lat, lon)

    # ---------- Parsing ----------
    @staticmethod
    def _parse_latlon_from_nmea(sentence: str):
        """
        Very small parser for $GNGGA / $GPGGA:
          $GNGGA,hhmmss.sss,ddmm.mmmm,N,dddmm.mmmm,E,fix,...
        Returns (lat, lon) in decimal degrees or None.
        """
        if not sentence.startswith(("$GNGGA", "$GPGGA")):
            return None
        parts = sentence.split(",")
        if len(parts) < 6:
            return None
        lat = ReceiverClientWorker._nmea_to_decimal(parts[2], parts[3], 2)
        lon = ReceiverClientWorker._nmea_to_decimal(parts[4], parts[5], 3)
        if lat is None or lon is None:
            return None
        return (lat, lon)

    @staticmethod
    def _nmea_to_decimal(deg_min: str, hemi: str, deg_len: int):
        if not deg_min:
            return None
        try:
            deg = int(deg_min[:deg_len])
            minutes = float(deg_min[deg_len:])
            dec = deg + minutes / 60.0
            if hemi in ("S", "W"):
                dec = -dec
            return dec
        except Exception:
            return None
