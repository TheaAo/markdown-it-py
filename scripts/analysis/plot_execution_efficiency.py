"""Plot Phase 2 execution-efficiency metrics by participant group."""

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


GROUPS = ("Manual-AI", "AI-AI")
COLORS = {"Manual-AI": "#6B7280", "AI-AI": "#2563EB"}
METRICS = {
    "statement_execution_efficiency_per_second": (
        "Statement execution efficiency",
        "Coverage per second",
        "phase2_statement_execution_efficiency_raw_by_group.png",
    ),
    "branch_execution_efficiency_per_second": (
        "Branch execution efficiency",
        "Coverage per second",
        "phase2_branch_execution_efficiency_raw_by_group.png",
    ),
    "mutation_execution_efficiency_per_second": (
        "Mutation execution efficiency",
        "Score per second",
        "phase2_mutation_execution_efficiency_raw_by_group.png",
    ),
}
REQUIRED_COLUMNS = {"participant_number", "efficiency_status", *METRICS}


def read_efficiency_values(path: Path, metric: str) -> dict[str, list[float]]:
    """Read collected values, treating blank metric fields as zero."""

    values = {group: [] for group in GROUPS}
    seen_participants: set[int] = set()
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing required columns: {sorted(missing)}")

        for row in reader:
            if row["efficiency_status"] != "collected":
                continue
            participant = int(row["participant_number"])
            metadata = PARTICIPANTS_BY_NUMBER.get(participant)
            if metadata is None or not metadata.participated_in_phase2:
                continue
            if participant in seen_participants:
                raise ValueError(f"Duplicate collected participant: {participant}")
            seen_participants.add(participant)

            raw_value = row[metric].strip()
            value = float(raw_value) if raw_value else 0.0
            if value < 0:
                raise ValueError(
                    f"{metric} for participant {participant} cannot be negative: {value}"
                )
            group = "AI-AI" if metadata.phase1_group == "AI" else "Manual-AI"
            values[group].append(value)

    for group in GROUPS:
        if not values[group]:
            raise ValueError(f"No {metric} values found for {group}")
    return values


def _format_value(value: float) -> str:
    """Format efficiency values compactly."""

    return f"{value:.3g}"


def plot_metric(
    values_by_group: dict[str, list[float]],
    title: str,
    y_label: str,
    output_path: Path,
) -> None:
    """Create and save one execution-efficiency comparison chart."""

    positions = {group: index for index, group in enumerate(GROUPS)}
    fig, ax = plt.subplots(figsize=(8.5, 6))
    for group in GROUPS:
        values = values_by_group[group]
        x = positions[group]
        point_positions = [
            x + (index - (len(values) - 1) / 2) * 0.055
            for index in range(len(values))
        ]
        ax.scatter(
            point_positions,
            values,
            s=70,
            color=COLORS[group],
            edgecolor="white",
            linewidth=0.8,
            alpha=0.9,
            label=f"{group} raw data",
            zorder=3,
        )

        group_mean = sum(values) / len(values)
        group_median = median(values)
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
        scale = max(values)
        label_offset = (
            0.012 * scale
            if scale and abs(group_mean - group_median) < 0.025 * scale
            else 0
        )
        ax.text(
            x + 0.23,
            group_mean + label_offset,
            f"mean {_format_value(group_mean)}",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )
        ax.text(
            x + 0.23,
            group_median - label_offset,
            f"median {_format_value(group_median)}",
            va="center",
            fontsize=9,
            color=COLORS[group],
        )

    ax.set_title(title)
    ax.set_xlabel("Group")
    ax.set_ylabel(y_label)
    ax.set_xticks(list(positions.values()), GROUPS)
    ax.set_xlim(-0.5, 1.5)
    maximum = max(max(values) for values in values_by_group.values())
    ax.set_ylim(0, maximum * 1.1 if maximum else 1)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="lower left")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def main(input_path: Path, output_dir: Path) -> None:
    """Generate all three execution-efficiency plots."""

    for metric, (title, y_label, filename) in METRICS.items():
        values = read_efficiency_values(input_path, metric)
        plot_metric(values, f"Raw {title} by Group", y_label, output_dir / filename)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Plot Phase 2 execution-efficiency metrics by group."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=repo_root / "results" / "phase2" / "efficiency" / "execution_efficiency.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=repo_root / "scripts" / "analysis" / "outputs" / "figures",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args.input, args.output_dir)
