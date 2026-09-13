from __future__ import annotations

import csv
import json
from pathlib import Path

from scripts.summarize_execution_times import summarize_execution_times


def test_summary_writes_focused_execution_time_table(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "execution_time.csv"
    manifest.write_text(
        json.dumps(
            {
                "participants": [
                    {
                        "participant_number": 1,
                        "status": "collected",
                        "summary": {
                            "metric_status": "collected",
                            "valid_tests_included": 10,
                            "invalid_tests_excluded": 1,
                            "execution_time": {
                                "execution_time_seconds": 1.25,
                                "measurement_count": 15,
                            },
                        },
                    },
                    {"participant_number": 13, "status": "not_participated"},
                ]
            }
        ),
        encoding="utf-8",
    )

    summarize_execution_times(manifest, output)

    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["execution_time_seconds"] == "1.250000000"
    assert rows[0]["measurement_count"] == "15"
    assert rows[1]["execution_time_seconds"] == ""
