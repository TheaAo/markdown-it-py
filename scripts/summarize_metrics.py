from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any, Sequence


COMMON_COLUMNS = ("participant_number", "status")
ASSERTION_TEST_FUNCTIONS = (
    "test_file",
    "test_spec",
    "test_core_after",
    "test_parse_fail",
    "test_non_utf8",
)
ASSERTION_CLASSIFICATIONS = {
    "invalid",
    "non_trivial",
    "trivial",
    "assertionless",
    "uncertain",
}

ERROR_RATE_COLUMNS = (
    *COMMON_COLUMNS,
    "suite_collectable",
    "total_generated_test_cases",
    "valid_test_count",
    "syntax_error_count",
    "runtime_error_count",
    "function_error_count",
    "syntax_error_rate",
    "runtime_error_rate",
    "function_error_rate",
)

COVERAGE_COLUMNS = (
    *COMMON_COLUMNS,
    "valid_tests_included",
    "invalid_tests_excluded",
    "participant_statement_coverage",
    "participant_branch_coverage",
    "combined_statement_coverage",
    "combined_branch_coverage",
)

ASSERTION_SCORE_COLUMNS = (
    *COMMON_COLUMNS,
    "total_source_tests",
    "invalid_test_count",
    "non_trivial_test_count",
    "trivial_test_count",
    "assertionless_test_count",
    "uncertain_test_count",
    *ASSERTION_TEST_FUNCTIONS,
    "assertion_score",
)

CLASSIFICATIONS = (
    ("syntax_error", "syntax_error_count"),
    ("runtime_error", "runtime_error_count"),
    ("function_error", "function_error_count"),
    ("valid", "valid_test_count"),
)


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"manifest does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("manifest root must be a JSON object")
    if not isinstance(payload.get("participants"), list):
        raise ValueError("manifest must contain a participants array")
    return payload


def _required_int(mapping: dict[str, Any], field: str, context: str) -> int:
    value = mapping.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{context}.{field} must be a non-negative integer")
    return value


def _required_string(mapping: dict[str, Any], field: str, context: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}.{field} must be a non-empty string")
    return value


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def _error_rate_values(
    participant: dict[str, Any], context: str
) -> dict[str, Any]:
    summary = participant.get("summary")
    if not isinstance(summary, dict):
        raise ValueError(f"{context}.summary must be an object for collected data")
    total = _required_int(summary, "total_generated_test_cases", f"{context}.summary")
    counts = {
        count_field: _required_int(summary, count_field, f"{context}.summary")
        for _classification, count_field in CLASSIFICATIONS
    }
    classified_total = sum(counts.values())
    if classified_total != total:
        raise ValueError(
            f"{context} classified total {classified_total} does not equal {total}"
        )
    suite_collectable = summary.get("suite_collectable")
    if not isinstance(suite_collectable, bool):
        raise ValueError(f"{context}.summary.suite_collectable must be a boolean")
    return {
        "suite_collectable": suite_collectable,
        "total_generated_test_cases": total,
        **counts,
        "syntax_error_rate": _rate(counts["syntax_error_count"], total),
        "runtime_error_rate": _rate(counts["runtime_error_count"], total),
        "function_error_rate": _rate(counts["function_error_count"], total),
    }


def _coverage_scope_rate(
    coverage: dict[str, Any], scope_name: str, metric_name: str, context: str
) -> float | None:
    scope = coverage.get(scope_name)
    if scope is None and scope_name == "participant_tests_only":
        return None
    if not isinstance(scope, dict):
        raise ValueError(f"{context}.{scope_name} must be an object")
    metric = scope.get(metric_name)
    if not isinstance(metric, dict):
        raise ValueError(f"{context}.{scope_name}.{metric_name} must be an object")
    metric_context = f"{context}.{scope_name}.{metric_name}"
    covered = _required_int(metric, "covered", metric_context)
    total = _required_int(metric, "total", metric_context)
    if covered > total:
        raise ValueError(f"{metric_context}.covered exceeds total")
    return covered / total if total else 1.0


def _coverage_values(participant: dict[str, Any], context: str) -> dict[str, Any]:
    summary = participant.get("summary")
    assert isinstance(summary, dict)
    coverage = summary.get("coverage")
    if coverage is None:
        return {}
    if not isinstance(coverage, dict):
        raise ValueError(f"{context}.summary.coverage must be an object")
    coverage_context = f"{context}.summary.coverage"
    return {
        "valid_tests_included": _required_int(
            coverage, "valid_tests_included", coverage_context
        ),
        "invalid_tests_excluded": _required_int(
            coverage, "invalid_tests_excluded", coverage_context
        ),
        "participant_statement_coverage": _coverage_scope_rate(
            coverage, "participant_tests_only", "statement", coverage_context
        ),
        "participant_branch_coverage": _coverage_scope_rate(
            coverage, "participant_tests_only", "branch", coverage_context
        ),
        "combined_statement_coverage": _coverage_scope_rate(
            coverage, "all_tests_combined", "statement", coverage_context
        ),
        "combined_branch_coverage": _coverage_scope_rate(
            coverage, "all_tests_combined", "branch", coverage_context
        ),
    }


def _assertion_score_values(
    participant: dict[str, Any], context: str
) -> dict[str, Any]:
    summary = participant.get("summary")
    assert isinstance(summary, dict)
    assertion = summary.get("assertion_score")
    if assertion is None:
        raise ValueError(
            f"{context}.summary.assertion_score is missing; rerun "
            "collect_all_branches.py without --skip-coverage"
        )
    if not isinstance(assertion, dict):
        raise ValueError(f"{context}.summary.assertion_score must be an object")
    assertion_context = f"{context}.summary.assertion_score"
    count_fields = {
        "invalid": "invalid_test_count",
        "non_trivial": "non_trivial_test_count",
        "trivial": "trivial_test_count",
        "assertionless": "assertionless_test_count",
        "uncertain": "uncertain_test_count",
    }
    total = _required_int(assertion, "total_source_tests", assertion_context)
    eligible = _required_int(assertion, "eligible_test_count", assertion_context)
    counts = {
        csv_field: _required_int(assertion, source_field, assertion_context)
        for csv_field, source_field in count_fields.items()
    }
    classified_total = sum(counts.values())
    if classified_total != total:
        raise ValueError(
            f"{assertion_context} classified total {classified_total} "
            f"does not equal {total}"
        )
    expected_eligible = total - counts["invalid"]
    if eligible != expected_eligible:
        raise ValueError(
            f"{assertion_context}.eligible_test_count {eligible} does not equal "
            f"{expected_eligible}"
        )
    test_statuses = assertion.get("test_statuses")
    if not isinstance(test_statuses, dict):
        raise ValueError(f"{assertion_context}.test_statuses must be an object")
    statuses: dict[str, str] = {}
    for test_function in ASSERTION_TEST_FUNCTIONS:
        test_status = test_statuses.get(test_function)
        if test_status not in ASSERTION_CLASSIFICATIONS:
            raise ValueError(
                f"{assertion_context}.test_statuses.{test_function} "
                "must be a supported assertion classification"
            )
        statuses[test_function] = test_status
    return {
        "total_source_tests": total,
        **{
            source_field: counts[csv_field]
            for csv_field, source_field in count_fields.items()
        },
        **statuses,
        "assertion_score": (
            counts["non_trivial"] / eligible if eligible else None
        ),
    }


def _metric_rows(
    manifest: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    error_rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    assertion_rows: list[dict[str, Any]] = []
    seen_numbers: set[int] = set()

    for index, raw_participant in enumerate(manifest["participants"]):
        context = f"participants[{index}]"
        if not isinstance(raw_participant, dict):
            raise ValueError(f"{context} must be an object")
        participant_number = _required_int(
            raw_participant, "participant_number", context
        )
        if participant_number in seen_numbers:
            raise ValueError(f"duplicate participant number: {participant_number}")
        seen_numbers.add(participant_number)
        status = _required_string(raw_participant, "status", context)
        common = {"participant_number": participant_number, "status": status}
        error_row = dict(common)
        coverage_row = dict(common)
        assertion_row = dict(common)
        if status == "collected":
            error_row.update(_error_rate_values(raw_participant, context))
            coverage_row.update(_coverage_values(raw_participant, context))
            assertion_row.update(_assertion_score_values(raw_participant, context))
        error_rows.append(error_row)
        coverage_rows.append(coverage_row)
        assertion_rows.append(assertion_row)

    error_rows.sort(key=lambda item: item["participant_number"])
    coverage_rows.sort(key=lambda item: item["participant_number"])
    assertion_rows.sort(key=lambda item: item["participant_number"])
    return error_rows, coverage_rows, assertion_rows


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, float):
        return f"{value:.6f}"
    return value


def _write_csv(
    path: Path, columns: Sequence[str], rows: Sequence[dict[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    with temporary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _csv_value(row.get(column)) for column in columns})
    temporary_path.replace(path)


def summarize_metrics(manifest_path: Path, output_dir: Path) -> tuple[Path, Path, Path]:
    manifest = _read_manifest(manifest_path)
    error_rows, coverage_rows, assertion_rows = _metric_rows(manifest)
    error_rate_path = output_dir / "error_rates.csv"
    coverage_path = output_dir / "coverage.csv"
    assertion_score_path = output_dir / "assertion_score.csv"
    _write_csv(error_rate_path, ERROR_RATE_COLUMNS, error_rows)
    _write_csv(coverage_path, COVERAGE_COLUMNS, coverage_rows)
    _write_csv(assertion_score_path, ASSERTION_SCORE_COLUMNS, assertion_rows)
    return error_rate_path, coverage_path, assertion_score_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert collected metric JSON into focused CSV summary tables."
    )
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=Path("results/error_rates/collection_manifest.json"),
        help="Collection manifest generated by collect_all_branches.py.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/error_rates/summary"),
        help="Directory for focused metric CSV files.",
    )
    args = parser.parse_args(argv)

    try:
        error_rate_path, coverage_path, assertion_score_path = summarize_metrics(
            args.manifest.resolve(), args.output_dir.resolve()
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Wrote {error_rate_path}")
    print(f"Wrote {coverage_path}")
    print(f"Wrote {assertion_score_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
