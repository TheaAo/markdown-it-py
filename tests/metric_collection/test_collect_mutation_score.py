from pathlib import Path

from scripts.metric_collection.collect_error_rates import TestCaseResult as CaseResult
from scripts.metric_collection.collect_mutation_score import (
    _catalog_summary,
    _copy_submission_resources,
    _result_execution_metadata,
    _test_review_rows,
    _write_config,
)


def test_test_review_rows_group_parameter_instances() -> None:
    results = [
        CaseResult("task.py::test_spec[a]", "test_spec", "valid", 0, "ok"),
        CaseResult("task.py::test_spec[b]", "test_spec", "function_error", 1, "failed"),
        CaseResult("task.py::test_file", "test_file", "valid", 0, "ok"),
    ]

    rows = _test_review_rows(results)

    assert rows == [
        {
            "source_test": "test_file",
            "classification": "unreviewed",
            "valid_generated_cases": 1,
            "invalid_generated_cases": 0,
            "review_notes": "",
        },
        {
            "source_test": "test_spec",
            "classification": "unreviewed",
            "valid_generated_cases": 1,
            "invalid_generated_cases": 1,
            "review_notes": "",
        },
    ]


def test_copy_submission_resources_preserves_relative_material_paths(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    task = repo / "tests/task/task.py"
    material = repo / "tests/task/materials/spec.md"
    material.parent.mkdir(parents=True)
    task.write_text("def test_example(): pass\n", encoding="utf-8")
    material.write_text("specification", encoding="utf-8")
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    _copy_submission_resources(repo, task, workspace)

    assert (workspace / "tests/task/task.py").is_file()
    assert (workspace / "tests/task/materials/spec.md").read_text() == "specification"


def test_census_summary_has_no_sampling_estimate() -> None:
    summary = _catalog_summary(
        {"catalog_kind": "task_relevant_census"},
        [
            {
                "status": "killed",
                "review_status": "unreviewed",
                "workload_layer": "specified",
            }
        ],
        exclude_duplicates=False,
    )
    assert summary["specified"]["mutation_score"] == 1.0
    assert "estimated_mutation_score" not in summary["specified"]


def test_mutmut_config_uses_fixed_timeout_policy(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        ["tests/task.py::test_example"],
        [],
        timeout_multiplier=5.0,
        timeout_constant=0.5,
    )
    config = (tmp_path / "setup.cfg").read_text(encoding="utf-8")
    assert "timeout_multiplier=5.0" in config
    assert "timeout_constant=0.5" in config


def test_reused_result_keeps_previous_metadata_over_empty_mutmut_placeholder() -> None:
    reused = {
        "duration_seconds": 1.2,
        "estimated_test_duration_seconds": 0.3,
        "exit_code": 0,
    }
    metadata = {
        "module.x_mutant": {
            "duration_seconds": None,
            "estimated_test_duration_seconds": None,
            "exit_code": None,
        }
    }

    selected = _result_execution_metadata(
        "M1",
        "module.x_mutant",
        rerun_ids=set(),
        execution_metadata=metadata,
        reused_row=reused,
    )

    assert selected == reused


def test_rerun_result_uses_new_execution_metadata() -> None:
    reused = {
        "duration_seconds": 1.2,
        "estimated_test_duration_seconds": 0.3,
        "exit_code": 0,
    }
    executed = {
        "duration_seconds": 2.4,
        "estimated_test_duration_seconds": 0.4,
        "exit_code": 1,
    }

    selected = _result_execution_metadata(
        "M1",
        "module.x_mutant",
        rerun_ids={"M1"},
        execution_metadata={"module.x_mutant": executed},
        reused_row=reused,
    )

    assert selected == executed
