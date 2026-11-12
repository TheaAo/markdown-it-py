"""Calculate Phase 2 execution-efficiency statistics by group."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

try:
    from .participants import PARTICIPANTS_BY_NUMBER
except ImportError:
    from participants import PARTICIPANTS_BY_NUMBER


GROUPS = ("Manual-AI", "AI-AI")
METRICS = {
    "statement_execution_efficiency": "statement_execution_efficiency_per_second",
    "branch_execution_efficiency": "branch_execution_efficiency_per_second",
    "mutation_execution_efficiency": "mutation_execution_efficiency_per_second",
}


def _read_values(path: Path) -> dict[str, dict[str, list[float]]]:
    """Read valid Phase 2 execution-efficiency values as percent per ms."""

    values = {
        metric: {group: [] for group in GROUPS}
        for metric in METRICS
    }
    seen_participants: set[int] = set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required_columns = {
            "participant_number",
            "phase1_group",
            "phase2_group",
            "efficiency_status",
            *METRICS.values(),
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
            metadata = PARTICIPANTS_BY_NUMBER.get(participant)
            if metadata is None or not metadata.participated_in_phase2:
                continue
            group = f"{row['phase1_group'].strip()}-{row['phase2_group'].strip()}"
            if group not in GROUPS:
                raise ValueError(f"Unexpected Phase 2 group: {group}")
            if participant in seen_participants:
                raise ValueError(f"Duplicate valid participant: {participant}")
            seen_participants.add(participant)

            if row["phase1_group"].strip() != metadata.phase1_group:
                raise ValueError(f"Phase 1 group mismatch for participant {participant}")

            for metric, column in METRICS.items():
                raw_value = row[column].strip()
                if not raw_value:
                    raise ValueError(
                        f"Missing {column} for valid participant {participant}"
                    )
                # The source is a fraction per second; convert to percent per ms.
                values[metric][group].append(float(raw_value) / 10)

    for metric in METRICS:
        for group in GROUPS:
            if len(values[metric][group]) < 2:
                raise ValueError(f"Not enough {metric} values found for {group}")
    return values


def calculate_statistics(path: Path) -> list[dict[str, str | float | int]]:
    """Calculate mean, median, and sample SD in percent per ms."""

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
                    "mean_percent_per_ms": statistics.mean(group_values),
                    "median_percent_per_ms": statistics.median(group_values),
                    "sd_percent_per_ms": statistics.stdev(group_values),
                }
            )
    return rows


def _write_csv(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    """Write execution-efficiency statistics to CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=(
                "group",
                "metric",
                "n",
                "mean_percent_per_ms",
                "median_percent_per_ms",
                "sd_percent_per_ms",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)


def _print_table(rows: list[dict[str, str | float | int]]) -> None:
    """Print execution-efficiency statistics as a Markdown table."""

    print("| Group | Metric | n | Mean (%/ms) | Median (%/ms) | SD (%/ms) |")
    print("|---|---|---:|---:|---:|---:|")
    for row in rows:
        print(
            f"| {row['group']} | {row['metric']} | {row['n']} | "
            f"{row['mean_percent_per_ms']:.6f} | "
            f"{row['median_percent_per_ms']:.6f} | "
            f"{row['sd_percent_per_ms']:.6f} |"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Calculate Phase 2 execution-efficiency statistics."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=repo_root / "results" / "phase2" / "efficiency"
        / "execution_efficiency.csv",
        help="Phase 2 execution-efficiency CSV.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repo_root / "scripts" / "analysis" / "outputs" / "tables"
        / "phase2_execution_efficiency_statistics.csv",
        help="CSV file to write.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    statistics_rows = calculate_statistics(arguments.input)
    _write_csv(arguments.output, statistics_rows)
    _print_table(statistics_rows)
    print(f"\nCSV written to {arguments.output}")
