from copy import deepcopy
import hashlib
from pathlib import Path
import sys

import pytest

from scripts.metric_collection_phase2.collect_coverage import (
    combine,
    measure,
    partition_pool,
    valid_pool,
)


def test_valid_pool_excludes_errors_and_rejects_changed_artifacts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "task.py"
    path.write_text("# original participant source\n")
    raw = {
        "metrics": {
            "artifact_sha256": {
                "task.py": hashlib.sha256(path.read_bytes()).hexdigest()
            },
            "valid_nodeids": ["task.py::test_ok[1]"],
            "case_level": {
                "test_cases": [
                    {"nodeid": "task.py::test_ok[1]", "classification": "valid"},
                    {
                        "nodeid": "task.py::test_ok[2]",
                        "classification": "function_error",
                    },
                ]
            },
        }
    }
    assert valid_pool(raw, tmp_path) == ["task.py::test_ok[1]"]
    inconsistent = deepcopy(raw)
    inconsistent["metrics"]["valid_nodeids"].append("task.py::test_ok[2]")
    with pytest.raises(ValueError, match="inconsistent"):
        valid_pool(inconsistent, tmp_path)
    path.write_text("# modified participant source\n")
    with pytest.raises(ValueError, match="Artifact changed"):
        valid_pool(raw, tmp_path)


def test_partition_preserves_relocation_parameters_and_extra_cases() -> None:
    nodeids = [
        "tests/test_cli.py::test_non_utf8",
        "tests/task/phase1/task.py::test_file[example]",
        "tests/task/phase1/task.py::test_parse_fail",
        "tests/task/task2.py::test_make_fence_at",
        "tests/task/task2.py::test_default_fence_exists",
    ]
    groups = partition_pool(nodeids)
    assert groups["maintenance"] == nodeids[:2]
    assert groups["retained_legacy"] == [nodeids[2]]
    assert groups["new_generation"] == [nodeids[3]]
    assert groups["additional"] == [nodeids[4]]
    assert sorted(nodeid for ids in groups.values() for nodeid in ids) == sorted(
        nodeids
    )


def test_combined_coverage_unions_arcs_across_original_snapshot_paths(
    tmp_path: Path,
) -> None:
    reports = []
    inputs = []
    for index, value in enumerate((True, False)):
        root = tmp_path / f"snapshot-{index}"
        (root / "markdown_it").mkdir(parents=True)
        (root / "markdown_it/__init__.py").write_text(
            "def choose(value):\n    if value:\n        return 1\n    return 2\n"
        )
        (root / "test_task.py").write_text(
            "from markdown_it import choose\n"
            f"def test_choose():\n    assert choose({value!r}) == {1 if value else 2}\n"
        )
        evidence = tmp_path / f"evidence-{index}"
        reports.append(
            measure(root, ["test_task.py::test_choose"], sys.executable, 30, evidence)
        )
        inputs.append(evidence / "coverage-data")
    union = combine(root, inputs, sys.executable, 30, tmp_path / "union")
    assert reports[0]["branch"]["covered"] == reports[1]["branch"]["covered"] == 1
    assert union["branch"]["covered"] == union["branch"]["total"] == 2
    assert union["statement"]["covered"] == union["statement"]["total"] == 4
    assert (tmp_path / "evidence-0/coverage-data").exists()
    assert (tmp_path / "evidence-1/coverage-data").exists()
