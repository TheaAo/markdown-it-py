import csv
import json
from pathlib import Path

from scripts.collect_test_smells import FORMAL_SMELLS
from scripts.summarize_test_smells import TEST_SMELL_COLUMNS, summarize_test_smells


def test_summary_writes_one_focused_row_per_participant(tmp_path: Path) -> None:
    per_smell = {
        smell: {
            "confirmed_count": int(smell == "unknown_test"),
            "uncertain_count": 0,
            "rate": 0.2 if smell == "unknown_test" else 0.0,
        }
        for smell in FORMAL_SMELLS
    }
    manifest = {
        "participants": [
            {"participant_number": 13, "status": "not_participated"},
            {
                "participant_number": 1,
                "status": "collected",
                "summary": {
                    "total_source_tests": 5,
                    "eligible_test_count": 5,
                    "invalid_test_count": 0,
                    "smelly_test_count": 1,
                    "confirmed_pair_count": 1,
                    "uncertain_pair_count": 0,
                    "smelly_test_rate": 0.2,
                    "mean_smells_per_test": 0.2,
                    "test_smell_density": 1 / 35,
                    "per_smell": per_smell,
                },
            },
        ]
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    output = summarize_test_smells(manifest_path, tmp_path / "test_smell.csv")

    with output.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert list(reader.fieldnames or []) == list(TEST_SMELL_COLUMNS)
        rows = list(reader)
    assert rows[0]["participant_number"] == "1"
    assert rows[0]["unknown_test_count"] == "1"
    assert rows[0]["test_smell_density"] == "0.028571"
    assert rows[1]["status"] == "not_participated"
    assert rows[1]["test_smell_density"] == ""
