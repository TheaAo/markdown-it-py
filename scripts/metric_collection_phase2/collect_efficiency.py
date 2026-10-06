"""Derive Phase 2 efficiencies from frozen scores and explicit timing datasets."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metric_collection_phase1.collect_all_branches import _write_json
from scripts.metric_collection_phase2.collect_execution_times import (
    PARTICIPANTS,
    file_hash,
)


def index_rows(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Reject duplicate IDs and incomplete or expanded cohorts."""
    indexed = {int(row["participant_number"]): row for row in rows}
    if len(indexed) != len(rows) or set(indexed) != set(PARTICIPANTS):
        raise ValueError("Expected exactly the eight Phase 2 participants")
    return indexed


def ratio(score: float | None, seconds: float | None) -> float | None:
    """Keep unavailable inputs unavailable; never turn them into zero."""
    if score is None or seconds is None:
        return None
    if not math.isfinite(score) or not math.isfinite(seconds):
        raise ValueError("Non-finite efficiency input")
    return score / seconds if seconds > 0 else None


def efficiency_row(base: dict[str, Any], seconds: float, kind: str) -> dict[str, Any]:
    """Use one calculation for generation and execution efficiency."""
    row = dict(base)
    row[f"{kind}_time_seconds"] = seconds
    row["efficiency_status"] = "collected" if seconds > 0 else "unavailable"
    for metric, field in (
        ("statement", "participant_statement_coverage"),
        ("branch", "participant_branch_coverage"),
        ("mutation", "specified_estimated_adjusted_mutation_score"),
    ):
        row[f"{metric}_{kind}_efficiency_per_second"] = ratio(base[field], seconds)
    for bound in ("lower", "upper"):
        row[f"mutation_{kind}_efficiency_conditional_ci95_{bound}_per_second"] = ratio(
            base[f"specified_mutation_score_ci95_{bound}"], seconds
        )
    return row


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write full precision components and ratios without modifying sources."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def derive(root: Path, timing_dir: Path, output: Path) -> dict[str, Any]:
    """Validate shared identities, then derive the six full-suite ratios."""
    paths = {
        "coverage": root / "coverage/collection_manifest.json",
        "mutation": root / "mutation_score/mutation_score.csv",
        "mutation_manifest": root / "mutation_score/formal/collection_manifest.json",
        "generation": root / "generation_time/generation_time.csv",
        "timing": timing_dir / "collection_manifest.json",
    }
    hashes = {key: file_hash(path) for key, path in paths.items()}
    coverage = json.loads(paths["coverage"].read_text())
    mutation_manifest = json.loads(paths["mutation_manifest"].read_text())
    timing = json.loads(paths["timing"].read_text())
    with paths["mutation"].open(newline="", encoding="utf-8") as stream:
        mutants = index_rows(list(csv.DictReader(stream)))
    with paths["generation"].open(newline="", encoding="utf-8") as stream:
        generation = index_rows(list(csv.DictReader(stream)))
    cov = index_rows(coverage["participants"])
    times = index_rows(timing["participants"])
    mutation_sources = index_rows(mutation_manifest["participants"])
    if len({m["baseline_commit"] for m in (coverage, mutation_manifest, timing)}) != 1:
        raise ValueError("SUT baselines differ")
    if not (
        coverage["error_rate_manifest_sha256"]
        == mutation_manifest["error_rate_manifest_sha256"]
        == timing["source_manifest_sha256"]
    ):
        raise ValueError("Frozen validity pools differ")

    generation_rows = []
    execution_rows = []
    for number in PARTICIPANTS:
        c, m, t, g, source = (
            cov[number],
            mutants[number],
            times[number],
            generation[number],
            mutation_sources[number],
        )
        if any(r["status"] != "collected" for r in (c, m, t, g, source)):
            raise ValueError(f"Incomplete source for participant {number}")
        if len({r["participant_commit"] for r in (c, t, source)}) != 1:
            raise ValueError(f"Submission identities differ for participant {number}")
        count = c["summary"]["valid_tests_included"]
        if not (
            count
            == t["summary"]["valid_tests_included"]
            == int(m["valid_tests_included"])
        ):
            raise ValueError(f"Valid test counts differ for participant {number}")
        if m["catalog_hash"] != mutation_manifest["catalog_hash"]:
            raise ValueError("Mutation catalog identity differs")
        if g["group"] != t["phase2_group"]:
            raise ValueError("Generation-time group differs")
        h, minute, second = map(int, g["total_time"].split(":"))
        duration = h * 3600 + minute * 60 + second
        if not (0 <= minute < 60 and 0 <= second < 60 and h >= 0 and duration > 0):
            raise ValueError("Invalid generation duration")
        if duration != int(g["total_time_seconds"]) or duration != int(
            g["generation_time_seconds"]
        ):
            raise ValueError("Generation seconds differ from supplied duration")
        scores = c["summary"]["participant_tests_only"]
        base = {
            "participant_number": number,
            "phase": 2,
            "phase1_group": t["phase1_group"],
            "phase2_group": t["phase2_group"],
            "participant_commit": t["participant_commit"],
            "scope": "full_valid_participant_suite",
            "valid_tests_included": count,
            "participant_statement_coverage": scores["statement"]["covered"]
            / scores["statement"]["total"],
            "participant_branch_coverage": scores["branch"]["covered"]
            / scores["branch"]["total"],
            "specified_estimated_adjusted_mutation_score": float(
                m["specified_estimated_adjusted_score"]
            ),
            "specified_mutation_score_ci95_lower": float(
                m["specified_estimated_ci95_lower"]
            ),
            "specified_mutation_score_ci95_upper": float(
                m["specified_estimated_ci95_upper"]
            ),
        }
        if not all(
            0 <= base[k] <= 1
            for k in (
                "participant_statement_coverage",
                "participant_branch_coverage",
                "specified_mutation_score_ci95_lower",
                "specified_estimated_adjusted_mutation_score",
                "specified_mutation_score_ci95_upper",
            )
        ):
            raise ValueError("Scores must be 0-1 fractions")
        if not (
            base["specified_mutation_score_ci95_lower"]
            <= base["specified_estimated_adjusted_mutation_score"]
            <= base["specified_mutation_score_ci95_upper"]
        ):
            raise ValueError("Mutation interval does not contain its estimate")
        generation_rows.append(efficiency_row(base, duration, "generation"))
        summary = t["summary"]["execution_time"]
        if (
            t["summary"]["metric_status"] != "collected"
            or summary["execution_time_seconds"] <= 0
        ):
            raise ValueError("Execution time is unavailable")
        row = efficiency_row(base, summary["execution_time_seconds"], "execution")
        row.update(
            execution_dataset=timing_dir.name,
            execution_measurement_count=summary["measurement_count"],
            execution_coefficient_of_variation=summary["coefficient_of_variation"],
            execution_cv_review_threshold=summary["cv_review_threshold"],
            execution_cv_review_required=summary["cv_review_required"],
            execution_first_quartile_seconds=summary["first_quartile_seconds"],
            execution_third_quartile_seconds=summary["third_quartile_seconds"],
        )
        execution_rows.append(row)

    if hashes != {key: file_hash(path) for key, path in paths.items()}:
        raise ValueError("Input changed during derivation")
    write_csv(output / "generation_efficiency.csv", generation_rows)
    write_csv(output / "execution_efficiency.csv", execution_rows)
    manifest = {
        "schema_version": "phase2-efficiency-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            key: {"path": str(path), "sha256": hashes[key]}
            for key, path in paths.items()
        },
        "collector_sha256": file_hash(Path(__file__)),
        "participant_numbers": list(PARTICIPANTS),
        "execution_dataset": timing_dir.name,
        "score_units": "0-1 fractions, not percentages",
        "coverage_source": "exact participant-only covered/total counts; excludes pristine project tests",
        "mutation_source": "specified_estimated_adjusted_score",
        "generation_denominator": "total task seconds including comprehension, maintenance, generation and debugging",
        "execution_denominator": "median of complete valid-suite pytest subprocess durations",
        "mutation_interval": "conditional on fixed observed time; propagates only score-estimation uncertainty, not timing or self-report uncertainty",
        "task_group_efficiency": "unavailable: no separate task-group time denominators were collected",
        "outputs": {
            name: file_hash(output / name)
            for name in ("generation_efficiency.csv", "execution_efficiency.csv")
        },
    }
    _write_json(output / "collection_manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", type=Path, default=Path("results/phase2"))
    parser.add_argument(
        "--timing-dir", type=Path, default=Path("results/phase2/execution_time/formal")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("results/phase2/efficiency")
    )
    args = parser.parse_args()
    derive(
        args.results_root.resolve(),
        args.timing_dir.resolve(),
        args.output_dir.resolve(),
    )


if __name__ == "__main__":
    main()
