from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import sys
from typing import Any

try:
    from scripts.metric_collection.classify_mutation_operators import (
        classify_catalog,
    )
    from scripts.metric_collection.mutation_common import (
        canonical_json,
        catalog_hash,
        load_catalog,
        write_csv,
        write_json,
    )
except ModuleNotFoundError:  # pragma: no cover
    from classify_mutation_operators import classify_catalog  # type: ignore[no-redef]
    from mutation_common import (  # type: ignore[no-redef]
        canonical_json,
        catalog_hash,
        load_catalog,
        write_csv,
        write_json,
    )


STRATEGIES = (
    "base_random",
    "operator_stratified",
    "function_stratified",
    "function_operator_stratified",
    "layer_function_operator_stratified",
)
SAMPLED_COLUMNS = (
    "mutant_id",
    "mutant_name",
    "workload_layer",
    "module",
    "function",
    "operator_family",
    "source_line",
    "sampling_stratum",
    "stratum_population",
    "stratum_sample_size",
    "sampling_weight",
    "original_code",
    "mutated_code",
    "review_status",
)


def stratum_key(mutant: dict[str, Any], strategy: str) -> str:
    layer = str(mutant.get("workload_layer", "specified"))
    function = f"{mutant['module']}::{mutant.get('function', '<module>')}"
    operator = str(mutant.get("operator_family", "OTHER"))
    if strategy == "base_random":
        values = ("ALL",)
    elif strategy == "operator_stratified":
        values = (operator,)
    elif strategy == "function_stratified":
        values = (function,)
    elif strategy == "function_operator_stratified":
        values = (function, operator)
    elif strategy == "layer_function_operator_stratified":
        values = (layer, function, operator)
    else:
        raise ValueError(f"unknown sampling strategy: {strategy}")
    return " | ".join(values)


def _allocate(
    populations: dict[str, int], requested_size: int, minimum_per_stratum: int
) -> dict[str, int]:
    if minimum_per_stratum < 0:
        raise ValueError("minimum per stratum cannot be negative")
    total = sum(populations.values())
    allocations = {
        key: min(size, minimum_per_stratum) for key, size in populations.items()
    }
    target = min(total, max(requested_size, sum(allocations.values())))
    while sum(allocations.values()) < target:
        allocated_total = sum(allocations.values())
        candidates = [
            key for key in sorted(populations) if allocations[key] < populations[key]
        ]
        if not candidates:
            break
        key = max(
            candidates,
            key=lambda item: (
                requested_size * populations[item] / total - allocations[item],
                populations[item] - allocations[item],
                item,
            ),
        )
        allocations[key] += 1
        if sum(allocations.values()) == allocated_total:
            raise RuntimeError("sampling allocation did not make progress")
    return allocations


def sample_catalog(
    source_catalog: dict[str, Any],
    *,
    strategy: str,
    ratio: float | None,
    sample_size: int | None,
    minimum_sample_size: int,
    minimum_per_stratum: int,
    seed: int,
    census_layers: Sequence[str] = (),
    generated_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown sampling strategy: {strategy}")
    if (ratio is None) == (sample_size is None):
        raise ValueError("provide exactly one of ratio or sample size")
    if ratio is not None and not 0 < ratio <= 1:
        raise ValueError("sampling ratio must be in (0, 1]")
    mutants = source_catalog["mutants"]
    if not mutants:
        raise ValueError("cannot sample an empty catalog")
    if any("operator_family" not in item for item in mutants):
        source_catalog = classify_catalog(source_catalog)
        mutants = source_catalog["mutants"]
    census_layer_set = set(census_layers)
    unknown_census_layers = census_layer_set - {
        str(item.get("workload_layer", "specified")) for item in mutants
    }
    if unknown_census_layers:
        raise ValueError(
            f"unknown census workload layers: {sorted(unknown_census_layers)}"
        )
    census_mutants = [
        item
        for item in mutants
        if item.get("workload_layer", "specified") in census_layer_set
    ]
    sampling_frame = [item for item in mutants if item not in census_mutants]
    if not sampling_frame:
        raise ValueError("sampling frame is empty after selecting census layers")
    requested = (
        int(sample_size)
        if sample_size is not None
        else max(
            minimum_sample_size,
            math.ceil(float(ratio) * len(sampling_frame)),
        )
    )
    if requested <= 0:
        raise ValueError("sample size must be positive")
    requested = min(requested, len(sampling_frame))

    strata: dict[str, list[dict[str, Any]]] = {}
    for mutant in sorted(sampling_frame, key=lambda item: item["mutant_id"]):
        strata.setdefault(stratum_key(mutant, strategy), []).append(mutant)
    populations = {key: len(rows) for key, rows in strata.items()}
    effective_minimum = 0 if strategy == "base_random" else minimum_per_stratum
    allocations = _allocate(populations, requested, effective_minimum)
    generator = random.Random(seed)
    sampled: list[dict[str, Any]] = []
    stratum_rows: list[dict[str, Any]] = []
    for key in sorted(strata):
        rows = list(strata[key])
        generator.shuffle(rows)
        selected = sorted(rows[: allocations[key]], key=lambda item: item["mutant_id"])
        population = len(rows)
        selected_count = len(selected)
        weight = population / selected_count if selected_count else 0.0
        for item in selected:
            sampled.append(
                {
                    **item,
                    "sampling_stratum": key,
                    "stratum_population": population,
                    "stratum_sample_size": selected_count,
                    "sampling_weight": weight,
                }
            )
        stratum_rows.append(
            {
                "sampling_stratum": key,
                "population": population,
                "sample_size": selected_count,
                "sampling_fraction": selected_count / population,
                "sampling_weight": weight,
            }
        )
    for layer in sorted(census_layer_set):
        layer_mutants = sorted(
            (
                item
                for item in census_mutants
                if item.get("workload_layer", "specified") == layer
            ),
            key=lambda item: item["mutant_id"],
        )
        stratum = f"CENSUS | {layer}"
        population = len(layer_mutants)
        for item in layer_mutants:
            sampled.append(
                {
                    **item,
                    "sampling_stratum": stratum,
                    "stratum_population": population,
                    "stratum_sample_size": population,
                    "sampling_weight": 1.0,
                }
            )
        stratum_rows.append(
            {
                "sampling_stratum": stratum,
                "population": population,
                "sample_size": population,
                "sampling_fraction": 1.0,
                "sampling_weight": 1.0,
            }
        )
    sampled.sort(key=lambda item: item["mutant_id"])
    sampled_hash = catalog_hash(sampled)
    timestamp = generated_at or datetime.now(timezone.utc).isoformat()
    strategy_payload = {
        "strategy": strategy,
        "ratio": ratio,
        "requested_sample_size": requested,
        "actual_sample_size": len(sampled),
        "sampling_frame_size": len(sampling_frame),
        "sampled_from_frame": len(sampled) - len(census_mutants),
        "effective_sampling_ratio": (
            (len(sampled) - len(census_mutants)) / len(sampling_frame)
        ),
        "census_layers": sorted(census_layer_set),
        "census_mutants": len(census_mutants),
        "minimum_sample_size": minimum_sample_size,
        "minimum_per_stratum": effective_minimum,
        "seed": seed,
        "stratum_fields": {
            "base_random": [],
            "operator_stratified": ["operator_family"],
            "function_stratified": ["module", "function"],
            "function_operator_stratified": [
                "module",
                "function",
                "operator_family",
            ],
            "layer_function_operator_stratified": [
                "workload_layer",
                "module",
                "function",
                "operator_family",
            ],
        }[strategy],
    }
    manifest_identity = {
        "source_catalog_hash": source_catalog["catalog_hash"],
        "sampled_catalog_hash": sampled_hash,
        **strategy_payload,
        "strata": stratum_rows,
        "sampled_mutant_ids": [item["mutant_id"] for item in sampled],
    }
    manifest = {
        "schema_version": 1,
        "generated_at": timestamp,
        **manifest_identity,
        "manifest_hash": hashlib.sha256(
            canonical_json(manifest_identity).encode()
        ).hexdigest(),
    }
    payload = {
        key: value
        for key, value in source_catalog.items()
        if key not in {"mutants", "catalog_hash", "catalog_statistics"}
    }
    payload.update(
        {
            "schema_version": 3,
            "catalog_kind": "sampled",
            "source_catalog_hash": source_catalog["catalog_hash"],
            "catalog_hash": sampled_hash,
            "sampling": strategy_payload,
            "catalog_statistics": {
                "retained_mutants": len(sampled),
                "specified_mutants": sum(
                    item["workload_layer"] == "specified" for item in sampled
                ),
                "extended_only_mutants": sum(
                    item["workload_layer"] == "extended_only" for item in sampled
                ),
                "operator_family_counts": dict(
                    sorted(Counter(item["operator_family"] for item in sampled).items())
                ),
            },
            "mutants": sampled,
        }
    )
    return payload, manifest


def write_sample(
    source_catalog: dict[str, Any], output_dir: Path, **options: Any
) -> tuple[dict[str, Any], dict[str, Any]]:
    sampled, manifest = sample_catalog(source_catalog, **options)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "sampled_mutant_catalog.json", sampled)
    write_csv(
        output_dir / "sampled_mutant_catalog.csv", SAMPLED_COLUMNS, sampled["mutants"]
    )
    write_json(output_dir / "sampling_manifest.json", manifest)
    manifest_rows = [
        {
            "source_catalog_hash": manifest["source_catalog_hash"],
            "sampled_catalog_hash": manifest["sampled_catalog_hash"],
            "manifest_hash": manifest["manifest_hash"],
            "strategy": manifest["strategy"],
            "ratio": manifest["ratio"],
            "requested_sample_size": manifest["requested_sample_size"],
            "actual_sample_size": manifest["actual_sample_size"],
            "sampling_frame_size": manifest["sampling_frame_size"],
            "sampled_from_frame": manifest["sampled_from_frame"],
            "effective_sampling_ratio": manifest["effective_sampling_ratio"],
            "census_layers": ";".join(manifest["census_layers"]),
            "census_mutants": manifest["census_mutants"],
            "minimum_sample_size": manifest["minimum_sample_size"],
            "minimum_per_stratum": manifest["minimum_per_stratum"],
            "seed": manifest["seed"],
            **row,
        }
        for row in manifest["strata"]
    ]
    write_csv(
        output_dir / "sampling_manifest.csv",
        tuple(manifest_rows[0]) if manifest_rows else (),
        manifest_rows,
    )
    (output_dir / "sampled_catalog.sha256").write_text(
        sampled["catalog_hash"] + "\n", encoding="utf-8"
    )
    return sampled, manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a fixed sampled catalog.")
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--strategy", choices=STRATEGIES, required=True)
    size = parser.add_mutually_exclusive_group(required=True)
    size.add_argument("--ratio", type=float)
    size.add_argument("--sample-size", type=int)
    parser.add_argument("--minimum-sample-size", type=int, default=30)
    parser.add_argument("--minimum-per-stratum", type=int, default=1)
    parser.add_argument("--census-layer", action="append", default=[])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        sampled, manifest = write_sample(
            load_catalog(args.catalog.resolve()),
            args.output_dir.resolve(),
            strategy=args.strategy,
            ratio=args.ratio,
            sample_size=args.sample_size,
            minimum_sample_size=args.minimum_sample_size,
            minimum_per_stratum=args.minimum_per_stratum,
            seed=args.seed,
            census_layers=args.census_layer,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Sampled mutants: {len(sampled['mutants'])}")
    print(f"Sampled catalog hash: {sampled['catalog_hash']}")
    print(f"Manifest hash: {manifest['manifest_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
