# calculation/math_worker.py
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Deque, Optional
import numpy as np
from scipy.io import wavfile

from Classifier.AKA1A import AKA1A

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

from model.models import CalcJob

logger = logging.getLogger(__name__)

class CalculationWorker(QObject):
    job_started  = pyqtSignal(str)
    job_finished = pyqtSignal(str, dict)
    job_failed   = pyqtSignal(str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._queue: Deque[CalcJob] = deque()
        self._busy = False
        self._stopping = False 

    @pyqtSlot()
    def request_stop(self) -> None:
        """
        Ask the worker to stop: no new drains will be scheduled after
        the current job. You may also choose to clear the queue here.
        """
        self._stopping = True
        # Optional policy: drop pending jobs
        # self._queue.clear()

    @pyqtSlot(object)
    def enqueue_job(self, job: CalcJob) -> None:
        if self._stopping:
            logger.info("[CalculationWorker] Ignoring job %s: stopping", job.job_id)
            return
        self._queue.append(job)
        for calc_job in self._queue:
            print(f"[CalculationWorker] queued job: {calc_job.job_id}")
        if not self._busy:
            QTimer.singleShot(0, self._get_job_from_queue)

    def _get_job_from_queue(self) -> None:
        if self._busy or not self._queue:
            return
        job = self._queue.popleft()
        print(f"Processed job:\n{job.job_id}\n")
        self._busy = True
        try:
            if self._stopping:
                logger.info("[CalculationWorker] Stop requested; skipping job %s", job.job_id)
                return
            self.job_started.emit(job.job_id)
            result = self._compute(job)
            self.job_finished.emit(job.job_id, result)
        except Exception as e:
            import traceback
            self.job_failed.emit(job.job_id, f"{e}\n{traceback.format_exc()}")
        finally:
            self._busy = False
            if self._queue and not self._stopping:
                QTimer.singleShot(0, self._get_job_from_queue)

    def _compute(self, job: CalcJob) -> dict:
        """
        long-running math → if possible, periodically check self._stopping
        and return early. For chunked or iterative algorithms, sprinkle:
            if self._stopping: raise RuntimeError("Cancelled")
        """

            #job_id: str           # use the ts_key as a unique id
            #wav_rpis: dict[str,str]

        print(f"job.job_id: {job.job_id}")
        print(f"job.wav_rpis:\n{job.wav_rpis}")

        for receiver_id, wav_path in job.wav_rpis.items():
            fs_i, data = wavfile.read(wav_path)          # fs_i: int, data: np.ndarray
            s_i = data.astype(np.int32)  
            pred_class, class_prob = AKA1A(s_i, fs_i)
            print(f"pred_class: {pred_class}")
            print(f"class_prob: {class_prob}")



        time.sleep(2.0)
        return {"x": 0.0, "y": 0.0}

def start_calculation_thread(worker: CalculationWorker) -> QThread:

    th = QThread()
    worker.moveToThread(th)
    th.finished.connect(worker.deleteLater)
    th.start()
    logger.info("[CalculationWorker] Thread started")
    print("[CalculationWorker] Thread started")
    return th

def stop_calculation_thread(worker: CalculationWorker, thread: QThread, timeout_ms: int = 3000) -> None:
    """
    Gracefully stop the worker's thread:
      1) ask the worker to stop (cooperative),
      2) quit the event loop,
      3) wait bounded time for clean shutdown.
    """
    try:
        worker.request_stop()
    except Exception:
        pass
    try:
        thread.quit()         # posts exit to the thread's event loop
        thread.wait(timeout_ms)
    finally:
        if thread.isRunning():
            # Last resort: forceful termination is discouraged; prefer cooperative stop.
            logger.warning("[CalculationWorker] Thread did not stop within %d ms", timeout_ms)
