from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot
from PyQt5.QtNetwork import QUdpSocket, QHostAddress
import logging
import time


logger = logging.getLogger(__name__)


class ReceiverClientWorker(QObject):
    """
    Worker class that communicates with the GPS target server over UDP.

    The worker:
        1. creates a UDP socket;
        2. periodically sends a request message, by default "GET";
        3. receives UDP datagrams;
        4. searches for an NMEA GGA sentence;
        5. extracts latitude, longitude and timestamp;
        6. emits the parsed position to TargetController.
    """

    new_gps = pyqtSignal(float, float, str)  # latitude, longitude, timestamp
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(
        self,
        server_ip,
        server_port,
        poll_interval_ms=2000,
        stale_timeout_ms=6000,
        request_text="GET",
        parent=None,
    ):
        super().__init__(parent)

        self.server_ip = str(server_ip or "")
        self.server_port = server_port
        self.poll_interval_ms = int(poll_interval_ms)
        self.stale_timeout_ms = int(stale_timeout_ms)
        self.request_text = str(request_text)

        self._sock = None
        self._timer = None
        self._stale_timer = None
        self._running = False
        self._last_gps_time = None
        self._state = "DISCONNECTED"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @pyqtSlot()
    def start(self):
        """
        Start UDP polling.

        This method is executed in the worker thread. Therefore, QTimer and
        QUdpSocket are also created in the worker thread.
        """
        if self._running:
            return

        self._set_state("STARTING")

        port = self._validated_port()
        if port is None:
            self._set_state("ERROR")
            self.finished.emit()
            return

        if QHostAddress(self.server_ip).isNull():
            self._emit_error(f"Invalid target IP address: {self.server_ip!r}")
            self._set_state("ERROR")
            self.finished.emit()
            return

        self._running = True

        self._sock = QUdpSocket(self)

        if not self._sock.bind(QHostAddress.AnyIPv4, 0):
            self._emit_error(f"Could not bind UDP socket: {self._sock.errorString()}")
            self._set_state("ERROR")
            self._cleanup()
            self.finished.emit()
            return

        self._sock.readyRead.connect(self._on_ready_read)

        self._timer = QTimer(self)
        self._timer.setInterval(self.poll_interval_ms)
        self._timer.timeout.connect(self._send_request)
        self._timer.start()

        self._stale_timer = QTimer(self)
        self._stale_timer.setInterval(1000)
        self._stale_timer.timeout.connect(self._check_stale)
        self._stale_timer.start()

        self._set_state("POLLING")

        # Send first request immediately.
        QTimer.singleShot(0, self._send_request)

    @pyqtSlot()
    def stop(self):
        """
        Stop UDP polling and release Qt resources.
        """
        if not self._running:
            self._set_state("DISCONNECTED")
            self.finished.emit()
            return

        self._set_state("STOPPING")
        self._running = False

        self._cleanup()

        self._set_state("DISCONNECTED")
        self.finished.emit()

    def _cleanup(self):
        """
        Stop timers and close the UDP socket.
        """
        if self._timer:
            self._timer.stop()
            self._timer.deleteLater()
            self._timer = None

        if self._stale_timer:
            self._stale_timer.stop()
            self._stale_timer.deleteLater()
            self._stale_timer = None

        if self._sock:
            self._sock.close()
            self._sock.deleteLater()
            self._sock = None

    # ------------------------------------------------------------------
    # UDP communication
    # ------------------------------------------------------------------

    def _send_request(self):
        """
        Send one UDP request to the target.
        """
        if not (self._running and self._sock):
            return

        port = self._validated_port()
        if port is None:
            self._set_state("ERROR")
            return

        sent = self._sock.writeDatagram(
            self.request_text.encode("utf-8"),
            QHostAddress(self.server_ip),
            port,
        )

        if sent == -1:
            self._emit_error(f"UDP write failed: {self._sock.errorString()}")
            self._set_state("ERROR")

    def _on_ready_read(self):
        """
        Read all pending UDP datagrams.

        Non-GPS packets, for example 'Get', are ignored.
        Valid GGA packets emit:
            new_gps(latitude, longitude, timestamp)
        """
        if not self._sock:
            return

        while self._sock.hasPendingDatagrams():
            datagram_size = self._sock.pendingDatagramSize()
            if datagram_size < 0:
                logger.debug(
                    "[ReceiverClientWorker][%s:%s] Ignoring invalid UDP datagram size: %s",
                    self.server_ip,
                    self.server_port,
                    datagram_size,
                )
                break

            data, host, port = self._sock.readDatagram(datagram_size)
            if data is None:
                logger.warning(
                    "[ReceiverClientWorker][%s:%s] UDP read failed: %s",
                    self.server_ip,
                    self.server_port,
                    self._sock.errorString(),
                )
                continue

            text = data.decode("utf-8", errors="replace").strip()

            latlon = self._parse_latlon_from_nmea(text)

            if latlon is None:
                logger.debug(
                    "[ReceiverClientWorker] Ignoring non-GPS UDP message from %s:%s: %r",
                    host.toString(),
                    port,
                    text,
                )
                continue

            lat, lon = latlon

            timestamp = self._extract_timestamp_from_nmea(text)

            if not timestamp:
                timestamp = time.strftime("%H:%M:%S")

            self._last_gps_time = time.monotonic()
            self._set_state("RECEIVING")

            # IMPORTANT:
            # new_gps has three arguments:
            #     float, float, str
            self.new_gps.emit(lat, lon, timestamp)

    # ------------------------------------------------------------------
    # Status / stale detection
    # ------------------------------------------------------------------

    def _check_stale(self):
        """
        Mark the target as STALE if no GPS packet has arrived recently.
        """
        if not self._running:
            return

        if self._last_gps_time is None:
            return

        elapsed_ms = (time.monotonic() - self._last_gps_time) * 1000.0

        if elapsed_ms > self.stale_timeout_ms:
            self._set_state("STALE")

    def _set_state(self, state):
        """
        Store and emit communication state.
        """
        if self._state == state:
            return

        self._state = state
        self.status_changed.emit(state)

        logger.info(
            "[ReceiverClientWorker][%s:%s] state=%s",
            self.server_ip,
            self.server_port,
            state,
        )

    def _emit_error(self, message):
        logger.error(
            "[ReceiverClientWorker][%s:%s] %s",
            self.server_ip,
            self.server_port,
            message,
        )
        self.error_occurred.emit(message)

    def _validated_port(self):
        """
        Validate UDP port.
        """
        try:
            port = int(self.server_port)
        except (TypeError, ValueError):
            self._emit_error(f"Invalid target UDP port: {self.server_port!r}")
            return None

        if not (1 <= port <= 65535):
            self._emit_error(f"UDP port outside valid range: {port}")
            return None

        return port

    # ------------------------------------------------------------------
    # NMEA parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_latlon_from_nmea(message):
        """
        Robust parser for NMEA GGA messages.

        It accepts:
            $GNGGA,...
            $GPGGA,...
            $GAGGA,...
            $BDGGA,...
            $GLGGA,...

        It also handles:
            - leading/trailing spaces;
            - CR/LF line endings;
            - multiple NMEA sentences in one UDP packet;
            - extra text before the GGA sentence;
            - checksum suffix after '*'.

        Returns
        -------
        tuple[float, float] | None
            (latitude, longitude) in decimal degrees.
        """
        if not message:
            return None

        text = str(message).replace("\x00", "").strip()

        candidates = []

        for raw_line in text.replace("\r", "\n").split("\n"):
            line = raw_line.strip()

            if not line:
                continue

            dollar_pos = line.find("$")
            if dollar_pos >= 0:
                line = line[dollar_pos:]

            # Accept any NMEA talker ID ending with GGA:
            # $GNGGA, $GPGGA, $GAGGA, $GLGGA, etc.
            if len(line) >= 6 and line.startswith("$") and line[3:6] == "GGA":
                candidates.append(line)

        if not candidates:
            return None

        sentence = candidates[0]

        if "*" in sentence:
            sentence = sentence.split("*", 1)[0]

        parts = [p.strip() for p in sentence.split(",")]

        # Required fields:
        # 0: $GNGGA
        # 1: UTC time
        # 2: latitude
        # 3: N/S
        # 4: longitude
        # 5: E/W
        if len(parts) < 6:
            return None

        lat_raw = parts[2]
        lat_hemi = parts[3].upper()
        lon_raw = parts[4]
        lon_hemi = parts[5].upper()

        lat = ReceiverClientWorker._nmea_to_decimal(lat_raw, lat_hemi, 2)
        lon = ReceiverClientWorker._nmea_to_decimal(lon_raw, lon_hemi, 3)

        if lat is None or lon is None:
            return None

        return lat, lon

    @staticmethod
    def _extract_timestamp_from_nmea(message):
        """
        Extract UTC time from an NMEA GGA sentence and add 2 hours.

        Example
        -------
        $GNGGA,130717.00,5350.2760005,N,01738.8892785,E,...

        NMEA UTC time:
            13:07:17

        Displayed local time after +2 hours:
            15:07:17

        The implementation also correctly handles midnight overflow, e.g.
            23:30:00 + 2 hours -> 01:30:00
        """
        if not message:
            return ""

        from datetime import datetime, timedelta

        text = str(message).replace("\x00", "").strip()

        for raw_line in text.replace("\r", "\n").split("\n"):
            line = raw_line.strip()

            if not line:
                continue

            dollar_pos = line.find("$")
            if dollar_pos >= 0:
                line = line[dollar_pos:]

            if not (len(line) >= 6 and line.startswith("$") and line[3:6] == "GGA"):
                continue

            if "*" in line:
                line = line.split("*", 1)[0]

            parts = [p.strip() for p in line.split(",")]

            if len(parts) < 2:
                return ""

            raw_time = parts[1]

            # Expected NMEA time format:
            # hhmmss.ss or hhmmss
            if len(raw_time) < 6:
                return ""

            try:
                hh = int(raw_time[0:2])
                mm = int(raw_time[2:4])
                ss = int(raw_time[4:6])

                utc_time = datetime(2000, 1, 1, hh, mm, ss)

                # Fixed local-time correction requested by the user.
                local_time = utc_time + timedelta(hours=2)

                return local_time.strftime("%H:%M:%S")

            except Exception:
                return ""

        return ""

    @staticmethod
    def _nmea_to_decimal(deg_min, hemi, deg_len):
        """
        Convert NMEA degree-minute coordinate to decimal degrees.

        Latitude:
            DDMM.MMMMM

        Longitude:
            DDDMM.MMMMM

        Example
        -------
        5350.2760005,N

        degrees = 53
        minutes = 50.2760005

        decimal = 53 + 50.2760005 / 60
        """
        if not deg_min:
            return None

        hemi = str(hemi).strip().upper()

        if hemi not in ("N", "S", "E", "W"):
            return None

        try:
            deg_min = str(deg_min).strip()

            if len(deg_min) <= deg_len:
                return None

            degrees = int(deg_min[:deg_len])
            minutes = float(deg_min[deg_len:])

            decimal = degrees + minutes / 60.0

            if hemi in ("S", "W"):
                decimal = -decimal

            return decimal

        except Exception:
            return None
