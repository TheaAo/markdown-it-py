from dataclasses import asdict
import hashlib
from pathlib import Path
from typing import Any

import pytest

from scripts.metric_collection_phase1.collect_test_smells import (
    EXPECTED_TEST_FUNCTIONS,
    collect_test_smells,
)
from scripts.metric_collection_phase2.collect_test_smells import (
    collect_submission,
    summarize,
)


def make_input(checkout: Path) -> dict[str, Any]:
    declarations = {
        "tests/task/phase1/task.py": ["test_same", "test_invalid"],
        "tests/task/task2.py": ["test_same"],
    }
    hashes = {}
    for path, code in (
        (
            "tests/task/phase1/task.py",
            "def test_same():\n    pass\n\ndef test_invalid():\n    pass\n",
        ),
        ("tests/task/task2.py", "def test_same():\n    assert True\n"),
    ):
        destination = checkout / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(code)
        hashes[path] = hashlib.sha256(destination.read_bytes()).hexdigest()
    cases = [
        {
            "source_file": "tests/task/phase1/task.py",
            "source_test": "test_same",
            "classification": status,
            "nodeid": f"tests/task/phase1/task.py::test_same[{index}]",
        }
        for index, status in enumerate(("valid", "function_error"))
    ]
    cases.extend(
        [
            {
                "source_file": "tests/task/phase1/task.py",
                "source_test": "test_invalid",
                "classification": "runtime_error",
                "nodeid": "tests/task/phase1/task.py::test_invalid",
            },
            {
                "source_file": "tests/task/task2.py",
                "source_test": "test_same",
                "classification": "valid",
                "nodeid": "tests/task/task2.py::test_same",
            },
        ]
    )
    return {
        "metrics": {
            "source_test_declarations": declarations,
            "artifact_sha256": hashes,
            "case_level": {"test_cases": cases},
            "valid_nodeids": [
                case["nodeid"] for case in cases if case["classification"] == "valid"
            ],
            "missing_expected_tests": {},
        }
    }


def test_counts_functions_not_instances_and_preserves_file_identity(
    tmp_path: Path,
) -> None:
    raw = make_input(tmp_path)
    report = collect_submission(tmp_path, raw, evidence=tmp_path / "tools")
    summary = report["summary"]
    assert summary["total_source_tests"] == 3
    assert summary["eligible_test_count"] == 2
    assert summary["invalid_test_count"] == 1
    assert summary["partially_valid_test_count"] == 1
    assert summary["confirmed_pair_count"] == 1
    assert summary["test_smell_density"] == 1 / 14
    assert len({case["source_id"] for case in report["test_cases"]}) == 3
    partial = report["test_cases"][0]
    assert partial["validity"] == "partially_valid"
    assert partial["total_instance_count"] == 2
    assert (
        sum(group["confirmed_pair_count"] for group in report["by_task_group"].values())
        == 1
    )


def test_zero_valid_tests_are_unavailable_not_zero(tmp_path: Path) -> None:
    raw = make_input(tmp_path)
    for case in raw["metrics"]["case_level"]["test_cases"]:
        case["classification"] = "function_error"
    raw["metrics"]["valid_nodeids"] = []
    report = collect_submission(tmp_path, raw, evidence=tmp_path / "tools")
    assert report["summary"]["eligible_test_count"] == 0
    assert report["summary"]["test_smell_density"] is None
    assert report["summary"]["smelly_test_rate"] is None
    assert report["summary"]["confirmed_pair_count"] == 0


def test_changed_artifact_is_rejected(tmp_path: Path) -> None:
    raw = make_input(tmp_path)
    (tmp_path / "tests/task/task2.py").write_text("def test_same():\n    pass\n")
    with pytest.raises(ValueError, match="Artifact changed"):
        collect_submission(tmp_path, raw, evidence=tmp_path / "tools")


def test_default_phase1_scope_stays_identical(tmp_path: Path) -> None:
    path = tmp_path / "task.py"
    path.write_text("def test_file():\n    pass\n")
    errors = {
        "case_level": {
            "test_cases": [
                {
                    "source_test": "test_file",
                    "nodeid": "task.py::test_file",
                    "classification": "valid",
                }
            ]
        }
    }
    default = collect_test_smells(test_path=path, error_rates=errors)
    explicit = collect_test_smells(
        test_path=path, error_rates=errors, expected_tests=EXPECTED_TEST_FUNCTIONS
    )
    assert default == explicit
    assert default["total_source_tests"] == 5


def test_aggregate_preserves_uncertain_pairs_outside_numerator() -> None:
    from scripts.metric_collection_phase1.detect_test_smells_ast import (
        FORMAL_SMELLS,
        SmellDecision,
    )

    case = {
        "eligible": True,
        "validity": "fully_valid",
        "has_confirmed_smell": False,
        "smells": [
            asdict(SmellDecision(smell, "uncertain", [], "unresolved"))
            for smell in FORMAL_SMELLS
        ],
    }
    summary = summarize([case])
    assert summary["uncertain_pair_count"] == 7
    assert summary["test_smell_density"] == 0
    case["smells"] = case["smells"][:-1]
    with pytest.raises(ValueError, match="Missing or duplicate"):
        summarize([case])
