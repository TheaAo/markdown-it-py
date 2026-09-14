from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
import json
from pathlib import Path
import re
import sys
from typing import Any

try:
    from scripts.metric_collection.mutation_common import (
        catalog_hash,
        changed_code,
        load_catalog,
        write_csv,
        write_json,
    )
except ModuleNotFoundError:  # pragma: no cover
    from mutation_common import (  # type: ignore[no-redef]
        catalog_hash,
        changed_code,
        load_catalog,
        write_csv,
        write_json,
    )


OPERATOR_FAMILIES = (
    "ARITHMETIC",
    "BOOLEAN_CONNECTOR",
    "COMPARISON",
    "CONSTANT_REPLACEMENT",
    "CONTROL_FLOW",
    "RETURN_VALUE",
    "CALL_ARGUMENT",
    "STATEMENT_REPLACEMENT",
    "OTHER",
)
TOKEN_PATTERN = re.compile(
    r"(?<!\w)(?:and|or|not|is|in|True|False|None|break|continue)(?!\w)"
    r"|==|!=|<=|>=|//|\*\*|[+\-*/%<>]"
)
COMPARISON_TOKENS = {"==", "!=", "<", "<=", ">", ">=", "is", "in"}
ARITHMETIC_TOKENS = {"+", "-", "*", "/", "//", "%", "**"}
BOOLEAN_TOKENS = {"and", "or", "not"}


def _tokens(code: str) -> list[str]:
    return TOKEN_PATTERN.findall(code)


def classify_operator_family(diff: str) -> str:
    original, mutated = changed_code(diff)
    original_text = original.strip()
    mutated_text = mutated.strip()
    original_tokens = _tokens(original)
    mutated_tokens = _tokens(mutated)

    if original_text in {"break", "continue"} or mutated_text in {
        "break",
        "continue",
    }:
        return "CONTROL_FLOW"
    if (
        original_text.startswith("return ")
        and mutated_text.startswith("return ")
        and (mutated_text == "return None" or original_text == "return None")
    ):
        return "RETURN_VALUE"
    if original_tokens != mutated_tokens and any(
        token in COMPARISON_TOKENS for token in original_tokens + mutated_tokens
    ):
        return "COMPARISON"
    if original_tokens != mutated_tokens and any(
        token in BOOLEAN_TOKENS for token in original_tokens + mutated_tokens
    ):
        return "BOOLEAN_CONNECTOR"
    if original_tokens != mutated_tokens and any(
        token in ARITHMETIC_TOKENS for token in original_tokens + mutated_tokens
    ):
        return "ARITHMETIC"
    if original != mutated and re.search(
        r"\b(?:True|False|None)\b|(?<!\w)[-+]?\d+(?:\.\d+)?", original
    ):
        return "CONSTANT_REPLACEMENT"
    if (
        original != mutated
        and re.search(r"\([^\n]*\)", original)
        and re.search(r"\([^\n]*\)", mutated)
    ):
        return "CALL_ARGUMENT"
    if len(original.splitlines()) == len(mutated.splitlines()) == 1:
        return "STATEMENT_REPLACEMENT"
    return "OTHER"


def classify_catalog(catalog: dict[str, Any]) -> dict[str, Any]:
    mutants = catalog["mutants"]
    for mutant in mutants:
        mutant["operator_family"] = classify_operator_family(mutant["diff"])
    counts = Counter(item["operator_family"] for item in mutants)
    catalog["operator_family_method"] = "normalized_diff_rules_v1"
    catalog["operator_family_counts"] = dict(sorted(counts.items()))
    if catalog.get("catalog_hash") != catalog_hash(mutants):
        raise ValueError("operator metadata unexpectedly changed catalog identity")
    return catalog


def _rows(catalog: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "mutant_id": item["mutant_id"],
            "mutant_name": item["mutant_name"],
            "workload_layer": item["workload_layer"],
            "module": item["module"],
            "function": item["function"],
            "source_line": item["source_line"],
            "operator_family": item["operator_family"],
            "original_code": item.get("original_code", ""),
            "mutated_code": item.get("mutated_code", ""),
            "manual_family": "",
            "review_notes": "",
        }
        for item in catalog["mutants"]
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Add deterministic operator-family metadata to a catalog."
    )
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--review-csv", type=Path)
    args = parser.parse_args(argv)
    try:
        catalog = classify_catalog(load_catalog(args.catalog.resolve()))
        write_json(args.output.resolve(), catalog)
        if args.review_csv:
            write_csv(
                args.review_csv.resolve(),
                (
                    "mutant_id",
                    "mutant_name",
                    "workload_layer",
                    "module",
                    "function",
                    "source_line",
                    "operator_family",
                    "original_code",
                    "mutated_code",
                    "manual_family",
                    "review_notes",
                ),
                _rows(catalog),
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
