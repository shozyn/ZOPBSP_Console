# target.py

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal
from qgis.core import QgsPointXY
import socket


class ReceiverClientWorker(QObject):
    """
    Worker class that communicates with the GPS server over UDP every second
    and emits the parsed position as latitude/longitude in decimal degrees.
    """
    new_gps = pyqtSignal(float, float)  # latitude, longitude

    def __init__(self, server_ip, server_port, parent=None):
        super().__init__(parent)
        self.server_ip = server_ip
        self.server_port = server_port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(5)
        self.timer = None  # Delay QTimer creation

    def start(self):
        # This is called inside the worker thread
        self.timer = QTimer(self)  # Must be owned by this object
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.fetch_position)
        self.timer.start()
        print("[ReceiverClientWorker] Timer started in thread:", QThread.currentThread())

    def stop(self):
        self.timer.stop()

    def fetch_position(self):
        try:
            self.sock.sendto(b"GET", (self.server_ip, self.server_port))
            data, _ = self.sock.recvfrom(1024)
            nmea = data.decode('utf-8')

            if nmea.startswith("$GNGGA"):
                parts = nmea.split(',')
                lat = self.nmea_to_decimal(parts[2], parts[3], 2)
                lon = self.nmea_to_decimal(parts[4], parts[5], 3)

                if lat is not None and lon is not None:
                    self.new_gps.emit(lat, lon)

        except socket.timeout:
            print("[ReceiverClientWorker] Timeout waiting for GPS response.")
        except Exception as e:
            print(f"[ReceiverClientWorker] Error: {e}")

    @staticmethod
    def nmea_to_decimal(degree_minute, direction, degree_length):
        if degree_minute == "":
            return None
        degrees = int(degree_minute[:degree_length])
        minutes = float(degree_minute[degree_length:])
        decimal = degrees + (minutes / 60)
        if direction in ['S', 'W']:
            decimal = -decimal
        return decimal


class Target(QObject):
    """
    Represents a target object with a real GPS position and a predicted one.
    Updates are handled asynchronously via a background UDP client.
    """
    actual_position_updated = pyqtSignal(QgsPointXY)
    predicted_position_updated = pyqtSignal(QgsPointXY)

    def __init__(self, server_ip, server_port, calculator=None, parent=None):
        """
        :param server_ip: IP address of the GPS server
        :param server_port: Port number of the GPS server
        :param calculator: Object that calculates predicted positions
        """
        super().__init__(parent)
        self.actual_position = None
        self.predicted_position = None
        self.calculator = calculator

        self.worker = ReceiverClientWorker(server_ip, server_port)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)

        # Connections
        self.thread.started.connect(self.worker.start)
        self.worker.new_gps.connect(self.update_actual_position)

        self.thread.start()

    def update_actual_position(self, lat, lon):
        #self.actual_position = QgsPointXY(lon, lat)
        self.actual_position = QgsPointXY(18.54534607666666801, 54.5435800300000011)
        self.actual_position_updated.emit(self.actual_position)

        # Call prediction logic
        # self.predicted_position = self.calculator.predict(self.actual_position)
        # if self.predicted_position:
        #     self.predicted_position_updated.emit(self.predicted_position)

    def stop(self):
        self.worker.stop()
        self.thread.quit()
        self.thread.wait()
