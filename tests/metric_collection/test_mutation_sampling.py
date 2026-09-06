from copy import deepcopy
import csv
from pathlib import Path
from typing import Any

import pytest

from scripts.metric_collection.analyze_sampling_pilot import (
    DEFAULT_THRESHOLDS,
    adjusted_r_squared,
    analyze_sampling,
    kendall_tau_b,
    spearman_rho,
)
from scripts.metric_collection.classify_mutation_operators import (
    classify_operator_family,
)
from scripts.metric_collection.mutation_common import (
    catalog_hash,
    weighted_mutation_summary,
)
from scripts.metric_collection.sample_mutant_catalog import sample_catalog, write_sample


def _catalog(size: int = 60) -> dict[str, Any]:
    mutants = [
        {
            "mutant_id": f"M{number:03d}",
            "mutant_name": f"example.function__mutmut_{number}",
            "module": "example.py",
            "function": "first" if number < size // 2 else "second",
            "source_line": number + 1,
            "workload_layer": "extended_only" if number % 5 == 0 else "specified",
            "operator_family": "COMPARISON" if number % 2 else "ARITHMETIC",
            "diff": f"--- example.py\n+++ example.py\n@@ -{number + 1},1 +{number + 1},1 @@\n-return 1\n+return 2\n",
            "review_status": "unreviewed",
        }
        for number in range(size)
    ]
    return {"catalog_hash": catalog_hash(mutants), "mutants": mutants}


def _sample(
    catalog: dict[str, Any], seed: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    return sample_catalog(
        deepcopy(catalog),
        strategy="layer_function_operator_stratified",
        ratio=0.2,
        sample_size=None,
        minimum_sample_size=12,
        minimum_per_stratum=1,
        seed=seed,
        generated_at="fixed",
    )


def test_sampling_is_deterministic_without_replacement() -> None:
    catalog = _catalog()
    first, first_manifest = _sample(catalog, 7)
    repeated, repeated_manifest = _sample(catalog, 7)
    different, _manifest = _sample(catalog, 8)
    ids = [item["mutant_id"] for item in first["mutants"]]
    assert first == repeated
    assert first_manifest == repeated_manifest
    assert first["catalog_hash"] != different["catalog_hash"]
    assert len(ids) == len(set(ids))
    assert set(ids) <= {item["mutant_id"] for item in catalog["mutants"]}
    assert {item["workload_layer"] for item in first["mutants"]} == {
        "specified",
        "extended_only",
    }


def test_minimum_per_stratum_can_increase_actual_sample_size() -> None:
    sampled, manifest = sample_catalog(
        _catalog(),
        strategy="layer_function_operator_stratified",
        ratio=None,
        sample_size=1,
        minimum_sample_size=1,
        minimum_per_stratum=2,
        seed=1,
        generated_at="fixed",
    )
    assert len(sampled["mutants"]) > 1
    assert all(
        row["sample_size"] >= min(2, row["population"]) for row in manifest["strata"]
    )
    assert all(
        item["sampling_weight"]
        == item["stratum_population"] / item["stratum_sample_size"]
        for item in sampled["mutants"]
    )


def test_sampling_manifest_csv_contains_reproducibility_metadata(
    tmp_path: Path,
) -> None:
    write_sample(
        _catalog(),
        tmp_path,
        strategy="operator_stratified",
        ratio=0.5,
        sample_size=None,
        minimum_sample_size=1,
        minimum_per_stratum=1,
        seed=17,
        generated_at="fixed",
    )
    with (tmp_path / "sampling_manifest.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows
    assert {row["strategy"] for row in rows} == {"operator_stratified"}
    assert {row["seed"] for row in rows} == {"17"}
    assert all(
        row["source_catalog_hash"] and row["sampled_catalog_hash"] for row in rows
    )


def test_extended_layer_can_be_kept_as_a_census() -> None:
    catalog = _catalog()
    sampled, manifest = sample_catalog(
        catalog,
        strategy="operator_stratified",
        ratio=0.2,
        sample_size=None,
        minimum_sample_size=10,
        minimum_per_stratum=1,
        seed=3,
        census_layers=["extended_only"],
        generated_at="fixed",
    )
    source_extended = {
        item["mutant_id"]
        for item in catalog["mutants"]
        if item["workload_layer"] == "extended_only"
    }
    sampled_extended = {
        item["mutant_id"]
        for item in sampled["mutants"]
        if item["workload_layer"] == "extended_only"
    }
    assert sampled_extended == source_extended
    assert manifest["census_mutants"] == len(source_extended)
    assert manifest["sampling_frame_size"] == len(catalog["mutants"]) - len(
        source_extended
    )
    assert all(
        item["sampling_weight"] == 1.0
        for item in sampled["mutants"]
        if item["workload_layer"] == "extended_only"
    )


def test_weighted_score_uses_population_weights() -> None:
    rows = [
        {
            "status": "killed",
            "sampling_weight": 9.0,
            "sampling_stratum": "large",
            "stratum_population": 9,
        },
        {
            "status": "survived",
            "sampling_weight": 1.0,
            "sampling_stratum": "small",
            "stratum_population": 1,
        },
    ]
    summary = weighted_mutation_summary(rows)
    assert summary["mutation_score"] == 0.5
    assert summary["estimated_mutation_score"] == 0.9
    assert summary["estimated_ci95_lower"] == 0.0
    assert summary["estimated_ci95_upper"] == 1.0


@pytest.mark.parametrize(
    ("original", "mutated", "expected"),
    [
        ("if value < limit:", "if value <= limit:", "COMPARISON"),
        ("return value + 1", "return value - 1", "ARITHMETIC"),
        ("if first and second:", "if first or second:", "BOOLEAN_CONNECTOR"),
        ("continue", "break", "CONTROL_FLOW"),
        ("return value", "return None", "RETURN_VALUE"),
    ],
)
def test_operator_classification(original: str, mutated: str, expected: str) -> None:
    diff = f"--- example.py\n+++ example.py\n@@ -1,1 +1,1 @@\n-{original}\n+{mutated}\n"
    assert classify_operator_family(diff) == expected


def test_rank_statistics_handle_order_and_ties() -> None:
    assert spearman_rho([1, 2, 3], [3, 2, 1]) == -1.0
    assert kendall_tau_b([1, 2, 3], [3, 2, 1]) == -1.0
    assert spearman_rho([1, 1, 2], [1, 1, 2]) == 1.0
    assert kendall_tau_b([1, 1, 2], [1, 1, 2]) == 1.0
    assert adjusted_r_squared([0.1, 0.4, 0.9], [0.1, 0.4, 0.9]) == 1.0


def test_sampling_pilot_accepts_census_and_does_not_select_failed_strategy() -> None:
    catalog = _catalog(12)
    participants = [
        (
            f"experiment-{number:02d}",
            [
                {**item, "status": "killed" if index < number * 2 else "survived"}
                for index, item in enumerate(catalog["mutants"])
            ],
        )
        for number in range(1, 5)
    ]
    payload = analyze_sampling(
        catalog,
        participants,
        strategies=["base_random"],
        ratios=[1.0],
        seeds=[1, 2],
        minimum_sample_size=1,
        minimum_per_stratum=1,
        thresholds=DEFAULT_THRESHOLDS,
    )
    assert payload["recommended"] is not None
    assert payload["recommended"]["mean_absolute_error"] == 0.0
    assert all(row["rank_change"] == 0 for row in payload["sampling_runs"])

    payload = analyze_sampling(
        catalog,
        participants,
        strategies=["base_random"],
        ratios=[0.1],
        seeds=[1, 2],
        minimum_sample_size=1,
        minimum_per_stratum=1,
        thresholds={**DEFAULT_THRESHOLDS, "median_absolute_error": -1.0},
    )
    assert payload["recommended"] is None
