"""Calculate Phase 1 execution-efficiency statistics by group."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

try:
    from .participants import PARTICIPANTS_BY_NUMBER
except ImportError:
    from participants import PARTICIPANTS_BY_NUMBER


GROUPS = ("Manual", "AI")
METRICS = {
    "statement_execution_efficiency_per_ms": "statement_execution_efficiency_per_second",
    "branch_execution_efficiency_per_ms": "branch_execution_efficiency_per_second",
    "mutation_execution_efficiency_per_ms": "mutation_execution_efficiency_per_second",
}


def read_values(path: Path) -> dict[str, dict[str, list[float]]]:
    """Read valid execution-efficiency values grouped by Phase 1 assignment."""

    values = {
        metric: {group: [] for group in GROUPS}
        for metric in METRICS
    }
    seen_participants: set[int] = set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required_columns = {
            "participant_number",
            "status",
            "execution_metric_status",
            *METRICS.values(),
        }
        missing_columns = required_columns - set(reader.fieldnames or ())
        if missing_columns:
            raise ValueError(
                f"{path} is missing required columns: {sorted(missing_columns)}"
            )

        for row in reader:
            if (
                row["status"].strip() != "collected"
                or row["execution_metric_status"].strip() != "collected"
            ):
                continue
            participant = int(row["participant_number"])
            metadata = PARTICIPANTS_BY_NUMBER.get(participant)
            if metadata is None:
                continue
            if participant in seen_participants:
                raise ValueError(f"Duplicate valid participant: {participant}")
            seen_participants.add(participant)

            for metric, column in METRICS.items():
                raw_value = row[column].strip()
                if not raw_value:
                    raise ValueError(
                        f"Missing {column} for valid participant {participant}"
                    )
                values[metric][metadata.phase1_group].append(float(raw_value) / 1000)

    for metric in METRICS:
        for group in GROUPS:
            if len(values[metric][group]) < 2:
                raise ValueError(f"Not enough {metric} values found for {group}")
    return values


def calculate_statistics(path: Path) -> list[dict[str, str | float | int]]:
    """Calculate mean, median, and sample SD."""

    values = read_values(path)
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


def write_csv(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    """Write execution-efficiency statistics to CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=("group", "metric", "n", "mean", "median", "sd"),
        )
        writer.writeheader()
        writer.writerows(rows)


def print_table(rows: list[dict[str, str | float | int]]) -> None:
    """Print execution-efficiency statistics as a Markdown table."""

    print("| Group | Metric | n | Mean | Median | SD |")
    print("|---|---|---:|---:|---:|---:|")
    for row in rows:
        print(
            f"| {row['group']} | {row['metric']} | {row['n']} | "
            f"{row['mean']:.6f} | {row['median']:.6f} | {row['sd']:.6f} |"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Calculate Phase 1 execution-efficiency statistics by group."
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
        / "execution_efficiency_statistics.csv",
        help="CSV file to write.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    statistics_rows = calculate_statistics(arguments.input)
    write_csv(arguments.output, statistics_rows)
    print_table(statistics_rows)
    print(f"\nCSV written to {arguments.output}")
