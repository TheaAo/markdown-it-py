from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
from pathlib import Path
import sys
from typing import Any

try:
    from scripts.metric_collection.mutation_common import (
        layered_weighted_mutation_summary,
        load_catalog,
        write_json,
    )
except ModuleNotFoundError:  # pragma: no cover
    from mutation_common import (  # type: ignore[no-redef]
        layered_weighted_mutation_summary,
        load_catalog,
        write_json,
    )


def derive_result(
    sampled_catalog: dict[str, Any], full_payload: dict[str, Any]
) -> dict[str, Any]:
    participant = full_payload.get("participant", {})
    mutation = full_payload.get("mutation", full_payload)
    if mutation.get("catalog_hash") != sampled_catalog.get("source_catalog_hash"):
        raise ValueError("full result does not reference the sampled source catalog")
    full_by_id = {item["mutant_id"]: item for item in mutation["mutants"]}
    sampled_ids = {item["mutant_id"] for item in sampled_catalog["mutants"]}
    if not sampled_ids <= set(full_by_id):
        raise ValueError("sample contains mutants absent from the full result")
    mutants = [
        {**full_by_id[item["mutant_id"]], **item} for item in sampled_catalog["mutants"]
    ]
    original_summary = mutation["summary"]
    summary = {
        "valid_tests_included": original_summary["valid_tests_included"],
        "invalid_tests_excluded": original_summary["invalid_tests_excluded"],
        **layered_weighted_mutation_summary(mutants),
    }
    sampled_mutation = {
        **mutation,
        "schema_version": 2,
        "catalog_hash": sampled_catalog["catalog_hash"],
        "source_catalog_hash": sampled_catalog["source_catalog_hash"],
        "summary": summary,
        "mutants": mutants,
    }
    return {
        "participant": participant,
        "catalog_hash": sampled_catalog["catalog_hash"],
        "baseline_commit": sampled_catalog["baseline_commit"],
        "derived_from_full_catalog": sampled_catalog["source_catalog_hash"],
        "mutation": sampled_mutation,
    }


def derive_results(
    sampled_catalog: dict[str, Any],
    full_results_dir: Path,
    full_manifest: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    if full_manifest.get("catalog_hash") != sampled_catalog.get("source_catalog_hash"):
        raise ValueError("full manifest does not match sampled source catalog")
    participants: list[dict[str, Any]] = []
    raw_dir = output_dir / "raw"
    for participant in full_manifest["participants"]:
        record = dict(participant)
        if participant["status"] == "collected":
            source = full_results_dir / f"{participant['participant_id']}.json"
            payload = json.loads(source.read_text(encoding="utf-8"))
            derived = derive_result(sampled_catalog, payload)
            write_json(raw_dir / source.name, derived)
            record["summary"] = derived["mutation"]["summary"]
        participants.append(record)
    manifest = {
        "schema_version": 1,
        "catalog_hash": sampled_catalog["catalog_hash"],
        "source_catalog_hash": sampled_catalog["source_catalog_hash"],
        "baseline_commit": sampled_catalog["baseline_commit"],
        "derivation": "offline filtering of complete fixed-catalog outcomes",
        "participants": participants,
    }
    write_json(output_dir / "collection_manifest.json", manifest)
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Derive sampled pilot outcomes from complete mutation results."
    )
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--full-results", type=Path, required=True)
    parser.add_argument("--full-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog.resolve())
        if catalog.get("catalog_kind") != "sampled":
            raise ValueError("catalog must be a sampled catalog")
        manifest = derive_results(
            catalog,
            args.full_results.resolve(),
            json.loads(args.full_manifest.read_text(encoding="utf-8")),
            args.output_dir.resolve(),
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    collected = sum(item["status"] == "collected" for item in manifest["participants"])
    print(f"Derived participant results: {collected}")
    print(f"Sampled catalog hash: {manifest['catalog_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
