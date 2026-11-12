"""Calculate Phase 2 assertion-score statistics by experiment group."""

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
SCORE_COLUMN = "assertion_score"
GROUP_BY_PHASE1_GROUP = {"AI": "AI-AI", "Manual": "Manual-AI"}
EXPECTED_PARTICIPANTS = {
    participant.number
    for participant in PARTICIPANTS_BY_NUMBER.values()
    if participant.participated_in_phase2
}


def _read_scores(path: Path) -> dict[str, list[float]]:
    """Read collected scores and assign them to the Phase 2 experiment groups."""

    scores = {group: [] for group in GROUPS}
    seen_participants: set[int] = set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required_columns = {"participant_number", "status", SCORE_COLUMN}
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

            raw_score = row[SCORE_COLUMN].strip()
            score = float(raw_score) if raw_score else 0.0
            if not 0 <= score <= 1:
                raise ValueError(
                    f"Assertion score for participant {participant} "
                    f"must be between 0 and 1, got {score}"
                )
            group = GROUP_BY_PHASE1_GROUP[metadata.phase1_group]
            scores[group].append(score)

    missing_participants = EXPECTED_PARTICIPANTS - seen_participants
    if missing_participants:
        raise ValueError(
            "Missing collected Phase 2 participants: "
            f"{sorted(missing_participants)}"
        )
    return scores


def calculate_statistics(path: Path) -> list[dict[str, str | float | int]]:
    """Calculate mean, median, and sample SD as decimal values."""

    scores = _read_scores(path)
    return [
        {
            "group": group,
            "n": len(group_scores),
            "mean": statistics.mean(group_scores),
            "median": statistics.median(group_scores),
            "sd": statistics.stdev(group_scores),
        }
        for group in GROUPS
        for group_scores in [scores[group]]
    ]


def _write_csv(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    """Write assertion-score statistics as decimal values."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=("group", "n", "mean", "median", "sd"),
        )
        writer.writeheader()
        writer.writerows(rows)


def _print_table(rows: list[dict[str, str | float | int]]) -> None:
    """Print assertion-score statistics as a Markdown table."""

    print("| Group | n | Mean | Median | SD |")
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
        description="Calculate Phase 2 assertion-score statistics by group."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            repo_root
            / "results"
            / "phase2"
            / "assertion_score"
            / "assertion_score.csv"
        ),
        help="Phase 2 assertion-score CSV.",
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
            / "phase2_assertion_score_statistics.csv"
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
