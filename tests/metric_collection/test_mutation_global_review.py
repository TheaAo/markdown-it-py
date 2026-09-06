from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.metric_collection.aggregate_mutant_outcomes import (
    BLINDED_REVIEW_COLUMNS,
    _include_manifest_failures,
    aggregate_outcomes,
)
from scripts.metric_collection.apply_global_mutant_reviews import apply_global_reviews
from scripts.metric_collection.mutation_common import catalog_hash, mutation_summary


def _catalog() -> dict[str, Any]:
    mutants = [
        {
            "mutant_id": f"M{number}",
            "mutant_name": f"example__mutmut_{number}",
            "module": "example.py",
            "function": "example",
            "source_line": number,
            "workload_layer": "specified",
            "diff": f"--- example.py\n+++ example.py\n@@ -{number},1 +{number},1 @@\n-return 1\n+return 2\n",
            "review_status": "unreviewed",
        }
        for number in range(1, 4)
    ]
    return {
        "catalog_hash": catalog_hash(mutants),
        "baseline_commit": "base",
        "sut_hash": "sut",
        "workload_hashes": {"specified": "specified", "extended": "extended"},
        "material_hashes": {"spec.md": "material"},
        "mutants": mutants,
    }


def _result(
    catalog: dict[str, Any], participant_number: int, statuses: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {
            "participant_id": f"experiment-{participant_number:02d}",
            "participant_number": participant_number,
            "status": "collected",
        },
        {
            "catalog_hash": catalog["catalog_hash"],
            "baseline_commit": catalog["baseline_commit"],
            "sut_hash": catalog["sut_hash"],
            "workload_hashes": catalog["workload_hashes"],
            "material_hashes": catalog["material_hashes"],
            "collection_policy_hash": "policy",
            "collection_status": "success",
            "baseline_valid_only_passed": True,
            "infrastructure_error": False,
            "mutants": [
                {**mutant, "status": status, "raw_status": status}
                for mutant, status in zip(catalog["mutants"], statuses, strict=True)
            ],
        },
    )


def test_any_reliable_kill_removes_global_review_candidate() -> None:
    catalog = _catalog()
    results = [
        _result(catalog, 1, ["survived", "timeout", "no_tests"]),
        _result(catalog, 2, ["killed", "killed", "survived"]),
    ]
    payload = aggregate_outcomes(catalog, results)
    assert [row["global_status"] for row in payload["outcomes"]] == [
        "auto_non_equivalent",
        "auto_non_equivalent",
        "review_candidate",
    ]
    assert len(payload["review_candidates"]) == 1
    assert payload["summary"]["manual_review_reduction"] == 2
    assert payload["participant_matrix"]["M1"]["experiment-01"] == "survived"
    assert not any(
        "participant" in column or "kill" in column for column in BLINDED_REVIEW_COLUMNS
    )


def test_global_evidence_is_independent_of_current_participant_status() -> None:
    catalog = _catalog()
    results = [_result(catalog, 1, ["survived", "survived", "no_tests"])]
    evidence = {
        "schema_version": 1,
        "records": {
            "evidence": {
                "mutant_id": "M1",
                "catalog_hash": catalog["catalog_hash"],
                "sut_hash": catalog["sut_hash"],
                "confirmed_status": "reliably_killed",
            }
        },
    }

    payload = aggregate_outcomes(
        catalog,
        results,
        require_confirmed_kills=True,
        reliable_kill_evidence=evidence,
    )

    assert payload["outcomes"][0]["global_status"] == "auto_non_equivalent"
    assert payload["outcomes"][0]["survived"] == 1
    assert payload["outcomes"][0]["reliable_kill_count"] == 1


def test_failure_flaky_and_unconfirmed_kills_are_not_reliable() -> None:
    catalog = _catalog()
    failed = _result(catalog, 1, ["killed", "killed", "killed"])
    failed[0]["status"] = "collection_failed"
    flaky = _result(catalog, 2, ["killed", "survived", "timeout"])
    flaky[1]["mutants"][0]["flaky_kill"] = True
    payload = aggregate_outcomes(catalog, [failed, flaky])
    assert payload["summary"]["auto_non_equivalent"] == 0

    unconfirmed = _result(catalog, 3, ["killed", "killed", "killed"])
    payload = aggregate_outcomes(catalog, [unconfirmed], require_confirmed_kills=True)
    assert payload["summary"]["auto_non_equivalent"] == 0


def test_not_participated_results_are_ignored_and_hash_mismatch_rejected() -> None:
    catalog = _catalog()
    payload = aggregate_outcomes(
        catalog,
        [_result(catalog, 13, ["killed"] * 3), _result(catalog, 15, ["killed"] * 3)],
    )
    assert payload["summary"]["participants_total"] == 0
    mismatched = _result(catalog, 1, ["killed"] * 3)
    mismatched[1]["catalog_hash"] = "wrong"
    with pytest.raises(ValueError, match="catalog hash mismatch"):
        aggregate_outcomes(catalog, [mismatched])


def test_aggregation_rejects_material_and_policy_mismatches() -> None:
    catalog = _catalog()
    first = _result(catalog, 1, ["killed"] * 3)
    wrong_material = _result(catalog, 2, ["killed"] * 3)
    wrong_material[1]["material_hashes"] = {"spec.md": "wrong"}
    with pytest.raises(ValueError, match="material hash mismatch"):
        aggregate_outcomes(catalog, [wrong_material])

    wrong_policy = _result(catalog, 2, ["killed"] * 3)
    wrong_policy[1]["collection_policy_hash"] = "different-policy"
    with pytest.raises(ValueError, match="collection policy hash mismatch"):
        aggregate_outcomes(catalog, [first, wrong_policy])


def test_manifest_collection_failure_is_visible_but_not_reliable(
    tmp_path: Path,
) -> None:
    catalog = _catalog()
    manifest = {
        "catalog_hash": catalog["catalog_hash"],
        "collection_policy_hash": "policy",
        "participants": [
            {
                "participant_id": "experiment-01",
                "participant_number": 1,
                "status": "collection_failed",
            },
            {
                "participant_id": "experiment-13",
                "participant_number": 13,
                "status": "not_participated",
            },
        ],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")

    pairs = _include_manifest_failures(catalog, [], path)
    payload = aggregate_outcomes(catalog, pairs)

    assert payload["summary"]["participants_total"] == 1
    assert payload["summary"]["reliable_participants"] == 0
    assert all(
        row["global_status"] == "execution_unresolved" for row in payload["outcomes"]
    )


def test_global_reviews_preserve_identity_and_report_agreement() -> None:
    catalog = _catalog()
    original_hash = catalog["catalog_hash"]
    first = {
        "M1": {
            "reviewer_1_status": "confirmed_equivalent",
            "reviewer_1_reason": "行为一致",
        },
        "M2": {"reviewer_1_status": "non_equivalent", "reviewer_1_reason": "存在反例"},
    }
    second = {
        "M1": {
            "reviewer_2_status": "confirmed_equivalent",
            "reviewer_2_reason": "所有路径一致",
        },
        "M2": {"reviewer_2_status": "unresolved", "reviewer_2_reason": "证据不足"},
    }
    reviewed, summary, decisions = apply_global_reviews(catalog, first, second)
    assert reviewed["catalog_hash"] == original_hash
    assert catalog_hash(reviewed["mutants"]) == original_hash
    assert reviewed["global_review_hash"] == summary["review_artifact_hash"]
    assert (
        reviewed["reviewed_catalog_artifact_hash"]
        == summary["reviewed_catalog_artifact_hash"]
    )
    assert summary["raw_agreement"] == 0.5
    assert summary["disagreement_count"] == 1
    assert decisions[1]["adjudicated_status"] == "unresolved"


def test_equivalent_is_excluded_globally_and_unresolved_is_retained() -> None:
    rows = [
        {"status": "killed", "review_status": "unreviewed"},
        {"status": "survived", "review_status": "confirmed_equivalent"},
        {"status": "no_tests", "review_status": "unresolved"},
        {"status": "survived", "review_status": "duplicate"},
    ]
    first = mutation_summary(rows)
    second_rows = deepcopy(rows)
    second_rows[1]["status"] = "no_tests"
    second = mutation_summary(second_rows)
    assert first["eligible_mutants"] == second["eligible_mutants"] == 3
    assert first["mutation_score"] == second["mutation_score"] == pytest.approx(1 / 3)
    assert mutation_summary(rows, exclude_duplicates=True)["mutation_score"] == 0.5
