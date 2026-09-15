import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.metric_collection.equivalent_mutant_sampling import (
    estimate_adjusted_scores,
    main as sampling_main,
    plan_review_sample,
    write_adjusted_score_outputs,
    write_review_sample,
)
from scripts.metric_collection.mutation_common import canonical_json
from scripts.metric_collection.summarize_equivalent_mutant_sample import main


def _candidates() -> list[dict[str, Any]]:
    return [
        {
            "mutant_id": f"M{number:02d}",
            "workload_layer": "specified",
            "operator_family": "ARITHMETIC" if number < 6 else "CONTROL_FLOW",
        }
        for number in range(8)
    ] + [
        {
            "mutant_id": "M08",
            "workload_layer": "extended_only",
            "operator_family": "OTHER",
        }
    ]


def _sampling_inputs(
    global_outcomes: dict[str, Any], *, sample_size: int, seed: int
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sample, manifest = plan_review_sample(
        global_outcomes["review_candidates"],
        sample_size=sample_size,
        seed=seed,
        generated_at="fixed",
    )
    identity = {
        key: value
        for key, value in manifest.items()
        if key not in {"generated_at", "manifest_hash"}
    }
    identity.update(
        {
            "catalog_hash": global_outcomes["catalog_hash"],
            "sut_hash": global_outcomes.get("sut_hash"),
            "execution_policy_hash": global_outcomes.get("execution_policy_hash"),
            "global_outcomes_hash": hashlib.sha256(
                canonical_json(global_outcomes).encode()
            ).hexdigest(),
        }
    )
    return sample, {
        "schema_version": 1,
        "generated_at": "fixed",
        **identity,
        "manifest_hash": hashlib.sha256(canonical_json(identity).encode()).hexdigest(),
    }


def test_review_sample_is_reproducible_and_sequentially_nested() -> None:
    first, first_manifest = plan_review_sample(
        _candidates(), sample_size=5, seed=17, generated_at="fixed"
    )
    repeated, repeated_manifest = plan_review_sample(
        _candidates(), sample_size=5, seed=17, generated_at="fixed"
    )
    expanded, _expanded_manifest = plan_review_sample(
        _candidates(), sample_size=7, seed=17, generated_at="fixed"
    )

    assert first == repeated
    assert first_manifest == repeated_manifest
    assert {row["mutant_id"] for row in first} < {
        row["mutant_id"] for row in expanded
    }
    assert first_manifest["stratum_fields"] == [
        "workload_layer",
        "operator_family",
    ]


def test_review_sample_records_design_weights_and_censuses_tiny_strata() -> None:
    sampled, manifest = plan_review_sample(
        _candidates(), sample_size=5, seed=9, generated_at="fixed"
    )

    singleton = next(row for row in sampled if row["mutant_id"] == "M08")
    assert singleton["inclusion_probability"] == 1.0
    assert singleton["sampling_weight"] == 1.0
    assert singleton["cluster_multiplicity"] == 1
    assert singleton["cluster_id"] == "M08"
    assert all(
        row["inclusion_probability"]
        == row["stratum_sample_size"] / row["stratum_population"]
        for row in sampled
    )
    assert sum(row["sample_size"] for row in manifest["strata"]) == 5
    assert manifest["sampling_frame_size"] == 9
    assert manifest["actual_sample_size"] == 5


def test_write_review_sample_creates_blinded_templates_and_audit_manifest(
    tmp_path: Path,
) -> None:
    payload = {
        "catalog_hash": "catalog",
        "sut_hash": "sut",
        "execution_policy_hash": "policy",
        "review_candidates": _candidates(),
    }

    write_review_sample(
        payload,
        tmp_path,
        sample_size=5,
        seed=17,
        generated_at="fixed",
    )

    manifest = json.loads((tmp_path / "sampling_manifest.json").read_text())
    with (tmp_path / "reviewer_1.csv").open(newline="") as stream:
        reviewer_rows = list(csv.DictReader(stream))
    with (tmp_path / "sample.csv").open(newline="") as stream:
        sample_rows = list(csv.DictReader(stream))
    assert manifest["catalog_hash"] == "catalog"
    assert manifest["global_outcomes_hash"]
    assert manifest["planned_sample_sizes"] == [5, 9]
    assert len(reviewer_rows) == len(sample_rows) == 5
    assert (tmp_path / "adjudication.csv").is_file()
    assert "sampling_weight" not in reviewer_rows[0]
    assert "reviewer_2_status" not in reviewer_rows[0]
    assert "adjudicated_status" not in reviewer_rows[0]
    assert "sampling_weight" in sample_rows[0]
    assert not any("experiment-" in column for column in reviewer_rows[0])


def test_expanded_review_sample_preserves_prior_blinded_work(tmp_path: Path) -> None:
    payload = {
        "catalog_hash": "catalog",
        "sut_hash": "sut",
        "execution_policy_hash": "policy",
        "review_candidates": _candidates(),
    }
    first_dir = tmp_path / "first"
    expanded_dir = tmp_path / "expanded"
    write_review_sample(
        payload,
        first_dir,
        sample_size=5,
        seed=17,
        generated_at="first",
        planned_sample_sizes=[5, 7, 9],
    )
    reviewer_path = first_dir / "reviewer_1.csv"
    with reviewer_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
        columns = tuple(rows[0])
    rows[0]["reviewer_1_status"] = "non_equivalent"
    rows[0]["reviewer_1_reason"] = "counterexample"
    with reviewer_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    write_review_sample(
        payload,
        expanded_dir,
        sample_size=7,
        seed=17,
        generated_at="expanded",
        previous_review_dir=first_dir,
        planned_sample_sizes=[5, 7, 9],
    )

    with (expanded_dir / "reviewer_1.csv").open(newline="") as stream:
        expanded_rows = list(csv.DictReader(stream))
    preserved = next(
        row for row in expanded_rows if row["mutant_id"] == rows[0]["mutant_id"]
    )
    assert preserved["reviewer_1_status"] == "non_equivalent"
    assert preserved["reviewer_1_reason"] == "counterexample"
    assert len(expanded_rows) == 7


def test_review_sample_refuses_to_overwrite_existing_review_files(
    tmp_path: Path,
) -> None:
    payload = {"catalog_hash": "catalog", "review_candidates": _candidates()}
    write_review_sample(
        payload, tmp_path, sample_size=5, seed=17, generated_at="first"
    )

    with pytest.raises(ValueError, match="already contains review artifacts"):
        write_review_sample(
            payload, tmp_path, sample_size=5, seed=17, generated_at="second"
        )


def test_sampling_cli_defaults_to_staged_one_hundred_item_first_look(
    tmp_path: Path,
) -> None:
    global_path = tmp_path / "global.json"
    output_dir = tmp_path / "review"
    global_path.write_text(
        json.dumps(
            {
                "catalog_hash": "catalog",
                "sut_hash": "sut",
                "execution_policy_hash": "policy",
                "review_candidates": [
                    {
                        "mutant_id": f"M{number:03d}",
                        "workload_layer": "specified",
                        "operator_family": "ARITHMETIC",
                    }
                    for number in range(400)
                ],
            }
        )
    )

    assert (
        sampling_main(
            [
                "--global-outcomes",
                str(global_path),
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )
    manifest = json.loads((output_dir / "sampling_manifest.json").read_text())
    with (output_dir / "reviewer_1.csv").open(newline="") as stream:
        reviewer_rows = list(csv.DictReader(stream))

    assert manifest["actual_sample_size"] == 100
    assert manifest["planned_sample_sizes"] == [100, 150, 225, 313]
    assert len(reviewer_rows) == 100


def test_estimate_adjusted_scores_uses_design_weights_and_fpc_interval() -> None:
    manifest = {
        "catalog_hash": "catalog",
        "execution_policy_hash": "policy",
        "participants": [
            {
                "participant_id": "experiment-01",
                "participant_number": 1,
                "status": "collected",
                "summary": {
                    "baseline_valid_only_passed": True,
                    "valid_tests_included": 2,
                    "invalid_tests_excluded": 0,
                    "specified": {
                        "catalog_total": 12,
                        "killed": 5,
                        "survived": 4,
                        "no_tests": 1,
                        "timeout": 2,
                        "eligible_mutants": 10,
                        "eligible_killed": 5,
                        "mutation_score": 0.5,
                    },
                    "extended": {
                        "eligible_mutants": 0,
                        "eligible_killed": 0,
                        "mutation_score": 0.0,
                    },
                    "combined": {
                        "eligible_mutants": 10,
                        "eligible_killed": 5,
                        "mutation_score": 0.5,
                    },
                },
            }
        ],
    }
    candidates = [
        {
            "mutant_id": f"M{number}",
            "workload_layer": "specified",
            "operator_family": "ARITHMETIC",
        }
        for number in range(1, 5)
    ]
    global_outcomes = {
        "catalog_hash": "catalog",
        "sut_hash": "sut",
        "execution_policy_hash": "policy",
        "review_candidates": candidates,
        "summary": {"auto_non_equivalent": 6, "review_candidates": 4},
    }
    matrix = {
        row["mutant_id"]: {"experiment-01": "survived"} for row in candidates
    }
    global_outcomes["participant_matrix"] = matrix
    sample, sampling_manifest = _sampling_inputs(
        global_outcomes, sample_size=2, seed=17
    )
    decisions = {
        sample[0]["mutant_id"]: "confirmed_equivalent",
        sample[1]["mutant_id"]: "non_equivalent",
    }
    review_provenance = {
        "review_artifact_hash": "review",
        "reviewed_catalog_artifact_hash": "reviewed",
    }

    result = estimate_adjusted_scores(
        manifest,
        global_outcomes,
        sampling_manifest,
        sample,
        decisions,
        matrix,
        review_provenance,
        target_half_width=0.05,
    )

    row = result["participants"][0]
    assert row["specified_timeout"] == 2
    assert row["specified_no_tests"] == 1
    assert row["specified_estimated_equivalent"] == 2.0
    assert row["specified_estimated_adjusted_score"] == 0.625
    assert row["specified_estimated_ci95_lower"] == 0.5
    assert row["specified_estimated_ci95_upper"] == pytest.approx(0.87156170)
    assert row["specified_interval_half_width"] == pytest.approx(0.18578085)
    assert result["review_population"]["estimated_equivalent"] == 2.0
    assert result["review_population"]["estimated_equivalent_proportion"] == 0.5
    assert result["stopping"]["all_primary_intervals_within_target"] is False
    assert result["stopping"]["next_planned_sample_size"] == 4
    assert result["stopping"]["interval_method"] == "bonferroni_across_looks"
    assert result["stopping"]["confidence_level"] == 0.975
    assert result["review_artifact_hash"] == "review"
    assert result["participant_matrix_hash"]

    relaxed = estimate_adjusted_scores(
        manifest,
        global_outcomes,
        sampling_manifest,
        sample,
        decisions,
        matrix,
        review_provenance,
        target_half_width=0.25,
    )
    assert relaxed["stopping"]["all_primary_intervals_within_target"] is True
    assert relaxed["stopping"]["next_planned_sample_size"] is None


def test_estimation_requires_every_sampled_decision_to_be_resolved() -> None:
    with pytest.raises(ValueError, match="resolved adjudication"):
        estimate_adjusted_scores(
            {"catalog_hash": "catalog", "participants": []},
            {"catalog_hash": "catalog", "summary": {}},
            {
                "catalog_hash": "catalog",
                "seed": 1,
                "actual_sample_size": 1,
                "sampling_frame_size": 1,
            },
            [
                {
                    "mutant_id": "M1",
                    "workload_layer": "specified",
                    "sampling_stratum": "specified | OTHER",
                    "stratum_population": 1,
                    "stratum_sample_size": 1,
                    "sampling_weight": 1.0,
                }
            ],
            {"M1": "unresolved"},
            {"M1": {}},
            {
                "review_artifact_hash": "review",
                "reviewed_catalog_artifact_hash": "reviewed",
            },
            target_half_width=0.05,
        )


def test_estimation_rejects_tampered_design_weights() -> None:
    with pytest.raises(ValueError, match="design weight"):
        estimate_adjusted_scores(
            {"catalog_hash": "catalog", "participants": []},
            {"catalog_hash": "catalog", "summary": {}},
            {
                "catalog_hash": "catalog",
                "seed": 1,
                "actual_sample_size": 1,
                "sampling_frame_size": 2,
            },
            [
                {
                    "mutant_id": "M1",
                    "workload_layer": "specified",
                    "sampling_stratum": "specified | OTHER",
                    "stratum_population": 2,
                    "stratum_sample_size": 1,
                    "inclusion_probability": 0.5,
                    "sampling_weight": 99.0,
                }
            ],
            {"M1": "non_equivalent"},
            {"M1": {}},
            {
                "review_artifact_hash": "review",
                "reviewed_catalog_artifact_hash": "reviewed",
            },
            target_half_width=0.05,
        )


def test_estimation_rejects_sample_outside_global_review_population() -> None:
    with pytest.raises(ValueError, match="review population"):
        estimate_adjusted_scores(
            {"catalog_hash": "catalog", "participants": []},
            {
                "catalog_hash": "catalog",
                "summary": {},
                "review_candidates": [{"mutant_id": "M2"}],
            },
            {
                "catalog_hash": "catalog",
                "seed": 1,
                "actual_sample_size": 1,
                "sampling_frame_size": 1,
            },
            [
                {
                    "mutant_id": "M1",
                    "workload_layer": "specified",
                    "sampling_stratum": "specified | OTHER",
                    "stratum_population": 1,
                    "stratum_sample_size": 1,
                    "inclusion_probability": 1.0,
                    "sampling_weight": 1.0,
                }
            ],
            {"M1": "non_equivalent"},
            {"M1": {}},
            {
                "review_artifact_hash": "review",
                "reviewed_catalog_artifact_hash": "reviewed",
            },
            target_half_width=0.05,
        )


def test_estimation_rejects_tampered_sampling_provenance() -> None:
    global_outcomes = {
        "catalog_hash": "catalog",
        "sut_hash": "sut",
        "execution_policy_hash": "policy",
        "review_candidates": _candidates(),
        "summary": {},
    }
    sample, sampling_manifest = _sampling_inputs(
        global_outcomes, sample_size=5, seed=17
    )
    sampling_manifest["sample_hash"] = "tampered"

    with pytest.raises(ValueError, match="sampling manifest hash"):
        estimate_adjusted_scores(
            {
                "catalog_hash": "catalog",
                "execution_policy_hash": "policy",
                "participants": [],
            },
            global_outcomes,
            sampling_manifest,
            sample,
            {row["mutant_id"]: "non_equivalent" for row in sample},
            {row["mutant_id"]: {} for row in sample},
            {
                "review_artifact_hash": "review",
                "reviewed_catalog_artifact_hash": "reviewed",
            },
            target_half_width=0.05,
        )


def test_adjusted_score_outputs_include_method_and_stopping_metadata(
    tmp_path: Path,
) -> None:
    payload = {
        "schema_version": 1,
        "catalog_hash": "catalog",
        "method": "design-weighted",
        "confidence_level": 0.95,
        "reviewed_sample_size": 313,
        "sampling_seed": 17,
        "review_artifact_hash": "review",
        "reviewed_catalog_artifact_hash": "reviewed",
        "decision_status_hash": "decisions",
        "participant_matrix_hash": "matrix",
        "review_population": {
            "auto_non_equivalent": 3041,
            "confirmed_equivalent_in_sample": 20,
            "unresolved_in_sample": 0,
        },
        "participants": [
            {
                "participant_id": "experiment-01",
                "participant_number": 1,
                "status": "collected",
                "catalog_hash": "catalog",
                "specified_raw_mutation_score": 0.5,
                "specified_estimated_adjusted_score": 0.6,
                "specified_estimated_ci95_lower": 0.55,
                "specified_estimated_ci95_upper": 0.65,
            }
        ],
        "stopping": {
            "target_half_width": 0.05,
            "interval_method": "bonferroni_across_looks",
            "confidence_level": 0.99,
            "current_look": 1,
            "next_planned_sample_size": None,
            "all_primary_intervals_within_target": True,
        },
    }

    write_adjusted_score_outputs(payload, tmp_path)

    written = json.loads((tmp_path / "mutation_score_estimates.json").read_text())
    with (tmp_path / "mutation_scores.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert written == payload
    assert rows[0]["weighting_method"] == "design-weighted"
    assert rows[0]["reviewed_sample_size"] == "313"
    assert rows[0]["stopping_interval_method"] == "bonferroni_across_looks"
    assert rows[0]["stopping_confidence_level"] == "0.99"
    assert rows[0]["current_look"] == "1"
    assert rows[0]["next_planned_sample_size"] == ""
    assert rows[0]["all_primary_intervals_within_target"] == "True"
    assert rows[0]["specified_estimated_adjusted_score"] == "0.6"


def test_summarize_sampled_reviews_cli_writes_final_outputs(tmp_path: Path) -> None:
    candidates = [
        {
            "mutant_id": f"M{number}",
            "workload_layer": "specified",
            "operator_family": "ARITHMETIC",
        }
        for number in range(4)
    ]
    matrix = {
        row["mutant_id"]: {"experiment-01": "survived"} for row in candidates
    }
    global_outcomes = {
        "catalog_hash": "catalog",
        "sut_hash": "sut",
        "execution_policy_hash": "policy",
        "review_candidates": candidates,
        "participant_matrix": matrix,
        "summary": {"auto_non_equivalent": 6, "review_candidates": 4},
    }
    collection_manifest = {
        "catalog_hash": "catalog",
        "execution_policy_hash": "policy",
        "participants": [
            {
                "participant_id": "experiment-01",
                "participant_number": 1,
                "status": "collected",
                "summary": {
                    "baseline_valid_only_passed": True,
                    "valid_tests_included": 1,
                    "invalid_tests_excluded": 0,
                    "specified": {
                        "eligible_mutants": 10,
                        "eligible_killed": 5,
                        "mutation_score": 0.5,
                    },
                    "extended": {
                        "eligible_mutants": 0,
                        "eligible_killed": 0,
                        "mutation_score": 0.0,
                    },
                    "combined": {
                        "eligible_mutants": 10,
                        "eligible_killed": 5,
                        "mutation_score": 0.5,
                    },
                },
            }
        ],
    }
    global_path = tmp_path / "global.json"
    collection_path = tmp_path / "collection.json"
    global_path.write_text(json.dumps(global_outcomes))
    collection_path.write_text(json.dumps(collection_manifest))
    review_dir = tmp_path / "review"
    write_review_sample(
        global_outcomes,
        review_dir,
        sample_size=2,
        seed=17,
        generated_at="fixed",
    )
    with (review_dir / "sample.csv").open(newline="") as stream:
        sampled = list(csv.DictReader(stream))
    decisions_path = review_dir / "decisions.csv"
    decision_rows = [
        {
            "mutant_id": row["mutant_id"],
            "adjudicated_status": (
                "confirmed_equivalent" if index == 0 else "non_equivalent"
            ),
            "adjudication_reason": "reviewed",
        }
        for index, row in enumerate(sampled)
    ]
    with decisions_path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "mutant_id",
                "adjudicated_status",
                "adjudication_reason",
            ),
        )
        writer.writeheader()
        writer.writerows(decision_rows)
    review_identity = [
        {
            "mutant_id": row["mutant_id"],
            "review_status": row["adjudicated_status"],
            "review_reason": row["adjudication_reason"],
        }
        for row in sorted(decision_rows, key=lambda row: row["mutant_id"])
    ]
    review_summary_path = review_dir / "review_summary.json"
    review_summary_path.write_text(
        json.dumps(
            {
                "catalog_hash": "catalog",
                "review_artifact_hash": hashlib.sha256(
                    canonical_json(review_identity).encode()
                ).hexdigest(),
                "reviewed_catalog_artifact_hash": "reviewed",
            }
        )
    )
    matrix_path = tmp_path / "matrix.csv"
    with matrix_path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=("mutant_id", "experiment-01")
        )
        writer.writeheader()
        for row in candidates:
            writer.writerow(
                {"mutant_id": row["mutant_id"], "experiment-01": "survived"}
            )
    output_dir = tmp_path / "output"

    result = main(
        [
            "--collection-manifest",
            str(collection_path),
            "--global-outcomes",
            str(global_path),
            "--sampling-manifest",
            str(review_dir / "sampling_manifest.json"),
            "--sample",
            str(review_dir / "sample.csv"),
            "--decisions",
            str(decisions_path),
            "--review-summary",
            str(review_summary_path),
            "--participant-matrix",
            str(matrix_path),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert result == 0
    assert (output_dir / "mutation_scores.csv").is_file()
    assert (output_dir / "mutation_score_estimates.json").is_file()
