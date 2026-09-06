from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

try:
    from scripts.metric_collection.collect_coverage import _isolated_valid_nodeids
    from scripts.metric_collection.collect_error_rates import (
        TestCaseResult,
        collect_error_rates,
    )
    from scripts.metric_collection.mutation_common import (
        labeled_files_hash,
        layered_mutation_summary,
        layered_weighted_mutation_summary,
        load_catalog,
        parse_mutmut_results,
        semantic_artifact_hash,
        sut_hash,
        write_csv,
        write_json,
    )
    from scripts.metric_collection.mutation_cache import (
        RUNNER_PROTOCOL,
        add_evidence,
        build_execution_context,
        build_execution_policy,
        execution_context_hash,
        execution_policy_hash,
        load_evidence,
        migrate_legacy_confirmations,
        persist_evidence,
        plan_result_reuse,
        reliable_evidence_for_mutant,
        timeout_limit,
        upgrade_legacy_result,
    )
except ModuleNotFoundError:  # pragma: no cover
    from collect_coverage import _isolated_valid_nodeids  # type: ignore[no-redef]
    from collect_error_rates import (  # type: ignore[no-redef]
        TestCaseResult,
        collect_error_rates,
    )
    from mutation_common import (  # type: ignore[no-redef]
        labeled_files_hash,
        layered_mutation_summary,
        layered_weighted_mutation_summary,
        load_catalog,
        parse_mutmut_results,
        semantic_artifact_hash,
        sut_hash,
        write_csv,
        write_json,
    )
    from mutation_cache import (  # type: ignore[no-redef]
        RUNNER_PROTOCOL,
        add_evidence,
        build_execution_context,
        build_execution_policy,
        execution_context_hash,
        execution_policy_hash,
        load_evidence,
        migrate_legacy_confirmations,
        persist_evidence,
        plan_result_reuse,
        reliable_evidence_for_mutant,
        timeout_limit,
        upgrade_legacy_result,
    )


AUDIT_COLUMNS = (
    "mutant_id",
    "mutant_name",
    "workload_layer",
    "module",
    "function",
    "source_line",
    "original_code",
    "mutated_code",
    "status",
    "review_status",
    "review_notes",
    "covering_tests",
    "show_command",
    "tests_command",
    "rerun_command",
)
TEST_REVIEW_COLUMNS = (
    "source_test",
    "classification",
    "valid_generated_cases",
    "invalid_generated_cases",
    "review_notes",
)


def _test_review_rows(
    results: Sequence[TestCaseResult],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[TestCaseResult]] = {}
    for result in results:
        grouped.setdefault(result.source_test, []).append(result)
    return [
        {
            "source_test": source_test,
            "classification": "unreviewed",
            "valid_generated_cases": sum(
                item.classification == "valid" for item in cases
            ),
            "invalid_generated_cases": sum(
                item.classification != "valid" for item in cases
            ),
            "review_notes": "",
        }
        for source_test, cases in sorted(grouped.items())
    ]


def _run(
    command: Sequence[str], cwd: Path, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def _error_payload(
    path: Path | None, test_path: Path, args: argparse.Namespace
) -> dict[str, Any]:
    if path is None:
        return asdict(
            collect_error_rates(
                test_path=test_path,
                repo_root=args.repo_root,
                python_executable=str(args.python),
                timeout=args.test_timeout,
            )
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("metrics"), dict):
        payload = payload["metrics"]
    if not isinstance(payload, dict) or not isinstance(payload.get("case_level"), dict):
        raise ValueError("error-rate JSON is missing case_level")
    return payload


def _test_results(payload: dict[str, Any]) -> list[TestCaseResult]:
    raw_cases = payload["case_level"].get("test_cases")
    if not isinstance(raw_cases, list):
        raise ValueError("error-rate JSON is missing case_level.test_cases")
    return [
        TestCaseResult(
            nodeid=item["nodeid"],
            source_test=item["source_test"],
            classification=item["classification"],
            returncode=item.get("returncode"),
            reason=item["reason"],
        )
        for item in raw_cases
    ]


def _write_config(
    workspace: Path,
    nodeids: Sequence[str],
    only_mutate: Sequence[str],
    *,
    timeout_multiplier: float,
    timeout_constant: float,
) -> None:
    selection = "\n".join(f"    {nodeid}" for nodeid in nodeids)
    mutation_filter = ""
    if only_mutate:
        mutation_filter = (
            "only_mutate=\n" + "\n".join(f"    {path}" for path in only_mutate) + "\n"
        )
    (workspace / "setup.cfg").write_text(
        "[mutmut]\n"
        "source_paths=markdown_it/\n"
        f"{mutation_filter}"
        "pytest_add_cli_args_test_selection=\n"
        f"{selection}\n"
        "use_setproctitle=false\n"
        "track_dependencies=false\n"
        f"timeout_multiplier={timeout_multiplier}\n"
        f"timeout_constant={timeout_constant}\n",
        encoding="utf-8",
    )


def _mutmut_results(executable: Path, workspace: Path) -> dict[str, str]:
    completed = _run([str(executable), "results", "--all", "true"], workspace)
    if completed.returncode:
        raise RuntimeError(f"mutmut results failed:\n{completed.stdout}")
    return parse_mutmut_results(completed.stdout)


def _copy_submission_resources(
    repo_root: Path, test_path: Path, workspace: Path
) -> None:
    try:
        relative_parent = test_path.parent.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("participant test must be inside the repository") from exc
    shutil.copytree(
        test_path.parent,
        workspace / relative_parent,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _valid_test_artifact_hash(valid_root: Path, nodeids: Sequence[str]) -> str:
    files = [
        {
            "path": path.relative_to(valid_root).as_posix(),
            "content": path.read_text(encoding="utf-8"),
        }
        for path in valid_root.rglob("*")
        if path.is_file() and path.suffix == ".py" and "__pycache__" not in path.parts
    ]
    return semantic_artifact_hash(
        {"files": sorted(files, key=lambda item: item["path"]), "nodeids": sorted(nodeids)}
    )


def _test_materials_hash(test_path: Path) -> str:
    root = test_path.parent
    files = [
        (path.relative_to(root).as_posix(), path)
        for path in root.rglob("*")
        if path.is_file()
        and path != test_path
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
    ]
    return labeled_files_hash(files)


def _mutmut_execution_metadata(workspace: Path) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for path in sorted((workspace / "mutants").rglob("*.meta")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        durations = payload.get("durations_by_key", {})
        estimates = payload.get("estimated_durations_by_key", {})
        exit_codes = payload.get("exit_code_by_key", {})
        for name in set(durations) | set(estimates) | set(exit_codes):
            metadata[name] = {
                "duration_seconds": durations.get(name),
                "estimated_test_duration_seconds": estimates.get(name),
                "exit_code": exit_codes.get(name),
            }
    return metadata


def _result_execution_metadata(
    mutant_id: str,
    mutant_name: str,
    *,
    rerun_ids: set[str],
    execution_metadata: dict[str, dict[str, Any]],
    reused_row: dict[str, Any],
) -> dict[str, Any]:
    """Select metadata from the execution that supplied the result status."""
    if mutant_id in rerun_ids:
        return execution_metadata.get(mutant_name, {})
    return reused_row


def _load_previous_result(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload.get("mutation"), dict):
        mutation = dict(payload["mutation"])
        for key in (
            "catalog_hash",
            "sut_hash",
            "collection_policy",
            "generated_at",
            "participant",
        ):
            if key not in mutation and key in payload:
                mutation[key] = payload[key]
        return mutation
    return payload


def _run_mutants(
    executable: Path,
    workspace: Path,
    names: Sequence[str],
    max_children: int,
    execution_timeout: float | None,
) -> None:
    for start in range(0, len(names), 400):
        chunk = names[start : start + 400]
        completed = _run(
            [
                str(executable),
                "run",
                "--max-children",
                str(max_children),
                *chunk,
            ],
            workspace,
            timeout=execution_timeout,
        )
        if completed.returncode:
            raise RuntimeError(f"mutmut run failed:\n{completed.stdout}")


def _covering_tests(
    python: Path, workspace: Path, names: Sequence[str]
) -> dict[str, list[str]]:
    names_path = workspace / ".covering-test-names.json"
    output_path = workspace / ".covering-tests.json"
    names_path.write_text(json.dumps(list(names)), encoding="utf-8")
    helper = """
import json
from pathlib import Path
import sys

from mutmut.__main__ import load_stats, tests_for_mutant_names

if not load_stats():
    raise SystemExit("Mutmut stats are unavailable")
names = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
results = {}
for name in names:
    try:
        tests = tests_for_mutant_names([name])
        results[name] = sorted({test.split("[", 1)[0] for test in tests})
    except (KeyError, ValueError):
        results[name] = []
Path(sys.argv[2]).write_text(json.dumps(results), encoding="utf-8")
"""
    completed = _run(
        [str(python), "-c", helper, str(names_path), str(output_path)], workspace
    )
    if completed.returncode or not output_path.is_file():
        raise RuntimeError(f"covering-test extraction failed:\n{completed.stdout}")
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("covering-test extraction returned invalid JSON")
    return payload


def _catalog_summary(
    catalog: dict[str, Any],
    results: Sequence[dict[str, Any]],
    *,
    exclude_duplicates: bool,
) -> dict[str, dict[str, Any]]:
    summary_function = (
        layered_weighted_mutation_summary
        if catalog.get("catalog_kind") == "sampled"
        else layered_mutation_summary
    )
    return summary_function(results, exclude_duplicates=exclude_duplicates)


def collect_mutation_score(args: argparse.Namespace) -> dict[str, Any]:
    if args.confirmation_batch_size <= 0:
        raise ValueError("confirmation batch size must be positive")
    args.repo_root = args.repo_root.resolve()
    args.python = args.python.expanduser().absolute()
    test_path = args.test_path.resolve()
    catalog = load_catalog(args.catalog.resolve())
    if catalog.get("catalog_kind") == "full_sut_raw" or any(
        item.get("workload_layer") == "out_of_scope" for item in catalog["mutants"]
    ):
        raise ValueError("participant collection requires a task-relevant catalog")
    python_version_result = _run(
        [str(args.python), "-c", "import platform; print(platform.python_version())"],
        args.repo_root,
    )
    if python_version_result.returncode:
        raise RuntimeError("could not determine collection Python version")
    python_version = python_version_result.stdout.strip()
    policy = build_execution_policy(
        timeout_multiplier=args.timeout_multiplier,
        timeout_constant=args.timeout_constant,
        timeout_retry_count=args.timeout_retry_count,
        confirm_kills=args.confirm_kills,
        confirmation_protocol="independent_second_execution_v3_incremental",
        exclude_duplicates=args.exclude_duplicates,
        test_timeout=args.test_timeout,
        execution_timeout=args.execution_timeout,
    )
    previous_result = _load_previous_result(args.previous_result)
    evidence = load_evidence(args.reliable_kill_evidence)
    actual_sut_hash = sut_hash(args.repo_root / "markdown_it")
    if actual_sut_hash != catalog.get("sut_hash"):
        raise ValueError("participant SUT hash does not match the fixed catalog")
    error_rates = _error_payload(args.error_rates, test_path, args)
    all_results = _test_results(error_rates)
    valid_results = [item for item in all_results if item.classification == "valid"]
    catalog_mutants = catalog["mutants"]
    only_mutate = catalog.get("only_mutate", [])
    if not isinstance(only_mutate, list) or not all(
        isinstance(path, str) for path in only_mutate
    ):
        raise ValueError("catalog only_mutate must be a string array")

    with tempfile.TemporaryDirectory(prefix="mutation-participant-") as directory:
        workspace = Path(directory)
        shutil.copytree(args.repo_root / "markdown_it", workspace / "markdown_it")
        shutil.copy2(args.repo_root / "pyproject.toml", workspace / "pyproject.toml")
        _copy_submission_resources(args.repo_root, test_path, workspace)
        valid_root = workspace / "tests/valid_participant"
        valid_root.mkdir(parents=True)
        nodeids: list[str] = []
        if valid_results:
            absolute_nodeids = _isolated_valid_nodeids(
                test_path=test_path,
                repo_root=args.repo_root,
                temp_root=valid_root,
                valid_results=valid_results,
            )
            nodeids = [
                str(Path(nodeid.split("::", 1)[0]).relative_to(workspace))
                + "::"
                + nodeid.split("::", 1)[1]
                for nodeid in absolute_nodeids
            ]
            baseline = _run(
                [str(args.python), "-m", "pytest", "-q", *nodeids],
                workspace,
                timeout=args.test_timeout,
            )
            if baseline.returncode:
                raise RuntimeError(f"valid-only baseline failed:\n{baseline.stdout}")

        test_artifact_hash = _valid_test_artifact_hash(valid_root, nodeids)
        context = build_execution_context(
            catalog,
            test_artifact_hash=test_artifact_hash,
            test_materials_hash=_test_materials_hash(test_path),
            python_version=python_version,
        )
        context_hash = execution_context_hash(context)
        participant_commit = args.participant_commit or ""
        if not participant_commit:
            participant_commit_result = _run(
                ["git", "rev-parse", "HEAD"], args.repo_root
            )
            participant_commit = (
                participant_commit_result.stdout.strip()
                if participant_commit_result.returncode == 0
                else ""
            )
        previous_result = upgrade_legacy_result(
            previous_result,
            context=context,
            participant_commit=participant_commit,
        )
        migrated_confirmations = 0
        if previous_result is not None:
            migrated_confirmations = migrate_legacy_confirmations(
                previous_result,
                evidence,
                participant_id=args.participant_id,
                context=context,
            )
            if migrated_confirmations and args.reliable_kill_evidence:
                persist_evidence(args.reliable_kill_evidence, evidence)

        reuse_plan = plan_result_reuse(
            catalog_mutants,
            previous_result,
            current_context_hash=context_hash,
            current_policy=policy,
            backfill_missing_durations=args.backfill_missing_durations,
        )
        reused_by_id = reuse_plan["reused"]
        rerun_ids = set(reuse_plan["rerun_ids"])

        statuses: dict[str, str]
        executable = args.python.expanduser().absolute().parent / "mutmut"
        if not executable.is_file():
            raise ValueError(f"mutmut executable not found: {executable}")
        execution_metadata: dict[str, dict[str, Any]] = {}
        if not valid_results:
            statuses = {item["mutant_name"]: "no_tests" for item in catalog_mutants}
        else:
            _write_config(
                workspace,
                nodeids,
                only_mutate,
                timeout_multiplier=args.timeout_multiplier,
                timeout_constant=args.timeout_constant,
            )
            version = _run([str(executable), "--version"], workspace)
            if version.returncode or version.stdout.strip() != catalog["tool_version"]:
                found_version = version.stdout.strip()
                raise RuntimeError(
                    "Mutmut version does not match catalog: "
                    f"expected {catalog['tool_version']}, found {found_version}"
                )
            names_by_id = {
                item["mutant_id"]: item["mutant_name"] for item in catalog_mutants
            }
            names = [names_by_id[mutant_id] for mutant_id in reuse_plan["rerun_ids"]]
            if names:
                _run_mutants(
                    executable,
                    workspace,
                    names,
                    args.max_children,
                    args.execution_timeout,
                )
                statuses = _mutmut_results(executable, workspace)
                for _attempt in range(args.timeout_retry_count):
                    timeout_names = [
                        name for name in names if statuses.get(name) == "timeout"
                    ]
                    if not timeout_names:
                        break
                    _run_mutants(
                        executable,
                        workspace,
                        timeout_names,
                        1,
                        args.execution_timeout,
                    )
                    statuses = _mutmut_results(executable, workspace)
                execution_metadata = _mutmut_execution_metadata(workspace)
            else:
                statuses = {}

        for item in catalog_mutants:
            if item["mutant_id"] in reused_by_id:
                statuses[item["mutant_name"]] = reused_by_id[item["mutant_id"]][
                    "status"
                ]

        kill_confirmations: dict[str, str] = {}
        confirmation_metadata: dict[str, dict[str, Any]] = {}
        reused_confirmed_kills = 0
        names_to_confirm: list[str] = []
        if args.confirm_kills and valid_results:
            item_by_name = {item["mutant_name"]: item for item in catalog_mutants}
            for item in catalog_mutants:
                name = item["mutant_name"]
                if statuses.get(name) != "killed":
                    continue
                reliable = reliable_evidence_for_mutant(
                    evidence,
                    mutant_id=item["mutant_id"],
                    catalog_hash=catalog["catalog_hash"],
                    sut_hash=actual_sut_hash,
                )
                if reliable:
                    kill_confirmations[name] = "confirmed"
                    reused_confirmed_kills += 1
                else:
                    names_to_confirm.append(name)
            for start in range(0, len(names_to_confirm), args.confirmation_batch_size):
                batch = sorted(
                    names_to_confirm[start : start + args.confirmation_batch_size]
                )
                _run_mutants(
                    executable,
                    workspace,
                    batch,
                    args.max_children,
                    args.execution_timeout,
                )
                repeated_statuses = _mutmut_results(executable, workspace)
                batch_metadata = _mutmut_execution_metadata(workspace)
                for name in batch:
                    repeated = repeated_statuses.get(name)
                    kill_confirmations[name] = (
                        "confirmed" if repeated == "killed" else "flaky"
                    )
                    confirmation_metadata[name] = batch_metadata.get(name, {})
                    if repeated != "killed":
                        continue
                    item = item_by_name[name]
                    timing = confirmation_metadata[name]
                    if timing.get("exit_code") != 1:
                        raise RuntimeError(
                            f"confirmed kill {name} is missing Mutmut exit code 1"
                        )
                    estimated = timing.get("estimated_test_duration_seconds")
                    record = {
                        "schema_version": 1,
                        "mutant_id": item["mutant_id"],
                        "catalog_hash": catalog["catalog_hash"],
                        "catalog_identity_hash": context["catalog_identity_hash"],
                        "sut_hash": actual_sut_hash,
                        "test_artifact_hash": test_artifact_hash,
                        "execution_context_hash": context_hash,
                        "participant_id": args.participant_id,
                        "confirmed_status": "reliably_killed",
                        "exit_code": timing.get("exit_code"),
                        "duration_seconds": timing.get("duration_seconds"),
                        "confirmed_at": datetime.now(timezone.utc).isoformat(),
                        "timeout_used": (
                            timeout_limit(policy, float(estimated))
                            if isinstance(estimated, (int, float))
                            else None
                        ),
                        "python_version": context["python_version"],
                        "mutmut_version": context["mutmut_version"],
                        "valid_only_protocol": RUNNER_PROTOCOL,
                        "evidence_quality": "direct_independent_confirmation",
                    }
                    add_evidence(evidence, record)
                if args.reliable_kill_evidence:
                    persist_evidence(args.reliable_kill_evidence, evidence)

        rerun_audit_names = [
            item["mutant_name"]
            for item in catalog_mutants
            if item["mutant_id"] in rerun_ids
            and statuses.get(item["mutant_name"]) != "killed"
        ]
        covering_tests_by_name = (
            _covering_tests(args.python, workspace, rerun_audit_names)
            if valid_results and rerun_audit_names
            else {}
        )
        results: list[dict[str, Any]] = []
        for catalog_item in catalog_mutants:
            name = catalog_item["mutant_name"]
            raw_status = statuses.get(name)
            if raw_status is None:
                raise RuntimeError(f"Mutmut did not report catalog mutant {name}")
            status = raw_status
            reused_row = reused_by_id.get(catalog_item["mutant_id"], {})
            timing = _result_execution_metadata(
                catalog_item["mutant_id"],
                name,
                rerun_ids=rerun_ids,
                execution_metadata=execution_metadata,
                reused_row=reused_row,
            )
            confirmation_timing = _result_execution_metadata(
                catalog_item["mutant_id"],
                name,
                rerun_ids=rerun_ids,
                execution_metadata=confirmation_metadata,
                reused_row=reused_row,
            )
            covering_tests = covering_tests_by_name.get(
                name, reused_row.get("covering_tests", [])
            )
            results.append(
                {
                    **catalog_item,
                    "status": status,
                    "raw_status": raw_status,
                    "covering_tests": covering_tests,
                    "possible_killer": None,
                    "kill_confirmation": kill_confirmations.get(name, "not_requested"),
                    "flaky_kill": kill_confirmations.get(name) == "flaky",
                    "duration_seconds": timing.get("duration_seconds"),
                    "estimated_test_duration_seconds": timing.get(
                        "estimated_test_duration_seconds"
                    ),
                    "exit_code": timing.get("exit_code"),
                    "confirmation_duration_seconds": confirmation_timing.get(
                        "confirmation_duration_seconds",
                        confirmation_timing.get("duration_seconds"),
                    ),
                    "confirmation_exit_code": confirmation_timing.get(
                        "confirmation_exit_code",
                        confirmation_timing.get("exit_code"),
                    ),
                    "result_reused": catalog_item["mutant_id"] in reused_by_id,
                }
            )

        cache_statistics = {
            **reuse_plan["statistics"],
            "reused_confirmed_kills": reused_confirmed_kills,
            "rerun_previous_timeouts": reuse_plan["statistics"][
                "rerun_previous_timeouts"
            ],
            "rerun_policy_affected": reuse_plan["statistics"][
                "rerun_policy_affected"
            ],
            "rerun_missing_durations": reuse_plan["statistics"][
                "rerun_missing_durations"
            ],
            "backfill_missing_durations": args.backfill_missing_durations,
            "new_kills_to_confirm": len(names_to_confirm),
            "invalidated_context_mismatch": reuse_plan["statistics"][
                "invalidated_context_mismatch"
            ],
            "migrated_legacy_confirmations": migrated_confirmations,
        }

    summary: dict[str, Any] = {
        "baseline_valid_only_passed": True,
        "valid_tests_included": len(valid_results),
        "invalid_tests_excluded": len(all_results) - len(valid_results),
        **_catalog_summary(
            catalog, results, exclude_duplicates=args.exclude_duplicates
        ),
    }
    payload = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection_status": "success",
        "baseline_valid_only_passed": True,
        "infrastructure_error": False,
        "test_path": str(test_path),
        "catalog_hash": catalog["catalog_hash"],
        "baseline_commit": catalog["baseline_commit"],
        "sut_hash": actual_sut_hash,
        "workload_hashes": catalog.get("workload_hashes"),
        "material_hashes": catalog.get("material_hashes"),
        "execution_context": context,
        "execution_context_hash": context_hash,
        "execution_policy": policy,
        "execution_policy_hash": execution_policy_hash(policy),
        "cache_statistics": cache_statistics,
        "exclude_duplicates": args.exclude_duplicates,
        "summary": summary,
        "mutants": results,
    }
    if args.output:
        write_json(args.output, payload)
    if args.audit_csv:
        write_csv(
            args.audit_csv,
            AUDIT_COLUMNS,
            (
                {
                    **item,
                    "covering_tests": ";".join(item["covering_tests"]),
                    "show_command": f"mutmut show '{item['mutant_name']}'",
                    "tests_command": f"mutmut tests-for-mutant '{item['mutant_name']}'",
                    "rerun_command": f"mutmut run '{item['mutant_name']}'",
                }
                for item in results
                if item["status"] != "killed"
            ),
        )
    if args.test_review_csv:
        write_csv(
            args.test_review_csv,
            TEST_REVIEW_COLUMNS,
            _test_review_rows(all_results),
        )
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect one participant Mutation Score."
    )
    parser.add_argument("test_path", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--error-rates", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--audit-csv", type=Path)
    parser.add_argument("--test-review-csv", type=Path)
    parser.add_argument("--max-children", type=int, default=4)
    parser.add_argument("--test-timeout", type=float, default=120.0)
    parser.add_argument("--execution-timeout", type=float)
    parser.add_argument("--timeout-multiplier", type=float, default=5.0)
    parser.add_argument("--timeout-constant", type=float, default=0.5)
    parser.add_argument("--timeout-retry-count", type=int, default=1)
    parser.add_argument("--confirm-kills", action="store_true")
    parser.add_argument("--previous-result", type=Path)
    parser.add_argument(
        "--backfill-missing-durations",
        action="store_true",
        help=(
            "rerun matching cached rows that lack duration metadata; this is an "
            "explicit maintenance mode and is never enabled by ordinary resume"
        ),
    )
    parser.add_argument("--reliable-kill-evidence", type=Path)
    parser.add_argument("--participant-id", default="single-participant")
    parser.add_argument("--participant-commit")
    parser.add_argument("--confirmation-batch-size", type=int, default=25)
    parser.add_argument("--exclude-duplicates", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = collect_mutation_score(args)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not args.quiet:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
