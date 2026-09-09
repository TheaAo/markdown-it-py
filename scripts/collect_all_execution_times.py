from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

try:
    from scripts.collect_all_branches import (
        NOT_PARTICIPATED,
        PARTICIPANT_NUMBERS,
        TASK_PATH,
        _git,
        _participant_record,
        _protected_changes,
        _remove_worktree,
        _resolve_repo_root,
        _run,
        _write_json,
    )
except ModuleNotFoundError:  # pragma: no cover - used when run as a script
    from collect_all_branches import (  # type: ignore[no-redef]
        NOT_PARTICIPATED,
        PARTICIPANT_NUMBERS,
        TASK_PATH,
        _git,
        _participant_record,
        _protected_changes,
        _remove_worktree,
        _resolve_repo_root,
        _run,
        _write_json,
    )


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    status = report.get("status")
    if not isinstance(status, str):
        raise ValueError("execution-time output is missing status")
    valid = report.get("valid_tests_included")
    invalid = report.get("invalid_tests_excluded")
    if not isinstance(valid, int) or not isinstance(invalid, int):
        raise ValueError("execution-time output has invalid test counts")
    timing = report.get("summary")
    if status == "collected":
        if not isinstance(timing, dict):
            raise ValueError("collected execution-time output is missing summary")
        execution_time = timing.get("execution_time_seconds")
        if not isinstance(execution_time, int | float) or execution_time <= 0:
            raise ValueError("execution_time_seconds must be positive")
    elif status == "no_valid_tests":
        if timing is not None:
            raise ValueError("no_valid_tests output must not contain a summary")
    else:
        raise ValueError(f"collector returned non-success status {status!r}")
    return {
        "metric_status": status,
        "valid_tests_included": valid,
        "invalid_tests_excluded": invalid,
        "execution_time": timing,
    }


def _collect_participant(
    *,
    repo_root: Path,
    collector_path: Path,
    python_executable: Path,
    baseline_commit: str,
    collector_commit: str,
    remote: str,
    branch_prefix: str,
    participant_number: int,
    output_dir: Path,
    timeout: float,
    warmups: int,
    measurements: int,
    cv_review_threshold: float,
    worktree_parent: Path,
) -> dict[str, Any]:
    record = _participant_record(participant_number, remote, branch_prefix)
    raw_path = output_dir / "raw" / f"{record['participant_id']}.json"
    raw_path.unlink(missing_ok=True)
    if participant_number in NOT_PARTICIPATED:
        record.update(
            status="not_participated",
            reason="Participant did not take part in the experiment.",
        )
        return record

    verify = _run(
        ["git", "rev-parse", "--verify", f"{record['branch']}^{{commit}}"],
        cwd=repo_root,
    )
    if verify.returncode != 0:
        record.update(status="missing_branch", reason="Participant branch not found.")
        return record
    participant_commit = verify.stdout.strip()
    record["participant_commit"] = participant_commit
    ancestor = _run(
        ["git", "merge-base", "--is-ancestor", baseline_commit, participant_commit],
        cwd=repo_root,
    )
    if ancestor.returncode != 0:
        record.update(status="incompatible_history", reason="Incompatible baseline.")
        return record

    changed_files = _git(
        repo_root,
        "diff",
        "--name-only",
        f"{baseline_commit}...{participant_commit}",
    ).splitlines()
    protected = _protected_changes(changed_files)
    if protected:
        record.update(
            status="invalid_sut_modification",
            reason="Participant branch modifies protected experiment files.",
            protected_changes=protected,
        )
        return record

    task_check = _run(
        ["git", "cat-file", "-e", f"{participant_commit}:{TASK_PATH.as_posix()}"],
        cwd=repo_root,
    )
    if task_check.returncode != 0:
        record.update(status="missing_task_file", reason="Task file not found.")
        return record

    worktree_path = worktree_parent / record["participant_id"]
    added = _run(
        ["git", "worktree", "add", "--detach", str(worktree_path), participant_commit],
        cwd=repo_root,
    )
    if added.returncode != 0:
        record.update(status="worktree_failed", reason=added.stderr.strip())
        return record

    try:
        command = [
            str(python_executable),
            str(collector_path),
            str(worktree_path / TASK_PATH),
            "--repo-root",
            str(worktree_path),
            "--python",
            str(python_executable),
            "--timeout",
            str(timeout),
            "--warmups",
            str(warmups),
            "--measurements",
            str(measurements),
            "--cv-review-threshold",
            str(cv_review_threshold),
        ]
        collector_timeout = timeout * (warmups + measurements + 2) + 300
        completed = _run(command, cwd=repo_root, timeout=collector_timeout)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            record.update(status="collection_failed", reason=detail[-4000:])
            return record
        try:
            report = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            record.update(status="invalid_collector_output", reason=str(exc))
            return record
        if not isinstance(report, dict):
            record.update(
                status="invalid_collector_output",
                reason="Collector output must be a JSON object.",
            )
            return record
        try:
            summary = _summary(report)
        except ValueError as exc:
            record.update(status="invalid_collector_output", reason=str(exc))
            return record
        _write_json(
            raw_path,
            {
                "participant_id": record["participant_id"],
                "branch": record["branch"],
                "participant_commit": participant_commit,
                "baseline_commit": baseline_commit,
                "collector_commit": collector_commit,
                "execution_time": report,
            },
        )
        record.update(
            status="collected",
            output_file=str(raw_path.relative_to(output_dir)),
            summary=summary,
        )
        return record
    finally:
        _remove_worktree(repo_root, worktree_path)


def collect_all_execution_times(
    *,
    repo_root: Path,
    collector_path: Path,
    python_executable: Path,
    baseline_ref: str,
    remote: str,
    branch_prefix: str,
    output_dir: Path,
    timeout: float,
    warmups: int,
    measurements: int,
    cv_review_threshold: float = 0.05,
    participant_numbers: tuple[int, ...] = PARTICIPANT_NUMBERS,
) -> dict[str, Any]:
    baseline_commit = _git(repo_root, "rev-parse", f"{baseline_ref}^{{commit}}")
    collector_commit = _git(repo_root, "rev-parse", "HEAD^{commit}")
    output_dir.mkdir(parents=True, exist_ok=True)
    participants: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="execution-time-branches-") as directory:
        worktree_parent = Path(directory)
        for participant_number in participant_numbers:
            participant_id = f"experiment-{participant_number:02d}"
            print(f"Collecting {participant_id}...", file=sys.stderr)
            record = _collect_participant(
                repo_root=repo_root,
                collector_path=collector_path,
                python_executable=python_executable,
                baseline_commit=baseline_commit,
                collector_commit=collector_commit,
                remote=remote,
                branch_prefix=branch_prefix,
                participant_number=participant_number,
                output_dir=output_dir,
                timeout=timeout,
                warmups=warmups,
                measurements=measurements,
                cv_review_threshold=cv_review_threshold,
                worktree_parent=worktree_parent,
            )
            participants.append(record)
            print(f"  {record['status']}", file=sys.stderr)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": str(repo_root),
        "baseline_ref": baseline_ref,
        "baseline_commit": baseline_commit,
        "collector_commit": collector_commit,
        "collector_script": str(collector_path),
        "python_executable": str(python_executable),
        "warmup_count": warmups,
        "measurement_count": measurements,
        "timeout_seconds": timeout,
        "cv_review_threshold": cv_review_threshold,
        "participants": participants,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect execution time across participant branches."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--collector",
        type=Path,
        default=Path(__file__).with_name("collect_execution_time.py"),
    )
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--baseline", default="origin/experiment-base")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch-prefix", default="experiment-")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("results/execution_time")
    )
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--measurements", type=int, default=15)
    parser.add_argument("--cv-review-threshold", type=float, default=0.05)
    parser.add_argument(
        "--participants",
        type=int,
        nargs="+",
        choices=PARTICIPANT_NUMBERS,
        default=list(PARTICIPANT_NUMBERS),
        help="Participant numbers to collect; defaults to all participants.",
    )
    args = parser.parse_args(argv)

    try:
        repo_root = _resolve_repo_root(args.repo_root.resolve())
        manifest = collect_all_execution_times(
            repo_root=repo_root,
            collector_path=args.collector.resolve(),
            python_executable=args.python.absolute(),
            baseline_ref=args.baseline,
            remote=args.remote,
            branch_prefix=args.branch_prefix,
            output_dir=(repo_root / args.output_dir).resolve(),
            timeout=args.timeout,
            warmups=args.warmups,
            measurements=args.measurements,
            cv_review_threshold=args.cv_review_threshold,
            participant_numbers=tuple(dict.fromkeys(args.participants)),
        )
        _write_json(
            (repo_root / args.output_dir).resolve() / "collection_manifest.json",
            manifest,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    statuses = {participant["status"] for participant in manifest["participants"]}
    return 0 if statuses <= {"collected", "not_participated"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
