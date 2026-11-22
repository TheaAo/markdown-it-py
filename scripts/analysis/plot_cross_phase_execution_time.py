"""Plot paired Phase 1 and Phase 2 execution-time distributions."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

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
REQUIRED_COLUMNS = {"participant_number", "status", "execution_time_seconds"}


def read_execution_times(path: Path) -> dict[int, dict[str, float | str]]:
    """Read collected, non-empty execution times and match by participant ID."""

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

            raw_value = row["execution_time_seconds"].strip()
            if not raw_value:
                continue
            if participant in seen:
                raise ValueError(f"Duplicate execution-time participant: {participant}")

            seen.add(participant)
            execution_time = float(raw_value)
            if execution_time < 0:
                raise ValueError(
                    f"Execution time for participant {participant} cannot be negative: {execution_time}"
                )

            sequence = (
                "Manual → AI"
                if participant_metadata.phase1_group == "Manual"
                else "AI → AI"
            )
            values[participant] = {"sequence": sequence, "time": execution_time}

    return values


def read_phase2_execution_times(path: Path) -> dict[int, dict[str, float | str]]:
    """Read Phase 2 values and retain only Phase 2 participants."""

    values = read_execution_times(path)
    return {
        participant: participant_values
        for participant, participant_values in values.items()
        if PARTICIPANTS_BY_NUMBER[participant].participated_in_phase2
    }


def build_participant_x_offsets() -> dict[int, float]:
    """Return deterministic horizontal offsets shared across phases."""

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


def time_y_limits(values: list[float]) -> tuple[float, float]:
    """Choose a focused range while retaining every observation."""

    if not values:
        return (0.0, 1.0)
    maximum = max(values)
    padding = max(maximum * 0.06, 20.0)
    return (0.0, maximum + padding)


def plot_cross_phase_execution_time(
    phase1_path: Path,
    phase2_path: Path,
    output_path: Path,
) -> None:
    """Create a paired scatter-and-line plot for cross-phase execution time."""

    phase1 = read_execution_times(phase1_path)
    phase2 = read_phase2_execution_times(phase2_path)
    participant_offsets = build_participant_x_offsets()

    figure, axis = plt.subplots(figsize=(7.2, 4.2))
    all_times: list[float] = []

    for participant, phase1_values in phase1.items():
        sequence = str(phase1_values["sequence"])
        offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
        value_ms = float(phase1_values["time"]) * 1000
        all_times.append(value_ms)
        axis.scatter(
            0 + offset,
            value_ms,
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
            (
                float(phase1_values["time"]) * 1000,
                float(phase2_values["time"]) * 1000,
            ),
            color=SEQUENCE_COLORS[sequence],
            linewidth=1.0,
            alpha=0.38,
            zorder=1,
        )

    for participant, phase2_values in phase2.items():
        sequence = str(phase2_values["sequence"])
        offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
        value_ms = float(phase2_values["time"]) * 1000
        all_times.append(value_ms)
        axis.scatter(
            1 + offset,
            value_ms,
            s=64,
            color=SEQUENCE_COLORS[sequence],
            edgecolor="white",
            linewidth=0.7,
            alpha=0.92,
            zorder=3,
        )

    axis.set_xticks([0, 1], ["Phase 1", "Phase 2"])
    axis.set_xlim(-0.23, 1.23)
    axis.set_ylim(*time_y_limits(all_times))
    axis.tick_params(axis="both", which="major", labelsize=15)
    axis.grid(axis="y", linestyle="-", linewidth=0.7, alpha=0.30)
    axis.set_axisbelow(True)
    axis.set_ylabel("Execution Time (ms)", fontsize=16)
    axis.set_xlabel("", fontsize=16)
    axis.set_title("Execution Time", fontsize=18)
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
        description="Plot paired cross-phase execution-time distributions."
    )
    parser.add_argument(
        "--phase1",
        type=Path,
        default=(
            REPO_ROOT
            / "results"
            / "phase1"
            / "execution_time"
            / "formal"
            / "summary"
            / "execution_time.csv"
        ),
    )
    parser.add_argument(
        "--phase2",
        type=Path,
        default=(
            REPO_ROOT
            / "results"
            / "phase2"
            / "execution_time"
            / "formal"
            / "summary"
            / "execution_time.csv"
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
            / "cross_phase_execution_time.pdf"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    plot_cross_phase_execution_time(arguments.phase1, arguments.phase2, arguments.output)
