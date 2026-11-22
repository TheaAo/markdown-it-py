"""Plot paired Phase 1 and Phase 2 statement and branch coverage distributions.

Phase 1 participants are grouped according to their initial assignment:
Manual -> AI and AI -> AI.  The same grouping is retained in Phase 2, and
observations are matched by participant number rather than dataframe row.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator, PercentFormatter

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from scripts.analysis.participants import PARTICIPANTS_BY_NUMBER
except ImportError:
    from ..participants import PARTICIPANTS_BY_NUMBER


SEQUENCE_COLORS = {
    "Manual → AI": "#0072B2",
    "AI → AI": "#D55E00",
}
GROUP_X_OFFSET = {
    "Manual → AI": -0.07,
    "AI → AI": 0.07,
}
COVERAGE_METRICS = (
    ("participant_statement_coverage", "Statement Coverage"),
    ("participant_branch_coverage", "Branch Coverage"),
)


def read_phase1_coverage(path: Path) -> dict[int, dict[str, float]]:
    """Read Phase 1 coverage, using the established missing-value rules."""

    phase1: dict[int, dict[str, float]] = {}
    seen: set[int] = set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required = {
            "participant_number",
            "status",
            *(column for column, _ in COVERAGE_METRICS),
        }
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

        for row in reader:
            if row["status"].strip() != "collected":
                continue

            participant = int(row["participant_number"])
            if participant == 6:
                continue
            if participant in seen:
                raise ValueError(f"Duplicate Phase 1 participant: {participant}")

            participant_metadata = PARTICIPANTS_BY_NUMBER.get(participant)
            if participant_metadata is None:
                continue

            seen.add(participant)
            sequence = (
                "Manual → AI"
                if participant_metadata.phase1_group == "Manual"
                else "AI → AI"
            )
            values: dict[str, float] = {"sequence": sequence}  # type: ignore[dict-item]
            for column, _ in COVERAGE_METRICS:
                raw_value = row[column].strip()
                if not raw_value:
                    if participant == 4:
                        coverage = 0.0
                    else:
                        raise ValueError(
                            f"Missing Phase 1 {column} for participant {participant}"
                        )
                else:
                    coverage = float(raw_value)
                if not 0 <= coverage <= 1:
                    raise ValueError(
                        f"Phase 1 {column} for participant {participant} "
                        f"must be between 0 and 1, got {coverage}"
                    )
                values[column] = coverage
            phase1[participant] = values

    return phase1


def read_phase2_coverage(path: Path) -> dict[int, dict[str, float]]:
    """Read collected Phase 2 coverage and match it to participant metadata."""

    phase2: dict[int, dict[str, float]] = {}
    seen: set[int] = set()
    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        required = {
            "participant_number",
            "status",
            *(column for column, _ in COVERAGE_METRICS),
        }
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

        for row in reader:
            if row["status"].strip() != "collected":
                continue

            participant = int(row["participant_number"])
            if participant in seen:
                raise ValueError(f"Duplicate Phase 2 participant: {participant}")

            participant_metadata = PARTICIPANTS_BY_NUMBER.get(participant)
            if participant_metadata is None:
                continue
            if not participant_metadata.participated_in_phase2:
                continue

            seen.add(participant)
            sequence = (
                "Manual → AI"
                if participant_metadata.phase1_group == "Manual"
                else "AI → AI"
            )
            values: dict[str, float] = {"sequence": sequence}  # type: ignore[dict-item]
            for column, _ in COVERAGE_METRICS:
                raw_value = row[column].strip()
                if not raw_value:
                    continue
                coverage = float(raw_value)
                if not 0 <= coverage <= 1:
                    raise ValueError(
                        f"Phase 2 {column} for participant {participant} "
                        f"must be between 0 and 1, got {coverage}"
                    )
                values[column] = coverage
            phase2[participant] = values

    return phase2


def build_participant_x_offsets() -> dict[int, float]:
    """Return one stable horizontal offset per participant within its sequence."""

    participant_ids_by_sequence: dict[str, list[int]] = {
        "Manual → AI": [],
        "AI → AI": [],
    }
    for participant_number, participant in PARTICIPANTS_BY_NUMBER.items():
        sequence = "Manual → AI" if participant.phase1_group == "Manual" else "AI → AI"
        participant_ids_by_sequence[sequence].append(participant_number)

    offsets: dict[int, float] = {}
    for sequence, participant_ids in participant_ids_by_sequence.items():
        participant_ids.sort()
        for rank, participant_number in enumerate(participant_ids):
            offsets[participant_number] = (
                rank - (len(participant_ids) - 1) / 2
            ) * 0.022
    return offsets


def coverage_y_limits(values: list[float]) -> tuple[float, float]:
    """Use a focused percentage range while retaining every observed value."""

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


def plot_cross_phase_coverage(
    phase1_path: Path,
    phase2_path: Path,
    output_path: Path,
) -> None:
    """Create paired scatter-and-line plots for Statement and Branch Coverage."""

    phase1 = read_phase1_coverage(phase1_path)
    phase2 = read_phase2_coverage(phase2_path)
    participant_offsets = build_participant_x_offsets()

    figure, axes = plt.subplots(1, 2, figsize=(11.2, 4.2), sharey=False)

    for axis, (coverage_column, coverage_label) in zip(axes, COVERAGE_METRICS):
        all_values: list[float] = []

        for participant, phase1_values in phase1.items():
            if coverage_column not in phase1_values:
                continue
            sequence = str(phase1_values["sequence"])
            value = phase1_values[coverage_column]
            all_values.append(value)
            offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
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
            if coverage_column not in phase1_values or coverage_column not in phase2_values:
                continue
            sequence = str(phase1_values["sequence"])
            offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
            axis.plot(
                (0 + offset, 1 + offset),
                (phase1_values[coverage_column], phase2_values[coverage_column]),
                color=SEQUENCE_COLORS[sequence],
                linewidth=1.0,
                alpha=0.38,
                zorder=1,
            )

        for participant, phase2_values in phase2.items():
            if coverage_column not in phase2_values:
                continue
            sequence = str(phase2_values["sequence"])
            offset = GROUP_X_OFFSET[sequence] + participant_offsets[participant]
            value = phase2_values[coverage_column]
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
        lower, upper = coverage_y_limits(all_values)
        axis.set_ylim(lower, upper)
        axis.yaxis.set_major_locator(MultipleLocator(0.20))
        axis.yaxis.set_minor_locator(MultipleLocator(0.10))
        axis.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        axis.set_ylabel("Coverage (%)", fontsize=16)
        axis.set_xlabel("", fontsize=16)
        axis.set_title(coverage_label, fontsize=18)
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

    figure.subplots_adjust(left=0.07, right=0.99, bottom=0.16, top=0.96, wspace=0.18)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, bbox_inches="tight")
    plt.close(figure)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = REPO_ROOT
    parser = argparse.ArgumentParser(
        description="Plot paired cross-phase Statement and Branch Coverage distributions."
    )
    parser.add_argument(
        "--phase1",
        type=Path,
        default=repo_root / "results" / "phase1" / "coverage" / "coverage.csv",
    )
    parser.add_argument(
        "--phase2",
        type=Path,
        default=repo_root / "results" / "phase2" / "coverage" / "coverage.csv",
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
            / "cross_phase_coverage.pdf"
        ),
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    plot_cross_phase_coverage(arguments.phase1, arguments.phase2, arguments.output)
