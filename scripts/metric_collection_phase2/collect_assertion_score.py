"""Analyze Phase 2 assertion quality using frozen error-rate classifications."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metric_collection_phase1.collect_all_branches import _git, _write_json
from scripts.metric_collection_phase1.collect_assertion_score import (
    _report_from_results,
)
from scripts.metric_collection_phase1.collect_error_rates import TestCaseResult
from scripts.metric_collection_phase2.collect_coverage import (
    export_snapshot,
    partition_pool,
    valid_pool,
)
from scripts.metric_collection_phase2.collect_error_rates import PARTICIPANTS


def summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Preserve Phase 1's non-trivial / eligible-source-function score definition."""
    counts = Counter(case["classification"] for case in cases)
    eligible = len(cases) - counts["invalid"]
    return {
        "total_source_tests": len(cases),
        "invalid_test_count": counts["invalid"],
        "eligible_test_count": eligible,
        "non_trivial_test_count": counts["non_trivial"],
        "trivial_test_count": counts["trivial"],
        "assertionless_test_count": counts["assertionless"],
        "uncertain_test_count": counts["uncertain"],
        "partially_valid_test_count": sum(
            case["validity"] == "partially_valid" for case in cases
        ),
        "assertion_score": counts["non_trivial"] / eligible if eligible else None,
    }


def collect_submission(checkout: Path, raw: dict[str, Any]) -> dict[str, Any]:
    """Analyze each selected source file without counting untouched upstream functions."""
    valid_nodeids = valid_pool(raw, checkout)
    metrics = raw["metrics"]
    cases = []
    for path, names in metrics["source_test_declarations"].items():
        results = [
            TestCaseResult(
                **{
                    key: case[key]
                    for key in (
                        "nodeid",
                        "source_test",
                        "classification",
                        "returncode",
                        "reason",
                    )
                }
            )
            for case in metrics["case_level"]["test_cases"]
            if case["source_file"] == path
        ]
        report = _report_from_results(checkout / path, results, expected_tests=names)
        for case in report.test_cases:
            identity = f"{path}::{case.source_test}"
            group = next(
                name for name, ids in partition_pool([identity]).items() if ids
            )
            cases.append(
                {
                    **asdict(case),
                    "source_file": path,
                    "source_id": identity,
                    "task_group": group,
                }
            )
    if len({case["source_id"] for case in cases}) != len(cases):
        raise ValueError("Duplicate source-function identity")
    groups = partition_pool(valid_nodeids)
    return {
        "summary": summarize(cases),
        "test_cases": cases,
        "by_file": {
            path: summarize([case for case in cases if case["source_file"] == path])
            for path in metrics["source_test_declarations"]
        },
        "by_task_group": {
            name: summarize([case for case in cases if case["task_group"] == name])
            for name in groups
        },
        "valid_nodeids": valid_nodeids,
        "artifact_sha256": metrics["artifact_sha256"],
        "missing_expected_tests": metrics["missing_expected_tests"],
        "uncertain_source_ids": [
            case["source_id"] for case in cases if case["classification"] == "uncertain"
        ],
    }


def apply_reviews(manifest: dict[str, Any], output: Path, review_path: Path) -> None:
    """Export reviewed scores while preserving original automated evidence."""
    reviews = json.loads(review_path.read_text())["reviews"]
    applied = 0
    for row in manifest["participants"]:
        if row["status"] != "collected":
            continue
        raw = json.loads((output / row["output_file"]).read_text())
        cases = [dict(case) for case in raw["metrics"]["test_cases"]]
        selected = [
            review
            for review in reviews
            if review["participant_number"] == row["participant_number"]
        ]
        for review in selected:
            if review["participant_commit"] != row["participant_commit"]:
                raise ValueError("Review refers to a different participant commit")
            case = next(
                case for case in cases if case["source_id"] == review["source_id"]
            )
            if case["classification"] != review["automated_classification"]:
                raise ValueError("Review no longer matches automated classification")
            if review["reviewed_classification"] != "non_trivial":
                raise ValueError("Unsupported review classification")
            case["classification"] = review["reviewed_classification"]
            applied += 1
        row["final_summary"] = {
            **summarize(cases),
            "automated_assertion_score": row["summary"]["assertion_score"],
            "uncertain_functions_reviewed": len(selected),
        }
    if applied != len(reviews):
        raise ValueError("Not all review decisions matched collected participants")
    manifest["final_export"] = {
        "adjudications_sha256": hashlib.sha256(review_path.read_bytes()).hexdigest(),
        "reviewed_function_count": applied,
        "summary_source": "final_summary; original summary and raw evidence are automated",
    }


def collect_all(repo: Path, error_dir: Path, output: Path) -> dict[str, Any]:
    source_path = error_dir / "collection_manifest.json"
    source = json.loads(source_path.read_text())
    if sorted(row["participant_number"] for row in source["participants"]) != sorted(
        PARTICIPANTS
    ):
        raise ValueError("Error-rate cohort differs from Phase 2 cohort")
    if any(row["status"] != "collected" for row in source["participants"]):
        raise ValueError("Complete error-rate collection is required")
    records = []
    for row in source["participants"]:
        record = {
            key: row[key]
            for key in (
                "participant_id",
                "participant_number",
                "participant_commit",
                "phase1_group",
            )
        }
        print(
            f"Collecting assertion score: {row['participant_id']}...", file=sys.stderr
        )
        try:
            raw_path = error_dir / row["output_file"]
            raw = json.loads(raw_path.read_text())
            if (
                raw["participant_commit"] != row["participant_commit"]
                or raw["baseline_commit"] != source["baseline_commit"]
            ):
                raise ValueError("Error-rate manifest/raw commit mismatch")
            with tempfile.TemporaryDirectory(prefix="phase2-assertions-") as tmp:
                checkout = Path(tmp)
                export_snapshot(repo, row["participant_commit"], checkout)
                report = collect_submission(checkout, raw)
            destination = output / "raw" / f"{row['participant_id']}.json"
            _write_json(
                destination,
                {
                    **record,
                    "baseline_commit": source["baseline_commit"],
                    "error_rate_raw_sha256": hashlib.sha256(
                        raw_path.read_bytes()
                    ).hexdigest(),
                    "metrics": report,
                },
            )
            record.update(
                status="collected",
                output_file=destination.relative_to(output).as_posix(),
                summary=report["summary"],
            )
        except (ValueError, OSError, RuntimeError) as exc:
            record.update(status="collection_failed", reason=str(exc))
        records.append(record)
        print(f"  {record['status']}", file=sys.stderr)
    paths = [
        Path(__file__).resolve(),
        repo / "scripts/metric_collection_phase1/collect_assertion_score.py",
        repo / "scripts/metric_collection_phase1/collect_error_rates.py",
        repo / "scripts/metric_collection_phase2/collect_coverage.py",
    ]
    return {
        "schema_version": "phase2-assertion-score-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": source["baseline_commit"],
        "collector_commit": _git(repo, "rev-parse", "HEAD"),
        "collector_sha256": {
            path.relative_to(repo).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in paths
        },
        "error_rate_manifest_sha256": hashlib.sha256(
            source_path.read_bytes()
        ).hexdigest(),
        "python_version": sys.version.split()[0],
        "count_basis": "source file plus function; at least one valid pytest instance is eligible",
        "participants": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--error-dir", type=Path, default=Path("results/phase2/error_rates")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("results/phase2/assertion_score")
    )
    parser.add_argument(
        "--adjudications",
        type=Path,
        default=Path("results/phase2/assertion_score/manual_review/adjudications.json"),
    )
    args = parser.parse_args(argv)
    repo = args.repo_root.resolve()
    output = (repo / args.output_dir).resolve()
    if output.exists():
        parser.error(
            "Output directory exists; use a new directory to preserve evidence"
        )
    manifest = collect_all(repo, (repo / args.error_dir).resolve(), output)
    review_path = (repo / args.adjudications).resolve()
    if review_path.exists():
        apply_reviews(manifest, output, review_path)
    _write_json(output / "collection_manifest.json", manifest)
    columns = [
        "participant_number",
        "status",
        "total_source_tests",
        "invalid_test_count",
        "eligible_test_count",
        "non_trivial_test_count",
        "trivial_test_count",
        "assertionless_test_count",
        "uncertain_test_count",
        "partially_valid_test_count",
        "assertion_score",
        "automated_assertion_score",
        "uncertain_functions_reviewed",
    ]
    with (output / "assertion_score.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in manifest["participants"]:
            values = {**row, **row.get("final_summary", row.get("summary", {}))}
            if values.get("assertion_score") is not None:
                values["assertion_score"] = f"{values['assertion_score']:.6f}"
            writer.writerow({name: values.get(name) for name in columns})
    return int(any(row["status"] != "collected" for row in manifest["participants"]))


if __name__ == "__main__":
    raise SystemExit(main())
