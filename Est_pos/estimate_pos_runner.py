from __future__ import annotations

import argparse
import faulthandler
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path


class Tee:
    """
    Write text simultaneously to several streams.

    We use it to duplicate child-process stdout/stderr:
        - to the normal pipe captured by the parent process;
        - to the persistent Est_pos session log file.
    """

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            try:
                stream.write(text)
                stream.flush()
            except Exception:
                pass

    def flush(self):
        for stream in self.streams:
            try:
                stream.flush()
            except Exception:
                pass


def _to_jsonable(value):
    """
    Convert NumPy/Python objects into JSON-serialisable structures.
    """
    try:
        import numpy as np
    except Exception:
        np = None

    if np is not None:
        if isinstance(value, np.generic):
            return value.item()

        if isinstance(value, np.ndarray):
            return value.tolist()

    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}

    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]

    return value


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safe subprocess wrapper for estimate_pos()."
    )

    parser.add_argument("--out", required=True)
    parser.add_argument("--session-log", required=True)
    parser.add_argument("--run-id", required=True)

    parser.add_argument("gps1_path")
    parser.add_argument("gps2_path")
    parser.add_argument("gps3_path")
    parser.add_argument("wav1_path")
    parser.add_argument("wav2_path")
    parser.add_argument("wav3_path")

    args = parser.parse_args()

    out_path = Path(args.out)
    session_log_path = Path(args.session_log)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    session_log_path.parent.mkdir(parents=True, exist_ok=True)

    # Line-buffered text log: useful when the child process crashes abruptly.
    with session_log_path.open("a", encoding="utf-8", errors="replace", buffering=1) as log_file:
        original_stdout = sys.stdout
        original_stderr = sys.stderr

        sys.stdout = Tee(original_stdout, log_file)
        sys.stderr = Tee(original_stderr, log_file)

        # If there is a segmentation fault / access violation, faulthandler
        # will try to write diagnostics into the same session log file.
        faulthandler.enable(file=log_file, all_threads=True)

        start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

        print("\n" + "=" * 90)
        print(f"[Est_pos child] RUN START: {args.run_id}")
        print(f"[Est_pos child] Time: {start_time}")
        print("[Est_pos child] Input files:")
        print(f"  gps1: {args.gps1_path}")
        print(f"  gps2: {args.gps2_path}")
        print(f"  gps3: {args.gps3_path}")
        print(f"  wav1: {args.wav1_path}")
        print(f"  wav2: {args.wav2_path}")
        print(f"  wav3: {args.wav3_path}")
        print("-" * 90)

        try:
            # Import only inside the child process.
            # This avoids loading pyproj/PROJ/Cython estimator code into the GUI process.
            from Est_pos.Estimator_pos import estimate_pos

            result = estimate_pos(
                args.gps1_path,
                args.gps2_path,
                args.gps3_path,
                args.wav1_path,
                args.wav2_path,
                args.wav3_path,
            )

            payload = {
                "ok": True,
                "result": _to_jsonable(result),
            }

            out_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            print("-" * 90)
            print(f"[Est_pos child] RUN OK: {args.run_id}")
            print(f"[Est_pos child] Result length: {len(result) if isinstance(result, list) else 'N/A'}")
            print(f"[Est_pos child] Output JSON: {out_path}")
            print("=" * 90)

            return 0

        except BaseException as e:
            tb = traceback.format_exc()

            payload = {
                "ok": False,
                "error": repr(e),
                "traceback": tb,
            }

            out_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            print("-" * 90, file=sys.stderr)
            print(f"[Est_pos child] RUN FAILED: {args.run_id}", file=sys.stderr)
            print(f"[Est_pos child] Error: {repr(e)}", file=sys.stderr)
            print("[Est_pos child] Traceback:", file=sys.stderr)
            print(tb, file=sys.stderr)
            print("=" * 90, file=sys.stderr)

            return 1


if __name__ == "__main__":
    sys.exit(main())