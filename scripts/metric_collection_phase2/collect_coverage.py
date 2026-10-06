"""Measure coverage from the frozen Phase 2 error-rate valid pool."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metric_collection_phase1.collect_all_branches import _git, _write_json
from scripts.metric_collection_phase1.collect_coverage import (
    _metrics_from_coverage_json,
    _run_coverage,
)
from scripts.metric_collection_phase2.collect_error_rates import EXPECTED, PARTICIPANTS


def export_snapshot(repo: Path, commit: str, checkout: Path) -> None:
    """Extract the immutable submission without relocating its tests."""
    archive = subprocess.check_output(["git", "archive", commit], cwd=repo)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(checkout, filter="data")


def valid_pool(raw: dict[str, Any], checkout: Path) -> list[str]:
    """Verify artifact identity and select only previously classified valid instances."""
    metrics = raw["metrics"]
    for relative, expected_hash in metrics["artifact_sha256"].items():
        if (
            hashlib.sha256((checkout / relative).read_bytes()).hexdigest()
            != expected_hash
        ):
            raise ValueError(
                f"Artifact changed since error-rate collection: {relative}"
            )
    nodeids = [
        case["nodeid"]
        for case in metrics["case_level"]["test_cases"]
        if case["classification"] == "valid"
    ]
    if nodeids != metrics["valid_nodeids"] or len(nodeids) != len(set(nodeids)):
        raise ValueError("Error-rate valid pool is inconsistent")
    return nodeids


def partition_pool(nodeids: list[str]) -> dict[str, list[str]]:
    """Partition required tasks and extra tests; groups are measured independently."""
    groups: dict[str, list[str]] = {
        "maintenance": [],
        "new_generation": [],
        "retained_legacy": [],
        "additional": [],
    }
    for nodeid in nodeids:
        path, name = nodeid.split("::", 1)
        name = name.split("[", 1)[0]
        if path == "tests/task/task2.py" and name in EXPECTED[path]:
            group = "new_generation"
        elif path == "tests/task/phase1/task.py" and name == "test_parse_fail":
            group = "retained_legacy"
        elif (path == "tests/task/phase1/task.py" and name in EXPECTED[path]) or (
            path == "tests/test_cli.py" and name == "test_non_utf8"
        ):
            group = "maintenance"
        else:
            group = "additional"
        groups[group].append(nodeid)
    return groups


def measure(
    checkout: Path,
    nodeids: list[str],
    python: str,
    timeout: float,
    evidence: Path,
) -> dict[str, Any]:
    """Reuse the Phase 1 coverage engine with original node IDs and import proof."""
    evidence.mkdir(parents=True, exist_ok=True)
    (checkout / ".coveragerc").write_text(
        "[run]\nbranch = True\nrelative_files = True\nsource = markdown_it\n",
        encoding="utf-8",
    )
    plugin = checkout / "_phase2_coverage_provenance.py"
    provenance_path = evidence / "provenance.json"
    plugin.write_text(
        "import json, platform\nfrom pathlib import Path\nimport pytest\n"
        "def pytest_sessionstart(session):\n"
        "    import markdown_it, coverage\n"
        f"    root = Path({str(checkout)!r}).resolve()\n"
        "    source = Path(markdown_it.__file__).resolve()\n"
        "    if not source.is_relative_to(root):\n"
        "        raise RuntimeError('SUT imported outside frozen snapshot')\n"
        f"    Path({str(provenance_path)!r}).write_text(json.dumps({{\n"
        "        'python': platform.python_version(), 'pytest': pytest.__version__,\n"
        "        'coverage': coverage.__version__,\n"
        "        'markdown_it_path': str(source.relative_to(root)),\n"
        "    }))\n",
        encoding="utf-8",
    )
    report = _run_coverage(
        pytest_arguments=[
            "-p",
            "_phase2_coverage_provenance",
            f"--junitxml={evidence / 'pytest.xml'}",
            *nodeids,
        ],
        repo_root=checkout,
        python_executable=python,
        source="markdown_it",
        timeout=timeout,
        data_path=evidence / "coverage-data",
        json_path=evidence / "coverage.json",
        scope_name=evidence.name,
    )
    payload = json.loads((evidence / "coverage.json").read_text())
    if not payload["files"] or any(
        not path.startswith("markdown_it/") for path in payload["files"]
    ):
        raise RuntimeError("Coverage includes files outside the frozen SUT")
    return {**asdict(report), "provenance": json.loads(provenance_path.read_text())}


def combine(
    checkout: Path,
    inputs: list[Path],
    python: str,
    timeout: float,
    evidence: Path,
) -> dict[str, Any]:
    """Union executed lines and arcs from pristine project and participant runs."""
    evidence.mkdir(parents=True, exist_ok=True)
    data = evidence / "coverage-data"
    report = evidence / "coverage.json"
    for command in (
        [
            python,
            "-m",
            "coverage",
            "combine",
            "--keep",
            f"--data-file={data}",
            *[str(path) for path in inputs],
        ],
        [python, "-m", "coverage", "json", f"--data-file={data}", "-o", str(report)],
    ):
        completed = subprocess.run(
            command,
            cwd=checkout,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError(completed.stdout + completed.stderr)
    statement, branch = _metrics_from_coverage_json(json.loads(report.read_text()))
    return {"statement": asdict(statement), "branch": asdict(branch)}


def collect_all(
    repo: Path,
    error_dir: Path,
    output: Path,
    python: str,
    timeout: float,
) -> dict[str, Any]:
    source_path = error_dir / "collection_manifest.json"
    source = json.loads(source_path.read_text())
    participants = source["participants"]
    if sorted(row["participant_number"] for row in participants) != sorted(
        PARTICIPANTS
    ):
        raise ValueError("Error-rate cohort does not match Phase 2 cohort")
    if any(row["status"] != "collected" for row in participants):
        raise ValueError("Complete error-rate collection is required")
    baseline = source["baseline_commit"]
    with tempfile.TemporaryDirectory(prefix="phase2-coverage-baseline-") as tmp:
        checkout = Path(tmp)
        export_snapshot(repo, baseline, checkout)
        baseline_evidence = output / "evidence" / "baseline"
        project = measure(
            checkout,
            ["--ignore=tests/task", "tests"],
            python,
            timeout,
            baseline_evidence,
        )
    records = []
    for row in participants:
        record = {
            key: row[key]
            for key in (
                "participant_id",
                "participant_number",
                "participant_commit",
                "phase1_group",
            )
        }
        print(f"Collecting coverage: {row['participant_id']}...", file=sys.stderr)
        try:
            raw = json.loads((error_dir / row["output_file"]).read_text())
            if raw["participant_commit"] != row["participant_commit"]:
                raise ValueError("Manifest/raw commit mismatch")
            if _git(
                repo,
                "diff",
                "--name-only",
                baseline,
                row["participant_commit"],
                "--",
                "markdown_it",
                "pyproject.toml",
                "tox.ini",
            ):
                raise ValueError("SUT/config differs from common baseline")
            with tempfile.TemporaryDirectory(prefix="phase2-coverage-") as tmp:
                checkout = Path(tmp)
                export_snapshot(repo, row["participant_commit"], checkout)
                nodeids = valid_pool(raw, checkout)
                evidence = output / "evidence" / row["participant_id"]
                participant = (
                    measure(
                        checkout,
                        nodeids,
                        python,
                        timeout,
                        evidence / "participant",
                    )
                    if nodeids
                    else None
                )
                inputs = [baseline_evidence / "coverage-data"]
                if participant is not None:
                    inputs.append(evidence / "participant/coverage-data")
                # Configure relative paths even when the participant valid pool is empty.
                (checkout / ".coveragerc").write_text(
                    "[run]\nrelative_files = True\nsource = markdown_it\n"
                )
                combined = combine(
                    checkout, inputs, python, timeout, evidence / "combined"
                )
                groups = partition_pool(nodeids)
                group_reports = {
                    name: measure(checkout, ids, python, timeout, evidence / name)
                    if ids
                    else None
                    for name, ids in groups.items()
                }
                for measured in [participant, combined, *group_reports.values()]:
                    if measured is not None:
                        for metric in ("statement", "branch"):
                            if measured[metric]["total"] != project[metric]["total"]:
                                raise ValueError("SUT coverage denominator differs")
            result = {
                **record,
                "baseline_commit": baseline,
                "error_rate_raw_sha256": hashlib.sha256(
                    (error_dir / row["output_file"]).read_bytes()
                ).hexdigest(),
                "valid_nodeids": nodeids,
                "valid_tests_included": len(nodeids),
                "invalid_tests_excluded": raw["metrics"]["case_level"][
                    "total_generated_test_cases"
                ]
                - len(nodeids),
                "missing_expected_tests": raw["metrics"]["missing_expected_tests"],
                "participant_tests_only": participant,
                "all_tests_combined": combined,
                "group_nodeids": groups,
                "group_coverage": group_reports,
            }
            raw_path = output / "raw" / f"{row['participant_id']}.json"
            _write_json(raw_path, result)
            record.update(
                status="collected",
                output_file=raw_path.relative_to(output).as_posix(),
                summary={
                    key: result[key]
                    for key in (
                        "valid_tests_included",
                        "invalid_tests_excluded",
                        "participant_tests_only",
                        "all_tests_combined",
                    )
                },
            )
        except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
            record.update(status="collection_failed", reason=str(exc))
        records.append(record)
        print(f"  {record['status']}", file=sys.stderr)
    collector_paths = [
        Path(__file__).resolve(),
        repo / "scripts/metric_collection_phase1/collect_coverage.py",
    ]
    return {
        "schema_version": "phase2-coverage-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": baseline,
        "collector_commit": _git(repo, "rev-parse", "HEAD"),
        "collector_sha256": {
            path.relative_to(repo).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in collector_paths
        },
        "error_rate_manifest_sha256": hashlib.sha256(
            source_path.read_bytes()
        ).hexdigest(),
        "python_executable": python,
        "source": "markdown_it",
        "project_tests_only": project,
        "combined_method": "coverage line/arc union of pristine baseline tests and valid participant instances",
        "participants": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--error-dir", type=Path, default=Path("results/phase2/error_rates")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("results/phase2/coverage")
    )
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args(argv)
    repo = args.repo_root.resolve()
    output = (repo / args.output_dir).resolve()
    if output.exists():
        parser.error(
            "Output directory exists; use a new directory to preserve evidence"
        )
    manifest = collect_all(
        repo,
        (repo / args.error_dir).resolve(),
        output,
        str(Path(args.python).absolute()),
        args.timeout,
    )
    _write_json(output / "collection_manifest.json", manifest)
    columns = [
        "participant_number",
        "status",
        "valid_tests_included",
        "invalid_tests_excluded",
        "participant_statement_coverage",
        "participant_branch_coverage",
        "combined_statement_coverage",
        "combined_branch_coverage",
    ]
    with (output / "coverage.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in manifest["participants"]:
            summary = row.get("summary", {})
            flat = {
                "participant_number": row["participant_number"],
                "status": row["status"],
                "valid_tests_included": summary.get("valid_tests_included"),
                "invalid_tests_excluded": summary.get("invalid_tests_excluded"),
            }
            for prefix, key in (
                ("participant", "participant_tests_only"),
                ("combined", "all_tests_combined"),
            ):
                scope = summary.get(key)
                for metric in ("statement", "branch"):
                    flat[f"{prefix}_{metric}_coverage"] = (
                        f"{scope[metric]['percent'] / 100:.6f}"
                        if scope is not None
                        else None
                    )
            writer.writerow(flat)
    return int(any(row["status"] != "collected" for row in manifest["participants"]))


if __name__ == "__main__":
    raise SystemExit(main())
