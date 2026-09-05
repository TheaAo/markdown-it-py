from __future__ import annotations

import pytest

from scripts.collect_all_execution_times import _summary


def test_summary_preserves_primary_execution_time_name() -> None:
    report = {
        "status": "collected",
        "valid_tests_included": 10,
        "invalid_tests_excluded": 2,
        "summary": {
            "execution_time_seconds": 1.25,
            "measurement_count": 15,
        },
    }

    result = _summary(report)

    assert result["metric_status"] == "collected"
    assert result["execution_time"]["execution_time_seconds"] == 1.25


def test_summary_rejects_non_positive_execution_time() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        _summary(
            {
                "status": "collected",
                "valid_tests_included": 1,
                "invalid_tests_excluded": 0,
                "summary": {"execution_time_seconds": 0.0},
            }
        )


def test_summary_keeps_no_valid_tests_unavailable() -> None:
    result = _summary(
        {
            "status": "no_valid_tests",
            "valid_tests_included": 0,
            "invalid_tests_excluded": 5,
            "summary": None,
        }
    )

    assert result["metric_status"] == "no_valid_tests"
    assert result["execution_time"] is None
