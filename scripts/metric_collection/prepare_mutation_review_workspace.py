from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

try:
    from scripts.metric_collection.build_mutant_catalog import (
        WORKLOAD_FILES,
        WORKLOAD_SUPPORT,
    )
    from scripts.metric_collection.mutation_common import load_catalog
except ModuleNotFoundError:  # pragma: no cover
    from build_mutant_catalog import (  # type: ignore[no-redef]
        WORKLOAD_FILES,
        WORKLOAD_SUPPORT,
    )
    from mutation_common import load_catalog  # type: ignore[no-redef]


def _run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _write_config(workspace: Path, catalog: dict[str, Any]) -> None:
    only_mutate = catalog.get("only_mutate", [])
    mutation_filter = ""
    if only_mutate:
        mutation_filter = (
            "only_mutate=\n" + "\n".join(f"    {path}" for path in only_mutate) + "\n"
        )
    selection = "\n".join(f"    {name}" for name in WORKLOAD_FILES.values())
    also_copy = "\n".join(
        f"    {name}" for name in (*WORKLOAD_FILES.values(), WORKLOAD_SUPPORT)
    )
    (workspace / "setup.cfg").write_text(
        "[mutmut]\n"
        "source_paths=markdown_it/\n"
        f"{mutation_filter}"
        "pytest_add_cli_args_test_selection=\n"
        f"{selection}\n"
        "also_copy=\n"
        f"{also_copy}\n"
        "    mutation_materials/\n"
        "use_setproctitle=false\n"
        "track_dependencies=false\n",
        encoding="utf-8",
    )


def prepare_workspace(
    repo_root: Path,
    target: Path,
    catalog: dict[str, Any],
    mutant_id: str,
    mutmut_python: Path,
) -> Path:
    if target.exists():
        raise ValueError(f"review workspace already exists: {target}")
    by_id = {item["mutant_id"]: item for item in catalog["mutants"]}
    if mutant_id not in by_id:
        raise ValueError(f"unknown mutant ID: {mutant_id}")
    completed = _run(
        [
            "git",
            "worktree",
            "add",
            "--detach",
            str(target),
            catalog["baseline_commit"],
        ],
        repo_root,
    )
    if completed.returncode:
        raise RuntimeError(f"could not create review worktree:\n{completed.stdout}")
    try:
        for filename in (*WORKLOAD_FILES.values(), WORKLOAD_SUPPORT):
            shutil.copy2(Path(__file__).with_name(filename), target / filename)
        shutil.copytree(target / "tests/task/materials", target / "mutation_materials")
        _write_config(target, catalog)
        executable = mutmut_python.expanduser().absolute().parent / "mutmut"
        version = _run([str(executable), "--version"], target)
        if version.returncode or version.stdout.strip() != catalog["tool_version"]:
            raise RuntimeError("Mutmut version does not match the catalog")
        mutant = by_id[mutant_id]
        run = _run(
            [str(executable), "run", "--max-children", "1", mutant["mutant_name"]],
            target,
        )
        if run.returncode:
            raise RuntimeError(f"could not materialize mutant:\n{run.stdout}")
        guide = target / "MUTATION_REVIEW.md"
        guide.write_text(
            "# Disposable Mutation Review Workspace\n\n"
            f"Mutant ID: `{mutant_id}`  \n"
            f"Mutmut name: `{mutant['mutant_name']}`\n\n"
            "Run these commands from this directory:\n\n"
            "```bash\n"
            f"{executable} show '{mutant['mutant_name']}'\n"
            f"{executable} tests-for-mutant '{mutant['mutant_name']}'\n"
            f"{executable} run --max-children 1 '{mutant['mutant_name']}'\n"
            f"{executable} apply '{mutant['mutant_name']}'\n"
            "```\n\n"
            "`apply` modifies only this disposable worktree. Do not commit it. "
            "Inspect or test the mutation, then run the cleanup command printed "
            "by the preparation script from the main repository.\n",
            encoding="utf-8",
        )
        return guide
    except Exception:
        _run(["git", "worktree", "remove", "--force", str(target)], repo_root)
        raise


def cleanup_workspace(repo_root: Path, target: Path) -> None:
    completed = _run(["git", "worktree", "remove", "--force", str(target)], repo_root)
    if completed.returncode:
        raise RuntimeError(f"could not remove review worktree:\n{completed.stdout}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage a disposable mutant review worktree."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--repo-root", type=Path, default=Path.cwd())
    prepare.add_argument("--catalog", type=Path, required=True)
    prepare.add_argument("--mutant-id", required=True)
    prepare.add_argument("--mutmut-python", type=Path, required=True)
    prepare.add_argument("--target", type=Path, required=True)
    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--repo-root", type=Path, default=Path.cwd())
    cleanup.add_argument("--target", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            guide = prepare_workspace(
                args.repo_root.resolve(),
                args.target.resolve(),
                load_catalog(args.catalog.resolve()),
                args.mutant_id,
                args.mutmut_python,
            )
            print(f"Review guide: {guide}")
            print(
                "Cleanup: "
                f"{sys.executable} {Path(__file__).resolve()} cleanup "
                f"--repo-root {args.repo_root.resolve()} --target {args.target.resolve()}"
            )
        else:
            cleanup_workspace(args.repo_root.resolve(), args.target.resolve())
            print(f"Removed {args.target.resolve()}")
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
