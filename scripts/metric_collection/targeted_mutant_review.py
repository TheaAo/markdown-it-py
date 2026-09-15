from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

try:
    from scripts.metric_collection.equivalent_mutant_sampling import (
        ADJUDICATION_COLUMNS,
        REVIEWER_COLUMNS,
    )
    from scripts.metric_collection.mutation_common import (
        canonical_json,
        load_catalog,
        write_csv,
        write_json,
    )
except ModuleNotFoundError:  # pragma: no cover
    from equivalent_mutant_sampling import (  # type: ignore[no-redef]
        ADJUDICATION_COLUMNS,
        REVIEWER_COLUMNS,
    )
    from mutation_common import (  # type: ignore[no-redef]
        canonical_json,
        load_catalog,
        write_csv,
        write_json,
    )


REVIEW_STATUSES = frozenset(
    {"non_equivalent", "confirmed_equivalent", "duplicate", "unresolved"}
)
TARGETED_STATUSES = frozenset(
    {"confirmed_equivalent", "duplicate", "unresolved"}
)
DECISION_COLUMNS = (
    "mutant_id",
    "reviewer_1_status",
    "reviewer_1_reason",
    "reviewer_2_status",
    "reviewer_2_reason",
    "adjudicated_status",
    "adjudication_reason",
    "decision_basis",
)


def _primary_identity(rows: Sequence[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        (
            {
                "mutant_id": row.get("mutant_id", "").strip(),
                "reviewer_1_status": row.get("reviewer_1_status", "").strip(),
                "reviewer_1_reason": row.get("reviewer_1_reason", "").strip(),
            }
            for row in rows
        ),
        key=lambda row: row["mutant_id"],
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def _validate_primary(rows: Sequence[dict[str, str]]) -> None:
    identities = _primary_identity(rows)
    mutant_ids = [row["mutant_id"] for row in identities]
    if not mutant_ids or any(not mutant_id for mutant_id in mutant_ids):
        raise ValueError("complete primary review requires non-empty mutant IDs")
    if len(set(mutant_ids)) != len(mutant_ids):
        raise ValueError("complete primary review requires unique mutant IDs")
    if any(row["reviewer_1_status"] not in REVIEW_STATUSES for row in identities):
        raise ValueError(
            "complete primary review requires a valid status for every row"
        )


def prepare_secondary_review(
    primary_rows: Sequence[dict[str, str]], *, qc_size: int, seed: int
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Select a blinded targeted-secondary workload plus random quality control."""
    _validate_primary(primary_rows)
    if qc_size < 0:
        raise ValueError("quality-control sample size cannot be negative")
    by_id = {row["mutant_id"].strip(): row for row in primary_rows}
    targeted_ids = {
        mutant_id
        for mutant_id, row in by_id.items()
        if row["reviewer_1_status"].strip() in TARGETED_STATUSES
    }
    qc_pool = sorted(set(by_id) - targeted_ids)
    if qc_size > len(qc_pool):
        raise ValueError("quality-control sample exceeds the eligible pool")
    ranked_qc = sorted(
        qc_pool,
        key=lambda mutant_id: hashlib.sha256(
            f"{seed}|targeted-secondary-qc|{mutant_id}".encode()
        ).hexdigest(),
    )
    qc_ids = ranked_qc[:qc_size]
    selected_ids = sorted(targeted_ids | set(qc_ids))
    secondary_rows = []
    for mutant_id in selected_ids:
        source = by_id[mutant_id]
        secondary_rows.append(
            {
                column: (
                    ""
                    if column in {"reviewer_2_status", "reviewer_2_reason"}
                    else source.get(column, "")
                )
                for column in REVIEWER_COLUMNS["reviewer_2"]
            }
        )
    identity = {
        "schema_version": 1,
        "method": "targeted_secondary_plus_deterministic_random_qc",
        "seed": seed,
        "quality_control_sample_size": qc_size,
        "targeted_statuses": sorted(TARGETED_STATUSES),
        "primary_review_hash": _sha256(_primary_identity(primary_rows)),
        "primary_reviewed_mutants": len(primary_rows),
        "targeted_mutant_count": len(targeted_ids),
        "quality_control_pool_size": len(qc_pool),
        "quality_control_mutant_ids": qc_ids,
        "selected_mutant_ids": selected_ids,
    }
    return secondary_rows, {**identity, "manifest_hash": _sha256(identity)}


def _validate_selection_manifest(
    primary_rows: Sequence[dict[str, str]], manifest: dict[str, Any]
) -> None:
    identity = {key: value for key, value in manifest.items() if key != "manifest_hash"}
    if manifest.get("manifest_hash") != _sha256(identity):
        raise ValueError("secondary selection manifest hash does not match")
    _rows, expected = prepare_secondary_review(
        primary_rows,
        qc_size=int(manifest["quality_control_sample_size"]),
        seed=int(manifest["seed"]),
    )
    fields = (
        "method",
        "targeted_statuses",
        "primary_review_hash",
        "primary_reviewed_mutants",
        "targeted_mutant_count",
        "quality_control_pool_size",
        "quality_control_mutant_ids",
        "selected_mutant_ids",
    )
    if any(manifest.get(field) != expected[field] for field in fields):
        raise ValueError("secondary selection provenance does not match primary review")


def apply_targeted_reviews(
    catalog: dict[str, Any],
    primary: dict[str, dict[str, str]],
    secondary: dict[str, dict[str, str]],
    adjudication: dict[str, dict[str, str]],
    selection_manifest: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    """Finalize targeted reviews while retaining their asymmetric decision basis."""
    primary_rows = list(primary.values())
    _validate_selection_manifest(primary_rows, selection_manifest)
    selected_ids = set(selection_manifest["selected_mutant_ids"])
    if set(secondary) != selected_ids:
        raise ValueError("secondary rows do not match selection provenance")
    known_ids = {str(row["mutant_id"]) for row in catalog["mutants"]}
    if set(primary) - known_ids:
        raise ValueError("primary review contains unknown mutant IDs")
    if set(adjudication) - selected_ids:
        raise ValueError("adjudication contains mutants absent from secondary review")

    decisions: list[dict[str, str]] = []
    qc_ids = set(selection_manifest["quality_control_mutant_ids"])
    qc_pairs: list[tuple[str, str]] = []
    for mutant_id in sorted(primary):
        first = primary[mutant_id].get("reviewer_1_status", "").strip()
        first_reason = primary[mutant_id].get("reviewer_1_reason", "").strip()
        if mutant_id not in selected_ids:
            if first != "non_equivalent":
                raise ValueError(
                    "only non-equivalent labels may bypass secondary review"
                )
            second = ""
            second_reason = ""
            final = first
            final_reason = first_reason
            basis = "primary_only_non_equivalent"
        else:
            second = secondary[mutant_id].get("reviewer_2_status", "").strip()
            second_reason = secondary[mutant_id].get("reviewer_2_reason", "").strip()
            if second not in REVIEW_STATUSES:
                raise ValueError(f"invalid secondary status for {mutant_id}")
            if mutant_id in qc_ids:
                qc_pairs.append((first, second))
            if first == second:
                final = first
                final_reason = "; ".join(filter(None, (first_reason, second_reason)))
                basis = "independent_agreement"
            else:
                row = adjudication.get(mutant_id, {})
                final = row.get("adjudicated_status", "").strip()
                final_reason = row.get("adjudication_reason", "").strip()
                if final not in REVIEW_STATUSES:
                    raise ValueError(
                        f"disagreement requires adjudication for {mutant_id}"
                    )
                basis = "adjudicated_disagreement"
        decisions.append(
            {
                "mutant_id": mutant_id,
                "reviewer_1_status": first,
                "reviewer_1_reason": first_reason,
                "reviewer_2_status": second,
                "reviewer_2_reason": second_reason,
                "adjudicated_status": final,
                "adjudication_reason": final_reason,
                "decision_basis": basis,
            }
        )

    review_identity = [
        {
            "mutant_id": row["mutant_id"],
            "review_status": row["adjudicated_status"],
            "review_reason": row["adjudication_reason"],
        }
        for row in decisions
    ]
    review_hash = _sha256(review_identity)
    reviewed = deepcopy(catalog)
    reviewed_by_id = {row["mutant_id"]: row for row in reviewed["mutants"]}
    for decision in decisions:
        mutant = reviewed_by_id[decision["mutant_id"]]
        mutant["review_status"] = decision["adjudicated_status"]
        mutant["review_notes"] = decision["adjudication_reason"]
    reviewed_catalog_hash = _sha256(
        {
            "catalog_hash": reviewed["catalog_hash"],
            "review_artifact_hash": review_hash,
            "review_decisions": review_identity,
        }
    )
    reviewed["global_review_hash"] = review_hash
    reviewed["reviewed_catalog_artifact_hash"] = reviewed_catalog_hash
    counts = Counter(row["adjudicated_status"] for row in decisions)
    summary = {
        "reviewed_mutants": len(decisions),
        "secondary_reviewed_mutants": len(selected_ids),
        "primary_only_non_equivalent_mutants": len(decisions) - len(selected_ids),
        "quality_control_sample_size": len(qc_pairs),
        "quality_control_raw_agreement": (
            sum(first == second for first, second in qc_pairs) / len(qc_pairs)
            if qc_pairs
            else None
        ),
        "cohen_kappa": None,
        "cohen_kappa_reason": (
            "targeted secondary review is not a full random double code"
        ),
        "disagreement_count": sum(
            bool(row["reviewer_2_status"])
            and row["reviewer_1_status"] != row["reviewer_2_status"]
            for row in decisions
        ),
        "final_status_counts": dict(sorted(counts.items())),
        "review_artifact_hash": review_hash,
        "reviewed_catalog_artifact_hash": reviewed_catalog_hash,
        "catalog_hash": reviewed["catalog_hash"],
        "secondary_selection_manifest_hash": selection_manifest["manifest_hash"],
    }
    return reviewed, summary, decisions


def _load_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        mutant_id = row.get("mutant_id", "").strip()
        if not mutant_id or mutant_id in by_id:
            raise ValueError(f"review mutant IDs must be unique and non-empty: {path}")
        by_id[mutant_id] = row
    return by_id


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage targeted secondary reviews.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare-secondary")
    prepare.add_argument("--primary-review", type=Path, required=True)
    prepare.add_argument("--output-secondary", type=Path, required=True)
    prepare.add_argument("--output-manifest", type=Path, required=True)
    prepare.add_argument("--output-adjudication", type=Path, required=True)
    prepare.add_argument("--qc-size", type=int, default=10)
    prepare.add_argument("--seed", type=int, default=20260915)
    apply = subparsers.add_parser("apply")
    apply.add_argument("--catalog", type=Path, required=True)
    apply.add_argument("--primary-review", type=Path, required=True)
    apply.add_argument("--secondary-review", type=Path, required=True)
    apply.add_argument("--selection-manifest", type=Path, required=True)
    apply.add_argument("--adjudication", type=Path)
    apply.add_argument("--output-catalog", type=Path, required=True)
    apply.add_argument("--output-summary", type=Path, required=True)
    apply.add_argument("--output-decisions", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare-secondary":
            primary = _load_rows(args.primary_review)
            rows, manifest = prepare_secondary_review(
                list(primary.values()), qc_size=args.qc_size, seed=args.seed
            )
            outputs = (
                args.output_secondary,
                args.output_manifest,
                args.output_adjudication,
            )
            if any(path.exists() for path in outputs):
                raise ValueError("targeted secondary outputs already exist")
            write_csv(args.output_secondary, REVIEWER_COLUMNS["reviewer_2"], rows)
            write_json(args.output_manifest, manifest)
            write_csv(
                args.output_adjudication,
                ADJUDICATION_COLUMNS,
                (
                    {
                        "mutant_id": row["mutant_id"],
                        "adjudicated_status": "",
                        "adjudication_reason": "",
                    }
                    for row in rows
                ),
            )
        else:
            catalog = load_catalog(args.catalog)
            primary = _load_rows(args.primary_review)
            secondary = _load_rows(args.secondary_review)
            adjudication = (
                _load_rows(args.adjudication) if args.adjudication else {}
            )
            manifest = json.loads(args.selection_manifest.read_text(encoding="utf-8"))
            reviewed, summary, decisions = apply_targeted_reviews(
                catalog, primary, secondary, adjudication, manifest
            )
            write_json(args.output_catalog, reviewed)
            write_json(args.output_summary, summary)
            write_csv(args.output_decisions, DECISION_COLUMNS, decisions)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
