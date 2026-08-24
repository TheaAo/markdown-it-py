from __future__ import annotations

import argparse
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


Classification = Literal["valid", "syntax_error", "runtime_error", "function_error"]


@dataclass(frozen=True)
class TestBlock:
    name: str
    start_line: int
    source: str


@dataclass(frozen=True)
class TestCaseResult:
    nodeid: str
    source_test: str
    classification: Classification
    returncode: int | None
    reason: str


@dataclass(frozen=True)
class SuiteLevelReport:
    collectable: bool
    collection_returncode: int
    collection_error: str | None
    collected_nodeids: list[str]


@dataclass(frozen=True)
class CaseLevelReport:
    total_generated_test_cases: int
    syntax_error_count: int
    runtime_error_count: int
    function_error_count: int
    valid_test_count: int
    syntax_error_rate: float
    runtime_error_rate: float
    function_error_rate: float
    test_cases: list[TestCaseResult]


@dataclass(frozen=True)
class ErrorRateReport:
    test_path: str
    suite_level: SuiteLevelReport
    case_level: CaseLevelReport


def _run(command: list[str], cwd: Path, timeout: float) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        output += f"\nCommand timed out after {timeout} seconds."
        return subprocess.CompletedProcess(command, 124, output)


def _ensure_pytest_available(python_executable: str, repo_root: Path) -> None:
    completed = _run(
        [python_executable, "-m", "pytest", "--version"],
        cwd=repo_root,
        timeout=10,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"pytest is not available for {python_executable!r}; "
            "pass --python pointing to the experiment environment."
        )


def _collect_nodeids(
    python_executable: str,
    repo_root: Path,
    test_path: Path,
    timeout: float,
) -> tuple[int, list[str], str]:
    completed = _run(
        [python_executable, "-m", "pytest", "--collect-only", "-q", str(test_path)],
        cwd=repo_root,
        timeout=timeout,
    )
    nodeids: list[str] = []
    for line in completed.stdout.splitlines():
        stripped = line.strip()
        if "::" in stripped and not stripped.startswith("ERROR"):
            nodeids.append(stripped)
    return completed.returncode, nodeids, completed.stdout


def _classify_failure(output: str) -> tuple[Classification, str]:
    if "SyntaxError" in output:
        return "syntax_error", "pytest reported SyntaxError"
    if "AssertionError" in output or re.search(r"\bFailed:\s", output):
        return "function_error", "test executed but assertion failed on the original SUT"
    if re.search(r"^ERROR\b", output, flags=re.MULTILINE):
        return "runtime_error", "pytest reported an execution error"
    return "runtime_error", "test failed with a non-assertion exception"


def _suite_collection_report(
    python_executable: str,
    repo_root: Path,
    test_path: Path,
    timeout: float,
) -> SuiteLevelReport:
    returncode, nodeids, output = _collect_nodeids(
        python_executable=python_executable,
        repo_root=repo_root,
        test_path=test_path,
        timeout=timeout,
    )
    collection_error = None
    if returncode != 0:
        _classification, collection_error = _classify_failure(output)
    return SuiteLevelReport(
        collectable=returncode == 0,
        collection_returncode=returncode,
        collection_error=collection_error,
        collected_nodeids=nodeids,
    )


def _top_level_block_starts(lines: list[str]) -> list[tuple[int, str | None]]:
    def_pattern = re.compile(r"^(?:async\s+def|def)\s+([A-Za-z_][A-Za-z0-9_]*)")
    class_pattern = re.compile(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)")
    starts: list[tuple[int, str | None]] = []

    for index, line in enumerate(lines):
        if line.startswith((" ", "\t")):
            continue
        match = def_pattern.match(line) or class_pattern.match(line)
        if not match:
            continue
        start = index
        while start > 0 and lines[start - 1].startswith("@"):
            start -= 1
        starts.append((start, match.group(1)))

    return sorted(set(starts), key=lambda item: item[0])


def _split_test_file(test_path: Path) -> tuple[str, list[TestBlock]]:
    lines = test_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    test_ranges: list[tuple[int, int, str]] = []

    try:
        tree = ast.parse("".join(lines), filename=str(test_path))
    except SyntaxError:
        starts = _top_level_block_starts(lines)
        for position, (start, name) in enumerate(starts):
            end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
            if name and name.startswith("test_"):
                test_ranges.append((start, end, name))
    else:
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            decorator_lines = [decorator.lineno for decorator in node.decorator_list]
            start = min([node.lineno, *decorator_lines]) - 1
            end = node.end_lineno or node.lineno
            test_ranges.append((start, end, node.name))

    support_lines = lines[:]
    for start, end, _name in reversed(test_ranges):
        del support_lines[start:end]

    test_blocks = [
        TestBlock(name=name, start_line=start + 1, source="".join(lines[start:end]))
        for start, end, name in test_ranges
    ]
    return "".join(support_lines).rstrip() + "\n", test_blocks


def _copy_materials(test_path: Path, isolated_dir: Path) -> None:
    materials = test_path.parent / "materials"
    if materials.exists():
        shutil.copytree(materials, isolated_dir / "materials")


def _display_nodeid(original_test_path: Path, repo_root: Path, isolated_nodeid: str) -> str:
    try:
        display_path = original_test_path.relative_to(repo_root)
    except ValueError:
        display_path = original_test_path
    if "::" not in isolated_nodeid:
        return str(display_path)
    return f"{display_path}::{isolated_nodeid.split('::', 1)[1]}"


_PYTEST_PLUGIN_TEMPLATE = '''
import json
from pathlib import Path

import pytest


RESULT_PATH = Path({result_path!r})
ITEMS = {{}}
COLLECTION_ERRORS = []


def _item_entry(item):
    return ITEMS.setdefault(
        item.nodeid,
        {{
            "nodeid": item.nodeid,
            "source_file": Path(str(item.path)).name,
            "source_test": getattr(item, "originalname", None)
            or item.name.split("[", 1)[0],
            "classification": "runtime_error",
            "reason": "test was collected but did not complete",
        }},
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    entry = _item_entry(item)

    if report.when == "setup":
        if report.failed:
            entry["classification"] = "runtime_error"
            entry["reason"] = "pytest setup failed"
        elif report.skipped:
            entry["classification"] = "runtime_error"
            entry["reason"] = "test was skipped before execution"
        return

    if report.when == "call":
        if report.passed:
            entry["classification"] = "valid"
            entry["reason"] = "passed on original SUT"
        elif report.skipped:
            entry["classification"] = "runtime_error"
            entry["reason"] = "test was skipped during execution"
        elif report.failed:
            exception_type = call.excinfo.type if call.excinfo is not None else None
            is_assertion = exception_type is not None and issubclass(
                exception_type, AssertionError
            )
            is_pytest_fail = exception_type is not None and (
                exception_type.__name__ == "Failed"
                and exception_type.__module__.startswith("_pytest")
            )
            if is_assertion or is_pytest_fail:
                entry["classification"] = "function_error"
                entry["reason"] = (
                    "test executed but assertion failed on the original SUT"
                )
            else:
                entry["classification"] = "runtime_error"
                exception_name = (
                    exception_type.__name__ if exception_type is not None else "unknown"
                )
                entry["reason"] = f"test failed with {{exception_name}}"
        return

    if report.when == "teardown" and report.failed:
        entry["classification"] = "runtime_error"
        entry["reason"] = "pytest teardown failed"


def pytest_collectreport(report):
    if report.failed:
        COLLECTION_ERRORS.append(
            {{
                "nodeid": report.nodeid,
                "source_file": Path(report.nodeid.split("::", 1)[0]).name,
                "reason": str(report.longrepr),
            }}
        )


def pytest_sessionfinish(session, exitstatus):
    payload = {{
        "exitstatus": int(exitstatus),
        "items": list(ITEMS.values()),
        "collection_errors": COLLECTION_ERRORS,
    }}
    RESULT_PATH.write_text(json.dumps(payload), encoding="utf-8")
'''


def _syntax_error_result(
    block: TestBlock,
    original_test_path: Path,
    repo_root: Path,
    reason: str,
) -> TestCaseResult:
    return TestCaseResult(
        nodeid=_display_nodeid(
            original_test_path,
            repo_root,
            f"{original_test_path.name}::{block.name}",
        ),
        source_test=block.name,
        classification="syntax_error",
        returncode=None,
        reason=reason,
    )


def _write_batch_test_files(
    test_blocks: list[TestBlock],
    support_source: str,
    original_test_path: Path,
    repo_root: Path,
    temp_root: Path,
) -> tuple[list[TestCaseResult], dict[str, TestBlock]]:
    syntax_results: list[TestCaseResult] = []
    files_to_blocks: dict[str, TestBlock] = {}

    try:
        ast.parse(support_source, filename=str(original_test_path))
    except SyntaxError as exc:
        reason = f"SyntaxError in shared test support at line {exc.lineno}: {exc.msg}"
        return [
            _syntax_error_result(block, original_test_path, repo_root, reason)
            for block in test_blocks
        ], files_to_blocks

    for index, block in enumerate(test_blocks):
        try:
            ast.parse(block.source, filename=str(original_test_path))
        except SyntaxError as exc:
            original_line = block.start_line + (exc.lineno or 1) - 1
            syntax_results.append(
                _syntax_error_result(
                    block,
                    original_test_path,
                    repo_root,
                    f"SyntaxError at line {original_line}: {exc.msg}",
                )
            )
            continue

        safe_name = re.sub(r"[^A-Za-z0-9_]", "_", block.name)
        isolated_path = temp_root / f"test_isolated_{index:03d}_{safe_name}.py"
        isolated_path.write_text(
            f"{support_source}\n\n{block.source}", encoding="utf-8"
        )
        files_to_blocks[isolated_path.name] = block

    return syntax_results, files_to_blocks


def _batch_runtime_results(
    test_path: Path,
    repo_root: Path,
    python_executable: str,
    timeout: float,
    support_source: str,
    test_blocks: list[TestBlock],
    temp_root: Path,
) -> list[TestCaseResult]:
    syntax_results, files_to_blocks = _write_batch_test_files(
        test_blocks=test_blocks,
        support_source=support_source,
        original_test_path=test_path,
        repo_root=repo_root,
        temp_root=temp_root,
    )
    if not files_to_blocks:
        return syntax_results

    _copy_materials(test_path, temp_root)
    result_path = temp_root / "pytest-results.json"
    (temp_root / "conftest.py").write_text(
        _PYTEST_PLUGIN_TEMPLATE.format(result_path=str(result_path)),
        encoding="utf-8",
    )
    test_files = [str(temp_root / name) for name in files_to_blocks]
    completed = _run(
        [
            python_executable,
            "-m",
            "pytest",
            "-q",
            "--continue-on-collection-errors",
            *test_files,
        ],
        cwd=repo_root,
        timeout=timeout,
    )

    if not result_path.exists():
        reason = (
            f"batch pytest did not produce results (return code {completed.returncode})"
        )
        return syntax_results + [
            TestCaseResult(
                nodeid=_display_nodeid(
                    test_path, repo_root, f"{test_path.name}::{block.name}"
                ),
                source_test=block.name,
                classification="runtime_error",
                returncode=completed.returncode,
                reason=reason,
            )
            for block in files_to_blocks.values()
        ]

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    runtime_results: list[TestCaseResult] = []
    represented_files: set[str] = set()

    for item in payload["items"]:
        source_file = item["source_file"]
        block = files_to_blocks[source_file]
        represented_files.add(source_file)
        runtime_results.append(
            TestCaseResult(
                nodeid=_display_nodeid(test_path, repo_root, item["nodeid"]),
                source_test=block.name,
                classification=item["classification"],
                returncode=0 if item["classification"] == "valid" else 1,
                reason=item["reason"],
            )
        )

    collection_errors = {
        error["source_file"]: error for error in payload["collection_errors"]
    }
    for source_file, block in files_to_blocks.items():
        if source_file in represented_files:
            continue
        error = collection_errors.get(source_file)
        reason = (
            "pytest collection failed before test execution"
            if error is not None
            else "pytest collected no test items for this test function"
        )
        runtime_results.append(
            TestCaseResult(
                nodeid=_display_nodeid(
                    test_path, repo_root, f"{test_path.name}::{block.name}"
                ),
                source_test=block.name,
                classification="runtime_error",
                returncode=completed.returncode,
                reason=reason,
            )
        )

    return syntax_results + runtime_results


def _case_level_report(test_cases: list[TestCaseResult]) -> CaseLevelReport:
    total = len(test_cases)
    syntax_count = sum(1 for item in test_cases if item.classification == "syntax_error")
    runtime_count = sum(1 for item in test_cases if item.classification == "runtime_error")
    function_count = sum(1 for item in test_cases if item.classification == "function_error")
    valid_count = sum(1 for item in test_cases if item.classification == "valid")
    denominator = total or 1
    return CaseLevelReport(
        total_generated_test_cases=total,
        syntax_error_count=syntax_count,
        runtime_error_count=runtime_count,
        function_error_count=function_count,
        valid_test_count=valid_count,
        syntax_error_rate=syntax_count / denominator,
        runtime_error_rate=runtime_count / denominator,
        function_error_rate=function_count / denominator,
        test_cases=test_cases,
    )


def collect_error_rates(
    test_path: Path,
    repo_root: Path,
    python_executable: str,
    timeout: float,
) -> ErrorRateReport:
    test_path = test_path.resolve()
    repo_root = repo_root.resolve()
    suite_level = _suite_collection_report(
        python_executable=python_executable,
        repo_root=repo_root,
        test_path=test_path,
        timeout=timeout,
    )
    support_source, test_blocks = _split_test_file(test_path)

    with tempfile.TemporaryDirectory(prefix="error-rate-cases-") as temp_dir:
        test_cases = _batch_runtime_results(
            test_path=test_path,
            repo_root=repo_root,
            python_executable=python_executable,
            timeout=timeout,
            support_source=support_source,
            test_blocks=test_blocks,
            temp_root=Path(temp_dir),
        )

    return ErrorRateReport(
        test_path=str(test_path),
        suite_level=suite_level,
        case_level=_case_level_report(test_cases),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect syntax/runtime/function error rates for participant pytest artifacts."
    )
    parser.add_argument("test_path", type=Path, help="Path to the participant test file.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root used as pytest working directory.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable with pytest and project test dependencies installed.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Timeout in seconds for suite collection, isolated collection, and each test run.",
    )
    args = parser.parse_args(argv)

    try:
        _ensure_pytest_available(args.python, args.repo_root.resolve())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    report = collect_error_rates(
        test_path=args.test_path,
        repo_root=args.repo_root,
        python_executable=args.python,
        timeout=args.timeout,
    )
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
