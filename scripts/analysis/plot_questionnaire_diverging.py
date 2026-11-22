"""Create compact diverging Likert plots for the Phase 1 and Phase 2 surveys."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch


LEVELS = (1, 2, 3, 4, 5)
COLORS = {
    1: "#B2182B",
    2: "#EF8A62",
    3: "#D9D9D9",
    4: "#78C679",
    5: "#238443",
}
LABELS = {
    1: "Strongly disagree",
    2: "Disagree",
    3: "Neither agree nor disagree",
    4: "Agree",
    5: "Strongly agree",
}

PHASE_CONFIG = {
    "phase1": {
        "input": Path("results/phase1/questionnaire/post_survey_ai_group.csv"),
        "output": Path("scripts/analysis/outputs/figures/phase1_likert_diverging.pdf"),
        "groups": (
            (
                "Perceived Usefulness",
                (
                    ("F", "PU1"),
                    ("G", "PU2"),
                    ("H", "PU3"),
                ),
            ),
            (
                "Perceived Trustworthiness",
                (
                    ("I", "PT1"),
                    ("J", "PT2"),
                    ("K", "PT3"),
                ),
            ),
            (
                "Perceived Self-efficacy",
                (
                    ("L", "PS1"),
                    ("M", "PS2"),
                    ("N", "PS3"),
                ),
            ),
        ),
    },
    "phase2": {
        "input": Path("results/phase2/Post-experiment Survey (Phase 2).csv"),
        "output": Path("scripts/analysis/outputs/figures/phase2_likert_diverging.pdf"),
        "groups": (
            (
                "Perceived Usefulness",
                (
                    ("V", "PU1"),
                    ("W", "PU2"),
                    ("X", "PU3"),
                ),
            ),
            (
                "Perceived Trustworthiness",
                (
                    ("O", "PT1"),
                    ("R", "PT2"),
                    ("Q", "PT3"),
                    ("G", "PT4"),
                    ("L", "PT5"),
                ),
            ),
            (
                "Perceived Self-efficacy",
                (
                    ("J", "PS1"),
                    ("T", "PS2"),
                    ("U", "PS3"),
                    ("I", "PS4"),
                    ("P", "PS5"),
                ),
            ),
        ),
    },
}


def _read_rows(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.reader(file))
    if len(rows) < 2:
        raise ValueError(f"Expected at least one response row in {path}")
    return rows


def _response_counts(rows: list[list[str]], column_letter: str) -> Counter[int]:
    column_index = ord(column_letter.upper()) - ord("A")
    try:
        values = [
            int(row[column_index].strip())
            for row in rows[1:]
            if column_index < len(row) and row[column_index].strip()
        ]
    except (IndexError, ValueError) as error:
        raise ValueError(
            f"Column {column_letter} contains a non-integer Likert response"
        ) from error

    invalid = sorted(set(values) - set(LEVELS))
    if invalid:
        raise ValueError(f"Unexpected Likert values in column {column_letter}: {invalid}")
    return Counter(values)


def _text_label(count: int, percentage: float, neutral: bool = False) -> str | None:
    if count == 0:
        return None
    if percentage >= 10.0:
        return str(count)
    return None


def _text_color(level: int) -> str:
    if level == 3:
        return "#374151"
    if level == 4:
        return "#172B1A"
    return "white"


def plot_diverging(rows: list[list[str]], output_path: Path, groups: tuple) -> None:
    """Plot all questionnaire items in one compact diverging stacked bar chart."""

    question_items: list[tuple[str, str]] = []
    group_ranges: list[tuple[str, int, int]] = []
    y_positions: list[float] = []
    y = 0.0

    for group_index, (group_name, items) in enumerate(groups):
        start = len(question_items)
        for column_letter, item_label in items:
            question_items.append((column_letter, item_label))
            y_positions.append(y)
            y += 1.0
        end = len(question_items) - 1
        group_ranges.append((group_name, start, end))
        if group_index < len(groups) - 1:
            y += 0.75

    figure_height = max(3.8, 2.2 + len(question_items) * 0.22)
    figure, axis = plt.subplots(figsize=(7.2, figure_height), constrained_layout=False)

    response_counts: list[int] = []
    for y_position, (column_letter, item_label) in zip(y_positions, question_items):
        counts = _response_counts(rows, column_letter)
        sample_size = sum(counts.values())
        if not sample_size:
            raise ValueError(f"Column {column_letter} has no valid Likert responses")
        response_counts.append(sample_size)
        percentages = {level: counts[level] / sample_size * 100 for level in LEVELS}

        neutral_width = percentages[3]
        neutral_left = -neutral_width / 2
        neutral_midpoint = 0.0

        negative_left = neutral_left
        for level in (2, 1):
            width = percentages[level]
            segment_left = negative_left - width
            axis.barh(
                y_position,
                width,
                left=segment_left,
                height=0.64,
                color=COLORS[level],
                edgecolor="white",
                linewidth=0.8,
            )
            label = _text_label(counts[level], width)
            if label:
                axis.text(
                    segment_left + width / 2,
                    y_position,
                    label,
                    ha="center",
                    va="center",
                    fontsize=8,
                    color=_text_color(level),
                    fontweight="bold",
                )
            negative_left = segment_left

        axis.barh(
            y_position,
            neutral_width,
            left=neutral_left,
            height=0.64,
            color=COLORS[3],
            edgecolor="white",
            linewidth=0.8,
        )
        label = _text_label(counts[3], neutral_width, neutral=True)
        if label:
            axis.text(
                neutral_midpoint,
                y_position,
                label,
                ha="center",
                va="center",
                fontsize=8,
                color=_text_color(3),
                fontweight="bold",
            )

        positive_left = neutral_left + neutral_width
        for level in (4, 5):
            width = percentages[level]
            axis.barh(
                y_position,
                width,
                left=positive_left,
                height=0.64,
                color=COLORS[level],
                edgecolor="white",
                linewidth=0.8,
            )
            label = _text_label(counts[level], width)
            if label:
                axis.text(
                    positive_left + width / 2,
                    y_position,
                    label,
                    ha="center",
                    va="center",
                    fontsize=8,
                    color=_text_color(level),
                    fontweight="bold",
                )
            positive_left += width

    axis.axvline(0.0, color="#374151", linewidth=1.0, zorder=6)
    axis.set_xlim(-100, 100)
    axis.set_xticks(range(-100, 101, 20))
    axis.set_xticklabels([f"{abs(value)}%" for value in range(-100, 101, 20)], fontsize=8.5)

    axis.set_yticks(y_positions)
    axis.set_yticklabels([item_label for _, item_label in question_items], fontsize=9)
    axis.invert_yaxis()

    for group_name, start, _ in group_ranges:
        title_y = y_positions[start] - 0.42
        axis.text(
            -96,
            title_y,
            group_name,
            ha="left",
            va="bottom",
            fontsize=8,
            fontweight="bold",
            color="#4B5563",
            clip_on=True,
        )

    for index in range(len(group_ranges) - 1):
        _, _, previous_end = group_ranges[index]
        next_name, next_start, _ = group_ranges[index + 1]
        del next_name
        separator = (y_positions[previous_end] + y_positions[next_start]) / 2
        axis.axhline(separator, color="#D1D5DB", linewidth=0.8, linestyle="--", zorder=0)

    if len(set(response_counts)) == 1:
        axis.set_xlabel(f"Share of valid responses (n={response_counts[0]})", fontsize=9.5)
    else:
        axis.set_xlabel("Share of valid responses", fontsize=9.5)

    axis.grid(axis="x", linestyle="--", linewidth=0.6, alpha=0.35)
    axis.set_axisbelow(True)
    axis.spines[["top", "right", "left", "bottom"]].set_visible(False)
    axis.tick_params(axis="y", length=0)
    axis.tick_params(axis="x", length=0)

    legend_handles = [
        Patch(facecolor=COLORS[level], label=f"{level}: {LABELS[level]}")
        for level in LEVELS
    ]
    axis.legend(
        handles=legend_handles,
        title="Likert response",
        ncol=3,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.15),
        fontsize=8.5,
        title_fontsize=9,
        handlelength=1.4,
        columnspacing=1.4,
    )

    figure.subplots_adjust(left=0.24, right=0.98, top=0.98, bottom=0.22)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, bbox_inches="tight", dpi=300)
    figure.savefig(output_path.with_suffix(".png"), bbox_inches="tight", dpi=300)
    figure.savefig(output_path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(figure)


def main(phase: str, input_path: Path | None = None, output_path: Path | None = None) -> None:
    project_root = Path(__file__).resolve().parents[2]
    config = PHASE_CONFIG[phase]

    source_path = input_path if input_path is not None else project_root / config["input"]
    destination = output_path if output_path is not None else project_root / config["output"]
    if destination.suffix.lower() != ".pdf":
        destination = destination.with_suffix(".pdf")

    plot_diverging(_read_rows(source_path), destination, config["groups"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("phase1", "phase2"), help="Survey phase to plot")
    parser.add_argument("input_path", nargs="?", type=Path, help="Optional CSV input override")
    parser.add_argument("output_path", nargs="?", type=Path, help="Optional PDF output override")
    arguments = parser.parse_args()
    main(arguments.phase, arguments.input_path, arguments.output_path)
