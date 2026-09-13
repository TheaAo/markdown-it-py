import ast
import json
from pathlib import Path

from scripts.detect_test_smells_ast import detect_file
from scripts.evaluate_test_smell_pilot import evaluate_pilot


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "test_smell_pilot"
PILOT_FILE = FIXTURE_DIR / "test_pilot_cases.py"


def _pairs(items: list[dict[str, str]]) -> set[tuple[str, str]]:
    return {(item["test_name"], item["smell"]) for item in items}


def test_gold_labels_match_all_source_test_functions() -> None:
    tree = ast.parse(PILOT_FILE.read_text(encoding="utf-8"))
    source_tests = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }
    gold = json.loads((FIXTURE_DIR / "gold_labels.json").read_text())

    assert len(source_tests) == 42
    assert source_tests == set(gold["labels"])


def test_ast_rule_engine_scans_all_formal_smells_and_matches_oracle() -> None:
    gold = json.loads((FIXTURE_DIR / "gold_labels.json").read_text())
    expected = {
        (test_name, smell)
        for test_name, smells in gold["labels"].items()
        for smell in smells
    }
    observations = json.loads((FIXTURE_DIR / "observations.json").read_text())

    assert _pairs(detect_file(PILOT_FILE)) == expected
    assert _pairs(observations["tools"]["ast_rule_engine"]["detections"]) == expected


def test_aligned_pilot_metrics_are_reproducible() -> None:
    report = evaluate_pilot(
        FIXTURE_DIR / "gold_labels.json",
        FIXTURE_DIR / "observations.json",
    )

    assert report["test_function_count"] == 42
    assert report["positive_label_count"] == 22

    ast_result = report["tool_results"]["ast_rule_engine"]
    assert (ast_result["true_positives"], ast_result["false_positives"]) == (22, 0)
    assert ast_result["false_negatives"] == 0
    assert ast_result["f1"] == 1.0

    pytest_smell = report["tool_results"]["pytest-smell"]
    assert (pytest_smell["true_positives"], pytest_smell["false_positives"]) == (
        16,
        9,
    )
    assert pytest_smell["false_negatives"] == 6
    assert pytest_smell["f1"] == 32 / 47
    assert pytest_smell["per_smell"]["eager_test"]["recall"] == 0.0
    assert pytest_smell["per_smell"]["duplicate_assert"]["recall"] == 1 / 3

    tempy = report["tool_results"]["TEMPY"]
    assert (tempy["true_positives"], tempy["false_positives"]) == (9, 5)
    assert tempy["false_negatives"] == 1
    assert tempy["f1"] == 0.75
    assert set(tempy["per_smell"]) == {
        "conditional_test_logic",
        "exception_handling",
        "unknown_test",
    }

    assert report["tool_results"]["PyNose"]["status"] == "not_runnable"
