"""Run Welch's t-tests for Phase 2 generation-efficiency metrics."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

from scipy import stats


GROUPS = ("Manual-AI", "AI-AI")
METRICS = (
    "statement_generation_efficiency_per_second",
    "branch_generation_efficiency_per_second",
    "mutation_generation_efficiency_per_second",
)


def _read_values(path: Path) -> dict[str, dict[str, list[float]]]:
    """Read collected efficiency values grouped by Phase 1 and Phase 2 groups."""

    values = {metric: {group: [] for group in GROUPS} for metric in METRICS}
    seen_participants: set[int] = set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required_columns = {
            "participant_number",
            "phase1_group",
            "phase2_group",
            "efficiency_status",
            *METRICS,
        }
        missing_columns = required_columns - set(reader.fieldnames or ())
        if missing_columns:
            raise ValueError(
                f"{path} is missing required columns: {sorted(missing_columns)}"
            )

        for row in reader:
            if row["efficiency_status"].strip() != "collected":
                continue
            participant = int(row["participant_number"])
            if participant in seen_participants:
                raise ValueError(f"Duplicate collected participant: {participant}")
            seen_participants.add(participant)

            group = f"{row['phase1_group']}-{row['phase2_group']}"
            if group not in GROUPS:
                raise ValueError(
                    f"Unsupported group for participant {participant}: {group}"
                )
            for metric in METRICS:
                raw_value = row[metric].strip()
                if not raw_value:
                    raise ValueError(
                        f"Missing {metric} for participant {participant}"
                    )
                value = float(raw_value)
                if value < 0:
                    raise ValueError(
                        f"{metric} for participant {participant} "
                        f"cannot be negative: {value}"
                    )
                values[metric][group].append(value)

    return values


def _welch_test(first: list[float], second: list[float]) -> dict[str, float | int]:
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
    margin_of_error = stats.t.ppf(0.975, degrees_of_freedom) * standard_error
    return {
        "n_first": len(first),
        "n_second": len(second),
        "mean_first": first_mean,
        "mean_second": second_mean,
        "difference_manual_ai_minus_ai_ai": difference,
        "t": t_statistic,
        "df": degrees_of_freedom,
        "p_value": p_value,
        "ci95_lower": difference - margin_of_error,
        "ci95_upper": difference + margin_of_error,
    }


def calculate_tests(path: Path) -> list[dict[str, str | float | int]]:
    """Calculate Welch tests for all Phase 2 efficiency metrics."""

    values = _read_values(path)
    rows: list[dict[str, str | float | int]] = []
    for metric in METRICS:
        result = _welch_test(
            values[metric]["Manual-AI"],
            values[metric]["AI-AI"],
        )
        rows.append({"metric": metric, **result})
    return rows


def _write_csv(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    """Write Welch test results to CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "metric",
        "n_first",
        "n_second",
        "mean_first",
        "mean_second",
        "difference_manual_ai_minus_ai_ai",
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
        "| Metric | n Manual-AI | n AI-AI | Mean diff | "
        "t | df | p value | 95% CI |"
    )
    print("|---|---:|---:|---:|---:|---:|---:|---|")
    for row in rows:
        ci = f"[{row['ci95_lower']:.9f}, {row['ci95_upper']:.9f}]"
        print(
            f"| {row['metric']} | {row['n_first']} | {row['n_second']} | "
            f"{row['difference_manual_ai_minus_ai_ai']:.9f} | "
            f"{row['t']:.6f} | {row['df']:.6f} | "
            f"{row['p_value']:.6f} | {ci} |"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Run Welch's t-tests for Phase 2 efficiency metrics."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            repo_root
            / "results"
            / "phase2"
            / "efficiency"
            / "generation_efficiency.csv"
        ),
        help="Phase 2 generation-efficiency CSV.",
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
            / "welch_phase2_generation_efficiency_tests.csv"
        ),
        help="CSV file to write.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    test_rows = calculate_tests(arguments.input)
    _write_csv(arguments.output, test_rows)
    _print_table(test_rows)
    print(f"\nCSV written to {arguments.output}")
