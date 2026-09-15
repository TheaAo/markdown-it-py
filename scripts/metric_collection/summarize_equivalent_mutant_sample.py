from __future__ import annotations

import argparse
from collections.abc import Sequence
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

try:
    from scripts.metric_collection.equivalent_mutant_sampling import (
        estimate_adjusted_scores,
        write_adjusted_score_outputs,
    )
    from scripts.metric_collection.mutation_common import canonical_json
except ModuleNotFoundError:  # pragma: no cover
    from equivalent_mutant_sampling import (  # type: ignore[no-redef]
        estimate_adjusted_scores,
        write_adjusted_score_outputs,
    )
    from mutation_common import canonical_json  # type: ignore[no-redef]


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _load_sample(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for field in (
            "stratum_population",
            "stratum_sample_size",
            "within_stratum_rank",
            "cluster_multiplicity",
        ):
            row[field] = int(row[field])
        for field in ("inclusion_probability", "sampling_weight"):
            row[field] = float(row[field])
    return rows


def _load_decisions(path: Path) -> tuple[dict[str, str], str]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    decisions: dict[str, str] = {}
    review_identity: list[dict[str, str]] = []
    for row in rows:
        mutant_id = row.get("mutant_id", "").strip()
        status = row.get("adjudicated_status", row.get("review_status", "")).strip()
        if not mutant_id or mutant_id in decisions:
            raise ValueError("decision mutant IDs must be unique and non-empty")
        decisions[mutant_id] = status
        review_identity.append(
            {
                "mutant_id": mutant_id,
                "review_status": status,
                "review_reason": row.get("adjudication_reason", "").strip(),
            }
        )
    review_identity.sort(key=lambda row: row["mutant_id"])
    review_hash = hashlib.sha256(
        canonical_json(review_identity).encode()
    ).hexdigest()
    return decisions, review_hash


def _load_matrix(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    matrix: dict[str, dict[str, str]] = {}
    for row in rows:
        mutant_id = row.pop("mutant_id", "").strip()
        if not mutant_id or mutant_id in matrix:
            raise ValueError("matrix mutant IDs must be unique and non-empty")
        matrix[mutant_id] = row
    return matrix


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Estimate equivalent-adjusted participant mutation scores."
    )
    parser.add_argument("--collection-manifest", type=Path, required=True)
    parser.add_argument("--global-outcomes", type=Path, required=True)
    parser.add_argument("--sampling-manifest", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--review-summary", type=Path, required=True)
    parser.add_argument("--participant-matrix", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target-half-width", type=float, default=0.05)
    args = parser.parse_args(argv)
    try:
        collection_manifest = _load_json(args.collection_manifest)
        global_outcomes = _load_json(args.global_outcomes)
        review_summary = _load_json(args.review_summary)
        decisions, review_hash = _load_decisions(args.decisions)
        if review_summary.get("review_artifact_hash") != review_hash:
            raise ValueError("review summary hash does not match review decisions")
        if review_summary.get("catalog_hash") != collection_manifest.get(
            "catalog_hash"
        ):
            raise ValueError("review summary catalog hash does not match collection")
        estimates = estimate_adjusted_scores(
            collection_manifest,
            global_outcomes,
            _load_json(args.sampling_manifest),
            _load_sample(args.sample),
            decisions,
            _load_matrix(args.participant_matrix),
            {
                "review_artifact_hash": review_hash,
                "reviewed_catalog_artifact_hash": str(
                    review_summary["reviewed_catalog_artifact_hash"]
                ),
            },
            target_half_width=args.target_half_width,
        )
        json_path, csv_path = write_adjusted_score_outputs(
            estimates, args.output_dir.resolve()
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    print(
        "All primary intervals within target: "
        f"{estimates['stopping']['all_primary_intervals_within_target']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
