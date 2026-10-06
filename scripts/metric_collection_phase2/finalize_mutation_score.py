"""Validate complete Phase 2 execution, prepare review, and export adjusted scores."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metric_collection_phase1.aggregate_mutant_outcomes import (
    _unwrap,
    aggregate_outcomes,
    write_aggregation,
)
from scripts.metric_collection_phase1.equivalent_mutant_sampling import (
    estimate_adjusted_scores,
    write_adjusted_score_outputs,
    write_review_sample,
)
from scripts.metric_collection_phase1.mutation_common import load_catalog, write_json
from scripts.metric_collection_phase1.summarize_equivalent_mutant_sample import (
    _load_decisions,
    _load_matrix,
    _load_sample,
)
from scripts.metric_collection_phase2.collect_error_rates import PARTICIPANTS


def validate_completion(manifest: dict[str, Any], catalog: dict[str, Any]) -> None:
    """Fail closed on pilot, partial cohort, missing outcomes or mixed identity."""
    if (
        manifest.get("stage") != "formal_execution"
        or manifest.get("status") != "executions_complete"
    ):
        raise ValueError(
            "Full formal participant execution must complete before finalization"
        )
    rows = manifest["participants"]
    if sorted(row["participant_number"] for row in rows) != sorted(PARTICIPANTS):
        raise ValueError("Finalization requires exactly the eight Phase 2 participants")
    if any(row["status"] != "collected" for row in rows):
        raise ValueError("Some participant mutation results are incomplete")
    for key in ("catalog_hash", "sut_hash", "baseline_commit"):
        if manifest.get(key) != catalog.get(key):
            raise ValueError(f"Formal manifest/catalog identity mismatch: {key}")


def validate_unresolved_exclusions(
    outcomes: dict[str, Any], participant_ids: set[str]
) -> None:
    """Allow only mutants timed out and already excluded for every participant."""
    for row in outcomes["execution_unresolved"]:
        statuses = outcomes["participant_matrix"][row["mutant_id"]]
        if set(statuses) != participant_ids or set(statuses.values()) != {"timeout"}:
            raise ValueError(
                "Unresolved executions other than all-participant timeouts require retry"
            )


def prepare_review(
    root: Path, protocol: dict[str, Any], sample_size: int | None = None
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    size = protocol["initial_sample_size"] if sample_size is None else sample_size
    if size not in protocol["planned_sample_sizes"]:
        raise ValueError("Review sample size is outside the frozen expansion plan")
    catalog = load_catalog(root / "catalog/task_relevant_mutant_catalog.json")
    formal = root / "formal"
    manifest = json.loads((formal / "collection_manifest.json").read_text())
    validate_completion(manifest, catalog)
    paths = [formal / row["output_file"] for row in manifest["participants"]]
    pairs = [_unwrap(path) for path in paths]
    if any(
        row.get("flaky_kill") for _, mutation in pairs for row in mutation["mutants"]
    ):
        raise ValueError("Flaky kills need resolution before final adjusted scoring")
    evidence = json.loads((formal / "reliable_kill_evidence.json").read_text())
    global_dir = root / "global"
    identity = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
    }
    identity["reliable_kill_evidence"] = hashlib.sha256(
        (formal / "reliable_kill_evidence.json").read_bytes()
    ).hexdigest()
    outcome_path = global_dir / "global_mutant_outcomes.json"
    provenance_path = global_dir / "input_hashes.json"
    if outcome_path.exists():
        if json.loads(provenance_path.read_text()) != identity:
            raise ValueError(
                "Frozen global outcome inputs changed; use a fresh review directory"
            )
        outcomes = json.loads(outcome_path.read_text())
    else:
        outcomes = aggregate_outcomes(
            catalog,
            pairs,
            require_confirmed_kills=True,
            reliable_kill_evidence=evidence,
        )
        if outcomes["summary"]["reliable_participants"] != len(PARTICIPANTS):
            raise ValueError("Some participant outcomes are not reliable")
        validate_unresolved_exclusions(
            outcomes, {row["participant_id"] for row in manifest["participants"]}
        )
        outcomes["generated_at"] = datetime.now(timezone.utc).isoformat()
        write_aggregation(global_dir, outcomes)
        write_json(provenance_path, identity)
    if manifest["execution_policy_hash"] != outcomes["execution_policy_hash"]:
        raise ValueError("Formal/global execution policies differ")
    validate_unresolved_exclusions(
        outcomes, {row["participant_id"] for row in manifest["participants"]}
    )
    stage = protocol["planned_sample_sizes"].index(size) + 1
    review = global_dir / f"equivalent_review_sample_stage{stage}"
    if not (review / "sampling_manifest.json").exists():
        write_review_sample(
            outcomes,
            review,
            sample_size=size,
            seed=protocol["seed"],
            minimum_per_stratum=protocol["minimum_per_stratum"],
            planned_sample_sizes=protocol["planned_sample_sizes"],
        )
    return manifest, outcomes, review


def finalize(
    root: Path, manifest: dict[str, Any], outcomes: dict[str, Any], review: Path
) -> None:
    decisions, review_hash = _load_decisions(review / "review_decisions.csv")
    summary = json.loads((review / "review_summary.json").read_text())
    if (
        summary["review_artifact_hash"] != review_hash
        or summary["catalog_hash"] != manifest["catalog_hash"]
    ):
        raise ValueError("Review summary does not match the reviewed decisions/catalog")
    estimates = estimate_adjusted_scores(
        manifest,
        outcomes,
        json.loads((review / "sampling_manifest.json").read_text()),
        _load_sample(review / "sample.csv"),
        decisions,
        _load_matrix(root / "global/participant_mutant_matrix.csv"),
        {
            "review_artifact_hash": review_hash,
            "reviewed_catalog_artifact_hash": summary["reviewed_catalog_artifact_hash"],
        },
        target_half_width=0.05,
    )
    if not estimates["stopping"]["all_primary_intervals_within_target"]:
        raise ValueError("Equivalent-mutant sample needs the next planned review stage")
    final = root / "final"
    json_path, csv_path = write_adjusted_score_outputs(estimates, final)
    shutil.copy2(csv_path, root / "mutation_score.csv")
    write_json(
        final / "finalization_manifest.json",
        {
            "status": "complete",
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "primary_scope": "specified",
            "method": "equivalent-adjusted stratified estimate",
            "review_method": summary.get("method"),
            "independent_secondary_review": summary.get("independent_secondary_review"),
            "final_run_max_children": manifest.get("max_children"),
            "review_directory": review.relative_to(root).as_posix(),
            "finalizer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "all_participant_timeout_mutants": len(outcomes["execution_unresolved"]),
            "timeout_policy": "exclude from each eligible denominator; no semantic equivalence claim",
            "formal_manifest_sha256": hashlib.sha256(
                (root / "formal/collection_manifest.json").read_bytes()
            ).hexdigest(),
            "review_summary_sha256": hashlib.sha256(
                (review / "review_summary.json").read_bytes()
            ).hexdigest(),
            "final_csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
            "estimates_sha256": hashlib.sha256(json_path.read_bytes()).hexdigest(),
        },
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path("results/phase2/mutation_score")
    )
    parser.add_argument("--prepare-review", action="store_true")
    parser.add_argument(
        "--review-sample-size", type=int, choices=(100, 150, 225, 313), default=100
    )
    parser.add_argument("--wait-seconds", type=float, default=0)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    protocol_path = root / "equivalence_protocol.json"
    protocol = {
        "seed": 20261005,
        "initial_sample_size": 100,
        "minimum_per_stratum": 2,
        "planned_sample_sizes": [100, 150, 225, 313],
        "target_half_width": 0.05,
        "primary_scope": "specified",
        "nominal_confidence_level": 0.95,
        "review_population": "no reliable global kill; no automatic equivalence claims",
    }
    if protocol_path.exists():
        if json.loads(protocol_path.read_text()) != protocol:
            raise ValueError("Frozen equivalence protocol differs")
    else:
        write_json(protocol_path, protocol)
    deadline = time.monotonic() + args.wait_seconds
    while True:
        formal_path = root / "formal/collection_manifest.json"
        if formal_path.exists():
            manifest = json.loads(formal_path.read_text())
            if manifest.get("status") == "collection_failed":
                raise RuntimeError(
                    "Participant execution failed; inspect mutation pipeline logs"
                )
            if manifest.get("status") == "executions_complete":
                break
        pipeline_path = root / "pipeline_status.json"
        if (
            pipeline_path.exists()
            and json.loads(pipeline_path.read_text()).get("status") == "failed"
        ):
            raise RuntimeError(
                "Mutation pipeline failed before final participant collection"
            )
        if time.monotonic() >= deadline:
            raise RuntimeError("Formal execution is not complete yet")
        time.sleep(5)
    manifest, outcomes, review = prepare_review(root, protocol, args.review_sample_size)
    print(f"Prepared review: {review}", flush=True)
    if not args.prepare_review:
        finalize(root, manifest, outcomes, review)
        print(f"Final Mutation Score: {root / 'mutation_score.csv'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
