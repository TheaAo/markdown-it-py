"""Time original Phase 2 tests using the frozen effectiveness valid pool."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
import tarfile
import tempfile
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.metric_collection_phase1.collect_all_branches import _git, _write_json
from scripts.metric_collection_phase1.collect_execution_time import (
    _summarize,
    _timed_pytest,
)
from scripts.metric_collection_phase1.summarize_execution_times import (
    summarize_execution_times,
)

PARTICIPANTS = (2, 3, 4, 5, 7, 8, 9, 12)


def file_hash(path: Path) -> str:
    """Return a source hash for audit and reproducibility."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def valid_pool(raw: dict[str, Any], checkout: Path) -> list[str]:
    """Check source hashes and the saved instance-level classification."""
    metrics = raw["metrics"]
    for relative, expected in metrics["artifact_sha256"].items():
        path = (checkout / relative).resolve()
        if not path.is_relative_to(checkout.resolve()) or file_hash(path) != expected:
            raise ValueError(
                f"Artifact differs from frozen validity evidence: {relative}"
            )
    cases = metrics["case_level"]["test_cases"]
    nodeids = [case["nodeid"] for case in cases if case["classification"] == "valid"]
    if (
        nodeids != metrics["valid_nodeids"]
        or len(nodeids) != len(set(nodeids))
        or len(nodeids) != metrics["case_level"]["valid_test_count"]
    ):
        raise ValueError("Saved valid pool is inconsistent")
    for nodeid in nodeids:
        path, separator, _name = nodeid.partition("::")
        resolved = (checkout / path).resolve()
        if not separator or not resolved.is_relative_to(checkout.resolve()):
            raise ValueError(f"Invalid saved node ID: {nodeid}")
    return nodeids


def verify_runtime(checkout: Path, python: str, nodeids: list[str]) -> dict[str, Any]:
    """Prove SUT import identity and exactly selected items before timing."""
    verifier = checkout / "_phase2_timing_verify.py"
    verifier.write_text(
        "import json, platform, sys\nfrom pathlib import Path\n"
        "import pytest, markdown_it\n"
        "root = Path.cwd().resolve()\n"
        "source = Path(markdown_it.__file__).resolve()\n"
        "assert source.is_relative_to(root), str(source)\n"
        "class Items:\n"
        "    def pytest_collection_finish(self, session):\n"
        "        self.nodeids = [item.nodeid for item in session.items]\n"
        "items = Items()\n"
        "code = pytest.main(['--collect-only', '-q', '-p', 'no:cacheprovider', *sys.argv[1:]], plugins=[items])\n"
        "assert code == 0, code\n"
        "Path('_timing_provenance.json').write_text(json.dumps({\n"
        "    'python_version': platform.python_version(), 'pytest_version': pytest.__version__,\n"
        "    'markdown_it_path': str(source.relative_to(root)),\n"
        "    'selected_nodeids': items.nodeids,\n"
        "}))\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [python, str(verifier), *nodeids],
        cwd=checkout,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"Runtime verification failed: {result.stdout}\n{result.stderr}"
        )
    provenance: dict[str, Any] = json.loads(
        (checkout / "_timing_provenance.json").read_text()
    )
    if sorted(provenance["selected_nodeids"]) != sorted(nodeids):
        raise ValueError("Pytest selected items differ from saved valid pool")
    return provenance


def measure(
    checkout: Path,
    python: str,
    nodeids: list[str],
    invalid_count: int,
    protocol: dict[str, Any],
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reuse Phase 1 process timer and estimator; retain every attempted run."""
    report: dict[str, Any] = {
        "status": "no_valid_tests" if not nodeids else "collected",
        "valid_tests_included": len(nodeids),
        "invalid_tests_excluded": invalid_count,
        "summary": None,
        "baseline": None,
        "warmups": [],
        "measurements": [],
        "selected_nodeids": nodeids,
    }
    if not nodeids:
        return report
    report["provenance"] = (
        provenance
        if provenance is not None
        else verify_runtime(checkout, python, nodeids)
    )
    for phase, count in (
        ("baseline", 1),
        ("warmup", protocol["warmup_count"]),
        ("measurement", protocol["measurement_count"]),
    ):
        for index in range(1, count + 1):
            run = _timed_pytest(
                python_executable=python,
                repo_root=checkout,
                nodeids=nodeids,
                timeout=protocol["timeout_seconds"],
                phase=phase,
                index=index,
            )
            if phase == "baseline":
                report["baseline"] = asdict(run)
            else:
                report["warmups" if phase == "warmup" else "measurements"].append(
                    asdict(run)
                )
            if run.returncode:
                report["status"] = (
                    "measurement_timeout" if run.timed_out else "measurement_failed"
                )
                report["reason"] = run.failure_output
                return report
    # Reconstruct the shared timer record for the unchanged Phase 1 estimator.
    from scripts.metric_collection_phase1.collect_execution_time import TimedRun

    report["summary"] = asdict(
        _summarize(
            [TimedRun(**item) for item in report["measurements"]],
            protocol["cv_review_threshold"],
        )
    )
    return report


def collect(
    repo: Path,
    source_manifest: Path,
    output: Path,
    python: str,
    participants: list[int],
    protocol: dict[str, Any],
) -> dict[str, Any]:
    """Export frozen commits and measure participants sequentially."""
    source = json.loads(source_manifest.read_text())
    records = {p["participant_number"]: p for p in source["participants"]}
    if len(records) != len(source["participants"]) or set(records) != set(PARTICIPANTS):
        raise ValueError("Expected the frozen eight-person Phase 2 manifest")
    if len(participants) != len(set(participants)) or not set(participants) <= set(
        records
    ):
        raise ValueError("Invalid participant selection")
    if protocol["global_warmup_count_per_participant"] not in (0, 1):
        raise ValueError("Global warmup count must be zero or one")
    if output.exists():
        raise ValueError(
            "Output exists; use a new directory to preserve earlier observations"
        )
    output.mkdir(parents=True)
    manifest: dict[str, Any] = {
        "schema_version": protocol["schema_version"],
        "phase": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": source["baseline_commit"],
        "collector_commit": _git(repo, "rev-parse", "HEAD"),
        "collector_sha256": {
            relative: file_hash(repo / relative)
            for relative in (
                "scripts/metric_collection_phase2/collect_execution_times.py",
                "scripts/metric_collection_phase1/collect_execution_time.py",
                "scripts/metric_collection_phase1/summarize_execution_times.py",
                "scripts/metric_collection_phase1/collect_all_branches.py",
            )
        },
        "source_manifest": str(source_manifest),
        "source_manifest_sha256": file_hash(source_manifest),
        "python_executable": python,
        "machine": platform.uname()._asdict(),
        "protocol": protocol,
        "participants": [],
    }
    _write_json(output / "collection_manifest.json", manifest)
    order = sorted(participants)
    if protocol.get("order_seed") is not None:
        random.Random(protocol["order_seed"]).shuffle(order)
    global_order = (
        sorted(participants) if protocol["global_warmup_count_per_participant"] else []
    )
    manifest["preflight_order"] = sorted(participants)
    manifest["global_warmup_order"] = global_order
    manifest["measurement_order"] = order
    manifest["global_warmups"] = []
    prepared: dict[
        int, tuple[Path, list[str], int, dict[str, Any], dict[str, Any]]
    ] = {}
    with ExitStack() as stack:
        # Retain verified snapshots through any warmups and formal collection.
        for number in sorted(participants):
            participant = records[number]
            print(f"Preparing {participant['participant_id']}...", flush=True)
            raw_path = source_manifest.parent / participant["output_file"]
            raw = json.loads(raw_path.read_text())
            record = {
                key: participant[key]
                for key in (
                    "participant_id",
                    "participant_number",
                    "branch",
                    "participant_commit",
                    "phase1_commit",
                    "phase1_group",
                    "phase2_group",
                )
            }
            record["input_error_rate_sha256"] = file_hash(raw_path)
            try:
                if (
                    participant["status"] != "collected"
                    or raw["participant_commit"] != record["participant_commit"]
                ):
                    raise ValueError("Missing or inconsistent frozen submission")
                if raw["baseline_commit"] != source["baseline_commit"]:
                    raise ValueError("Inconsistent baseline identity")
                changed = _git(
                    repo,
                    "diff",
                    "--name-only",
                    source["baseline_commit"],
                    record["participant_commit"],
                    "--",
                    "markdown_it",
                    "pyproject.toml",
                    "tox.ini",
                )
                if changed:
                    raise ValueError(
                        f"SUT/config differs from common baseline: {changed}"
                    )
                tmp = stack.enter_context(
                    tempfile.TemporaryDirectory(prefix="phase2-timing-")
                )
                checkout = Path(tmp)
                archive = subprocess.check_output(
                    ["git", "archive", record["participant_commit"]], cwd=repo
                )
                with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                    tar.extractall(checkout, filter="data")
                nodeids = valid_pool(raw, checkout)
                cases = raw["metrics"]["case_level"]["test_cases"]
                provenance = verify_runtime(checkout, python, nodeids)
                prepared[number] = (
                    checkout,
                    nodeids,
                    len(cases) - len(nodeids),
                    provenance,
                    record,
                )
            except (
                OSError,
                ValueError,
                RuntimeError,
                subprocess.SubprocessError,
            ) as exc:
                record.update(status="collection_failed", reason=str(exc))
                manifest["participants"].append(record)
                _write_json(output / "collection_manifest.json", manifest)
                return manifest

        for number in global_order:
            checkout, nodeids, _invalid, _provenance, record = prepared[number]
            print(f"Global warmup {record['participant_id']}...", flush=True)
            run = _timed_pytest(
                python_executable=python,
                repo_root=checkout,
                nodeids=nodeids,
                timeout=protocol["timeout_seconds"],
                phase="warmup",
                index=1,
            )
            manifest["global_warmups"].append(
                {
                    "participant_number": number,
                    "run": asdict(run),
                    "included_in_formal_summary": False,
                }
            )
            _write_json(output / "collection_manifest.json", manifest)
            if run.returncode:
                record.update(status="collection_failed", reason="Global warmup failed")
                manifest["participants"].append(record)
                _write_json(output / "collection_manifest.json", manifest)
                return manifest

        for number in order:
            checkout, nodeids, invalid, provenance, record = prepared[number]
            print(f"Measuring {record['participant_id']}...", flush=True)
            try:
                timing = measure(
                    checkout, python, nodeids, invalid, protocol, provenance
                )
                record["status"] = (
                    "collected"
                    if timing["status"] in {"collected", "no_valid_tests"}
                    else "collection_failed"
                )
                record["summary"] = {
                    "metric_status": timing["status"],
                    "valid_tests_included": len(nodeids),
                    "invalid_tests_excluded": invalid,
                    "execution_time": timing["summary"],
                }
                record["output_file"] = f"raw/{record['participant_id']}.json"
                _write_json(
                    output / record["output_file"], {**record, "execution_time": timing}
                )
            except (
                OSError,
                ValueError,
                RuntimeError,
                subprocess.SubprocessError,
            ) as exc:
                record.update(status="collection_failed", reason=str(exc))
            manifest["participants"].append(record)
            _write_json(output / "collection_manifest.json", manifest)
            print(f"  {record['status']}", flush=True)
    summarize_execution_times(
        output / "collection_manifest.json", output / "summary/execution_time.csv"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument(
        "--participants", nargs="+", type=int, default=list(PARTICIPANTS)
    )
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    protocol = json.loads(
        Path(__file__).with_name("execution_timing_protocol.json").read_text()
    )
    manifest = collect(
        repo,
        args.source_manifest.resolve(),
        args.output_dir.resolve(),
        str(Path(args.python).absolute()),
        args.participants,
        protocol,
    )
    return 0 if all(p["status"] == "collected" for p in manifest["participants"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
