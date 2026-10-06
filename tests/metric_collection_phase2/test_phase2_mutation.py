import json
from pathlib import Path

import pytest

from scripts.metric_collection_phase1.build_mutant_catalog import _absolute_source_lines
from scripts.metric_collection_phase1.collect_error_rates import TestCaseResult as Case
from scripts.metric_collection_phase1.collect_mutation_score import (
    _original_valid_nodeids,
)
from scripts.metric_collection_phase1.mutation_common import catalog_hash
from scripts.metric_collection_phase2.collect_error_rates import PARTICIPANTS
from scripts.metric_collection_phase2.collect_mutation_score import pilot_catalog
from scripts.metric_collection_phase2.finalize_mutation_score import (
    validate_completion,
    validate_unresolved_exclusions,
)


def test_original_pool_preserves_file_identity_and_rejects_missing_or_extra_cases(
    tmp_path: Path,
) -> None:
    first = "tests/task/phase1/task.py::test_shared[1]"
    second = "tests/test_cli.py::test_shared"
    for relative in (first.split("::")[0], second.split("::")[0]):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("def test_shared():\n    assert True\n")
    results = [
        Case(
            nodeid=node,
            source_test="test_shared",
            classification="valid",
            returncode=0,
            reason="passed",
        )
        for node in (first, second)
    ]
    pool = tmp_path / "pool.json"
    pool.write_text(json.dumps([first, second]))
    assert _original_valid_nodeids(pool, tmp_path, results) == [first, second]
    pool.write_text(json.dumps([first]))
    with pytest.raises(ValueError, match="classified valid pool"):
        _original_valid_nodeids(pool, tmp_path, results)
    pool.write_text(json.dumps([first, second, second]))
    with pytest.raises(ValueError, match="classified valid pool"):
        _original_valid_nodeids(pool, tmp_path, results)


def test_pilot_is_reproducible_and_not_a_formal_catalog() -> None:
    mutants = [
        {
            "mutant_id": f"id-{i}",
            "module": f"module-{i % 2}",
            "operator_family": "COMPARISON",
            "mutant_name": f"name-{i}",
            "function": "function",
            "source_line": i + 1,
            "diff": "--- old\n+++ new\n@@ -1 +1 @@\n-True\n+False\n",
        }
        for i in range(10)
    ]
    catalog = {"mutants": mutants, "catalog_hash": "parent"}
    pilot = pilot_catalog(catalog, 4)
    assert pilot == pilot_catalog({**catalog, "mutants": list(reversed(mutants))}, 4)
    assert len(pilot["mutants"]) == 4
    assert len({item["module"] for item in pilot["mutants"]}) == 2
    assert pilot["catalog_hash"] == catalog_hash(pilot["mutants"])
    assert pilot["catalog_kind"] == "phase2_execution_pilot"
    assert pilot["parent_catalog_hash"] == "parent"
    assert len(catalog["mutants"]) == 10


@pytest.mark.parametrize(
    "invalid",
    [
        "pilot",
        "partial_cohort",
        "duplicate_participant",
        "failed_participant",
        "mixed_sut",
    ],
)
def test_finalization_rejects_incomplete_or_incompatible_execution(
    invalid: str,
) -> None:
    catalog = {
        "catalog_hash": "catalog",
        "sut_hash": "sut",
        "baseline_commit": "baseline",
    }
    manifest = {
        **catalog,
        "stage": "formal_execution",
        "status": "executions_complete",
        "participants": [
            {"participant_number": number, "status": "collected"}
            for number in PARTICIPANTS
        ],
    }
    validate_completion(manifest, catalog)
    if invalid == "pilot":
        manifest["stage"] = "pilot"
    elif invalid == "partial_cohort":
        manifest["participants"].pop()
    elif invalid == "duplicate_participant":
        manifest["participants"][-1]["participant_number"] = PARTICIPANTS[0]
    elif invalid == "failed_participant":
        manifest["participants"][-1]["status"] = "collection_failed"
    else:
        manifest["sut_hash"] = "different-sut"
    with pytest.raises(ValueError):
        validate_completion(manifest, catalog)


def test_unresolved_exclusion_requires_timeout_for_the_entire_cohort() -> None:
    participants = {f"experiment-{number:02d}" for number in PARTICIPANTS}
    statuses = dict.fromkeys(participants, "timeout")
    outcomes = {
        "execution_unresolved": [{"mutant_id": "loop"}],
        "participant_matrix": {"loop": statuses},
    }
    validate_unresolved_exclusions(outcomes, participants)
    statuses["experiment-02"] = "suspicious"
    with pytest.raises(ValueError, match="all-participant timeouts"):
        validate_unresolved_exclusions(outcomes, participants)
    statuses.pop("experiment-02")
    with pytest.raises(ValueError, match="all-participant timeouts"):
        validate_unresolved_exclusions(outcomes, participants)


@pytest.mark.parametrize(
    ("source", "name", "diff", "expected"),
    [
        (
            "import math\n\n# A rule\n\ndef calculate(value):\n    return value + 1\n",
            "markdown_it.example.x_calculate__mutmut_1",
            "@@ -1,4 +1,4 @@\n # A rule\n\n def calculate(value):\n-    return value + 1\n+    return value - 1\n",
            (6,),
        ),
        (
            "from typing import overload\n\nclass Example:\n    @overload\n    def calculate(self, value: int) -> int: ...\n\n    def calculate(self, value):\n        return value + 1\n",
            "markdown_it.example.xǁExampleǁcalculate__mutmut_1",
            "@@ -1,2 +1,2 @@\n def calculate(self, value):\n-    return value + 1\n+    return value - 1\n",
            (8,),
        ),
    ],
)
def test_mutmut_function_diff_maps_to_verified_source(
    tmp_path: Path, source: str, name: str, diff: str, expected: tuple[int, ...]
) -> None:
    path = tmp_path / "markdown_it/example.py"
    path.parent.mkdir()
    path.write_text(source)
    assert (
        _absolute_source_lines(tmp_path, "markdown_it/example.py", name, diff)
        == expected
    )
    with pytest.raises(ValueError, match="align mutant diff"):
        _absolute_source_lines(
            tmp_path,
            "markdown_it/example.py",
            name,
            diff.replace("value + 1", "other + 1"),
        )


def test_semantic_patch_preserves_method_docstring_indentation() -> None:
    from scripts.metric_collection_phase2.probe_mutant_semantics import patch_source

    source = 'class Example:\n    def value(self):\n        """Doc.\n            detail\n        """\n        result = ""\n        return result\n'
    diff = '@@ -2,5 +2,5 @@\n         """Doc.\n             detail\n         """\n-    result = ""\n+    result = "XXXX"\n     return result\n'
    changed = patch_source(source, diff, 6)
    assert '        result = "XXXX"' in changed
    assert "            detail" in changed


def test_semantic_patch_uses_verified_source_coordinate() -> None:
    from scripts.metric_collection_phase2.probe_mutant_semantics import patch_source

    source = "def one():\n    return 0\ndef two():\n    return 0\n"
    diff = "@@ -2,1 +2,1 @@\n-    return 0\n+    return 1\n"
    assert (
        patch_source(source, diff, 4)
        == "def one():\n    return 0\ndef two():\n    return 1\n"
    )


def test_primary_review_rejects_changed_patch_and_never_invents_secondary() -> None:
    import hashlib

    from scripts.metric_collection_phase2.apply_primary_mutant_review import (
        apply_review,
    )

    catalog = {
        "catalog_hash": "catalog",
        "sut_hash": "sut",
        "mutants": [{"mutant_id": "M1", "diff": "patch"}],
    }
    primary = {
        "catalog_hash": "catalog",
        "sut_hash": "sut",
        "decisions": {
            "M1": {
                "diff_sha256": hashlib.sha256(b"patch").hexdigest(),
                "review_status": "confirmed_equivalent",
                "review_reason": "Every local initializer is overwritten before use.",
            }
        },
    }
    _, rows = apply_review(catalog, {"M1"}, primary)
    assert rows[0]["reviewer_2_status"] == ""
    assert rows[0]["decision_basis"] == "primary_source_review_only"
    catalog["mutants"][0]["diff"] = "different patch"
    with pytest.raises(ValueError, match="patch changed"):
        apply_review(catalog, {"M1"}, primary)


def test_participant_08_always_runs_serially() -> None:
    from scripts.metric_collection_phase2.collect_mutation_score import (
        participant_workers,
    )

    assert participant_workers(8, 4) == 1
    assert participant_workers(2, 4) == 4
    with pytest.raises(ValueError, match="positive"):
        participant_workers(8, 0)
