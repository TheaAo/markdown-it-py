"""Plot paired cross-phase execution-efficiency distributions."""

from __future__ import annotations

import argparse
import csv
import statistics
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
EFFICIENCY_METRICS = (
    ("statement_execution_efficiency_per_second", "Statement Coverage"),
    ("branch_execution_efficiency_per_second", "Branch Coverage"),
    ("mutation_execution_efficiency_per_second", "Mutation Score"),
)


def read_phase1_efficiency(path: Path) -> dict[int, dict[str, float | str]]:
    """Read Phase 1 execution efficiency, excluding Participant 6."""

    values: dict[int, dict[str, float | str]] = {}
    seen: set[int] = set()
    required = {
        "participant_number",
        "status",
        "valid_tests_included",
        *(column for column, _ in EFFICIENCY_METRICS),
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
            if int(row["valid_tests_included"]) == 0:
                continue
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

            for column, _ in EFFICIENCY_METRICS:
                raw_value = row[column].strip()
                if not raw_value:
                    efficiency = 0.0 if participant == 4 else -1.0
                else:
                    efficiency = float(raw_value)
                if efficiency < 0:
                    raise ValueError(
                        f"Missing Phase 1 {column} for participant {participant}"
                    )
                participant_values[column] = efficiency

            values[participant] = participant_values

    return values


def read_phase2_efficiency(path: Path) -> dict[int, dict[str, float | str]]:
    """Read collected Phase 2 execution efficiency by participant ID."""

    values: dict[int, dict[str, float | str]] = {}
    seen: set[int] = set()
    required = {
        "participant_number",
        "efficiency_status",
        "valid_tests_included",
        *(column for column, _ in EFFICIENCY_METRICS),
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
            if int(row["valid_tests_included"]) == 0:
                continue
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

            for column, _ in EFFICIENCY_METRICS:
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
    return (0.0, maximum * 1.12)


def find_excluded_participants(path: Path) -> list[tuple[int, int]]:
    """Return collected participants with no valid tests."""

    excluded: list[tuple[int, int]] = []
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        for row in reader:
            status_column = (
                "status"
                if "status" in (reader.fieldnames or ())
                else "efficiency_status"
            )
            collected_status = "collected"
            if row[status_column].strip() != collected_status:
                continue
            valid_test_count = int(row["valid_tests_included"])
            if valid_test_count == 0:
                excluded.append((int(row["participant_number"]), valid_test_count))
    return excluded


def print_group_statistics(
    phase_name: str,
    values: dict[int, dict[str, float | str]],
) -> None:
    """Print mean, median, and sample SD in percent per millisecond."""

    print(f"\n{phase_name} execution-efficiency statistics (%/ms)")
    print("| Group | n | Metric | Mean | Median | SD |")
    print("|---|---:|---|---:|---:|---:|")

    for sequence in ("Manual → AI", "AI → AI"):
        group = "Manual" if sequence == "Manual → AI" else "AI"
        participants = [
            participant_values
            for participant_values in values.values()
            if participant_values["sequence"] == sequence
        ]
        for metric, full_label in EFFICIENCY_METRICS:
            metric_values = [
                float(participant_values[metric]) / 10
                for participant_values in participants
                if metric in participant_values
            ]
            if not metric_values:
                continue
            print(
                f"| {group} | {len(metric_values)} | {full_label} | "
                f"{statistics.mean(metric_values):.9f} | "
                f"{statistics.median(metric_values):.9f} | "
                f"{statistics.stdev(metric_values):.9f} |"
            )


def plot_cross_phase_execution_efficiency(
    phase1_path: Path,
    phase2_path: Path,
    output_path: Path,
) -> None:
    """Create three side-by-side paired execution-efficiency plots."""

    phase1 = read_phase1_efficiency(phase1_path)
    phase2 = read_phase2_efficiency(phase2_path)
    participant_offsets = build_participant_x_offsets()

    excluded_phase1 = find_excluded_participants(phase1_path)
    excluded_phase2 = find_excluded_participants(phase2_path)
    print(
        "Excluded Phase 1 participants with no valid tests: "
        + (
            ", ".join(
                f"{participant} (valid_tests_included={count})"
                for participant, count in excluded_phase1
            )
            if excluded_phase1
            else "none"
        )
    )
    print(
        "Excluded Phase 2 participants with no valid tests: "
        + (
            ", ".join(
                f"{participant} (valid_tests_included={count})"
                for participant, count in excluded_phase2
            )
            if excluded_phase2
            else "none"
        )
    )
    print_group_statistics("Phase 1", phase1)
    print_group_statistics("Phase 2", phase2)

    figure, axes = plt.subplots(1, 3, figsize=(11.2, 4.2), sharey=False)

    for axis, (metric, full_label) in zip(axes, EFFICIENCY_METRICS):
        all_values: list[float] = []

        for participant, phase1_values in phase1.items():
            sequence = str(phase1_values["sequence"])
            offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
            # Values are proportion/second; convert to percentage-points/millisecond.
            value = float(phase1_values[metric]) * 0.1
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
            sequence = str(phase1_values["sequence"])
            offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
            axis.plot(
                (0 + offset, 1 + offset),
                (
                    float(phase1_values[metric]) * 0.1,
                    float(phase2_values[metric]) * 0.1,
                ),
                color=SEQUENCE_COLORS[sequence],
                linewidth=1.0,
                alpha=0.38,
                zorder=1,
            )

        for participant, phase2_values in phase2.items():
            sequence = str(phase2_values["sequence"])
            offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
            value = float(phase2_values[metric]) * 0.1
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
        _, upper = efficiency_y_limits(all_values)
        axis.set_ylim(0, upper)
        axis.tick_params(axis="both", which="major", labelsize=15)
        axis.grid(axis="y", linestyle="-", linewidth=0.7, alpha=0.30)
        axis.set_axisbelow(True)
        axis.set_title(full_label, fontsize=16, pad=22)
        axis.set_xlabel("", fontsize=16)
        for spine in axis.spines.values():
            spine.set_visible(False)

    axes[0].set_ylabel("Execution efficiency (pp/ms)", fontsize=16)

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

    figure.suptitle("Execution Efficiency", fontsize=20, y=0.995)
    figure.subplots_adjust(left=0.09, right=0.99, bottom=0.18, top=0.76, wspace=0.32)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, bbox_inches="tight")
    plt.close(figure)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Plot paired cross-phase execution-efficiency distributions."
    )
    parser.add_argument(
        "--phase1",
        type=Path,
        default=(
            REPO_ROOT
            / "results"
            / "phase1"
            / "execution_time"
            / "execution_efficiency.csv"
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
            / "execution_efficiency.csv"
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
            / "cross_phase_execution_efficiency.pdf"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    plot_cross_phase_execution_efficiency(arguments.phase1, arguments.phase2, arguments.output)
