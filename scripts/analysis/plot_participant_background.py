"""Plot participant programming experience and proficiency distributions."""

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
    ("pytest proficiency", "How would you rate your experience in pytest?"),
    ("GitHub Copilot proficiency", "How would you rate your experience in using Github Copilot?"),
)
PROGRAMMING_EXPERIENCE_ORDER = ("1_2 years", "3-5 years", "5-10 years")
PROFICIENCY_ORDER = ("0", "1", "2", "3", "4", "5")
PROFICIENCY_LABELS = {
    "0": "No experience",
    "1": "Beginner (Understand basic syntax and write simple Python code with guidance)",
    "2": "Junior (Have written simple scripts or code independently)",
    "3": "Intermediate (Comfortable with standard libraries, OOP, and idiomatic Python)",
    "4": "Advanced (Strong understanding of advanced features, best practices, and performance \n optimizations)",
    "5": "Expert (Extensive experience, including complex system architecture or low-level design)",
}
COLORS = {
    "0": "#E5E7EB",
    "1": "#DBEAFE",
    "2": "#93C5FD",
    "3": "#60A5FA",
    "4": "#2563EB",
    "5": "#1E3A8A",
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


def plot_programming_experience_across_phases(
    phase1_rows: list[dict[str, str]],
    phase2_rows: list[dict[str, str]],
    output_path: Path,
) -> None:
    """Create a grouped stacked-bar chart comparing both phases."""

    phase_rows = (
        ("Phase 1", phase1_rows),
        ("Phase 2", phase2_rows),
    )
    figure, axis = plt.subplots(figsize=(12, 6.0))

    y_positions = list(range(len(phase_rows)))
    for y_position, (_, rows) in zip(y_positions, phase_rows):
        counts = _counts(rows, DIMENSIONS[0][1])
        left = 0
        for level in PROGRAMMING_EXPERIENCE_ORDER:
            count = counts[level]
            if count == 0:
                continue
            axis.barh(
                y_position,
                count,
                left=left,
                height=0.55,
                color=COLORS[level],
                edgecolor="white",
                linewidth=1,
            )
            axis.text(
                left + count / 2,
                y_position,
                f"{count}",
                ha="center",
                va="center",
                fontsize=16,
                color="#111827",
                fontweight="bold",
            )
            left += count

    experience_labels = {
        "1_2 years": "1–2 years",
        "3-5 years": "3–5 years",
        "5-10 years": "5–10 years",
    }
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=COLORS[level])
        for level in PROGRAMMING_EXPERIENCE_ORDER
    ]
    labels = [experience_labels[level] for level in PROGRAMMING_EXPERIENCE_ORDER]
    legend = axis.legend(
        handles,
        labels,
        ncol=3,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
    )
    for text in legend.get_texts():
        text.set_fontsize(15)

    axis.set_yticks(y_positions, [title for title, _ in phase_rows])
    axis.invert_yaxis()
    axis.tick_params(axis="both", labelsize=16)
    axis.set_xlabel("Number of participants", labelpad=8, fontsize=18)
    axis.set_title(
        "Programming Experience of Participants Across Both Phases",
        fontsize=20,
        pad=12,
    )
    axis.set_xlim(0, max(len(rows) for _, rows in phase_rows))
    axis.set_xticks(range(max(len(rows) for _, rows in phase_rows) + 1))
    axis.grid(axis="x", linestyle="--", alpha=0.35)
    axis.set_axisbelow(True)
    figure.tight_layout(rect=(0, 0.16, 1, 1))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    figure.savefig(output_path.with_suffix(".svg"), bbox_inches="tight")
    figure.savefig(output_path.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(figure)


def plot_proficiency_across_phases(
    all_rows: list[dict[str, str]],
    phase2_rows: list[dict[str, str]],
    output_path: Path,
) -> None:
    """Create a single-coordinate stacked-bar chart for both phases."""

    proficiency_dimensions = DIMENSIONS[1:]
    figure, axis = plt.subplots(figsize=(11, 12.0))

    y_positions = [position for group in range(len(proficiency_dimensions)) for position in (group * 2.5, group * 2.5 + 1)]
    phase_rows = (("Phase 1", all_rows), ("Phase 2", phase2_rows))

    for group_index, (dimension, column) in enumerate(proficiency_dimensions):
        group_y_positions = (
            y_positions[group_index * 2],
            y_positions[group_index * 2 + 1],
        )
        for y_position, (_, rows) in zip(group_y_positions, phase_rows):
            counts = _counts(rows, column)
            left = 0
            for level in PROFICIENCY_ORDER:
                count = counts[level]
                if count == 0:
                    continue
                axis.barh(
                    y_position,
                    count,
                    left=left,
                    height=1.0,
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
                    fontsize=16,
                    color="white" if level in {"4", "5"} else "#111827",
                    fontweight="bold",
                )
                left += count

    tick_labels = [
        phase_label
        for _ in proficiency_dimensions
        for phase_label in ("Phase 1", "Phase 2")
    ]
    axis.set_yticks(y_positions, tick_labels)
    axis.invert_yaxis()
    axis.tick_params(axis="y", labelsize=13)
    axis.tick_params(axis="x", labelsize=14)
    axis.set_xlabel("Number of participants", fontsize=17, labelpad=10)

    dimension_labels = (
        "Python\nproficiency",
        "Software testing\nproficiency",
        "Unit-test writing\nproficiency",
        "pytest\nproficiency",
        "GitHub Copilot\nproficiency",
    )
    for group_index, label in enumerate(dimension_labels):
        center = (y_positions[group_index * 2] + y_positions[group_index * 2 + 1]) / 2
        axis.text(
            -0.15,
            center,
            label,
            transform=axis.get_yaxis_transform(),
            ha="right",
            va="center",
            fontsize=15,
            linespacing=1.15,
        )

    handles = [
        plt.Rectangle((0, 0), 1, 1, color=COLORS[level])
        for level in PROFICIENCY_ORDER
    ]
    labels = [PROFICIENCY_LABELS[level] for level in PROFICIENCY_ORDER]
    legend = axis.legend(
        handles,
        labels,
        ncol=1,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        handlelength=1.5,
        handletextpad=0.6,
        labelspacing=0.20,
    )
    for text in legend.get_texts():
        text.set_fontsize(15)

    max_participants = max(len(all_rows), len(phase2_rows))
    axis.set_xlim(0, max(len(all_rows), len(phase2_rows)))
    axis.set_xticks(range(max_participants + 1))
    axis.grid(axis="x", linestyle="--", alpha=0.35)
    axis.set_axisbelow(True)
    axis.set_title(
        "Technical Proficiency of Participants Across Both Phases",
        fontsize=20,
        pad=32,
    )
    axis.text(
        0.5,
        1.05,
        f"Phase 1 (n = {len(all_rows)}), Phase 2 (n = {len(phase2_rows)})",
        transform=axis.transAxes,
        ha="center",
        va="bottom",
        fontsize=14,
        style="italic",
    )

    figure.subplots_adjust(left=0.27, right=0.98, bottom=0.43, top=0.78)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    figure.savefig(output_path.with_suffix(".svg"), bbox_inches="tight")
    figure.savefig(output_path.with_suffix(".pdf"), bbox_inches="tight")
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
    plot_programming_experience_across_phases(
        rows,
        phase2_rows,
        output_dir / "participant_programming_experience_across_phases.png",
    )
    plot_proficiency_across_phases(
        rows,
        phase2_rows,
        output_dir / "participant_proficiency_across_phases.png",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_path", type=Path)
    parser.add_argument("output_dir", type=Path)
    arguments = parser.parse_args()
    main(arguments.input_path, arguments.output_dir)