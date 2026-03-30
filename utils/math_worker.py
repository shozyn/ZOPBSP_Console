# calculation/math_worker.py
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Deque, Optional
import numpy as np
from scipy.io import wavfile
from Classifier.classifier1 import wav_to_si_cut, OUTPUT_CLASSES
from calculation.algorithms import (
    AKA1AAlgorithm,
    VMDv2Algorithm,
    TDOAAlgorithm,
    TDOAPositionAlgorithm,
)


#from Estymacja_Pozycji.Estymacja_Pozycji.tdoa_solver_31_03_2025 import position_estimation_TDOA_6

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
        self.algo_aka1a = AKA1AAlgorithm()
        self.algo_vmd = VMDv2Algorithm()
        self.algo_tdoa = TDOAAlgorithm()
        self.algo_pos = TDOAPositionAlgorithm()


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

    def _compute(self, job):
        items = list(job.wav_rpis.items())
        n = len(items)
        
        #n = 2 #! temp. change

        if n == 0:
            return {"job_id": job.job_id, "results": "No WAV files"}

        if n == 1:
            rid1, path1 = items[0]
            fs1, d1 = wavfile.read(path1)
            
            if d1.ndim == 2:
                d1 = d1.mean(axis=1)
            
            d1=d1.astype(np.int32)
            aka1a_res1 = self.algo_aka1a.run(*wav_to_si_cut(path1)[::-1])
            vmd_res1 = self.algo_vmd.run(d1, fs1)

            return {
                "job_id": job.job_id,
                "fs": [fs1],
                "receivers": [rid1],
                "AKA1A": [aka1a_res1],
                "VMDv2": [vmd_res1],
            }

        if n == 2:
            (rid1, path1), (rid2, path2) = items[0], items[1]
            fs1, d1 = wavfile.read(path1)
            fs2, d2 = wavfile.read(path2) #! Changed input

            if fs1 != fs2:
                raise ValueError(f"Sampling rate mismatch: {rid1}={fs1}, {rid1}={fs2}") #! rid1 and rid2

            d1=d1.astype(np.int32)
            d2=d2.astype(np.int32)

            aka1a_res1 = self.algo_aka1a.run(*wav_to_si_cut(path1)[::-1])
            aka1a_res2 = self.algo_aka1a.run(*wav_to_si_cut(path2)[::-1])
            vmd_res1 = self.algo_vmd.run(d1, fs1)
            vmd_res2 = self.algo_vmd.run(d2, fs2)
            
            # sample_duration = 10
            # x1 = np.array(d1[0:sample_duration*fs1], dtype=np.float64)
            # x2 = np.array(d2[0:sample_duration*fs2], dtype=np.float64)

            tdoa_res_1_2 = self.algo_tdoa.run(d1, d2, fs1)

            # TDOA_POS currently ignores tdoa_res and runs the developer synthetic demo,
            # but we still pass it so the interface is future-ready.
            pos_res_1_2 = self.algo_pos.run(tdoa_res_1_2)

            return {
                "job_id": job.job_id,
                "fs": [fs1,fs2],
                "receivers": [rid1, rid2], #! rid1 and rid2
                "AKA1A": [aka1a_res1,aka1a_res2],
                "VMDv2": [vmd_res1,vmd_res2],
                "TDOA": [tdoa_res_1_2],
                "TDOA_POS": [pos_res_1_2],
            }

        if n == 3:
            (rid1, path1), (rid2, path2), (rid3, path3) = items[0], items[1], items[2]
            fs1, d1 = wavfile.read(path1)
            fs2, d2 = wavfile.read(path2) #! Changed input
            fs3, d3 = wavfile.read(path3)

            if fs1 != fs2 or fs2 != fs3:
                raise ValueError(f"Sampling rate mismatch: {rid1}={fs1}, {rid2}={fs2}, {rid3}={fs3}") #! rid1 and rid2

            d1=d1.astype(np.int32)
            d2=d2.astype(np.int32)
            d3=d3.astype(np.int32)

            aka1a_res1 = self.algo_aka1a.run(*wav_to_si_cut(path1)[::-1])
            aka1a_res2 = self.algo_aka1a.run(*wav_to_si_cut(path2)[::-1])
            aka1a_res3 = self.algo_aka1a.run(*wav_to_si_cut(path3)[::-1])
            vmd_res1 = self.algo_vmd.run(d1, fs1)
            vmd_res2 = self.algo_vmd.run(d2, fs2)
            vmd_res3 = self.algo_vmd.run(d3, fs3)
            
            sample_duration = 10
            x1 = np.array(d1[0:sample_duration*fs1], dtype=np.float64)
            x2 = np.array(d2[0:sample_duration*fs2], dtype=np.float64)
            x3 = np.array(d3[0:sample_duration*fs3], dtype=np.float64)

            tdoa_res_1_2 = self.algo_tdoa.run(x1, x2, fs1)
            tdoa_res_2_3 = self.algo_tdoa.run(x2, x3, fs2)
            tdoa_res_3_1 = self.algo_tdoa.run(x3, x1, fs3)

            # TDOA_POS currently ignores tdoa_res and runs the developer synthetic demo,
            # but we still pass it so the interface is future-ready.
            pos_res_1_2 = self.algo_pos.run(tdoa_res_1_2)
            pos_res_2_3 = self.algo_pos.run(tdoa_res_2_3)
            pos_res_3_1 = self.algo_pos.run(tdoa_res_3_1)

            return {
                "job_id": job.job_id,
                "fs": [fs1,fs2,fs3],
                "receivers": [rid1, rid2,rid3], #! rid1 and rid2
                "AKA1A": [aka1a_res1,aka1a_res2,aka1a_res3],
                "VMDv2": [vmd_res1,vmd_res2,vmd_res3],
                "TDOA": [tdoa_res_1_2,tdoa_res_2_3,tdoa_res_3_1],
                "TDOA_POS": [pos_res_1_2,pos_res_2_3,pos_res_3_1],
            }

def start_calculation_thread(worker: CalculationWorker) -> QThread:

    th = QThread()
    worker.moveToThread(th)
    th.finished.connect(worker.deleteLater)
    th.finished.connect(th.deleteLater)
    th.start()
    logger.info("[CalculationWorker] Thread started (id=%s)", int(th.currentThreadId()))
    print("[CalculationWorker] Thread started")
    return th

def stop_calculation_thread(worker: CalculationWorker, thread: QThread, timeout_ms: int = 3000) -> bool:
    """
    Attempt graceful stop. Returns True if the thread stopped within timeout.
    If False, caller MUST keep references alive and retry / escalate.
    """
    try:
        worker.request_stop()
    except Exception:
        pass

    thread.quit()
    stopped = thread.wait(timeout_ms)  # blocks caller thread until finished or timeout :contentReference[oaicite:5]{index=5}
    if not stopped:
        logger.warning("[CalculationWorker] Thread did not stop within %d ms", timeout_ms)
    return stopped

@pyqtSlot()
def clear_pending(self):
    """
    Drop all jobs that are waiting in the queue.
    This does NOT interrupt a job that is currently executing.
    """
    self._queue.clear()
