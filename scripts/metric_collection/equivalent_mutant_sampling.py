from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Sequence
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist
import sys
from typing import Any

try:
    from scripts.metric_collection.aggregate_mutant_outcomes import (
        BLINDED_REVIEW_COLUMNS,
    )
    from scripts.metric_collection.mutation_common import canonical_json
    from scripts.metric_collection.mutation_common import write_csv, write_json
except ModuleNotFoundError:  # pragma: no cover
    from aggregate_mutant_outcomes import (  # type: ignore[no-redef]
        BLINDED_REVIEW_COLUMNS,
    )
    from mutation_common import canonical_json  # type: ignore[no-redef]
    from mutation_common import write_csv, write_json  # type: ignore[no-redef]


STRATUM_FIELDS = ("workload_layer", "operator_family")
RESOLVED_REVIEW_STATUSES = frozenset(
    {"confirmed_equivalent", "non_equivalent", "duplicate"}
)
SCOREABLE_MUTANT_STATUSES = frozenset({"killed", "survived", "no_tests"})
DEFAULT_PLANNED_SAMPLE_SIZES = (100, 150, 225, 313)
DESIGN_COLUMNS = (
    *BLINDED_REVIEW_COLUMNS,
    "sampling_stratum",
    "stratum_population",
    "stratum_sample_size",
    "inclusion_probability",
    "sampling_weight",
    "within_stratum_rank",
    "cluster_id",
    "cluster_multiplicity",
)
REVIEW_EVIDENCE_COLUMNS = tuple(
    column
    for column in BLINDED_REVIEW_COLUMNS
    if not column.startswith("reviewer_")
    and column not in {"adjudicated_status", "adjudication_reason"}
)
REVIEWER_COLUMNS = {
    "reviewer_1": (*REVIEW_EVIDENCE_COLUMNS, "reviewer_1_status", "reviewer_1_reason"),
    "reviewer_2": (*REVIEW_EVIDENCE_COLUMNS, "reviewer_2_status", "reviewer_2_reason"),
}
PARTICIPANT_COLUMNS = (
    "participant_id",
    "participant_number",
    "status",
    "catalog_hash",
    "baseline_valid_only_passed",
    "valid_tests_included",
    "invalid_tests_excluded",
)
LAYER_RAW_FIELDS = (
    "catalog_total",
    "killed",
    "survived",
    "no_tests",
    "timeout",
    "eligible_mutants",
    "eligible_killed",
    "raw_mutation_score",
)
LAYER_ESTIMATE_FIELDS = (
    "estimated_equivalent",
    "estimated_adjusted_score",
    "estimated_ci95_lower",
    "estimated_ci95_upper",
    "interval_half_width",
    "stopping_interval_half_width",
)
ESTIMATE_COLUMNS = (
    *PARTICIPANT_COLUMNS,
    *(
        f"{layer}_{field}"
        for layer in ("specified", "extended", "combined")
        for field in (*LAYER_RAW_FIELDS, *LAYER_ESTIMATE_FIELDS)
    ),
    "reviewed_sample_size",
    "sampling_seed",
    "weighting_method",
    "confidence_level",
    "review_artifact_hash",
    "reviewed_catalog_artifact_hash",
    "decision_status_hash",
    "participant_matrix_hash",
    "automatic_witness_count",
    "confirmed_equivalent_sample_count",
    "unresolved_sample_count",
    "target_half_width",
    "stopping_interval_method",
    "stopping_confidence_level",
    "current_look",
    "next_planned_sample_size",
    "all_primary_intervals_within_target",
)
ADJUDICATION_COLUMNS = (
    "mutant_id",
    "adjudicated_status",
    "adjudication_reason",
)


def _stratum_key(row: dict[str, Any]) -> str:
    return " | ".join(str(row.get(field, "OTHER")) for field in STRATUM_FIELDS)


def _allocate_stratum_sample_sizes(
    populations: dict[str, int], target: int, minimum_per_stratum: int
) -> dict[str, int]:
    allocations = {
        key: min(population, minimum_per_stratum)
        for key, population in populations.items()
    }
    target = min(sum(populations.values()), max(target, sum(allocations.values())))
    while sum(allocations.values()) < target:
        candidates = [
            key for key in sorted(populations) if allocations[key] < populations[key]
        ]
        selected = min(
            candidates,
            key=lambda key: (
                allocations[key] / populations[key],
                -populations[key],
                key,
            ),
        )
        allocations[selected] += 1
    return allocations


def _priority(seed: int, stratum: str, mutant_id: str) -> str:
    return hashlib.sha256(f"{seed}\0{stratum}\0{mutant_id}".encode()).hexdigest()


def plan_review_sample(
    candidates: list[dict[str, Any]],
    *,
    sample_size: int,
    seed: int,
    minimum_per_stratum: int = 2,
    generated_at: str | None = None,
    planned_sample_sizes: Sequence[int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create a reproducible, nested stratified review sample."""
    if not candidates:
        raise ValueError("cannot sample an empty review population")
    if sample_size <= 0:
        raise ValueError("sample size must be positive")
    if minimum_per_stratum < 1:
        raise ValueError("minimum per stratum must be positive")
    planned_sizes = list(
        planned_sample_sizes
        if planned_sample_sizes is not None
        else dict.fromkeys((sample_size, len(candidates)))
    )
    if (
        planned_sizes != sorted(set(planned_sizes))
        or sample_size not in planned_sizes
        or any(size <= 0 or size > len(candidates) for size in planned_sizes)
    ):
        raise ValueError(
            "planned sample sizes must be unique, increasing, in range, and include "
            "the current sample size"
        )
    ids = [str(row.get("mutant_id", "")) for row in candidates]
    if any(not mutant_id for mutant_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("candidate mutant IDs must be unique non-empty strings")

    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidates:
        strata[_stratum_key(row)].append(row)
    populations = {key: len(rows) for key, rows in strata.items()}
    allocations = _allocate_stratum_sample_sizes(
        populations, sample_size, minimum_per_stratum
    )

    sampled: list[dict[str, Any]] = []
    stratum_summaries: list[dict[str, Any]] = []
    for key in sorted(strata):
        population = populations[key]
        selected_count = allocations[key]
        ordered = sorted(
            strata[key],
            key=lambda row: (
                _priority(seed, key, str(row["mutant_id"])),
                row["mutant_id"],
            ),
        )
        probability = selected_count / population
        for rank, row in enumerate(ordered[:selected_count], start=1):
            sampled.append(
                {
                    **row,
                    "sampling_stratum": key,
                    "stratum_population": population,
                    "stratum_sample_size": selected_count,
                    "inclusion_probability": probability,
                    "sampling_weight": 1.0 / probability,
                    "within_stratum_rank": rank,
                    "cluster_id": row["mutant_id"],
                    "cluster_multiplicity": 1,
                }
            )
        stratum_summaries.append(
            {
                "sampling_stratum": key,
                "population": population,
                "sample_size": selected_count,
                "inclusion_probability": probability,
                "sampling_weight": 1.0 / probability,
            }
        )
    sampled.sort(key=lambda row: row["mutant_id"])
    frame_identity = [
        {
            "mutant_id": row["mutant_id"],
            "sampling_stratum": _stratum_key(row),
            "cluster_id": row["mutant_id"],
            "cluster_multiplicity": 1,
        }
        for row in sorted(candidates, key=lambda row: row["mutant_id"])
    ]
    selected_identity = [
        {
            "mutant_id": row["mutant_id"],
            "sampling_stratum": row["sampling_stratum"],
            "inclusion_probability": row["inclusion_probability"],
        }
        for row in sampled
    ]
    manifest_identity = {
        "sampling_frame_hash": hashlib.sha256(
            canonical_json(frame_identity).encode()
        ).hexdigest(),
        "sample_hash": hashlib.sha256(
            canonical_json(selected_identity).encode()
        ).hexdigest(),
        "sampling_frame_size": len(candidates),
        "requested_sample_size": sample_size,
        "actual_sample_size": len(sampled),
        "planned_sample_sizes": planned_sizes,
        "current_look": planned_sizes.index(sample_size) + 1,
        "seed": seed,
        "stratum_fields": list(STRATUM_FIELDS),
        "minimum_per_stratum": minimum_per_stratum,
        "allocation_method": "sequential_equal_fraction_with_minimum",
        "selection_method": "sha256_priority_without_replacement",
        "cluster_method": "identity_no_automatic_clustering",
        "strata": stratum_summaries,
        "sampled_mutant_ids": [row["mutant_id"] for row in sampled],
    }
    manifest = {
        "schema_version": 1,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        **manifest_identity,
        "manifest_hash": hashlib.sha256(
            canonical_json(manifest_identity).encode()
        ).hexdigest(),
    }
    return sampled, manifest


def _estimated_total_and_variance_bound(
    sample: list[dict[str, Any]],
    decisions: dict[str, str],
    *,
    participant_statuses: dict[str, str] | None = None,
) -> tuple[float, float]:
    estimate = 0.0
    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sample:
        if int(row.get("cluster_multiplicity", 1)) != 1:
            raise ValueError("cluster multiplicities require a cluster sampling design")
        strata[str(row["sampling_stratum"])].append(row)
        is_equivalent = decisions[str(row["mutant_id"])] == "confirmed_equivalent"
        is_scoreable = participant_statuses is None or participant_statuses.get(
            str(row["mutant_id"])
        ) in SCOREABLE_MUTANT_STATUSES
        if is_equivalent and is_scoreable:
            estimate += float(row["sampling_weight"])

    variance_bound = 0.0
    for rows in strata.values():
        population = int(rows[0]["stratum_population"])
        sampled_count = int(rows[0]["stratum_sample_size"])
        if sampled_count != len(rows):
            raise ValueError(
                "sample rows do not match the recorded stratum sample size"
            )
        if any(int(row["stratum_population"]) != population for row in rows):
            raise ValueError("inconsistent stratum population")
        if sampled_count < population:
            variance_bound += (
                population**2
                * (1.0 - sampled_count / population)
                * 0.25
                * population
                / (population - 1)
                / sampled_count
            )
    return estimate, variance_bound


def _validate_sample_design(sample: list[dict[str, Any]]) -> None:
    for row in sample:
        population = int(row["stratum_population"])
        sampled_count = int(row["stratum_sample_size"])
        if population <= 0 or not 0 < sampled_count <= population:
            raise ValueError("invalid stratum population or sample size")
        expected_probability = sampled_count / population
        if not math.isclose(
            float(row["inclusion_probability"]), expected_probability
        ):
            raise ValueError("inclusion probability does not match sample design")
        if not math.isclose(
            float(row["sampling_weight"]), 1.0 / expected_probability
        ):
            raise ValueError("design weight does not match inclusion probability")


def _validate_sampling_provenance(
    collection_manifest: dict[str, Any],
    global_outcomes: dict[str, Any],
    sampling_manifest: dict[str, Any],
    sample: list[dict[str, Any]],
) -> None:
    manifest_identity = {
        key: value
        for key, value in sampling_manifest.items()
        if key not in {"generated_at", "manifest_hash"}
    }
    expected_manifest_hash = hashlib.sha256(
        canonical_json(manifest_identity).encode()
    ).hexdigest()
    if sampling_manifest.get("manifest_hash") != expected_manifest_hash:
        raise ValueError("sampling manifest hash does not match its contents")
    expected_global_hash = hashlib.sha256(
        canonical_json(global_outcomes).encode()
    ).hexdigest()
    if sampling_manifest.get("global_outcomes_hash") != expected_global_hash:
        raise ValueError("global outcomes hash does not match sampling provenance")
    for field in ("catalog_hash", "sut_hash", "execution_policy_hash"):
        if sampling_manifest.get(field) != global_outcomes.get(field):
            raise ValueError(f"{field} does not match sampling provenance")
    if (
        collection_manifest.get("execution_policy_hash")
        != global_outcomes.get("execution_policy_hash")
    ):
        raise ValueError("collection policy does not match global outcomes")

    expected_sample, expected_manifest = plan_review_sample(
        global_outcomes["review_candidates"],
        sample_size=int(sampling_manifest["requested_sample_size"]),
        seed=int(sampling_manifest["seed"]),
        minimum_per_stratum=int(sampling_manifest["minimum_per_stratum"]),
        generated_at="provenance-check",
        planned_sample_sizes=sampling_manifest["planned_sample_sizes"],
    )
    for field in (
        "sampling_frame_hash",
        "sample_hash",
        "sampling_frame_size",
        "requested_sample_size",
        "actual_sample_size",
        "seed",
        "stratum_fields",
        "minimum_per_stratum",
        "allocation_method",
        "selection_method",
        "cluster_method",
        "strata",
        "sampled_mutant_ids",
    ):
        if sampling_manifest.get(field) != expected_manifest[field]:
            raise ValueError(f"sample provenance mismatch: {field}")
    design_fields = (
        "mutant_id",
        "workload_layer",
        "operator_family",
        "sampling_stratum",
        "stratum_population",
        "stratum_sample_size",
        "inclusion_probability",
        "sampling_weight",
        "within_stratum_rank",
        "cluster_id",
        "cluster_multiplicity",
    )
    observed_design = [
        {field: row.get(field) for field in design_fields}
        for row in sorted(sample, key=lambda row: row["mutant_id"])
    ]
    expected_design = [
        {field: row.get(field) for field in design_fields}
        for row in expected_sample
    ]
    if observed_design != expected_design:
        raise ValueError("sample rows do not match deterministic sampling provenance")


def _count_interval(
    estimate: float,
    variance_bound: float,
    maximum: float,
    *,
    confidence_level: float = 0.95,
) -> tuple[float, float]:
    quantile = (1.0 + confidence_level) / 2.0
    margin = NormalDist().inv_cdf(quantile) * math.sqrt(max(0.0, variance_bound))
    return max(0.0, estimate - margin), min(maximum, estimate + margin)


def estimate_adjusted_scores(
    collection_manifest: dict[str, Any],
    global_outcomes: dict[str, Any],
    sampling_manifest: dict[str, Any],
    sample: list[dict[str, Any]],
    decisions: dict[str, str],
    participant_matrix: dict[str, dict[str, str]],
    review_provenance: dict[str, str],
    *,
    target_half_width: float,
) -> dict[str, Any]:
    """Estimate equivalent-adjusted scores from a completed probability sample."""
    catalog_hashes = {
        collection_manifest.get("catalog_hash"),
        global_outcomes.get("catalog_hash"),
        sampling_manifest.get("catalog_hash"),
    }
    if len(catalog_hashes) != 1 or None in catalog_hashes:
        raise ValueError("catalog hashes do not match")
    if not 0 < target_half_width < 1:
        raise ValueError("target half width must be in (0, 1)")
    sample_ids = {str(row.get("mutant_id", "")) for row in sample}
    if len(sample_ids) != len(sample) or "" in sample_ids:
        raise ValueError("sample mutant IDs must be unique non-empty strings")
    candidates = global_outcomes.get("review_candidates")
    if isinstance(candidates, list):
        candidate_ids = {str(row.get("mutant_id", "")) for row in candidates}
        if (
            sample_ids - candidate_ids
            or len(candidate_ids)
            != int(sampling_manifest.get("sampling_frame_size", -1))
        ):
            raise ValueError("sample does not match the global review population")
    if sample_ids != set(decisions):
        raise ValueError("decisions must cover exactly the sampled mutants")
    if any(status not in RESOLVED_REVIEW_STATUSES for status in decisions.values()):
        raise ValueError("every sampled mutant needs a resolved adjudication")
    for field in ("review_artifact_hash", "reviewed_catalog_artifact_hash"):
        if not review_provenance.get(field):
            raise ValueError(f"review provenance is missing {field}")
    if len(sample) != int(sampling_manifest.get("actual_sample_size", -1)):
        raise ValueError("sample size does not match sampling manifest")
    _validate_sample_design(sample)
    _validate_sampling_provenance(
        collection_manifest, global_outcomes, sampling_manifest, sample
    )
    if global_outcomes.get("participant_matrix") != participant_matrix:
        raise ValueError("participant matrix does not match global outcomes")
    decision_status_hash = hashlib.sha256(
        canonical_json(
            [
                {"mutant_id": mutant_id, "adjudicated_status": decisions[mutant_id]}
                for mutant_id in sorted(decisions)
            ]
        ).encode()
    ).hexdigest()
    participant_matrix_hash = hashlib.sha256(
        canonical_json(participant_matrix).encode()
    ).hexdigest()

    population_estimate, population_variance = _estimated_total_and_variance_bound(
        sample, decisions
    )
    review_population_size = int(sampling_manifest["sampling_frame_size"])
    population_lower, population_upper = _count_interval(
        population_estimate, population_variance, review_population_size
    )
    planned_sizes = list(
        sampling_manifest.get("planned_sample_sizes", [len(sample)])
    )
    stopping_confidence_level = 1.0 - 0.05 / len(planned_sizes)

    participant_rows: list[dict[str, Any]] = []
    for participant in collection_manifest.get("participants", []):
        if participant.get("status") != "collected":
            continue
        participant_id = str(participant["participant_id"])
        statuses = {
            mutant_id: values.get(participant_id, "")
            for mutant_id, values in participant_matrix.items()
        }
        if any(mutant_id not in statuses for mutant_id in sample_ids):
            raise ValueError(f"participant matrix is incomplete for {participant_id}")
        summary = participant.get("summary")
        if not isinstance(summary, dict):
            raise ValueError(f"participant summary is missing for {participant_id}")
        result: dict[str, Any] = {
            "participant_id": participant_id,
            "participant_number": participant["participant_number"],
            "status": participant["status"],
            "catalog_hash": collection_manifest["catalog_hash"],
            "baseline_valid_only_passed": summary.get(
                "baseline_valid_only_passed", True
            ),
            "valid_tests_included": summary["valid_tests_included"],
            "invalid_tests_excluded": summary["invalid_tests_excluded"],
        }
        for layer in ("specified", "extended", "combined"):
            source = summary[layer]
            raw_eligible = int(source["eligible_mutants"])
            raw_killed = int(source.get("eligible_killed", 0))
            layer_sample = (
                sample
                if layer == "combined"
                else [
                    row
                    for row in sample
                    if row.get("workload_layer")
                    == ("specified" if layer == "specified" else "extended_only")
                ]
            )
            equivalent, variance_bound = _estimated_total_and_variance_bound(
                layer_sample, decisions, participant_statuses=statuses
            )
            maximum_exclusion = max(0, raw_eligible - raw_killed)
            equivalent = min(equivalent, maximum_exclusion)
            lower_equivalent, upper_equivalent = _count_interval(
                equivalent, variance_bound, maximum_exclusion
            )
            stopping_lower_equivalent, stopping_upper_equivalent = _count_interval(
                equivalent,
                variance_bound,
                maximum_exclusion,
                confidence_level=stopping_confidence_level,
            )
            adjusted_denominator = raw_eligible - equivalent
            adjusted_score = (
                raw_killed / adjusted_denominator if adjusted_denominator else 0.0
            )
            lower_score = (
                raw_killed / (raw_eligible - lower_equivalent)
                if raw_eligible > lower_equivalent
                else 0.0
            )
            upper_score = (
                raw_killed / (raw_eligible - upper_equivalent)
                if raw_eligible > upper_equivalent
                else (1.0 if raw_killed else 0.0)
            )
            stopping_lower_score = (
                raw_killed / (raw_eligible - stopping_lower_equivalent)
                if raw_eligible > stopping_lower_equivalent
                else 0.0
            )
            stopping_upper_score = (
                raw_killed / (raw_eligible - stopping_upper_equivalent)
                if raw_eligible > stopping_upper_equivalent
                else (1.0 if raw_killed else 0.0)
            )
            result.update(
                {
                    f"{layer}_catalog_total": source.get("catalog_total"),
                    f"{layer}_killed": source.get("killed"),
                    f"{layer}_survived": source.get("survived"),
                    f"{layer}_no_tests": source.get("no_tests"),
                    f"{layer}_timeout": source.get("timeout"),
                    f"{layer}_eligible_mutants": raw_eligible,
                    f"{layer}_eligible_killed": raw_killed,
                    f"{layer}_raw_mutation_score": source["mutation_score"],
                    f"{layer}_estimated_equivalent": equivalent,
                    f"{layer}_estimated_adjusted_score": adjusted_score,
                    f"{layer}_estimated_ci95_lower": lower_score,
                    f"{layer}_estimated_ci95_upper": upper_score,
                    f"{layer}_interval_half_width": (upper_score - lower_score)
                    / 2.0,
                    f"{layer}_stopping_interval_half_width": (
                        stopping_upper_score - stopping_lower_score
                    )
                    / 2.0,
                }
            )
        participant_rows.append(result)
    participant_rows.sort(key=lambda row: row["participant_number"])
    primary_widths = [
        float(row["specified_stopping_interval_half_width"])
        for row in participant_rows
    ]
    current_index = planned_sizes.index(len(sample))
    planned_next_sample_size = (
        planned_sizes[current_index + 1]
        if current_index + 1 < len(planned_sizes)
        else None
    )
    all_primary_intervals_within_target = bool(primary_widths) and all(
        width <= target_half_width for width in primary_widths
    )
    return {
        "schema_version": 1,
        "catalog_hash": collection_manifest["catalog_hash"],
        "method": "stratified_horvitz_thompson_worst_case_fpc_normal_ci",
        "confidence_level": 0.95,
        "reviewed_sample_size": len(sample),
        "sampling_seed": sampling_manifest["seed"],
        **review_provenance,
        "decision_status_hash": decision_status_hash,
        "participant_matrix_hash": participant_matrix_hash,
        "review_population": {
            "population_size": review_population_size,
            "confirmed_equivalent_in_sample": sum(
                status == "confirmed_equivalent" for status in decisions.values()
            ),
            "estimated_equivalent": population_estimate,
            "estimated_equivalent_ci95_lower": population_lower,
            "estimated_equivalent_ci95_upper": population_upper,
            "estimated_equivalent_proportion": population_estimate
            / review_population_size,
            "auto_non_equivalent": global_outcomes.get("summary", {}).get(
                "auto_non_equivalent", 0
            ),
            "unresolved_in_sample": 0,
        },
        "participants": participant_rows,
        "stopping": {
            "primary_score": "specified_estimated_adjusted_score",
            "interval_method": "bonferroni_across_looks",
            "confidence_level": stopping_confidence_level,
            "target_half_width": target_half_width,
            "maximum_observed_half_width": max(primary_widths, default=None),
            "all_primary_intervals_within_target": (
                all_primary_intervals_within_target
            ),
            "planned_sample_sizes": planned_sizes,
            "current_look": current_index + 1,
            "next_planned_sample_size": (
                None
                if all_primary_intervals_within_target
                else planned_next_sample_size
            ),
        },
    }


def write_adjusted_score_outputs(
    estimates: dict[str, Any], output_dir: Path
) -> tuple[Path, Path]:
    """Write the auditable estimate payload and participant-level final CSV."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "mutation_score_estimates.json"
    csv_path = output_dir / "mutation_scores.csv"
    write_json(json_path, estimates)
    population = estimates["review_population"]
    stopping = estimates["stopping"]
    shared = {
        "reviewed_sample_size": estimates["reviewed_sample_size"],
        "sampling_seed": estimates["sampling_seed"],
        "weighting_method": estimates["method"],
        "confidence_level": estimates["confidence_level"],
        "review_artifact_hash": estimates["review_artifact_hash"],
        "reviewed_catalog_artifact_hash": estimates[
            "reviewed_catalog_artifact_hash"
        ],
        "decision_status_hash": estimates["decision_status_hash"],
        "participant_matrix_hash": estimates["participant_matrix_hash"],
        "automatic_witness_count": population["auto_non_equivalent"],
        "confirmed_equivalent_sample_count": population[
            "confirmed_equivalent_in_sample"
        ],
        "unresolved_sample_count": population["unresolved_in_sample"],
        "target_half_width": stopping["target_half_width"],
        "stopping_interval_method": stopping["interval_method"],
        "stopping_confidence_level": stopping["confidence_level"],
        "current_look": stopping["current_look"],
        "next_planned_sample_size": stopping["next_planned_sample_size"],
        "all_primary_intervals_within_target": stopping[
            "all_primary_intervals_within_target"
        ],
    }
    rows = [{**row, **shared} for row in estimates["participants"]]
    write_csv(csv_path, ESTIMATE_COLUMNS, rows)
    return json_path, csv_path


def write_review_sample(
    global_outcomes: dict[str, Any],
    output_dir: Path,
    *,
    sample_size: int,
    seed: int,
    minimum_per_stratum: int = 2,
    generated_at: str | None = None,
    previous_review_dir: Path | None = None,
    planned_sample_sizes: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Write the sample design and two participant-outcome-blinded templates."""
    artifact_names = (
        "sampling_manifest.json",
        "sample.csv",
        "reviewer_1.csv",
        "reviewer_2.csv",
        "adjudication.csv",
    )
    if any((output_dir / name).exists() for name in artifact_names):
        raise ValueError("output directory already contains review artifacts")
    candidates = global_outcomes.get("review_candidates")
    if not isinstance(candidates, list):
        raise ValueError("global outcomes are missing review_candidates")
    sampled, manifest = plan_review_sample(
        candidates,
        sample_size=sample_size,
        seed=seed,
        minimum_per_stratum=minimum_per_stratum,
        generated_at=generated_at,
        planned_sample_sizes=planned_sample_sizes,
    )
    provenance = {
        "catalog_hash": global_outcomes.get("catalog_hash"),
        "sut_hash": global_outcomes.get("sut_hash"),
        "execution_policy_hash": global_outcomes.get("execution_policy_hash"),
        "global_outcomes_hash": hashlib.sha256(
            canonical_json(global_outcomes).encode()
        ).hexdigest(),
    }
    previous_rows: dict[str, dict[str, dict[str, str]]] = {}
    previous_manifest: dict[str, Any] | None = None
    if previous_review_dir is not None:
        previous_manifest = json.loads(
            (previous_review_dir / "sampling_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        if (
            previous_manifest.get("sampling_frame_hash")
            != manifest["sampling_frame_hash"]
            or previous_manifest.get("seed") != seed
            or previous_manifest.get("planned_sample_sizes")
            != manifest["planned_sample_sizes"]
        ):
            raise ValueError(
                "previous review sample uses a different frame, seed, or schedule"
            )
        previous_ids = set(previous_manifest.get("sampled_mutant_ids", []))
        current_ids = {row["mutant_id"] for row in sampled}
        if not previous_ids < current_ids:
            raise ValueError(
                "new review sample must strictly expand the previous sample"
            )
        for name in ("reviewer_1", "reviewer_2", "adjudication"):
            with (previous_review_dir / f"{name}.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                previous_rows[name] = {
                    row["mutant_id"]: row for row in csv.DictReader(stream)
                }
    manifest_identity = {
        key: value
        for key, value in manifest.items()
        if key not in {"generated_at", "manifest_hash"}
    }
    manifest_identity.update(provenance)
    if previous_manifest is not None:
        manifest_identity.update(
            {
                "previous_manifest_hash": previous_manifest["manifest_hash"],
                "carried_forward_review_rows": previous_manifest[
                    "actual_sample_size"
                ],
                "new_review_rows": len(sampled)
                - int(previous_manifest["actual_sample_size"]),
            }
        )
    manifest = {
        "schema_version": 1,
        "generated_at": manifest["generated_at"],
        **manifest_identity,
        "manifest_hash": hashlib.sha256(
            canonical_json(manifest_identity).encode()
        ).hexdigest(),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "sampling_manifest.json", manifest)
    write_csv(output_dir / "sample.csv", DESIGN_COLUMNS, sampled)
    blinded_rows = [
        {column: row.get(column, "") for column in REVIEW_EVIDENCE_COLUMNS}
        for row in sampled
    ]
    for name in ("reviewer_1", "reviewer_2"):
        carried = previous_rows.get(name, {})
        columns = REVIEWER_COLUMNS[name]
        rows = [
            {
                **row,
                **{
                    column: carried.get(str(row["mutant_id"]), {}).get(
                        column, ""
                    )
                    for column in columns
                    if column not in REVIEW_EVIDENCE_COLUMNS
                },
            }
            for row in blinded_rows
        ]
        write_csv(output_dir / f"{name}.csv", columns, rows)
    prior_adjudication = previous_rows.get("adjudication", {})
    write_csv(
        output_dir / "adjudication.csv",
        ADJUDICATION_COLUMNS,
        (
            {
                "mutant_id": row["mutant_id"],
                "adjudicated_status": prior_adjudication.get(
                    str(row["mutant_id"]), {}
                ).get("adjudicated_status", ""),
                "adjudication_reason": prior_adjudication.get(
                    str(row["mutant_id"]), {}
                ).get("adjudication_reason", ""),
            }
            for row in sampled
        ),
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a stratified sample for equivalent-mutant review."
    )
    parser.add_argument("--global-outcomes", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20260915)
    parser.add_argument("--minimum-per-stratum", type=int, default=2)
    parser.add_argument("--previous-review-dir", type=Path)
    parser.add_argument(
        "--planned-sample-sizes",
        type=int,
        nargs="+",
        default=DEFAULT_PLANNED_SAMPLE_SIZES,
    )
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.global_outcomes.read_text(encoding="utf-8"))
        manifest = write_review_sample(
            payload,
            args.output_dir.resolve(),
            sample_size=args.sample_size,
            seed=args.seed,
            minimum_per_stratum=args.minimum_per_stratum,
            previous_review_dir=(
                args.previous_review_dir.resolve() if args.previous_review_dir else None
            ),
            planned_sample_sizes=args.planned_sample_sizes,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Review sample size: {manifest['actual_sample_size']}")
    print(f"Sampling manifest: {args.output_dir / 'sampling_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
