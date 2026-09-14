import json
from pathlib import Path

import pytest

from scripts.metric_collection.apply_mutant_reviews import apply_reviews
from scripts.metric_collection.build_mutant_catalog import _absolute_source_line
from scripts.metric_collection.mutation_common import (
    catalog_hash,
    changed_line_from_diff,
    changed_code,
    function_from_mutant_name,
    load_catalog,
    layered_mutation_summary,
    mutation_summary,
    parse_mutmut_results,
    source_line_from_diff,
    stable_mutant_id,
)


DIFF = """--- markdown_it/example.py
+++ markdown_it/example.py
@@ -10,1 +10,1 @@
-    return value + 1
+    return value - 1
"""


def _catalog_mutant() -> dict[str, object]:
    return {
        "mutant_id": stable_mutant_id(
            "markdown_it/example.py", "markdown_it.example.x__mutmut_1", 10, DIFF
        ),
        "mutant_name": "markdown_it.example.x__mutmut_1",
        "module": "markdown_it/example.py",
        "function": "x",
        "source_line": 10,
        "workload_layer": "specified",
        "diff": DIFF,
        "review_status": "unreviewed",
    }


def test_diff_and_mutmut_result_parsing() -> None:
    assert source_line_from_diff(DIFF) == 10
    assert changed_line_from_diff(DIFF) == 10
    assert changed_code(DIFF) == ("    return value + 1", "    return value - 1")
    assert (
        function_from_mutant_name("markdown_it.ruler.xǁRulerǁafter__mutmut_6")
        == "after"
    )
    assert parse_mutmut_results(
        "  first: killed\n  second: no tests\n  third: timeout\n"
    ) == {"first": "killed", "second": "no_tests", "third": "timeout"}


def test_catalog_hash_rejects_tampering(tmp_path: Path) -> None:
    mutant = _catalog_mutant()
    payload = {"catalog_hash": catalog_hash([mutant]), "mutants": [mutant]}
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_catalog(path)["catalog_hash"] == payload["catalog_hash"]

    mutant["source_line"] = 11
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="catalog hash"):
        load_catalog(path)


def test_mutation_score_uses_conservative_policy() -> None:
    mutants = [
        {"status": "killed", "review_status": "unreviewed"},
        {"status": "survived", "review_status": "unreviewed"},
        {"status": "no_tests", "review_status": "unreviewed"},
        {"status": "no_tests", "review_status": "confirmed_equivalent"},
        {"status": "timeout", "review_status": "confirmed_equivalent"},
    ]

    summary = mutation_summary(mutants)

    assert summary["confirmed_equivalent"] == 1
    assert summary["eligible_mutants"] == 3
    assert summary["mutation_score"] == pytest.approx(1 / 3)
    assert summary["timeout"] == 1


def test_layered_mutation_score_separates_workloads() -> None:
    mutants = [
        {
            "status": "killed",
            "review_status": "unreviewed",
            "workload_layer": "specified",
        },
        {
            "status": "survived",
            "review_status": "unreviewed",
            "workload_layer": "extended_only",
        },
    ]

    summary = layered_mutation_summary(mutants)

    assert summary["specified"]["mutation_score"] == 1.0
    assert summary["extended"]["mutation_score"] == 0.0
    assert summary["combined"]["mutation_score"] == 0.5


def test_apply_reviews_preserves_catalog_identity(tmp_path: Path) -> None:
    mutant = _catalog_mutant()
    identity_hash = catalog_hash([mutant])
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(
        json.dumps({"catalog_hash": identity_hash, "mutants": [mutant]}),
        encoding="utf-8",
    )
    reviews_path = tmp_path / "reviews.csv"
    reviews_path.write_text(
        "mutant_id,review_status,review_notes\n"
        f"{mutant['mutant_id']},confirmed_equivalent,same behavior\n",
        encoding="utf-8",
    )

    updated = apply_reviews(catalog_path, reviews_path)

    assert updated["catalog_hash"] == identity_hash
    assert updated["mutants"][0]["review_status"] == "confirmed_equivalent"


def test_mutmut_function_relative_line_becomes_absolute(tmp_path: Path) -> None:
    module = tmp_path / "markdown_it/example.py"
    module.parent.mkdir()
    module.write_text(
        "class Example:\n"
        "    def calculate(self, value):\n"
        "        return value + 1\n",
        encoding="utf-8",
    )
    diff = """--- markdown_it/example.py
+++ markdown_it/example.py
@@ -2,1 +2,1 @@
-    return value + 1
+    return value - 1
"""

    line = _absolute_source_line(
        tmp_path,
        "markdown_it/example.py",
        "markdown_it.example.xǁExampleǁcalculate__mutmut_1",
        diff,
    )

    assert line == 3
