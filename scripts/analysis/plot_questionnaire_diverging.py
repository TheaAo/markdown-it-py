"""Plot diverging stacked bars for selected Likert questionnaire columns."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Patch


QUESTION_GROUPS = {
    "FGH": (
        (
            "F",
            "Copilot helped me complete\n"
            "test-generation tasks more quickly.",
        ),
        (
            "G",
            "Copilot helped me achieve\n"
            "better test quality.",
        ),
        (
            "H",
            "Copilot was a useful assistant\n"
            "for this unit-testing task.",
        ),
    ),
    "IJK": (
        (
            "I",
            "Copilot accurately captured the intended\n"
            "business logic and test oracles.",
        ),
        (
            "J",
            "Copilot-generated tests were executable and correct\n"
            "without major manual modifications.",
        ),
        (
            "K",
            "Copilot frequently generated hallucinated assertions\n"
            "or hidden logic errors.",
        ),
    ),
    "VWX": (
        (
            "V",
            "Copilot helped me complete the test-generation tasks\n"
            "more quickly compared to manual development.",
        ),
        (
            "W",
            "Copilot helped me achieve better test quality\n"
            "compared to manual development.",
        ),
        (
            "X",
            "Copilot was a useful assistant\n"
            "for this unit-testing task.",
        ),
    ),
    "ORQGL": (
        (
            "O",
            "Copilot accurately captured the intended business\n"
            "logic and test oracles of the code under test.",
        ),
        (
            "R",
            "Copilot-generated tests were executable and correct\n"
            "without major manual modifications.",
        ),
        (
            "Q",
            "Copilot frequently generated hallucinated assertions\n"
            "or hidden logic errors that cost time to debug.",
        ),
        (
            "G",
            "Copilot-generated tests fulfilled\n"
            "the task requirements.",
        ),
        (
            "L",
            "Copilot-generated tests could give developers\n"
            "a false sense of security.",
        ),
    ),
    "JTUIP": (
        (
            "J",
            "I was able to write effective comments or prompts\n"
            "to guide Copilot in generating the tests I wanted.",
        ),
        (
            "T",
            "I was able to accurately identify flaws or invalid\n"
            "assertions in Copilot-generated tests.",
        ),
        (
            "U",
            "I was able to effectively adapt my testing workflow\n"
            "to collaborate with Copilot.",
        ),
        (
            "I",
            "I clearly understood how or why Copilot-generated\n"
            "tests fulfilled the requirements.",
        ),
        (
            "P",
            "I felt capable of debugging failing tests and\n"
            "identifying the causes of failures with Copilot.",
        ),
    ),
    "LMN": (
        (
            "L",
            "I was able to write effective comments or prompts\n"
            "to guide Copilot in generating the tests I wanted.",
        ),
        (
            "M",
            "I was able to accurately identify flaws or invalid\n"
            "assertions in Copilot-generated tests.",
        ),
        (
            "N",
            "I was able to effectively adapt my testing workflow\n"
            "to collaborate with Copilot.",
        ),
    ),
}
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


def _read_rows(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.reader(file))
    if len(rows) < 2:
        raise ValueError(f"Expected at least one response row in {path}")
    return rows


def _response_counts(rows: list[list[str]], column_index: int) -> Counter[int]:
    try:
        values = [
            int(row[column_index].strip())
            for row in rows[1:]
            if row[column_index].strip()
        ]
    except (IndexError, ValueError) as error:
        raise ValueError(
            f"Column {column_index + 1} contains a non-integer Likert response"
        ) from error
    invalid = sorted(set(values) - set(LEVELS))
    if invalid:
        raise ValueError(f"Unexpected Likert values in column {column_index + 1}: {invalid}")
    return Counter(values)


def plot_diverging(
    rows: list[list[str]],
    output_path: Path,
    question_columns: tuple[tuple[str, str], ...],
) -> None:
    """Create a percentage-based diverging stacked bar chart."""

    figure, axis = plt.subplots(figsize=(11, 5.4))
    response_counts: list[int] = []

    for y_position, (column_letter, label) in enumerate(question_columns):
        counts = _response_counts(rows, ord(column_letter) - ord("A"))
        sample_size = sum(counts.values())
        if not sample_size:
            raise ValueError(f"Column {column_letter} has no valid Likert responses")
        response_counts.append(sample_size)
        percentages = {level: counts[level] / sample_size * 100 for level in LEVELS}

        negative_left = 0.0
        for level in (2, 1):
            width = percentages[level]
            axis.barh(
                y_position,
                -width,
                left=negative_left,
                color=COLORS[level],
                edgecolor="white",
                linewidth=1,
            )
            if width:
                axis.text(
                    negative_left - width / 2,
                    y_position,
                    f"{counts[level]} ({width:.0f}%)",
                    ha="center",
                    va="center",
                    fontsize=9,
                    color="white",
                    fontweight="bold",
                )
            negative_left -= width

        neutral_width = percentages[3]
        axis.barh(
            y_position,
            neutral_width,
            left=-neutral_width / 2,
            color=COLORS[3],
            edgecolor="white",
            linewidth=1,
        )
        if neutral_width:
            axis.text(
                0,
                y_position,
                f"{counts[3]} ({neutral_width:.0f}%)",
                ha="center",
                va="center",
                fontsize=9,
                color="#374151",
                fontweight="bold",
            )

        positive_left = 0.0
        for level in (4, 5):
            width = percentages[level]
            axis.barh(
                y_position,
                width,
                left=positive_left,
                color=COLORS[level],
                edgecolor="white",
                linewidth=1,
            )
            if width:
                axis.text(
                    positive_left + width / 2,
                    y_position,
                    f"{counts[level]} ({width:.0f}%)",
                    ha="center",
                    va="center",
                    fontsize=9,
                    color="white",
                    fontweight="bold",
                )
            positive_left += width

    axis.axvline(0, color="#374151", linewidth=0.8)
    axis.set_xlim(-100, 100)
    axis.set_xticks(range(-100, 101, 20))
    axis.set_xticklabels([f"{abs(value)}%" for value in range(-100, 101, 20)])
    if len(set(response_counts)) == 1:
        axis.set_xlabel(f"Share of responses (n={response_counts[0]})")
    else:
        axis.set_xlabel("Share of valid responses")
    include_counts = len(set(response_counts)) != 1
    axis.set_yticks(
        range(len(question_columns)),
        [
            f"{index}. {label}{f' (n={sample_size})' if include_counts else ''}"
            for index, ((_, label), sample_size) in enumerate(
                zip(question_columns, response_counts), 1
            )
        ],
    )
    axis.invert_yaxis()
    axis.grid(axis="x", linestyle="--", alpha=0.35)
    axis.set_axisbelow(True)
    axis.spines[["top", "right", "left"]].set_visible(False)
    legend_handles = [Patch(facecolor=COLORS[level], label=f"{level}: {LABELS[level]}") for level in LEVELS]
    axis.legend(
        handles=legend_handles,
        title="Likert response",
        ncol=3,
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
    )
    figure.tight_layout(rect=(0, 0.12, 1, 1))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    figure.savefig(output_path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(figure)


def main(input_path: Path, output_path: Path, columns: str) -> None:
    plot_diverging(_read_rows(input_path), output_path, QUESTION_GROUPS[columns])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_path", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument("--columns", choices=QUESTION_GROUPS, default="LMN")
    arguments = parser.parse_args()
    main(arguments.input_path, arguments.output_path, arguments.columns)
