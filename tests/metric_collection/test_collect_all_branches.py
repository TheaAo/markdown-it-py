from pathlib import Path

from scripts.collect_all_branches import (
    _branch_ref,
    _collect_branch,
    _protected_changes,
)


def test_branch_ref_uses_zero_padded_participant_number():
    assert _branch_ref("origin", "experiment-", 1) == "origin/experiment-01"
    assert _branch_ref("origin", "experiment-", 16) == "origin/experiment-16"


def test_protected_changes_detect_sut_and_configuration_files():
    changed_files = [
        "tests/task/task.py",
        "markdown_it/main.py",
        "pyproject.toml",
        "tox.ini",
    ]

    assert _protected_changes(changed_files) == [
        "markdown_it/main.py",
        "pyproject.toml",
        "tox.ini",
    ]


def test_non_participant_is_recorded_without_git_access(tmp_path: Path):
    record = _collect_branch(
        repo_root=tmp_path,
        collector_path=tmp_path / "collect_error_rates.py",
        python_executable=tmp_path / "python",
        baseline_ref="origin/experiment-base",
        baseline_commit="baseline",
        collector_commit="collector",
        remote="origin",
        branch_prefix="experiment-",
        participant_number=13,
        output_dir=tmp_path / "results",
        timeout=120,
        worktree_parent=tmp_path / "worktrees",
    )

    assert record["participant_id"] == "experiment-13"
    assert record["status"] == "not_participated"
