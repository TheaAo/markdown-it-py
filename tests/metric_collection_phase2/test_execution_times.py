import hashlib
from pathlib import Path
from typing import Any

import pytest

from scripts.metric_collection_phase1.collect_execution_time import TimedRun
from scripts.metric_collection_phase2 import collect_execution_times as collector


def test_valid_pool_rejects_changed_source_and_duplicate_items(tmp_path: Path) -> None:
    path = tmp_path / "test_task.py"
    path.write_text("def test_example(): pass\n")
    nodeid = "test_task.py::test_example"
    raw = {
        "metrics": {
            "artifact_sha256": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            },
            "valid_nodeids": [nodeid],
            "case_level": {
                "valid_test_count": 1,
                "test_cases": [
                    {"nodeid": nodeid, "classification": "valid"},
                    {
                        "nodeid": "test_task.py::test_invalid",
                        "classification": "function_error",
                    },
                ],
            },
        }
    }
    assert collector.valid_pool(raw, tmp_path) == [nodeid]
    raw["metrics"]["valid_nodeids"].append(nodeid)
    with pytest.raises(ValueError, match="inconsistent"):
        collector.valid_pool(raw, tmp_path)
    raw["metrics"]["valid_nodeids"].pop()
    path.write_text("def test_other(): pass\n")
    with pytest.raises(ValueError, match="Artifact differs"):
        collector.valid_pool(raw, tmp_path)


@pytest.mark.parametrize("fail_on", [None, "baseline", "warmup", "measurement"])
def test_measure_keeps_failures_and_times_the_joint_pool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fail_on: str | None,
) -> None:
    nodeids = ["tests/task/phase1/task.py::test_old", "tests/task/task2.py::test_new"]
    calls: list[str] = []
    monkeypatch.setattr(
        collector, "verify_runtime", lambda *args: {"selected_nodeids": nodeids}
    )

    def timer(**kwargs: Any) -> TimedRun:
        assert kwargs["nodeids"] == nodeids
        calls.append(kwargs["phase"])
        return TimedRun(
            phase=kwargs["phase"],
            index=kwargs["index"],
            elapsed_nanoseconds=kwargs["index"] * 1_000_000_000,
            returncode=1 if kwargs["phase"] == fail_on else 0,
            timed_out=False,
            failure_output="failure" if kwargs["phase"] == fail_on else None,
        )

    monkeypatch.setattr(collector, "_timed_pytest", timer)
    result = collector.measure(
        tmp_path,
        "python",
        nodeids,
        3,
        {
            "warmup_count": 2,
            "measurement_count": 3,
            "timeout_seconds": 120,
            "cv_review_threshold": 0.05,
        },
    )
    assert result["valid_tests_included"] == 2
    assert result["invalid_tests_excluded"] == 3
    if fail_on:
        assert result["status"] == "measurement_failed"
        assert result["summary"] is None
        assert calls[-1] == fail_on
        assert calls.count(fail_on) == 1
    else:
        assert calls == [
            "baseline",
            "warmup",
            "warmup",
            "measurement",
            "measurement",
            "measurement",
        ]
        assert result["summary"]["execution_time_seconds"] == 2
        assert result["summary"]["measurement_count"] == 3


@pytest.mark.parametrize(
    ("global_warmup", "fail_warmup"), [(True, False), (True, True), (False, False)]
)
def test_collection_order_and_optional_global_warmup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    global_warmup: bool,
    fail_warmup: bool,
) -> None:
    import io
    import json
    import random
    import tarfile

    source = tmp_path / "inputs"
    source.mkdir()
    participants = []
    for n in collector.PARTICIPANTS:
        p = {
            "participant_number": n,
            "participant_id": f"experiment-{n:02}",
            "branch": f"branch-{n}",
            "participant_commit": f"commit-{n}",
            "phase1_commit": "phase1",
            "phase1_group": "AI",
            "phase2_group": "AI",
            "status": "collected",
            "output_file": f"{n}.json",
        }
        participants.append(p)
        (source / p["output_file"]).write_text(
            json.dumps(
                {
                    "participant_commit": p["participant_commit"],
                    "baseline_commit": "base",
                    "metrics": {"case_level": {"test_cases": [{}]}},
                }
            )
        )
    manifest_path = source / "collection_manifest.json"
    manifest_path.write_text(
        json.dumps({"baseline_commit": "base", "participants": participants})
    )
    from types import SimpleNamespace

    machine = collector.platform.uname()._asdict()
    monkeypatch.setattr(
        collector.platform, "uname", lambda: SimpleNamespace(_asdict=lambda: machine)
    )
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w"):
        pass
    monkeypatch.setattr(
        collector.subprocess, "check_output", lambda *a, **k: archive.getvalue()
    )
    monkeypatch.setattr(
        collector, "_git", lambda repo, *args: "" if args[0] == "diff" else "head"
    )
    monkeypatch.setattr(collector, "file_hash", lambda path: "hash")
    monkeypatch.setattr(
        collector, "valid_pool", lambda raw, path: [raw["participant_commit"]]
    )
    events: list[tuple[str, str]] = []

    def verify(path: Path, python: str, nodes: list[str]) -> dict[str, Any]:
        events.append(("verify", nodes[0]))
        return {"selected_nodeids": nodes}

    def timer(**kwargs: Any) -> TimedRun:
        events.append(("global", kwargs["nodeids"][0]))
        return TimedRun("warmup", 1, 100, int(fail_warmup), False, None)

    def measure(*args: Any) -> dict[str, Any]:
        assert len(args) == 6  # Already verified provenance is passed through.
        events.append(("formal", args[2][0]))
        return {"status": "collected", "summary": {"measurement_count": 15}}

    monkeypatch.setattr(collector, "verify_runtime", verify)
    monkeypatch.setattr(collector, "_timed_pytest", timer)
    monkeypatch.setattr(collector, "measure", measure)
    monkeypatch.setattr(collector, "summarize_execution_times", lambda *args: None)
    result = collector.collect(
        tmp_path,
        manifest_path,
        tmp_path / "output",
        "python",
        list(reversed(collector.PARTICIPANTS)),
        {
            "schema_version": "test",
            "order_seed": 20261006 if global_warmup else None,
            "global_warmup_count_per_participant": int(global_warmup),
            "timeout_seconds": 120,
        },
    )
    assert [e[0] for e in events[:8]] == ["verify"] * 8
    if fail_warmup:
        assert len(events) == 9
        assert result["participants"][0]["status"] == "collection_failed"
    elif global_warmup:
        order = list(collector.PARTICIPANTS)
        random.Random(20261006).shuffle(order)
        assert result["measurement_order"] == order
        assert [e[0] for e in events[8:16]] == ["global"] * 8
        assert events[16:] == [("formal", f"commit-{n}") for n in order]
        assert len(result["global_warmups"]) == 8
        assert all(
            not r["included_in_formal_summary"] for r in result["global_warmups"]
        )

    else:
        assert events[8:] == [("formal", f"commit-{n}") for n in collector.PARTICIPANTS]
        assert result["measurement_order"] == list(collector.PARTICIPANTS)
        assert result["global_warmup_order"] == result["global_warmups"] == []
