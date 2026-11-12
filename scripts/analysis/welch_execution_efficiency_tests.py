"""Run Welch's t-tests for Phase 1 execution-efficiency metrics."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

from scipy import stats

try:
    from .execution_efficiency_statistics import METRICS, read_values
except ImportError:
    from execution_efficiency_statistics import METRICS, read_values


def welch_test(first: list[float], second: list[float]) -> dict[str, float | int]:
    """Calculate a two-sided Welch test and CI for first-minus-second."""

    first_mean = statistics.mean(first)
    second_mean = statistics.mean(second)
    first_variance = statistics.variance(first)
    second_variance = statistics.variance(second)
    first_term = first_variance / len(first)
    second_term = second_variance / len(second)
    standard_error = (first_term + second_term) ** 0.5
    degrees_of_freedom = (first_term + second_term) ** 2 / (
        first_term**2 / (len(first) - 1)
        + second_term**2 / (len(second) - 1)
    )
    difference = first_mean - second_mean
    t_statistic = difference / standard_error if standard_error else 0.0
    p_value = 2 * stats.t.sf(abs(t_statistic), degrees_of_freedom)
    margin_of_error = (
        stats.t.ppf(0.975, degrees_of_freedom) * standard_error
    )
    return {
        "n_manual": len(first),
        "n_ai": len(second),
        "mean_manual": first_mean,
        "mean_ai": second_mean,
        "difference_manual_minus_ai": difference,
        "t": t_statistic,
        "df": degrees_of_freedom,
        "p_value": p_value,
        "ci95_lower": difference - margin_of_error,
        "ci95_upper": difference + margin_of_error,
    }


def calculate_tests(path: Path) -> list[dict[str, str | float | int]]:
    """Calculate Welch tests for all execution-efficiency metrics."""

    values = read_values(path)
    rows: list[dict[str, str | float | int]] = []
    for metric in METRICS:
        result = welch_test(values[metric]["Manual"], values[metric]["AI"])
        rows.append({"metric": metric, **result})
    return rows


def write_csv(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    """Write Welch test results to CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "metric",
        "n_manual",
        "n_ai",
        "mean_manual",
        "mean_ai",
        "difference_manual_minus_ai",
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


def print_table(rows: list[dict[str, str | float | int]]) -> None:
    """Print Welch test results as a Markdown table."""

    print(
        "| Metric | n Manual | n AI | Mean diff (Manual-AI) | "
        "t | df | p value | 95% CI |"
    )
    print("|---|---:|---:|---:|---:|---:|---:|---|")
    for row in rows:
        ci = f"[{row['ci95_lower']:.6f}, {row['ci95_upper']:.6f}]"
        print(
            f"| {row['metric']} | {row['n_manual']} | {row['n_ai']} | "
            f"{row['difference_manual_minus_ai']:.6f} | "
            f"{row['t']:.6f} | {row['df']:.6f} | "
            f"{row['p_value']:.6f} | {ci} |"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Run Welch's t-tests for execution-efficiency metrics."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=repo_root / "results" / "phase1" / "execution_time"
        / "execution_efficiency.csv",
        help="Phase 1 execution-efficiency CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repo_root / "scripts" / "analysis" / "outputs" / "tables"
        / "welch_execution_efficiency_tests.csv",
        help="CSV file to write.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    test_rows = calculate_tests(arguments.input)
    write_csv(arguments.output, test_rows)
    print_table(test_rows)
    print(f"\nCSV written to {arguments.output}")
