import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.metric_collection.mutation_common import canonical_json, catalog_hash
from scripts.metric_collection.targeted_mutant_review import (
    apply_targeted_reviews,
    main,
    prepare_secondary_review,
)


def _review_rows() -> list[dict[str, str]]:
    statuses = (
        "confirmed_equivalent",
        "unresolved",
        "duplicate",
        "non_equivalent",
        "non_equivalent",
    )
    return [
        {
            "mutant_id": f"M{index}",
            "module": "example.py",
            "original_code": "return 1",
            "mutated_code": "return 2",
            "reviewer_1_status": status,
            "reviewer_1_reason": f"reason {index}",
        }
        for index, status in enumerate(statuses)
    ]


def _catalog() -> dict[str, Any]:
    mutants = [
        {
            "mutant_id": f"M{index}",
            "mutant_name": f"example__mutmut_{index}",
            "module": "example.py",
            "function": "example",
            "source_line": index + 1,
            "workload_layer": "specified",
            "diff": f"-return {index}\n+return {index + 1}\n",
            "review_status": "unreviewed",
        }
        for index in range(5)
    ]
    return {"catalog_hash": catalog_hash(mutants), "mutants": mutants}


def test_secondary_review_targets_risky_labels_and_random_quality_control() -> None:
    rows, manifest = prepare_secondary_review(_review_rows(), qc_size=1, seed=17)

    selected_ids = {row["mutant_id"] for row in rows}
    assert {"M0", "M1", "M2"} < selected_ids
    assert len(selected_ids) == 4
    assert len(manifest["quality_control_mutant_ids"]) == 1
    assert set(manifest["quality_control_mutant_ids"]) <= {"M3", "M4"}
    assert manifest["targeted_statuses"] == [
        "confirmed_equivalent",
        "duplicate",
        "unresolved",
    ]
    assert all("reviewer_1_status" not in row for row in rows)
    assert all("reviewer_1_reason" not in row for row in rows)
    assert all(row["reviewer_2_status"] == "" for row in rows)


def test_secondary_review_requires_complete_primary_decisions() -> None:
    rows = _review_rows()
    rows[0]["reviewer_1_status"] = ""

    with pytest.raises(ValueError, match="complete primary review"):
        prepare_secondary_review(rows, qc_size=1, seed=17)


def test_targeted_review_accepts_primary_only_non_equivalent_and_adjudicates() -> None:
    primary = _review_rows()
    secondary_rows, manifest = prepare_secondary_review(
        primary, qc_size=1, seed=17
    )
    secondary = {
        row["mutant_id"]: {
            **row,
            "reviewer_2_status": (
                "non_equivalent" if row["mutant_id"] == "M1" else "confirmed_equivalent"
            ),
            "reviewer_2_reason": "independent review",
        }
        for row in secondary_rows
    }
    qc_id = manifest["quality_control_mutant_ids"][0]
    secondary[qc_id]["reviewer_2_status"] = "non_equivalent"
    adjudication = {
        "M1": {
            "adjudicated_status": "non_equivalent",
            "adjudication_reason": "counterexample",
        },
        "M2": {
            "adjudicated_status": "duplicate",
            "adjudication_reason": "same generated mutant",
        },
    }

    reviewed, summary, decisions = apply_targeted_reviews(
        _catalog(),
        {row["mutant_id"]: row for row in primary},
        secondary,
        adjudication,
        manifest,
    )

    by_id = {row["mutant_id"]: row for row in decisions}
    unselected = ({"M3", "M4"} - {qc_id}).pop()
    assert by_id[unselected]["adjudicated_status"] == "non_equivalent"
    assert by_id[unselected]["decision_basis"] == "primary_only_non_equivalent"
    assert by_id["M1"]["adjudicated_status"] == "non_equivalent"
    assert by_id["M1"]["decision_basis"] == "adjudicated_disagreement"
    assert summary["reviewed_mutants"] == 5
    assert summary["secondary_reviewed_mutants"] == 4
    assert summary["quality_control_sample_size"] == 1
    assert summary["cohen_kappa"] is None
    assert reviewed["global_review_hash"] == summary["review_artifact_hash"]


def test_targeted_review_rejects_tampered_secondary_selection() -> None:
    primary = _review_rows()
    secondary_rows, manifest = prepare_secondary_review(
        primary, qc_size=1, seed=17
    )
    manifest["selected_mutant_ids"] = manifest["selected_mutant_ids"][:-1]
    manifest_identity = {
        key: value for key, value in manifest.items() if key != "manifest_hash"
    }
    manifest["manifest_hash"] = hashlib.sha256(
        canonical_json(manifest_identity).encode()
    ).hexdigest()

    with pytest.raises(ValueError, match="selection provenance"):
        apply_targeted_reviews(
            _catalog(),
            {row["mutant_id"]: row for row in primary},
            {row["mutant_id"]: row for row in secondary_rows},
            {},
            manifest,
        )


def test_prepare_secondary_cli_writes_blinded_review_and_adjudication(
    tmp_path: Path,
) -> None:
    primary_path = tmp_path / "primary.csv"
    secondary_path = tmp_path / "secondary.csv"
    manifest_path = tmp_path / "selection.json"
    adjudication_path = tmp_path / "adjudication.csv"
    rows = _review_rows()
    with primary_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    assert (
        main(
            [
                "prepare-secondary",
                "--primary-review",
                str(primary_path),
                "--output-secondary",
                str(secondary_path),
                "--output-manifest",
                str(manifest_path),
                "--output-adjudication",
                str(adjudication_path),
                "--qc-size",
                "1",
                "--seed",
                "17",
            ]
        )
        == 0
    )
    with secondary_path.open(newline="") as stream:
        secondary = list(csv.DictReader(stream))
    with adjudication_path.open(newline="") as stream:
        adjudication = list(csv.DictReader(stream))
    manifest = json.loads(manifest_path.read_text())

    assert len(secondary) == len(adjudication) == 4
    assert all("reviewer_1_status" not in row for row in secondary)
    assert {row["mutant_id"] for row in secondary} == set(
        manifest["selected_mutant_ids"]
    )
