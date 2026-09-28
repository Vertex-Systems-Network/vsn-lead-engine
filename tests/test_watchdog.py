import sys

from vsn_lead_engine.watchdog import (
    WATCHDOG_TIMEOUT_EXIT_CODE,
    supervise_process,
)


def test_supervise_process_returns_child_exit_code():
    result=supervise_process(
        [sys.executable,"-c","import sys; sys.exit(7)"],
        timeout_seconds=2,
        kill_grace_seconds=0.1,
    )

    assert result["status"]=="child-exit"
    assert result["exit_code"]==7
    assert result["terminated"] is False
    assert result["killed"] is False


def test_supervise_process_times_out_blocked_child():
    result=supervise_process(
        [sys.executable,"-c","import time; time.sleep(5)"],
        timeout_seconds=0.05,
        kill_grace_seconds=0.2,
    )

    assert result["status"]=="watchdog-timeout"
    assert result["exit_code"]==WATCHDOG_TIMEOUT_EXIT_CODE
    assert result["terminated"] is True
    assert result["runtime_seconds"] < 2
