"""Plot raw generation time for the Phase 1 AI and Manual groups.

Only collected participants defined in ``participants.py`` are included.
Generation time is read from the ``generation_time_seconds`` column.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib.pyplot as plt

try:
    from .participants import PARTICIPANTS_BY_NUMBER
except ImportError:
    from participants import PARTICIPANTS_BY_NUMBER


GROUPS = ("Manual", "AI")
COLORS = {"Manual": "#6B7280", "AI": "#2563EB"}
REQUIRED_COLUMNS = {"participant_number", "status", "generation_time_seconds"}


def read_generation_times(path: Path) -> dict[str, list[float]]:
    """Read collected participant-level generation times in seconds."""

    with path.open(newline="", encoding="utf-8") as file:
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
            if participant in seen_participants:
                raise ValueError(f"Duplicate collected participant: {participant}")
            seen_participants.add(participant)

            generation_time = float(row["generation_time_seconds"])
            if generation_time < 0:
                raise ValueError(
                    f"Generation time for participant {participant} "
                    f"cannot be negative: {generation_time}"
                )
            times[metadata.phase1_group].append(generation_time)

    for group in GROUPS:
        if not times[group]:
            raise ValueError(f"No generation-time values found for {group}")
    return times


def plot_generation_times(input_path: Path, output_path: Path) -> None:
    """Create and save the raw generation-time comparison chart."""

    times_by_group = read_generation_times(input_path)
    positions = {group: index for index, group in enumerate(GROUPS)}

    fig, ax = plt.subplots(figsize=(8.5, 6))
    for group in GROUPS:
        times = times_by_group[group]
        x = positions[group]
        point_positions = [
            x + (index - (len(times) - 1) / 2) * 0.055
            for index in range(len(times))
        ]
        ax.scatter(
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
        ordered_times = sorted(times)
        middle = len(ordered_times) // 2
        median = (
            ordered_times[middle]
            if len(ordered_times) % 2
            else (ordered_times[middle - 1] + ordered_times[middle]) / 2
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
        label_offset = 0.012 * max(times) if abs(mean - median) < 0.025 * max(times) else 0
        ax.text(
            x + 0.23,
            mean + label_offset,
            f"mean {mean:.2f}s",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )
        ax.text(
            x + 0.23,
            median - label_offset,
            f"median {median:.2f}s",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )

    ax.set_title("Raw Generation Time by Group")
    ax.set_xlabel("Group")
    ax.set_ylabel("Generation time (seconds)")
    ax.set_xticks(list(positions.values()), GROUPS)
    ax.set_xlim(-0.5, 1.5)
    ax.set_ylim(0, max(max(times) for times in times_by_group.values()) * 1.05)
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
        description="Plot raw generation time for Manual and AI groups."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=(
            repo_root
            / "results"
            / "phase1"
            / "generation_time"
            / "generation_time.csv"
        ),
        help="Generation-time CSV.",
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
            / "generation_time_raw_by_group.png"
        ),
        help="Output image path.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    plot_generation_times(args.input, args.output)
