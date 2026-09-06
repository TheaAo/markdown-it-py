from __future__ import annotations

import argparse
import ast
from collections import Counter
from collections.abc import Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
from time import perf_counter
from typing import Any

try:
    from scripts.metric_collection.classify_mutation_operators import (
        classify_operator_family,
    )
    from scripts.metric_collection.mutation_common import (
        catalog_hash,
        changed_code,
        changed_lines_from_diff,
        diff_fingerprint,
        files_hash,
        function_from_mutant_name,
        normalize_diff,
        parse_mutmut_results,
        stable_mutant_id,
        sut_hash,
        write_csv,
        write_json,
    )
except ModuleNotFoundError:  # pragma: no cover
    from classify_mutation_operators import (  # type: ignore[no-redef]
        classify_operator_family,
    )
    from mutation_common import (  # type: ignore[no-redef]
        catalog_hash,
        changed_code,
        changed_lines_from_diff,
        diff_fingerprint,
        files_hash,
        function_from_mutant_name,
        normalize_diff,
        parse_mutmut_results,
        stable_mutant_id,
        sut_hash,
        write_csv,
        write_json,
    )


WORKLOAD_FILES = {
    "specified": "mutation_specified_workload.py",
    "extended": "mutation_extended_workload.py",
}
WORKLOAD_SUPPORT = "mutation_workload_common.py"
TRACEABILITY = (
    {
        "requirement": "complete_specification",
        "layer": "specified",
        "source": "assignment and spec.md/test_file.html",
        "test": "test_complete_specification",
        "rationale": "Exact full-file CommonMark regression required by the task.",
    },
    {
        "requirement": "official_commonmark_examples",
        "layer": "specified",
        "source": "assignment and commonmark.json",
        "test": "test_commonmark_examples",
        "rationale": "All provided official examples are required; none are sampled.",
    },
    {
        "requirement": "ruler_after",
        "layer": "specified",
        "source": "assignment",
        "test": "test_ruler_after_executes_rule",
        "rationale": "Checks only the explicitly requested execution behavior.",
    },
    {
        "requirement": "missing_cli_file",
        "layer": "specified",
        "source": "assignment",
        "test": "test_cli_missing_file_exits_abnormally",
        "rationale": "Checks the required SystemExit and abnormal exit code.",
    },
    {
        "requirement": "non_utf8_cli_file",
        "layer": "specified",
        "source": "assignment",
        "test": "test_cli_handles_non_utf8_file",
        "rationale": "Latin-1 is a deterministic non-UTF-8 equivalence class.",
    },
    {
        "requirement": "rendering_boundaries",
        "layer": "extended_only",
        "source": "boundary and state analysis",
        "test": (
            "test_render_is_deterministic_and_handles_unicode;test_render_empty_input"
        ),
        "rationale": "Adds newline, Unicode, empty-input, and repeated-use paths.",
    },
    {
        "requirement": "ruler_after_boundaries",
        "layer": "extended_only",
        "source": "Ruler public API and control-flow analysis",
        "test": "test_ruler_after_*",
        "rationale": "Adds position, cache invalidation, and missing-anchor paths.",
    },
    {
        "requirement": "cli_path_boundaries",
        "layer": "extended_only",
        "source": "CLI public API and error-path analysis",
        "test": (
            "test_cli_directory_path_reports_error;"
            "test_cli_missing_unicode_path_reports_error"
        ),
        "rationale": "Adds directory and Unicode/space path equivalence classes.",
    },
    {
        "requirement": "non_utf8_boundaries",
        "layer": "extended_only",
        "source": "encoding equivalence-class analysis",
        "test": "test_cli_handles_additional_non_utf8_classes",
        "rationale": (
            "Adds UTF-16 BOM and invalid-byte inputs with baseline-defined behavior."
        ),
    },
)
CATALOG_COLUMNS = (
    "identity_schema",
    "mutant_id",
    "mutant_name",
    "workload_layer",
    "module",
    "function",
    "source_line",
    "changed_source_lines",
    "coverage_source_lines",
    "operator_family",
    "covered_by_specified",
    "covered_by_extended",
    "mapping_status",
    "original_code",
    "mutated_code",
    "diff",
    "reference_status",
    "review_status",
    "review_notes",
)


def _traceability_rows() -> list[dict[str, str]]:
    return [
        {
            **item,
            "review_status": "unreviewed",
            "reviewer": "",
            "review_notes": "",
        }
        for item in TRACEABILITY
    ]


def _run(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _archive(repo_root: Path, ref: str, paths: Sequence[str], target: Path) -> None:
    archive_path = target.parent / f"{target.name}.tar"
    with archive_path.open("wb") as stream:
        completed = subprocess.run(
            ["git", "archive", ref, *paths],
            cwd=repo_root,
            stdout=stream,
            stderr=subprocess.PIPE,
            check=False,
        )
    if completed.returncode:
        raise RuntimeError(completed.stderr.decode(errors="replace").strip())
    target.mkdir(parents=True)
    with tarfile.open(archive_path) as archive:
        archive.extractall(target, filter="data")
    archive_path.unlink()


def _prepare_workspace(
    repo_root: Path, baseline_ref: str, workspace: Path, only_mutate: Sequence[str]
) -> None:
    _archive(
        repo_root,
        baseline_ref,
        ["markdown_it", "pyproject.toml", "tests/task/materials"],
        workspace,
    )
    for filename in (*WORKLOAD_FILES.values(), WORKLOAD_SUPPORT):
        shutil.copy2(Path(__file__).with_name(filename), workspace / filename)
    shutil.copytree(
        workspace / "tests/task/materials", workspace / "mutation_materials"
    )
    mutation_filter = ""
    if only_mutate:
        mutation_filter = (
            "only_mutate=\n" + "\n".join(f"    {path}" for path in only_mutate) + "\n"
        )
    test_selection = "\n".join(
        f"    {filename}" for filename in WORKLOAD_FILES.values()
    )
    also_copy = "\n".join(
        f"    {filename}" for filename in (*WORKLOAD_FILES.values(), WORKLOAD_SUPPORT)
    )
    (workspace / "setup.cfg").write_text(
        "[mutmut]\n"
        "source_paths=markdown_it/\n"
        f"{mutation_filter}"
        "pytest_add_cli_args_test_selection=\n"
        f"{test_selection}\n"
        "also_copy=\n"
        f"{also_copy}\n"
        "    mutation_materials/\n"
        "use_setproctitle=false\n"
        "track_dependencies=false\n",
        encoding="utf-8",
    )


def _coverage(
    python: Path, workspace: Path, workload: str
) -> tuple[dict[str, set[int]], dict[str, Any], float]:
    data_file = workspace / f".{workload}.coverage"
    report_file = workspace / f"{workload}-coverage.json"
    started = perf_counter()
    completed = _run(
        [
            str(python),
            "-m",
            "coverage",
            "run",
            "--branch",
            "--source",
            "markdown_it",
            "--data-file",
            str(data_file),
            "-m",
            "pytest",
            "-q",
            WORKLOAD_FILES[workload],
        ],
        workspace,
    )
    if completed.returncode:
        raise RuntimeError(f"{workload} workload failed:\n{completed.stdout}")
    duration = perf_counter() - started
    completed = _run(
        [
            str(python),
            "-m",
            "coverage",
            "json",
            "--data-file",
            str(data_file),
            "-o",
            str(report_file),
        ],
        workspace,
    )
    if completed.returncode:
        raise RuntimeError(f"{workload} coverage export failed:\n{completed.stdout}")
    payload = json.loads(report_file.read_text(encoding="utf-8"))
    executed = {
        path: set(details["executed_lines"])
        for path, details in payload["files"].items()
    }
    report = {
        "totals": payload["totals"],
        "modules": {
            path: details["summary"]
            for path, details in sorted(payload["files"].items())
        },
    }
    return executed, report, duration


def _workspace_workload_hashes(workspace: Path) -> dict[str, str]:
    materials = [
        workspace / "mutation_materials" / filename
        for filename in ("spec.md", "test_file.html", "commonmark.json")
    ]
    support = workspace / WORKLOAD_SUPPORT
    return {
        layer: files_hash([workspace / filename, support, *materials], workspace)
        for layer, filename in WORKLOAD_FILES.items()
    }


def _workspace_material_hashes(workspace: Path) -> dict[str, str]:
    material_root = workspace / "mutation_materials"
    return {
        path.relative_to(material_root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted(material_root.rglob("*"))
        if path.is_file()
    }


def _show_mutant(executable: Path, workspace: Path, mutant_name: str) -> str:
    completed = _run([str(executable), "show", mutant_name], workspace)
    if completed.returncode:
        raise RuntimeError(f"mutmut show failed for {mutant_name}:\n{completed.stdout}")
    marker = completed.stdout.find("--- markdown_it/")
    if marker < 0:
        raise ValueError(f"mutmut show returned no source diff for {mutant_name}")
    return normalize_diff(completed.stdout[marker:])


def _show_mutants(
    python: Path, workspace: Path, mutant_names: Sequence[str]
) -> dict[str, dict[str, str]]:
    names_path = workspace / ".catalog-mutant-names.json"
    output_path = workspace / ".catalog-mutant-diffs.json"
    names_path.write_text(json.dumps(list(mutant_names)), encoding="utf-8")
    helper = """
import json
from pathlib import Path
import sys

from mutmut.__main__ import (
    Config,
    SourceFileMutationData,
    get_diff_for_mutant,
    walk_mutatable_files,
)

Config.ensure_loaded()
names = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
path_by_name = {}
for path in walk_mutatable_files():
    mutation_data = SourceFileMutationData(path=path)
    mutation_data.load()
    for name in mutation_data.exit_code_by_key:
        path_by_name[name] = mutation_data.path
results = {}
for name in names:
    try:
        path = path_by_name[name]
        results[name] = {"diff": get_diff_for_mutant(name, path=path)}
    except Exception as exc:
        results[name] = {"error": f"{type(exc).__name__}: {exc}"}
Path(sys.argv[2]).write_text(json.dumps(results), encoding="utf-8")
"""
    completed = _run(
        [str(python), "-c", helper, str(names_path), str(output_path)], workspace
    )
    if completed.returncode or not output_path.is_file():
        raise RuntimeError(f"bulk Mutmut diff extraction failed:\n{completed.stdout}")
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("bulk Mutmut diff extraction returned invalid JSON")
    return payload


def _module_from_diff(diff: str) -> str:
    first_line = diff.splitlines()[0]
    if not first_line.startswith("--- "):
        raise ValueError("unexpected mutant diff header")
    return first_line[4:].strip()


def _absolute_source_line(
    workspace: Path, module: str, mutant_name: str, diff: str
) -> int:
    return _absolute_source_lines(workspace, module, mutant_name, diff)[0]


def _absolute_source_lines(
    workspace: Path, module: str, mutant_name: str, diff: str
) -> tuple[int, ...]:
    local_lines = changed_lines_from_diff(diff)
    function_name = function_from_mutant_name(mutant_name)
    tree = ast.parse((workspace / module).read_text(encoding="utf-8"))
    name_parts = mutant_name.split("ǁ")
    class_name = name_parts[-2] if len(name_parts) >= 3 else None
    search_root: ast.AST = tree
    if class_name is not None:
        classes = [
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        ]
        if len(classes) == 1:
            search_root = classes[0]
    candidates = [
        node
        for node in ast.walk(search_root)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    ]
    if len(candidates) == 1:
        return tuple(candidates[0].lineno + line - 1 for line in local_lines)
    return local_lines


def _coverage_source_lines(
    workspace: Path, module: str, changed_source_lines: Sequence[int]
) -> tuple[int, ...]:
    tree = ast.parse((workspace / module).read_text(encoding="utf-8"))
    statements = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.stmt) and node.end_lineno is not None
    ]
    anchors: list[int] = []
    for source_line in changed_source_lines:
        enclosing = [
            node
            for node in statements
            if node.lineno <= source_line <= node.end_lineno
        ]
        if not enclosing:
            anchors.append(source_line)
            continue
        statement = min(
            enclosing,
            key=lambda node: (node.end_lineno - node.lineno, -node.lineno),
        )
        anchors.append(statement.lineno)
    return tuple(dict.fromkeys(anchors))


def _covered(
    executed: dict[str, set[int]], module: str, source_lines: Sequence[int]
) -> bool:
    normalized = module.removeprefix("./")
    return bool(set(source_lines).intersection(executed.get(normalized, set())))


def classify_workload_layer(
    covered_by_specified: bool, covered_by_extended: bool
) -> str:
    if covered_by_specified:
        return "specified"
    if covered_by_extended:
        return "extended_only"
    return "out_of_scope"


def derive_task_relevant_mutants(
    raw_mutants: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [item for item in raw_mutants if item["workload_layer"] != "out_of_scope"]


def _run_catalog(
    repo_root: Path,
    baseline_ref: str,
    mutmut_python: Path,
    root: Path,
    run_number: int,
    max_children: int,
    only_mutate: Sequence[str],
) -> dict[str, Any]:
    workspace = root / f"catalog-run-{run_number}"
    _prepare_workspace(repo_root, baseline_ref, workspace, only_mutate)
    executable = mutmut_python.expanduser().absolute().parent / "mutmut"
    version_result = _run([str(executable), "--version"], workspace)
    if version_result.returncode:
        raise RuntimeError(f"could not read Mutmut version:\n{version_result.stdout}")
    version = version_result.stdout.strip()
    if "3.7.0" not in version:
        raise RuntimeError(f"Mutmut 3.7.0 is required, found: {version}")
    specified_lines, specified_totals, specified_duration = _coverage(
        mutmut_python, workspace, "specified"
    )
    extended_lines, extended_totals, extended_duration = _coverage(
        mutmut_python, workspace, "extended"
    )
    frozen_sut_hash = sut_hash(workspace / "markdown_it")
    frozen_workload_hashes = _workspace_workload_hashes(workspace)
    frozen_material_hashes = _workspace_material_hashes(workspace)
    mutation_started = perf_counter()
    completed = _run(
        [str(executable), "run", "--max-children", str(max_children)], workspace
    )
    mutation_duration = perf_counter() - mutation_started
    if completed.returncode:
        raise RuntimeError(f"mutmut catalog run failed:\n{completed.stdout}")
    results_output = _run([str(executable), "results", "--all", "true"], workspace)
    results = parse_mutmut_results(results_output.stdout)
    shown_mutants = _show_mutants(mutmut_python, workspace, sorted(results))
    raw_mutants: list[dict[str, Any]] = []
    normalization_failures: list[dict[str, str]] = []
    mapping_failures = 0
    for mutant_name, reference_status in sorted(results.items()):
        try:
            shown = shown_mutants.get(mutant_name)
            if not isinstance(shown, dict) or not isinstance(shown.get("diff"), str):
                reason = shown.get("error", "missing bulk diff") if shown else "missing bulk diff"
                raise ValueError(str(reason))
            diff = normalize_diff(shown["diff"])
            module = _module_from_diff(diff)
        except (OSError, RuntimeError, ValueError) as exc:
            normalization_failures.append(
                {
                    "mutant_name": mutant_name,
                    "reference_status": reference_status,
                    "reason": str(exc),
                }
            )
            continue
        try:
            source_lines = _absolute_source_lines(workspace, module, mutant_name, diff)
            coverage_source_lines = _coverage_source_lines(
                workspace, module, source_lines
            )
            mapping_status = "mapped"
        except (OSError, SyntaxError, ValueError):
            source_lines = changed_lines_from_diff(diff)
            coverage_source_lines = source_lines
            mapping_status = "fallback_diff_line"
            mapping_failures += 1
        covered_by_specified = _covered(
            specified_lines, module, coverage_source_lines
        )
        covered_by_extended = _covered(extended_lines, module, coverage_source_lines)
        workload_layer = classify_workload_layer(
            covered_by_specified, covered_by_extended
        )
        source_line = source_lines[0]
        original_code, mutated_code = changed_code(diff)
        raw_mutants.append(
            {
                "identity_schema": 3,
                "mutant_id": stable_mutant_id(module, mutant_name, source_line, diff),
                "mutant_name": mutant_name,
                "module": module,
                "function": function_from_mutant_name(mutant_name),
                "source_line": source_line,
                "changed_source_lines": list(source_lines),
                "coverage_source_lines": list(coverage_source_lines),
                "operator_family": classify_operator_family(diff),
                "original_code": original_code,
                "mutated_code": mutated_code,
                "diff": diff,
                "reference_status": reference_status,
                "covered_by_specified": covered_by_specified,
                "covered_by_extended": covered_by_extended,
                "workload_layer": workload_layer,
                "mapping_status": mapping_status,
                "review_status": "unreviewed",
                "review_notes": "",
            }
        )
    raw_mutants.sort(key=lambda item: item["mutant_id"])
    task_mutants = derive_task_relevant_mutants(raw_mutants)
    layer_counts = Counter(item["workload_layer"] for item in raw_mutants)
    coverage_membership_counts = Counter(
        (
            "both"
            if item["covered_by_specified"] and item["covered_by_extended"]
            else "specified_only"
            if item["covered_by_specified"]
            else "extended_only"
            if item["covered_by_extended"]
            else "neither"
        )
        for item in raw_mutants
    )
    metadata = {
        "generated_mutants": len(results),
        "normalized_mutants": len(raw_mutants),
        "normalization_failures": normalization_failures,
        "mapping_failures": mapping_failures,
        "mapping_failure_rate": mapping_failures / len(results) if results else 0.0,
        "reference_status_counts": dict(sorted(Counter(results.values()).items())),
        "task_relevant_mutants": len(task_mutants),
        "specified_mutants": layer_counts["specified"],
        "extended_only_mutants": layer_counts["extended_only"],
        "out_of_scope_mutants": layer_counts["out_of_scope"],
        "coverage_membership_counts": {
            key: coverage_membership_counts[key]
            for key in ("specified_only", "extended_only", "both", "neither")
        },
        "operator_family_counts": dict(
            sorted(Counter(item["operator_family"] for item in raw_mutants).items())
        ),
        "module_counts": dict(
            sorted(Counter(item["module"] for item in raw_mutants).items())
        ),
        "function_counts": dict(
            sorted(
                Counter(
                    f"{item['module']}::{item['function']}" for item in raw_mutants
                ).items()
            )
        ),
        "coverage": {
            "specified": specified_totals,
            "extended": extended_totals,
        },
        "workload_hashes": frozen_workload_hashes,
        "material_hashes": frozen_material_hashes,
        "durations_seconds": {
            "specified_baseline": specified_duration,
            "extended_baseline": extended_duration,
            "reference_mutation_run": mutation_duration,
        },
    }
    return {
        "raw_mutants": raw_mutants,
        "task_mutants": task_mutants,
        "sut_hash": frozen_sut_hash,
        "tool_version": version,
        "python_version": platform.python_version(),
        "metadata": metadata,
    }


def _cosmic_diffs(path: Path) -> set[str]:
    diffs: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        _work, result = json.loads(line)
        if isinstance(result, dict) and isinstance(result.get("diff"), str):
            diffs.add(diff_fingerprint(result["diff"]))
    return diffs


def _catalog_payload(
    *,
    baseline_ref: str,
    baseline_commit: str,
    only_mutate: Sequence[str],
    run: dict[str, Any],
    mutants: list[dict[str, Any]],
    catalog_kind: str,
    generation_comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = run["metadata"]
    return {
        "schema_version": 3,
        "catalog_kind": catalog_kind,
        "creation_mode": "full_sut" if not only_mutate else "only_mutate",
        "tool": "mutmut",
        "tool_version": run["tool_version"],
        "python_version": run["python_version"],
        "baseline_ref": baseline_ref,
        "baseline_commit": baseline_commit,
        "sut_hash": run["sut_hash"],
        "source_paths": ["markdown_it/"],
        "only_mutate": list(only_mutate),
        "scope": (
            "complete raw Mutmut inventory"
            if catalog_kind == "full_sut_raw"
            else "task-relevant specified and extended-only census"
        ),
        "operator_family_method": "normalized_diff_rules_v1",
        "workload_hashes": metadata["workload_hashes"],
        "material_hashes": metadata["material_hashes"],
        "catalog_statistics": metadata,
        "generation_comparison": generation_comparison,
        "catalog_hash": catalog_hash(mutants),
        "traceability": _traceability_rows(),
        "mutants": mutants,
    }


def _csv_rows(mutants: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            **item,
            "changed_source_lines": ";".join(
                str(line) for line in item.get("changed_source_lines", [])
            ),
            "coverage_source_lines": ";".join(
                str(line) for line in item.get("coverage_source_lines", [])
            ),
        }
        for item in mutants
    ]


def _dry_run_report(run: dict[str, Any], baseline_commit: str) -> dict[str, Any]:
    metadata = run["metadata"]
    generated = metadata["generated_mutants"]
    task_relevant = metadata["task_relevant_mutants"]
    mutation_duration = metadata["durations_seconds"]["reference_mutation_run"]
    seconds_per_mutant = mutation_duration / generated if generated else 0.0
    participant_executions = task_relevant * 14
    confirmation_executions = task_relevant
    estimated_seconds = (
        participant_executions + confirmation_executions
    ) * seconds_per_mutant
    reasons: list[str] = []
    if task_relevant > 5000:
        reasons.append("task_relevant_mutants_exceed_5000")
    if estimated_seconds > 72 * 60 * 60:
        reasons.append("estimated_serial_execution_exceeds_72_hours")
    if metadata["mapping_failure_rate"] > 0.01:
        reasons.append("source_line_mapping_failure_exceeds_1_percent")
    if metadata["normalization_failures"]:
        reasons.append("mutmut_could_not_show_all_generated_mutants")
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": baseline_commit,
        "sut_hash": run["sut_hash"],
        "tool_version": run["tool_version"],
        "python_version": run["python_version"],
        "full_raw_mutants": metadata["normalized_mutants"],
        "task_relevant_mutants": task_relevant,
        "specified_mutants": metadata["specified_mutants"],
        "extended_only_mutants": metadata["extended_only_mutants"],
        "out_of_scope_mutants": metadata["out_of_scope_mutants"],
        "coverage_membership_counts": metadata["coverage_membership_counts"],
        "estimated_participant_executions": participant_executions,
        "estimated_global_confirmation_executions": confirmation_executions,
        "measured_durations_seconds": metadata["durations_seconds"],
        "rough_estimate": {
            "reference_seconds_per_generated_mutant": seconds_per_mutant,
            "estimated_serial_seconds": estimated_seconds,
            "estimated_serial_hours": estimated_seconds / 3600,
            "limitations": (
                "Uses reference-workload seconds per raw mutant. Participant test "
                "cost and kill distribution can make the formal run slower or faster."
            ),
        },
        "mapping_failures": metadata["mapping_failures"],
        "mapping_failure_rate": metadata["mapping_failure_rate"],
        "normalization_failures": metadata["normalization_failures"],
        "module_counts": metadata["module_counts"],
        "operator_family_counts": metadata["operator_family_counts"],
        "reference_status_counts": metadata["reference_status_counts"],
        "checkpoint_status": "stop_required" if reasons else "passed",
        "checkpoint_reasons": reasons,
    }


def _write_traceability(output_dir: Path) -> None:
    write_csv(
        output_dir / "workload_traceability.csv",
        (
            "requirement",
            "layer",
            "source",
            "test",
            "rationale",
            "review_status",
            "reviewer",
            "review_notes",
        ),
        _traceability_rows(),
    )


def _write_dry_run(
    output_dir: Path, run: dict[str, Any], report: dict[str, Any]
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "dry_run_report.json", report)
    write_csv(
        output_dir / "dry_run_mutant_inventory.csv",
        CATALOG_COLUMNS,
        _csv_rows(run["raw_mutants"]),
    )
    write_csv(
        output_dir / "counts_by_module.csv",
        ("module", "mutant_count"),
        (
            {"module": key, "mutant_count": value}
            for key, value in run["metadata"]["module_counts"].items()
        ),
    )
    write_csv(
        output_dir / "counts_by_operator_family.csv",
        ("operator_family", "mutant_count"),
        (
            {"operator_family": key, "mutant_count": value}
            for key, value in run["metadata"]["operator_family_counts"].items()
        ),
    )
    (output_dir.parent / "run_report.md").write_text(
        "# Full-SUT Mutation Run Report\n\n"
        "## Dry-Run Checkpoint\n\n"
        f"- Baseline commit: `{report['baseline_commit']}`\n"
        f"- SUT hash: `{report['sut_hash']}`\n"
        f"- Mutmut: `{report['tool_version']}`\n"
        f"- Python: `{report['python_version']}`\n"
        f"- Full raw mutants: {report['full_raw_mutants']}\n"
        f"- Specified mutants: {report['specified_mutants']}\n"
        f"- Extended-only mutants: {report['extended_only_mutants']}\n"
        f"- Out-of-scope mutants: {report['out_of_scope_mutants']}\n"
        f"- Coverage membership: {report['coverage_membership_counts']}\n"
        f"- Estimated participant executions: "
        f"{report['estimated_participant_executions']}\n"
        f"- Estimated global confirmation executions: "
        f"{report['estimated_global_confirmation_executions']}\n"
        f"- Estimated serial hours: "
        f"{report['rough_estimate']['estimated_serial_hours']:.2f}\n"
        f"- Mapping failures: {report['mapping_failures']}\n"
        f"- Checkpoint: `{report['checkpoint_status']}`\n"
        f"- Reasons: {', '.join(report['checkpoint_reasons']) or 'none'}\n\n"
        "The estimate uses reference-workload mutation duration and is not a "
        "guarantee of participant execution time. Formal catalog and participant "
        "sections are added only after the checkpoint is approved.\n",
        encoding="utf-8",
    )


def _write_full_catalogs(
    output_dir: Path,
    raw_payload: dict[str, Any],
    task_payload: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_rows = _csv_rows(raw_payload["mutants"])
    task_rows = _csv_rows(task_payload["mutants"])
    write_json(output_dir / "full_sut_mutant_catalog.json", raw_payload)
    write_csv(output_dir / "full_sut_mutant_catalog.csv", CATALOG_COLUMNS, raw_rows)
    (output_dir / "full_sut_catalog.sha256").write_text(
        raw_payload["catalog_hash"] + "\n", encoding="utf-8"
    )
    write_json(output_dir / "task_relevant_mutant_catalog.json", task_payload)
    write_csv(
        output_dir / "task_relevant_mutant_catalog.csv", CATALOG_COLUMNS, task_rows
    )
    (output_dir / "task_relevant_catalog.sha256").write_text(
        task_payload["catalog_hash"] + "\n", encoding="utf-8"
    )
    write_csv(
        output_dir / "excluded_out_of_scope_mutants.csv",
        CATALOG_COLUMNS,
        (row for row in raw_rows if row["workload_layer"] == "out_of_scope"),
    )
    write_json(
        output_dir / "catalog_derivation_summary.json",
        {
            "full_sut_catalog_hash": raw_payload["catalog_hash"],
            "task_relevant_catalog_hash": task_payload["catalog_hash"],
            "full_raw_mutants": len(raw_payload["mutants"]),
            "task_relevant_mutants": len(task_payload["mutants"]),
            "specified_mutants": sum(
                item["workload_layer"] == "specified"
                for item in task_payload["mutants"]
            ),
            "extended_only_mutants": sum(
                item["workload_layer"] == "extended_only"
                for item in task_payload["mutants"]
            ),
            "out_of_scope_mutants": sum(
                item["workload_layer"] == "out_of_scope"
                for item in raw_payload["mutants"]
            ),
        },
    )
    write_json(
        output_dir / "workload_coverage.json",
        raw_payload["catalog_statistics"]["coverage"],
    )
    write_csv(
        output_dir / "mutant_review.csv",
        (*CATALOG_COLUMNS, "show_command", "tests_command"),
        (
            {
                **row,
                "show_command": f"mutmut show '{row['mutant_name']}'",
                "tests_command": f"mutmut tests-for-mutant '{row['mutant_name']}'",
            }
            for row in task_rows
        ),
    )
    _write_traceability(output_dir)


def build_catalog(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = args.repo_root.resolve()
    args.mutmut_python = args.mutmut_python.expanduser().absolute()
    baseline_result = _run(
        ["git", "rev-parse", f"{args.baseline_ref}^{{commit}}"], repo_root
    )
    if baseline_result.returncode:
        raise RuntimeError(f"could not resolve baseline:\n{baseline_result.stdout}")
    baseline_commit = baseline_result.stdout.strip()
    only_mutate = args.only_mutate or []
    with tempfile.TemporaryDirectory(prefix="mutant-catalog-") as directory:
        root = Path(directory)
        first = _run_catalog(
            repo_root,
            args.baseline_ref,
            args.mutmut_python,
            root,
            1,
            args.max_children,
            only_mutate,
        )
        if args.dry_run:
            report = _dry_run_report(first, baseline_commit)
            _write_dry_run(args.output_dir, first, report)
            return {"dry_run": report, "catalog_statistics": first["metadata"]}
        second = _run_catalog(
            repo_root,
            args.baseline_ref,
            args.mutmut_python,
            root,
            2,
            args.max_children,
            only_mutate,
        )
    deterministic_metadata_fields = (
        "generated_mutants",
        "normalized_mutants",
        "mapping_failures",
        "mapping_failure_rate",
        "task_relevant_mutants",
        "specified_mutants",
        "extended_only_mutants",
        "out_of_scope_mutants",
        "coverage_membership_counts",
        "operator_family_counts",
        "module_counts",
        "function_counts",
        "coverage",
        "workload_hashes",
        "material_hashes",
    )
    if (
        first["sut_hash"] != second["sut_hash"]
        or first["tool_version"] != second["tool_version"]
        or first["python_version"] != second["python_version"]
        or catalog_hash(first["raw_mutants"]) != catalog_hash(second["raw_mutants"])
        or any(
            first["metadata"][field] != second["metadata"][field]
            for field in deterministic_metadata_fields
        )
    ):
        raise RuntimeError("catalog was not reproducible across two generations")
    if (
        first["metadata"]["normalization_failures"]
        or second["metadata"]["normalization_failures"]
    ):
        raise RuntimeError("not all generated mutants could be normalized")
    if (
        first["metadata"]["mapping_failure_rate"] > 0.01
        or second["metadata"]["mapping_failure_rate"] > 0.01
    ):
        raise RuntimeError("source-line mapping failure exceeds 1 percent")
    generation_comparison = {
        "semantic_catalog_hash_match": True,
        "first_raw_catalog_hash": catalog_hash(first["raw_mutants"]),
        "second_raw_catalog_hash": catalog_hash(second["raw_mutants"]),
        "reference_status_counts_match": (
            first["metadata"]["reference_status_counts"]
            == second["metadata"]["reference_status_counts"]
        ),
        "first_reference_status_counts": first["metadata"][
            "reference_status_counts"
        ],
        "second_reference_status_counts": second["metadata"][
            "reference_status_counts"
        ],
        "first_durations_seconds": first["metadata"]["durations_seconds"],
        "second_durations_seconds": second["metadata"]["durations_seconds"],
    }
    raw_payload = _catalog_payload(
        baseline_ref=args.baseline_ref,
        baseline_commit=baseline_commit,
        only_mutate=only_mutate,
        run=first,
        mutants=first["raw_mutants"],
        catalog_kind="full_sut_raw",
        generation_comparison=generation_comparison,
    )
    task_payload = _catalog_payload(
        baseline_ref=args.baseline_ref,
        baseline_commit=baseline_commit,
        only_mutate=only_mutate,
        run=first,
        mutants=first["task_mutants"],
        catalog_kind="task_relevant_census",
        generation_comparison=generation_comparison,
    )
    if args.full_sut:
        _write_full_catalogs(args.output_dir, raw_payload, task_payload)
    else:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_json(args.output_dir / "mutant_catalog.json", task_payload)
        write_csv(
            args.output_dir / "mutant_catalog.csv",
            CATALOG_COLUMNS,
            _csv_rows(task_payload["mutants"]),
        )
        (args.output_dir / "catalog.sha256").write_text(
            task_payload["catalog_hash"] + "\n", encoding="utf-8"
        )
        _write_traceability(args.output_dir)
    return task_payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the fixed Mutmut catalog.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline-ref", default="origin/experiment-base")
    parser.add_argument("--mutmut-python", type=Path, required=True)
    parser.add_argument("--max-children", type=int, default=4)
    parser.add_argument("--only-mutate", action="append")
    parser.add_argument("--full-sut", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cosmic-ray-dump", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("results/metric_collection/mutation/catalog"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.dry_run and not args.full_sut:
        print("error: --dry-run requires --full-sut", file=sys.stderr)
        return 1
    try:
        payload = build_catalog(args)
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    statistics = payload["catalog_statistics"]
    print(f"Specified mutants: {statistics['specified_mutants']}")
    print(f"Extended-only mutants: {statistics['extended_only_mutants']}")
    print(f"Out-of-scope mutants: {statistics['out_of_scope_mutants']}")
    if args.dry_run:
        report = payload["dry_run"]
        print(f"Full raw mutants: {report['full_raw_mutants']}")
        print(
            f"Estimated serial hours: {report['rough_estimate']['estimated_serial_hours']:.2f}"
        )
        print(f"Checkpoint: {report['checkpoint_status']}")
    else:
        print(f"Catalog hash: {payload['catalog_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
