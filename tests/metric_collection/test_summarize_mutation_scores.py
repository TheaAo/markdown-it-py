import csv
import json
from pathlib import Path

from scripts.metric_collection.summarize_mutation_scores import COLUMNS, summarize


def test_writes_focused_mutation_table(tmp_path: Path) -> None:
    manifest = {
        "participants": [
            {"participant_number": 13, "status": "not_participated"},
            {
                "participant_number": 1,
                "status": "collected",
                "summary": {
                    "valid_tests_included": 5,
                    "invalid_tests_excluded": 1,
                    "specified": {
                        "catalog_total": 6,
                        "killed": 3,
                        "survived": 2,
                        "no_tests": 1,
                        "timeout": 0,
                        "confirmed_equivalent": 0,
                        "eligible_mutants": 6,
                        "mutation_score": 0.5,
                    },
                    "extended": {
                        "catalog_total": 4,
                        "killed": 0,
                        "survived": 2,
                        "no_tests": 1,
                        "timeout": 1,
                        "confirmed_equivalent": 1,
                        "eligible_mutants": 2,
                        "mutation_score": 0.0,
                    },
                    "combined": {
                        "catalog_total": 10,
                        "mutation_score": 0.375,
                    },
                },
            },
        ]
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    output = summarize(manifest_path, tmp_path / "mutation_scores.csv")

    with output.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == list(COLUMNS)
        rows = list(reader)
    assert rows[0]["participant_number"] == "1"
    assert rows[0]["specified_mutation_score"] == "0.5"
    assert rows[0]["extended_mutation_score"] == "0.0"
    assert rows[0]["combined_mutation_score"] == "0.375"
    assert rows[1]["status"] == "not_participated"
    assert rows[1]["specified_catalog_total"] == ""
