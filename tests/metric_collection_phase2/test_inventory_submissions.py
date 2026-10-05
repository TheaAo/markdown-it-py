from pathlib import Path
import subprocess

import pytest

from scripts.metric_collection_phase2 import inventory_submissions as inventory


@pytest.mark.parametrize(
    "missing_branch,missing_file,protected_change,expected_status",
    [
        (True, False, False, "missing_branch"),
        (False, True, False, "missing_task_file"),
        (False, False, True, "baseline_mismatch"),
        (False, False, False, "pending_submission_review"),
    ],
)
def test_inventory_keeps_missing_and_modified_submissions_distinct(
    monkeypatch: pytest.MonkeyPatch,
    missing_branch: bool,
    missing_file: bool,
    protected_change: bool,
    expected_status: str,
) -> None:
    def fake_git(repo_root: Path, *arguments: str) -> str:
        if arguments[0] == "diff":
            return "markdown_it/cli/parse.py" if protected_change else ""
        if arguments[-1].endswith(":markdown_it"):
            return "sut-tree"
        if ":tests/" in arguments[-1]:
            return "test-blob"
        return "baseline-sha"

    def fake_run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        code = int(
            (command[1] == "rev-parse" and missing_branch)
            or (
                command[1] == "cat-file"
                and command[-1].endswith("task2.py")
                and missing_file
            )
        )
        return subprocess.CompletedProcess(command, code, "phase2-sha\n", "")

    monkeypatch.setattr(inventory, "_git", fake_git)
    monkeypatch.setattr(inventory, "_run", fake_run)
    manifest = {
        "participants": [
            {
                "participant_id": "experiment-01",
                "participant_commit": "frozen-phase1-sha",
                "status": "collected",
            }
        ]
    }
    report = inventory.inventory_submissions(
        Path("/repo"), manifest, "origin/experiment-base-phase2", "origin"
    )
    record = report["participants"][0]
    assert record["status"] == expected_status
    assert record["phase1_commit"] == "frozen-phase1-sha"
    assert record["phase2_ref"] == "origin/experiment-01-phase2"
    if not missing_branch:
        assert record["phase2_commit"] == "phase2-sha"
        assert ("tests/task/task2.py" in record["task_blob_hashes"]) != missing_file


def test_inventory_does_not_assume_phase2_absence_from_phase1_dropout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(inventory, "_git", lambda *args: "baseline-sha")
    monkeypatch.setattr(
        inventory,
        "_run",
        lambda command, cwd: subprocess.CompletedProcess(command, 1, "", ""),
    )
    report = inventory.inventory_submissions(
        Path("/repo"),
        {
            "participants": [
                {
                    "participant_id": "experiment-13",
                    "status": "not_participated",
                }
            ]
        },
        "origin/experiment-base-phase2",
        "origin",
    )
    record = report["participants"][0]
    assert record["phase1_status"] == "not_participated"
    assert record["phase1_commit"] is None
    assert record["status"] == "missing_branch"
