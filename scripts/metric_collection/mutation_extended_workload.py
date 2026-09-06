from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile

import pytest

from markdown_it import MarkdownIt
from markdown_it.cli import parse


def test_render_is_deterministic_and_handles_unicode() -> None:
    markdown = "# Héllo 世界\r\n\r\nText with *emphasis*.\r\n"
    parser = MarkdownIt("commonmark")
    first = parser.render(markdown)
    second = parser.render(markdown)
    assert first == second
    assert "<h1>Héllo 世界</h1>" in first
    assert "<em>emphasis</em>" in first


def test_render_empty_input() -> None:
    assert MarkdownIt("commonmark").render("") == ""


@pytest.mark.parametrize("anchor", ["normalize", "block", "text_join"])
def test_ruler_after_preserves_order(anchor: str) -> None:
    parser = MarkdownIt()
    before = parser.core.ruler.get_all_rules()
    parser.core.ruler.after(anchor, f"after_{anchor}", lambda state: None)
    after = parser.core.ruler.get_all_rules()
    index = after.index(anchor)
    assert after[index + 1] == f"after_{anchor}"
    assert len(after) == len(before) + 1


def test_ruler_after_invalidates_compiled_cache() -> None:
    parser = MarkdownIt()
    parser.core.ruler.getRules("")
    called: list[bool] = []
    parser.core.ruler.after(
        "normalize", "cached_rule", lambda state: called.append(True)
    )
    parser.parse("text")
    assert called == [True]


def test_ruler_after_missing_anchor() -> None:
    with pytest.raises(KeyError, match="Parser rule not found"):
        MarkdownIt().core.ruler.after("missing", "reference_rule", lambda state: None)


def test_cli_directory_path_reports_error() -> None:
    with tempfile.TemporaryDirectory() as directory:
        error_output = io.StringIO()
        with redirect_stderr(error_output), pytest.raises(SystemExit) as error:
            parse.main([directory])
        assert error.value.code == 1
        assert "Cannot open file" in error_output.getvalue()


def test_cli_missing_unicode_path_reports_error() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "missing file 世界.md"
        error_output = io.StringIO()
        with redirect_stderr(error_output), pytest.raises(SystemExit) as error:
            parse.main([str(path)])
        assert error.value.code == 1
        assert str(path) in error_output.getvalue()


@pytest.mark.parametrize(
    ("payload", "expected_fragment"),
    [
        ("# Héllo".encode("utf-16"), "<p>"),
        (b"# Hi\xffthere", "<h1>Hithere</h1>"),
    ],
)
def test_cli_handles_additional_non_utf8_classes(
    payload: bytes, expected_fragment: str
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "encoded.md"
        path.write_bytes(payload)
        output = io.StringIO()
        with redirect_stdout(output):
            assert parse.main([str(path)]) == 0
        assert expected_fragment in output.getvalue()
