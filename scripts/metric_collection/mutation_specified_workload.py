from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile

import pytest

from markdown_it import MarkdownIt
from markdown_it.cli import parse

try:
    from scripts.metric_collection.mutation_workload_common import (
        canonical_commonmark_html,
    )
except ModuleNotFoundError:  # pragma: no cover
    from mutation_workload_common import (  # type: ignore[no-redef]
        canonical_commonmark_html,
    )


MATERIALS = Path(__file__).parent / "mutation_materials"
if not MATERIALS.is_dir():
    MATERIALS = Path(__file__).parents[2] / "tests/task/materials"


def test_complete_specification() -> None:
    markdown = (MATERIALS / "spec.md").read_text(encoding="utf-8")
    expected = (MATERIALS / "test_file.html").read_text(encoding="utf-8")
    assert MarkdownIt("commonmark").render(markdown) == expected


CASES = json.loads((MATERIALS / "commonmark.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda case: f"example_{case['example']}")
def test_commonmark_examples(case: dict[str, object]) -> None:
    rendered = MarkdownIt("commonmark").render(str(case["markdown"]))
    assert canonical_commonmark_html(rendered) == canonical_commonmark_html(
        str(case["html"])
    )


def test_ruler_after_executes_rule() -> None:
    called: list[bool] = []

    def rule(state: object) -> None:
        called.append(True)

    def plugin(md: MarkdownIt) -> None:
        md.core.ruler.after("normalize", "reference_rule", rule)

    MarkdownIt().use(plugin).parse("text")
    assert called == [True]


def test_cli_missing_file_exits_abnormally() -> None:
    with pytest.raises(SystemExit) as error:
        parse.main([str(MATERIALS / "missing.md")])
    assert error.value.code == 1


def test_cli_handles_non_utf8_file() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "latin1.md"
        path.write_text("# Héllo", encoding="latin-1")
        output = io.StringIO()
        with redirect_stdout(output):
            assert parse.main([str(path)]) == 0
        assert output.getvalue()
