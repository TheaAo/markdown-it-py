from __future__ import annotations

import argparse
import ast
import csv
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Sequence

try:
    from scripts.collect_error_rates import _split_test_file
    from scripts.detect_test_smells_ast import (
        FORMAL_SMELLS,
        RULE_VERSION,
        SmellDecision,
        analyze_tree,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from collect_error_rates import _split_test_file  # type: ignore[no-redef]
    from detect_test_smells_ast import (  # type: ignore[no-redef]
        FORMAL_SMELLS,
        RULE_VERSION,
        SmellDecision,
        analyze_tree,
    )


EXPECTED_TEST_FUNCTIONS = (
    "test_file",
    "test_spec",
    "test_core_after",
    "test_parse_fail",
    "test_non_utf8",
)
PYTEST_SMELL_VERSION = "1.0.5"
TEMPY_COMMIT = "4c945d121d645b52fefb8f1b4f3e6caeec7c9095"
TEMPY_SMELLS = {
    "Conditional Test Logic": "conditional_test_logic",
    "Exception Handling": "exception_handling",
    "Unknown Test": "unknown_test",
}
PYTEST_SMELLS = {
    "Assertion Roullete": "assertion_roulette",
    "Assertion Roulette": "assertion_roulette",
    "Magic Number": "magic_number_test",
    "Magic Number Test": "magic_number_test",
    "Unknown Test": "unknown_test",
    "Conditional Logic": "conditional_test_logic",
    "Conditional Test Logic": "conditional_test_logic",
    "Eager Test": "eager_test",
    "Duplicate Assert": "duplicate_assert",
    "Exception Handling": "exception_handling",
}


def _run(
    command: Sequence[str], cwd: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (
            exc.stdout.decode(errors="replace")
            if isinstance(exc.stdout, bytes)
            else exc.stdout or ""
        )
        stderr = (
            exc.stderr.decode(errors="replace")
            if isinstance(exc.stderr, bytes)
            else exc.stderr or ""
        )
        return subprocess.CompletedProcess(
            command, 124, stdout, stderr + f"\ntimed out after {timeout:g} seconds"
        )


def _load_error_rate(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("error-rate JSON root must be an object")
    metrics = payload.get("metrics", payload)
    if not isinstance(metrics, dict):
        raise ValueError("error-rate JSON does not contain a metrics object")
    return metrics


def _validity_by_source(error_rates: dict[str, Any]) -> dict[str, dict[str, Any]]:
    case_level = error_rates.get("case_level")
    cases = case_level.get("test_cases") if isinstance(case_level, dict) else None
    if not isinstance(cases, list):
        raise ValueError("error-rate JSON is missing case_level.test_cases")
    grouped: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("error-rate test case must be an object")
        source_test = case.get("source_test")
        if isinstance(source_test, str):
            grouped.setdefault(source_test, []).append(case)

    results: dict[str, dict[str, Any]] = {}
    for source_test in EXPECTED_TEST_FUNCTIONS:
        source_cases = grouped.get(source_test, [])
        total = len(source_cases)
        valid = sum(case.get("classification") == "valid" for case in source_cases)
        if valid == 0:
            validity = "invalid"
        elif valid == total:
            validity = "fully_valid"
        else:
            validity = "partially_valid"
        results[source_test] = {
            "generated_nodeids": [
                case.get("nodeid")
                for case in source_cases
                if isinstance(case.get("nodeid"), str)
            ],
            "valid_instance_count": valid,
            "total_instance_count": total,
            "validity": validity,
            "eligible": validity != "invalid",
        }
    return results


def _isolated_source(test_path: Path, eligible: set[str]) -> str:
    support_source, test_blocks = _split_test_file(test_path)
    # pytest-smell 1.0.5 crashes when a file ends in a top-level blank line.
    selected = [
        block.source.rstrip() for block in test_blocks if block.name in eligible
    ]
    # pytest-smell ends a test only after two consecutive top-level blank lines.
    source = support_source.rstrip() + "\n\n\n" + "\n\n\n".join(selected) + "\n"
    # The external parser recognizes four-space indentation only. This copy is
    # evidence input; the final AST decision still uses the unmodified source.
    return source.expandtabs(4)


def _write_evidence(
    evidence_dir: Path | None, name: str, content: str
) -> str | None:
    if evidence_dir is None:
        return None
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = evidence_dir / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def _tool_result(
    *,
    status: str,
    supported_smells: Sequence[str],
    version: str | None = None,
    reason: str | None = None,
    command: Sequence[str] | None = None,
    returncode: int | None = None,
    stdout: str = "",
    stderr: str = "",
    detections: set[tuple[str, str]] | None = None,
    artifacts: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "version": version,
        "supported_smells": list(supported_smells),
        "reason": reason,
        "command": list(command) if command else None,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
        "detections": [
            {"source_test": source_test, "smell": smell}
            for source_test, smell in sorted(detections or set())
        ],
        "artifacts": artifacts or {},
    }


def _run_pytest_smell(
    executable: Path | None,
    isolated_path: Path,
    eligible: set[str],
    evidence_dir: Path | None,
    timeout: float,
) -> dict[str, Any]:
    supported = list(FORMAL_SMELLS)
    if executable is None:
        found = shutil.which("pytest-smell")
        executable = Path(found) if found else None
    if executable is None or not executable.is_file():
        return _tool_result(
            status="not_configured",
            supported_smells=supported,
            version=PYTEST_SMELL_VERSION,
            reason="pytest-smell executable was not supplied or found on PATH",
        )

    tool_python = executable.parent / "python"
    version_command = [
        str(tool_python),
        "-c",
        (
            "import importlib.metadata; "
            "print(importlib.metadata.version('pytest-smell'))"
        ),
    ]
    version_result = _run(version_command, isolated_path.parent, timeout=10)
    installed_version = version_result.stdout.strip()
    if version_result.returncode != 0 or installed_version != PYTEST_SMELL_VERSION:
        return _tool_result(
            status="failed",
            supported_smells=supported,
            version=installed_version or None,
            reason=f"pytest-smell must be version {PYTEST_SMELL_VERSION}",
            command=version_command,
            returncode=version_result.returncode,
            stdout=version_result.stdout,
            stderr=version_result.stderr,
        )

    output_dir = isolated_path.parent / "pytest-smell-output"
    output_dir.mkdir()
    command = [
        str(executable),
        "--tests_path",
        str(isolated_path.parent),
        "--out_path",
        str(output_dir),
        "--verbose",
    ]
    completed = _run(command, isolated_path.parent, timeout)
    csv_path = output_dir / "smells.csv"
    stdout_path = _write_evidence(
        evidence_dir, "pytest-smell.stdout.txt", completed.stdout
    )
    stderr_path = _write_evidence(
        evidence_dir, "pytest-smell.stderr.txt", completed.stderr
    )
    csv_artifact = None
    detections: set[tuple[str, str]] = set()
    if csv_path.exists():
        csv_content = csv_path.read_text(encoding="utf-8")
        csv_artifact = _write_evidence(evidence_dir, "pytest-smell.csv", csv_content)
        with csv_path.open(encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                test_name = row.get("test_name")
                smell = PYTEST_SMELLS.get(row.get("smell", ""))
                if test_name in eligible and smell is not None:
                    detections.add((test_name, smell))
    if completed.returncode != 0 or not csv_path.exists():
        return _tool_result(
            status="failed",
            supported_smells=supported,
            version=PYTEST_SMELL_VERSION,
            reason="pytest-smell did not complete with a readable smells.csv",
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            artifacts={
                "stdout": stdout_path,
                "stderr": stderr_path,
                "csv": csv_artifact,
            },
        )
    return _tool_result(
        status="completed",
        supported_smells=supported,
        version=installed_version,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        detections=detections,
        artifacts={"stdout": stdout_path, "stderr": stderr_path, "csv": csv_artifact},
    )


def _run_tempy(
    tempy_root: Path | None,
    python_executable: str,
    isolated_path: Path,
    eligible: set[str],
    evidence_dir: Path | None,
    timeout: float,
) -> dict[str, Any]:
    supported = list(TEMPY_SMELLS.values())
    if tempy_root is None:
        return _tool_result(
            status="not_configured",
            supported_smells=supported,
            version=TEMPY_COMMIT,
            reason="TEMPY root was not supplied",
        )
    assets = tempy_root / "assets"
    if not assets.is_dir():
        return _tool_result(
            status="failed",
            supported_smells=supported,
            version=TEMPY_COMMIT,
            reason=f"TEMPY assets directory not found: {assets}",
        )
    revision = _run(["git", "rev-parse", "HEAD"], tempy_root, timeout=10)
    if revision.returncode != 0 or revision.stdout.strip() != TEMPY_COMMIT:
        return _tool_result(
            status="failed",
            supported_smells=supported,
            version=revision.stdout.strip() or None,
            reason=f"TEMPY must be checked out at {TEMPY_COMMIT}",
            stdout=revision.stdout,
            stderr=revision.stderr,
        )

    adapter = (
        "import json,sys;"
        "sys.path.insert(0,sys.argv[1]);"
        "from python_parser import PythonParser;"
        "p=PythonParser(sys.argv[2]);"
        "xs=p.start() if p.ast_parser else p.start2();"
        "print('__TEMPY_JSON__'+json.dumps([vars(x) for x in xs]))"
    )
    command = [python_executable, "-c", adapter, str(assets), str(isolated_path)]
    completed = _run(command, tempy_root, timeout)
    stdout_path = _write_evidence(evidence_dir, "tempy.stdout.txt", completed.stdout)
    stderr_path = _write_evidence(evidence_dir, "tempy.stderr.txt", completed.stderr)
    detections: set[tuple[str, str]] = set()
    raw_json = ""
    for line in completed.stdout.splitlines():
        if line.startswith("__TEMPY_JSON__"):
            raw_json = line.removeprefix("__TEMPY_JSON__")
    try:
        items = json.loads(raw_json)
        if not isinstance(items, list):
            raise ValueError("TEMPY result is not an array")
        for item in items:
            if not isinstance(item, dict):
                continue
            test_name = item.get("method_name")
            smell = TEMPY_SMELLS.get(item.get("test_smell_type", ""))
            if test_name in eligible and smell is not None:
                detections.add((test_name, smell))
    except (json.JSONDecodeError, ValueError) as exc:
        return _tool_result(
            status="failed",
            supported_smells=supported,
            version=TEMPY_COMMIT,
            reason=f"TEMPY adapter returned invalid data: {exc}",
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            artifacts={"stdout": stdout_path, "stderr": stderr_path},
        )
    normalized = json.dumps(items, ensure_ascii=False, indent=2) + "\n"
    json_path = _write_evidence(evidence_dir, "tempy.json", normalized)
    if completed.returncode != 0:
        return _tool_result(
            status="failed",
            supported_smells=supported,
            version=TEMPY_COMMIT,
            reason="TEMPY adapter exited unsuccessfully",
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            artifacts={"stdout": stdout_path, "stderr": stderr_path, "json": json_path},
        )
    return _tool_result(
        status="completed",
        supported_smells=supported,
        version=TEMPY_COMMIT,
        command=command,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        detections=detections,
        artifacts={"stdout": stdout_path, "stderr": stderr_path, "json": json_path},
    )


def _pairs(tool: dict[str, Any]) -> set[tuple[str, str]]:
    if tool.get("status") != "completed":
        return set()
    return {
        (item["source_test"], item["smell"])
        for item in tool.get("detections", [])
        if isinstance(item, dict)
    }


def collect_test_smells(
    *,
    test_path: Path,
    error_rates: dict[str, Any],
    pytest_smell_executable: Path | None = None,
    tempy_root: Path | None = None,
    python_executable: str = sys.executable,
    evidence_dir: Path | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    validity = _validity_by_source(error_rates)
    eligible = {name for name, item in validity.items() if item["eligible"]}

    if not eligible:
        tools = {
            "pytest-smell": _tool_result(
                status="not_run",
                supported_smells=FORMAL_SMELLS,
                version=PYTEST_SMELL_VERSION,
                reason="no eligible source tests",
            ),
            "TEMPY": _tool_result(
                status="not_run",
                supported_smells=TEMPY_SMELLS.values(),
                version=TEMPY_COMMIT,
                reason="no eligible source tests",
            ),
        }
        ast_results: dict[str, list[SmellDecision]] = {}
    else:
        isolated_source = _isolated_source(test_path, eligible)
        with tempfile.TemporaryDirectory(prefix="test-smell-static-") as temp_dir:
            isolated_path = Path(temp_dir) / "test_participant.py"
            isolated_path.write_text(isolated_source, encoding="utf-8")
            try:
                original_tree = ast.parse(
                    test_path.read_text(encoding="utf-8", errors="replace"),
                    filename=str(test_path),
                )
                ast_results = analyze_tree(original_tree, eligible)
            except SyntaxError:
                isolated_tree = ast.parse(isolated_source, filename=str(test_path))
                ast_results = analyze_tree(isolated_tree, eligible)
            tools = {
                "pytest-smell": _run_pytest_smell(
                    pytest_smell_executable,
                    isolated_path,
                    eligible,
                    evidence_dir,
                    timeout,
                ),
                "TEMPY": _run_tempy(
                    tempy_root,
                    python_executable,
                    isolated_path,
                    eligible,
                    evidence_dir,
                    timeout,
                ),
            }

    pytest_pairs = _pairs(tools["pytest-smell"])
    tempy_pairs = _pairs(tools["TEMPY"])
    test_results: list[dict[str, Any]] = []
    confirmed_pairs = 0
    smelly_tests = 0
    uncertain_pairs = 0
    per_smell: dict[str, dict[str, int | float | None]] = {
        smell: {"confirmed_count": 0, "uncertain_count": 0}
        for smell in FORMAL_SMELLS
    }

    for source_test in EXPECTED_TEST_FUNCTIONS:
        source_validity = validity[source_test]
        decisions = (
            ast_results.get(source_test, [])
            if source_validity["eligible"]
            else []
        )
        if source_validity["eligible"] and not decisions:
            decisions = [
                SmellDecision(
                    smell=smell,
                    decision="uncertain",
                    lines=[],
                    reason=(
                        "eligible source function could not be resolved in static input"
                    ),
                )
                for smell in FORMAL_SMELLS
            ]
        smell_records = []
        confirmed_for_test = 0
        for decision in decisions:
            decision_payload = asdict(decision)
            decision_payload["external_evidence"] = {
                "pytest-smell": (
                    (source_test, decision.smell) in pytest_pairs
                    if decision.smell in tools["pytest-smell"]["supported_smells"]
                    and tools["pytest-smell"]["status"] == "completed"
                    else None
                ),
                "TEMPY": (
                    (source_test, decision.smell) in tempy_pairs
                    if decision.smell in tools["TEMPY"]["supported_smells"]
                    and tools["TEMPY"]["status"] == "completed"
                    else None
                ),
            }
            smell_records.append(decision_payload)
            if decision.decision == "confirmed":
                confirmed_pairs += 1
                confirmed_for_test += 1
                per_smell[decision.smell]["confirmed_count"] += 1
            elif decision.decision == "uncertain":
                uncertain_pairs += 1
                per_smell[decision.smell]["uncertain_count"] += 1
        if confirmed_for_test:
            smelly_tests += 1
        test_results.append(
            {
                "source_test": source_test,
                **source_validity,
                "has_confirmed_smell": confirmed_for_test > 0,
                "confirmed_smell_count": confirmed_for_test,
                "smells": smell_records,
            }
        )

    eligible_count = len(eligible)
    for counts in per_smell.values():
        counts["rate"] = (
            counts["confirmed_count"] / eligible_count if eligible_count else None
        )
    mean_smells = confirmed_pairs / eligible_count if eligible_count else None
    normalized_density = (
        confirmed_pairs / (eligible_count * len(FORMAL_SMELLS))
        if eligible_count
        else None
    )
    return {
        "protocol_version": "1.0.0",
        "rule_version": RULE_VERSION,
        "test_path": str(test_path),
        "analysis_unit": "source_test_function",
        "total_source_tests": len(EXPECTED_TEST_FUNCTIONS),
        "eligible_test_count": eligible_count,
        "invalid_test_count": len(EXPECTED_TEST_FUNCTIONS) - eligible_count,
        "smelly_test_count": smelly_tests,
        "confirmed_pair_count": confirmed_pairs,
        "uncertain_pair_count": uncertain_pairs,
        "smelly_test_rate": smelly_tests / eligible_count if eligible_count else None,
        "mean_smells_per_test": mean_smells,
        "test_smell_density": normalized_density,
        "per_smell": per_smell,
        "tools": tools,
        "test_cases": test_results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect source-level test smell metrics without executing tests."
    )
    parser.add_argument("test_path", type=Path)
    parser.add_argument("--error-rate-json", type=Path, required=True)
    parser.add_argument("--pytest-smell", type=Path)
    parser.add_argument("--tempy-root", type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)
    try:
        report = collect_test_smells(
            test_path=args.test_path.resolve(),
            error_rates=_load_error_rate(args.error_rate_json.resolve()),
            pytest_smell_executable=args.pytest_smell,
            tempy_root=args.tempy_root,
            python_executable=args.python,
            evidence_dir=args.evidence_dir,
            timeout=args.timeout,
        )
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
