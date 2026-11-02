"""Plot Phase 2 specified estimated adjusted mutation scores by group."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

try:
    from .participants import PARTICIPANTS_BY_NUMBER
except ImportError:
    from participants import PARTICIPANTS_BY_NUMBER


GROUPS = ("Manual-AI", "AI-AI")
COLORS = {"Manual-AI": "#6B7280", "AI-AI": "#2563EB"}
REQUIRED_COLUMNS = {
    "participant_number",
    "status",
    "specified_estimated_adjusted_score",
}


def read_scores(path: Path) -> dict[str, list[float]]:
    """Read Phase 2 scores and group them using Phase 1 assignments."""

    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

        scores = {group: [] for group in GROUPS}
        seen_participants: set[int] = set()
        for row in reader:
            if row["status"] != "collected":
                continue

            participant = int(row["participant_number"])
            metadata = PARTICIPANTS_BY_NUMBER.get(participant)
            if metadata is None or not metadata.participated_in_phase2:
                continue
            if participant in seen_participants:
                raise ValueError(f"Duplicate collected participant: {participant}")
            seen_participants.add(participant)

            raw_score = row["specified_estimated_adjusted_score"].strip()
            if not raw_score:
                raise ValueError(
                    f"Missing specified estimated adjusted score for participant {participant}"
                )
            score = float(raw_score)
            if not 0 <= score <= 1:
                raise ValueError(
                    f"Score for participant {participant} must be between 0 and 1: {score}"
                )
            group = "AI-AI" if metadata.phase1_group == "AI" else "Manual-AI"
            scores[group].append(score)

    for group in GROUPS:
        if not scores[group]:
            raise ValueError(f"No Phase 2 mutation-score values found for {group}")
    return scores


def plot_scores(input_path: Path, output_path: Path) -> None:
    """Create and save the grouped Phase 2 mutation-score chart."""

    scores_by_group = read_scores(input_path)
    positions = {group: index for index, group in enumerate(GROUPS)}
    figure, axis = plt.subplots(figsize=(8.5, 6))

    for group in GROUPS:
        scores = scores_by_group[group]
        x = positions[group]
        point_positions = [
            x + (index - (len(scores) - 1) / 2) * 0.055
            for index in range(len(scores))
        ]
        axis.scatter(
            point_positions,
            scores,
            s=70,
            color=COLORS[group],
            edgecolor="white",
            linewidth=0.8,
            alpha=0.9,
            label=f"{group} raw data",
            zorder=3,
        )

        group_mean = sum(scores) / len(scores)
        group_median = median(scores)
        axis.scatter(
            x,
            group_mean,
            s=100,
            marker="D",
            facecolors="none",
            edgecolors=COLORS[group],
            linewidth=2,
            label="Mean" if group == GROUPS[0] else None,
            zorder=4,
        )
        axis.hlines(
            group_median,
            x - 0.2,
            x + 0.2,
            color=COLORS[group],
            linestyle="--",
            linewidth=2,
            label="Median" if group == GROUPS[0] else None,
            zorder=4,
        )

        label_offset = 0.012 if abs(group_mean - group_median) < 0.025 else 0
        axis.text(
            x + 0.23,
            group_mean + label_offset,
            f"mean {group_mean:.2%}",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )
        axis.text(
            x + 0.23,
            group_median - label_offset,
            f"median {group_median:.2%}",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )

    axis.set_title("Phase 2 Specified Estimated Adjusted Mutation Score by Group")
    axis.set_xlabel("Group")
    axis.set_ylabel("Specified estimated adjusted score")
    axis.set_xticks(list(positions.values()), GROUPS)
    axis.set_xlim(-0.5, 1.5)
    axis.set_ylim(0, 1.05)
    axis.yaxis.set_major_formatter(PercentFormatter(1))
    axis.grid(axis="y", linestyle="--", alpha=0.35)
    axis.set_axisbelow(True)
    axis.legend(frameon=False, loc="lower left")
    figure.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(figure)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Plot Phase 2 specified adjusted mutation scores by group."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            repo_root
            / "results"
            / "phase2"
            / "mutation_score"
            / "mutation_score.csv"
        ),
        help="Phase 2 mutation-score CSV.",
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
            / "phase2_specified_estimated_adjusted_score_raw_by_group.png"
        ),
        help="Output image path.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    plot_scores(arguments.input, arguments.output)
