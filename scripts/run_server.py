"""
Resilient uvicorn runner.

- Restarts the server automatically on any unexpected exit.
- First Ctrl+C: restarts (treats it as accidental, e.g. VS Code auto-activation).
- Second Ctrl+C within 2 s: stops everything cleanly.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

_DOUBLE_CTRL_C_WINDOW = 2.0
_RESTART_DELAY = 2.0

_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER_ROOT = os.path.dirname(_HERE)
_UVICORN = os.path.join(_SERVER_ROOT, ".venv", "bin", "uvicorn")

_CMD = [
    _UVICORN,
    "app.main:app",
    "--host", "0.0.0.0",
    "--port", "8000",
    "--reload",
]


def main() -> None:
    last_ctrl_c: float = 0.0
    should_stop: bool = False
    proc: subprocess.Popen | None = None  # type: ignore[type-arg]

    def on_sigint(sig: int, frame: object) -> None:
        nonlocal last_ctrl_c, should_stop
        now = time.monotonic()
        if (now - last_ctrl_c) < _DOUBLE_CTRL_C_WINDOW:
            should_stop = True
            print("\n[watchdog] Stopping server...", flush=True)
            if proc is not None and proc.poll() is None:
                proc.terminate()
            sys.exit(0)
        last_ctrl_c = now
        print(
            f"\n[watchdog] Ctrl+C received — server will restart. "
            f"Press again within {_DOUBLE_CTRL_C_WINDOW:.0f}s to quit.",
            flush=True,
        )

    def on_exit(sig: int, frame: object) -> None:
        if proc is not None and proc.poll() is None:
            proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, on_sigint)
    signal.signal(signal.SIGTERM, on_exit)
    signal.signal(signal.SIGHUP, on_exit)

    while not should_stop:
        print("[watchdog] Starting uvicorn...", flush=True)
        proc = subprocess.Popen(_CMD, cwd=_SERVER_ROOT)
        proc.wait()

        if should_stop:
            break

        print(
            f"[watchdog] Server stopped — restarting in {_RESTART_DELAY:.0f}s. "
            "Press Ctrl+C again now to quit.",
            flush=True,
        )
        # Poll in short increments so a second Ctrl+C during the delay exits cleanly.
        deadline = time.monotonic() + _RESTART_DELAY
        while time.monotonic() < deadline and not should_stop:
            time.sleep(0.1)

    print("[watchdog] Server stopped.", flush=True)


if __name__ == "__main__":
    main()
