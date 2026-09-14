from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter
from typing import Any

try:
    from scripts.metric_collection.collect_all_branches import (
        NOT_PARTICIPATED,
        PARTICIPANT_NUMBERS,
        PROTECTED_PATHS,
        TASK_PATH,
    )
    from scripts.metric_collection.mutation_common import (
        labeled_files_hash,
        load_catalog,
        write_json,
    )
    from scripts.metric_collection.mutation_cache import (
        build_execution_policy,
        execution_policy_hash,
        load_evidence,
    )
except ModuleNotFoundError:  # pragma: no cover
    from collect_all_branches import (  # type: ignore[no-redef]
        NOT_PARTICIPATED,
        PARTICIPANT_NUMBERS,
        PROTECTED_PATHS,
        TASK_PATH,
    )
    from mutation_common import (  # type: ignore[no-redef]
        labeled_files_hash,
        load_catalog,
        write_json,
    )
    from mutation_cache import (  # type: ignore[no-redef]
        build_execution_policy,
        execution_policy_hash,
        load_evidence,
    )


def _run(
    command: Sequence[str], cwd: Path, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _git(repo_root: Path, *arguments: str) -> str:
    completed = _run(["git", *arguments], repo_root)
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return completed.stdout.strip()


def _archive_existing_result(raw_path: Path, history_root: Path) -> Path | None:
    if not raw_path.is_file():
        return None
    digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()[:16]
    archived = history_root / raw_path.stem / f"{digest}{raw_path.suffix}"
    if not archived.is_file():
        archived.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw_path, archived)
    return archived


def _fixed_input_hashes(repo_root: Path) -> tuple[dict[str, str], dict[str, str]]:
    script_root = repo_root / "scripts/metric_collection"
    material_root = repo_root / "tests/task/materials"
    material_paths = {
        name: material_root / name
        for name in ("spec.md", "test_file.html", "commonmark.json")
    }
    material_hashes = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in material_paths.items()
    }
    workload_hashes = {
        layer: labeled_files_hash(
            (
                (filename, script_root / filename),
                (
                    "mutation_workload_common.py",
                    script_root / "mutation_workload_common.py",
                ),
                *(
                    (f"mutation_materials/{name}", path)
                    for name, path in material_paths.items()
                ),
            )
        )
        for layer, filename in {
            "specified": "mutation_specified_workload.py",
            "extended": "mutation_extended_workload.py",
        }.items()
    }
    return workload_hashes, material_hashes


def collect_all(args: argparse.Namespace) -> dict[str, Any]:
    collection_started = perf_counter()
    repo_root = args.repo_root.resolve()
    args.python = args.python.expanduser().absolute()
    output_dir = args.output_dir.resolve()
    catalog = load_catalog(args.catalog.resolve())
    workload_hashes, material_hashes = _fixed_input_hashes(repo_root)
    if workload_hashes != catalog.get("workload_hashes"):
        raise ValueError("current workload hashes do not match catalog")
    if material_hashes != catalog.get("material_hashes"):
        raise ValueError("current material hashes do not match catalog")
    baseline_commit = _git(repo_root, "rev-parse", f"{args.baseline}^{{commit}}")
    if baseline_commit != catalog["baseline_commit"]:
        raise ValueError("configured baseline commit does not match catalog")
    python_version_result = _run(
        [str(args.python), "-c", "import platform; print(platform.python_version())"],
        repo_root,
    )
    if python_version_result.returncode:
        raise RuntimeError("could not determine collection Python version")
    python_version = python_version_result.stdout.strip()
    if catalog.get("python_version") and catalog["python_version"] != python_version:
        raise ValueError("collection Python version does not match catalog")
    policy = build_execution_policy(
        timeout_multiplier=args.timeout_multiplier,
        timeout_constant=args.timeout_constant,
        timeout_retry_count=args.timeout_retry_count,
        confirm_kills=args.confirm_kills,
        confirmation_protocol="independent_second_execution_v3_incremental",
        exclude_duplicates=args.exclude_duplicates,
        test_timeout=args.test_timeout,
        execution_timeout=args.execution_timeout,
    )
    policy_hash = execution_policy_hash(policy)
    participants: list[dict[str, Any]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "collection_manifest.json"
    _archive_existing_result(manifest_path, output_dir / "history")
    evidence_path = output_dir / "reliable_kill_evidence.json"
    evidence = load_evidence(evidence_path)
    with tempfile.TemporaryDirectory(prefix="mutation-branches-") as directory:
        worktree_parent = Path(directory)
        participant_numbers = args.participant_number or list(PARTICIPANT_NUMBERS)
        for number in participant_numbers:
            participant_id = f"experiment-{number:02d}"
            branch = f"{args.remote}/{args.branch_prefix}{number:02d}"
            record: dict[str, Any] = {
                "participant_number": number,
                "participant_id": participant_id,
                "branch": branch,
            }
            raw_path = output_dir / "raw" / f"{participant_id}.json"
            if number in NOT_PARTICIPATED:
                record["status"] = "not_participated"
                participants.append(record)
                continue
            verify = _run(
                ["git", "rev-parse", "--verify", f"{branch}^{{commit}}"],
                repo_root,
            )
            if verify.returncode:
                record["status"] = "missing_branch"
                participants.append(record)
                continue
            participant_commit = verify.stdout.strip()
            record["participant_commit"] = participant_commit
            ancestor = _run(
                [
                    "git",
                    "merge-base",
                    "--is-ancestor",
                    baseline_commit,
                    participant_commit,
                ],
                repo_root,
            )
            if ancestor.returncode:
                record["status"] = "incompatible_history"
                participants.append(record)
                continue
            task_exists = _run(
                ["git", "cat-file", "-e", f"{participant_commit}:{TASK_PATH}"],
                repo_root,
            )
            if task_exists.returncode:
                record["status"] = "missing_task_file"
                participants.append(record)
                continue
            changed = _git(
                repo_root,
                "diff",
                "--name-only",
                f"{baseline_commit}...{participant_commit}",
            ).splitlines()
            protected = [
                path
                for path in changed
                if any(
                    path == root or path.startswith(root) for root in PROTECTED_PATHS
                )
            ]
            if protected:
                record.update(
                    status="invalid_sut_modification", protected_changes=protected
                )
                participants.append(record)
                continue
            worktree = worktree_parent / participant_id
            added = _run(
                [
                    "git",
                    "worktree",
                    "add",
                    "--detach",
                    str(worktree),
                    participant_commit,
                ],
                repo_root,
            )
            if added.returncode:
                record.update(status="worktree_failed", reason=added.stderr.strip())
                participants.append(record)
                continue
            try:
                participant_started = perf_counter()
                mutation_path = raw_path.with_suffix(".mutation.json")
                audit_path = output_dir / "audit" / f"{participant_id}.csv"
                test_review_path = output_dir / "test_review" / f"{participant_id}.csv"
                _archive_existing_result(audit_path, output_dir / "history")
                _archive_existing_result(test_review_path, output_dir / "history")
                command = [
                    str(args.python),
                    str(args.collector.resolve()),
                    str(worktree / TASK_PATH),
                    "--repo-root",
                    str(worktree),
                    "--python",
                    str(args.python),
                    "--catalog",
                    str(args.catalog.resolve()),
                    "--output",
                    str(mutation_path),
                    "--audit-csv",
                    str(audit_path),
                    "--test-review-csv",
                    str(test_review_path),
                    "--max-children",
                    str(args.max_children),
                    "--quiet",
                    "--test-timeout",
                    str(args.test_timeout),
                    "--timeout-multiplier",
                    str(args.timeout_multiplier),
                    "--timeout-constant",
                    str(args.timeout_constant),
                    "--timeout-retry-count",
                    str(args.timeout_retry_count),
                    "--participant-id",
                    participant_id,
                    "--participant-commit",
                    participant_commit,
                    "--confirmation-batch-size",
                    str(args.confirmation_batch_size),
                    "--reliable-kill-evidence",
                    str(evidence_path),
                ]
                if args.resume and raw_path.is_file():
                    command.extend(("--previous-result", str(raw_path)))
                if args.backfill_missing_durations:
                    command.append("--backfill-missing-durations")
                if args.execution_timeout is not None:
                    command.extend(("--execution-timeout", str(args.execution_timeout)))
                if args.confirm_kills:
                    command.append("--confirm-kills")
                if args.exclude_duplicates:
                    command.append("--exclude-duplicates")
                completed = _run(command, repo_root, timeout=args.participant_timeout)
                record["collection_duration_seconds"] = (
                    perf_counter() - participant_started
                )
                if completed.returncode:
                    record.update(
                        status="collection_failed",
                        reason=completed.stderr.strip() or completed.stdout[-4000:],
                    )
                else:
                    mutation = json.loads(mutation_path.read_text(encoding="utf-8"))
                    record["status"] = "collected"
                    archived_result = _archive_existing_result(
                        raw_path, output_dir / "history"
                    )
                    payload = {
                        "participant": record,
                        "catalog_hash": catalog["catalog_hash"],
                        "baseline_commit": baseline_commit,
                        "execution_context": mutation["execution_context"],
                        "execution_context_hash": mutation[
                            "execution_context_hash"
                        ],
                        "execution_policy": policy,
                        "execution_policy_hash": policy_hash,
                        "previous_result_archived_at": (
                            str(archived_result) if archived_result else None
                        ),
                        "mutation": mutation,
                    }
                    write_json(raw_path, payload)
                    mutation_path.unlink(missing_ok=True)
                    evidence = load_evidence(evidence_path)
                    record.update(
                        status="collected",
                        summary=mutation["summary"],
                        cache_statistics=mutation["cache_statistics"],
                    )
            except subprocess.TimeoutExpired:
                record.update(status="collection_timeout")
            finally:
                _run(["git", "worktree", "remove", "--force", str(worktree)], repo_root)
            record.setdefault(
                "collection_duration_seconds", perf_counter() - participant_started
            )
            participants.append(record)
            write_json(
                manifest_path,
                {
                    "catalog_hash": catalog["catalog_hash"],
                    "baseline_commit": baseline_commit,
                    "execution_policy_hash": policy_hash,
                    "reliable_kill_evidence_count": len(evidence["records"]),
                    "participants": participants,
                },
            )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "catalog_hash": catalog["catalog_hash"],
        "baseline_commit": baseline_commit,
        "execution_policy": policy,
        "execution_policy_hash": policy_hash,
        "reliable_kill_evidence_count": len(evidence["records"]),
        "collection_duration_seconds": perf_counter() - collection_started,
        "participants": participants,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect Mutation Score across branches."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument(
        "--collector",
        type=Path,
        default=Path(__file__).with_name("collect_mutation_score.py"),
    )
    parser.add_argument("--baseline", default="origin/experiment-base")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch-prefix", default="experiment-")
    parser.add_argument(
        "--participant-number",
        action="append",
        type=int,
        choices=PARTICIPANT_NUMBERS,
        help="Collect only this participant number; repeat to select several.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/mutation_score"),
    )
    parser.add_argument("--max-children", type=int, default=4)
    parser.add_argument("--test-timeout", type=float, default=120.0)
    parser.add_argument("--execution-timeout", type=float)
    parser.add_argument("--timeout-multiplier", type=float, default=5.0)
    parser.add_argument("--timeout-constant", type=float, default=0.5)
    parser.add_argument("--timeout-retry-count", type=int, default=1)
    parser.add_argument("--confirmation-batch-size", type=int, default=25)
    parser.add_argument("--participant-timeout", type=float)
    parser.add_argument("--confirm-kills", action="store_true")
    parser.add_argument("--exclude-duplicates", action="store_true")
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--backfill-missing-durations",
        action="store_true",
        help=(
            "rerun matching cached rows without timing metadata; ordinary resume "
            "continues to reuse those rows"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = collect_all(args)
        write_json(args.output_dir.resolve() / "collection_manifest.json", manifest)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output_dir.resolve() / 'collection_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
