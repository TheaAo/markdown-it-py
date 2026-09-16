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
from markdown_it.cli import parse as cli_parse


# Please test the program’s parsing and rendering behavior when processing the complete CommonMark specification file.
# Requirements:
# - Read the full content of `spec.md`;
# - Render it into HTML using the CommonMark configuration;
# - Compare the rendered result with the full content of `test_file.html`;
# - This test can serve as an overall regression test for the parsing and rendering functionality.
def test_file():
    source = Path(__file__).parent / "materials" / "spec.md"
    expected_file = Path(__file__).parent / "materials" / "test_file.html"

    markdown = source.read_text(encoding="utf-8")
    expected_html = expected_file.read_text(encoding="utf-8")

    md = MarkdownIt("commonmark")
    rendered_html = md.render(markdown)

    assert rendered_html == expected_html


# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
def normalize_html(html: str) -> str:
    html = html.replace("\r\n", "\n")
    html = re.sub(r">\s+<", "><", html)
    return html.strip() + "\n"


def test_spec():
    spec_file = Path(__file__).parent / "materials" / "commonmark.json"
    with spec_file.open(encoding="utf-8") as f:
        test_cases = json.load(f)

    md = MarkdownIt("commonmark")

    for case in test_cases:
        markdown = case["markdown"]
        expected_html = case["html"]

        rendered_html = md.render(markdown)

        assert normalize_html(rendered_html) == normalize_html(expected_html), (
            f"Failed for case: {case['example']}"
        )

# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# Requirements:
# - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by printing a fixed string;
# - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# - Verify that the custom rule is actually called.
def test_core_after(capsys):
    def custom_core_rule(state):
        print("Custom core rule executed")

    def plugin(md):
        md.core.ruler.after("normalize", "custom_core_rule", custom_core_rule)

    md = MarkdownIt().use(plugin)
    md.parse("Hello, **world**!")

    captured = capsys.readouterr()
    assert "Custom core rule executed" in captured.out


# Please test the program’s behavior when processing a non-existent file path.
# Requirements:
# - Provide a non-existent file path as input;
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code.
def test_parse_fail():
    with pytest.raises(SystemExit) as exc_info:
        cli_parse.main(["non_existent_file.md"])
    assert exc_info.value.code != 0, "Expected non-zero exit code for non-existent file"

# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.
def test_non_utf8():
    with tempfile.NamedTemporaryFile(delete=False, mode="wb") as tmp_file:
        tmp_file.write("Hello, world!".encode("latin-1"))
        tmp_file_path = tmp_file.name

    try:
        with patch("sys.argv", ["markdown-it", tmp_file_path]):
            with redirect_stdout(io.StringIO()) as f:
                cli_parse.main([tmp_file_path])
                output = f.getvalue()
                assert "Hello, world!" in output
    finally:
        pathlib.Path(tmp_file_path).unlink()


