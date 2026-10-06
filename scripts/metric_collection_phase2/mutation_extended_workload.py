"""Phase 2 boundary workload for catalog membership, separate from participant tests."""

from contextlib import redirect_stderr
import io
from pathlib import Path
import tempfile

import pytest

from markdown_it import MarkdownIt
from markdown_it.cli import parse
from markdown_it.rules_block.fence import make_fence_rule

from phase1_reference_extended import (
    test_cli_directory_path_reports_error as test_cli_directory_path_reports_error,
    test_cli_missing_unicode_path_reports_error as test_cli_missing_unicode_path_reports_error,
    test_render_empty_input as test_render_empty_input,
    test_render_is_deterministic_and_handles_unicode as test_render_is_deterministic_and_handles_unicode,
    test_ruler_after_invalidates_compiled_cache as test_ruler_after_invalidates_compiled_cache,
    test_ruler_after_missing_anchor as test_ruler_after_missing_anchor,
    test_ruler_after_preserves_order as test_ruler_after_preserves_order,
)


@pytest.mark.parametrize("payload", [b"\xff", b"\xfe\xff", "# Hello".encode("utf-16")])
def test_non_utf8_classes(payload: bytes) -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "input.md"
        path.write_bytes(payload)
        output = io.StringIO()
        with redirect_stderr(output), pytest.raises(SystemExit) as error:
            parse.main([str(path)])
        assert error.value.code == 1
        assert "Cannot decode file" in output.getvalue()


@pytest.mark.parametrize("exact", [False, True])
def test_colon_closing_length(exact: bool) -> None:
    md = MarkdownIt()
    md.block.ruler.after(
        "fence",
        "colon",
        make_fence_rule(
            markers=(":",),
            token_type="colon_fence",
            exact_match=exact,
            disallow_marker_in_info=(),
        ),
    )
    tokens = md.parse("::: name\nbody\n::::\n")
    assert len(tokens) == 1
    assert tokens[0].type == "colon_fence"
    assert tokens[0].content == ("body\n::::\n" if exact else "body\n")


@pytest.mark.parametrize("marker", ["`", "~"])
def test_default_factory_markers(marker: str) -> None:
    md = MarkdownIt()
    md.block.ruler.at("fence", make_fence_rule())
    tokens = md.parse(f"{marker * 3} lang\nbody\n{marker * 3}\n")
    assert len(tokens) == 1
    assert (tokens[0].type, tokens[0].content) == ("fence", "body\n")


def test_colon_minimum_and_unclosed() -> None:
    md = MarkdownIt()
    md.block.ruler.after(
        "fence",
        "colon",
        make_fence_rule(
            markers=(":",),
            token_type="colon_fence",
            disallow_marker_in_info=(),
        ),
    )
    assert not any(token.type == "colon_fence" for token in md.parse("::\nbody\n::\n"))
    tokens = md.parse("::: title\nbody\n")
    assert len(tokens) == 1
    assert tokens[0].content == "body\n"
