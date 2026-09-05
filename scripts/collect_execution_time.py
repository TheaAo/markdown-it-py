from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Literal

try:
    from scripts.collect_coverage import _isolated_valid_nodeids
    from scripts.collect_error_rates import collect_error_rates
except ModuleNotFoundError:  # pragma: no cover - used when run as a script
    from collect_coverage import _isolated_valid_nodeids  # type: ignore[no-redef]
    from collect_error_rates import collect_error_rates  # type: ignore[no-redef]


Status = Literal[
    "collected",
    "no_valid_tests",
    "baseline_failed",
    "measurement_failed",
    "measurement_timeout",
]


@dataclass(frozen=True)
class TimedRun:
    phase: Literal["baseline", "warmup", "measurement"]
    index: int
    elapsed_nanoseconds: int
    returncode: int
    timed_out: bool
    failure_output: str | None

    @property
    def elapsed_seconds(self) -> float:
        return self.elapsed_nanoseconds / 1_000_000_000


@dataclass(frozen=True)
class ExecutionTimeSummary:
    execution_time_seconds: float
    measurement_count: int
    mean_seconds: float
    standard_deviation_seconds: float
    minimum_seconds: float
    maximum_seconds: float
    first_quartile_seconds: float
    third_quartile_seconds: float
    interquartile_range_seconds: float
    median_absolute_deviation_seconds: float
    coefficient_of_variation: float | None


@dataclass(frozen=True)
class ExecutionTimeReport:
    test_path: str
    status: Status
    valid_tests_included: int
    invalid_tests_excluded: int
    warmup_count: int
    requested_measurement_count: int
    timeout_seconds: float
    summary: ExecutionTimeSummary | None
    warmups: list[TimedRun]
    measurements: list[TimedRun]
    reason: str | None = None


def _controlled_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("PYTEST_ADDOPTS", None)
    environment["PYTHONHASHSEED"] = "0"
    return environment


def _timed_pytest(
    *,
    python_executable: str,
    repo_root: Path,
    nodeids: list[str],
    timeout: float,
    phase: Literal["baseline", "warmup", "measurement"],
    index: int,
) -> TimedRun:
    command = [
        python_executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        *nodeids,
    ]
    start = time.perf_counter_ns()
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            env=_controlled_environment(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter_ns() - start
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        return TimedRun(
            phase=phase,
            index=index,
            elapsed_nanoseconds=elapsed,
            returncode=124,
            timed_out=True,
            failure_output=output[-4000:] or None,
        )
    elapsed = time.perf_counter_ns() - start
    return TimedRun(
        phase=phase,
        index=index,
        elapsed_nanoseconds=elapsed,
        returncode=completed.returncode,
        timed_out=False,
        failure_output=completed.stdout[-4000:] if completed.returncode else None,
    )


def _summarize(measurements: list[TimedRun]) -> ExecutionTimeSummary:
    values = [run.elapsed_seconds for run in measurements]
    median = statistics.median(values)
    mean = statistics.fmean(values)
    standard_deviation = statistics.stdev(values) if len(values) > 1 else 0.0
    if len(values) > 1:
        first_quartile, _second_quartile, third_quartile = statistics.quantiles(
            values, n=4, method="inclusive"
        )
    else:
        first_quartile = third_quartile = values[0]
    absolute_deviations = [abs(value - median) for value in values]
    return ExecutionTimeSummary(
        execution_time_seconds=median,
        measurement_count=len(values),
        mean_seconds=mean,
        standard_deviation_seconds=standard_deviation,
        minimum_seconds=min(values),
        maximum_seconds=max(values),
        first_quartile_seconds=first_quartile,
        third_quartile_seconds=third_quartile,
        interquartile_range_seconds=third_quartile - first_quartile,
        median_absolute_deviation_seconds=statistics.median(absolute_deviations),
        coefficient_of_variation=(standard_deviation / mean if mean else None),
    )


def collect_execution_time(
    *,
    test_path: Path,
    repo_root: Path,
    python_executable: str,
    timeout: float,
    warmup_count: int,
    measurement_count: int,
) -> ExecutionTimeReport:
    if warmup_count < 0:
        raise ValueError("warmup_count must be non-negative")
    if measurement_count < 1:
        raise ValueError("measurement_count must be positive")
    if timeout <= 0:
        raise ValueError("timeout must be positive")

    test_path = test_path.resolve()
    repo_root = repo_root.resolve()
    error_report = collect_error_rates(
        test_path=test_path,
        repo_root=repo_root,
        python_executable=python_executable,
        timeout=timeout,
    )
    all_results = error_report.case_level.test_cases
    valid_results = [item for item in all_results if item.classification == "valid"]
    invalid_count = len(all_results) - len(valid_results)
    if not valid_results:
        return ExecutionTimeReport(
            test_path=str(test_path),
            status="no_valid_tests",
            valid_tests_included=0,
            invalid_tests_excluded=invalid_count,
            warmup_count=warmup_count,
            requested_measurement_count=measurement_count,
            timeout_seconds=timeout,
            summary=None,
            warmups=[],
            measurements=[],
            reason="No test cases passed on the original SUT.",
        )

    with tempfile.TemporaryDirectory(prefix="execution-time-valid-tests-") as temp_dir:
        nodeids = _isolated_valid_nodeids(
            test_path=test_path,
            repo_root=repo_root,
            temp_root=Path(temp_dir),
            valid_results=valid_results,
        )
        baseline = _timed_pytest(
            python_executable=python_executable,
            repo_root=repo_root,
            nodeids=nodeids,
            timeout=timeout,
            phase="baseline",
            index=1,
        )
        if baseline.returncode != 0:
            status: Status = (
                "measurement_timeout" if baseline.timed_out else "baseline_failed"
            )
            return ExecutionTimeReport(
                test_path=str(test_path),
                status=status,
                valid_tests_included=len(valid_results),
                invalid_tests_excluded=invalid_count,
                warmup_count=warmup_count,
                requested_measurement_count=measurement_count,
                timeout_seconds=timeout,
                summary=None,
                warmups=[],
                measurements=[],
                reason=(
                    baseline.failure_output or "Valid-only baseline execution failed."
                ),
            )

        warmups: list[TimedRun] = []
        for index in range(1, warmup_count + 1):
            run = _timed_pytest(
                python_executable=python_executable,
                repo_root=repo_root,
                nodeids=nodeids,
                timeout=timeout,
                phase="warmup",
                index=index,
            )
            warmups.append(run)
            if run.returncode != 0:
                status = (
                    "measurement_timeout" if run.timed_out else "measurement_failed"
                )
                return ExecutionTimeReport(
                    test_path=str(test_path),
                    status=status,
                    valid_tests_included=len(valid_results),
                    invalid_tests_excluded=invalid_count,
                    warmup_count=warmup_count,
                    requested_measurement_count=measurement_count,
                    timeout_seconds=timeout,
                    summary=None,
                    warmups=warmups,
                    measurements=[],
                    reason=run.failure_output or "Warm-up execution failed.",
                )

        measurements: list[TimedRun] = []
        for index in range(1, measurement_count + 1):
            run = _timed_pytest(
                python_executable=python_executable,
                repo_root=repo_root,
                nodeids=nodeids,
                timeout=timeout,
                phase="measurement",
                index=index,
            )
            measurements.append(run)
            if run.returncode != 0:
                status = (
                    "measurement_timeout" if run.timed_out else "measurement_failed"
                )
                return ExecutionTimeReport(
                    test_path=str(test_path),
                    status=status,
                    valid_tests_included=len(valid_results),
                    invalid_tests_excluded=invalid_count,
                    warmup_count=warmup_count,
                    requested_measurement_count=measurement_count,
                    timeout_seconds=timeout,
                    summary=None,
                    warmups=warmups,
                    measurements=measurements,
                    reason=run.failure_output or "Measured execution failed.",
                )

    return ExecutionTimeReport(
        test_path=str(test_path),
        status="collected",
        valid_tests_included=len(valid_results),
        invalid_tests_excluded=invalid_count,
        warmup_count=warmup_count,
        requested_measurement_count=measurement_count,
        timeout_seconds=timeout,
        summary=_summarize(measurements),
        warmups=warmups,
        measurements=measurements,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure wall-clock execution time for valid participant tests."
    )
    parser.add_argument("test_file", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--measurements", type=int, default=15)
    args = parser.parse_args(argv)

    report = collect_execution_time(
        test_path=args.test_file,
        repo_root=args.repo_root,
        python_executable=args.python,
        timeout=args.timeout,
        warmup_count=args.warmups,
        measurement_count=args.measurements,
    )
    json.dump(asdict(report), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if report.status in {"collected", "no_valid_tests"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
