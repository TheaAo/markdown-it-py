"""Apply explicit source-review decisions without inventing independent review."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metric_collection_phase1.mutation_common import canonical_json, write_json
from scripts.metric_collection_phase1.summarize_equivalent_mutant_sample import (
    _load_decisions,
)


def apply_review(
    catalog: dict[str, Any], selected: set[str], primary: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Require explicit decisions for every actual sample and unchanged exact patches."""
    if (
        primary["catalog_hash"] != catalog["catalog_hash"]
        or primary["sut_hash"] != catalog["sut_hash"]
    ):
        raise ValueError("Primary review uses a different frozen catalog/SUT")
    reviewed = deepcopy(catalog)
    mutants = {row["mutant_id"]: row for row in reviewed["mutants"]}
    rows: list[dict[str, str]] = []
    for mid in sorted(selected):
        decision = primary["decisions"][mid]
        mutant = mutants[mid]
        if (
            decision["diff_sha256"]
            != hashlib.sha256(mutant["diff"].encode()).hexdigest()
        ):
            raise ValueError("Reviewed mutant patch changed")
        status, reason = decision["review_status"], decision["review_reason"]
        if (
            status not in {"confirmed_equivalent", "non_equivalent", "duplicate"}
            or not reason.strip()
        ):
            raise ValueError(
                "Every sampled mutant requires a resolved, explained source decision"
            )
        mutant["review_status"], mutant["review_notes"] = status, reason
        rows.append(
            {
                "mutant_id": mid,
                "reviewer_1_status": status,
                "reviewer_1_reason": reason,
                "reviewer_2_status": "",
                "reviewer_2_reason": "",
                "adjudicated_status": status,
                "adjudication_reason": reason,
                "decision_basis": "primary_source_review_only",
            }
        )
    return reviewed, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--primary-decisions", type=Path, required=True)
    parser.add_argument("--witnesses", type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    primary = json.loads(args.primary_decisions.read_text())
    with (args.review_dir / "sample.csv").open(newline="") as stream:
        selected = {row["mutant_id"] for row in csv.DictReader(stream)}
    witnesses = json.loads(args.witnesses.read_text())
    if (
        witnesses["catalog_hash"] != catalog["catalog_hash"]
        or witnesses["sut_hash"] != catalog["sut_hash"]
        or not selected.issubset(witnesses["records"])
    ):
        raise ValueError(
            "Semantic witness artifact does not cover the actual frozen sample"
        )
    reviewed, rows = apply_review(catalog, selected, primary)
    destination = args.review_dir / "review_decisions.csv"
    with destination.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    primary_path = args.review_dir / "reviewer_1.csv"
    with primary_path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        template = list(reader)
    if columns is None or {row["mutant_id"] for row in template} != selected:
        raise ValueError("Primary reviewer template does not match the frozen sample")
    by_id = {row["mutant_id"]: row for row in rows}
    for row in template:
        decision = by_id[row["mutant_id"]]
        row["reviewer_1_status"] = decision["reviewer_1_status"]
        row["reviewer_1_reason"] = decision["reviewer_1_reason"]
    with primary_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(template)
    _, review_hash = _load_decisions(destination)
    identity = {
        "catalog_hash": catalog["catalog_hash"],
        "review_artifact_hash": review_hash,
        "review_decisions": [
            {
                "mutant_id": row["mutant_id"],
                "review_status": row["adjudicated_status"],
                "review_reason": row["adjudication_reason"],
            }
            for row in rows
        ],
    }
    artifact_hash = hashlib.sha256(canonical_json(identity).encode()).hexdigest()
    reviewed["global_review_hash"] = review_hash
    reviewed["reviewed_catalog_artifact_hash"] = artifact_hash
    write_json(args.review_dir / "reviewed_catalog.json", reviewed)
    write_json(
        args.review_dir / "review_summary.json",
        {
            "catalog_hash": catalog["catalog_hash"],
            "review_artifact_hash": review_hash,
            "reviewed_catalog_artifact_hash": artifact_hash,
            "reviewed_mutants": len(rows),
            "final_status_counts": dict(
                Counter(row["adjudicated_status"] for row in rows)
            ),
            "method": "single_reviewer_source_analysis_with_executable_witnesses",
            "independent_secondary_review": False,
            "secondary_reviewed_mutants": 0,
            "reviewer_agreement": None,
            "primary_decisions_sha256": hashlib.sha256(
                args.primary_decisions.read_bytes()
            ).hexdigest(),
            "semantic_witnesses_sha256": hashlib.sha256(
                args.witnesses.read_bytes()
            ).hexdigest(),
            "limitation": "Equivalent decisions have no independent secondary review; probe agreement alone was never used as an equivalence proof.",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
