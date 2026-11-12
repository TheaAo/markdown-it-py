"""Calculate Phase 2 generation-efficiency statistics by experiment group."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


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

    for metric in METRICS:
        for group in GROUPS:
            if not values[metric][group]:
                raise ValueError(f"No {metric} values found for {group}")
    return values


def calculate_statistics(path: Path) -> list[dict[str, str | float | int]]:
    """Calculate mean, median, and sample SD."""

    values = _read_values(path)
    rows: list[dict[str, str | float | int]] = []
    for metric in METRICS:
        for group in GROUPS:
            group_values = values[metric][group]
            rows.append(
                {
                    "group": group,
                    "metric": metric,
                    "n": len(group_values),
                    "mean": statistics.mean(group_values),
                    "median": statistics.median(group_values),
                    "sd": statistics.stdev(group_values),
                }
            )
    return rows


def _write_csv(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    """Write efficiency statistics to CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=("group", "metric", "n", "mean", "median", "sd"),
        )
        writer.writeheader()
        writer.writerows(rows)


def _print_table(rows: list[dict[str, str | float | int]]) -> None:
    """Print efficiency statistics as a Markdown table."""

    print("| Group | Metric | n | Mean | Median | SD |")
    print("|---|---|---:|---:|---:|---:|")
    for row in rows:
        print(
            f"| {row['group']} | {row['metric']} | {row['n']} | "
            f"{row['mean']:.9f} | {row['median']:.9f} | {row['sd']:.9f} |"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Calculate Phase 2 generation-efficiency statistics."
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
            / "phase2_generation_efficiency_statistics.csv"
        ),
        help="CSV file to write.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    statistics_rows = calculate_statistics(arguments.input)
    _write_csv(arguments.output, statistics_rows)
    _print_table(statistics_rows)
    print(f"\nCSV written to {arguments.output}")
