"""Collect Phase 2 errors on frozen submissions without rewriting participant tests."""

from __future__ import annotations

import argparse
import ast
from collections import Counter
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metric_collection_phase1.collect_all_branches import _git, _write_json
from scripts.metric_collection_phase1.collect_error_rates import (
    _PYTEST_PLUGIN_TEMPLATE,
    TestCaseResult,
    _case_level_report,
    _split_test_file,
)

PARTICIPANTS = (2, 3, 4, 5, 7, 8, 9, 12)
EXPECTED = {
    "tests/task/phase1/task.py": (
        "test_file",
        "test_spec",
        "test_core_after",
        "test_parse_fail",
        "test_non_utf8",
    ),
    "tests/task/task2.py": ("test_make_fence_after", "test_make_fence_at"),
}
EXPECTED_ALTERNATIVES = {
    ("tests/task/phase1/task.py", "test_non_utf8"): (
        ("tests/test_cli.py", "test_non_utf8"),
    ),
}
PROVENANCE_PLUGIN = """
import platform
import markdown_it

def pytest_sessionstart(session):
    path = Path(markdown_it.__file__).resolve()
    root = Path({root!r}).resolve()
    if not path.is_relative_to(root):
        raise RuntimeError("SUT was imported from outside the frozen submission: " + str(path))
    (root / "_sut_provenance.json").write_text(json.dumps({{
        "python_version": platform.python_version(),
        "pytest_version": pytest.__version__,
        "markdown_it_path": str(path.relative_to(root)),
    }}))
"""


def summarize(test_cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Use the Phase 1 classifier's count and ratio definitions."""
    report = asdict(
        _case_level_report(
            [
                TestCaseResult(
                    **{
                        key: case[key]
                        for key in (
                            "nodeid",
                            "source_test",
                            "classification",
                            "returncode",
                            "reason",
                        )
                    }
                )
                for case in test_cases
            ]
        )
    )
    report.pop("test_cases")
    if not test_cases:
        for field in ("syntax_error_rate", "runtime_error_rate", "function_error_rate"):
            report[field] = None
    report["overall_error_rate"] = (
        1 - report["valid_test_count"] / len(test_cases) if test_cases else None
    )
    return report


def external_test_selectors(
    repo_root: Path, baseline: str, commit: str, checkout: Path
) -> dict[str, list[str]]:
    """Select participant-added/changed top-level tests outside the task directory."""
    selected: dict[str, list[str]] = {}
    paths = _git(
        repo_root,
        "diff",
        "--name-only",
        "--diff-filter=AM",
        baseline,
        commit,
        "--",
        "tests",
    ).splitlines()
    for relative in paths:
        if relative.startswith("tests/task/") or not relative.endswith(".py"):
            continue
        previous = subprocess.run(
            ["git", "show", f"{baseline}:{relative}"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        old_source = previous.stdout if previous.returncode == 0 else ""
        old_functions = {
            node.name: ast.dump(node, include_attributes=False)
            for node in ast.parse(old_source).body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        }
        source = (checkout / relative).read_text(encoding="utf-8")
        try:
            functions = {
                node.name: ast.dump(node, include_attributes=False)
                for node in ast.parse(source).body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_")
            }
            names = [
                name
                for name, body in functions.items()
                if old_functions.get(name) != body
            ]
        except SyntaxError:
            # Retain recoverable declarations for collection-error classification.
            _, blocks = _split_test_file(checkout / relative)
            names = [block.name for block in blocks]
        if names:
            selected[relative] = names
    return selected


def collect_submission(
    checkout: Path,
    python: str,
    timeout: float,
    evidence_dir: Path,
    extra_tests: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Run original files together; retain missing tests separately from error counts."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    paths = sorted((checkout / "tests/task").rglob("*.py"))
    declarations: dict[str, list[str]] = {}
    test_paths: list[Path] = []
    for path in paths:
        _, blocks = _split_test_file(path)
        if blocks or path.relative_to(checkout).as_posix() in EXPECTED:
            relative = path.relative_to(checkout).as_posix()
            declarations[relative] = [block.name for block in blocks]
            test_paths.append(path)
    extra_tests = extra_tests or {}
    declarations.update(extra_tests)
    if not test_paths:
        raise RuntimeError("No participant task files found")
    hashes = {
        path.relative_to(checkout).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in sorted((checkout / "tests/task").rglob("*"))
        if path.is_file()
    }
    hashes.update(
        {
            relative: hashlib.sha256((checkout / relative).read_bytes()).hexdigest()
            for relative in extra_tests
        }
    )
    result_path = evidence_dir / "pytest-results.json"
    with tempfile.TemporaryDirectory(prefix="phase2-pytest-plugin-") as plugin_dir:
        plugin = Path(plugin_dir) / "_phase2_error_plugin.py"
        plugin.write_text(
            _PYTEST_PLUGIN_TEMPLATE.format(result_path=str(result_path)).replace(
                "original SUT", "frozen Phase 2 SUT"
            )
            + PROVENANCE_PLUGIN.format(root=str(checkout)),
            encoding="utf-8",
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = str(checkout) + os.pathsep + plugin_dir
        command = [
            python,
            "-m",
            "pytest",
            "-p",
            "_phase2_error_plugin",
            "-q",
            "--continue-on-collection-errors",
            *[str(path.relative_to(checkout)) for path in test_paths],
            *[
                f"{path}::{name}"
                for path, names in extra_tests.items()
                for name in names
            ],
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=checkout,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            captured = exc.stdout or b""
            output = (
                captured.decode(errors="replace")
                if isinstance(captured, bytes)
                else captured
            )
            (evidence_dir / "pytest-output.txt").write_text(output, encoding="utf-8")
            raise RuntimeError(f"pytest exceeded {timeout:g} seconds") from exc
    (evidence_dir / "pytest-output.txt").write_text(completed.stdout, encoding="utf-8")
    if not result_path.exists() or completed.returncode not in (0, 1, 2, 5):
        raise RuntimeError(
            f"pytest infrastructure failure, exit {completed.returncode}"
        )
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    provenance_path = checkout / "_sut_provenance.json"
    if not provenance_path.exists():
        raise RuntimeError("No proof that pytest imported the frozen SUT")
    cases: list[dict[str, Any]] = []
    for item in payload["items"]:
        nodeid = item["nodeid"]
        source_file = nodeid.split("::", 1)[0]
        if source_file not in declarations:
            raise RuntimeError(f"Unexpected pytest source file: {source_file}")
        if item["source_test"] not in declarations[source_file]:
            raise RuntimeError(f"Unexpected pytest test: {nodeid}")
        cases.append(
            {
                "nodeid": nodeid,
                "source_file": source_file,
                "source_test": item["source_test"],
                "classification": item["classification"],
                "reason": item["reason"],
                "returncode": 0 if item["classification"] == "valid" else 1,
                "count_basis": "pytest_instance",
            }
        )
    for error in payload["collection_errors"]:
        source_file = error["nodeid"].split("::", 1)[0]
        if source_file not in declarations:
            raise RuntimeError(f"Unexpected pytest collection error: {source_file}")
        represented = {
            case["source_test"] for case in cases if case["source_file"] == source_file
        }
        for name in declarations[source_file]:
            if name in represented:
                continue
            cases.append(
                {
                    "nodeid": f"{source_file}::{name}",
                    "source_file": source_file,
                    "source_test": name,
                    "classification": (
                        "syntax_error"
                        if "SyntaxError" in error["reason"]
                        else "runtime_error"
                    ),
                    "reason": error["reason"],
                    "returncode": completed.returncode,
                    "count_basis": "source_function_collection_fallback",
                }
            )
    missing = {
        path: [
            name
            for name in names
            if name not in declarations.get(path, [])
            and not any(
                alternate_name in declarations.get(alternate_path, [])
                for alternate_path, alternate_name in EXPECTED_ALTERNATIVES.get(
                    (path, name), ()
                )
            )
        ]
        for path, names in EXPECTED.items()
    }
    return {
        "suite_level": {
            "collectable": not payload["collection_errors"],
            "pytest_returncode": completed.returncode,
            "collection_errors": payload["collection_errors"],
            "test_paths": list(declarations),
            "external_test_selectors": extra_tests,
        },
        "provenance": json.loads(provenance_path.read_text()),
        "artifact_sha256": hashes,
        "source_test_declarations": declarations,
        "missing_expected_tests": {
            path: names for path, names in missing.items() if names
        },
        "case_level": {**summarize(cases), "test_cases": cases},
        "by_file": {
            path: summarize([case for case in cases if case["source_file"] == path])
            for path in declarations
        },
        "valid_nodeids": [
            case["nodeid"] for case in cases if case["classification"] == "valid"
        ],
    }


def collect_all(
    repo_root: Path, output: Path, python: str, timeout: float
) -> dict[str, Any]:
    baseline = _git(repo_root, "rev-parse", "origin/experiment-base-phase2^{commit}")
    phase1 = json.loads(
        (repo_root / "results/phase1/error_rates/collection_manifest.json").read_text()
    )
    old = {row["participant_number"]: row for row in phase1["participants"]}
    groups = {
        int(row["participant_number"]): row["group"]
        for row in csv.DictReader(
            io.StringIO(
                (
                    repo_root / "results/phase1/generation_time/generation_time.csv"
                ).read_text()
            )
        )
    }
    participants = []
    # Resolve every input SHA before executing any participant tests.
    frozen = {
        number: f"origin/experiment-{number:02d}-phase2" for number in PARTICIPANTS
    }
    commits: dict[int, str | None] = {}
    for number, ref in frozen.items():
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
            cwd=repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        commits[number] = resolved.stdout.strip() if resolved.returncode == 0 else None
    for number in PARTICIPANTS:
        participant = f"experiment-{number:02d}"
        commit = commits[number]
        record: dict[str, Any] = {
            "participant_id": participant,
            "participant_number": number,
            "branch": frozen[number],
            "participant_commit": commit,
            "phase1_commit": old[number]["participant_commit"],
            "phase1_group": groups[number],
            "phase2_group": "AI",
        }
        if commit is None:
            record.update(
                status="missing_branch",
                reason=f"Standard branch {frozen[number]} was not found",
            )
            participants.append(record)
            print(f"{participant}: missing_branch", file=sys.stderr)
            continue
        print(f"Collecting {participant} ({commit[:12]})...", file=sys.stderr)
        protected = _git(
            repo_root,
            "diff",
            "--name-only",
            baseline,
            commit,
            "--",
            "markdown_it",
            "pyproject.toml",
            "tox.ini",
        ).splitlines()
        record["protected_changes"] = protected
        if protected:
            record.update(
                status="baseline_mismatch", reason="SUT or configuration differs"
            )
        else:
            try:
                with tempfile.TemporaryDirectory(
                    prefix=f"phase2-{participant}-"
                ) as tmp:
                    checkout = Path(tmp)
                    archive = subprocess.check_output(
                        ["git", "archive", commit], cwd=repo_root
                    )
                    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                        tar.extractall(checkout, filter="data")
                    evidence = output / "evidence" / participant
                    extra_tests = external_test_selectors(
                        repo_root, baseline, commit, checkout
                    )
                    report = collect_submission(
                        checkout, python, timeout, evidence, extra_tests
                    )
                raw = output / "raw" / f"{participant}.json"
                _write_json(
                    raw, {**record, "baseline_commit": baseline, "metrics": report}
                )
                record.update(
                    status="collected",
                    output_file=raw.relative_to(output).as_posix(),
                    summary={
                        key: value
                        for key, value in report["case_level"].items()
                        if key != "test_cases"
                    },
                    missing_expected_tests=report["missing_expected_tests"],
                )
            except (RuntimeError, OSError, ValueError, SyntaxError) as exc:
                record.update(status="collection_failed", reason=str(exc))
        participants.append(record)
        print(f"  {record['status']}", file=sys.stderr)
    collector_paths = [
        Path(__file__).resolve(),
        repo_root / "scripts/metric_collection_phase1/collect_error_rates.py",
        repo_root / "scripts/metric_collection_phase1/collect_all_branches.py",
    ]
    return {
        "schema_version": "phase2-error-rates-v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": 2,
        "baseline_ref": "origin/experiment-base-phase2",
        "baseline_commit": baseline,
        "collector_commit": _git(repo_root, "rev-parse", "HEAD"),
        "collector_sha256": {
            path.relative_to(repo_root).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in collector_paths
        },
        "python_executable": python,
        "scope": (
            "all tests/task functions plus participant-added/changed top-level test "
            "functions elsewhere under tests, compared with baseline; original paths retained"
        ),
        "participants": participants,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-dir", type=Path, default=Path("results/phase2/error_rates")
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    output = (root / args.output_dir).resolve()
    if (output / "collection_manifest.json").exists():
        parser.error(
            "Output manifest already exists; use a new --output-dir to preserve evidence"
        )
    manifest = collect_all(
        root, output, str(Path(args.python).absolute()), args.timeout
    )
    _write_json(output / "collection_manifest.json", manifest)
    columns = [
        "participant_id",
        "participant_number",
        "status",
        "phase1_group",
        "total_generated_test_cases",
        "syntax_error_count",
        "runtime_error_count",
        "function_error_count",
        "valid_test_count",
        "syntax_error_rate",
        "runtime_error_rate",
        "function_error_rate",
        "overall_error_rate",
    ]
    with (output / "error_rates.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for record in manifest["participants"]:
            row = {**record, **record.get("summary", {})}
            writer.writerow({column: row.get(column) for column in columns})
    print(
        json.dumps(Counter(row["status"] for row in manifest["participants"]), indent=2)
    )
    return int(any(row["status"] != "collected" for row in manifest["participants"]))


if __name__ == "__main__":
    raise SystemExit(main())
