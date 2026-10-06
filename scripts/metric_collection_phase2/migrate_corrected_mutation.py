"""Preserve exact execution observations across a verified source-map correction."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metric_collection_phase1.mutation_cache import (
    add_evidence,
    build_execution_context,
    execution_context_hash,
    load_evidence,
)
from scripts.metric_collection_phase1.mutation_common import (
    load_catalog,
    normalize_diff,
    write_json,
)
from scripts.metric_collection_phase2.finalize_mutation_score import validate_completion


def same_executable_mutant(old: dict[str, Any], new: dict[str, Any]) -> bool:
    """Coordinates may change; the executable function and exact diff may not."""
    return (
        old["mutant_name"] == new["mutant_name"]
        and old["module"] == new["module"]
        and normalize_diff(old["diff"]) == normalize_diff(new["diff"])
    )


def migrate(root: Path) -> None:
    old_catalog = load_catalog(root / "catalog/task_relevant_mutant_catalog.json")
    new_catalog = load_catalog(
        root / "catalog_corrected/task_relevant_mutant_catalog.json"
    )
    raw_inventory = load_catalog(root / "catalog/full_sut_mutant_catalog.json")
    correction = new_catalog["generation_comparison"]["source_mapping_correction"]
    if correction["parent_raw_catalog_hash"] != raw_inventory["catalog_hash"]:
        raise ValueError(
            "Source-map correction does not derive from the frozen inventory"
        )
    for field in (
        "baseline_commit",
        "sut_hash",
        "tool_version",
        "python_version",
        "workload_hashes",
        "material_hashes",
        "source_paths",
        "only_mutate",
        "operator_family_method",
    ):
        if old_catalog.get(field) != new_catalog.get(field):
            raise ValueError(f"Execution identity changed beyond coordinates: {field}")
    source = root / "formal"
    target = root / "formal_corrected"
    if target.exists():
        raise ValueError("Migration destination already exists")
    manifest = json.loads((source / "collection_manifest.json").read_text())
    validate_completion(manifest, old_catalog)
    old_by_id = {row["mutant_id"]: row for row in old_catalog["mutants"]}
    new_by_name = {row["mutant_name"]: row for row in new_catalog["mutants"]}
    contexts: dict[str, dict[str, Any]] = {}
    reports = []
    for participant in manifest["participants"]:
        path = source / participant["output_file"]
        old = json.loads(path.read_text())
        if (
            old["collection_status"] != "success"
            or old["catalog_hash"] != old_catalog["catalog_hash"]
        ):
            raise ValueError("Successful original participant observations required")
        old_context = old["execution_context"]
        context = build_execution_context(
            new_catalog,
            test_artifact_hash=old_context["test_artifact_hash"],
            test_materials_hash=old_context["test_materials_hash"],
            python_version=old_context["python_version"],
        )
        context["valid_only_protocol"] = old_context["valid_only_protocol"]
        identity = execution_context_hash(context)
        contexts[participant["participant_id"]] = {
            "old": old_context,
            "new": context,
            "old_hash": old["execution_context_hash"],
            "new_hash": identity,
        }
        outcomes = {row["mutant_name"]: row for row in old["mutants"]}
        if {row["mutant_id"] for row in old["mutants"]} != set(old_by_id):
            raise ValueError("Original outcome inventory is incomplete")
        rows = []
        reused = 0
        for mutant in new_catalog["mutants"]:
            previous = outcomes.get(mutant["mutant_name"])
            if previous is None:
                rows.append(
                    {**mutant, "status": "unavailable", "raw_status": "unavailable"}
                )
                continue
            if not same_executable_mutant(previous, mutant):
                raise ValueError("Mutant body changed; cannot migrate execution")
            rows.append(
                {
                    **previous,
                    **mutant,
                    "source_mapping_parent_mutant_id": previous["mutant_id"],
                }
            )
            reused += 1
        provenance = {
            "protocol": "exact_name_diff_sut_test_context_mapping_migration_v1",
            "source_relative_path": participant["output_file"],
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "source_catalog_hash": old_catalog["catalog_hash"],
            "target_catalog_hash": new_catalog["catalog_hash"],
            "source_execution_context_hash": old["execution_context_hash"],
            "target_execution_context_hash": identity,
            "retained_observations": reused,
            "unexecuted_placeholders": len(rows) - reused,
            "flaky_observations_require_rerun": sum(
                bool(row.get("flaky_kill")) for row in rows
            ),
            "participant_commit": participant["participant_commit"],
        }
        cache = {
            **old,
            "collection_status": "migration_cache_not_final_results",
            "catalog_hash": new_catalog["catalog_hash"],
            "execution_context": context,
            "execution_context_hash": identity,
            "mutants": rows,
            "source_mapping_migration": provenance,
        }
        # Missing/flaky rows must be executed; placeholders never enter final scores.
        cache.pop("summary", None)
        name = f"{participant['participant_id']}.json"
        write_json(target / "migration_cache" / name, cache)
        write_json(target / "raw" / name, cache)
        reports.append({"participant_id": participant["participant_id"], **provenance})
    evidence: dict[str, Any] = {"schema_version": 1, "records": {}}
    for record in load_evidence(source / "reliable_kill_evidence.json")[
        "records"
    ].values():
        original = old_by_id.get(record["mutant_id"])
        if original is None:
            raise ValueError("Evidence refers to an unknown original mutant")
        mutant = new_by_name.get(original["mutant_name"])
        if mutant is None:
            continue
        if not same_executable_mutant(original, mutant):
            raise ValueError("Evidence mutant changed")
        context = contexts[record["participant_id"]]
        if (
            record["catalog_hash"] != old_catalog["catalog_hash"]
            or record["sut_hash"] != new_catalog["sut_hash"]
            or record["execution_context_hash"] != context["old_hash"]
            or record["test_artifact_hash"] != context["new"]["test_artifact_hash"]
            or record["confirmed_status"] != "reliably_killed"
            or record["exit_code"] != 1
        ):
            raise ValueError("Reliable evidence identity validation failed")
        add_evidence(
            evidence,
            {
                **record,
                "mutant_id": mutant["mutant_id"],
                "catalog_hash": new_catalog["catalog_hash"],
                "catalog_identity_hash": context["new"]["catalog_identity_hash"],
                "execution_context_hash": context["new_hash"],
                "source_mapping_parent_evidence_key": record["evidence_key"],
                "source_mapping_parent_catalog_hash": old_catalog["catalog_hash"],
            },
        )
    write_json(target / "reliable_kill_evidence.json", evidence)
    write_json(
        target / "source_mapping_migration.json",
        {
            "source_formal_manifest_sha256": hashlib.sha256(
                (source / "collection_manifest.json").read_bytes()
            ).hexdigest(),
            "source_evidence_sha256": hashlib.sha256(
                (source / "reliable_kill_evidence.json").read_bytes()
            ).hexdigest(),
            "participants": reports,
            "migrated_confirmed_evidence_records": len(evidence["records"]),
        },
    )
    print(
        f"Migrated eight caches; retained {reports[0]['retained_observations']} observations each; rerun {reports[0]['unexecuted_placeholders']} new mutants plus flaky observations"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path("results/phase2/mutation_score")
    )
    migrate(parser.parse_args().root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
