"""Plot Phase 2 test smell density by the participants' Phase 1 groups.

Test smell density is read from the collected test-smell summary:

    confirmed_pair_count / (eligible_test_count * 7)

Rows whose status is not ``collected`` are ignored. All Phase 2 participants
had eligible source test functions; a blank density would still be skipped.
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


GROUPS = ("Manual-AI", "AI-AI")
COLORS = {"Manual-AI": "#6B7280", "AI-AI": "#2563EB"}
REQUIRED_COLUMNS = {"participant_number", "status", "test_smell_density"}
# Shared with the Phase 1 plot so that both panels use the same vertical scale.
Y_MAX = 0.32


def read_test_smell_density(path: Path) -> dict[str, list[float]]:
    """Read collected Phase 2 densities grouped by Phase 1 assignment."""

    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

        densities = {group: [] for group in GROUPS}
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

            raw_value = row["test_smell_density"].strip()
            if not raw_value:
                # No eligible source functions: missing in the primary analysis.
                continue
            density = float(raw_value)
            if not 0 <= density <= 1:
                raise ValueError(
                    f"Test smell density for participant {participant} "
                    f"must be between 0 and 1, got {density}"
                )
            group = "AI-AI" if metadata.phase1_group == "AI" else "Manual-AI"
            densities[group].append(density)

    for group in GROUPS:
        if not densities[group]:
            raise ValueError(f"No test-smell-density values found for {group}")
    return densities


def plot_test_smell_density(input_path: Path, output_path: Path) -> None:
    """Create and save the Phase 2 test-smell-density comparison chart."""

    densities_by_group = read_test_smell_density(input_path)
    positions = {group: index for index, group in enumerate(GROUPS)}

    fig, ax = plt.subplots(figsize=(8.5, 6))
    for group in GROUPS:
        densities = densities_by_group[group]
        x = positions[group]
        point_positions = [
            x + (index - (len(densities) - 1) / 2) * 0.055
            for index in range(len(densities))
        ]
        ax.scatter(
            point_positions,
            densities,
            s=70,
            color=COLORS[group],
            edgecolor="white",
            linewidth=0.8,
            alpha=0.9,
            label=f"{group} raw data",
            zorder=3,
        )

        mean = sum(densities) / len(densities)
        ordered = sorted(densities)
        middle = len(ordered) // 2
        median = (
            ordered[middle]
            if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / 2
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
        label_offset = 0.012 * Y_MAX if abs(mean - median) < 0.025 * Y_MAX else 0
        mean_label_y = mean - label_offset if mean < median else mean + label_offset
        median_label_y = (
            median + label_offset if mean < median else median - label_offset
        )
        ax.text(
            x + 0.23,
            mean_label_y,
            f"mean {mean:.2%}",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )
        ax.text(
            x + 0.23,
            median_label_y,
            f"median {median:.2%}",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )

    ax.set_title("Phase 2 Test Smell Density by Phase 1 Group")
    ax.set_xlabel("Group")
    ax.set_ylabel("Test smell density")
    ax.set_xticks(list(positions.values()), GROUPS)
    ax.set_xlim(-0.5, 1.5)
    ax.set_ylim(0, Y_MAX)
    ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="upper right")
    fig.tight_layout()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Plot Phase 2 test smell density by Phase 1 group."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            repo_root
            / "results"
            / "phase2"
            / "test_smells"
            / "summary"
            / "test_smell.csv"
        ),
        help="Phase 2 test-smell summary CSV.",
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
            / "phase2_test_smell_density_raw_by_group.png"
        ),
        help="Output image path.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    plot_test_smell_density(args.input, args.output)
