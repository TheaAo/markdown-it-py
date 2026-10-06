"""Re-derive verified source positions and coverage scope from a frozen inventory."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
from pathlib import Path
import sys
import tempfile
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metric_collection_phase1 import build_mutant_catalog as engine
from scripts.metric_collection_phase1.mutation_common import (
    catalog_hash,
    function_from_mutant_name,
    load_catalog,
    stable_mutant_id,
    sut_hash,
    write_json,
)
from scripts.metric_collection_phase2.build_mutant_catalog import (
    prepare_workspace,
    workload_hashes,
)


def derive_rows(
    workspace: Path, rows: list[dict[str, Any]], lines: dict[str, dict[str, set[int]]]
) -> list[dict[str, Any]]:
    result = []
    for old in rows:
        mapped = engine._absolute_source_lines(
            workspace, old["module"], old["mutant_name"], old["diff"]
        )
        anchors = engine._coverage_source_lines(workspace, old["module"], mapped)
        specified = engine._covered(lines["specified"], old["module"], anchors)
        extended = engine._covered(lines["extended"], old["module"], anchors)
        result.append(
            {
                **old,
                "function": function_from_mutant_name(old["mutant_name"]),
                "mutant_id": stable_mutant_id(
                    old["module"], old["mutant_name"], mapped[0], old["diff"]
                ),
                "source_line": mapped[0],
                "changed_source_lines": list(mapped),
                "coverage_source_lines": list(anchors),
                "covered_by_specified": specified,
                "covered_by_extended": extended,
                "workload_layer": engine.classify_workload_layer(specified, extended),
                "mapping_status": "mapped",
            }
        )
    return sorted(result, key=lambda row: row["mutant_id"])


def repair(args: argparse.Namespace) -> None:
    parent_path = args.input_dir / "full_sut_mutant_catalog.json"
    parent = load_catalog(parent_path)
    comparison = parent["generation_comparison"]
    if (
        not comparison["semantic_catalog_hash_match"]
        or comparison["first_raw_catalog_hash"] != comparison["second_raw_catalog_hash"]
        or len(parent["mutants"]) != parent["catalog_statistics"]["generated_mutants"]
    ):
        raise ValueError("A complete twice-generated frozen inventory is required")
    runs = []
    with tempfile.TemporaryDirectory(prefix="phase2-source-map-") as directory:
        for number in (1, 2):
            workspace = Path(directory) / str(number)
            prepare_workspace(
                args.repo_root,
                parent["baseline_commit"],
                workspace,
                parent["only_mutate"],
            )
            if (
                sut_hash(workspace / "markdown_it") != parent["sut_hash"]
                or workload_hashes(workspace) != parent["workload_hashes"]
                or engine._workspace_material_hashes(workspace)
                != parent["material_hashes"]
            ):
                raise ValueError("Frozen SUT/reference inputs changed")
            lines = {}
            coverage = {}
            for layer in ("specified", "extended"):
                lines[layer], coverage[layer], _ = engine._coverage(
                    args.python, workspace, layer
                )
            rows = derive_rows(workspace, parent["mutants"], lines)
            runs.append((rows, lines, coverage))
    first, second = runs
    if catalog_hash(first[0]) != catalog_hash(second[0]) or first[1:] != second[1:]:
        raise ValueError("Corrected positions and scope are not reproducible")
    rows = first[0]
    layers = Counter(row["workload_layer"] for row in rows)
    metadata = deepcopy(parent["catalog_statistics"])
    metadata.update(
        mapping_failures=0,
        mapping_failure_rate=0.0,
        task_relevant_mutants=layers["specified"] + layers["extended_only"],
        specified_mutants=layers["specified"],
        extended_only_mutants=layers["extended_only"],
        out_of_scope_mutants=layers["out_of_scope"],
        coverage=first[2],
        function_counts=dict(Counter(f"{r['module']}::{r['function']}" for r in rows)),
        coverage_membership_counts=dict(
            Counter(
                "both"
                if r["covered_by_specified"] and r["covered_by_extended"]
                else "specified_only"
                if r["covered_by_specified"]
                else "extended_only"
                if r["covered_by_extended"]
                else "neither"
                for r in rows
            )
        ),
    )
    correction = {
        "protocol": "verified_function_hunks_with_leading_comments_and_overload_filter_v2",
        "parent_raw_catalog_sha256": hashlib.sha256(
            parent_path.read_bytes()
        ).hexdigest(),
        "parent_raw_catalog_hash": parent["catalog_hash"],
        "raw_inventory_generation_comparison": comparison,
        "corrected_derivation_hashes": [catalog_hash(run[0]) for run in runs],
        "source_mapping_failures": 0,
        "coverage_repetitions": 2,
        "mutant_executions_regenerated": False,
        "reason": "Correct coordinate metadata and scope; exact mutant names/diffs and frozen SUT are unchanged",
    }
    run = {
        "metadata": metadata,
        "sut_hash": parent["sut_hash"],
        "tool_version": parent["tool_version"],
        "python_version": parent["python_version"],
    }
    common = {
        "baseline_ref": parent["baseline_ref"],
        "baseline_commit": parent["baseline_commit"],
        "only_mutate": parent["only_mutate"],
        "run": run,
        "generation_comparison": {
            **comparison,
            "source_mapping_correction": correction,
        },
    }
    raw = engine._catalog_payload(**common, mutants=rows, catalog_kind="full_sut_raw")
    task = engine._catalog_payload(
        **common,
        mutants=engine.derive_task_relevant_mutants(rows),
        catalog_kind="task_relevant_census",
    )
    raw["traceability"] = deepcopy(parent["traceability"])
    task["traceability"] = deepcopy(parent["traceability"])
    engine._write_full_catalogs(args.output_dir, raw, task)
    (args.output_dir / "workload_traceability.csv").write_bytes(
        (args.input_dir / "workload_traceability.csv").read_bytes()
    )
    write_json(args.output_dir / "source_mapping_correction.json", correction)
    write_json(
        args.output_dir / "executed_source_lines.json",
        {
            layer: {path: sorted(values) for path, values in modules.items()}
            for layer, modules in first[1].items()
        },
    )
    print(f"Corrected task census: {len(task['mutants'])}; layers: {dict(layers)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--input-dir", type=Path, default=Path("results/phase2/mutation_score/catalog")
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/phase2/mutation_score/catalog_corrected"),
    )
    parser.add_argument("--python", type=Path, required=True)
    repair(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
