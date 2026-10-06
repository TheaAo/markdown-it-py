"""Run the Phase 1 mutation engine on frozen Phase 2 original-path valid instances."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metric_collection_phase1 import collect_mutation_score as engine
from scripts.metric_collection_phase1.mutation_common import (
    catalog_hash,
    load_catalog,
    write_json,
)
from scripts.metric_collection_phase2.collect_coverage import (
    export_snapshot,
    valid_pool,
)
from scripts.metric_collection_phase2.collect_error_rates import PARTICIPANTS


def pilot_catalog(catalog: dict[str, Any], count: int) -> dict[str, Any]:
    """Deterministic module/operator round-robin pilot; not a score estimator."""
    if count <= 0:
        raise ValueError("Pilot count must be positive")
    strata: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for mutant in sorted(catalog["mutants"], key=lambda item: item["mutant_id"]):
        strata.setdefault((mutant["module"], mutant["operator_family"]), []).append(
            mutant
        )
    selected: list[dict[str, Any]] = []
    while len(selected) < min(count, len(catalog["mutants"])):
        for key in sorted(strata):
            if strata[key] and len(selected) < count:
                selected.append(strata[key].pop(0))
    return {
        **catalog,
        "mutants": selected,
        "catalog_hash": catalog_hash(selected),
        "catalog_kind": "phase2_execution_pilot",
        "scope": "execution pilot, not a formal score",
        "parent_catalog_hash": catalog["catalog_hash"],
    }


def participant_workers(participant_number: int, requested: int) -> int:
    """Participant 08 writes one fixed output file and must execute serially."""
    if requested < 1:
        raise ValueError("Mutation worker count must be positive")
    return 1 if participant_number == 8 else requested


def collect_all(args: argparse.Namespace) -> dict[str, Any]:
    repo = args.repo_root.resolve()
    error_dir = (repo / args.error_dir).resolve()
    output = (repo / args.output_dir).resolve()
    catalog_path = (repo / args.catalog).resolve()
    catalog = load_catalog(catalog_path)
    inputs_path = error_dir / "collection_manifest.json"
    inputs = json.loads(inputs_path.read_text())
    if catalog["baseline_commit"] != inputs["baseline_commit"]:
        raise ValueError("Catalog baseline differs from frozen participant SUT")
    if sorted(row["participant_number"] for row in inputs["participants"]) != sorted(
        PARTICIPANTS
    ):
        raise ValueError("Unexpected error-rate cohort")
    if args.pilot_count:
        catalog = pilot_catalog(catalog, args.pilot_count)
        catalog_path = output / "pilot_catalog.json"
        write_json(catalog_path, catalog)
    manifest_path = output / "collection_manifest.json"
    records: list[dict[str, Any]] = []
    manifest = {
        "phase": 2,
        "stage": "pilot" if args.pilot_count else "formal_execution",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": catalog["baseline_commit"],
        "sut_hash": catalog["sut_hash"],
        "catalog_hash": catalog["catalog_hash"],
        "error_rate_manifest_sha256": hashlib.sha256(
            inputs_path.read_bytes()
        ).hexdigest(),
        "valid_only_protocol": "phase2_original_paths_valid_instances_v1",
        "confirm_kills": True,
        "max_children": args.max_children,
        "participants": records,
        "final_score_status": "pending global non-equivalence and equivalent-mutant assessment",
    }
    source_paths = [
        Path(__file__).resolve(),
        Path(engine.__file__).resolve(),
        repo / "scripts/metric_collection_phase1/mutation_cache.py",
        repo / "scripts/metric_collection_phase1/mutation_common.py",
        repo / "scripts/metric_collection_phase2/collect_coverage.py",
    ]
    manifest["collector_sha256"] = {
        path.relative_to(repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in source_paths
    }
    write_json(manifest_path, manifest)
    for row in inputs["participants"]:
        if (
            args.participant_number
            and row["participant_number"] not in args.participant_number
        ):
            continue
        if row["status"] != "collected":
            raise ValueError("Complete frozen error-rate inputs required")
        workers = participant_workers(row["participant_number"], args.max_children)
        record = {
            key: row[key]
            for key in (
                "participant_number",
                "participant_id",
                "participant_commit",
                "phase1_group",
            )
        }
        record["max_children"] = workers
        raw_path = error_dir / row["output_file"]
        raw = json.loads(raw_path.read_text())
        if raw["participant_commit"] != row["participant_commit"]:
            raise ValueError("Frozen manifest/raw commit mismatch")
        destination = output / "raw" / f"{row['participant_id']}.json"
        log_path = output / "logs" / f"{row['participant_id']}.txt"
        if destination.exists():
            previous = json.loads(destination.read_text())
            if previous["catalog_hash"] != catalog["catalog_hash"]:
                raise ValueError(
                    "Existing result uses a different catalog; use a new output directory"
                )
        records.append(record)
        record["status"] = "running"
        record["started_at"] = datetime.now(timezone.utc).isoformat()
        write_json(manifest_path, manifest)
        print(f"Collecting mutation score: {row['participant_id']}...", flush=True)
        try:
            with tempfile.TemporaryDirectory(
                prefix="phase2-mutation-submission-"
            ) as tmp:
                checkout = Path(tmp)
                export_snapshot(repo, row["participant_commit"], checkout)
                nodes = valid_pool(raw, checkout)
                pool_path = checkout / "_valid_nodeids.json"
                write_json(pool_path, nodes)
                command = [
                    str(args.python.absolute()),
                    str(Path(engine.__file__).resolve()),
                    str(checkout / "tests/task/phase1/task.py"),
                    "--repo-root",
                    str(checkout),
                    "--python",
                    str(args.python.absolute()),
                    "--catalog",
                    str(catalog_path),
                    "--error-rates",
                    str(raw_path),
                    "--original-nodeids",
                    str(pool_path),
                    "--participant-id",
                    row["participant_id"],
                    "--participant-commit",
                    row["participant_commit"],
                    "--output",
                    str(destination),
                    "--audit-csv",
                    str(output / "audit" / f"{row['participant_id']}.csv"),
                    "--reliable-kill-evidence",
                    str(output / "reliable_kill_evidence.json"),
                    "--confirm-kills",
                    "--max-children",
                    str(workers),
                    "--timeout-multiplier",
                    "5",
                    "--timeout-constant",
                    "0.5",
                    "--quiet",
                ]
                if destination.exists():
                    command.extend(["--previous-result", str(destination)])
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("w") as log:
                    completed = subprocess.run(
                        command,
                        cwd=checkout,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                if completed.returncode:
                    raise RuntimeError(
                        f"Mutation engine exited {completed.returncode}; see {log_path}"
                    )
                result = json.loads(destination.read_text())
                existing_policy = manifest.get("execution_policy_hash")
                if (
                    existing_policy is not None
                    and existing_policy != result["execution_policy_hash"]
                ):
                    raise ValueError("Participant mutation execution policies differ")
                manifest["execution_policy_hash"] = result["execution_policy_hash"]
                manifest["execution_policy"] = result["execution_policy"]
                if (
                    result["execution_context"]["valid_only_protocol"]
                    != manifest["valid_only_protocol"]
                ):
                    raise ValueError("Unexpected mutation execution protocol")
                if result["summary"]["valid_tests_included"] != len(nodes):
                    raise ValueError("Mutation engine did not use the full valid pool")
            record.update(
                status="collected",
                summary=result["summary"],
                output_file=destination.relative_to(output).as_posix(),
            )
        except (ValueError, OSError, RuntimeError) as exc:
            record.update(status="collection_failed", reason=str(exc))
        record["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_json(manifest_path, manifest)
        print(f"  {record['status']}", flush=True)
        if record["status"] != "collected":
            break
    manifest["status"] = (
        "executions_complete"
        if all(row["status"] == "collected" for row in records)
        else "collection_failed"
    )
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(manifest_path, manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--error-dir", type=Path, default=Path("results/phase2/error_rates")
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(
            "results/phase2/mutation_score/catalog/task_relevant_mutant_catalog.json"
        ),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("results/phase2/mutation_score/formal")
    )
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--max-children", type=int, default=1)
    parser.add_argument(
        "--participant-number", type=int, action="append", choices=PARTICIPANTS
    )
    parser.add_argument("--pilot-count", type=int, default=0)
    args = parser.parse_args(argv)
    manifest = collect_all(args)
    return int(manifest["status"] != "executions_complete")


if __name__ == "__main__":
    raise SystemExit(main())
