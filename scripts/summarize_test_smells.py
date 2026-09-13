from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any, Sequence

try:
    from scripts.collect_test_smells import FORMAL_SMELLS
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from collect_test_smells import FORMAL_SMELLS  # type: ignore[no-redef]


COMMON_COLUMNS = ("participant_number", "status")
COUNT_COLUMNS = tuple(f"{smell}_count" for smell in FORMAL_SMELLS)
RATE_COLUMNS = tuple(f"{smell}_rate" for smell in FORMAL_SMELLS)
TEST_SMELL_COLUMNS = (
    *COMMON_COLUMNS,
    "total_source_tests",
    "eligible_test_count",
    "invalid_test_count",
    "smelly_test_count",
    "confirmed_pair_count",
    "uncertain_pair_count",
    *COUNT_COLUMNS,
    *RATE_COLUMNS,
    "smelly_test_rate",
    "mean_smells_per_test",
    "test_smell_density",
)


def _required_int(mapping: dict[str, Any], field: str, context: str) -> int:
    value = mapping.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{context}.{field} must be a non-negative integer")
    return value


def _read_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(
        payload.get("participants"), list
    ):
        raise ValueError("Test Smell manifest must contain a participants array")
    return payload


def _row(participant: dict[str, Any], context: str) -> dict[str, Any]:
    number = _required_int(participant, "participant_number", context)
    status = participant.get("status")
    if not isinstance(status, str) or not status:
        raise ValueError(f"{context}.status must be a non-empty string")
    row: dict[str, Any] = {"participant_number": number, "status": status}
    if status != "collected":
        return row
    summary = participant.get("summary")
    if not isinstance(summary, dict):
        raise ValueError(f"{context}.summary must be an object")
    for field in (
        "total_source_tests",
        "eligible_test_count",
        "invalid_test_count",
        "smelly_test_count",
        "confirmed_pair_count",
        "uncertain_pair_count",
    ):
        row[field] = _required_int(summary, field, f"{context}.summary")
    if (
        row["eligible_test_count"] + row["invalid_test_count"]
        != row["total_source_tests"]
    ):
        raise ValueError(f"{context} eligible and invalid counts do not equal total")
    per_smell = summary.get("per_smell")
    if not isinstance(per_smell, dict):
        raise ValueError(f"{context}.summary.per_smell must be an object")
    for smell in FORMAL_SMELLS:
        values = per_smell.get(smell)
        if not isinstance(values, dict):
            raise ValueError(f"{context}.summary.per_smell.{smell} is missing")
        row[f"{smell}_count"] = _required_int(
            values, "confirmed_count", f"{context}.summary.per_smell.{smell}"
        )
        row[f"{smell}_rate"] = values.get("rate")
    for field in ("smelly_test_rate", "mean_smells_per_test", "test_smell_density"):
        row[field] = summary.get(field)
    return row


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6f}"
    return value


def summarize_test_smells(manifest_path: Path, output_path: Path) -> Path:
    manifest = _read_manifest(manifest_path)
    rows = [
        _row(participant, f"participants[{index}]")
        for index, participant in enumerate(manifest["participants"])
        if isinstance(participant, dict)
    ]
    if len(rows) != len(manifest["participants"]):
        raise ValueError("participant manifest entry must be an object")
    rows.sort(key=lambda item: item["participant_number"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=TEST_SMELL_COLUMNS, lineterminator="\n"
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    column: _csv_value(row.get(column))
                    for column in TEST_SMELL_COLUMNS
                }
            )
    temporary.replace(output_path)
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create the focused Test Smell CSV.")
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=Path("results/test_smells/collection_manifest.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/test_smells/summary/test_smell.csv"),
    )
    args = parser.parse_args(argv)
    try:
        output = summarize_test_smells(args.manifest.resolve(), args.output.resolve())
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
