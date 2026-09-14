from copy import deepcopy
import json
from pathlib import Path

from scripts.metric_collection.mutation_cache import (
    add_evidence,
    build_execution_context,
    build_execution_policy,
    evidence_key,
    execution_context_hash,
    execution_policy_hash,
    load_evidence,
    migrate_legacy_confirmations,
    persist_evidence,
    plan_result_reuse,
    reliable_evidence_for_mutant,
    upgrade_legacy_result,
)


def _catalog() -> dict:
    return {
        "catalog_hash": "catalog",
        "sut_hash": "sut",
        "tool_version": "mutmut, version 3.7.0",
    }


def _context(test_hash: str = "tests") -> dict:
    return build_execution_context(
        _catalog(),
        test_artifact_hash=test_hash,
        test_materials_hash="materials",
        python_version="3.11.6",
    )


def _policy(multiplier: float = 5.0, constant: float = 0.5) -> dict:
    return build_execution_policy(
        timeout_multiplier=multiplier,
        timeout_constant=constant,
        timeout_retry_count=1,
        confirm_kills=True,
        confirmation_protocol="independent_second_execution_v2",
        exclude_duplicates=False,
    )


def _mutants() -> list[dict]:
    return [{"mutant_id": name} for name in ("M1", "M2", "M3")]


def _previous(policy: dict | None = None, context: dict | None = None) -> dict:
    context = context or _context()
    return {
        "catalog_hash": "catalog",
        "sut_hash": "sut",
        "participant": {"participant_commit": "commit-11"},
        "execution_context_hash": execution_context_hash(context),
        "execution_policy": policy or _policy(),
        "mutants": [
            {
                "mutant_id": "M1",
                "status": "killed",
                "raw_status": "killed",
                "duration_seconds": 0.8,
                "estimated_test_duration_seconds": 0.2,
                "exit_code": 1,
                "kill_confirmation": "confirmed",
            },
            {
                "mutant_id": "M2",
                "status": "survived",
                "raw_status": "survived",
                "duration_seconds": 1.2,
                "estimated_test_duration_seconds": 0.3,
                "exit_code": 0,
            },
            {"mutant_id": "M3", "status": "timeout", "raw_status": "timeout"},
        ],
        "collection_policy": {
            "tool_version": "mutmut, version 3.7.0",
            "python_version": "3.11.6",
            "valid_only_protocol": "isolated_expanded_cases_v1",
            "mutant_timeout": {"multiplier": 5.0, "constant": 0.5},
            "timeout_retry": {"attempts": 1},
            "global_kill_confirmation": {
                "enabled": True,
                "protocol": "independent_second_execution_v2",
            },
        },
    }


def test_timeout_only_change_does_not_invalidate_confirmed_kill() -> None:
    plan = plan_result_reuse(
        _mutants(),
        _previous(_policy(3.0, 0.5)),
        current_context_hash=execution_context_hash(_context()),
        current_policy=_policy(5.0, 0.5),
    )
    assert set(plan["reused"]) == {"M1", "M2"}
    assert plan["rerun_ids"] == ["M3"]


def test_timeout_increase_only_reruns_previous_timeouts() -> None:
    plan = plan_result_reuse(
        _mutants(),
        _previous(_policy(3.0, 0.5)),
        current_context_hash=execution_context_hash(_context()),
        current_policy=_policy(5.0, 0.5),
    )
    assert plan["statistics"]["rerun_previous_timeouts"] == 1
    assert plan["statistics"]["rerun_policy_affected"] == 0


def test_timeout_decrease_reruns_slow_or_durationless_rows() -> None:
    previous = _previous(_policy(15.0, 1.0))
    previous["mutants"][1]["duration_seconds"] = 10.0
    plan = plan_result_reuse(
        _mutants(),
        previous,
        current_context_hash=execution_context_hash(_context()),
        current_policy=_policy(5.0, 0.5),
    )
    assert set(plan["reused"]) == {"M1"}
    assert plan["rerun_ids"] == ["M2", "M3"]


def test_duration_backfill_accepts_no_tests_without_actual_duration() -> None:
    previous = _previous()
    previous["mutants"][2]["status"] = "no_tests"
    previous["mutants"][2]["raw_status"] = "no_tests"
    previous["mutants"][2]["estimated_test_duration_seconds"] = 0.3
    previous["mutants"][2]["exit_code"] = 33

    plan = plan_result_reuse(
        _mutants(),
        previous,
        current_context_hash=execution_context_hash(_context()),
        current_policy=_policy(),
        backfill_missing_durations=True,
    )

    assert set(plan["reused"]) == {"M1", "M2", "M3"}
    assert plan["rerun_ids"] == []
    assert plan["statistics"]["rerun_missing_durations"] == 0


def test_duration_backfill_is_opt_in_and_not_execution_policy() -> None:
    previous = _previous()
    previous["mutants"][0]["duration_seconds"] = None
    previous["mutants"][1]["estimated_test_duration_seconds"] = None
    previous["mutants"][2]["duration_seconds"] = 2.0
    previous["mutants"][2]["estimated_test_duration_seconds"] = 0.3
    previous["mutants"][2]["exit_code"] = 2

    ordinary = plan_result_reuse(
        _mutants(),
        previous,
        current_context_hash=execution_context_hash(_context()),
        current_policy=_policy(),
    )
    backfill = plan_result_reuse(
        _mutants(),
        previous,
        current_context_hash=execution_context_hash(_context()),
        current_policy=_policy(),
        backfill_missing_durations=True,
    )

    assert set(ordinary["reused"]) == {"M1", "M2", "M3"}
    assert backfill["rerun_ids"] == ["M1", "M2"]
    assert backfill["statistics"]["rerun_missing_durations"] == 2
    assert backfill["statistics"]["rerun_previous_timeouts"] == 0
    assert backfill["statistics"]["rerun_policy_affected"] == 0
    assert "backfill" not in json.dumps(_policy())


def test_new_kill_is_the_only_confirmation_candidate() -> None:
    previous = _previous(_policy(3.0, 0.5))
    plan = plan_result_reuse(
        _mutants(),
        previous,
        current_context_hash=execution_context_hash(_context()),
        current_policy=_policy(5.0, 0.5),
    )
    rerun_statuses = {"M3": "killed"}
    candidates = [
        mutant_id
        for mutant_id in plan["rerun_ids"]
        if rerun_statuses[mutant_id] == "killed"
    ]
    assert candidates == ["M3"]


def test_participant_test_change_invalidates_status_cache() -> None:
    plan = plan_result_reuse(
        _mutants(),
        _previous(),
        current_context_hash=execution_context_hash(_context("changed")),
        current_policy=_policy(),
    )
    assert plan["statistics"]["invalidated_context_mismatch"] == 3


def test_catalog_or_sut_change_invalidates_context_hash() -> None:
    context = _context()
    changed_catalog = deepcopy(context)
    changed_catalog["catalog_hash"] = "changed"
    changed_sut = deepcopy(context)
    changed_sut["sut_hash"] = "changed"
    assert execution_context_hash(context) != execution_context_hash(changed_catalog)
    assert execution_context_hash(context) != execution_context_hash(changed_sut)


def test_max_children_is_not_in_execution_policy_hash() -> None:
    policy = _policy()
    assert "max_children" not in json.dumps(policy)
    assert execution_policy_hash(policy) == execution_policy_hash(deepcopy(policy))


def test_confirmed_evidence_survives_incremental_resume(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    context = _context()
    record = {
        "mutant_id": "M1",
        "catalog_hash": "catalog",
        "sut_hash": "sut",
        "test_artifact_hash": "tests",
        "python_version": "3.11.6",
        "mutmut_version": "mutmut, version 3.7.0",
        "valid_only_protocol": context["valid_only_protocol"],
        "confirmed_status": "reliably_killed",
    }
    payload = load_evidence(path)
    assert add_evidence(payload, record)
    persist_evidence(path, payload)
    loaded = load_evidence(path)
    assert evidence_key(record) in loaded["records"]


def test_empty_payload_does_not_overwrite_existing_evidence(tmp_path: Path) -> None:
    path = tmp_path / "evidence.json"
    path.write_text('{"schema_version": 1, "records": {"old": {}}}\n')
    persist_evidence(path, {"schema_version": 1, "records": {}})
    assert "old" in load_evidence(path)["records"]


def test_global_evidence_is_separate_from_participant_status() -> None:
    context = _context()
    evidence = {"schema_version": 1, "records": {}}
    migrated = migrate_legacy_confirmations(
        _previous(), evidence, participant_id="experiment-11", context=context
    )
    assert migrated == 1
    matches = reliable_evidence_for_mutant(
        evidence, mutant_id="M1", catalog_hash="catalog", sut_hash="sut"
    )
    assert len(matches) == 1
    assert _previous()["mutants"][2]["status"] == "timeout"


def test_legacy_result_requires_matching_participant_commit() -> None:
    context = _context()
    legacy = _previous()
    legacy.pop("execution_context_hash")
    legacy.pop("execution_policy")
    adopted = upgrade_legacy_result(
        legacy, context=context, participant_commit="commit-11"
    )
    rejected = upgrade_legacy_result(
        legacy, context=context, participant_commit="different"
    )

    assert adopted is not None and adopted["legacy_cache_adopted"] is True
    assert adopted["execution_context_hash"] == execution_context_hash(context)
    assert rejected is not None and "execution_context_hash" not in rejected
