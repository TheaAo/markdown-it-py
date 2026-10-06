"""Collect Phase 2 test smells with the frozen Phase 1 rules and valid pool."""

from __future__ import annotations

import argparse
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
from scripts.metric_collection_phase1.collect_test_smells import (
    collect_test_smells,
)
from scripts.metric_collection_phase1.detect_test_smells_ast import (
    FORMAL_SMELLS,
    RULE_VERSION,
)
from scripts.metric_collection_phase1.summarize_test_smells import summarize_test_smells
from scripts.metric_collection_phase2.collect_coverage import (
    export_snapshot,
    partition_pool,
    valid_pool,
)
from scripts.metric_collection_phase2.collect_error_rates import PARTICIPANTS


def summarize(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Count each smell once per eligible source function, as in Phase 1."""
    eligible = [case for case in cases if case["eligible"]]
    per_smell: dict[str, dict[str, Any]] = {}
    for smell in FORMAL_SMELLS:
        decisions = [
            decision["decision"]
            for case in eligible
            for decision in case["smells"]
            if decision["smell"] == smell
        ]
        if len(decisions) != len(eligible):
            raise ValueError(f"Missing or duplicate decisions for {smell}")
        confirmed = decisions.count("confirmed")
        per_smell[smell] = {
            "confirmed_count": confirmed,
            "uncertain_count": decisions.count("uncertain"),
            "rate": confirmed / len(eligible) if eligible else None,
        }
    pairs = sum(item["confirmed_count"] for item in per_smell.values())
    smelly = sum(case["has_confirmed_smell"] for case in eligible)
    return {
        "total_source_tests": len(cases),
        "eligible_test_count": len(eligible),
        "invalid_test_count": len(cases) - len(eligible),
        "partially_valid_test_count": sum(
            case["validity"] == "partially_valid" for case in cases
        ),
        "smelly_test_count": smelly,
        "confirmed_pair_count": pairs,
        "uncertain_pair_count": sum(
            item["uncertain_count"] for item in per_smell.values()
        ),
        "smelly_test_rate": smelly / len(eligible) if eligible else None,
        "mean_smells_per_test": pairs / len(eligible) if eligible else None,
        "test_smell_density": (
            pairs / (len(eligible) * len(FORMAL_SMELLS)) if eligible else None
        ),
        "per_smell": per_smell,
    }


def collect_submission(
    checkout: Path,
    raw: dict[str, Any],
    *,
    evidence: Path,
    pytest_smell: Path | None = None,
    tempy_root: Path | None = None,
) -> dict[str, Any]:
    """Reuse the Phase 1 collector per file; never combine source text or test names."""
    valid_nodeids = valid_pool(raw, checkout)
    metrics = raw["metrics"]
    cases: list[dict[str, Any]] = []
    files: dict[str, Any] = {}
    declarations = metrics["source_test_declarations"]
    all_cases = metrics["case_level"]["test_cases"]
    for case in all_cases:
        if case["source_test"] not in declarations.get(case["source_file"], []):
            raise ValueError("Error-rate case is outside the declared function scope")
    for path, names in declarations.items():
        if names and path not in metrics["artifact_sha256"]:
            raise ValueError(f"Missing source artifact hash: {path}")
        if not names:
            continue
        report = collect_test_smells(
            test_path=checkout / path,
            error_rates={
                "case_level": {
                    "test_cases": [
                        case for case in all_cases if case["source_file"] == path
                    ]
                }
            },
            expected_tests=names,
            evidence_dir=evidence / path.removesuffix(".py"),
            pytest_smell_executable=pytest_smell,
            tempy_root=tempy_root,
        )
        report["test_path"] = path
        files[path] = report
        for case in report["test_cases"]:
            identity = f"{path}::{case['source_test']}"
            group = next(
                name for name, ids in partition_pool([identity]).items() if ids
            )
            cases.append(
                {
                    **case,
                    "source_file": path,
                    "source_id": identity,
                    "task_group": group,
                }
            )
    if len({case["source_id"] for case in cases}) != len(cases):
        raise ValueError("Duplicate source-function identity")
    return {
        "protocol_version": "1.0.0",
        "rule_version": RULE_VERSION,
        "analysis_unit": "source_test_function",
        "summary": summarize(cases),
        "test_cases": cases,
        "files": files,
        "by_task_group": {
            group: summarize([case for case in cases if case["task_group"] == group])
            for group in partition_pool(valid_nodeids)
        },
        "legacy_task_scope": summarize(
            [
                case
                for case in cases
                if case["task_group"] in ("maintenance", "retained_legacy")
            ]
        ),
        "valid_nodeids": valid_nodeids,
        "artifact_sha256": metrics["artifact_sha256"],
        "missing_expected_tests": metrics["missing_expected_tests"],
    }


def collect_all(
    repo: Path,
    error_dir: Path,
    output: Path,
    *,
    pytest_smell: Path | None = None,
    tempy_root: Path | None = None,
) -> dict[str, Any]:
    """Consume immutable error-rate commits, recording hashes for reproducibility."""
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
                "phase1_commit",
                "phase1_group",
                "phase2_group",
                "branch",
            )
        }
        print(f"Collecting test smells: {row['participant_id']}...", file=sys.stderr)
        try:
            raw_path = error_dir / row["output_file"]
            raw = json.loads(raw_path.read_text())
            if (
                raw["participant_commit"] != row["participant_commit"]
                or raw["baseline_commit"] != source["baseline_commit"]
                or raw["participant_number"] != row["participant_number"]
            ):
                raise ValueError("Error-rate manifest/raw provenance mismatch")
            with tempfile.TemporaryDirectory(prefix="phase2-smells-") as tmp:
                checkout = Path(tmp)
                export_snapshot(repo, row["participant_commit"], checkout)
                report = collect_submission(
                    checkout,
                    raw,
                    evidence=output / "tools" / row["participant_id"],
                    pytest_smell=pytest_smell,
                    tempy_root=tempy_root,
                )
            destination = output / "raw" / f"{row['participant_id']}.json"
            _write_json(
                destination,
                {
                    **record,
                    "baseline_commit": source["baseline_commit"],
                    "error_rate_raw_sha256": hashlib.sha256(
                        raw_path.read_bytes()
                    ).hexdigest(),
                    "test_smell": report,
                },
            )
            record.update(
                status="collected",
                output_file=destination.relative_to(output).as_posix(),
                summary=report["summary"],
            )
        except (ValueError, OSError, RuntimeError, SyntaxError) as exc:
            record.update(status="collection_failed", reason=str(exc))
        records.append(record)
    paths = [
        Path(__file__).resolve(),
        repo / "scripts/metric_collection_phase1/collect_test_smells.py",
        repo / "scripts/metric_collection_phase1/detect_test_smells_ast.py",
        repo / "scripts/metric_collection_phase1/summarize_test_smells.py",
        repo / "scripts/metric_collection_phase1/collect_error_rates.py",
        repo / "scripts/metric_collection_phase2/collect_coverage.py",
        repo / "scripts/metric_collection_phase2/collect_error_rates.py",
    ]
    return {
        "schema_version": "phase2-test-smells-v1",
        "phase": 2,
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
        "source_error_manifest": source_path.relative_to(repo).as_posix()
        if source_path.is_relative_to(repo)
        else str(source_path),
        "rule_version": RULE_VERSION,
        "formal_smells": list(FORMAL_SMELLS),
        "density_definition": "confirmed source-function/smell pairs / (eligible source functions * 7)",
        "participants": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--error-dir", type=Path, default=Path("results/phase2/error_rates")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("results/phase2/test_smells")
    )
    parser.add_argument("--pytest-smell", type=Path)
    parser.add_argument("--tempy-root", type=Path)
    args = parser.parse_args(argv)
    repo = args.repo_root.resolve()
    output = (repo / args.output_dir).resolve()
    if output.exists():
        parser.error(
            "Output directory exists; use a new directory to preserve evidence"
        )
    try:
        manifest = collect_all(
            repo,
            (repo / args.error_dir).resolve(),
            output,
            pytest_smell=args.pytest_smell,
            tempy_root=args.tempy_root,
        )
        _write_json(output / "collection_manifest.json", manifest)
        summarize_test_smells(
            output / "collection_manifest.json", output / "summary/test_smell.csv"
        )
        all_cases = []
        reports = {}
        for record in manifest["participants"]:
            if record["status"] == "collected":
                report = json.loads((output / record["output_file"]).read_text())[
                    "test_smell"
                ]
                reports[record["participant_id"]] = report
                all_cases.extend(report["test_cases"])
        _write_json(
            output / "summary/aggregate.json",
            {
                "participant_count": len(reports),
                "summary": summarize(all_cases),
                "by_task_group": {
                    group: summarize(
                        [case for case in all_cases if case["task_group"] == group]
                    )
                    for group in partition_pool([])
                },
                "legacy_task_scope": summarize(
                    [
                        case
                        for case in all_cases
                        if case["task_group"] in ("maintenance", "retained_legacy")
                    ]
                ),
            },
        )
        for scope in (*partition_pool([]), "legacy_task_scope"):
            rows = []
            for record in manifest["participants"]:
                selected = dict(record)
                if record["status"] == "collected":
                    report = reports[record["participant_id"]]
                    selected["summary"] = (
                        report["legacy_task_scope"]
                        if scope == "legacy_task_scope"
                        else report["by_task_group"][scope]
                    )
                rows.append(selected)
            scope_dir = output / "summary/by_task"
            scope_manifest = scope_dir / f"{scope}_manifest.json"
            _write_json(
                scope_manifest,
                {
                    "scope": scope,
                    "rule_version": RULE_VERSION,
                    "participants": rows,
                },
            )
            summarize_test_smells(scope_manifest, scope_dir / f"{scope}.csv")
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return int(any(row["status"] != "collected" for row in manifest["participants"]))


if __name__ == "__main__":
    raise SystemExit(main())
