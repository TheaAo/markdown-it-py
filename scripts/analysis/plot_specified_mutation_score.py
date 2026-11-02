"""Plot Phase 1 specified estimated adjusted mutation scores by group."""

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


GROUPS = ("Manual", "AI")
COLORS = {"Manual": "#6B7280", "AI": "#2563EB"}
REQUIRED_COLUMNS = {
    "participant_number",
    "status",
    "specified_estimated_adjusted_score",
}


def read_scores(path: Path) -> dict[str, list[float]]:
    """Read collected participant scores and group them using participants.py."""

    with path.open(newline="", encoding="utf-8") as file:
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
            if metadata is None:
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
            scores[metadata.phase1_group].append(score)

    for group in GROUPS:
        if not scores[group]:
            raise ValueError(f"No mutation-score values found for {group}")
    return scores


def plot_scores(input_path: Path, output_path: Path) -> None:
    """Create and save the grouped specified mutation-score chart."""

    scores_by_group = read_scores(input_path)
    positions = {group: index for index, group in enumerate(GROUPS)}

    fig, ax = plt.subplots(figsize=(8.5, 6))
    for group in GROUPS:
        scores = scores_by_group[group]
        x = positions[group]
        point_positions = [
            x + (index - (len(scores) - 1) / 2) * 0.055
            for index in range(len(scores))
        ]
        ax.scatter(
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
        ax.scatter(
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
        ax.hlines(
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
        ax.text(
            x + 0.23,
            group_mean + label_offset,
            f"mean {group_mean:.2%}",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )
        ax.text(
            x + 0.23,
            group_median - label_offset,
            f"median {group_median:.2%}",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )

    ax.set_title("Specified Estimated Adjusted Mutation Score by Group")
    ax.set_xlabel("Group")
    ax.set_ylabel("Specified estimated adjusted score")
    ax.set_xticks(list(positions.values()), GROUPS)
    ax.set_xlim(-0.5, 1.5)
    ax.set_ylim(0, 1.05)
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="lower left")
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Plot specified estimated adjusted mutation scores by group."
    )
    parser.add_argument(
        "--input",
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
        "--output",
        type=Path,
        default=(
            repo_root
            / "scripts"
            / "analysis"
            / "outputs"
            / "figures"
            / "specified_estimated_adjusted_score_raw_by_group.png"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    plot_scores(args.input, args.output)
