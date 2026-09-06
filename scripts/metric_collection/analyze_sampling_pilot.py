from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Sequence
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any

try:
    from scripts.metric_collection.aggregate_mutant_outcomes import (
        _result_paths,
        _unwrap,
    )
    from scripts.metric_collection.mutation_common import (
        load_catalog,
        mutation_summary,
        weighted_mutation_summary,
        write_csv,
        write_json,
    )
    from scripts.metric_collection.sample_mutant_catalog import sample_catalog
except ModuleNotFoundError:  # pragma: no cover
    from aggregate_mutant_outcomes import (  # type: ignore[no-redef]
        _result_paths,
        _unwrap,
    )
    from mutation_common import (  # type: ignore[no-redef]
        load_catalog,
        mutation_summary,
        weighted_mutation_summary,
        write_csv,
        write_json,
    )
    from sample_mutant_catalog import sample_catalog  # type: ignore[no-redef]


DEFAULT_THRESHOLDS = {
    "median_absolute_error": 0.05,
    "p95_absolute_error": 0.10,
    "adjusted_r_squared": 0.95,
    "kendall_tau_b": 0.90,
    "spearman_rho": 0.90,
}
LAYERS = ("specified", "extended", "combined")


def _percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    start = 0
    while start < len(indexed):
        end = start + 1
        while end < len(indexed) and indexed[end][1] == indexed[start][1]:
            end += 1
        rank = (start + 1 + end) / 2
        for index, _value in indexed[start:end]:
            ranks[index] = rank
        start = end
    return ranks


def _pearson(first: Sequence[float], second: Sequence[float]) -> float:
    if len(first) != len(second) or not first:
        return math.nan
    mean_first = statistics.fmean(first)
    mean_second = statistics.fmean(second)
    numerator = sum(
        (left - mean_first) * (right - mean_second)
        for left, right in zip(first, second, strict=True)
    )
    first_sum = sum((value - mean_first) ** 2 for value in first)
    second_sum = sum((value - mean_second) ** 2 for value in second)
    denominator = math.sqrt(first_sum * second_sum)
    if denominator == 0:
        return 1.0 if list(first) == list(second) else 0.0
    return numerator / denominator


def spearman_rho(first: Sequence[float], second: Sequence[float]) -> float:
    return _pearson(_ranks(first), _ranks(second))


def kendall_tau_b(first: Sequence[float], second: Sequence[float]) -> float:
    concordant = discordant = first_ties = second_ties = 0
    for left in range(len(first)):
        for right in range(left + 1, len(first)):
            delta_first = first[left] - first[right]
            delta_second = second[left] - second[right]
            if delta_first == 0 and delta_second == 0:
                continue
            if delta_first == 0:
                first_ties += 1
            elif delta_second == 0:
                second_ties += 1
            elif delta_first * delta_second > 0:
                concordant += 1
            else:
                discordant += 1
    denominator = math.sqrt(
        (concordant + discordant + first_ties) * (concordant + discordant + second_ties)
    )
    return (concordant - discordant) / denominator if denominator else 1.0


def adjusted_r_squared(actual: Sequence[float], predicted: Sequence[float]) -> float:
    if len(actual) < 3:
        return math.nan
    mean_actual = statistics.fmean(actual)
    total = sum((value - mean_actual) ** 2 for value in actual)
    residual = sum(
        (left - right) ** 2 for left, right in zip(actual, predicted, strict=True)
    )
    r_squared = (
        1.0
        if total == 0 and residual == 0
        else (1 - residual / total if total else 0.0)
    )
    return 1 - (1 - r_squared) * (len(actual) - 1) / (len(actual) - 2)


def _layer_rows(rows: Sequence[dict[str, Any]], layer: str) -> list[dict[str, Any]]:
    if layer == "combined":
        return list(rows)
    expected = "specified" if layer == "specified" else "extended_only"
    return [item for item in rows if item.get("workload_layer") == expected]


def _validated_results(
    catalog: dict[str, Any], paths: Sequence[Path]
) -> list[tuple[str, list[dict[str, Any]]]]:
    expected_ids = {item["mutant_id"] for item in catalog["mutants"]}
    results: list[tuple[str, list[dict[str, Any]]]] = []
    for path in paths:
        participant, mutation = _unwrap(path)
        if participant.get("status", "collected") != "collected":
            continue
        if mutation.get("catalog_hash") != catalog["catalog_hash"]:
            raise ValueError(f"catalog hash mismatch: {path}")
        rows = mutation.get("mutants")
        if (
            not isinstance(rows, list)
            or {item.get("mutant_id") for item in rows} != expected_ids
        ):
            raise ValueError(f"full mutant matrix mismatch: {path}")
        results.append((participant["participant_id"], rows))
    return sorted(results)


def analyze_sampling(
    catalog: dict[str, Any],
    participant_results: Sequence[tuple[str, list[dict[str, Any]]]],
    *,
    strategies: Sequence[str],
    ratios: Sequence[float],
    seeds: Sequence[int],
    minimum_sample_size: int,
    minimum_per_stratum: int,
    thresholds: dict[str, float],
    census_layers: Sequence[str] = (),
    acceptance_layer: str = "combined",
) -> dict[str, Any]:
    if not participant_results:
        raise ValueError("sampling pilot requires participant results")
    full_scores = {
        participant_id: {
            layer: mutation_summary(_layer_rows(rows, layer))["mutation_score"]
            for layer in LAYERS
        }
        for participant_id, rows in participant_results
    }
    run_rows: list[dict[str, Any]] = []
    correlation_rows: list[dict[str, Any]] = []
    for strategy in strategies:
        for ratio in ratios:
            for seed in seeds:
                sampled, manifest = sample_catalog(
                    catalog,
                    strategy=strategy,
                    ratio=ratio,
                    sample_size=None,
                    minimum_sample_size=minimum_sample_size,
                    minimum_per_stratum=minimum_per_stratum,
                    seed=seed,
                    census_layers=census_layers,
                    generated_at="pilot-simulation",
                )
                sampled_by_id = {item["mutant_id"]: item for item in sampled["mutants"]}
                per_layer: dict[str, tuple[list[float], list[float]]] = {}
                for participant_id, full_rows in participant_results:
                    sampled_rows = [
                        {**row, **sampled_by_id[row["mutant_id"]]}
                        for row in full_rows
                        if row["mutant_id"] in sampled_by_id
                    ]
                    for layer in LAYERS:
                        source_layer_count = len(_layer_rows(catalog["mutants"], layer))
                        sample_layer_count = len(_layer_rows(sampled_rows, layer))
                        sampled_score = weighted_mutation_summary(
                            _layer_rows(sampled_rows, layer)
                        )["estimated_mutation_score"]
                        full_score = full_scores[participant_id][layer]
                        full_rank_values = [
                            full_scores[item_id][layer]
                            for item_id, _rows in participant_results
                        ]
                        sampled_rank_values = per_layer.setdefault(layer, ([], []))[1]
                        per_layer[layer][0].append(full_score)
                        sampled_rank_values.append(sampled_score)
                        run_rows.append(
                            {
                                "strategy": strategy,
                                "ratio": ratio,
                                "seed": seed,
                                "layer": layer,
                                "participant_id": participant_id,
                                "source_catalog_size": len(catalog["mutants"]),
                                "sample_size": len(sampled["mutants"]),
                                "sampling_frame_size": manifest["sampling_frame_size"],
                                "sampled_from_frame": manifest["sampled_from_frame"],
                                "effective_sampling_ratio": manifest[
                                    "effective_sampling_ratio"
                                ],
                                "source_layer_count": source_layer_count,
                                "sample_layer_count": sample_layer_count,
                                "layer_represented": (
                                    layer == "combined"
                                    or source_layer_count == 0
                                    or sample_layer_count > 0
                                ),
                                "execution_cost_ratio": len(sampled["mutants"])
                                / len(catalog["mutants"]),
                                "full_score": full_score,
                                "sampled_score": sampled_score,
                                "absolute_error": abs(sampled_score - full_score),
                                "full_rank": _ranks(full_rank_values)[
                                    [item[0] for item in participant_results].index(
                                        participant_id
                                    )
                                ],
                                "sampled_catalog_hash": sampled["catalog_hash"],
                                "sampling_manifest_hash": manifest["manifest_hash"],
                            }
                        )
                for layer, (actual, predicted) in per_layer.items():
                    predicted_ranks = _ranks(predicted)
                    actual_ranks = _ranks(actual)
                    for row in run_rows[-len(participant_results) * len(LAYERS) :]:
                        if row["layer"] == layer:
                            index = [item[0] for item in participant_results].index(
                                row["participant_id"]
                            )
                            row["sampled_rank"] = predicted_ranks[index]
                            row["rank_change"] = (
                                predicted_ranks[index] - actual_ranks[index]
                            )
                    correlation_rows.append(
                        {
                            "strategy": strategy,
                            "ratio": ratio,
                            "seed": seed,
                            "layer": layer,
                            "adjusted_r_squared": adjusted_r_squared(actual, predicted),
                            "kendall_tau_b": kendall_tau_b(actual, predicted),
                            "spearman_rho": spearman_rho(actual, predicted),
                            "ranking_changes": sum(
                                left != right
                                for left, right in zip(
                                    actual_ranks, predicted_ranks, strict=True
                                )
                            ),
                        }
                    )

    grouped_runs: dict[tuple[str, float, str], list[dict[str, Any]]] = defaultdict(list)
    grouped_correlations: dict[tuple[str, float, str], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for row in run_rows:
        grouped_runs[(row["strategy"], row["ratio"], row["layer"])].append(row)
    for row in correlation_rows:
        grouped_correlations[(row["strategy"], row["ratio"], row["layer"])].append(row)
    summary_rows: list[dict[str, Any]] = []
    for key, rows in sorted(grouped_runs.items()):
        strategy, ratio, layer = key
        errors = [row["absolute_error"] for row in rows]
        correlations = grouped_correlations[key]
        participant_samples: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            participant_samples[row["participant_id"]].append(row["sampled_score"])
        row = {
            "strategy": strategy,
            "ratio": ratio,
            "layer": layer,
            "runs": len(correlations),
            "sample_size_mean": statistics.fmean(item["sample_size"] for item in rows),
            "sampled_from_frame_mean": statistics.fmean(
                item["sampled_from_frame"] for item in rows
            ),
            "effective_sampling_ratio_mean": statistics.fmean(
                item["effective_sampling_ratio"] for item in rows
            ),
            "execution_cost_ratio_mean": statistics.fmean(
                item["execution_cost_ratio"] for item in rows
            ),
            "mean_absolute_error": statistics.fmean(errors),
            "median_absolute_error": statistics.median(errors),
            "p95_absolute_error": _percentile(errors, 0.95),
            "rmse": math.sqrt(statistics.fmean(error**2 for error in errors)),
            "adjusted_r_squared_mean": statistics.fmean(
                item["adjusted_r_squared"] for item in correlations
            ),
            "kendall_tau_b_mean": statistics.fmean(
                item["kendall_tau_b"] for item in correlations
            ),
            "spearman_rho_mean": statistics.fmean(
                item["spearman_rho"] for item in correlations
            ),
            "participant_ranking_changes_mean": statistics.fmean(
                item["ranking_changes"] for item in correlations
            ),
            "sampling_standard_deviation_mean": statistics.fmean(
                statistics.pstdev(values) for values in participant_samples.values()
            ),
            "all_runs_layer_represented": all(
                item["layer_represented"] for item in rows
            ),
        }
        row["accepted"] = (
            layer == acceptance_layer
            and all(
                item["layer_represented"]
                for candidate_layer in ("specified", "extended")
                for item in grouped_runs[(strategy, ratio, candidate_layer)]
            )
            and row["median_absolute_error"] <= thresholds["median_absolute_error"]
            and row["p95_absolute_error"] <= thresholds["p95_absolute_error"]
            and row["adjusted_r_squared_mean"] >= thresholds["adjusted_r_squared"]
            and row["kendall_tau_b_mean"] >= thresholds["kendall_tau_b"]
            and row["spearman_rho_mean"] >= thresholds["spearman_rho"]
        )
        summary_rows.append(row)
    accepted = [row for row in summary_rows if row["accepted"]]
    recommended = min(
        accepted,
        key=lambda item: (
            item["execution_cost_ratio_mean"],
            item["mean_absolute_error"],
            item["strategy"],
        ),
        default=None,
    )
    return {
        "sampling_runs": run_rows,
        "sampling_summary": summary_rows,
        "sampling_rank_correlations": correlation_rows,
        "recommended": recommended,
        "thresholds": thresholds,
        "acceptance_layer": acceptance_layer,
        "census_layers": list(census_layers),
    }


def _parse_numbers(values: str, cast: Any) -> list[Any]:
    return [cast(value.strip()) for value in values.split(",") if value.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate sampled scores against a full mutation matrix."
    )
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument(
        "--protocol",
        type=Path,
        default=Path(__file__).with_name("mutation_sampling_protocol.json"),
    )
    parser.add_argument("--strategies")
    parser.add_argument("--ratios")
    parser.add_argument("--seeds")
    parser.add_argument("--minimum-sample-size", type=int)
    parser.add_argument("--minimum-per-stratum", type=int)
    parser.add_argument("--thresholds", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog.resolve())
        protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
        thresholds = {
            **DEFAULT_THRESHOLDS,
            **protocol.get("acceptance_thresholds", {}),
        }
        if args.thresholds:
            thresholds.update(json.loads(args.thresholds.read_text(encoding="utf-8")))
        results = _validated_results(catalog, _result_paths(args.results))
        payload = analyze_sampling(
            catalog,
            results,
            strategies=(
                _parse_numbers(args.strategies, str)
                if args.strategies
                else protocol["strategies"]
            ),
            ratios=(
                _parse_numbers(args.ratios, float)
                if args.ratios
                else protocol["ratios"]
            ),
            seeds=(
                _parse_numbers(args.seeds, int) if args.seeds else protocol["seeds"]
            ),
            minimum_sample_size=(
                args.minimum_sample_size
                if args.minimum_sample_size is not None
                else protocol["minimum_sample_size"]
            ),
            minimum_per_stratum=(
                args.minimum_per_stratum
                if args.minimum_per_stratum is not None
                else protocol["minimum_per_stratum"]
            ),
            thresholds=thresholds,
            census_layers=protocol.get("census_layers", []),
            acceptance_layer=protocol.get("acceptance_layer", "combined"),
        )
        output_dir = args.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        write_csv(
            output_dir / "sampling_runs.csv",
            tuple(payload["sampling_runs"][0]),
            payload["sampling_runs"],
        )
        write_csv(
            output_dir / "sampling_summary.csv",
            tuple(payload["sampling_summary"][0]),
            payload["sampling_summary"],
        )
        write_csv(
            output_dir / "sampling_rank_correlations.csv",
            tuple(payload["sampling_rank_correlations"][0]),
            payload["sampling_rank_correlations"],
        )
        write_json(
            output_dir / "recommended_sampling_strategy.json",
            {"thresholds": thresholds, "recommended": payload["recommended"]},
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Recommended: {payload['recommended']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
