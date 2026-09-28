from __future__ import annotations

import os
import signal
import subprocess
import time
from collections.abc import Sequence


WATCHDOG_TIMEOUT_EXIT_CODE = 124


def _signal_process_tree(process: subprocess.Popen, sig: signal.Signals) -> None:
    """Signal the supervised child and its descendants when possible."""
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, sig)
        elif sig == signal.SIGTERM:
            process.terminate()
        else:
            process.kill()
    except ProcessLookupError:
        return


def supervise_process(
    command: Sequence[str],
    *,
    timeout_seconds: float,
    kill_grace_seconds: float = 20,
) -> dict:
    """Run one production child behind a hard parent-process deadline.

    The engine's internal event budget remains the preferred graceful shutdown
    path. This outer watchdog exists for native/blocking calls that do not
    return control to Python in time for those in-process checks to run.
    """
    timeout_seconds = max(0.01, float(timeout_seconds))
    kill_grace_seconds = max(0.01, float(kill_grace_seconds))
    started = time.monotonic()
    process = subprocess.Popen(
        list(command),
        start_new_session=(os.name == "posix"),
    )
    terminated = False
    killed = False

    try:
        exit_code = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        terminated = True
        _signal_process_tree(process, signal.SIGTERM)
        try:
            process.wait(timeout=kill_grace_seconds)
        except subprocess.TimeoutExpired:
            killed = True
            _signal_process_tree(process, signal.SIGKILL)
            process.wait()
        return {
            "status": "watchdog-timeout",
            "exit_code": WATCHDOG_TIMEOUT_EXIT_CODE,
            "timeout_seconds": timeout_seconds,
            "kill_grace_seconds": kill_grace_seconds,
            "runtime_seconds": round(max(0.0, time.monotonic() - started), 3),
            "terminated": terminated,
            "killed": killed,
        }

    return {
        "status": "completed" if exit_code == 0 else "child-exit",
        "exit_code": int(exit_code),
        "timeout_seconds": timeout_seconds,
        "kill_grace_seconds": kill_grace_seconds,
        "runtime_seconds": round(max(0.0, time.monotonic() - started), 3),
        "terminated": terminated,
        "killed": killed,
    }
