"""Plot paired cross-phase generation-efficiency distributions.

Three efficiency metrics are shown side by side:
statement generation efficiency, branch generation efficiency, and mutation
generation efficiency. Observations are matched by participant number.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FormatStrFormatter

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
EFFICIENCY_METRICS = (
    ("statement_generation_efficiency_per_second", "Statement", "Statement Coverage"),
    ("branch_generation_efficiency_per_second", "Branch", "Branch Coverage"),
    ("mutation_generation_efficiency_per_second", "Mutation", "Mutation Score"),
)


def read_phase1_efficiency(path: Path) -> dict[int, dict[str, float | str]]:
    """Read Phase 1 generation-efficiency values by participant ID."""

    values: dict[int, dict[str, float | str]] = {}
    seen: set[int] = set()
    required = {
        "participant_number",
        "status",
        *(column for column, _, _ in EFFICIENCY_METRICS),
    }

    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        missing = required - set(reader.fieldnames or ())
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
                raise ValueError(f"Duplicate Phase 1 participant: {participant}")

            seen.add(participant)
            sequence = (
                "Manual → AI"
                if participant_metadata.phase1_group == "Manual"
                else "AI → AI"
            )
            participant_values: dict[str, float | str] = {"sequence": sequence}

            for column, _, _ in EFFICIENCY_METRICS:
                raw_value = row[column].strip()
                if not raw_value:
                    if participant == 4:
                        efficiency = 0.0
                    else:
                        raise ValueError(
                            f"Missing Phase 1 {column} for participant {participant}"
                        )
                else:
                    efficiency = float(raw_value)
                if efficiency < 0:
                    raise ValueError(
                        f"Phase 1 {column} for participant {participant} cannot be negative"
                    )
                participant_values[column] = efficiency

            values[participant] = participant_values

    return values


def read_phase2_efficiency(path: Path) -> dict[int, dict[str, float | str]]:
    """Read collected Phase 2 generation-efficiency values by participant ID."""

    values: dict[int, dict[str, float | str]] = {}
    seen: set[int] = set()
    required = {
        "participant_number",
        "efficiency_status",
        *(column for column, _, _ in EFFICIENCY_METRICS),
    }

    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

        for row in reader:
            if row["efficiency_status"].strip() != "collected":
                continue

            participant = int(row["participant_number"])
            participant_metadata = PARTICIPANTS_BY_NUMBER.get(participant)
            if participant_metadata is None or not participant_metadata.participated_in_phase2:
                continue
            if participant in seen:
                raise ValueError(f"Duplicate Phase 2 participant: {participant}")

            seen.add(participant)
            sequence = (
                "Manual → AI"
                if participant_metadata.phase1_group == "Manual"
                else "AI → AI"
            )
            participant_values: dict[str, float | str] = {"sequence": sequence}

            for column, _, _ in EFFICIENCY_METRICS:
                raw_value = row[column].strip()
                if not raw_value:
                    raise ValueError(
                        f"Missing Phase 2 {column} for participant {participant}"
                    )
                efficiency = float(raw_value)
                if efficiency < 0:
                    raise ValueError(
                        f"Phase 2 {column} for participant {participant} cannot be negative"
                    )
                participant_values[column] = efficiency

            values[participant] = participant_values

    return values


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


def efficiency_y_limits(values: list[float]) -> tuple[float, float]:
    """Choose a focused range while retaining every observation."""

    if not values:
        return (0.0, 1.0)
    maximum = max(values)
    if maximum <= 0:
        return (0.0, 0.001)
    upper = maximum * 1.12
    return (0.0, upper)


def plot_cross_phase_generation_efficiency(
    phase1_path: Path,
    phase2_path: Path,
    output_path: Path,
) -> None:
    """Create three side-by-side paired generation-efficiency plots."""

    phase1 = read_phase1_efficiency(phase1_path)
    phase2 = read_phase2_efficiency(phase2_path)
    participant_offsets = build_participant_x_offsets()

    figure, axes = plt.subplots(1, 3, figsize=(11.2, 4.2), sharey=False)

    for axis, (metric, short_label, full_label) in zip(axes, EFFICIENCY_METRICS):
        all_values: list[float] = []

        for participant, phase1_values in phase1.items():
            if metric not in phase1_values:
                continue
            sequence = str(phase1_values["sequence"])
            offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
            value = float(phase1_values[metric]) * 100
            all_values.append(value)
            axis.scatter(
                0 + offset,
                value,
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
            if metric not in phase1_values or metric not in phase2_values:
                continue
            sequence = str(phase1_values["sequence"])
            offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
            axis.plot(
                (0 + offset, 1 + offset),
                (
                    float(phase1_values[metric]) * 100,
                    float(phase2_values[metric]) * 100,
                ),
                color=SEQUENCE_COLORS[sequence],
                linewidth=1.0,
                alpha=0.38,
                zorder=1,
            )

        for participant, phase2_values in phase2.items():
            if metric not in phase2_values:
                continue
            sequence = str(phase2_values["sequence"])
            offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
            value = float(phase2_values[metric]) * 100
            all_values.append(value)
            axis.scatter(
                1 + offset,
                value,
                s=64,
                color=SEQUENCE_COLORS[sequence],
                edgecolor="white",
                linewidth=0.7,
                alpha=0.92,
                zorder=3,
            )

        axis.set_xticks([0, 1], ["Phase 1", "Phase 2"])
        axis.set_xlim(-0.23, 1.23)
        _, upper_scaled = efficiency_y_limits([value / 100 for value in all_values])
        axis.set_ylim(0, upper_scaled * 100)
        axis.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
        axis.tick_params(axis="both", which="major", labelsize=15)
        axis.grid(axis="y", linestyle="-", linewidth=0.7, alpha=0.30)
        axis.set_axisbelow(True)
        axis.set_title(full_label, fontsize=16, pad=22)
        axis.set_xlabel("", fontsize=16)
        for spine in axis.spines.values():
            spine.set_visible(False)

    axes[0].set_ylabel("Generation efficiency (pp/s)", fontsize=16)

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

    figure.suptitle("Generation Efficiency", fontsize=20, y=0.995)
    figure.subplots_adjust(left=0.09, right=0.99, bottom=0.18, top=0.76, wspace=0.32)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, bbox_inches="tight")
    plt.close(figure)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Plot paired cross-phase generation-efficiency distributions."
    )
    parser.add_argument(
        "--phase1",
        type=Path,
        default=(
            REPO_ROOT
            / "results"
            / "phase1"
            / "generation_time"
            / "generation_efficiency.csv"
        ),
    )
    parser.add_argument(
        "--phase2",
        type=Path,
        default=(
            REPO_ROOT
            / "results"
            / "phase2"
            / "efficiency"
            / "generation_efficiency.csv"
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
            / "cross_phase_generation_efficiency.pdf"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    plot_cross_phase_generation_efficiency(arguments.phase1, arguments.phase2, arguments.output)
