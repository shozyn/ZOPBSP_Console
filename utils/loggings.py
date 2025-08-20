import logging, queue, os
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from typing import Optional
from collections import deque
from PyQt5.QtCore import QObject, pyqtSignal

class LoggingConfig:
    def __init__(
        self,
        file_path: str = "logs/app.log",
        file_level: str = "DEBUG",
        gui_level: str = "INFO",
        ring_capacity: int = 2000,
        rotate: bool = True,
        max_bytes: int = 5_000_000,
        backup_count: int = 5,
        fmt: str = "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt: str = "%Y-%m-%d %H:%M:%S",
    ):
        self.file_path = file_path
        self.file_level = file_level
        self.gui_level = gui_level
        self.ring_capacity = ring_capacity
        self.rotate = rotate
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.fmt = fmt
        self.datefmt = datefmt

class QtLogSignal(QObject):
    message = pyqtSignal(str)  # delivered on receiver's (GUI) thread

class GuiLogHandler(logging.Handler):
    """
    A logging handler that:
      - formats records to strings
      - keeps a ring buffer of the last N messages
      - emits each message to the GUI via a Qt signal
    """
    def __init__(self, capacity: int = 2000):
        super().__init__()
        self.signals = QtLogSignal()
        self._buffer = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            # Don't let a bad formatter kill GUI logging
            msg = record.getMessage()
        self._buffer.append(msg)
        self.signals.message.emit(msg)

    # Handy when the dock is created later or after you change filters
    def replay_to(self, sink_callable):
        for line in self._buffer:
            sink_callable(line)

def setup_logging_for_app(gui_append_slot, cfg: LoggingConfig) -> tuple[logging.Logger, QueueListener, GuiLogHandler]:
    """
    Creates a thread-safe logging pipeline:
      producers -> QueueHandler -> QueueListener -> [FileHandler, GuiLogHandler]
    """
    os.makedirs(os.path.dirname(cfg.file_path), exist_ok=True)

    q = queue.Queue()
    formatter = logging.Formatter(cfg.fmt, cfg.datefmt)

    # File handler (DEBUG to disk)
    if cfg.rotate:
        file_handler = RotatingFileHandler(
            cfg.file_path, maxBytes=cfg.max_bytes, backupCount=cfg.backup_count, encoding="utf-8"
        )
    else:
        file_handler = logging.FileHandler(cfg.file_path, encoding="utf-8")
    file_handler.setLevel(getattr(logging, cfg.file_level.upper(), logging.DEBUG))
    file_handler.setFormatter(formatter)

    # GUI handler (INFO+ to dock by default)
    gui_handler = GuiLogHandler(capacity=cfg.ring_capacity)
    gui_handler.setLevel(getattr(logging, cfg.gui_level.upper(), logging.INFO))
    gui_handler.setFormatter(formatter)
    gui_handler.signals.message.connect(gui_append_slot)

    # One listener thread fans out to both handlers
    listener = QueueListener(q, file_handler, gui_handler, respect_handler_level=True)
    listener.start()

    # Root logger writes into the queue
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # let handlers decide; or expose in config if needed
    root.handlers.clear()
    root.addHandler(QueueHandler(q))

    # Primer: dump any ring-buffered lines into the dock (useful on hot-reload of UI)
    gui_handler.replay_to(gui_append_slot)

    return root, listener, gui_handler

class QtLogSignal(QObject):
    message = pyqtSignal(str)  # delivered on receiver's (GUI) thread

class GuiLogHandler(logging.Handler):
    """
    A logging handler that:
      - formats records to strings
      - keeps a ring buffer of the last N messages
      - emits each message to the GUI via a Qt signal
    """
    def __init__(self, capacity: int = 2000):
        super().__init__()
        self.signals = QtLogSignal()
        self._buffer = deque(maxlen=capacity)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            # Don't let a bad formatter kill GUI logging
            msg = record.getMessage()
        self._buffer.append(msg)
        self.signals.message.emit(msg)

    # Handy when the dock is created later or after you change filters
    def replay_to(self, sink_callable):
        for line in self._buffer:
            sink_callable(line)