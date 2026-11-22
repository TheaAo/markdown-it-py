"""Plot paired Phase 1 and Phase 2 specified mutation-score distributions."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator, PercentFormatter

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from scripts.analysis.participants import PARTICIPANTS_BY_NUMBER
except ImportError:
    from .participants import PARTICIPANTS_BY_NUMBER


SCORE_COLUMN = "specified_estimated_adjusted_score"
SEQUENCE_COLORS = {
    "Manual → AI": "#0072B2",
    "AI → AI": "#D55E00",
}
GROUP_X_OFFSET = {
    "Manual → AI": -0.07,
    "AI → AI": 0.07,
}


def read_mutation_scores(path: Path) -> dict[int, dict[str, float | str]]:
    """Read collected participant-level mutation scores by participant ID."""

    values: dict[int, dict[str, float | str]] = {}
    seen: set[int] = set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required = {"participant_number", "status", SCORE_COLUMN}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

        for row in reader:
            if row["status"].strip() != "collected":
                continue

            participant = int(row["participant_number"])
            if participant in seen:
                raise ValueError(f"Duplicate participant: {participant}")
            participant_metadata = PARTICIPANTS_BY_NUMBER.get(participant)
            if participant_metadata is None:
                continue

            seen.add(participant)
            raw_score = row[SCORE_COLUMN].strip()
            if not raw_score:
                raise ValueError(
                    f"Missing specified estimated adjusted score for participant {participant}"
                )
            score = float(raw_score)
            if not 0 <= score <= 1:
                raise ValueError(
                    f"Mutation score for participant {participant} must be between 0 and 1, got {score}"
                )

            sequence = (
                "Manual → AI"
                if participant_metadata.phase1_group == "Manual"
                else "AI → AI"
            )
            values[participant] = {"sequence": sequence, "score": score}

    return values


def read_phase2_mutation_scores(path: Path) -> dict[int, dict[str, float | str]]:
    """Read Phase 2 collected scores and retain only participating metadata IDs."""

    values = read_mutation_scores(path)
    return {
        participant: participant_values
        for participant, participant_values in values.items()
        if PARTICIPANTS_BY_NUMBER[participant].participated_in_phase2
    }


def build_participant_x_offsets() -> dict[int, float]:
    """Return a deterministic horizontal offset for every participant."""

    ids_by_sequence: dict[str, list[int]] = {
        "Manual → AI": [],
        "AI → AI": [],
    }
    for participant_number, participant in PARTICIPANTS_BY_NUMBER.items():
        sequence = "Manual → AI" if participant.phase1_group == "Manual" else "AI → AI"
        ids_by_sequence[sequence].append(participant_number)

    offsets: dict[int, float] = {}
    for sequence, participant_ids in ids_by_sequence.items():
        participant_ids.sort()
        for rank, participant_number in enumerate(participant_ids):
            offsets[participant_number] = (
                rank - (len(participant_ids) - 1) / 2
            ) * 0.022
    return offsets


def score_y_limits(values: list[float]) -> tuple[float, float]:
    """Choose a focused range while retaining every observation."""

    if not values:
        return (0.0, 1.0)
    minimum = min(values)
    maximum = max(values)
    padding = max((maximum - minimum) * 0.12, 0.03)
    lower = max(0.0, minimum - padding)
    upper = min(1.0, maximum + padding)
    if upper == lower:
        upper = min(1.0, upper + 0.05)
    return lower, upper


def plot_cross_phase_mutation_score(
    phase1_path: Path,
    phase2_path: Path,
    output_path: Path,
) -> None:
    """Create a paired scatter-and-line plot for cross-phase mutation score."""

    phase1 = read_mutation_scores(phase1_path)
    phase2 = read_phase2_mutation_scores(phase2_path)
    participant_offsets = build_participant_x_offsets()

    figure, axis = plt.subplots(figsize=(7.2, 4.2))
    all_scores = [
        float(values["score"])
        for values in list(phase1.values()) + list(phase2.values())
    ]

    for participant, phase1_values in phase1.items():
        sequence = str(phase1_values["sequence"])
        offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
        axis.scatter(
            0 + offset,
            float(phase1_values["score"]),
            s=64,
            color=SEQUENCE_COLORS[sequence],
            edgecolor="white",
            linewidth=0.7,
            alpha=0.92,
            zorder=3,
        )

    for participant in sorted(set(phase1) & set(phase2)):
        phase1_values = phase1[participant]
        phase2_values = phase2[participant]
        sequence = str(phase1_values["sequence"])
        offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
        axis.plot(
            (0 + offset, 1 + offset),
            (float(phase1_values["score"]), float(phase2_values["score"])),
            color=SEQUENCE_COLORS[sequence],
            linewidth=1.0,
            alpha=0.38,
            zorder=1,
        )

    for participant, phase2_values in phase2.items():
        sequence = str(phase2_values["sequence"])
        offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
        axis.scatter(
            1 + offset,
            float(phase2_values["score"]),
            s=64,
            color=SEQUENCE_COLORS[sequence],
            edgecolor="white",
            linewidth=0.7,
            alpha=0.92,
            zorder=3,
        )

    axis.set_xticks([0, 1], ["Phase 1", "Phase 2"])
    axis.set_xlim(-0.23, 1.23)
    lower, upper = score_y_limits(all_scores)
    axis.set_ylim(lower, upper)
    axis.yaxis.set_major_locator(MultipleLocator(0.20))
    axis.yaxis.set_minor_locator(MultipleLocator(0.10))
    axis.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    axis.set_ylabel("Mutation Score (%)", fontsize=16)
    axis.set_xlabel("", fontsize=16)
    axis.set_title("", fontsize=18)
    axis.grid(axis="y", which="major", linestyle="-", linewidth=0.7, alpha=0.30)
    axis.grid(axis="y", which="minor", linestyle="-", linewidth=0.5, alpha=0.18)
    axis.set_axisbelow(True)
    axis.tick_params(axis="both", which="major", labelsize=15)
    axis.tick_params(axis="y", which="minor", length=3)
    for spine in axis.spines.values():
        spine.set_visible(False)

    legend_labels = {
        "Manual → AI": "Initially Manual (Manual → AI for returning participants)",
        "AI → AI": "Initially AI (AI → AI for returning participants)",
    }
    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle="None",
            markerfacecolor=color,
            markeredgecolor="white",
            markersize=9,
            label=legend_labels[sequence],
        )
        for sequence, color in SEQUENCE_COLORS.items()
    ]
    figure.legend(
        handles=legend_handles,
        frameon=False,
        loc="lower center",
        ncol=2,
        bbox_to_anchor=(0.5, -0.02),
        fontsize=14.5,
        handletextpad=0.5,
        columnspacing=1.8,
    )

    figure.subplots_adjust(left=0.09, right=0.99, bottom=0.18, top=0.93)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, bbox_inches="tight")
    plt.close(figure)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = REPO_ROOT
    parser = argparse.ArgumentParser(
        description="Plot paired cross-phase specified mutation-score distributions."
    )
    parser.add_argument(
        "--phase1",
        type=Path,
        default=(
            repo_root
            / "results"
            / "phase1"
            / "mutation_score"
            / "full-sut"
            / "formal"
            / "global"
            / "equivalent_review_sample_stage1"
            / "final"
            / "mutation_scores.csv"
        ),
    )
    parser.add_argument(
        "--phase2",
        type=Path,
        default=(repo_root / "results" / "phase2" / "mutation_score" / "mutation_score.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            repo_root
            / "scripts"
            / "analysis"
            / "outputs"
            / "figures"
            / "cross_phase_mutation_score.pdf"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    plot_cross_phase_mutation_score(arguments.phase1, arguments.phase2, arguments.output)
