"""Create a grouped participant characteristics table from the pre-survey."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

try:
    from .participants import PARTICIPANTS_BY_NUMBER
except ImportError:
    from participants import PARTICIPANTS_BY_NUMBER


GROUPS = ("Manual", "AI")
GROUP_LABELS = {"Manual": "Manual", "AI": "AI"}
NUMERIC_CHARACTERISTICS = {
    "English proficiency": (
        "How would you rate your English proficiency for reading technical or academic materials "
        "(e.g., documentation, research papers)?"
    ),
    "Python proficiency": "How would you rate your overall proficiency in Python development?",
    "Software testing proficiency": "How would you rate your overall proficiency in software testing?",
    "Unit-test writing proficiency": "How would you rate your overall proficiency in writing unit tests?",
    "pytest experience": "How would you rate your experience in pytest?",
    "GitHub Copilot experience": "How would you rate your experience in using Github Copilot?",
}
CATEGORICAL_CHARACTERISTICS = {
    "Primary status": "What is your current primary status?",
    "Primary field/background": "What is your primary field or background?",
    "Programming experience": "How many years of active programming experience do you have?",
    "AI-tool usage frequency": (
        "How often do you use AI-assisted tools (e.g., GitHub Copilot, Claude, ChatGPT) for coding?"
    ),
}
MULTISELECT_CHARACTERISTICS = {
    "AI-assisted tools used": "Which AI-assisted coding tools have you used before? (Select all that apply)",
}


def _read_rows(path: Path) -> list[dict[str, str]]:
    """Read and validate pre-survey rows against the participant metadata."""

    with path.open(newline="", encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    if not rows:
        raise ValueError(f"Pre-survey is empty: {path}")

    selected: list[dict[str, str]] = []
    for row in rows:
        try:
            number = int(row["No"])
        except (KeyError, ValueError) as error:
            raise ValueError(f"Invalid participant number in {path}: {row.get('No', '')}") from error
        participant = PARTICIPANTS_BY_NUMBER.get(number)
        if participant is None:
            continue
        if row.get("Group") != participant.phase1_group:
            raise ValueError(
                f"Group mismatch for participant {number}: "
                f"{row.get('Group')} != {participant.phase1_group}"
            )
        selected.append(row)

    if len({int(row["No"]) for row in selected}) != len(selected):
        raise ValueError(f"Duplicate participant in {path}")
    return selected


def _format_count(values: list[str]) -> str:
    """Format category frequencies."""

    counts = Counter(values)
    return "; ".join(
        f"{value}: {count}"
        for value, count in sorted(counts.items())
    )


def _format_multiselect(values: list[str]) -> str:
    """Format semicolon-separated multi-select response frequencies."""

    counts: Counter[str] = Counter()
    for value in values:
        counts.update(item.strip() for item in value.split(";") if item.strip() and item != "None")
    return "; ".join(
        f"{item}: {count}"
        for item, count in sorted(counts.items())
    ) or "None reported"


def build_table(rows: list[dict[str, str]]) -> str:
    """Build a grouped Markdown participant characteristics table."""

    grouped_rows = {
        group: [row for row in rows if row["Group"] == group] for group in GROUPS
    }
    columns = ["Characteristic", *(GROUP_LABELS[group] for group in GROUPS), "Overall"]
    output = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
        "| **Participants, n** | "
        + " | ".join(str(len(grouped_rows[group])) for group in GROUPS)
        + f" | {len(rows)} |",
    ]

    for label, column in NUMERIC_CHARACTERISTICS.items():
        cells = [
            _format_count([row[column] for row in grouped_rows[group]])
            for group in GROUPS
        ]
        cells.append(_format_count([row[column] for row in rows]))
        output.append("| " + " | ".join([label, *cells]) + " |")

    for label, column in CATEGORICAL_CHARACTERISTICS.items():
        cells = [
            _format_count([row[column] for row in grouped_rows[group]])
            for group in GROUPS
        ]
        cells.append(_format_count([row[column] for row in rows]))
        output.append("| " + " | ".join([label, *cells]) + " |")

    for label, column in MULTISELECT_CHARACTERISTICS.items():
        cells = [
            _format_multiselect([row[column] for row in grouped_rows[group]])
            for group in GROUPS
        ]
        cells.append(_format_multiselect([row[column] for row in rows]))
        output.append("| " + " | ".join([label, *cells]) + " |")

    return "\n".join(output) + "\n"


def main(input_path: Path, output_path: Path) -> None:
    """Read the pre-survey and write the grouped characteristics table."""

    table = build_table(_read_rows(input_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(table, encoding="utf-8")
    print(table, end="")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_path", type=Path)
    parser.add_argument("output_path", type=Path)
    arguments = parser.parse_args()
    main(arguments.input_path, arguments.output_path)
