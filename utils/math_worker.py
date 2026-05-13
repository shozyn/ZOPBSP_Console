from __future__ import annotations

import logging
import time
from collections import deque
from typing import Deque, Optional
import numpy as np
from scipy.io import wavfile
from Classifier.classifier1 import wav_to_si_cut, OUTPUT_CLASSES
from calculation.algorithms import (
    AKA1AAlgorithm, ESTPOSAlgorithm
)

from PyQt5.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

from model.models import CalcJob

logger = logging.getLogger(__name__)

class CalculationWorker(QObject):
    job_started  = pyqtSignal(str)
    job_finished = pyqtSignal(str, dict)
    job_failed   = pyqtSignal(str, str)

    # NEW: emitted when the worker is ready for thread shutdown
    finished = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._queue: Deque[CalcJob] = deque()
        self._busy = False
        self._stopping = False
        self._finished_emitted = False

        self.algo_aka1a = AKA1AAlgorithm()
        self.algo_est_pos = ESTPOSAlgorithm()

    def _emit_finished_once(self) -> None:
        """
        Emit finished only once.
        This prevents duplicate thread.quit() calls and duplicate deleteLater()
        scheduling during repeated Stop clicks.
        """
        if self._finished_emitted:
            return

        self._finished_emitted = True
        logger.info("[CalculationWorker] finished emitted")
        self.finished.emit()

    @pyqtSlot()
    def stop(self) -> None:
        """
        Stop the worker from its own Qt thread.
        """
        logger.info(
            "[CalculationWorker] stop requested; busy=%s queue_size=%d",
            self._busy,
            len(self._queue),
        )

        self._stopping = True
        self._queue.clear()

        cancel = getattr(self.algo_est_pos, "cancel", None)
        if callable(cancel):
            try:
                cancel()
            except Exception:
                logger.exception("[CalculationWorker] Est_pos cancel failed")

        if not self._busy:
            self._emit_finished_once()

    @pyqtSlot()
    def request_stop(self) -> None:
        """
        Backward-compatible name.
        It is safer to route this to stop(), but still call it only via
        Qt queued connection.
        """
        self.stop()

    @pyqtSlot(object)
    def enqueue_job(self, job: CalcJob) -> None:
        if self._stopping:
            logger.info("[CalculationWorker] Ignoring job %s: stopping", job.job_id)
            return

        was_idle = not self._busy and not self._queue
        self._queue.append(job)

        logger.debug(
            "[CalculationWorker] Job enqueued: %s; queue_size=%d",
            job.job_id,
            len(self._queue),
        )

        if was_idle:
            QTimer.singleShot(0, self._get_job_from_queue)

    def _get_job_from_queue(self) -> None:
        if self._busy or not self._queue:
            return

        if self._stopping:
            logger.info("[CalculationWorker] Stop requested; no further jobs will be processed")
            self._queue.clear()
            self._emit_finished_once()
            return

        job = self._queue.popleft()
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

            if self._stopping:
                self._queue.clear()
                self._emit_finished_once()
                return

            if self._queue:
                QTimer.singleShot(0, self._get_job_from_queue)

    def _compute(self, job):
        wav_items = list(job.wav_rpis.items())
        gps_rpis = getattr(job, "gps_rpis", {})

        n = len(wav_items)

        if n == 0:
            return {
                "job_id": job.job_id,
                "results": "No WAV files",
                "gps_files": gps_rpis,
            }

        if n == 1:
            rid1, path1 = wav_items[0]
            fs1, s1 = wav_to_si_cut(path1)

            aka1a_res1 = self.algo_aka1a.run(s1,fs1)

            return {
                "job_id": job.job_id,
                "fs": [fs1],
                "receivers": [rid1],
                "gps_files": gps_rpis,
                "AKA1A": [aka1a_res1],
            }

        if n == 2:
            (rid1, path1), (rid2, path2) = wav_items[0], wav_items[1]
            fs1, s1 = wav_to_si_cut(path1)
            fs2, s2 = wav_to_si_cut(path2)

            aka1a_res1 = self.algo_aka1a.run(s1,fs1)
            aka1a_res2 = self.algo_aka1a.run(s2,fs2)

            return {
                "job_id": job.job_id,
                "fs": [fs1,fs2],
                "receivers": [rid1, rid2], #! rid1 and rid2
                "gps_files": gps_rpis,
                "AKA1A": [aka1a_res1,aka1a_res2],
            }

        if n == 3:
            (rid1, path1), (rid2, path2), (rid3, path3) = wav_items[0], wav_items[1], wav_items[2]
            fs1, s1 = wav_to_si_cut(path1)
            fs2, s2 = wav_to_si_cut(path2)
            fs3, s3 = wav_to_si_cut(path3)

            #est_pos_res = self.algo_est_pos.run(gps_rpis[rid1],gps_rpis[rid2],gps_rpis[rid2],path1,path2,path3)
            aka1a_res1 = self.algo_aka1a.run(s1,fs1)
            aka1a_res2 = self.algo_aka1a.run(s2,fs2)
            aka1a_res3 = self.algo_aka1a.run(s3,fs3)
            
            # ------------------------------------------------------------
            # Safe Est_pos localisation
            # ------------------------------------------------------------
            est_pos_res = []
            est_pos_status = "NOT_RUN"
            est_pos_error = ""

            missing_gps = [
                rid for rid in (rid1, rid2, rid3)
                if rid not in gps_rpis
            ]

            if missing_gps:
                est_pos_status = "FAILED"
                est_pos_error = f"Missing GPS files for receivers: {missing_gps}"
                logger.error(
                    "[CalculationWorker] Est_pos cannot run for job %s: %s",
                    job.job_id,
                    est_pos_error,
                )

            else:
                try:
                    est_pos_res = self.algo_est_pos.run(
                        gps_rpis[rid1],
                        gps_rpis[rid2],
                        gps_rpis[rid3],
                        path1,
                        path2,
                        path3,
                    )

                    est_pos_status = "OK"

                except Exception as e:
                    est_pos_res = []
                    est_pos_status = "FAILED"
                    est_pos_error = str(e)

                    logger.exception(
                        "[CalculationWorker] Est_pos failed for job %s. "
                        "The worker thread will continue with the next job.",
                        job.job_id,
                    )
            
            return {
                "job_id": job.job_id,
                "receivers": [rid1, rid2, rid3],
                "gps_files": gps_rpis,
                "AKA1A": [aka1a_res1, aka1a_res2, aka1a_res3],
                "Est_pos": est_pos_res,
                "Est_pos_status": est_pos_status,
                "Est_pos_error": est_pos_error,
            }

    @pyqtSlot()
    def clear_pending(self):
        """
        Drop all jobs that are waiting in the queue.
        This does NOT interrupt a job that is currently executing.
        """
        self._queue.clear()
        
def start_calculation_thread(worker: CalculationWorker) -> QThread:
    th = QThread()

    worker.moveToThread(th)

    # Worker decides when it is safe to stop the thread.
    worker.finished.connect(th.quit)

    # Delete objects after the event loop has stopped.
    th.finished.connect(worker.deleteLater)
    th.finished.connect(th.deleteLater)

    th.start()

    logger.info("[CalculationWorker] Thread started")

    return th

def stop_calculation_thread(worker: CalculationWorker, thread: QThread, timeout_ms: int = 3000) -> bool:
    """
    Deprecated compatibility wrapper.

    Do not directly call worker methods across threads.
    The controller should now use QMetaObject.invokeMethod(worker, "stop", ...).
    """
    logger.warning(
        "[CalculationWorker] stop_calculation_thread() is deprecated; "
        "use queued worker.stop() instead."
    )
    return False
