from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from scripts.collect_execution_time import (
    TimedRun,
    _controlled_environment,
    _summarize,
    _timed_pytest,
)


def _measurement(index: int, seconds: float) -> TimedRun:
    return TimedRun(
        phase="measurement",
        index=index,
        elapsed_nanoseconds=int(seconds * 1_000_000_000),
        returncode=0,
        timed_out=False,
        failure_output=None,
    )


def test_summary_uses_median_as_execution_time() -> None:
    summary = _summarize(
        [_measurement(1, 1.0), _measurement(2, 2.0), _measurement(3, 9.0)]
    )

    assert summary.execution_time_seconds == 2.0
    assert summary.measurement_count == 3
    assert summary.minimum_seconds == 1.0
    assert summary.maximum_seconds == 9.0
    assert summary.median_absolute_deviation_seconds == 1.0
    assert summary.cv_review_threshold == 0.05
    assert summary.cv_review_required is True


def test_controlled_environment_removes_external_pytest_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYTEST_ADDOPTS", "--maxfail=1")
    monkeypatch.setenv("PYTHONHASHSEED", "random")

    environment = _controlled_environment()

    assert "PYTEST_ADDOPTS" not in environment
    assert environment["PYTHONHASHSEED"] == "0"


def test_timed_pytest_records_complete_process_duration(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    moments = iter((1_000_000_000, 3_500_000_000))
    monkeypatch.setattr(
        "scripts.collect_execution_time.time.perf_counter_ns", lambda: next(moments)
    )
    monkeypatch.setattr(
        "scripts.collect_execution_time.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, "passed"),
    )

    result = _timed_pytest(
        python_executable="python",
        repo_root=tmp_path,
        nodeids=["test_example.py::test_example"],
        timeout=10.0,
        phase="measurement",
        index=1,
    )

    assert result.elapsed_nanoseconds == 2_500_000_000
    assert result.elapsed_seconds == 2.5
    assert result.returncode == 0
    assert result.failure_output is None
