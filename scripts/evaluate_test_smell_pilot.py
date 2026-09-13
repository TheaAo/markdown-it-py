from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence


DEFAULT_FIXTURE_DIR = (
    Path(__file__).parents[1]
    / "tests"
    / "metric_collection"
    / "fixtures"
    / "test_smell_pilot"
)


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _metrics(
    predicted_pairs: set[tuple[str, str]],
    gold_pairs: set[tuple[str, str]],
    universe: set[tuple[str, str]],
) -> dict[str, int | float]:
    true_positives = len(predicted_pairs & gold_pairs)
    false_positives = len(predicted_pairs - gold_pairs)
    false_negatives = len(gold_pairs - predicted_pairs)
    true_negatives = len(universe - (predicted_pairs | gold_pairs))
    precision = _ratio(true_positives, true_positives + false_positives)
    recall = _ratio(true_positives, true_positives + false_negatives)
    f1 = _ratio(2 * precision * recall, precision + recall)
    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "true_negatives": true_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def evaluate_pilot(gold_path: Path, observations_path: Path) -> dict[str, Any]:
    gold = _load_object(gold_path)
    observations = _load_object(observations_path)
    labels = gold.get("labels")
    scored_smells = gold.get("scored_smells")
    tools = observations.get("tools")
    if not isinstance(labels, dict) or not isinstance(scored_smells, list):
        raise ValueError("gold data must contain labels and scored_smells")
    if not isinstance(tools, dict):
        raise ValueError("observations must contain a tools object")

    test_names = set(labels)
    smells = set(scored_smells)
    gold_pairs = {
        (test_name, smell)
        for test_name, test_smells in labels.items()
        for smell in test_smells
    }
    results: dict[str, Any] = {}

    for tool_name, tool in tools.items():
        if not isinstance(tool, dict):
            raise ValueError(f"tool {tool_name} must be an object")
        if tool.get("status") != "completed":
            results[tool_name] = {
                "status": tool.get("status"),
                "reason": tool.get("reason"),
                "repeatable": tool.get("repeatable"),
            }
            continue

        detections = tool.get("detections")
        supported_smells = tool.get("supported_smells")
        if not isinstance(detections, list) or not isinstance(supported_smells, list):
            raise ValueError(
                f"tool {tool_name} needs detections and supported_smells arrays"
            )
        supported = set(supported_smells)
        if not supported <= smells:
            raise ValueError(f"tool {tool_name} declares unknown supported smells")
        universe = {
            (test_name, smell) for test_name in test_names for smell in supported
        }
        supported_gold = {pair for pair in gold_pairs if pair[1] in supported}
        predicted_pairs = {
            (item["test_name"], item["smell"])
            for item in detections
            if isinstance(item, dict) and item.get("smell") in supported
        }
        unknown_pairs = predicted_pairs - universe
        if unknown_pairs:
            raise ValueError(
                f"tool {tool_name} has unknown detections: {unknown_pairs}"
            )

        overall = _metrics(predicted_pairs, supported_gold, universe)
        per_smell = {}
        for smell in sorted(supported):
            smell_universe = {pair for pair in universe if pair[1] == smell}
            smell_gold = {pair for pair in supported_gold if pair[1] == smell}
            smell_predictions = {pair for pair in predicted_pairs if pair[1] == smell}
            per_smell[smell] = _metrics(
                smell_predictions, smell_gold, smell_universe
            )
        results[tool_name] = {
            "status": "completed",
            "supported_smells": sorted(supported),
            **overall,
            "per_smell": per_smell,
            "repeatable": tool.get("repeatable"),
        }

    return {
        "test_function_count": len(test_names),
        "scored_smells": sorted(smells),
        "positive_label_count": len(gold_pairs),
        "tool_results": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the test-smell pilot")
    parser.add_argument(
        "--gold", type=Path, default=DEFAULT_FIXTURE_DIR / "gold_labels.json"
    )
    parser.add_argument(
        "--observations",
        type=Path,
        default=DEFAULT_FIXTURE_DIR / "observations.json",
    )
    args = parser.parse_args(argv)
    print(json.dumps(evaluate_pilot(args.gold, args.observations), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
