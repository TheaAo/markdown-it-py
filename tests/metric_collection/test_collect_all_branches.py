from pathlib import Path

from scripts.collect_all_branches import (
    _assertion_score_summary,
    _branch_ref,
    _collect_branch,
    _coverage_summary,
    _protected_changes,
)


def test_branch_ref_uses_zero_padded_participant_number() -> None:
    assert _branch_ref("origin", "experiment-", 1) == "origin/experiment-01"
    assert _branch_ref("origin", "experiment-", 16) == "origin/experiment-16"


def test_protected_changes_detect_sut_and_configuration_files() -> None:
    changed_files = [
        "tests/task/task.py",
        "markdown_it/main.py",
        "pyproject.toml",
        "tox.ini",
    ]

    assert _protected_changes(changed_files) == [
        "markdown_it/main.py",
        "pyproject.toml",
        "tox.ini",
    ]


def test_non_participant_is_recorded_without_git_access(tmp_path: Path) -> None:
    record = _collect_branch(
        repo_root=tmp_path,
        collector_path=tmp_path / "collect_error_rates.py",
        python_executable=tmp_path / "python",
        baseline_ref="origin/experiment-base",
        baseline_commit="baseline",
        collector_commit="collector",
        remote="origin",
        branch_prefix="experiment-",
        participant_number=13,
        output_dir=tmp_path / "results",
        timeout=120,
        worktree_parent=tmp_path / "worktrees",
    )

    assert record["participant_id"] == "experiment-13"
    assert record["status"] == "not_participated"


def test_coverage_summary_uses_rates_from_covered_counts() -> None:
    summary = _coverage_summary(
        {
            "valid_tests_included": 4,
            "invalid_tests_excluded": 1,
            "participant_tests_only": {
                "statement": {"covered": 60, "total": 100, "percent": 60.0},
                "branch": {"covered": 20, "total": 50, "percent": 40.0},
            },
            "all_tests_combined": {
                "statement": {"covered": 90, "total": 100, "percent": 90.0},
                "branch": {"covered": 40, "total": 50, "percent": 80.0},
            },
        }
    )

    participant_scope = summary["participant_tests_only"]
    assert participant_scope["statement"]["rate"] == 0.6
    assert participant_scope["branch"]["rate"] == 0.4
    assert summary["all_tests_combined"]["statement"]["rate"] == 0.9


def test_assertion_score_summary_uses_valid_tests_as_denominator() -> None:
    summary = _assertion_score_summary(
        {
            "total_source_tests": 5,
            "invalid_test_count": 1,
            "eligible_test_count": 4,
            "non_trivial_test_count": 2,
            "trivial_test_count": 1,
            "assertionless_test_count": 0,
            "uncertain_test_count": 1,
            "test_cases": [
                {"source_test": "test_file", "classification": "non_trivial"},
                {"source_test": "test_spec", "classification": "non_trivial"},
                {"source_test": "test_core_after", "classification": "invalid"},
                {"source_test": "test_parse_fail", "classification": "trivial"},
                {"source_test": "test_non_utf8", "classification": "uncertain"},
            ],
        }
    )

    assert summary["score"] == 0.5
    assert summary["test_statuses"]["test_core_after"] == "invalid"
