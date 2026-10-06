"""Continue from a reproducible Phase 2 catalog through pilot and full execution."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metric_collection_phase1.mutation_common import load_catalog, write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--catalog-wait-seconds", type=float, default=3600)
    args = parser.parse_args(argv)
    repo = args.repo_root.resolve()
    root = repo / "results/phase2/mutation_score"
    status_path = root / "pipeline_status.json"
    status: dict[str, Any] = {
        "stage": "waiting_for_reproducible_catalog",
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(status_path, status)
    catalog_path = root / "catalog/task_relevant_mutant_catalog.json"
    deadline = time.monotonic() + args.catalog_wait_seconds
    try:
        while not catalog_path.exists():
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    "Catalog was not ready within the configured wait budget"
                )
            time.sleep(5)
        catalog = load_catalog(catalog_path)
        if (
            catalog["catalog_kind"] != "task_relevant_census"
            or not catalog["generation_comparison"]["semantic_catalog_hash_match"]
        ):
            raise ValueError(
                "A complete, twice-generated task-relevant catalog is required"
            )
        status.update(
            catalog_hash=catalog["catalog_hash"],
            task_relevant_mutants=len(catalog["mutants"]),
        )
        collector = Path(__file__).with_name("collect_mutation_score.py")
        status["collector_sha256"] = hashlib.sha256(collector.read_bytes()).hexdigest()
        for stage, extra in (
            (
                "pilot",
                [
                    "--pilot-count",
                    "30",
                    "--participant-number",
                    "2",
                    "--participant-number",
                    "8",
                ],
            ),
            ("formal", []),
        ):
            status["stage"] = stage
            write_json(status_path, status)
            print(f"Starting Phase 2 mutation {stage}...", flush=True)
            completed = subprocess.run(
                [
                    str(args.python.absolute()),
                    str(collector),
                    "--repo-root",
                    str(repo),
                    "--python",
                    str(args.python.absolute()),
                    "--output-dir",
                    str(root / stage),
                    *extra,
                ],
                cwd=repo,
                check=False,
            )
            if completed.returncode:
                raise RuntimeError(
                    f"{stage} execution failed; inspect stage manifest and logs"
                )
            manifest = json.loads(
                (root / stage / "collection_manifest.json").read_text()
            )
            if manifest["status"] != "executions_complete":
                raise RuntimeError(f"{stage} execution is incomplete")
        status.update(
            stage="executions_complete",
            status="completed",
            final_score_status="pending global equivalence assessment",
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
    except (ValueError, OSError, RuntimeError) as exc:
        status.update(
            status="failed",
            reason=str(exc),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
        write_json(status_path, status)
        print(str(exc), file=sys.stderr)
        return 1
    write_json(status_path, status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
