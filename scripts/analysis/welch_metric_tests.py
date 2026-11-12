"""Run Welch's t-tests for Phase 1 and Phase 2 participant metrics."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

from scipy import stats

try:
    from .phase1_metric_statistics import _metric_values
    from .phase2_assertion_score_statistics import _read_scores as read_assertion
    from .phase2_mutation_score_statistics import _read_scores as read_mutation
    from .phase2_coverage_statistics import _read_values as read_coverage
except ImportError:
    from phase1_metric_statistics import _metric_values
    from phase2_assertion_score_statistics import _read_scores as read_assertion
    from phase2_mutation_score_statistics import _read_scores as read_mutation
    from phase2_coverage_statistics import _read_values as read_coverage


METRICS = (
    "statement_coverage",
    "branch_coverage",
    "mutation_score",
    "assertion_score",
)


def _phase2_values(
    coverage_path: Path,
    mutation_path: Path,
    assertion_path: Path,
) -> dict[str, dict[str, list[float]]]:
    """Read Phase 2 metrics grouped as Manual-AI and AI-AI."""

    coverage = read_coverage(coverage_path)
    mutation = read_mutation(mutation_path)
    assertion = read_assertion(assertion_path)
    return {
        "statement_coverage": coverage["statement_coverage"],
        "branch_coverage": coverage["branch_coverage"],
        "mutation_score": mutation,
        "assertion_score": assertion,
    }


def _welch_test(first: list[float], second: list[float]) -> dict[str, float | int]:
    """Calculate a two-sided Welch test and CI for first-minus-second."""

    first_variance = statistics.variance(first)
    second_variance = statistics.variance(second)
    first_mean = statistics.mean(first)
    second_mean = statistics.mean(second)
    difference = first_mean - second_mean
    first_term = first_variance / len(first)
    second_term = second_variance / len(second)
    standard_error = (first_term + second_term) ** 0.5
    degrees_of_freedom = (first_term + second_term) ** 2 / (
        first_term**2 / (len(first) - 1)
        + second_term**2 / (len(second) - 1)
    )
    t_statistic = difference / standard_error if standard_error else 0.0
    p_value = 2 * stats.t.sf(abs(t_statistic), degrees_of_freedom)
    margin_of_error = stats.t.ppf(0.975, degrees_of_freedom) * standard_error
    return {
        "n_first": len(first),
        "n_second": len(second),
        "mean_first": first_mean,
        "mean_second": second_mean,
        "difference_first_minus_second": difference,
        "t": t_statistic,
        "df": degrees_of_freedom,
        "p_value": p_value,
        "ci95_lower": difference - margin_of_error,
        "ci95_upper": difference + margin_of_error,
    }


def calculate_tests(
    phase1_path: Path,
    phase2_coverage_path: Path,
    phase2_mutation_path: Path,
    phase2_assertion_path: Path,
) -> list[dict[str, str | float | int]]:
    """Calculate Welch tests for all requested metrics and phases."""

    phase_values = (
        (
            "Phase 1",
            "Manual",
            "AI",
            _metric_values(phase1_path),
        ),
        (
            "Phase 2",
            "Manual-AI",
            "AI-AI",
            _phase2_values(
                phase2_coverage_path,
                phase2_mutation_path,
                phase2_assertion_path,
            ),
        ),
    )
    rows: list[dict[str, str | float | int]] = []
    for phase, first_group, second_group, values in phase_values:
        for metric in METRICS:
            result = _welch_test(
                values[metric][first_group],
                values[metric][second_group],
            )
            rows.append(
                {
                    "phase": phase,
                    "metric": metric,
                    "first_group": first_group,
                    "second_group": second_group,
                    **result,
                }
            )
    return rows


def _write_csv(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    """Write Welch test results to CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "phase",
        "metric",
        "first_group",
        "second_group",
        "n_first",
        "n_second",
        "mean_first",
        "mean_second",
        "difference_first_minus_second",
        "t",
        "df",
        "p_value",
        "ci95_lower",
        "ci95_upper",
    )
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _print_table(rows: list[dict[str, str | float | int]]) -> None:
    """Print Welch test results as a Markdown table."""

    print(
        "| Phase | Metric | Comparison | n1 | n2 | Mean diff | "
        "t | df | p value | 95% CI |"
    )
    print("|---|---|---|---:|---:|---:|---:|---:|---:|---|")
    for row in rows:
        comparison = f"{row['first_group']} - {row['second_group']}"
        ci = f"[{row['ci95_lower']:.6f}, {row['ci95_upper']:.6f}]"
        print(
            f"| {row['phase']} | {row['metric']} | {comparison} | "
            f"{row['n_first']} | {row['n_second']} | "
            f"{row['difference_first_minus_second']:.6f} | "
            f"{row['t']:.6f} | {row['df']:.6f} | "
            f"{row['p_value']:.6f} | {ci} |"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Run Welch's t-tests for Phase 1 and Phase 2 metrics."
    )
    parser.add_argument(
        "--phase1",
        type=Path,
        default=repo_root / "results" / "phase1" / "summary" / "thesis_metrics.xlsx",
    )
    parser.add_argument(
        "--phase2-coverage",
        type=Path,
        default=repo_root / "results" / "phase2" / "coverage" / "coverage.csv",
    )
    parser.add_argument(
        "--phase2-mutation",
        type=Path,
        default=(
            repo_root
            / "results"
            / "phase2"
            / "mutation_score"
            / "mutation_score.csv"
        ),
    )
    parser.add_argument(
        "--phase2-assertion",
        type=Path,
        default=(
            repo_root
            / "results"
            / "phase2"
            / "assertion_score"
            / "assertion_score.csv"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            repo_root
            / "scripts"
            / "analysis"
            / "outputs"
            / "tables"
            / "welch_metric_tests.csv"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    test_rows = calculate_tests(
        arguments.phase1,
        arguments.phase2_coverage,
        arguments.phase2_mutation,
        arguments.phase2_assertion,
    )
    _write_csv(arguments.output, test_rows)
    _print_table(test_rows)
    print(f"\nCSV written to {arguments.output}")