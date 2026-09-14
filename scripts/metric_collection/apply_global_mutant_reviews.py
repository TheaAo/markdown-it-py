from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
import csv
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

try:
    from scripts.metric_collection.mutation_common import (
        canonical_json,
        load_catalog,
        write_csv,
        write_json,
    )
except ModuleNotFoundError:  # pragma: no cover
    from mutation_common import (  # type: ignore[no-redef]
        canonical_json,
        load_catalog,
        write_csv,
        write_json,
    )


FINAL_STATUSES = frozenset(
    {"non_equivalent", "confirmed_equivalent", "duplicate", "unresolved"}
)


def _load_rows(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    by_id: dict[str, dict[str, str]] = {}
    for row in rows:
        mutant_id = row.get("mutant_id", "").strip()
        if not mutant_id:
            raise ValueError(f"review row has no mutant ID: {path}")
        if mutant_id in by_id:
            raise ValueError(f"duplicate mutant ID in {path}: {mutant_id}")
        by_id[mutant_id] = row
    return by_id


def _status(row: dict[str, str], prefix: str) -> str:
    return row.get(f"{prefix}_status", row.get("review_status", "")).strip()


def _reason(row: dict[str, str], prefix: str) -> str:
    return row.get(f"{prefix}_reason", row.get("review_reason", "")).strip()


def _cohen_kappa(pairs: Sequence[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    agreement = sum(first == second for first, second in pairs) / len(pairs)
    first_counts = Counter(first for first, _second in pairs)
    second_counts = Counter(second for _first, second in pairs)
    expected = sum(
        first_counts[value] / len(pairs) * second_counts[value] / len(pairs)
        for value in FINAL_STATUSES
    )
    if expected == 1.0:
        return 1.0 if agreement == 1.0 else 0.0
    return (agreement - expected) / (1.0 - expected)


def apply_global_reviews(
    catalog: dict[str, Any],
    reviewer_1: dict[str, dict[str, str]],
    reviewer_2: dict[str, dict[str, str]],
    adjudication: dict[str, dict[str, str]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
    known_ids = {item["mutant_id"] for item in catalog["mutants"]}
    if set(reviewer_1) != set(reviewer_2):
        raise ValueError("reviewer files must contain the same mutant IDs")
    unknown = set(reviewer_1) - known_ids
    if unknown:
        raise ValueError(f"review contains unknown mutant IDs: {sorted(unknown)}")
    if adjudication is not None and set(adjudication) - set(reviewer_1):
        raise ValueError("adjudication contains mutant IDs absent from reviews")

    pairs: list[tuple[str, str]] = []
    decisions: list[dict[str, str]] = []
    for mutant_id in sorted(reviewer_1):
        first = _status(reviewer_1[mutant_id], "reviewer_1")
        second = _status(reviewer_2[mutant_id], "reviewer_2")
        if first not in FINAL_STATUSES or second not in FINAL_STATUSES:
            raise ValueError(f"invalid reviewer status for {mutant_id}")
        pairs.append((first, second))
        if first == second:
            final = first
            final_reason = _reason(reviewer_1[mutant_id], "reviewer_1")
            if _reason(reviewer_2[mutant_id], "reviewer_2"):
                final_reason = "; ".join(
                    filter(
                        None,
                        (
                            final_reason,
                            _reason(reviewer_2[mutant_id], "reviewer_2"),
                        ),
                    )
                )
        else:
            row = (adjudication or {}).get(mutant_id, {})
            final = row.get("adjudicated_status", "unresolved").strip() or "unresolved"
            final_reason = row.get("adjudication_reason", "").strip()
            if final not in FINAL_STATUSES:
                raise ValueError(f"invalid adjudicated status for {mutant_id}")
        decisions.append(
            {
                "mutant_id": mutant_id,
                "reviewer_1_status": first,
                "reviewer_1_reason": _reason(reviewer_1[mutant_id], "reviewer_1"),
                "reviewer_2_status": second,
                "reviewer_2_reason": _reason(reviewer_2[mutant_id], "reviewer_2"),
                "adjudicated_status": final,
                "adjudication_reason": final_reason,
            }
        )
    by_id = {item["mutant_id"]: item for item in catalog["mutants"]}
    for decision in decisions:
        mutant = by_id[decision["mutant_id"]]
        mutant["review_status"] = decision["adjudicated_status"]
        mutant["review_notes"] = decision["adjudication_reason"]
    review_identity = [
        {
            "mutant_id": item["mutant_id"],
            "review_status": item["adjudicated_status"],
            "review_reason": item["adjudication_reason"],
        }
        for item in decisions
    ]
    review_hash = hashlib.sha256(canonical_json(review_identity).encode()).hexdigest()
    catalog["global_review_hash"] = review_hash
    reviewed_catalog_artifact_hash = hashlib.sha256(
        canonical_json(
            {
                "catalog_hash": catalog["catalog_hash"],
                "review_artifact_hash": review_hash,
                "review_decisions": review_identity,
            }
        ).encode()
    ).hexdigest()
    catalog["reviewed_catalog_artifact_hash"] = reviewed_catalog_artifact_hash
    summary = {
        "reviewed_mutants": len(decisions),
        "raw_agreement": (
            sum(first == second for first, second in pairs) / len(pairs)
            if pairs
            else None
        ),
        "cohen_kappa": _cohen_kappa(pairs),
        "disagreement_count": sum(first != second for first, second in pairs),
        "final_status_counts": dict(
            sorted(Counter(item["adjudicated_status"] for item in decisions).items())
        ),
        "review_artifact_hash": review_hash,
        "reviewed_catalog_artifact_hash": reviewed_catalog_artifact_hash,
        "catalog_hash": catalog["catalog_hash"],
    }
    return catalog, summary, decisions


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply blinded global mutant reviews.")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--reviewer-1", type=Path, required=True)
    parser.add_argument("--reviewer-2", type=Path, required=True)
    parser.add_argument("--adjudication", type=Path)
    parser.add_argument("--output-catalog", type=Path, required=True)
    parser.add_argument("--output-summary", type=Path, required=True)
    parser.add_argument("--output-decisions", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        catalog, summary, decisions = apply_global_reviews(
            load_catalog(args.catalog.resolve()),
            _load_rows(args.reviewer_1.resolve()),
            _load_rows(args.reviewer_2.resolve()),
            _load_rows(args.adjudication.resolve()) if args.adjudication else None,
        )
        write_json(args.output_catalog.resolve(), catalog)
        write_json(args.output_summary.resolve(), summary)
        write_csv(
            args.output_decisions.resolve(),
            (
                "mutant_id",
                "reviewer_1_status",
                "reviewer_1_reason",
                "reviewer_2_status",
                "reviewer_2_reason",
                "adjudicated_status",
                "adjudication_reason",
            ),
            decisions,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Reviewed mutants: {summary['reviewed_mutants']}")
    print(f"Raw agreement: {summary['raw_agreement']}")
    print(f"Cohen's kappa: {summary['cohen_kappa']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
