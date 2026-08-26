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
        raise RuntimeError(
            "The command must be run inside the markdown-it-py repository."
        )
    return Path(completed.stdout.strip()).resolve()


def _branch_ref(remote: str, branch_prefix: str, participant_number: int) -> str:
    return f"{remote}/{branch_prefix}{participant_number:02d}"


def _protected_changes(changed_files: Sequence[str]) -> list[str]:
    return [
        path
        for path in changed_files
        if any(
            path == protected or path.startswith(protected)
            for protected in PROTECTED_PATHS
        )
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


def _error_rate_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    case_level = metrics.get("case_level")
    suite_level = metrics.get("suite_level")
    if not isinstance(case_level, dict) or not isinstance(suite_level, dict):
        raise ValueError("error-rate output is missing suite_level or case_level")
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
        raise ValueError(
            f"classified total {classified_total} does not equal total {total}"
        )
    return {
        "suite_collectable": suite_level["collectable"],
        "total_generated_test_cases": total,
        "syntax_error_count": case_level["syntax_error_count"],
        "runtime_error_count": case_level["runtime_error_count"],
        "function_error_count": case_level["function_error_count"],
        "valid_test_count": case_level["valid_test_count"],
        "syntax_error_rate": case_level["syntax_error_rate"],
        "runtime_error_rate": case_level["runtime_error_rate"],
        "function_error_rate": case_level["function_error_rate"],
    }


def _coverage_scope_summary(scope: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for metric_name in ("statement", "branch"):
        metric = scope.get(metric_name)
        if not isinstance(metric, dict):
            raise ValueError(f"coverage scope is missing {metric_name}")
        covered = metric.get("covered")
        total = metric.get("total")
        if (
            isinstance(covered, bool)
            or isinstance(total, bool)
            or not isinstance(covered, int)
            or not isinstance(total, int)
            or total < 0
        ):
            raise ValueError(f"invalid {metric_name} coverage counts")
        if covered < 0 or covered > total:
            raise ValueError(f"invalid {metric_name} covered count")
        summary[metric_name] = {
            "covered": covered,
            "total": total,
            "rate": covered / total if total else 1.0,
        }
    return summary


def _coverage_summary(coverage: dict[str, Any]) -> dict[str, Any]:
    combined = coverage.get("all_tests_combined")
    if not isinstance(combined, dict):
        raise ValueError("coverage output is missing all_tests_combined")
    participant_scope = coverage.get("participant_tests_only")
    if participant_scope is not None and not isinstance(participant_scope, dict):
        raise ValueError("participant_tests_only must be an object or null")
    valid_tests = coverage.get("valid_tests_included")
    invalid_tests = coverage.get("invalid_tests_excluded")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in (valid_tests, invalid_tests)
    ):
        raise ValueError("coverage test counts must be non-negative integers")
    return {
        "valid_tests_included": valid_tests,
        "invalid_tests_excluded": invalid_tests,
        "participant_tests_only": (
            _coverage_scope_summary(participant_scope)
            if participant_scope is not None
            else None
        ),
        "all_tests_combined": _coverage_scope_summary(combined),
    }


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
    coverage_collector_path: Path | None = None,
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
        record.update(
            status="missing_branch", reason=f"Branch {branch_ref} was not found."
        )
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
        _git(
            repo_root,
            "rev-list",
            "--count",
            f"{baseline_commit}..{participant_commit}",
        )
    )
    record["commits_ahead_of_baseline"] = commits_ahead
    if commits_ahead == 0:
        record.update(
            status="no_submission",
            reason=(
                "Branch contains no participant commit after the experiment baseline."
            ),
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
        active_collector = coverage_collector_path or collector_path
        command = [
            str(python_executable),
            str(active_collector),
            str(worktree_path / TASK_PATH),
            "--repo-root",
            str(worktree_path),
            "--python",
            str(python_executable),
            "--timeout",
            str(timeout),
        ]
        if coverage_collector_path is not None:
            command.extend(("--format", "json"))
        collector_timeout = (
            timeout * 5 + 30 if coverage_collector_path else timeout + 30
        )
        completed = _run(
            command,
            cwd=repo_root,
            timeout=collector_timeout,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            record.update(
                status="collection_failed",
                reason=f"Collector exited with code {completed.returncode}: {detail}",
            )
            return record

        try:
            collector_output = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            record.update(
                status="invalid_collector_output",
                reason=f"Collector did not return valid JSON: {exc}",
            )
            return record

        if not isinstance(collector_output, dict):
            record.update(
                status="invalid_collector_output",
                reason="Collector output must be a JSON object.",
            )
            return record
        coverage: dict[str, Any] | None = None
        if coverage_collector_path is None:
            metrics = collector_output
        else:
            metrics = collector_output.get("error_rates")
            coverage = collector_output.get("coverage")
            if not isinstance(metrics, dict) or not isinstance(coverage, dict):
                record.update(
                    status="invalid_collector_output",
                    reason=(
                        "Coverage collector output is missing error_rates or coverage."
                    ),
                )
                return record
        metrics["test_path"] = TASK_PATH.as_posix()
        try:
            summary = _error_rate_summary(metrics)
            if coverage is not None:
                summary["coverage"] = _coverage_summary(coverage)
        except (KeyError, TypeError, ValueError) as exc:
            record.update(status="invalid_metric_totals", reason=str(exc))
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
        if coverage is not None:
            raw_payload["coverage"] = coverage
        _write_json(raw_path, raw_payload)
        record.update(
            status="collected",
            output_file=str(raw_path.relative_to(output_dir)),
            summary=summary,
        )
        return record
    except subprocess.TimeoutExpired:
        record.update(
            status="collection_timeout",
            reason=f"Collection exceeded {collector_timeout:g} seconds.",
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
    coverage_collector_path: Path | None = None,
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
                coverage_collector_path=coverage_collector_path,
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
        "coverage_collector_script": (
            str(coverage_collector_path) if coverage_collector_path else None
        ),
        "python_executable": str(python_executable),
        "participants": participants,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Collect test-quality metrics from all experiment participant branches."
        )
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
        "--coverage-collector",
        type=Path,
        default=Path(__file__).with_name("collect_coverage.py"),
        help="Path to collect_coverage.py; enabled by default.",
    )
    parser.add_argument(
        "--skip-coverage",
        action="store_true",
        help="Collect error rates only and omit coverage metrics.",
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
    parser.add_argument(
        "--remote", default="origin", help="Remote containing experiment branches."
    )
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
        coverage_collector_path = (
            None if args.skip_coverage else args.coverage_collector.resolve()
        )
        python_executable = args.python.absolute()
        output_dir = (repo_root / args.output_dir).resolve()
        if not collector_path.is_file():
            raise RuntimeError(f"Collector script does not exist: {collector_path}")
        if (
            coverage_collector_path is not None
            and not coverage_collector_path.is_file()
        ):
            raise RuntimeError(
                f"Coverage collector script does not exist: {coverage_collector_path}"
            )
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
            coverage_collector_path=coverage_collector_path,
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
