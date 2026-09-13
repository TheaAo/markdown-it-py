import json
from pathlib import Path

from scripts.collect_test_smells import collect_test_smells


EXPECTED = (
    "test_file",
    "test_spec",
    "test_core_after",
    "test_parse_fail",
    "test_non_utf8",
)


def _error_rates(classifications: dict[str, list[str]]) -> dict[str, object]:
    cases = []
    for source_test, statuses in classifications.items():
        for index, status in enumerate(statuses):
            cases.append(
                {
                    "nodeid": f"task.py::{source_test}[{index}]",
                    "source_test": source_test,
                    "classification": status,
                }
            )
    return {"case_level": {"test_cases": cases}}


def test_collector_uses_source_level_partial_validity_and_normalized_density(
    tmp_path: Path,
) -> None:
    test_path = tmp_path / "task.py"
    test_path.write_text(
        """
import pytest
from markdown_it import MarkdownIt

def test_file(value=True):
    assert value
    assert str(value)

def test_spec():
    for value in ["text"]:
        result = MarkdownIt().render(value)
    assert result, "render result"

def test_core_after():
    pass

def test_parse_fail():
    with pytest.raises(TypeError):
        MarkdownIt().render(None)
    assert 1 == 1, "required exit convention"

def test_non_utf8():
    pass
""",
        encoding="utf-8",
    )
    report = collect_test_smells(
        test_path=test_path,
        error_rates=_error_rates(
            {
                "test_file": ["valid", "function_error"],
                "test_spec": ["valid"],
                "test_core_after": ["function_error"],
                "test_parse_fail": ["valid"],
                "test_non_utf8": ["runtime_error"],
            }
        ),
    )

    assert report["eligible_test_count"] == 3
    assert report["invalid_test_count"] == 2
    assert report["smelly_test_count"] == 2
    assert report["confirmed_pair_count"] == 2
    assert report["smelly_test_rate"] == 2 / 3
    assert report["mean_smells_per_test"] == 2 / 3
    assert report["test_smell_density"] == 2 / 21
    cases = {item["source_test"]: item for item in report["test_cases"]}
    assert cases["test_file"]["validity"] == "partially_valid"
    assert cases["test_core_after"]["smells"] == []
    assert report["tools"]["pytest-smell"]["status"] == "not_configured"


def test_reachable_helper_supplies_unknown_test_oracle(tmp_path: Path) -> None:
    test_path = tmp_path / "task.py"
    test_path.write_text(
        """
def verify(value):
    assert value

def unused_verify(value):
    assert value

def test_file():
    verify(True)
""",
        encoding="utf-8",
    )
    report = collect_test_smells(
        test_path=test_path,
        error_rates=_error_rates({"test_file": ["valid"]}),
    )
    test_file = report["test_cases"][0]
    unknown = next(
        item for item in test_file["smells"] if item["smell"] == "unknown_test"
    )
    assert unknown["decision"] == "not_detected"


def test_zero_eligible_tests_produces_null_metrics(tmp_path: Path) -> None:
    test_path = tmp_path / "task.py"
    test_path.write_text("this is not valid python", encoding="utf-8")
    report = collect_test_smells(
        test_path=test_path,
        error_rates=_error_rates({name: ["syntax_error"] for name in EXPECTED}),
    )
    assert report["eligible_test_count"] == 0
    assert report["smelly_test_rate"] is None
    assert report["mean_smells_per_test"] is None
    assert report["test_smell_density"] is None
    assert report["tools"]["TEMPY"]["status"] == "not_run"


def test_report_is_json_serializable(tmp_path: Path) -> None:
    test_path = tmp_path / "task.py"
    test_path.write_text("def test_file():\n    assert True\n", encoding="utf-8")
    report = collect_test_smells(
        test_path=test_path,
        error_rates=_error_rates({"test_file": ["valid"]}),
    )
    json.dumps(report)
