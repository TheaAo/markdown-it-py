from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.metric_collection.build_mutant_catalog import (
    _absolute_source_lines,
    _catalog_payload,
    _coverage_source_lines,
    _dry_run_report,
    classify_workload_layer,
    derive_task_relevant_mutants,
)
from scripts.metric_collection.mutation_common import (
    build_collection_policy,
    catalog_hash,
    changed_lines_from_diff,
    collection_policy_hash,
    load_catalog,
)

MULTILINE_DIFF = """--- markdown_it/example.py
+++ markdown_it/example.py
@@ -2,4 +2,4 @@
-    first = value + 1
-    second = first * 2
+    first = value - 1
+    second = first / 2
     return second
"""


def _mutant(
    mutant_id: str, layer: str, reference_status: str = "no_tests"
) -> dict[str, Any]:
    return {
        "identity_schema": 3,
        "mutant_id": mutant_id,
        "mutant_name": f"example.calculate__mutmut_{mutant_id}",
        "module": "markdown_it/example.py",
        "function": "calculate",
        "source_line": 10,
        "changed_source_lines": [10, 11],
        "coverage_source_lines": [10, 11],
        "operator_family": "ARITHMETIC",
        "original_code": "first = value + 1",
        "mutated_code": "first = value - 1",
        "diff": MULTILINE_DIFF,
        "reference_status": reference_status,
        "covered_by_specified": layer == "specified",
        "covered_by_extended": layer in {"specified", "extended_only"},
        "workload_layer": layer,
        "mapping_status": "mapped",
        "review_status": "unreviewed",
        "review_notes": "",
    }


def _run(mutants: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "raw_mutants": mutants,
        "task_mutants": derive_task_relevant_mutants(mutants),
        "sut_hash": "sut-hash",
        "tool_version": "mutmut, version 3.7.0",
        "python_version": "3.11.6",
        "metadata": {
            "generated_mutants": len(mutants),
            "normalized_mutants": len(mutants),
            "normalization_failures": [],
            "mapping_failures": 0,
            "mapping_failure_rate": 0.0,
            "reference_status_counts": {"no_tests": len(mutants)},
            "task_relevant_mutants": len(derive_task_relevant_mutants(mutants)),
            "specified_mutants": sum(
                item["workload_layer"] == "specified" for item in mutants
            ),
            "extended_only_mutants": sum(
                item["workload_layer"] == "extended_only" for item in mutants
            ),
            "out_of_scope_mutants": sum(
                item["workload_layer"] == "out_of_scope" for item in mutants
            ),
            "coverage_membership_counts": {
                "specified_only": sum(
                    item["covered_by_specified"]
                    and not item["covered_by_extended"]
                    for item in mutants
                ),
                "extended_only": sum(
                    not item["covered_by_specified"]
                    and item["covered_by_extended"]
                    for item in mutants
                ),
                "both": sum(
                    item["covered_by_specified"]
                    and item["covered_by_extended"]
                    for item in mutants
                ),
                "neither": sum(
                    not item["covered_by_specified"]
                    and not item["covered_by_extended"]
                    for item in mutants
                ),
            },
            "operator_family_counts": {"ARITHMETIC": len(mutants)},
            "module_counts": {"markdown_it/example.py": len(mutants)},
            "function_counts": {"markdown_it/example.py::calculate": len(mutants)},
            "coverage": {"specified": {}, "extended": {}},
            "workload_hashes": {"specified": "s", "extended": "e"},
            "material_hashes": {"spec.md": "material"},
            "durations_seconds": {
                "specified_baseline": 1.0,
                "extended_baseline": 1.0,
                "reference_mutation_run": 10.0,
            },
        },
    }


def test_multiline_diff_maps_every_changed_line(tmp_path: Path) -> None:
    module = tmp_path / "markdown_it/example.py"
    module.parent.mkdir()
    module.write_text(
        "class Example:\n"
        "    def calculate(self, value):\n"
        "        first = value + 1\n"
        "        second = first * 2\n"
        "        return second\n",
        encoding="utf-8",
    )
    assert changed_lines_from_diff(MULTILINE_DIFF) == (2, 3)
    assert _absolute_source_lines(
        tmp_path,
        "markdown_it/example.py",
        "markdown_it.example.xǁExampleǁcalculate__mutmut_1",
        MULTILINE_DIFF,
    ) == (3, 4)


def test_multiline_statement_uses_coverage_statement_anchor(tmp_path: Path) -> None:
    module = tmp_path / "markdown_it/example.py"
    module.parent.mkdir()
    module.write_text(
        "def calculate(value):\n"
        "    return max(\n"
        "        value,\n"
        "        0,\n"
        "    )\n",
        encoding="utf-8",
    )
    assert _coverage_source_lines(
        tmp_path, "markdown_it/example.py", (3, 4)
    ) == (2,)


def test_specified_precedence_and_task_relevant_derivation() -> None:
    assert classify_workload_layer(True, True) == "specified"
    assert classify_workload_layer(False, True) == "extended_only"
    assert classify_workload_layer(False, False) == "out_of_scope"
    raw = [_mutant("M1", "specified"), _mutant("M2", "out_of_scope")]
    task = derive_task_relevant_mutants(raw)
    assert [item["mutant_id"] for item in task] == ["M1"]
    assert raw[0]["reference_status"] == "no_tests"
    assert len(task) + sum(
        item["workload_layer"] == "out_of_scope" for item in raw
    ) == len(raw)


def test_enriched_catalog_hash_covers_scope_but_not_timestamps() -> None:
    mutants = [_mutant("M1", "specified")]
    first = catalog_hash(mutants)
    payload = {"catalog_hash": first, "generated_at": "first", "mutants": mutants}
    payload["generated_at"] = "second"
    assert catalog_hash(payload["mutants"]) == first
    changed = deepcopy(mutants)
    changed[0]["covered_by_specified"] = False
    changed[0]["workload_layer"] = "extended_only"
    assert catalog_hash(changed) != first


def test_raw_catalog_accepts_out_of_scope_and_task_catalog_rejects_it(
    tmp_path: Path,
) -> None:
    mutant = _mutant("M1", "out_of_scope")
    path = tmp_path / "raw.json"
    path.write_text(
        json.dumps(
            {
                "catalog_kind": "full_sut_raw",
                "catalog_hash": catalog_hash([mutant]),
                "mutants": [mutant],
            }
        ),
        encoding="utf-8",
    )
    assert load_catalog(path)["mutants"][0]["reference_status"] == "no_tests"
    path.write_text(
        json.dumps(
            {
                "catalog_kind": "task_relevant_census",
                "catalog_hash": catalog_hash([mutant]),
                "mutants": [mutant],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid workload layer"):
        load_catalog(path)


def test_creation_mode_and_dry_run_checkpoint() -> None:
    run = _run([_mutant("M1", "specified"), _mutant("M2", "out_of_scope")])
    full = _catalog_payload(
        baseline_ref="origin/experiment-base",
        baseline_commit="base",
        only_mutate=[],
        run=run,
        mutants=run["raw_mutants"],
        catalog_kind="full_sut_raw",
    )
    pilot = _catalog_payload(
        baseline_ref="origin/experiment-base",
        baseline_commit="base",
        only_mutate=["markdown_it/example.py"],
        run=run,
        mutants=run["task_mutants"],
        catalog_kind="task_relevant_census",
    )
    report = _dry_run_report(run, "base")
    assert full["creation_mode"] == "full_sut"
    assert pilot["creation_mode"] == "only_mutate"
    assert report["estimated_participant_executions"] == 14
    assert report["checkpoint_status"] == "passed"


def test_collection_policy_hash_rejects_semantic_policy_change() -> None:
    catalog = _catalog_payload(
        baseline_ref="origin/experiment-base",
        baseline_commit="base",
        only_mutate=[],
        run=_run([_mutant("M1", "specified")]),
        mutants=[_mutant("M1", "specified")],
        catalog_kind="task_relevant_census",
    )
    policy = build_collection_policy(
        catalog,
        python_version="3.11.6",
        test_timeout=120.0,
        execution_timeout=None,
        timeout_multiplier=5.0,
        timeout_constant=0.5,
        confirm_kills=True,
        confirmation_max_children=4,
        exclude_duplicates=False,
    )
    changed = deepcopy(policy)
    changed["global_kill_confirmation"] = False
    assert collection_policy_hash(policy) != collection_policy_hash(changed)
