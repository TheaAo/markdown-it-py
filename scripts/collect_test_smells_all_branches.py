from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

try:
    from scripts.collect_test_smells import collect_test_smells
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from collect_test_smells import collect_test_smells  # type: ignore[no-redef]


TASK_PATH = "tests/task/task.py"


def _collector_hashes() -> dict[str, str]:
    script_dir = Path(__file__).parent
    names = (
        "collect_test_smells_all_branches.py",
        "collect_test_smells.py",
        "detect_test_smells_ast.py",
    )
    return {
        name: hashlib.sha256((script_dir / name).read_bytes()).hexdigest()
        for name in names
    }


def _read_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _git_show(repo_root: Path, commit: str, path: str) -> str:
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=repo_root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"git show {commit}:{path} failed: {detail}")
    return completed.stdout


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    return {
        field: report[field]
        for field in (
            "total_source_tests",
            "eligible_test_count",
            "invalid_test_count",
            "smelly_test_count",
            "confirmed_pair_count",
            "uncertain_pair_count",
            "smelly_test_rate",
            "mean_smells_per_test",
            "test_smell_density",
            "per_smell",
        )
    }


def collect_all(
    *,
    repo_root: Path,
    error_manifest_path: Path,
    output_dir: Path,
    pytest_smell_executable: Path | None,
    tempy_root: Path | None,
    python_executable: str,
    timeout: float,
) -> dict[str, Any]:
    error_manifest = _read_object(error_manifest_path)
    participants = error_manifest.get("participants")
    if not isinstance(participants, list):
        raise ValueError("error-rate manifest must contain a participants array")

    collected: list[dict[str, Any]] = []
    for participant in participants:
        if not isinstance(participant, dict):
            raise ValueError("participant manifest entry must be an object")
        record = {
            field: participant[field]
            for field in ("participant_id", "participant_number", "status")
            if field in participant
        }
        if participant.get("status") != "collected":
            if "reason" in participant:
                record["reason"] = participant["reason"]
            collected.append(record)
            continue

        participant_id = participant.get("participant_id")
        participant_commit = participant.get("participant_commit")
        output_file = participant.get("output_file")
        if not all(
            isinstance(value, str) and value
            for value in (participant_id, participant_commit, output_file)
        ):
            record.update(
                status="invalid_input",
                reason="error manifest provenance is incomplete",
            )
            collected.append(record)
            continue
        assert isinstance(participant_id, str)
        assert isinstance(participant_commit, str)
        assert isinstance(output_file, str)
        error_raw_path = error_manifest_path.parent / output_file
        try:
            error_raw = _read_object(error_raw_path)
            test_source = _git_show(repo_root, participant_commit, TASK_PATH)
            with tempfile.TemporaryDirectory(
                prefix=f"{participant_id}-test-smell-"
            ) as temp_dir:
                test_path = Path(temp_dir) / "task.py"
                test_path.write_text(test_source, encoding="utf-8")
                report = collect_test_smells(
                    test_path=test_path,
                    error_rates=error_raw.get("metrics", error_raw),
                    pytest_smell_executable=pytest_smell_executable,
                    tempy_root=tempy_root,
                    python_executable=python_executable,
                    evidence_dir=output_dir / "tools" / participant_id,
                    timeout=timeout,
                )
                report["test_path"] = TASK_PATH
        except (OSError, RuntimeError, ValueError, SyntaxError) as exc:
            record.update(status="collection_failed", reason=str(exc))
            collected.append(record)
            continue

        raw_path = output_dir / "raw" / f"{participant_id}.json"
        raw_payload = {
            "participant_id": participant_id,
            "participant_number": participant.get("participant_number"),
            "branch": participant.get("branch"),
            "participant_commit": participant_commit,
            "error_rate_input": str(error_raw_path),
            "error_rate_collector_commit": error_raw.get("collector_commit"),
            "test_smell": report,
        }
        _write_json(raw_path, raw_payload)
        record.update(
            status="collected",
            participant_commit=participant_commit,
            output_file=str(raw_path.relative_to(output_dir)),
            summary=_summary(report),
        )
        collected.append(record)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": str(repo_root),
        "source_error_manifest": str(error_manifest_path),
        "baseline_ref": error_manifest.get("baseline_ref"),
        "baseline_commit": error_manifest.get("baseline_commit"),
        "python_executable": python_executable,
        "collector_sha256": _collector_hashes(),
        "pytest_smell_executable": (
            str(pytest_smell_executable) if pytest_smell_executable else None
        ),
        "tempy_root": str(tempy_root) if tempy_root else None,
        "participants": collected,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Collect Test Smell from saved Error Rate results without rerunning tests."
        )
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--error-manifest",
        type=Path,
        default=Path("results/error_rates/collection_manifest.json"),
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("results/test_smells")
    )
    parser.add_argument("--pytest-smell", type=Path)
    parser.add_argument("--tempy-root", type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    error_manifest = (repo_root / args.error_manifest).resolve()
    output_dir = (repo_root / args.output_dir).resolve()
    try:
        manifest = collect_all(
            repo_root=repo_root,
            error_manifest_path=error_manifest,
            output_dir=output_dir,
            pytest_smell_executable=args.pytest_smell,
            tempy_root=args.tempy_root,
            python_executable=args.python,
            timeout=args.timeout,
        )
        _write_json(output_dir / "collection_manifest.json", manifest)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    statuses: dict[str, int] = {}
    for participant in manifest["participants"]:
        status = participant["status"]
        statuses[status] = statuses.get(status, 0) + 1
    print(json.dumps(statuses, indent=2))
    return 0 if set(statuses) <= {"collected", "not_participated"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
