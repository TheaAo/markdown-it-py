from contextlib import redirect_stdout
import io
import json
import pathlib
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from markdown_it import MarkdownIt
from markdown_it.cli import parse


# Please test the program’s parsing and rendering behavior when processing the complete CommonMark specification file.
# Requirements:
# - Read the full content of `spec.md`;
# - Render it into HTML using the CommonMark configuration;
# - Compare the rendered result with the full content of `test_file.html`;
# - This test can serve as an overall regression test for the parsing and rendering functionality.
def normalize_html(html: str) -> str:
    html = html.replace("\r\n", "\n").strip()
    html = re.sub(r">\s+<", "><", html)
    return html


def test_file():
    spec_path = Path(__file__).parent / "materials" / "spec.md"
    expected_path = Path(__file__).parent / "materials" / "test_file.html"

    with open(spec_path, "r", encoding="utf-8") as f:
        spec_text = f.read()
    with open(expected_path, "r", encoding="utf-8") as f:
        expected_html = f.read()

    md = MarkdownIt("commonmark")
    rendered = md.render(spec_text)
    assert normalize_html(rendered) == normalize_html(expected_html)


def load_commonmark_cases():
    commonmark_json = Path(__file__).parent / "materials" / "commonmark.json"
    with open(commonmark_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [(item["example"], item["markdown"], item["html"]) for item in data]


COMMONMARK_CASES = load_commonmark_cases()


@pytest.mark.parametrize(
    "example,markdown,expected_html",
    COMMONMARK_CASES,
    ids=[f"example_{example}" for example, _, _ in COMMONMARK_CASES],
)
def test_spec(example, markdown, expected_html):
    md = MarkdownIt("commonmark")
    rendered = md.render(markdown)
    assert normalize_html(rendered) == normalize_html(expected_html)


# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
# NOTE: `test_spec` below is the parameterized fixture-based implementation for this requirement.
# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# Requirements:
# - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by printing a fixed string;
# - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# - Verify that the custom rule is actually called.
def test_core_after(capsys):
    def core_rule(state):
        print("core plugin called")

    def _plugin(_md: MarkdownIt) -> None:
        _md.core.ruler.after("normalize", "new_core_rule", core_rule)

    MarkdownIt().use(_plugin).parse("a")
    assert "core plugin called" in capsys.readouterr().out


# Please test the program’s behavior when processing a non-existent file path.
# Requirements:
# - Provide a non-existent file path as input;
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code.
def test_parse_fail():
    missing_path = Path(__file__).parent / "nonexistent_file_12345.md"
    with pytest.raises(SystemExit) as exc_info:
        parse.main([str(missing_path)])
    assert exc_info.value.code == 1

# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.
def test_non_utf8():
    with tempfile.TemporaryDirectory() as tempdir:
        path = pathlib.Path(tempdir).joinpath("test_non_utf8.md")
        # Write Markdown content in Latin-1 encoding (not UTF-8)
        content = "# Héllo\n\nSöme tëxt with äccënts"
        path.write_text(content, encoding="latin-1")

        string_io = io.StringIO()
        with redirect_stdout(string_io):
            result = parse.main([str(path)])

        # Should exit normally with exit code 0
        assert result == 0
        # Verify output was produced
        assert len(string_io.getvalue()) > 0


