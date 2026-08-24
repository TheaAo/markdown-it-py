from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Sequence


PARTICIPANT_NUMBERS = tuple(range(1, 17))
NOT_PARTICIPATED = frozenset({13, 15})
TASK_PATH = Path("tests/task/task.py")
PROTECTED_PATHS = ("markdown_it/", "pyproject.toml", "tox.ini")


def _run(
    command: Sequence[str],
    cwd: Path,
    *,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def _git(repo_root: Path, *arguments: str) -> str:
    completed = _run(["git", *arguments], cwd=repo_root)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"git {' '.join(arguments)} failed: {detail}")
    return completed.stdout.strip()


def _resolve_repo_root(start: Path) -> Path:
    completed = _run(["git", "rev-parse", "--show-toplevel"], cwd=start)
    if completed.returncode != 0:
        raise RuntimeError("The command must be run inside the markdown-it-py repository.")
    return Path(completed.stdout.strip()).resolve()


def _branch_ref(remote: str, branch_prefix: str, participant_number: int) -> str:
    return f"{remote}/{branch_prefix}{participant_number:02d}"


def _protected_changes(changed_files: Sequence[str]) -> list[str]:
    return [
        path
        for path in changed_files
        if any(path == protected or path.startswith(protected) for protected in PROTECTED_PATHS)
    ]


def _participant_record(
    participant_number: int,
    remote: str,
    branch_prefix: str,
) -> dict[str, Any]:
    return {
        "participant_id": f"experiment-{participant_number:02d}",
        "participant_number": participant_number,
        "branch": _branch_ref(remote, branch_prefix, participant_number),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(f"{path.suffix}.tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(path)


def _remove_worktree(repo_root: Path, worktree_path: Path) -> None:
    completed = _run(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=repo_root,
    )
    if completed.returncode != 0:
        _run(["git", "worktree", "prune"], cwd=repo_root)


def _collect_branch(
    *,
    repo_root: Path,
    collector_path: Path,
    python_executable: Path,
    baseline_ref: str,
    baseline_commit: str,
    collector_commit: str,
    remote: str,
    branch_prefix: str,
    participant_number: int,
    output_dir: Path,
    timeout: float,
    worktree_parent: Path,
) -> dict[str, Any]:
    record = _participant_record(participant_number, remote, branch_prefix)
    branch_ref = record["branch"]
    raw_path = output_dir / "raw" / f"{record['participant_id']}.json"
    raw_path.unlink(missing_ok=True)

    if participant_number in NOT_PARTICIPATED:
        record.update(
            status="not_participated",
            reason="Participant did not take part in the experiment.",
        )
        return record

    verify = _run(
        ["git", "rev-parse", "--verify", f"{branch_ref}^{{commit}}"],
        cwd=repo_root,
    )
    if verify.returncode != 0:
        record.update(status="missing_branch", reason=f"Branch {branch_ref} was not found.")
        return record

    participant_commit = verify.stdout.strip()
    record["participant_commit"] = participant_commit
    ancestor = _run(
        ["git", "merge-base", "--is-ancestor", baseline_commit, participant_commit],
        cwd=repo_root,
    )
    if ancestor.returncode != 0:
        record.update(
            status="incompatible_history",
            reason=f"{branch_ref} is not based on {baseline_ref}.",
        )
        return record

    commits_ahead = int(
        _git(repo_root, "rev-list", "--count", f"{baseline_commit}..{participant_commit}")
    )
    record["commits_ahead_of_baseline"] = commits_ahead
    if commits_ahead == 0:
        record.update(
            status="no_submission",
            reason="Branch contains no participant commit after the experiment baseline.",
        )
        return record

    task_check = _run(
        ["git", "cat-file", "-e", f"{participant_commit}:{TASK_PATH.as_posix()}"],
        cwd=repo_root,
    )
    if task_check.returncode != 0:
        record.update(
            status="missing_task_file",
            reason=f"{TASK_PATH.as_posix()} does not exist on {branch_ref}.",
        )
        return record

    changed_output = _git(
        repo_root,
        "diff",
        "--name-only",
        f"{baseline_commit}...{participant_commit}",
    )
    changed_files = [line for line in changed_output.splitlines() if line]
    record["changed_files"] = changed_files
    protected_changes = _protected_changes(changed_files)
    if protected_changes:
        record.update(
            status="invalid_sut_modification",
            reason="Participant branch modifies the SUT or experiment configuration.",
            protected_changes=protected_changes,
        )
        return record

    worktree_path = worktree_parent / record["participant_id"]
    add_worktree = _run(
        [
            "git",
            "worktree",
            "add",
            "--detach",
            str(worktree_path),
            participant_commit,
        ],
        cwd=repo_root,
    )
    if add_worktree.returncode != 0:
        detail = add_worktree.stderr.strip() or add_worktree.stdout.strip()
        record.update(status="worktree_failed", reason=detail)
        return record

    try:
        completed = _run(
            [
                str(python_executable),
                str(collector_path),
                str(worktree_path / TASK_PATH),
                "--repo-root",
                str(worktree_path),
                "--python",
                str(python_executable),
                "--timeout",
                str(timeout),
            ],
            cwd=repo_root,
            timeout=timeout + 30,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            record.update(
                status="collection_failed",
                reason=f"Collector exited with code {completed.returncode}: {detail}",
            )
            return record

        try:
            metrics = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            record.update(
                status="invalid_collector_output",
                reason=f"Collector did not return valid JSON: {exc}",
            )
            return record

        metrics["test_path"] = TASK_PATH.as_posix()
        case_level = metrics.get("case_level", {})
        total = case_level.get("total_generated_test_cases")
        classified_total = sum(
            case_level.get(field, 0)
            for field in (
                "syntax_error_count",
                "runtime_error_count",
                "function_error_count",
                "valid_test_count",
            )
        )
        if total != classified_total:
            record.update(
                status="invalid_metric_totals",
                reason=f"Classified total {classified_total} does not equal total {total}.",
            )
            return record

        raw_payload = {
            "participant_id": record["participant_id"],
            "branch": branch_ref,
            "participant_commit": participant_commit,
            "baseline_ref": baseline_ref,
            "baseline_commit": baseline_commit,
            "collector_commit": collector_commit,
            "metrics": metrics,
        }
        _write_json(raw_path, raw_payload)
        record.update(
            status="collected",
            output_file=str(raw_path.relative_to(output_dir)),
            summary={
                "suite_collectable": metrics["suite_level"]["collectable"],
                "total_generated_test_cases": total,
                "syntax_error_count": case_level["syntax_error_count"],
                "runtime_error_count": case_level["runtime_error_count"],
                "function_error_count": case_level["function_error_count"],
                "valid_test_count": case_level["valid_test_count"],
                "syntax_error_rate": case_level["syntax_error_rate"],
                "runtime_error_rate": case_level["runtime_error_rate"],
                "function_error_rate": case_level["function_error_rate"],
            },
        )
        return record
    except subprocess.TimeoutExpired:
        record.update(
            status="collection_timeout",
            reason=f"Collection exceeded {timeout + 30:g} seconds.",
        )
        return record
    finally:
        _remove_worktree(repo_root, worktree_path)


def collect_all_branches(
    *,
    repo_root: Path,
    collector_path: Path,
    python_executable: Path,
    baseline_ref: str,
    remote: str,
    branch_prefix: str,
    output_dir: Path,
    timeout: float,
) -> dict[str, Any]:
    baseline_commit = _git(repo_root, "rev-parse", f"{baseline_ref}^{{commit}}")
    collector_commit = _git(repo_root, "rev-parse", "HEAD^{commit}")
    output_dir.mkdir(parents=True, exist_ok=True)

    participants: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="experiment-worktrees-") as temp_dir:
        worktree_parent = Path(temp_dir)
        for participant_number in PARTICIPANT_NUMBERS:
            participant_id = f"experiment-{participant_number:02d}"
            print(f"Collecting {participant_id}...", file=sys.stderr)
            record = _collect_branch(
                repo_root=repo_root,
                collector_path=collector_path,
                python_executable=python_executable,
                baseline_ref=baseline_ref,
                baseline_commit=baseline_commit,
                collector_commit=collector_commit,
                remote=remote,
                branch_prefix=branch_prefix,
                participant_number=participant_number,
                output_dir=output_dir,
                timeout=timeout,
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
        "participants": participants,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect error-rate metrics from all experiment participant branches."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root. Defaults to the current Git repository.",
    )
    parser.add_argument(
        "--collector",
        type=Path,
        default=Path(__file__).with_name("collect_error_rates.py"),
        help="Path to collect_error_rates.py on the metrics branch.",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=Path(sys.executable),
        help="Python executable containing pytest and project test dependencies.",
    )
    parser.add_argument(
        "--baseline",
        default="origin/experiment-base",
        help="Git ref for the common experiment baseline.",
    )
    parser.add_argument("--remote", default="origin", help="Remote containing experiment branches.")
    parser.add_argument(
        "--branch-prefix",
        default="experiment-",
        help="Branch prefix before the zero-padded participant number.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/error_rates"),
        help="Directory for raw participant JSON files and the manifest.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-participant collector timeout in seconds.",
    )
    args = parser.parse_args(argv)

    try:
        repo_root = _resolve_repo_root(args.repo_root.resolve())
        collector_path = args.collector.resolve()
        python_executable = args.python.absolute()
        output_dir = (repo_root / args.output_dir).resolve()
        if not collector_path.is_file():
            raise RuntimeError(f"Collector script does not exist: {collector_path}")
        if not python_executable.is_file():
            raise RuntimeError(f"Python executable does not exist: {python_executable}")

        manifest = collect_all_branches(
            repo_root=repo_root,
            collector_path=collector_path,
            python_executable=python_executable,
            baseline_ref=args.baseline,
            remote=args.remote,
            branch_prefix=args.branch_prefix,
            output_dir=output_dir,
            timeout=args.timeout,
        )
        _write_json(output_dir / "collection_manifest.json", manifest)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    statuses: dict[str, int] = {}
    for participant in manifest["participants"]:
        status = participant["status"]
        statuses[status] = statuses.get(status, 0) + 1
    print(json.dumps(statuses, indent=2))
    return 0 if set(statuses) <= {"collected", "not_participated"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
