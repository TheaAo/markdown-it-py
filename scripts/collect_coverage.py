from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    from scripts.collect_error_rates import (
        _copy_materials,
        _ensure_pytest_available,
        _split_test_file,
        _write_batch_test_files,
        ErrorRateReport,
        TestCaseResult,
        collect_error_rates,
    )
except ModuleNotFoundError:  # pragma: no cover - used when run as a script
    from collect_error_rates import (  # type: ignore[no-redef]
        _copy_materials,
        _ensure_pytest_available,
        _split_test_file,
        _write_batch_test_files,
        ErrorRateReport,
        TestCaseResult,
        collect_error_rates,
    )


@dataclass(frozen=True)
class CoverageMetric:
    covered: int
    total: int
    percent: float


@dataclass(frozen=True)
class CoverageScope:
    statement: CoverageMetric
    branch: CoverageMetric


@dataclass(frozen=True)
class CoverageReport:
    test_path: str
    source: str
    valid_tests_included: int
    invalid_tests_excluded: int
    participant_tests_only: CoverageScope | None
    all_tests_combined: CoverageScope
    error_rates: ErrorRateReport | None = None


def _run(
    command: list[str], cwd: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        output += f"\nCommand timed out after {timeout} seconds."
        return subprocess.CompletedProcess(command, 124, output)


def _ensure_coverage_available(python_executable: str, repo_root: Path) -> None:
    completed = _run(
        [python_executable, "-m", "coverage", "--version"],
        cwd=repo_root,
        timeout=10,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"coverage.py is not available for {python_executable!r}; "
            "pass --python pointing to the experiment environment."
        )


def _metric(covered: int, total: int) -> CoverageMetric:
    percent = (covered / total * 100) if total else 100.0
    return CoverageMetric(covered=covered, total=total, percent=percent)


def _metrics_from_coverage_json(
    coverage_json: dict[str, object],
) -> tuple[CoverageMetric, CoverageMetric]:
    totals = coverage_json["totals"]
    if not isinstance(totals, dict):
        raise ValueError(
            "coverage JSON does not contain an object-valued 'totals' field"
        )

    statement = _metric(
        covered=int(totals["covered_lines"]),
        total=int(totals["num_statements"]),
    )
    branch = _metric(
        covered=int(totals["covered_branches"]),
        total=int(totals["num_branches"]),
    )
    return statement, branch


def _isolated_valid_nodeids(
    test_path: Path,
    repo_root: Path,
    temp_root: Path,
    valid_results: list[TestCaseResult],
) -> list[str]:
    support_source, test_blocks = _split_test_file(test_path)
    _syntax_results, files_to_blocks = _write_batch_test_files(
        test_blocks=test_blocks,
        support_source=support_source,
        original_test_path=test_path,
        repo_root=repo_root,
        temp_root=temp_root,
    )
    _copy_materials(test_path, temp_root)

    paths_by_test_name = {
        block.name: temp_root / filename
        for filename, block in files_to_blocks.items()
    }
    nodeids: list[str] = []
    for result in valid_results:
        isolated_path = paths_by_test_name.get(result.source_test)
        if isolated_path is None:
            raise RuntimeError(
                f"could not map valid test {result.nodeid!r} to an isolated test file"
            )
        node_suffix = result.nodeid.split("::", 1)[1]
        nodeids.append(f"{isolated_path}::{node_suffix}")
    return nodeids


def _run_coverage(
    pytest_arguments: list[str],
    repo_root: Path,
    python_executable: str,
    source: str,
    timeout: float,
    data_path: Path,
    json_path: Path,
    scope_name: str,
) -> CoverageScope:
    run_result = _run(
        [
            python_executable,
            "-m",
            "coverage",
            "run",
            "--branch",
            f"--source={source}",
            f"--data-file={data_path}",
            "-m",
            "pytest",
            "-q",
            *pytest_arguments,
        ],
        cwd=repo_root,
        timeout=timeout,
    )
    if run_result.returncode != 0:
        raise RuntimeError(
            f"coverage execution failed for {scope_name}:\n{run_result.stdout}"
        )

    json_result = _run(
        [
            python_executable,
            "-m",
            "coverage",
            "json",
            f"--data-file={data_path}",
            "-o",
            str(json_path),
        ],
        cwd=repo_root,
        timeout=timeout,
    )
    if json_result.returncode != 0 or not json_path.exists():
        raise RuntimeError(
            f"coverage JSON generation failed for {scope_name}:\n"
            f"{json_result.stdout}"
        )

    coverage_json = json.loads(json_path.read_text(encoding="utf-8"))
    statement, branch = _metrics_from_coverage_json(coverage_json)
    return CoverageScope(statement=statement, branch=branch)


def collect_coverage(
    test_path: Path,
    repo_root: Path,
    python_executable: str,
    source: str,
    project_tests_path: Path,
    timeout: float,
) -> CoverageReport:
    test_path = test_path.resolve()
    repo_root = repo_root.resolve()
    if not project_tests_path.is_absolute():
        project_tests_path = repo_root / project_tests_path
    project_tests_path = project_tests_path.resolve()
    if not project_tests_path.is_dir():
        raise ValueError(f"project tests directory not found: {project_tests_path}")

    error_report = collect_error_rates(
        test_path=test_path,
        repo_root=repo_root,
        python_executable=python_executable,
        timeout=timeout,
    )
    all_results = error_report.case_level.test_cases
    valid_results = [item for item in all_results if item.classification == "valid"]
    invalid_count = len(all_results) - len(valid_results)

    with tempfile.TemporaryDirectory(prefix="coverage-valid-tests-") as temp_dir:
        temp_root = Path(temp_dir)
        nodeids: list[str] = []
        participant_tests_only = None
        if valid_results:
            nodeids = _isolated_valid_nodeids(
                test_path=test_path,
                repo_root=repo_root,
                temp_root=temp_root,
                valid_results=valid_results,
            )
            participant_tests_only = _run_coverage(
                pytest_arguments=nodeids,
                repo_root=repo_root,
                python_executable=python_executable,
                source=source,
                timeout=timeout,
                data_path=temp_root / ".coverage-participant",
                json_path=temp_root / "coverage-participant.json",
                scope_name="participant tests only",
            )

        try:
            ignored_test_path = test_path.relative_to(repo_root)
        except ValueError:
            ignored_test_path = test_path
        all_tests_combined = _run_coverage(
            pytest_arguments=[
                f"--ignore={ignored_test_path}",
                str(project_tests_path),
                *nodeids,
            ],
            repo_root=repo_root,
            python_executable=python_executable,
            source=source,
            timeout=timeout,
            data_path=temp_root / ".coverage-all-tests",
            json_path=temp_root / "coverage-all-tests.json",
            scope_name="all project tests combined with valid participant tests",
        )

    return CoverageReport(
        test_path=str(test_path),
        source=source,
        valid_tests_included=len(valid_results),
        invalid_tests_excluded=invalid_count,
        participant_tests_only=participant_tests_only,
        all_tests_combined=all_tests_combined,
        error_rates=error_report,
    )


def _report_payload(report: CoverageReport) -> dict[str, Any]:
    payload = asdict(report)
    error_rates = payload.pop("error_rates")
    return {"error_rates": error_rates, "coverage": payload}


def _print_scope(name: str, scope: CoverageScope) -> None:
    print(f"\n{name}")
    print(
        "  Statement coverage: "
        f"{scope.statement.percent:.2f}% "
        f"({scope.statement.covered}/{scope.statement.total})"
    )
    print(
        "  Branch coverage: "
        f"{scope.branch.percent:.2f}% "
        f"({scope.branch.covered}/{scope.branch.total})"
    )


def _print_report(report: CoverageReport) -> None:
    print(f"Test file: {report.test_path}")
    print(f"Measured source: {report.source}")
    print(f"Valid tests included: {report.valid_tests_included}")
    print(f"Invalid tests excluded: {report.invalid_tests_excluded}")
    if report.participant_tests_only is None:
        print("\nParticipant tests only")
        print("  Statement coverage: unavailable (no valid participant tests)")
        print("  Branch coverage: unavailable (no valid participant tests)")
    else:
        _print_scope("Participant tests only", report.participant_tests_only)
    _print_scope("All tests combined", report.all_tests_combined)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare statement and branch coverage from valid participant tests "
            "with coverage from all project tests combined."
        )
    )
    parser.add_argument(
        "test_path", type=Path, help="Path to the participant test file."
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root used as the pytest working directory.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable with pytest, coverage.py, and project dependencies.",
    )
    parser.add_argument(
        "--source",
        default="markdown_it",
        help="Package or source directory to measure (default: markdown_it).",
    )
    parser.add_argument(
        "--project-tests",
        type=Path,
        default=Path("tests"),
        help=(
            "Project test directory to include in the combined result "
            "(default: tests)."
        ),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Timeout in seconds for classification and coverage commands.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (default: text).",
    )
    args = parser.parse_args(argv)

    try:
        _ensure_pytest_available(args.python, args.repo_root.resolve())
        _ensure_coverage_available(args.python, args.repo_root.resolve())
        report = collect_coverage(
            test_path=args.test_path,
            repo_root=args.repo_root,
            python_executable=args.python,
            source=args.source,
            project_tests_path=args.project_tests,
            timeout=args.timeout,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(_report_payload(report), ensure_ascii=False, indent=2))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
