import json
import re
from pathlib import Path

import pytest

from markdown_it import MarkdownIt
from markdown_it.cli import parse as cli_parse


# Regression test: full CommonMark spec fixture should render exactly as expected.
def test_file():
    source = Path(__file__).parent / "materials" / "spec.md"
    expected_file = Path(__file__).parent / "materials" / "test_file.html"

    markdown = source.read_text(encoding="utf-8")
    expected_html = expected_file.read_text(encoding="utf-8")

    md = MarkdownIt("commonmark")
    rendered_html = md.render(markdown)

    assert rendered_html == expected_html


# Compare against CommonMark examples from the official JSON fixtures.
def normalize_html(html: str) -> str:
    html = html.replace("\r\n", "\n")
    html = re.sub(r">\s+<", "><", html)
    return html.strip() + "\n"


def test_spec():
    spec_file = Path(__file__).parent / "materials" / "commonmark.json"
    with spec_file.open(encoding="utf-8") as f:
        test_cases = json.load(f)

    md = MarkdownIt("commonmark")

    for index, case in enumerate(test_cases):
        markdown = case["markdown"]
        expected_html = case["html"]
        rendered_html = md.render(markdown)

        assert normalize_html(rendered_html) == normalize_html(expected_html), (
            f"Failed for case: {case.get('example', index)}"
        )


# Verify that a custom core rule inserted with after() is actually executed.
def test_core_after(capsys):
    def custom_core_rule(state):
        print("Custom core rule executed")

    def plugin(md):
        md.core.ruler.after("normalize", "custom_core_rule", custom_core_rule)

    md = MarkdownIt().use(plugin)
    md.parse("Hello, **world**!")

    captured = capsys.readouterr()
    assert "Custom core rule executed" in captured.out


# A missing file should exit abnormally.
def test_parse_fail():
    with pytest.raises(SystemExit) as exc_info:
        cli_parse.main(["non_existent_file.md"])
    assert exc_info.value.code != 0, "Expected non-zero exit code for non-existent file"


# Invalid UTF-8 input should trigger a CLI failure with a decode error.
def test_non_utf8(tmp_path, capsys):
    bad_file = tmp_path / "bad-utf8.md"
    bad_file.write_bytes(b"\x80not-valid-utf8")

    with pytest.raises(SystemExit) as exc_info:
        cli_parse.main([str(bad_file)])

    assert exc_info.value.code != 0, "Expected non-zero exit code for invalid UTF-8 input"
    captured = capsys.readouterr()
    assert "Cannot decode file" in captured.err
    assert "UTF-8" in captured.err


