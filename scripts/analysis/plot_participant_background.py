"""Plot participant background distributions as stacked bar charts."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt

try:
    from .participants import PARTICIPANTS_BY_NUMBER
except ImportError:
    from participants import PARTICIPANTS_BY_NUMBER


DIMENSIONS = (
    ("Programming experience", "How many years of active programming experience do you have?"),
    ("Python proficiency", "How would you rate your overall proficiency in Python development?"),
    ("Software testing proficiency", "How would you rate your overall proficiency in software testing?"),
    ("Unit-test writing proficiency", "How would you rate your overall proficiency in writing unit tests?"),
    ("pytest experience", "How would you rate your experience in pytest?"),
    ("GitHub Copilot experience", "How would you rate your experience in using Github Copilot?"),
)
PROGRAMMING_EXPERIENCE_ORDER = ("1_2 years", "3-5 years", "5-10 years")
PROFICIENCY_ORDER = ("0", "1", "2", "3", "4", "5")
COLORS = {
    "0": "#D1D5DB",
    "1": "#FDE68A",
    "2": "#FDBA74",
    "3": "#93C5FD",
    "4": "#60A5FA",
    "5": "#2563EB",
    "1_2 years": "#FDE68A",
    "3-5 years": "#93C5FD",
    "5-10 years": "#2563EB",
}


def _read_rows(path: Path) -> list[dict[str, str]]:
    """Read questionnaire rows for participants defined in participants.py."""

    with path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    selected: list[dict[str, str]] = []
    for row in rows:
        participant_number = int(row["No"])
        if participant_number in PARTICIPANTS_BY_NUMBER:
            selected.append(row)
    if not selected:
        raise ValueError(f"No valid participant rows found in {path}")
    return selected


def _counts(rows: list[dict[str, str]], column: str) -> Counter[str]:
    """Count responses for one questionnaire dimension."""

    return Counter(row[column].strip() for row in rows)


def _ordered_levels(counts: Counter[str], dimension: str) -> list[str]:
    """Return levels in a stable, meaningful order."""

    order = PROGRAMMING_EXPERIENCE_ORDER if dimension == "Programming experience" else PROFICIENCY_ORDER
    return [level for level in order if counts[level]]


def plot_background(rows: list[dict[str, str]], title: str, output_path: Path) -> None:
    """Create a horizontal stacked bar chart for a participant subset."""

    figure, axis = plt.subplots(figsize=(12, 6.8))
    y_positions = list(range(len(DIMENSIONS)))
    for y_position, (dimension, column) in zip(y_positions, DIMENSIONS):
        counts = _counts(rows, column)
        left = 0
        for level in _ordered_levels(counts, dimension):
            count = counts[level]
            axis.barh(
                y_position,
                count,
                left=left,
                color=COLORS[level],
                edgecolor="white",
                linewidth=1,
            )
            axis.text(
                left + count / 2,
                y_position,
                str(count),
                ha="center",
                va="center",
                fontsize=10,
                color="white" if level in {"4", "5", "5-10 years"} else "#111827",
                fontweight="bold",
            )
            left += count

    handles = [plt.Rectangle((0, 0), 1, 1, color=COLORS[level]) for level in PROFICIENCY_ORDER]
    labels = list(PROFICIENCY_ORDER)
    handles.extend(plt.Rectangle((0, 0), 1, 1, color=COLORS[level]) for level in PROGRAMMING_EXPERIENCE_ORDER)
    labels.extend(PROGRAMMING_EXPERIENCE_ORDER)
    axis.legend(
        handles,
        labels,
        title="Response level",
        ncol=3,
        frameon=False,
        loc="upper right",
        bbox_to_anchor=(1, -0.08),
    )
    axis.text(
        0,
        -0.12,
        "Proficiency scale: 1 = Very Basic; 5 = Proficient. "
        "0 = No experience / Not applicable.",
        transform=axis.transAxes,
        ha="left",
        va="top",
        fontsize=10,
    )
    axis.set_yticks(y_positions, [dimension for dimension, _ in DIMENSIONS])
    axis.invert_yaxis()
    axis.set_xlabel("Number of participants")
    axis.set_title(title)
    axis.set_xlim(0, len(rows))
    axis.set_xticks(range(len(rows) + 1))
    axis.grid(axis="x", linestyle="--", alpha=0.35)
    axis.set_axisbelow(True)
    figure.tight_layout(rect=(0, 0.18, 1, 1))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(figure)


def main(input_path: Path, output_dir: Path) -> None:
    """Generate charts for all valid participants and Phase 2 participants."""

    rows = _read_rows(input_path)
    phase2_numbers = {
        participant.number
        for participant in PARTICIPANTS_BY_NUMBER.values()
        if participant.participated_in_phase2
    }
    phase2_rows = [row for row in rows if int(row["No"]) in phase2_numbers]
    plot_background(
        rows,
        "Participant Background Composition (All Participants)",
        output_dir / "participant_background_all.png",
    )
    plot_background(
        phase2_rows,
        "Participant Background Composition (Phase 2 Participants)",
        output_dir / "participant_background_phase2.png",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_path", type=Path)
    parser.add_argument("output_dir", type=Path)
    arguments = parser.parse_args()
    main(arguments.input_path, arguments.output_dir)