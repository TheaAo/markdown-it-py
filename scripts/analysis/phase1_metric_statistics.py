"""Calculate Phase 1 metric statistics for the Manual and AI groups.

The input workbook is read without third-party Excel dependencies.  Only
participants listed in ``participants.py`` and rows marked ``collected`` are
included.  Empty metric cells are treated as zero.

Coverage statistics are displayed as percentages for mean and median, and as
percentage points for standard deviation.  The script prints a Markdown table
and writes the same displayed values to CSV.
"""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree

try:
    from .participants import PARTICIPANTS_BY_NUMBER
except ImportError:
    from participants import PARTICIPANTS_BY_NUMBER


GROUPS = ("Manual", "AI")
METRICS = {
    "statement_coverage": "participant_statement_coverage",
    "branch_coverage": "participant_branch_coverage",
    "mutation_score": "specified_estimated_adjusted_mutation_score",
    "assertion_score": "assertion_score",
}
NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELATIONSHIP_NAMESPACE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)


def _read_cell_value(
    cell: ElementTree.Element,
    shared_strings: list[str],
) -> str:
    """Return the displayed value of an XLSX cell."""

    value = cell.find(f"{{{NAMESPACE}}}v")
    if cell.get("t") == "inlineStr":
        return "".join(
            text.text or ""
            for text in cell.findall(f".//{{{NAMESPACE}}}t")
        )
    if value is None or value.text is None:
        return ""
    if cell.get("t") == "s":
        return shared_strings[int(value.text)]
    return value.text


def _summary_sheet_path(workbook: ZipFile) -> str:
    """Find the worksheet path for the sheet named ``Summary``."""

    workbook_root = ElementTree.fromstring(workbook.read("xl/workbook.xml"))
    relationships_root = ElementTree.fromstring(
        workbook.read("xl/_rels/workbook.xml.rels")
    )
    relationships = {
        relationship.get("Id"): relationship.get("Target")
        for relationship in relationships_root
    }
    for sheet in workbook_root.findall(f".//{{{NAMESPACE}}}sheet"):
        if sheet.get("name") != "Summary":
            continue
        relationship_id = sheet.get(
            f"{{{RELATIONSHIP_NAMESPACE}}}id"
        )
        target = relationships[relationship_id]
        return target.lstrip("/")
    raise ValueError("Workbook does not contain a Summary sheet")


def _read_summary(path: Path) -> list[dict[str, str]]:
    """Read the Summary worksheet as dictionaries keyed by column name."""

    with ZipFile(path) as workbook:
        shared_root = ElementTree.fromstring(workbook.read("xl/sharedStrings.xml"))
        shared_strings = [
            "".join(text.text or "" for text in item.findall(f".//{{{NAMESPACE}}}t"))
            for item in shared_root.findall(f"{{{NAMESPACE}}}si")
        ]
        sheet_root = ElementTree.fromstring(
            workbook.read(_summary_sheet_path(workbook))
        )

    rows: list[dict[str, str]] = []
    for row in sheet_root.findall(f".//{{{NAMESPACE}}}sheetData/{{{NAMESPACE}}}row"):
        values: dict[str, str] = {}
        for cell in row.findall(f"{{{NAMESPACE}}}c"):
            coordinate = cell.get("r", "")
            column = coordinate.rstrip("0123456789")
            values[column] = _read_cell_value(cell, shared_strings)
        if values:
            rows.append(values)

    if not rows:
        raise ValueError("Summary worksheet is empty")
    headers = rows[0]
    return [
        {headers[column]: value for column, value in row.items() if column in headers}
        for row in rows[1:]
    ]


def _metric_values(path: Path) -> dict[str, dict[str, list[float]]]:
    """Collect metric values by group, treating empty cells as zero."""

    values = {
        metric: {group: [] for group in GROUPS}
        for metric in METRICS
    }
    seen_participants: set[int] = set()
    for row in _read_summary(path):
        participant_text = row.get("participant_number", "").strip()
        if not participant_text:
            continue
        participant = int(participant_text)
        metadata = PARTICIPANTS_BY_NUMBER.get(participant)
        if metadata is None or row.get("status", "").strip() != "collected":
            continue
        if participant in seen_participants:
            raise ValueError(f"Duplicate collected participant: {participant}")
        seen_participants.add(participant)

        for metric, column in METRICS.items():
            raw_value = row.get(column, "").strip()
            values[metric][metadata.phase1_group].append(
                float(raw_value) if raw_value else 0.0
            )

    expected_participants = set(PARTICIPANTS_BY_NUMBER)
    missing_participants = expected_participants - seen_participants
    if missing_participants:
        raise ValueError(
            "Missing collected participants from Summary: "
            f"{sorted(missing_participants)}"
        )
    return values


def calculate_statistics(
    path: Path,
) -> list[dict[str, str | float | int]]:
    """Calculate mean, median, and sample SD for each group and metric."""

    values = _metric_values(path)
    result: list[dict[str, str | float | int]] = []
    for metric in METRICS:
        for group in GROUPS:
            group_values = values[metric][group]
            result.append(
                {
                    "group": group,
                    "metric": metric,
                    "n": len(group_values),
                    "mean": statistics.mean(group_values),
                    "median": statistics.median(group_values),
                    "sd": statistics.stdev(group_values),
                }
            )
    return result


def _print_table(rows: list[dict[str, str | float | int]]) -> None:
    """Print statistics as Markdown tables with metric-specific units."""

    coverage_rows = [
        row
        for row in rows
        if row["metric"] in {"statement_coverage", "branch_coverage"}
    ]
    score_rows = [
        row
        for row in rows
        if row["metric"] not in {"statement_coverage", "branch_coverage"}
    ]
    print("| Group | Metric | n | Mean (%) | Median (%) | SD (pp) |")
    print("|---|---|---:|---:|---:|---:|")
    for row in coverage_rows:
        print(
            f"| {row['group']} | {row['metric']} | {row['n']} | "
            f"{float(row['mean']) * 100:.6f} | "
            f"{float(row['median']) * 100:.6f} | "
            f"{float(row['sd']) * 100:.6f} |"
        )
    print("\n| Group | Metric | n | Mean | Median | SD |")
    print("|---|---|---:|---:|---:|---:|")
    for row in score_rows:
        print(
            f"| {row['group']} | {row['metric']} | {row['n']} | "
            f"{row['mean']:.6f} | {row['median']:.6f} | {row['sd']:.6f} |"
        )


def _write_csv(path: Path, rows: list[dict[str, str | float | int]]) -> None:
    """Write displayed statistics to CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=("group", "metric", "n", "mean", "median", "sd"),
        )
        writer.writeheader()
        for row in rows:
            output_row = row.copy()
            if row["metric"] in {"statement_coverage", "branch_coverage"}:
                output_row["mean"] = float(row["mean"]) * 100
                output_row["median"] = float(row["median"]) * 100
                output_row["sd"] = float(row["sd"]) * 100
            writer.writerow(output_row)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Calculate Phase 1 metric statistics by participant group."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=repo_root / "results" / "phase1" / "summary" / "thesis_metrics.xlsx",
        help="XLSX workbook containing the Summary worksheet.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            repo_root
            / "scripts"
            / "analysis"
            / "outputs"
            / "tables"
            / "phase1_metric_statistics.csv"
        ),
        help="CSV file to write.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    statistics_rows = calculate_statistics(arguments.input)
    _write_csv(arguments.output, statistics_rows)
    _print_table(statistics_rows)
    print(f"\nCSV written to {arguments.output}")
