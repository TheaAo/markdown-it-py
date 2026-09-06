from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.metric_collection.mutation_common import (
        semantic_artifact_hash,
        write_json,
    )
except ModuleNotFoundError:  # pragma: no cover
    from mutation_common import semantic_artifact_hash, write_json  # type: ignore[no-redef]


RUNNER_PROTOCOL = "isolated_expanded_cases_v1"
EVIDENCE_SCHEMA_VERSION = 1


def catalog_identity_hash(catalog: dict[str, Any]) -> str:
    return semantic_artifact_hash(
        {
            "mutant_catalog_hash": catalog["catalog_hash"],
            "baseline_commit": catalog.get("baseline_commit"),
            "sut_hash": catalog["sut_hash"],
            "tool": catalog.get("tool", "mutmut"),
            "tool_version": catalog["tool_version"],
            "source_paths": catalog.get("source_paths"),
            "only_mutate": catalog.get("only_mutate"),
            "operator_family_method": catalog.get("operator_family_method"),
        }
    )


def build_execution_context(
    catalog: dict[str, Any],
    *,
    test_artifact_hash: str,
    test_materials_hash: str,
    python_version: str,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "catalog_hash": catalog["catalog_hash"],
        "catalog_identity_hash": catalog_identity_hash(catalog),
        "sut_hash": catalog["sut_hash"],
        "test_artifact_hash": test_artifact_hash,
        "test_materials_hash": test_materials_hash,
        "python_version": python_version,
        "mutmut_version": catalog["tool_version"],
        "valid_only_protocol": RUNNER_PROTOCOL,
    }


def build_execution_policy(
    *,
    timeout_multiplier: float,
    timeout_constant: float,
    timeout_retry_count: int,
    confirm_kills: bool,
    confirmation_protocol: str,
    exclude_duplicates: bool,
    test_timeout: float | None = None,
    execution_timeout: float | None = None,
) -> dict[str, Any]:
    if timeout_multiplier <= 0:
        raise ValueError("timeout multiplier must be positive")
    if timeout_constant < 0:
        raise ValueError("timeout constant must be non-negative")
    if timeout_retry_count < 0:
        raise ValueError("timeout retry count must be non-negative")
    return {
        "schema_version": 1,
        "mutant_timeout": {
            "formula": "(estimated_test_time + constant) * multiplier",
            "multiplier": timeout_multiplier,
            "constant": timeout_constant,
        },
        "timeout_retry_count": timeout_retry_count,
        "baseline_test_timeout_seconds": test_timeout,
        "collection_execution_timeout_seconds": execution_timeout,
        "kill_confirmation": {
            "enabled": confirm_kills,
            "protocol": confirmation_protocol,
        },
        "equivalent_duplicate_policy": {
            "exclude_confirmed_equivalent": True,
            "exclude_duplicates": exclude_duplicates,
        },
    }


def execution_context_hash(context: dict[str, Any]) -> str:
    return semantic_artifact_hash(context)


def execution_policy_hash(policy: dict[str, Any]) -> str:
    return semantic_artifact_hash(policy)


def timeout_limit(policy: dict[str, Any], estimated_test_time: float) -> float:
    timeout = policy["mutant_timeout"]
    return (estimated_test_time + float(timeout["constant"])) * float(
        timeout["multiplier"]
    )


def _timeout_relation(old: dict[str, Any], new: dict[str, Any]) -> str:
    old_timeout = old["mutant_timeout"]
    new_timeout = new["mutant_timeout"]
    old_slope = float(old_timeout["multiplier"])
    new_slope = float(new_timeout["multiplier"])
    old_intercept = old_slope * float(old_timeout["constant"])
    new_intercept = new_slope * float(new_timeout["constant"])
    if new_slope == old_slope and new_intercept == old_intercept:
        return "same"
    if new_slope >= old_slope and new_intercept >= old_intercept:
        return "increased"
    if new_slope <= old_slope and new_intercept <= old_intercept:
        return "decreased"
    return "mixed"


def _duration_fits_policy(row: dict[str, Any], policy: dict[str, Any]) -> bool:
    duration = row.get("duration_seconds")
    estimated = row.get("estimated_test_duration_seconds")
    if not isinstance(duration, (int, float)) or not isinstance(
        estimated, (int, float)
    ):
        return False
    return float(duration) <= timeout_limit(policy, float(estimated))


def _has_complete_execution_metadata(row: dict[str, Any]) -> bool:
    estimated = row.get("estimated_test_duration_seconds")
    exit_code = row.get("exit_code")
    if not isinstance(estimated, (int, float)) or not isinstance(exit_code, int):
        return False
    duration = row.get("duration_seconds")
    return isinstance(duration, (int, float)) or row.get("status") == "no_tests"


def plan_result_reuse(
    mutants: Sequence[dict[str, Any]],
    previous_result: dict[str, Any] | None,
    *,
    current_context_hash: str,
    current_policy: dict[str, Any],
    backfill_missing_durations: bool = False,
) -> dict[str, Any]:
    mutant_ids = [item["mutant_id"] for item in mutants]
    empty = {
        "reused": {},
        "rerun_ids": mutant_ids,
        "statistics": {
            "reused_results": 0,
            "rerun_previous_timeouts": 0,
            "rerun_policy_affected": 0,
            "rerun_missing_durations": 0,
            "invalidated_context_mismatch": len(mutant_ids),
        },
    }
    if previous_result is None:
        empty["statistics"]["invalidated_context_mismatch"] = 0
        return empty
    if previous_result.get("execution_context_hash") != current_context_hash:
        return empty
    previous_rows = {
        row.get("mutant_id"): row
        for row in previous_result.get("mutants", [])
        if isinstance(row, dict)
    }
    if set(previous_rows) != set(mutant_ids):
        return empty
    old_policy = previous_result.get("execution_policy")
    if not isinstance(old_policy, dict):
        return empty
    relation = _timeout_relation(old_policy, current_policy)
    same_retry = old_policy.get("timeout_retry_count") == current_policy.get(
        "timeout_retry_count"
    )
    reused: dict[str, dict[str, Any]] = {}
    rerun_ids: list[str] = []
    rerun_previous_timeouts = 0
    rerun_policy_affected = 0
    rerun_missing_durations = 0
    for mutant_id in mutant_ids:
        row = previous_rows[mutant_id]
        status = row.get("status")
        reuse = False
        if relation == "same" and same_retry:
            reuse = True
        elif relation == "increased":
            reuse = status != "timeout"
        elif relation in {"decreased", "mixed"}:
            reuse = _duration_fits_policy(row, current_policy)
        if reuse and backfill_missing_durations and not _has_complete_execution_metadata(
            row
        ):
            rerun_ids.append(mutant_id)
            rerun_missing_durations += 1
            continue
        if reuse:
            reused[mutant_id] = row
            continue
        rerun_ids.append(mutant_id)
        if status == "timeout":
            rerun_previous_timeouts += 1
        else:
            rerun_policy_affected += 1
    return {
        "reused": reused,
        "rerun_ids": rerun_ids,
        "statistics": {
            "reused_results": len(reused),
            "rerun_previous_timeouts": rerun_previous_timeouts,
            "rerun_policy_affected": rerun_policy_affected,
            "rerun_missing_durations": rerun_missing_durations,
            "invalidated_context_mismatch": 0,
        },
    }


def upgrade_legacy_result(
    previous_result: dict[str, Any] | None,
    *,
    context: dict[str, Any],
    participant_commit: str,
) -> dict[str, Any] | None:
    if previous_result is None or "execution_context_hash" in previous_result:
        return previous_result
    old_policy = previous_result.get("collection_policy")
    participant = previous_result.get("participant")
    if not isinstance(old_policy, dict) or not isinstance(participant, dict):
        return previous_result
    checks = (
        previous_result.get("catalog_hash") == context["catalog_hash"],
        previous_result.get("sut_hash") == context["sut_hash"],
        participant.get("participant_commit") == participant_commit,
        old_policy.get("tool_version") == context["mutmut_version"],
        old_policy.get("python_version") == context["python_version"],
        old_policy.get("valid_only_protocol") == context["valid_only_protocol"],
    )
    if not all(checks):
        return previous_result
    timeout = old_policy.get("mutant_timeout", {})
    retry = old_policy.get("timeout_retry", {})
    confirmation = old_policy.get("global_kill_confirmation", {})
    try:
        execution_policy = build_execution_policy(
            timeout_multiplier=float(timeout["multiplier"]),
            timeout_constant=float(timeout["constant"]),
            timeout_retry_count=int(retry.get("attempts", 1)),
            confirm_kills=bool(confirmation.get("enabled", False)),
            confirmation_protocol=str(confirmation.get("protocol", "legacy")),
            exclude_duplicates=bool(old_policy.get("exclude_duplicates", False)),
            test_timeout=old_policy.get("test_timeout_seconds"),
            execution_timeout=old_policy.get("execution_timeout_seconds"),
        )
    except (KeyError, TypeError, ValueError):
        return previous_result
    upgraded = dict(previous_result)
    upgraded["execution_context"] = context
    upgraded["execution_context_hash"] = execution_context_hash(context)
    upgraded["execution_policy"] = execution_policy
    upgraded["execution_policy_hash"] = execution_policy_hash(execution_policy)
    upgraded["legacy_cache_adopted"] = True
    return upgraded


def evidence_key(record: dict[str, Any]) -> str:
    return semantic_artifact_hash(
        {
            "mutant_id": record["mutant_id"],
            "catalog_hash": record["catalog_hash"],
            "catalog_identity_hash": record.get("catalog_identity_hash"),
            "sut_hash": record["sut_hash"],
            "test_artifact_hash": record["test_artifact_hash"],
            "execution_context_hash": record.get("execution_context_hash"),
            "python_version": record["python_version"],
            "mutmut_version": record["mutmut_version"],
            "valid_only_protocol": record["valid_only_protocol"],
        }
    )


def load_evidence(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {"schema_version": EVIDENCE_SCHEMA_VERSION, "records": {}}
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != EVIDENCE_SCHEMA_VERSION
        or not isinstance(payload.get("records"), dict)
    ):
        raise ValueError("invalid reliable-kill evidence artifact")
    return payload


def persist_evidence(path: Path, payload: dict[str, Any]) -> None:
    if not payload.get("records") and path.is_file():
        return
    write_json(path, payload)


def add_evidence(payload: dict[str, Any], record: dict[str, Any]) -> bool:
    key = evidence_key(record)
    records = payload.setdefault("records", {})
    if key in records:
        return False
    records[key] = {**record, "evidence_key": key}
    return True


def reliable_evidence_for_mutant(
    payload: dict[str, Any],
    *,
    mutant_id: str,
    catalog_hash: str,
    sut_hash: str,
) -> list[dict[str, Any]]:
    return [
        record
        for record in payload.get("records", {}).values()
        if record.get("mutant_id") == mutant_id
        and record.get("catalog_hash") == catalog_hash
        and record.get("sut_hash") == sut_hash
        and record.get("confirmed_status") == "reliably_killed"
    ]


def migrate_legacy_confirmations(
    previous_result: dict[str, Any],
    evidence: dict[str, Any],
    *,
    participant_id: str,
    context: dict[str, Any],
) -> int:
    if previous_result.get("catalog_hash") != context["catalog_hash"]:
        return 0
    if previous_result.get("sut_hash") != context["sut_hash"]:
        return 0
    old_policy = previous_result.get("collection_policy", {})
    if old_policy.get("tool_version") != context["mutmut_version"]:
        return 0
    if old_policy.get("python_version") != context["python_version"]:
        return 0
    if old_policy.get("valid_only_protocol") != context["valid_only_protocol"]:
        return 0
    added = 0
    migrated_at = datetime.now(timezone.utc).isoformat()
    source_artifact_hash = semantic_artifact_hash(previous_result)
    for row in previous_result.get("mutants", []):
        if (
            row.get("raw_status") != "killed"
            or row.get("kill_confirmation") != "confirmed"
        ):
            continue
        record = {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "mutant_id": row["mutant_id"],
            "catalog_hash": context["catalog_hash"],
            "catalog_identity_hash": context["catalog_identity_hash"],
            "sut_hash": context["sut_hash"],
            "test_artifact_hash": context["test_artifact_hash"],
            "execution_context_hash": execution_context_hash(context),
            "participant_id": participant_id,
            "confirmed_status": "reliably_killed",
            "exit_code": 1,
            "duration_seconds": row.get("confirmation_duration_seconds"),
            "confirmed_at": previous_result.get("generated_at") or migrated_at,
            "timeout_used": row.get("confirmation_timeout_seconds"),
            "python_version": context["python_version"],
            "mutmut_version": context["mutmut_version"],
            "valid_only_protocol": context["valid_only_protocol"],
            "evidence_quality": "verified_legacy_status_inferred_exit_code",
            "source_artifact_hash": source_artifact_hash,
            "source_format": "legacy_confirmed_mutant_row",
            "migrated_at": migrated_at,
        }
        added += add_evidence(evidence, record)
    return added
