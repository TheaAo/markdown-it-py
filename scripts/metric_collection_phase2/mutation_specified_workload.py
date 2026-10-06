"""Reference workload for the Phase 2 assignment; never participant score tests."""

from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile

import pytest

from markdown_it import MarkdownIt
from markdown_it.cli import parse
from markdown_it.rules_block.fence import make_fence_rule

from phase1_reference_specified import (
    test_cli_missing_file_exits_abnormally as test_cli_missing_file_exits_abnormally,
    test_commonmark_examples as test_commonmark_examples,
    test_complete_specification as test_complete_specification,
)


def test_core_after_normalize_order() -> None:
    events: list[str] = []
    md = MarkdownIt()
    original = md.core.ruler.getRules("")[
        md.core.ruler.get_active_rules().index("normalize")
    ]

    def normalize(state):
        events.append("normalize")
        original(state)

    def custom(state):
        events.append("custom")
        assert state.src == "first\nsecond"

    md.core.ruler.at("normalize", normalize)
    md.core.ruler.after("normalize", "custom", custom)
    md.parse("first\r\nsecond")
    assert events == ["normalize", "custom"]


def test_non_utf8_exits_with_decode_message() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "non-utf8.md"
        path.write_bytes(b"\xff")
        output = io.StringIO()
        with redirect_stderr(output), pytest.raises(SystemExit) as error:
            parse.main([str(path)])
        assert error.value.code == 1
        assert output.getvalue() == f'Cannot decode file "{path}" as UTF-8.\n'


def _colon_rule():
    return make_fence_rule(
        markers=(":",), token_type="colon_fence", disallow_marker_in_info=()
    )


def test_make_fence_after_keeps_default() -> None:
    md = MarkdownIt()
    md.block.ruler.after("fence", "colon_fence", _colon_rule())
    colon = md.parse("::: python\ncontent\n:::\n")
    assert len(colon) == 1
    assert (colon[0].type, colon[0].content, colon[0].info) == (
        "colon_fence",
        "content\n",
        " python",
    )
    for marker in ("```", "~~~"):
        default = md.parse(f"{marker}\ndefault\n{marker}\n")
        assert len(default) == 1
        assert (default[0].type, default[0].content) == ("fence", "default\n")


def test_make_fence_at_replaces_default() -> None:
    md = MarkdownIt()
    md.block.ruler.at("fence", _colon_rule())
    colon = md.parse("::: text\ncontent\n:::\n")
    assert len(colon) == 1
    assert (colon[0].type, colon[0].content, colon[0].info) == (
        "colon_fence",
        "content\n",
        " text",
    )
    for marker in ("```", "~~~"):
        assert not any(
            token.type == "fence"
            for token in md.parse(f"{marker}\ncontent\n{marker}\n")
        )
