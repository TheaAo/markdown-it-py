from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys
from typing import Any

COLUMNS = (
    "participant_number",
    "status",
    "metric_status",
    "valid_tests_included",
    "invalid_tests_excluded",
    "measurement_count",
    "execution_time_seconds",
    "mean_seconds",
    "standard_deviation_seconds",
    "minimum_seconds",
    "maximum_seconds",
    "first_quartile_seconds",
    "third_quartile_seconds",
    "interquartile_range_seconds",
    "median_absolute_deviation_seconds",
    "coefficient_of_variation",
    "cv_review_threshold",
    "cv_review_required",
)


def summarize_execution_times(manifest_path: Path, output_path: Path) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    participants = payload.get("participants")
    if not isinstance(participants, list):
        raise ValueError("manifest must contain a participants array")
    rows: list[dict[str, Any]] = []
    for participant in participants:
        if not isinstance(participant, dict):
            raise ValueError("each participant must be an object")
        row: dict[str, Any] = {
            "participant_number": participant.get("participant_number"),
            "status": participant.get("status"),
        }
        if participant.get("status") == "collected":
            summary = participant.get("summary")
            if not isinstance(summary, dict):
                raise ValueError("collected participant is missing summary")
            row.update(
                metric_status=summary.get("metric_status"),
                valid_tests_included=summary.get("valid_tests_included"),
                invalid_tests_excluded=summary.get("invalid_tests_excluded"),
            )
            timing = summary.get("execution_time")
            if timing is not None:
                if not isinstance(timing, dict):
                    raise ValueError("execution_time summary must be an object")
                row.update(timing)
        rows.append(row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: f"{value:.9f}" if isinstance(value, float) else value
                    for key, value in row.items()
                }
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create an analysis-ready execution-time CSV."
    )
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/execution_time/summary/execution_time.csv"),
    )
    args = parser.parse_args(argv)
    try:
        summarize_execution_times(args.manifest, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
