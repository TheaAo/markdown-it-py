"""Plot raw assertion scores for the Phase 1 AI and Manual groups.

Assertion score is calculated as:

    non_trivial_test_count / (total_source_tests - invalid_test_count)

Rows whose status is not ``collected`` are ignored.  A zero denominator gives
an assertion score of zero.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

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
    "total_source_tests",
    "invalid_test_count",
    "non_trivial_test_count",
}


def read_assertion_scores(path: Path) -> dict[str, list[float]]:
    """Read collected rows and calculate participant-level assertion scores."""

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

            total_source_tests = int(row["total_source_tests"])
            invalid_test_count = int(row["invalid_test_count"])
            non_trivial_test_count = int(row["non_trivial_test_count"])
            if participant == 8:
                # Manual review reclassified the original uncertain_test_count
                # as one non-trivial test for this participant.
                non_trivial_test_count = 1
            denominator = total_source_tests - invalid_test_count
            score = (
                non_trivial_test_count / denominator if denominator else 0.0
            )
            if not 0 <= score <= 1:
                raise ValueError(
                    f"Assertion score for participant {participant} "
                    f"must be between 0 and 1, got {score}"
                )
            scores[metadata.phase1_group].append(score)

    for group in GROUPS:
        if not scores[group]:
            raise ValueError(f"No assertion-score values found for {group}")
    return scores


def plot_assertion_scores(input_path: Path, output_path: Path) -> None:
    """Create and save the raw assertion-score comparison chart."""

    scores_by_group = read_assertion_scores(input_path)
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

        mean = sum(scores) / len(scores)
        ordered_scores = sorted(scores)
        middle = len(ordered_scores) // 2
        median = (
            ordered_scores[middle]
            if len(ordered_scores) % 2
            else (ordered_scores[middle - 1] + ordered_scores[middle]) / 2
        )
        ax.scatter(
            x,
            mean,
            s=100,
            marker="D",
            facecolors="none",
            edgecolors=COLORS[group],
            linewidth=2,
            label="Mean" if group == GROUPS[0] else None,
            zorder=4,
        )
        ax.hlines(
            median,
            x - 0.2,
            x + 0.2,
            color=COLORS[group],
            linestyle="--",
            linewidth=2,
            label="Median" if group == GROUPS[0] else None,
            zorder=4,
        )
        label_offset = 0.012 if abs(mean - median) < 0.025 else 0
        ax.text(
            x + 0.23,
            mean + label_offset,
            f"mean {mean:.2%}",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )
        ax.text(
            x + 0.23,
            median - label_offset,
            f"median {median:.2%}",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )

    ax.set_title("Raw Assertion Score by Group")
    ax.set_xlabel("Group")
    ax.set_ylabel("Assertion score")
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
        description="Plot raw assertion scores for Manual and AI groups."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            repo_root
            / "results"
            / "phase1"
            / "assertion_score"
            / "assertion_score.csv"
        ),
        help="Assertion-score CSV.",
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
            / "assertion_score_raw_by_group.png"
        ),
        help="Output image path.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    plot_assertion_scores(args.input, args.output)
