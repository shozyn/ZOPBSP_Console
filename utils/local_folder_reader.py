from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QTimer


class LocalFolderReader(QObject):
    """
    One-shot local replay:
      - scans disk folders once
      - emits files_arrived(receiver_id, role, files) in batches
    """

    files_arrived = pyqtSignal(str, str, list)  # (receiver_id, role, files)
    status = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, receiver_id, batch=400, parent=None):
        super().__init__(parent)
        self.receiver_id = receiver_id
        self.batch = max(1, int(batch))
        self._queue = []
        self._i = 0
        self._stopped = False

    @pyqtSlot(str, str)
    def start(self, hydro_dir, gps_dir):
        self._stopped = False
        self._queue = self._build_queue(hydro_dir, gps_dir)
        self._i = 0
        self.status.emit(f"[LocalFolderReader][{self.receiver_id}] emitting {sum(len(x[1]) for x in self._queue)} files")
        self._emit_next_batch()

    @pyqtSlot()
    def stop(self):
        self._stopped = True
        self.finished.emit()

    def _list_files(self, folder, pattern):
        p = Path(folder)
        if not p.exists():
            self.status.emit(f"[LocalFolderReader][{self.receiver_id}] missing folder: {p}")
            return []
        return [str(x) for x in sorted(p.glob(pattern), key=lambda z: z.name)]

    def _build_queue(self, hydro_dir, gps_dir):
        # Remote worker emits gps and hydro separately; we mirror that.
        gps_files = self._list_files(gps_dir, "*.txt")
        hydro_files = self._list_files(hydro_dir, "*.wav")

        queue = []
        if gps_files:
            queue.append(("gps", gps_files))
        if hydro_files:
            queue.append(("hydro", hydro_files))
        return queue

    def _emit_next_batch(self):
        if self._stopped:
            return

        if self._i >= len(self._queue):
            self.status.emit(f"[LocalFolderReader][{self.receiver_id}] done")
            self.finished.emit()
            return

        role, files = self._queue[self._i]

        # emit this role in chunks
        if not files:
            self._i += 1
            QTimer.singleShot(0, self._emit_next_batch)
            return

        chunk = files[:self.batch]
        rest = files[self.batch:]

        self.files_arrived.emit(self.receiver_id, role, chunk)

        # put remaining files back in the queue (same role)
        self._queue[self._i] = (role, rest)
        QTimer.singleShot(0, self._emit_next_batch)
