from scripts.collect_coverage import (
    CoverageMetric,
    CoverageReport,
    CoverageScope,
    _metric,
    _metrics_from_coverage_json,
    _print_report,
    _report_payload,
)


def test_metric_percentage() -> None:
    metric = _metric(covered=3, total=4)

    assert metric.covered == 3
    assert metric.total == 4
    assert metric.percent == 75.0


def test_metric_with_no_measurable_items() -> None:
    assert _metric(covered=0, total=0).percent == 100.0


def test_metrics_from_coverage_json() -> None:
    statement, branch = _metrics_from_coverage_json(
        {
            "totals": {
                "covered_lines": 80,
                "num_statements": 100,
                "covered_branches": 30,
                "num_branches": 50,
            }
        }
    )

    assert statement.percent == 80.0
    assert branch.percent == 60.0


def test_report_distinguishes_the_two_coverage_scopes(capsys) -> None:
    report = CoverageReport(
        test_path="tests/task/task.py",
        source="markdown_it",
        valid_tests_included=5,
        invalid_tests_excluded=1,
        participant_tests_only=CoverageScope(
            statement=CoverageMetric(covered=60, total=100, percent=60.0),
            branch=CoverageMetric(covered=20, total=50, percent=40.0),
        ),
        all_tests_combined=CoverageScope(
            statement=CoverageMetric(covered=90, total=100, percent=90.0),
            branch=CoverageMetric(covered=40, total=50, percent=80.0),
        ),
    )

    _print_report(report)

    output = capsys.readouterr().out
    assert "Participant tests only" in output
    assert "Statement coverage: 60.00%" in output
    assert "All tests combined" in output
    assert "Statement coverage: 90.00%" in output


def test_json_payload_separates_error_rates_and_coverage() -> None:
    report = CoverageReport(
        test_path="tests/task/task.py",
        source="markdown_it",
        valid_tests_included=0,
        invalid_tests_excluded=1,
        participant_tests_only=None,
        all_tests_combined=CoverageScope(
            statement=CoverageMetric(covered=90, total=100, percent=90.0),
            branch=CoverageMetric(covered=40, total=50, percent=80.0),
        ),
    )

    payload = _report_payload(report)

    assert payload["error_rates"] is None
    assert payload["assertion_score"] is None
    assert payload["coverage"]["valid_tests_included"] == 0
    assert payload["coverage"]["all_tests_combined"]["statement"]["covered"] == 90
