from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from time import perf_counter
from typing import Any, Sequence


MUTPY_SUMMARY_PATTERN = re.compile(
    r"- all: (?P<total>\d+).*?"
    r"- killed: (?P<killed>\d+).*?"
    r"- survived: (?P<survived>\d+).*?"
    r"- incompetent: (?P<incompetent>\d+).*?"
    r"- timeout: (?P<timeout>\d+)",
    re.DOTALL,
)
MUTPY_CATALOG_PATTERN = re.compile(
    r"^\s+- lineno: (?P<line>\d+)\n\s+operator: (?P<operator>\S+)",
    re.MULTILINE,
)
SUMMARY_COLUMNS = (
    "tool",
    "version",
    "compatible",
    "duration_seconds",
    "total_mutants",
    "killed",
    "survived",
    "incompetent",
    "timeout",
    "no_tests",
    "catalog_reproducible",
)


def _run(
    command: Sequence[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> tuple[subprocess.CompletedProcess[str], float]:
    started = perf_counter()
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )
    return completed, perf_counter() - started


def _tool_executable(python: Path, name: str) -> Path:
    executable = python.expanduser().absolute().parent / name
    if not executable.is_file():
        raise ValueError(f"tool executable does not exist: {executable}")
    return executable


def _version(executable: Path, cwd: Path) -> str:
    completed = subprocess.run(
        [str(executable), "--version"],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return completed.stdout.strip().splitlines()[-1] if completed.stdout else "unknown"


def _archive_ref(repo_root: Path, ref: str, paths: Sequence[str], target: Path) -> None:
    archive_path = target.parent / f"{target.name}.tar"
    with archive_path.open("wb") as stream:
        completed = subprocess.run(
            ["git", "archive", ref, *paths],
            cwd=repo_root,
            stdout=stream,
            stderr=subprocess.PIPE,
            check=False,
        )
    if completed.returncode:
        raise ValueError(completed.stderr.decode().strip())
    target.mkdir(parents=True)
    with tarfile.open(archive_path) as archive:
        archive.extractall(target, filter="data")
    archive_path.unlink()


def _prepare_baseline(
    repo_root: Path, sut_ref: str, participant_ref: str, target: Path
) -> None:
    _archive_ref(repo_root, sut_ref, ["markdown_it", "pyproject.toml"], target)
    participant_archive = target.parent / "participant"
    _archive_ref(repo_root, participant_ref, ["tests/task"], participant_archive)
    shutil.copytree(participant_archive / "tests", target / "tests")


def _write_log(output_dir: Path, name: str, output: str) -> None:
    (output_dir / name).write_text(output, encoding="utf-8")


def parse_mutpy_summary(output: str) -> dict[str, int]:
    match = MUTPY_SUMMARY_PATTERN.search(output)
    if match is None:
        raise ValueError("MutPy summary was not found")
    return {name: int(value) for name, value in match.groupdict().items()}


def mutpy_catalog(report: str) -> list[tuple[int, str]]:
    return sorted(
        (int(match.group("line")), match.group("operator"))
        for match in MUTPY_CATALOG_PATTERN.finditer(report)
    )


def parse_mutmut_stats(payload: str) -> dict[str, int]:
    raw = json.loads(payload)
    fields = ("total", "killed", "survived", "timeout", "no_tests")
    if not isinstance(raw, dict) or any(
        isinstance(raw.get(field), bool) or not isinstance(raw.get(field), int)
        for field in fields
    ):
        raise ValueError("Mutmut statistics have an unexpected schema")
    return {field: raw[field] for field in fields}


def parse_cosmic_ray_dump(payload: str) -> tuple[Counter[str], list[tuple[Any, ...]]]:
    outcomes: Counter[str] = Counter()
    catalog: list[tuple[Any, ...]] = []
    for line in payload.splitlines():
        if not line.strip():
            continue
        work_item, result = json.loads(line)
        for mutation in work_item["mutations"]:
            catalog.append(
                (
                    mutation["module_path"],
                    mutation["operator_name"],
                    mutation["occurrence"],
                    tuple(mutation["start_pos"]),
                    tuple(mutation["end_pos"]),
                )
            )
        outcomes["pending" if result is None else result["test_outcome"]] += 1
    return outcomes, sorted(catalog)


def _mutpy_run(workspace: Path, python: Path, output_dir: Path) -> dict[str, Any]:
    executable = _tool_executable(python, "mut.py")
    shutil.copy2(workspace / "tests/task/task.py", workspace / "test_pilot.py")
    shutil.copytree(workspace / "tests/task/materials", workspace / "materials")
    command = [
        str(executable),
        "--target",
        "markdown_it.ruler",
        "--unit-test",
        "test_pilot",
        "--runner",
        "pytest",
        "--report",
        "mutpy.yml",
        "--path",
        ".",
    ]
    completed, duration = _run(command, workspace)
    _write_log(output_dir, "mutpy.log", completed.stdout)
    summary = parse_mutpy_summary(completed.stdout)
    report = (workspace / "mutpy.yml").read_text(encoding="utf-8")
    catalog = mutpy_catalog(report)
    compatible = completed.returncode == 0 and summary["incompetent"] == 0
    return {
        "tool": "MutPy",
        "version": _version(executable, workspace),
        "compatible": compatible,
        "duration_seconds": duration,
        **summary,
        "no_tests": 0,
        "catalog": catalog,
        "catalog_reproducible": None,
    }


def _write_mutmut_config(workspace: Path) -> None:
    (workspace / "setup.cfg").write_text(
        "[mutmut]\n"
        "source_paths=markdown_it/\n"
        "only_mutate=markdown_it/ruler.py\n"
        "pytest_add_cli_args_test_selection=tests/task/task.py\n"
        "use_setproctitle=false\n"
        "track_dependencies=false\n",
        encoding="utf-8",
    )


def _mutmut_run(workspace: Path, python: Path, output_dir: Path) -> dict[str, Any]:
    executable = _tool_executable(python, "mutmut")
    _write_mutmut_config(workspace)
    env = dict(os.environ)
    env["PATH"] = (
        f"{python.expanduser().absolute().parent}{os.pathsep}{env.get('PATH', '')}"
    )
    completed, duration = _run([str(executable), "run"], workspace, env=env)
    _write_log(output_dir, "mutmut.log", completed.stdout)
    export, _ = _run([str(executable), "export-cicd-stats"], workspace, env=env)
    if export.returncode:
        raise ValueError(f"Mutmut export failed:\n{export.stdout}")
    stats_path = workspace / "mutants/mutmut-cicd-stats.json"
    stats = parse_mutmut_stats(stats_path.read_text(encoding="utf-8"))
    results, _ = _run([str(executable), "results", "--all", "true"], workspace, env=env)
    catalog = sorted(
        line.split(":", 1)[0].strip()
        for line in results.stdout.splitlines()
        if line.strip()
    )
    return {
        "tool": "Mutmut",
        "version": _version(executable, workspace),
        "compatible": completed.returncode == 0,
        "duration_seconds": duration,
        **stats,
        "incompetent": 0,
        "catalog": catalog,
        "catalog_reproducible": None,
    }


def _write_cosmic_ray_config(workspace: Path, python: Path) -> Path:
    path = workspace / "cosmic-ray.toml"
    path.write_text(
        "[cosmic-ray]\n"
        'module-path = "markdown_it/ruler.py"\n'
        "timeout = 5.0\n"
        "excluded-modules = []\n"
        f'test-command = "{python.expanduser().absolute()} '
        '-m pytest -q tests/task/task.py"\n\n'
        "[cosmic-ray.distributor]\n"
        'name = "local"\n',
        encoding="utf-8",
    )
    return path


def _cosmic_ray_run(workspace: Path, python: Path, output_dir: Path) -> dict[str, Any]:
    executable = _tool_executable(python, "cosmic-ray")
    config = _write_cosmic_ray_config(workspace, python)
    session = workspace / "session.sqlite"
    initialized, _ = _run(
        [str(executable), "init", str(config), str(session)], workspace
    )
    if initialized.returncode:
        raise ValueError(f"Cosmic Ray init failed:\n{initialized.stdout}")
    completed, duration = _run(
        [str(executable), "exec", str(config), str(session)], workspace
    )
    dumped, _ = _run([str(executable), "dump", str(session)], workspace)
    _write_log(output_dir, "cosmic-ray.log", completed.stdout)
    _write_log(output_dir, "cosmic-ray.jsonl", dumped.stdout)
    outcomes, catalog = parse_cosmic_ray_dump(dumped.stdout)
    return {
        "tool": "Cosmic Ray",
        "version": _version(executable, workspace),
        "compatible": completed.returncode == 0 and not outcomes["pending"],
        "duration_seconds": duration,
        "total": sum(outcomes.values()),
        "killed": outcomes["killed"],
        "survived": outcomes["survived"],
        "incompetent": outcomes["incompetent"],
        "timeout": outcomes["timeout"],
        "no_tests": 0,
        "catalog": catalog,
        "catalog_reproducible": None,
    }


def _cosmic_ray_catalog(workspace: Path, python: Path) -> list[tuple[Any, ...]]:
    executable = _tool_executable(python, "cosmic-ray")
    config = _write_cosmic_ray_config(workspace, python)
    session = workspace / "session.sqlite"
    initialized, _ = _run(
        [str(executable), "init", str(config), str(session)], workspace
    )
    if initialized.returncode:
        raise ValueError(f"Cosmic Ray init failed:\n{initialized.stdout}")
    dumped, _ = _run([str(executable), "dump", str(session)], workspace)
    _outcomes, catalog = parse_cosmic_ray_dump(dumped.stdout)
    return catalog


def _result_workspace(base: Path, root: Path, tool: str, run: int) -> Path:
    workspace = root / f"{tool}-{run}"
    shutil.copytree(base, workspace)
    return workspace


def _write_results(
    output_dir: Path, results: list[dict[str, Any]], args: argparse.Namespace
) -> None:
    serializable = []
    for result in results:
        item = dict(result)
        item.pop("catalog")
        serializable.append(item)
    (output_dir / "benchmark.json").write_text(
        json.dumps(
            {
                "sut_ref": args.sut_ref,
                "participant_ref": args.participant_ref,
                "target": "markdown_it/ruler.py",
                "test_file": "tests/task/task.py",
                "operator_policy": "tool_native_defaults",
                "tools": serializable,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path = output_dir / "benchmark.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        for result in serializable:
            writer.writerow(
                {
                    "tool": result["tool"],
                    "version": result["version"],
                    "compatible": result["compatible"],
                    "duration_seconds": f"{result['duration_seconds']:.3f}",
                    "total_mutants": result["total"],
                    "killed": result["killed"],
                    "survived": result["survived"],
                    "incompetent": result["incompetent"],
                    "timeout": result["timeout"],
                    "no_tests": result["no_tests"],
                    "catalog_reproducible": result["catalog_reproducible"],
                }
            )


def benchmark(args: argparse.Namespace) -> list[dict[str, Any]]:
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mutation-tool-benchmark-") as raw_root:
        root = Path(raw_root)
        base = root / "base"
        _prepare_baseline(repo_root, args.sut_ref, args.participant_ref, base)
        tool_runs = (
            ("mutpy", Path(args.mutpy_python), _mutpy_run),
            ("mutmut", Path(args.mutmut_python), _mutmut_run),
            ("cosmic-ray", Path(args.cosmic_ray_python), _cosmic_ray_run),
        )
        results: list[dict[str, Any]] = []
        for tool, python, runner in tool_runs:
            first = runner(_result_workspace(base, root, tool, 1), python, output_dir)
            second_workspace = _result_workspace(base, root, tool, 2)
            if tool == "cosmic-ray":
                second_catalog = _cosmic_ray_catalog(second_workspace, python)
            else:
                second = runner(second_workspace, python, output_dir)
                second_catalog = second["catalog"]
            first["catalog_reproducible"] = first["catalog"] == second_catalog
            results.append(first)
    _write_results(output_dir, results, args)
    return results


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Benchmark MutPy, Mutmut, and Cosmic Ray on one fixed test suite."
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--sut-ref", default="pilot-metric")
    parser.add_argument("--participant-ref", default="origin/experiment-11")
    parser.add_argument("--mutpy-python", type=Path, required=True)
    parser.add_argument("--mutmut-python", type=Path, required=True)
    parser.add_argument("--cosmic-ray-python", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/metric_collection/mutation_pilot"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        results = benchmark(_parser().parse_args(argv))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for result in results:
        print(
            f"{result['tool']}: total={result['total']}, "
            f"compatible={result['compatible']}, "
            f"catalog_reproducible={result['catalog_reproducible']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
