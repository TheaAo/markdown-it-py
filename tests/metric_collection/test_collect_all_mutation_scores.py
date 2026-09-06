import json
from pathlib import Path

from scripts.metric_collection.collect_all_mutation_scores import (
    _archive_existing_result,
)


def test_archive_existing_result_preserves_original(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw/experiment-11.json"
    raw_path.parent.mkdir(parents=True)
    payload = {"mutation": {"summary": {"killed": 3018}}}
    raw_path.write_text(json.dumps(payload), encoding="utf-8")

    archived = _archive_existing_result(raw_path, tmp_path / "history")

    assert archived is not None
    assert json.loads(archived.read_text(encoding="utf-8")) == payload
    assert json.loads(raw_path.read_text(encoding="utf-8")) == payload


def test_archive_existing_result_is_content_addressed(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw/experiment-11.json"
    raw_path.parent.mkdir(parents=True)
    raw_path.write_text('{"result": 1}', encoding="utf-8")

    first = _archive_existing_result(raw_path, tmp_path / "history")
    second = _archive_existing_result(raw_path, tmp_path / "history")

    assert first == second
    assert first is not None and first.is_file()
