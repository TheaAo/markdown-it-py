from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

try:
    from scripts.metric_collection.mutation_common import (
        load_catalog,
        write_csv,
        write_json,
    )
except ModuleNotFoundError:  # pragma: no cover
    from mutation_common import (  # type: ignore[no-redef]
        load_catalog,
        write_csv,
        write_json,
    )


MUTANT_COLUMNS = (
    "mutant_id",
    "global_status",
    "reliable_kill_count",
    "killed",
    "survived",
    "no_tests",
    "timeout",
    "suspicious",
    "skipped",
    "segfault",
    "unavailable",
    "workload_layer",
    "module",
    "function",
    "source_line",
    "operator_family",
    "original_code",
    "mutated_code",
)
BLINDED_REVIEW_COLUMNS = (
    "mutant_id",
    "workload_layer",
    "module",
    "function",
    "source_line",
    "operator_family",
    "original_code",
    "mutated_code",
    "context_diff",
    "show_command",
    "tests_command",
    "rerun_command",
    "reviewer_1_status",
    "reviewer_1_reason",
    "reviewer_2_status",
    "reviewer_2_reason",
    "adjudicated_status",
    "adjudication_reason",
)


def _unwrap(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"result is not an object: {path}")
    if isinstance(payload.get("mutation"), dict):
        participant = payload.get("participant", {})
        mutation = payload["mutation"]
        outer_policy_hash = payload.get(
            "execution_policy_hash", payload.get("collection_policy_hash")
        )
        inner_policy_hash = mutation.get(
            "execution_policy_hash", mutation.get("collection_policy_hash")
        )
        if outer_policy_hash != inner_policy_hash:
            raise ValueError(f"collection policy hash mismatch inside {path}")
    else:
        participant = payload.get("participant", {})
        mutation = payload
    if not isinstance(participant, dict) or not isinstance(mutation, dict):
        raise ValueError(f"invalid participant result: {path}")
    participant_id = participant.get("participant_id") or path.stem.split(".", 1)[0]
    participant = {**participant, "participant_id": str(participant_id)}
    return participant, mutation


def _participant_reliable(
    participant: dict[str, Any], mutation: dict[str, Any]
) -> bool:
    wrapper_status = participant.get("status", "collected")
    return (
        wrapper_status == "collected"
        and mutation.get("collection_status") == "success"
        and mutation.get("baseline_valid_only_passed") is True
        and mutation.get("infrastructure_error", False) is False
        and isinstance(mutation.get("workload_hashes"), dict)
        and isinstance(mutation.get("material_hashes"), dict)
        and isinstance(
            mutation.get(
                "execution_context_hash", mutation.get("collection_policy_hash")
            ),
            str,
        )
    )


def _blinded_row(mutant: dict[str, Any]) -> dict[str, Any]:
    name = mutant["mutant_name"]
    return {
        "mutant_id": mutant["mutant_id"],
        "workload_layer": mutant["workload_layer"],
        "module": mutant["module"],
        "function": mutant["function"],
        "source_line": mutant["source_line"],
        "operator_family": mutant.get("operator_family", "OTHER"),
        "original_code": mutant.get("original_code", ""),
        "mutated_code": mutant.get("mutated_code", ""),
        "context_diff": mutant["diff"],
        "show_command": f"mutmut show '{name}'",
        "tests_command": f"mutmut tests-for-mutant '{name}'",
        "rerun_command": f"mutmut run '{name}'",
        "reviewer_1_status": "",
        "reviewer_1_reason": "",
        "reviewer_2_status": "",
        "reviewer_2_reason": "",
        "adjudicated_status": "",
        "adjudication_reason": "",
    }


def aggregate_outcomes(
    catalog: dict[str, Any],
    participant_results: Iterable[tuple[dict[str, Any], dict[str, Any]]],
    *,
    require_confirmed_kills: bool = False,
    reliable_kill_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    participant_results = list(participant_results)
    catalog_mutants = {item["mutant_id"]: item for item in catalog["mutants"]}
    participants: list[dict[str, Any]] = []
    matrix: dict[str, dict[str, str]] = {mutant_id: {} for mutant_id in catalog_mutants}
    reliable: dict[str, bool] = {}
    source_rows: dict[str, dict[str, dict[str, Any]]] = {}
    workload_hashes = catalog.get("workload_hashes")
    material_hashes = catalog.get("material_hashes")
    expected_policy_hash: str | None = None
    evidence_by_mutant: dict[str, list[dict[str, Any]]] = {}
    if reliable_kill_evidence is not None:
        for record in reliable_kill_evidence.get("records", {}).values():
            if (
                record.get("confirmed_status") == "reliably_killed"
                and record.get("catalog_hash") == catalog["catalog_hash"]
                and record.get("sut_hash") == catalog.get("sut_hash")
            ):
                evidence_by_mutant.setdefault(record["mutant_id"], []).append(record)
    for participant, mutation in participant_results:
        participant_id = participant["participant_id"]
        if (
            participant.get("status") == "not_participated"
            or participant.get("participant_number") in {13, 15}
            or participant_id in {"experiment-13", "experiment-15"}
        ):
            continue
        if participant_id in reliable:
            raise ValueError(f"duplicate participant result: {participant_id}")
        if mutation.get("catalog_hash") != catalog["catalog_hash"]:
            raise ValueError(f"catalog hash mismatch for {participant_id}")
        if mutation.get("sut_hash") != catalog.get("sut_hash"):
            raise ValueError(f"SUT hash mismatch for {participant_id}")
        if mutation.get("baseline_commit") != catalog.get("baseline_commit"):
            raise ValueError(f"baseline commit mismatch for {participant_id}")
        if (
            workload_hashes is not None
            and mutation.get("workload_hashes", workload_hashes) != workload_hashes
        ):
            raise ValueError(f"workload hash mismatch for {participant_id}")
        if (
            material_hashes is not None
            and mutation.get("material_hashes") != material_hashes
        ):
            raise ValueError(f"material hash mismatch for {participant_id}")
        participant_policy_hash = mutation.get(
            "execution_policy_hash", mutation.get("collection_policy_hash")
        )
        if not isinstance(participant_policy_hash, str):
            raise ValueError(f"missing collection policy hash for {participant_id}")
        if expected_policy_hash is None:
            expected_policy_hash = participant_policy_hash
        elif participant_policy_hash != expected_policy_hash:
            raise ValueError(f"collection policy hash mismatch for {participant_id}")
        rows = mutation.get("mutants")
        if not isinstance(rows, list):
            raise ValueError(f"missing mutant outcomes for {participant_id}")
        by_id = {row.get("mutant_id"): row for row in rows if isinstance(row, dict)}
        if set(by_id) != set(catalog_mutants):
            raise ValueError(f"mutant IDs do not match catalog for {participant_id}")
        is_reliable = _participant_reliable(participant, mutation)
        reliable[participant_id] = is_reliable
        source_rows[participant_id] = by_id
        participants.append(
            {
                "participant_id": participant_id,
                "collection_status": participant.get("status", "collected"),
                "reliable": is_reliable,
            }
        )
        for mutant_id, row in by_id.items():
            status = str(row.get("status", "unavailable"))
            if row.get("flaky_kill") is True:
                status = "flaky_kill"
            matrix[mutant_id][participant_id] = status

    outcome_rows: list[dict[str, Any]] = []
    review_candidates: list[dict[str, Any]] = []
    execution_unresolved: list[dict[str, Any]] = []
    auto_non_equivalent: list[dict[str, Any]] = []
    naive_review_ids: set[str] = set()
    for mutant_id, mutant in sorted(catalog_mutants.items()):
        statuses = matrix[mutant_id]
        counts = Counter(statuses.values())
        reliable_kills = len(evidence_by_mutant.get(mutant_id, []))
        for participant_id, status in statuses.items():
            if not reliable[participant_id] or status != "killed":
                continue
            source_row = source_rows[participant_id][mutant_id]
            if source_row.get("raw_status") != "killed" or source_row.get(
                "infrastructure_error", False
            ):
                continue
            if (
                require_confirmed_kills
                and not evidence_by_mutant.get(mutant_id)
                and source_row.get("kill_confirmation") != "confirmed"
            ):
                continue
            if not evidence_by_mutant.get(mutant_id):
                reliable_kills += 1
        if counts["survived"] or counts["no_tests"] or counts["timeout"]:
            naive_review_ids.add(mutant_id)
        if reliable_kills:
            if mutant.get("review_status") in {
                "confirmed_equivalent",
                "duplicate",
            }:
                raise ValueError(
                    f"reliable kill conflicts with global review for {mutant_id}"
                )
            global_status = "auto_non_equivalent"
        elif mutant.get("review_status") in {
            "non_equivalent",
            "confirmed_equivalent",
            "duplicate",
            "unresolved",
        }:
            global_status = mutant["review_status"]
        elif counts["survived"] or counts["no_tests"]:
            global_status = "review_candidate"
        else:
            global_status = "execution_unresolved"
        row = {
            "mutant_id": mutant_id,
            "global_status": global_status,
            "reliable_kill_count": reliable_kills,
            "killed": counts["killed"],
            "survived": counts["survived"],
            "no_tests": counts["no_tests"],
            "timeout": counts["timeout"],
            "suspicious": counts["suspicious"],
            "skipped": counts["skipped"],
            "segfault": counts["segfault"],
            "unavailable": counts["unavailable"] + counts["flaky_kill"],
            **mutant,
        }
        outcome_rows.append(row)
        if global_status == "auto_non_equivalent":
            auto_non_equivalent.append(row)
        elif global_status == "review_candidate":
            review_candidates.append(_blinded_row(mutant))
        elif global_status == "execution_unresolved":
            execution_unresolved.append(_blinded_row(mutant))

    review_total = len(review_candidates) + len(execution_unresolved)
    return {
        "schema_version": 1,
        "catalog_hash": catalog["catalog_hash"],
        "sut_hash": catalog.get("sut_hash"),
        "workload_hashes": workload_hashes,
        "material_hashes": material_hashes,
        "execution_policy_hash": expected_policy_hash,
        "reliable_kill_evidence_records": sum(
            len(records) for records in evidence_by_mutant.values()
        ),
        "participants": participants,
        "outcomes": outcome_rows,
        "auto_non_equivalent": auto_non_equivalent,
        "review_candidates": review_candidates,
        "execution_unresolved": execution_unresolved,
        "participant_matrix": matrix,
        "summary": {
            "catalog_total": len(catalog_mutants),
            "participants_total": len(participants),
            "reliable_participants": sum(item["reliable"] for item in participants),
            "auto_non_equivalent": len(auto_non_equivalent),
            "review_candidates": len(review_candidates),
            "execution_unresolved": len(execution_unresolved),
            "naive_review_union": len(naive_review_ids),
            "manual_review_total": review_total,
            "manual_review_reduction": len(
                naive_review_ids.intersection(
                    item["mutant_id"] for item in auto_non_equivalent
                )
            ),
            "manual_review_reduction_rate": (
                len(
                    naive_review_ids.intersection(
                        item["mutant_id"] for item in auto_non_equivalent
                    )
                )
                / len(naive_review_ids)
                if naive_review_ids
                else 0.0
            ),
        },
    }


def write_aggregation(output_dir: Path, payload: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "global_mutant_outcomes.json", payload)
    write_csv(
        output_dir / "global_mutant_outcomes.csv", MUTANT_COLUMNS, payload["outcomes"]
    )
    write_csv(
        output_dir / "auto_non_equivalent.csv",
        MUTANT_COLUMNS,
        payload["auto_non_equivalent"],
    )
    write_csv(
        output_dir / "review_candidates.csv",
        BLINDED_REVIEW_COLUMNS,
        payload["review_candidates"],
    )
    common_review_columns = BLINDED_REVIEW_COLUMNS[:12]
    write_csv(
        output_dir / "reviewer_1.csv",
        (*common_review_columns, "reviewer_1_status", "reviewer_1_reason"),
        payload["review_candidates"],
    )
    write_csv(
        output_dir / "reviewer_2.csv",
        (*common_review_columns, "reviewer_2_status", "reviewer_2_reason"),
        payload["review_candidates"],
    )
    write_csv(
        output_dir / "execution_unresolved.csv",
        BLINDED_REVIEW_COLUMNS,
        payload["execution_unresolved"],
    )
    participant_ids = [item["participant_id"] for item in payload["participants"]]
    write_csv(
        output_dir / "participant_mutant_matrix.csv",
        ("mutant_id", *participant_ids),
        (
            {"mutant_id": mutant_id, **statuses}
            for mutant_id, statuses in sorted(payload["participant_matrix"].items())
        ),
    )


def _result_paths(inputs: Sequence[Path]) -> list[Path]:
    paths: list[Path] = []
    for path in inputs:
        if path.is_dir():
            paths.extend(sorted(path.glob("*.json")))
        else:
            paths.append(path)
    return paths


def _include_manifest_failures(
    catalog: dict[str, Any],
    pairs: list[tuple[dict[str, Any], dict[str, Any]]],
    manifest_path: Path | None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if manifest_path is None:
        return pairs
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("catalog_hash") != catalog["catalog_hash"]:
        raise ValueError("collection manifest catalog hash does not match")
    manifest_policy_hash = manifest.get(
        "execution_policy_hash", manifest.get("collection_policy_hash")
    )
    if not isinstance(manifest_policy_hash, str):
        raise ValueError("collection manifest is missing collection policy hash")
    existing = {participant["participant_id"] for participant, _mutation in pairs}
    for participant in manifest.get("participants", []):
        participant_id = participant.get("participant_id")
        if (
            not isinstance(participant_id, str)
            or participant_id in existing
            or participant.get("status") == "not_participated"
        ):
            continue
        pairs.append(
            (
                participant,
                {
                    "catalog_hash": catalog["catalog_hash"],
                    "sut_hash": catalog.get("sut_hash"),
                    "workload_hashes": catalog.get("workload_hashes"),
                    "material_hashes": catalog.get("material_hashes"),
                    "baseline_commit": catalog.get("baseline_commit"),
                    "execution_policy_hash": manifest_policy_hash,
                    "execution_context_hash": "unavailable",
                    "collection_status": participant.get("status"),
                    "baseline_valid_only_passed": False,
                    "infrastructure_error": True,
                    "mutants": [
                        {
                            **mutant,
                            "status": "unavailable",
                            "raw_status": "unavailable",
                        }
                        for mutant in catalog["mutants"]
                    ],
                },
            )
        )
    return pairs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Aggregate participant mutant outcomes."
    )
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--results", type=Path, nargs="+", required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--require-confirmed-kills", action="store_true")
    parser.add_argument("--reliable-kill-evidence", type=Path)
    args = parser.parse_args(argv)
    try:
        catalog = load_catalog(args.catalog.resolve())
        pairs = [_unwrap(path.resolve()) for path in _result_paths(args.results)]
        pairs = _include_manifest_failures(
            catalog,
            pairs,
            args.manifest.resolve() if args.manifest else None,
        )
        payload = aggregate_outcomes(
            catalog,
            pairs,
            require_confirmed_kills=args.require_confirmed_kills,
            reliable_kill_evidence=(
                json.loads(args.reliable_kill_evidence.read_text(encoding="utf-8"))
                if args.reliable_kill_evidence
                else None
            ),
        )
        payload["generated_at"] = datetime.now(timezone.utc).isoformat()
        write_aggregation(args.output_dir.resolve(), payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    summary = payload["summary"]
    print(f"Auto non-equivalent: {summary['auto_non_equivalent']}")
    print(f"Review candidates: {summary['review_candidates']}")
    print(f"Execution unresolved: {summary['execution_unresolved']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
