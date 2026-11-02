"""Plot Phase 1 execution time by participant group."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from statistics import median

import matplotlib.pyplot as plt

try:
    from .participants import PARTICIPANTS_BY_NUMBER
except ImportError:
    from participants import PARTICIPANTS_BY_NUMBER


GROUPS = ("Manual", "AI")
COLORS = {"Manual": "#6B7280", "AI": "#2563EB"}
REQUIRED_COLUMNS = {"participant_number", "status", "execution_time_seconds"}


def read_execution_times(path: Path) -> dict[str, list[float]]:
    """Read non-empty collected execution times for valid participants."""

    with path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

        times = {group: [] for group in GROUPS}
        seen_participants: set[int] = set()
        for row in reader:
            if row["status"] != "collected":
                continue

            participant = int(row["participant_number"])
            metadata = PARTICIPANTS_BY_NUMBER.get(participant)
            if metadata is None:
                continue

            raw_value = row["execution_time_seconds"].strip()
            if not raw_value:
                continue
            if participant in seen_participants:
                raise ValueError(f"Duplicate execution-time participant: {participant}")
            seen_participants.add(participant)

            value = float(raw_value)
            if value < 0:
                raise ValueError(
                    f"Execution time for participant {participant} cannot be negative: {value}"
                )
            times[metadata.phase1_group].append(value)

    for group in GROUPS:
        if not times[group]:
            raise ValueError(f"No execution-time values found for {group}")
    return times


def _format_value(value: float) -> str:
    """Format values without hiding meaningful precision."""

    return f"{value:.6g}"


def plot_execution_times(input_path: Path, output_path: Path) -> None:
    """Create and save the execution-time comparison chart."""

    times_by_group = read_execution_times(input_path)
    positions = {group: index for index, group in enumerate(GROUPS)}
    figure, axis = plt.subplots(figsize=(8.5, 6))

    for group in GROUPS:
        times = times_by_group[group]
        x = positions[group]
        point_positions = [
            x + (index - (len(times) - 1) / 2) * 0.055
            for index in range(len(times))
        ]
        axis.scatter(
            point_positions,
            times,
            s=70,
            color=COLORS[group],
            edgecolor="white",
            linewidth=0.8,
            alpha=0.9,
            label=f"{group} raw data",
            zorder=3,
        )

        mean = sum(times) / len(times)
        group_median = median(times)
        axis.scatter(
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

        scale = max(times)
        label_offset = 0.012 * scale if abs(mean - group_median) < 0.025 * scale else 0
        axis.text(
            x + 0.23,
            mean - label_offset if mean < group_median else mean + label_offset,
            f"mean {_format_value(mean)} s",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )
        axis.text(
            x + 0.23,
            group_median + label_offset if mean < group_median else group_median - label_offset,
            f"median {_format_value(group_median)} s",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )

    axis.set_title("Execution Time by Group")
    axis.set_xlabel("Group")
    axis.set_ylabel("Execution time (seconds)")
    axis.set_xticks(list(positions.values()), GROUPS)
    axis.set_xlim(-0.5, 1.5)
    maximum = max(max(times) for times in times_by_group.values())
    axis.set_ylim(0, maximum * 1.1 if maximum else 1)
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
    parser = argparse.ArgumentParser(description="Plot Phase 1 execution time by group.")
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            repo_root
            / "results"
            / "phase1"
            / "execution_time"
            / "formal"
            / "summary"
            / "execution_time.csv"
        ),
        help="Execution-time summary CSV.",
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
            / "execution_time_by_group.png"
        ),
        help="Output image path.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    plot_execution_times(arguments.input, arguments.output)
