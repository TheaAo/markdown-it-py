"""Inspect locally available submissions without checking out or executing tests."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

try:
    from scripts.metric_collection_phase1.collect_all_branches import (
        _git,
        _resolve_repo_root,
        _run,
        _write_json,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.metric_collection_phase1.collect_all_branches import (
        _git,
        _resolve_repo_root,
        _run,
        _write_json,
    )


TASK_PATHS = ("tests/task/phase1/task.py", "tests/task/task2.py")


def inventory_submissions(
    repo_root: Path,
    phase1_manifest: dict[str, Any],
    baseline_ref: str,
    remote: str,
) -> dict[str, Any]:
    """Pair frozen Phase 1 submissions with canonical Phase 2 refs for review."""
    baseline_commit = _git(repo_root, "rev-parse", f"{baseline_ref}^{{commit}}")
    baseline_sut_tree = _git(repo_root, "rev-parse", f"{baseline_commit}:markdown_it")
    records: list[dict[str, Any]] = []
    for original in phase1_manifest["participants"]:
        participant_id = original["participant_id"]
        branch = f"{remote}/{participant_id}-phase2"
        record: dict[str, Any] = {
            "participant_id": participant_id,
            "phase1_status": original["status"],
            "phase1_commit": original.get("participant_commit"),
            "phase2_ref": branch,
        }
        verify = _run(
            ["git", "rev-parse", "--verify", f"{branch}^{{commit}}"], cwd=repo_root
        )
        if verify.returncode:
            record["status"] = "missing_branch"
        else:
            commit = verify.stdout.strip()
            record["phase2_commit"] = commit
            missing_paths = [
                path
                for path in TASK_PATHS
                if _run(
                    ["git", "cat-file", "-e", f"{commit}:{path}"], cwd=repo_root
                ).returncode
            ]
            record["missing_task_paths"] = missing_paths
            sut_tree = _git(repo_root, "rev-parse", f"{commit}:markdown_it")
            record["sut_tree"] = sut_tree
            record["sut_matches_baseline"] = sut_tree == baseline_sut_tree
            record["protected_changes"] = _git(
                repo_root,
                "diff",
                "--name-only",
                baseline_commit,
                commit,
                "--",
                "markdown_it",
                "pyproject.toml",
                "tox.ini",
            ).splitlines()
            record["task_blob_hashes"] = {
                path: _git(repo_root, "rev-parse", f"{commit}:{path}")
                for path in TASK_PATHS
                if path not in missing_paths
            }
            if missing_paths:
                record["status"] = "missing_task_file"
            elif record["protected_changes"]:
                record["status"] = "baseline_mismatch"
            else:
                record["status"] = "pending_submission_review"
        records.append(record)
    return {
        "schema_version": "phase2-inventory-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_ref": baseline_ref,
        "baseline_commit": baseline_commit,
        "baseline_sut_tree": baseline_sut_tree,
        "task_paths": list(TASK_PATHS),
        "ref_source": "local refs only; no fetch performed",
        "participants": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", default="origin/experiment-base-phase2")
    parser.add_argument("--remote", default="origin")
    parser.add_argument(
        "--phase1-manifest",
        type=Path,
        default=Path("results/phase1/error_rates/collection_manifest.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/phase2/inventory/submissions.json"),
    )
    args = parser.parse_args(argv)
    try:
        repo_root = _resolve_repo_root(args.repo_root.resolve())
        manifest = json.loads((repo_root / args.phase1_manifest).read_text())
        report = inventory_submissions(repo_root, manifest, args.baseline, args.remote)
        _write_json(repo_root / args.output, report)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    counts: dict[str, int] = {}
    for record in report["participants"]:
        status = record["status"]
        counts[status] = counts.get(status, 0) + 1
    print(json.dumps(counts, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
