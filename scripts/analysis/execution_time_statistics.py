"""Calculate execution-time statistics for Phase 1 and Phase 2 groups."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path

try:
    from .participants import PARTICIPANTS_BY_NUMBER
except ImportError:
    from participants import PARTICIPANTS_BY_NUMBER


TIME_COLUMN = "execution_time_seconds"
PHASE1_GROUPS = ("Manual", "AI")
PHASE2_GROUPS = ("Manual-AI", "AI-AI")


def _read_times(
    path: Path,
    phase: str,
) -> dict[str, list[float]]:
    """Read non-empty collected execution times grouped by experiment phase."""

    groups = PHASE1_GROUPS if phase == "Phase 1" else PHASE2_GROUPS
    times = {group: [] for group in groups}
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
            if row["status"].strip() != "collected":
                continue
            participant = int(row["participant_number"])
            metadata = PARTICIPANTS_BY_NUMBER.get(participant)
            if metadata is None:
                continue
            if phase == "Phase 2" and not metadata.participated_in_phase2:
                continue
            raw_value = row[TIME_COLUMN].strip()
            if not raw_value:
                continue
            if participant in seen_participants:
                raise ValueError(f"Duplicate execution-time participant: {participant}")
            seen_participants.add(participant)

            value = float(raw_value)
            if value < 0:
                raise ValueError(
                    f"Execution time for participant {participant} "
                    f"cannot be negative: {value}"
                )
            group = (
                metadata.phase1_group
                if phase == "Phase 1"
                else (
                    "AI-AI"
                    if metadata.phase1_group == "AI"
                    else "Manual-AI"
                )
            )
            times[group].append(value)

    for group in groups:
        if not times[group]:
            raise ValueError(f"No execution-time values found for {phase} {group}")
    return times


def calculate_statistics(
    phase1_path: Path,
    phase2_path: Path,
) -> list[dict[str, str | float | int]]:
    """Calculate mean, median, and sample SD in seconds."""

    phase_inputs = (
        ("Phase 1", phase1_path),
        ("Phase 2", phase2_path),
    )
    rows: list[dict[str, str | float | int]] = []
    for phase, path in phase_inputs:
        times = _read_times(path, phase)
        for group, group_times in times.items():
            rows.append(
                {
                    "phase": phase,
                    "group": group,
                    "n": len(group_times),
                    "mean_seconds": statistics.mean(group_times),
                    "median_seconds": statistics.median(group_times),
                    "sd_seconds": statistics.stdev(group_times),
                }
            )
    return rows


def _write_csv(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    """Write execution-time statistics in seconds."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=(
                "phase",
                "group",
                "n",
                "mean_seconds",
                "median_seconds",
                "sd_seconds",
            ),
        )
        writer.writeheader()
        writer.writerows(rows)


def _print_table(rows: list[dict[str, str | float | int]]) -> None:
    """Print execution-time statistics as a Markdown table."""

    print("| Phase | Group | n | Mean (s) | Median (s) | SD (s) |")
    print("|---|---|---:|---:|---:|---:|")
    for row in rows:
        print(
            f"| {row['phase']} | {row['group']} | {row['n']} | "
            f"{row['mean_seconds']:.9f} | "
            f"{row['median_seconds']:.9f} | "
            f"{row['sd_seconds']:.9f} |"
        )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Calculate execution-time statistics for Phase 1 and Phase 2."
    )
    parser.add_argument(
        "--phase1",
        type=Path,
        default=(
            repo_root
            / "results"
            / "phase1"
            / "execution_time"
            / "formal"
            / "summary"
            / "execution_time.csv"
        ),
    )
    parser.add_argument(
        "--phase2",
        type=Path,
        default=(
            repo_root
            / "results"
            / "phase2"
            / "execution_time"
            / "formal"
            / "summary"
            / "execution_time.csv"
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
            / "execution_time_statistics.csv"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    statistics_rows = calculate_statistics(arguments.phase1, arguments.phase2)
    _write_csv(arguments.output, statistics_rows)
    _print_table(statistics_rows)
    print(f"\nCSV written to {arguments.output}")
