"""Calculate Phase 2 coverage statistics for the AI-AI and Manual-AI groups."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

try:
    from .participants import PARTICIPANTS_BY_NUMBER
except ImportError:
    from participants import PARTICIPANTS_BY_NUMBER


GROUPS = ("AI-AI", "Manual-AI")
METRICS = {
    "statement_coverage": "participant_statement_coverage",
    "branch_coverage": "participant_branch_coverage",
}
GROUP_BY_PHASE1_GROUP = {"AI": "AI-AI", "Manual": "Manual-AI"}
EXPECTED_PARTICIPANTS = {
    participant.number
    for participant in PARTICIPANTS_BY_NUMBER.values()
    if participant.participated_in_phase2
}


def _read_values(path: Path) -> dict[str, dict[str, list[float]]]:
    """Read collected Phase 2 coverage values and assign experiment groups."""

    values = {
        metric: {group: [] for group in GROUPS}
        for metric in METRICS
    }
    seen_participants: set[int] = set()
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        required_columns = {"participant_number", "status", *METRICS.values()}
        missing_columns = required_columns - set(reader.fieldnames or ())
        if missing_columns:
            raise ValueError(
                f"{path} is missing required columns: {sorted(missing_columns)}"
            )

        for row in reader:
            participant = int(row["participant_number"])
            metadata = PARTICIPANTS_BY_NUMBER.get(participant)
            if metadata is None or not metadata.participated_in_phase2:
                continue
            if row["status"].strip() != "collected":
                continue
            if participant in seen_participants:
                raise ValueError(f"Duplicate collected participant: {participant}")
            seen_participants.add(participant)
            group = GROUP_BY_PHASE1_GROUP[metadata.phase1_group]
            for metric, column in METRICS.items():
                raw_value = row[column].strip()
                values[metric][group].append(float(raw_value) if raw_value else 0.0)

    missing_participants = EXPECTED_PARTICIPANTS - seen_participants
    if missing_participants:
        raise ValueError(
            "Missing collected Phase 2 participants: "
            f"{sorted(missing_participants)}"
        )
    return values


def calculate_statistics(path: Path) -> list[dict[str, str | float | int]]:
    """Calculate mean, median, and sample SD for each group and metric."""

    metric_values = _read_values(path)
    rows: list[dict[str, str | float | int]] = []
    for metric in METRICS:
        for group in GROUPS:
            group_values = metric_values[metric][group]
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
    """Write coverage statistics in percentage and percentage-point units."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=("group", "metric", "n", "mean_percent", "median_percent", "sd_pp"),
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "group": row["group"],
                    "metric": row["metric"],
                    "n": row["n"],
                    "mean_percent": float(row["mean"]) * 100,
                    "median_percent": float(row["median"]) * 100,
                    "sd_pp": float(row["sd"]) * 100,
                }
            )


def _print_table(rows: list[dict[str, str | float | int]]) -> None:
    """Print coverage statistics as a Markdown table."""

    print("| Group | Metric | n | Mean (%) | Median (%) | SD (pp) |")
    print("|---|---|---:|---:|---:|---:|")
    for row in rows:
        print(
            f"| {row['group']} | {row['metric']} | {row['n']} | "
            f"{float(row['mean']) * 100:.6f} | "
            f"{float(row['median']) * 100:.6f} | "
            f"{float(row['sd']) * 100:.6f} |"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Calculate Phase 2 coverage statistics by experiment group."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=repo_root / "results" / "phase2" / "coverage" / "coverage.csv",
        help="Phase 2 coverage CSV.",
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
            / "phase2_coverage_statistics.csv"
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
