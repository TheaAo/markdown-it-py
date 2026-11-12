"""Calculate Phase 2 generation-time statistics by experiment group."""

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
TIME_COLUMN = "generation_time_seconds"
GROUP_BY_PHASE1_GROUP = {"AI": "AI-AI", "Manual": "Manual-AI"}
EXPECTED_PARTICIPANTS = {
    participant.number
    for participant in PARTICIPANTS_BY_NUMBER.values()
    if participant.participated_in_phase2
}


def _read_times(path: Path) -> dict[str, list[float]]:
    """Read collected generation times in seconds and assign experiment groups."""

    times = {group: [] for group in GROUPS}
    seen_participants: set[int] = set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required_columns = {"participant_number", "status", TIME_COLUMN}
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

            raw_time = row[TIME_COLUMN].strip()
            if not raw_time:
                raise ValueError(
                    f"Missing generation time for participant {participant}"
                )
            generation_time = float(raw_time)
            if generation_time < 0:
                raise ValueError(
                    f"Generation time for participant {participant} "
                    f"cannot be negative: {generation_time}"
                )
            group = GROUP_BY_PHASE1_GROUP[metadata.phase1_group]
            times[group].append(generation_time)

    missing_participants = EXPECTED_PARTICIPANTS - seen_participants
    if missing_participants:
        raise ValueError(
            "Missing collected Phase 2 participants: "
            f"{sorted(missing_participants)}"
        )
    return times


def calculate_statistics(path: Path) -> list[dict[str, str | float | int]]:
    """Calculate mean, median, and sample SD in seconds."""

    times = _read_times(path)
    return [
        {
            "group": group,
            "n": len(group_times),
            "mean": statistics.mean(group_times),
            "median": statistics.median(group_times),
            "sd": statistics.stdev(group_times),
        }
        for group in GROUPS
        for group_times in [times[group]]
    ]


def _write_csv(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    """Write generation-time statistics in seconds."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=("group", "n", "mean_seconds", "median_seconds", "sd_seconds"),
        )
        writer.writeheader()
        writer.writerows(
            {
                "group": row["group"],
                "n": row["n"],
                "mean_seconds": row["mean"],
                "median_seconds": row["median"],
                "sd_seconds": row["sd"],
            }
            for row in rows
        )


def _print_table(rows: list[dict[str, str | float | int]]) -> None:
    """Print generation-time statistics as a Markdown table."""

    print("| Group | n | Mean (s) | Median (s) | SD (s) |")
    print("|---|---:|---:|---:|---:|")
    for row in rows:
        print(
            f"| {row['group']} | {row['n']} | "
            f"{row['mean']:.6f} | {row['median']:.6f} | {row['sd']:.6f} |"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Calculate Phase 2 generation-time statistics by group."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            repo_root
            / "results"
            / "phase2"
            / "generation_time"
            / "generation_time.csv"
        ),
        help="Phase 2 generation-time CSV.",
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
            / "phase2_generation_time_statistics.csv"
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
