from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys
from typing import Any

try:
    from scripts.metric_collection.mutation_common import (
        layered_mutation_summary,
        layered_weighted_mutation_summary,
        load_catalog,
        write_csv,
    )
except ModuleNotFoundError:  # pragma: no cover
    from mutation_common import (  # type: ignore[no-redef]
        layered_mutation_summary,
        layered_weighted_mutation_summary,
        load_catalog,
        write_csv,
    )


COLUMNS = (
    "participant_number",
    "status",
    "catalog_hash",
    "baseline_valid_only_passed",
    "valid_tests_included",
    "invalid_tests_excluded",
    "specified_catalog_total",
    "specified_killed",
    "specified_survived",
    "specified_no_tests",
    "specified_timeout",
    "specified_confirmed_equivalent",
    "specified_eligible_mutants",
    "specified_mutation_score",
    "specified_estimated_mutation_score",
    "specified_estimated_ci95_lower",
    "specified_estimated_ci95_upper",
    "extended_catalog_total",
    "extended_killed",
    "extended_survived",
    "extended_no_tests",
    "extended_timeout",
    "extended_confirmed_equivalent",
    "extended_eligible_mutants",
    "extended_mutation_score",
    "extended_estimated_mutation_score",
    "extended_estimated_ci95_lower",
    "extended_estimated_ci95_upper",
    "combined_catalog_total",
    "combined_mutation_score",
    "combined_estimated_mutation_score",
    "combined_estimated_ci95_lower",
    "combined_estimated_ci95_upper",
)


def _flatten_summary(summary: dict[str, Any]) -> dict[str, Any]:
    row = {
        "baseline_valid_only_passed": summary.get("baseline_valid_only_passed", True),
        "valid_tests_included": summary["valid_tests_included"],
        "invalid_tests_excluded": summary["invalid_tests_excluded"],
    }
    fields = (
        "catalog_total",
        "killed",
        "survived",
        "no_tests",
        "timeout",
        "confirmed_equivalent",
        "eligible_mutants",
        "mutation_score",
    )
    for layer in ("specified", "extended"):
        layer_summary = summary.get(layer)
        if not isinstance(layer_summary, dict):
            raise ValueError(f"mutation summary is missing {layer} layer")
        row.update({f"{layer}_{field}": layer_summary[field] for field in fields})
        for field in (
            "estimated_mutation_score",
            "estimated_ci95_lower",
            "estimated_ci95_upper",
        ):
            row[f"{layer}_{field}"] = layer_summary.get(field)
    combined = summary.get("combined")
    if not isinstance(combined, dict):
        raise ValueError("mutation summary is missing combined layer")
    row["combined_catalog_total"] = combined["catalog_total"]
    row["combined_mutation_score"] = combined["mutation_score"]
    for field in (
        "estimated_mutation_score",
        "estimated_ci95_lower",
        "estimated_ci95_upper",
    ):
        row[f"combined_{field}"] = combined.get(field)
    return row


def summarize(
    manifest_path: Path,
    output_path: Path,
    *,
    reviewed_catalog: Path | None = None,
    raw_dir: Path | None = None,
    exclude_duplicates: bool = False,
) -> Path:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    catalog = load_catalog(reviewed_catalog) if reviewed_catalog else None
    if catalog is not None and catalog["catalog_hash"] != manifest.get("catalog_hash"):
        raise ValueError("reviewed catalog hash does not match collection manifest")
    participants = manifest.get("participants")
    if not isinstance(participants, list):
        raise ValueError("mutation manifest is missing participants")
    rows: list[dict[str, Any]] = []
    for participant in participants:
        if not isinstance(participant, dict):
            raise ValueError("participant must be an object")
        row = {
            "participant_number": participant["participant_number"],
            "status": participant["status"],
            "catalog_hash": manifest.get("catalog_hash", ""),
        }
        if participant["status"] == "collected":
            summary = participant.get("summary")
            if not isinstance(summary, dict):
                raise ValueError("collected participant is missing mutation summary")
            if catalog is not None:
                raw_path = (raw_dir or manifest_path.parent / "raw") / (
                    participant["participant_id"] + ".json"
                )
                raw = json.loads(raw_path.read_text(encoding="utf-8"))
                mutation = raw.get("mutation", raw)
                if mutation.get("catalog_hash") != catalog["catalog_hash"]:
                    raise ValueError(
                        "raw participant catalog hash does not match reviews"
                    )
                reviews = {item["mutant_id"]: item for item in catalog["mutants"]}
                mutants = [
                    {**item, **reviews[item["mutant_id"]]}
                    for item in mutation["mutants"]
                ]
                if {item["mutant_id"] for item in mutants} != set(reviews):
                    raise ValueError("raw participant mutant IDs do not match reviews")
                summary_function = (
                    layered_weighted_mutation_summary
                    if catalog.get("catalog_kind") == "sampled"
                    else layered_mutation_summary
                )
                summary = {
                    **summary,
                    **summary_function(mutants, exclude_duplicates=exclude_duplicates),
                }
            row.update(_flatten_summary(summary))
        rows.append(row)
    rows.sort(key=lambda item: item["participant_number"])
    write_csv(output_path, COLUMNS, rows)
    return output_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write mutation_scores.csv.")
    parser.add_argument(
        "manifest",
        type=Path,
        nargs="?",
        default=Path("results/mutation_score/collection_manifest.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/mutation_score/summary/mutation_scores.csv"),
    )
    parser.add_argument("--reviewed-catalog", type=Path)
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--exclude-duplicates", action="store_true")
    args = parser.parse_args(argv)
    try:
        path = summarize(
            args.manifest.resolve(),
            args.output.resolve(),
            reviewed_catalog=(
                args.reviewed_catalog.resolve() if args.reviewed_catalog else None
            ),
            raw_dir=args.raw_dir.resolve() if args.raw_dir else None,
            exclude_duplicates=args.exclude_duplicates,
        )
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
