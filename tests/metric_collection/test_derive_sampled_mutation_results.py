from typing import Any

from scripts.metric_collection.derive_sampled_mutation_results import derive_result
from scripts.metric_collection.mutation_common import catalog_hash


def _mutant(number: int, layer: str) -> dict[str, Any]:
    return {
        "mutant_id": f"M{number}",
        "mutant_name": f"example__mutmut_{number}",
        "module": "example.py",
        "function": "example",
        "source_line": number,
        "workload_layer": layer,
        "diff": f"--- example.py\n+++ example.py\n@@ -{number},1 +{number},1 @@\n-a\n+b\n",
        "review_status": "unreviewed",
    }


def test_derive_result_filters_full_matrix_and_recalculates_weighted_scores() -> None:
    full_mutants = [
        _mutant(1, "specified"),
        _mutant(2, "specified"),
        _mutant(3, "extended_only"),
    ]
    full_hash = catalog_hash(full_mutants)
    sampled_mutants = [
        {
            **full_mutants[0],
            "sampling_stratum": "specified",
            "stratum_population": 2,
            "stratum_sample_size": 1,
            "sampling_weight": 2.0,
        },
        {
            **full_mutants[2],
            "sampling_stratum": "CENSUS | extended_only",
            "stratum_population": 1,
            "stratum_sample_size": 1,
            "sampling_weight": 1.0,
        },
    ]
    sampled_catalog = {
        "catalog_kind": "sampled",
        "catalog_hash": catalog_hash(sampled_mutants),
        "source_catalog_hash": full_hash,
        "baseline_commit": "baseline",
        "mutants": sampled_mutants,
    }
    full_payload = {
        "participant": {"participant_id": "experiment-01", "status": "collected"},
        "mutation": {
            "catalog_hash": full_hash,
            "summary": {"valid_tests_included": 5, "invalid_tests_excluded": 0},
            "mutants": [
                {**full_mutants[0], "status": "killed"},
                {**full_mutants[1], "status": "survived"},
                {**full_mutants[2], "status": "survived"},
            ],
        },
    }

    derived = derive_result(sampled_catalog, full_payload)

    assert [item["mutant_id"] for item in derived["mutation"]["mutants"]] == [
        "M1",
        "M3",
    ]
    assert (
        derived["mutation"]["summary"]["specified"]["estimated_mutation_score"] == 1.0
    )
    assert derived["mutation"]["summary"]["extended"]["mutation_score"] == 0.0
