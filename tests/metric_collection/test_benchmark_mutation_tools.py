import json

import pytest

from scripts.metric_collection.benchmark_mutation_tools import (
    mutpy_catalog,
    parse_cosmic_ray_dump,
    parse_mutmut_stats,
    parse_mutpy_summary,
)


def test_parse_mutpy_summary_and_catalog() -> None:
    output = """
   - all: 72
   - killed: 0 (0.0%)
   - survived: 1 (1.4%)
   - incompetent: 71 (98.6%)
   - timeout: 0 (0.0%)
"""
    report = """
  - lineno: 20
    operator: ROR
  - lineno: 10
    operator: AOD
"""

    assert parse_mutpy_summary(output) == {
        "total": 72,
        "killed": 0,
        "survived": 1,
        "incompetent": 71,
        "timeout": 0,
    }
    assert mutpy_catalog(report) == [(10, "AOD"), (20, "ROR")]


def test_parse_mutmut_stats_validates_schema() -> None:
    payload = json.dumps(
        {"total": 10, "killed": 4, "survived": 3, "timeout": 1, "no_tests": 2}
    )
    assert parse_mutmut_stats(payload)["killed"] == 4

    with pytest.raises(ValueError, match="unexpected schema"):
        parse_mutmut_stats('{"total": true}')


def test_parse_cosmic_ray_dump_ignores_random_job_ids() -> None:
    mutation = {
        "module_path": "markdown_it/ruler.py",
        "operator_name": "core/NumberReplacer",
        "occurrence": 1,
        "start_pos": [10, 4],
        "end_pos": [10, 5],
    }
    payload = "\n".join(
        (
            json.dumps([{"job_id": "random-a", "mutations": [mutation]}, None]),
            json.dumps(
                [
                    {"job_id": "random-b", "mutations": [mutation]},
                    {"test_outcome": "killed"},
                ]
            ),
        )
    )

    outcomes, catalog = parse_cosmic_ray_dump(payload)

    assert outcomes == {"pending": 1, "killed": 1}
    assert catalog[0] == catalog[1]
