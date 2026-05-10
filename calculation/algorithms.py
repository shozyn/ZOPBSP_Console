from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import tempfile
from datetime import datetime
from pathlib import Path

from Classifier.AKA1A import AKA1A

logger = logging.getLogger(__name__)


# =============================================================================
# One Est_pos log file per console session
# =============================================================================

_ESTPOS_SESSION_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
_ESTPOS_LOG_DIR = Path("logs/estpos_subprocess")
_ESTPOS_LOG_DIR.mkdir(parents=True, exist_ok=True)

_ESTPOS_SESSION_LOG_PATH = _ESTPOS_LOG_DIR / f"estpos_session_{_ESTPOS_SESSION_ID}.log"
_ESTPOS_LOG_LOCK = threading.Lock()
_ESTPOS_HEADER_WRITTEN = False


def _append_estpos_session_log(text: str) -> None:
    """
    Append parent-process messages to the Est_pos session log.

    The child process also writes to the same file. Parent writes are short and
    occur before/after child execution.
    """
    with _ESTPOS_LOG_LOCK:
        with _ESTPOS_SESSION_LOG_PATH.open(
            "a",
            encoding="utf-8",
            errors="replace",
            buffering=1,
        ) as f:
            f.write(text)
            if not text.endswith("\n"):
                f.write("\n")


def _ensure_estpos_session_header() -> None:
    global _ESTPOS_HEADER_WRITTEN

    if _ESTPOS_HEADER_WRITTEN:
        return

    _append_estpos_session_log(
        "\n"
        + "#" * 100
        + "\n"
        + f"# EST_POS SESSION START\n"
        + f"# Session ID : {_ESTPOS_SESSION_ID}\n"
        + f"# Log file   : {_ESTPOS_SESSION_LOG_PATH.resolve()}\n"
        + f"# Python     : {sys.executable}\n"
        + f"# Started    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}\n"
        + "#" * 100
        + "\n"
    )

    _ESTPOS_HEADER_WRITTEN = True


class AKA1AAlgorithm:
    """
    Single-channel classifier.

    run(data, fs) -> dict
    """

    def run(self, data, fs):
        pred_class, class_prob = AKA1A(data, fs)
        return {
            "pred_class": int(pred_class),
            "class_prob": class_prob.tolist(),
        }


class EstPosError(RuntimeError):
    """
    Base error for failed position estimation.
    """


class EstPosProcessCrashed(EstPosError):
    """
    Raised when the child process died before producing a valid JSON result.
    """


class EstPosProcessFailed(EstPosError):
    """
    Raised when the child process finished but estimate_pos() raised
    a normal Python exception.
    """


class ESTPOSAlgorithm:
    """
    Safe wrapper around estimate_pos().

    A new child process is created for every localisation job. If pyproj/PROJ,
    QGIS DLLs, or Cython code crash, only the child process dies.
    The calculation worker thread remains alive and can process the next job.
    """

    def __init__(self, timeout_s: float = 180.0):
        self.timeout_s = float(timeout_s)
        _ensure_estpos_session_header()
        

    @property
    def session_log_path(self) -> Path:
        return _ESTPOS_SESSION_LOG_PATH

    def run(
        self,
        gps1_path,
        gps2_path,
        gps3_path,
        wav1_path,
        wav2_path,
        wav3_path,
    ):
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # JSON result can be temporary.
        # The diagnostic text goes to the persistent session log file.
        with tempfile.TemporaryDirectory(prefix="zopbsp_estpos_") as tmp_dir:
            tmp_dir = Path(tmp_dir)
            out_path = tmp_dir / "estpos_result.json"

            # algorithms.py is usually:
            #   <project_root>/calculation/algorithms.py
            project_root = Path(__file__).resolve().parents[1]

            cmd = [
                sys.executable,
                "-u",  # unbuffered child output
                "-m",
                "Est_pos.estimate_pos_runner",
                "--out",
                str(out_path),
                "--session-log",
                str(_ESTPOS_SESSION_LOG_PATH),
                "--run-id",
                run_id,
                str(gps1_path),
                str(gps2_path),
                str(gps3_path),
                str(wav1_path),
                str(wav2_path),
                str(wav3_path),
            ]

            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONFAULTHANDLER"] = "1"
            env["ZOPBSP_ESTPOS_SESSION_LOG"] = str(_ESTPOS_SESSION_LOG_PATH)

            _append_estpos_session_log(
                "\n"
                + "-" * 100
                + "\n"
                + f"[Est_pos parent] Starting run: {run_id}\n"
                + f"[Est_pos parent] Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')}\n"
                + f"[Est_pos parent] Command:\n  {' '.join(cmd)}\n"
                + f"[Est_pos parent] Working directory:\n  {project_root}\n"
                + "-" * 100
                + "\n"
            )

            logger.info(
                "[ESTPOSAlgorithm] Starting Est_pos subprocess. run_id=%s log=%s",
                run_id,
                _ESTPOS_SESSION_LOG_PATH,
            )

            try:
                completed = subprocess.run(
                    cmd,
                    cwd=str(project_root),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_s,
                )

            except subprocess.TimeoutExpired as e:
                _append_estpos_session_log(
                    "\n"
                    + f"[Est_pos parent] RUN TIMEOUT: {run_id}\n"
                    + f"[Est_pos parent] Timeout: {self.timeout_s:.1f} s\n"
                    + "-" * 100
                    + "\n"
                )

                raise EstPosProcessCrashed(
                    f"estimate_pos subprocess timeout after {self.timeout_s:.1f} s. "
                    f"Session log: {_ESTPOS_SESSION_LOG_PATH}"
                ) from e

            _append_estpos_session_log(
                "\n"
                + f"[Est_pos parent] Run finished: {run_id}\n"
                + f"[Est_pos parent] Return code: {completed.returncode}\n"
                + f"[Est_pos parent] JSON exists: {out_path.exists()}\n"
            )

            # If the child died before creating JSON, treat it as a native crash.
            if not out_path.exists():
                _append_estpos_session_log(
                    "\n"
                    + f"[Est_pos parent] RUN CRASHED BEFORE JSON OUTPUT: {run_id}\n"
                    + f"[Est_pos parent] Return code: {completed.returncode}\n"
                    + f"[Est_pos parent] Session log: {_ESTPOS_SESSION_LOG_PATH.resolve()}\n"
                    + "-" * 100
                    + "\n"
                )

                raise EstPosProcessCrashed(
                    "estimate_pos subprocess crashed before producing JSON output.\n"
                    f"Return code: {completed.returncode}\n"
                    f"Session log: {_ESTPOS_SESSION_LOG_PATH.resolve()}"
                )

            try:
                payload = json.loads(
                    out_path.read_text(encoding="utf-8", errors="replace")
                )

            except Exception as e:
                _append_estpos_session_log(
                    "\n"
                    + f"[Est_pos parent] INVALID JSON OUTPUT: {run_id}\n"
                    + f"[Est_pos parent] Result file: {out_path}\n"
                    + f"[Est_pos parent] Return code: {completed.returncode}\n"
                    + "-" * 100
                    + "\n"
                )

                raise EstPosProcessCrashed(
                    "estimate_pos subprocess produced invalid JSON output.\n"
                    f"Return code: {completed.returncode}\n"
                    f"Session log: {_ESTPOS_SESSION_LOG_PATH.resolve()}"
                ) from e

            if not payload.get("ok", False):
                _append_estpos_session_log(
                    "\n"
                    + f"[Est_pos parent] PYTHON FAILURE IN CHILD: {run_id}\n"
                    + f"[Est_pos parent] Error: {payload.get('error')}\n"
                    + f"[Est_pos parent] Traceback:\n{payload.get('traceback')}\n"
                    + "-" * 100
                    + "\n"
                )

                raise EstPosProcessFailed(
                    "estimate_pos failed with a Python exception in subprocess.\n"
                    f"Error: {payload.get('error')}\n"
                    f"Session log: {_ESTPOS_SESSION_LOG_PATH.resolve()}"
                )

            if completed.returncode != 0:
                _append_estpos_session_log(
                    "\n"
                    + f"[Est_pos parent] NON-ZERO RETURN CODE WITH OK PAYLOAD: {run_id}\n"
                    + f"[Est_pos parent] Return code: {completed.returncode}\n"
                    + "-" * 100
                    + "\n"
                )

                raise EstPosProcessCrashed(
                    "estimate_pos subprocess returned a non-zero code although "
                    "it produced an OK payload.\n"
                    f"Return code: {completed.returncode}\n"
                    f"Session log: {_ESTPOS_SESSION_LOG_PATH.resolve()}"
                )

            result = payload.get("result", [])

            _append_estpos_session_log(
                "\n"
                + f"[Est_pos parent] RUN OK: {run_id}\n"
                + f"[Est_pos parent] Result length: {len(result) if isinstance(result, list) else 'N/A'}\n"
                + "-" * 100
                + "\n"
            )

            logger.info(
                "[ESTPOSAlgorithm] Est_pos subprocess finished successfully. "
                "run_id=%s result_length=%s session_log=%s",
                run_id,
                len(result) if isinstance(result, list) else "N/A",
                _ESTPOS_SESSION_LOG_PATH,
            )

            return result