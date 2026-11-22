"""Plot paired Phase 1 and Phase 2 test-smell-density distributions."""

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


SEQUENCE_COLORS = {
    "Manual → AI": "#0072B2",
    "AI → AI": "#D55E00",
}
GROUP_X_OFFSET = {
    "Manual → AI": -0.07,
    "AI → AI": 0.07,
}
REQUIRED_COLUMNS = {"participant_number", "status", "test_smell_density"}


def read_test_smell_density(path: Path) -> dict[int, dict[str, float | str]]:
    """Read collected non-missing test-smell densities by participant ID."""

    values: dict[int, dict[str, float | str]] = {}
    seen: set[int] = set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

        for row in reader:
            if row["status"].strip() != "collected":
                continue

            participant = int(row["participant_number"])
            participant_metadata = PARTICIPANTS_BY_NUMBER.get(participant)
            if participant_metadata is None:
                continue
            if participant in seen:
                raise ValueError(f"Duplicate participant: {participant}")

            seen.add(participant)
            raw_value = row["test_smell_density"].strip()
            if not raw_value:
                continue
            density = float(raw_value)
            if not 0 <= density <= 1:
                raise ValueError(
                    f"Test smell density for participant {participant} "
                    f"must be between 0 and 1, got {density}"
                )

            sequence = (
                "Manual → AI"
                if participant_metadata.phase1_group == "Manual"
                else "AI → AI"
            )
            values[participant] = {"sequence": sequence, "density": density}

    return values


def read_phase2_test_smell_density(path: Path) -> dict[int, dict[str, float | str]]:
    """Read Phase 2 densities and retain only participating participant IDs."""

    values = read_test_smell_density(path)
    return {
        participant: participant_values
        for participant, participant_values in values.items()
        if PARTICIPANTS_BY_NUMBER[participant].participated_in_phase2
    }


def build_participant_x_offsets() -> dict[int, float]:
    """Return deterministic horizontal offsets shared across both phases."""

    ids_by_sequence: dict[str, list[int]] = {
        "Manual → AI": [],
        "AI → AI": [],
    }
    for participant_number, participant in PARTICIPANTS_BY_NUMBER.items():
        sequence = "Manual → AI" if participant.phase1_group == "Manual" else "AI → AI"
        ids_by_sequence[sequence].append(participant_number)

    offsets: dict[int, float] = {}
    for participant_ids in ids_by_sequence.values():
        participant_ids.sort()
        for rank, participant_number in enumerate(participant_ids):
            offsets[participant_number] = (
                rank - (len(participant_ids) - 1) / 2
            ) * 0.022
    return offsets


def density_y_limits(values: list[float]) -> tuple[float, float]:
    """Choose a focused range while retaining every observation."""

    if not values:
        return (0.0, 0.32)
    minimum = min(values)
    maximum = max(values)
    padding = max((maximum - minimum) * 0.12, 0.02)
    lower = max(0.0, minimum - padding)
    upper = min(1.0, max(0.32, maximum + padding))
    return lower, upper


def plot_cross_phase_test_smell_density(
    phase1_path: Path,
    phase2_path: Path,
    output_path: Path,
) -> None:
    """Create a paired scatter-and-line plot for test-smell density."""

    phase1 = read_test_smell_density(phase1_path)
    phase2 = read_phase2_test_smell_density(phase2_path)
    participant_offsets = build_participant_x_offsets()

    figure, axis = plt.subplots(figsize=(7.2, 4.2))
    all_densities = [
        float(values["density"])
        for values in list(phase1.values()) + list(phase2.values())
    ]

    for participant, phase1_values in phase1.items():
        sequence = str(phase1_values["sequence"])
        offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
        axis.scatter(
            0 + offset,
            float(phase1_values["density"]),
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
            (float(phase1_values["density"]), float(phase2_values["density"])),
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
            float(phase2_values["density"]),
            s=64,
            color=SEQUENCE_COLORS[sequence],
            edgecolor="white",
            linewidth=0.7,
            alpha=0.92,
            zorder=3,
        )

    axis.set_xticks([0, 1], ["Phase 1", "Phase 2"])
    axis.set_xlim(-0.23, 1.23)
    axis.set_ylim(*density_y_limits(all_densities))
    axis.yaxis.set_major_locator(MultipleLocator(0.05))
    axis.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
    axis.set_ylabel("Test Smell Density (%)", fontsize=16)
    axis.set_xlabel("", fontsize=16)
    axis.set_title("Test Smell Density", fontsize=18)
    axis.grid(axis="y", linestyle="-", linewidth=0.7, alpha=0.30)
    axis.set_axisbelow(True)
    axis.tick_params(axis="both", which="major", labelsize=15)
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

    figure.subplots_adjust(left=0.11, right=0.99, bottom=0.18, top=0.93)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, bbox_inches="tight")
    plt.close(figure)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Plot paired cross-phase test-smell-density distributions."
    )
    parser.add_argument(
        "--phase1",
        type=Path,
        default=(
            REPO_ROOT
            / "results"
            / "phase1"
            / "test_smells"
            / "summary"
            / "test_smell.csv"
        ),
    )
    parser.add_argument(
        "--phase2",
        type=Path,
        default=(
            REPO_ROOT
            / "results"
            / "phase2"
            / "test_smells"
            / "summary"
            / "test_smell.csv"
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            REPO_ROOT
            / "scripts"
            / "analysis"
            / "outputs"
            / "figures"
            / "cross_phase_test_smell_density.pdf"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    plot_cross_phase_test_smell_density(arguments.phase1, arguments.phase2, arguments.output)
