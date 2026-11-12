"""Run Brown-Forsythe variance tests for Phase 1 and Phase 2 metrics."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from scipy import stats

try:
    from .phase1_metric_statistics import _metric_values
    from .phase2_assertion_score_statistics import _read_scores as read_assertion
    from .phase2_coverage_statistics import _read_values as read_coverage
    from .phase2_mutation_score_statistics import _read_scores as read_mutation
except ImportError:
    from phase1_metric_statistics import _metric_values
    from phase2_assertion_score_statistics import _read_scores as read_assertion
    from phase2_coverage_statistics import _read_values as read_coverage
    from phase2_mutation_score_statistics import _read_scores as read_mutation


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
    return {
        "statement_coverage": coverage["statement_coverage"],
        "branch_coverage": coverage["branch_coverage"],
        "mutation_score": read_mutation(mutation_path),
        "assertion_score": read_assertion(assertion_path),
    }


def calculate_tests(
    phase1_path: Path,
    phase2_coverage_path: Path,
    phase2_mutation_path: Path,
    phase2_assertion_path: Path,
) -> list[dict[str, str | float | int]]:
    """Calculate two-sided Brown-Forsythe tests for all metrics and phases."""

    phase_values = (
        ("Phase 1", "Manual", "AI", _metric_values(phase1_path)),
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
            first = values[metric][first_group]
            second = values[metric][second_group]
            result = stats.levene(first, second, center="median")
            rows.append(
                {
                    "phase": phase,
                    "metric": metric,
                    "first_group": first_group,
                    "second_group": second_group,
                    "n_first": len(first),
                    "n_second": len(second),
                    "statistic": result.statistic,
                    "df1": 1,
                    "df2": len(first) + len(second) - 2,
                    "p_value": result.pvalue,
                }
            )
    return rows


def _write_csv(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    """Write Brown-Forsythe test results to CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "phase",
        "metric",
        "first_group",
        "second_group",
        "n_first",
        "n_second",
        "statistic",
        "df1",
        "df2",
        "p_value",
    )
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _print_table(rows: list[dict[str, str | float | int]]) -> None:
    """Print Brown-Forsythe test results as a Markdown table."""

    print(
        "| Phase | Metric | Comparison | n1 | n2 | W | df1 | df2 | p value |"
    )
    print("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        comparison = f"{row['first_group']} vs {row['second_group']}"
        print(
            f"| {row['phase']} | {row['metric']} | {comparison} | "
            f"{row['n_first']} | {row['n_second']} | "
            f"{row['statistic']:.6f} | {row['df1']} | {row['df2']} | "
            f"{row['p_value']:.6f} |"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Run Brown-Forsythe tests for Phase 1 and Phase 2 metrics."
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
            / "brown_forsythe_tests.csv"
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
