import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.metric_collection_phase2.collect_assertion_score import (
    apply_reviews,
    collect_submission,
    summarize,
)


def _raw(
    root: Path, declarations: dict[str, list[str]], cases: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "metrics": {
            "artifact_sha256": {
                path: hashlib.sha256((root / path).read_bytes()).hexdigest()
                for path in declarations
            },
            "source_test_declarations": declarations,
            "case_level": {"test_cases": cases},
            "valid_nodeids": [
                case["nodeid"] for case in cases if case["classification"] == "valid"
            ],
            "missing_expected_tests": {
                "tests/task/phase1/task.py": ["test_parse_fail"]
            },
        }
    }


def _case(
    path: str, name: str, classification: str, parameter: str = ""
) -> dict[str, Any]:
    return {
        "source_file": path,
        "source_test": name,
        "nodeid": f"{path}::{name}{parameter}",
        "classification": classification,
        "returncode": int(classification != "valid"),
        "reason": "fixture classification",
    }


def test_source_identity_partial_validity_relocation_and_upstream_exclusion(
    tmp_path: Path,
) -> None:
    sources = {
        "tests/task/phase1/task.py": (
            "from markdown_it import MarkdownIt\n"
            "def test_shared(value):\n    assert MarkdownIt().render(value) == 'expected'\n"
            "# def test_parse_fail():\n"
        ),
        "tests/task/task2.py": "def test_shared():\n    assert True\n",
        "tests/test_cli.py": (
            "from markdown_it import MarkdownIt\n"
            "def test_upstream():\n    assert False\n"
            "def test_non_utf8():\n    assert MarkdownIt().render('x') == 'expected'\n"
        ),
    }
    for relative, source in sources.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    declarations = {
        path: ["test_non_utf8" if path.endswith("test_cli.py") else "test_shared"]
        for path in sources
    }
    cases = [
        _case("tests/task/phase1/task.py", "test_shared", "valid", "[1]"),
        _case("tests/task/phase1/task.py", "test_shared", "function_error", "[2]"),
        _case("tests/task/task2.py", "test_shared", "valid"),
        _case("tests/test_cli.py", "test_non_utf8", "valid"),
    ]
    report = collect_submission(tmp_path, _raw(tmp_path, declarations, cases))
    summary = report["summary"]
    assert summary["total_source_tests"] == summary["eligible_test_count"] == 3
    assert summary["partially_valid_test_count"] == 1
    assert summary["non_trivial_test_count"] == 2
    assert summary["trivial_test_count"] == 1
    assert summary["assertion_score"] == pytest.approx(2 / 3)
    assert len({case["source_id"] for case in report["test_cases"]}) == 3
    partial = report["test_cases"][0]
    assert partial["valid_instance_count"] == 1
    assert partial["total_instance_count"] == 2
    assert partial["validity"] == "partially_valid"
    assert report["by_task_group"]["maintenance"]["eligible_test_count"] == 1
    assert all(case["source_test"] != "test_upstream" for case in report["test_cases"])
    assert report["missing_expected_tests"]["tests/task/phase1/task.py"] == [
        "test_parse_fail"
    ]


def test_invalid_source_and_empty_scope_have_unavailable_scores(tmp_path: Path) -> None:
    relative = "tests/task/task2.py"
    path = tmp_path / relative
    path.parent.mkdir(parents=True)
    path.write_text("def test_broken():\n    assert False\n")
    report = collect_submission(
        tmp_path,
        _raw(
            tmp_path,
            {relative: ["test_broken"]},
            [_case(relative, "test_broken", "function_error")],
        ),
    )
    assert report["summary"]["invalid_test_count"] == 1
    assert report["summary"]["eligible_test_count"] == 0
    assert report["summary"]["assertion_score"] is None
    assert summarize([])["assertion_score"] is None


def test_review_export_preserves_automatic_evidence_and_checks_commit(
    tmp_path: Path,
) -> None:
    case = {
        "source_id": "task.py::test_order",
        "classification": "uncertain",
        "validity": "fully_valid",
    }
    raw = tmp_path / "raw.json"
    raw.write_text(json.dumps({"metrics": {"test_cases": [case]}}))
    manifest = {
        "participants": [
            {
                "participant_number": 3,
                "participant_commit": "frozen",
                "status": "collected",
                "output_file": "raw.json",
                "summary": summarize([case]),
            }
        ]
    }
    decision = {
        "participant_number": 3,
        "participant_commit": "frozen",
        "source_id": case["source_id"],
        "automated_classification": "uncertain",
        "reviewed_classification": "non_trivial",
    }
    reviews = tmp_path / "reviews.json"
    reviews.write_text(json.dumps({"reviews": [decision]}))
    apply_reviews(manifest, tmp_path, reviews)
    row = manifest["participants"][0]
    assert row["summary"]["assertion_score"] == 0
    assert row["final_summary"]["assertion_score"] == 1
    assert (
        json.loads(raw.read_text())["metrics"]["test_cases"][0]["classification"]
        == "uncertain"
    )
    decision["participant_commit"] = "different"
    reviews.write_text(json.dumps({"reviews": [decision]}))
    with pytest.raises(ValueError, match="different participant commit"):
        apply_reviews(manifest, tmp_path, reviews)
