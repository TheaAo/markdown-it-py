from pathlib import Path
import subprocess
import sys

import pytest

from scripts.metric_collection_phase2 import collect_error_rates as collector
from scripts.metric_collection_phase2.collect_error_rates import (
    collect_submission,
    external_test_selectors,
    summarize,
)


def _checkout(tmp_path: Path) -> Path:
    root = tmp_path / "submission"
    (root / "markdown_it").mkdir(parents=True)
    (root / "markdown_it/__init__.py").write_text("# frozen test SUT\n")
    (root / "tests/task/phase1/materials").mkdir(parents=True)
    (root / "tests/task/phase1/materials/input.txt").write_text("expected")
    return root


def test_original_paths_parametrization_and_duplicate_names_are_preserved(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    (root / "tests/task/phase1/task.py").write_text("""\
from pathlib import Path
import pytest

@pytest.mark.parametrize("value", [1, 2])
def test_file(value):
    assert (Path(__file__).parent / "materials/input.txt").read_text() == "expected"
    assert value == 1

def test_wrong_old_path():
    Path("tests/task/materials/input.txt").read_text()
""")
    (root / "tests/task/task2.py").write_text("def test_file():\n    assert True\n")
    report = collect_submission(root, sys.executable, 30, tmp_path / "evidence")
    counts = report["case_level"]
    assert counts["total_generated_test_cases"] == 4
    assert counts["valid_test_count"] == 2
    assert counts["function_error_count"] == 1
    assert counts["runtime_error_count"] == 1
    assert counts["runtime_error_rate"] == 0.25
    assert len({case["nodeid"] for case in counts["test_cases"]}) == 4
    assert report["provenance"]["markdown_it_path"] == "markdown_it/__init__.py"
    assert report["missing_expected_tests"]["tests/task/task2.py"] == [
        "test_make_fence_after",
        "test_make_fence_at",
    ]


def test_collection_errors_do_not_hide_valid_tests_in_another_file(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    (root / "tests/task/phase1/task.py").write_text(
        "def test_broken():\n    assert (\n"
    )
    (root / "tests/task/task2.py").write_text("def test_good():\n    assert True\n")
    report = collect_submission(root, sys.executable, 30, tmp_path / "evidence")
    assert not report["suite_level"]["collectable"]
    assert report["case_level"]["syntax_error_count"] == 1
    assert report["case_level"]["valid_test_count"] == 1
    assert {case["count_basis"] for case in report["case_level"]["test_cases"]} == {
        "pytest_instance",
        "source_function_collection_fallback",
    }


def test_missing_tests_do_not_create_valid_cases_or_zero_error_rates(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    (root / "tests/task/task2.py").write_text("# test functions not implemented\n")
    report = collect_submission(root, sys.executable, 30, tmp_path / "evidence")
    assert report["case_level"]["total_generated_test_cases"] == 0
    assert report["case_level"]["runtime_error_rate"] is None
    assert report["case_level"]["overall_error_rate"] is None
    assert not report["valid_nodeids"]
    assert "tests/task/phase1/task.py" in report["missing_expected_tests"]


def test_empty_summary_has_no_available_rates() -> None:
    assert summarize([])["syntax_error_rate"] is None


def test_relocated_test_is_counted_without_unchanged_upstream_tests(
    tmp_path: Path,
) -> None:
    root = _checkout(tmp_path)
    (root / "tests/task/phase1/task.py").write_text(
        "# def test_parse_fail():\n# def test_non_utf8():\n"
    )
    (root / "tests/test_cli.py").write_text(
        "def test_upstream():\n    assert False\n\n"
        "def test_non_utf8():\n    assert True\n"
    )
    report = collect_submission(
        root,
        sys.executable,
        30,
        tmp_path / "evidence",
        {"tests/test_cli.py": ["test_non_utf8"]},
    )
    assert report["case_level"]["total_generated_test_cases"] == 1
    assert report["valid_nodeids"] == ["tests/test_cli.py::test_non_utf8"]
    assert (
        "test_non_utf8"
        not in report["missing_expected_tests"]["tests/task/phase1/task.py"]
    )
    assert (
        "test_parse_fail"
        in report["missing_expected_tests"]["tests/task/phase1/task.py"]
    )
    assert "tests/test_cli.py" in report["artifact_sha256"]


def test_external_selection_compares_functions_with_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _checkout(tmp_path)
    baseline_source = (
        "def test_unchanged():\n    assert True\n\n"
        "def test_changed():\n    assert False\n"
    )
    (root / "tests/test_cli.py").write_text(
        baseline_source.replace("assert False", "assert True")
        + "\ndef test_non_utf8():\n    assert True\n"
    )
    monkeypatch.setattr(collector, "_git", lambda *args: "tests/test_cli.py\n")
    monkeypatch.setattr(
        collector.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=0, stdout=baseline_source, stderr=""
        ),
    )
    assert external_test_selectors(root, "baseline", "submission", root) == {
        "tests/test_cli.py": ["test_changed", "test_non_utf8"]
    }
