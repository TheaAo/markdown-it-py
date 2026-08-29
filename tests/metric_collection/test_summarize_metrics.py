import csv
import json
from pathlib import Path

import pytest

from scripts.summarize_metrics import (
    ASSERTION_SCORE_COLUMNS,
    COVERAGE_COLUMNS,
    ERROR_RATE_COLUMNS,
    summarize_metrics,
)


def _write_manifest(path: Path, participants: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"participants": participants}), encoding="utf-8")


def _collected_participant(number: int) -> dict[str, object]:
    return {
        "participant_number": number,
        "participant_id": f"experiment-{number:02d}",
        "status": "collected",
        "summary": {
            "suite_collectable": False,
            "total_generated_test_cases": 5,
            "valid_test_count": 1,
            "syntax_error_count": 2,
            "runtime_error_count": 1,
            "function_error_count": 1,
            "coverage": {
                "valid_tests_included": 1,
                "invalid_tests_excluded": 4,
                "participant_tests_only": {
                    "statement": {"covered": 60, "total": 100, "rate": 0.6},
                    "branch": {"covered": 20, "total": 50, "rate": 0.4},
                },
                "all_tests_combined": {
                    "statement": {"covered": 90, "total": 100, "rate": 0.9},
                    "branch": {"covered": 40, "total": 50, "rate": 0.8},
                },
            },
            "assertion_score": {
                "total_source_tests": 5,
                "invalid_test_count": 4,
                "eligible_test_count": 1,
                "non_trivial_test_count": 1,
                "trivial_test_count": 0,
                "assertionless_test_count": 0,
                "uncertain_test_count": 0,
                "score": 1.0,
                "test_statuses": {
                    "test_file": "non_trivial",
                    "test_spec": "invalid",
                    "test_core_after": "invalid",
                    "test_parse_fail": "invalid",
                    "test_non_utf8": "invalid",
                },
            },
        },
    }


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def test_summary_writes_separate_focused_metric_tables(tmp_path: Path) -> None:
    manifest_path = tmp_path / "collection_manifest.json"
    _write_manifest(
        manifest_path,
        [
            {
                "participant_number": 13,
                "participant_id": "experiment-13",
                "status": "not_participated",
            },
            _collected_participant(2),
        ],
    )

    error_rate_path, coverage_path, assertion_score_path = summarize_metrics(
        manifest_path, tmp_path / "summary"
    )

    error_columns, error_rows = _read_rows(error_rate_path)
    assert error_columns == list(ERROR_RATE_COLUMNS)
    assert [row["participant_number"] for row in error_rows] == ["2", "13"]
    assert "participant_id" not in error_columns
    assert "included_in_analysis" not in error_columns
    assert "participant_commit" not in error_columns
    assert error_rows[0]["syntax_error_count"] == "2"
    assert error_rows[0]["syntax_error_rate"] == "0.400000"
    assert error_rows[1]["status"] == "not_participated"
    assert error_rows[1]["total_generated_test_cases"] == ""

    coverage_columns, coverage_rows = _read_rows(coverage_path)
    assert coverage_columns == list(COVERAGE_COLUMNS)
    assert [row["participant_number"] for row in coverage_rows] == ["2", "13"]
    assert coverage_rows[0]["participant_statement_coverage"] == "0.600000"
    assert coverage_rows[0]["combined_branch_coverage"] == "0.800000"
    assert coverage_rows[1]["participant_statement_coverage"] == ""

    assertion_columns, assertion_rows = _read_rows(assertion_score_path)
    assert assertion_columns == list(ASSERTION_SCORE_COLUMNS)
    assert [row["participant_number"] for row in assertion_rows] == ["2", "13"]
    assert assertion_rows[0]["total_source_tests"] == "5"
    assert "eligible_test_count" not in assertion_columns
    assert assertion_rows[0]["invalid_test_count"] == "4"
    assert assertion_rows[0]["non_trivial_test_count"] == "1"
    assert assertion_rows[0]["test_file"] == "non_trivial"
    assert assertion_rows[0]["test_spec"] == "invalid"
    assert assertion_rows[0]["assertion_score"] == "1.000000"
    assert assertion_rows[1]["assertion_score"] == ""


def test_summary_keeps_coverage_empty_for_old_manifest(tmp_path: Path) -> None:
    participant = _collected_participant(1)
    summary = participant["summary"]
    assert isinstance(summary, dict)
    summary.pop("coverage")
    manifest_path = tmp_path / "collection_manifest.json"
    _write_manifest(manifest_path, [participant])

    _error_rate_path, coverage_path, _assertion_score_path = summarize_metrics(
        manifest_path, tmp_path / "summary"
    )

    _columns, rows = _read_rows(coverage_path)
    assert rows[0]["status"] == "collected"
    assert rows[0]["valid_tests_included"] == ""


def test_summary_rejects_missing_assertion_score(tmp_path: Path) -> None:
    participant = _collected_participant(1)
    summary = participant["summary"]
    assert isinstance(summary, dict)
    summary.pop("assertion_score")
    manifest_path = tmp_path / "collection_manifest.json"
    _write_manifest(manifest_path, [participant])

    with pytest.raises(
        ValueError,
        match=r"assertion_score is missing; rerun collect_all_branches.py",
    ):
        summarize_metrics(manifest_path, tmp_path / "summary")


def test_summary_rejects_inconsistent_classification_total(tmp_path: Path) -> None:
    participant = _collected_participant(1)
    summary = participant["summary"]
    assert isinstance(summary, dict)
    summary["runtime_error_count"] = 2
    manifest_path = tmp_path / "collection_manifest.json"
    _write_manifest(manifest_path, [participant])

    with pytest.raises(ValueError, match="classified total 6 does not equal 5"):
        summarize_metrics(manifest_path, tmp_path / "summary")
