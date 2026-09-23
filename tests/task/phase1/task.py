from contextlib import redirect_stderr, redirect_stdout
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
# - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by appending a marker to a list;
# - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# - Verify that the custom rule is actually called;
# - Verify that the custom rule is invoked after the `normalize` rule rather than only checking final execution.
def test_core_after():
    execution_log = []

    def custom_core_rule(state):
        execution_log.append("custom_core_rule")

    md = MarkdownIt("commonmark")
    core_rule_names = md.get_all_rules()["core"]
    normalize_rule = md.core.ruler.getRules()[core_rule_names.index("normalize")]

    def tracking_normalize(state):
        execution_log.append("normalize")
        return normalize_rule(state)

    md.core.ruler.at("normalize", tracking_normalize)

    def plugin(_md):
        _md.core.ruler.after("normalize", "custom_core_rule", custom_core_rule)

    md.use(plugin)
    md.parse("Hello, **world**!")

    final_core_rule_names = md.get_all_rules()["core"]
    assert final_core_rule_names.index("normalize") < final_core_rule_names.index(
        "custom_core_rule"
    )
    assert "custom_core_rule" in execution_log
    assert execution_log.index("normalize") < execution_log.index("custom_core_rule")


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
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code;
# - Verify that the program writes a UTF-8 decode error message to stderr;
# - Do not require successful rendering to HTML.
def test_non_utf8():
    with tempfile.NamedTemporaryFile(delete=False, mode="wb") as tmp_file:
        tmp_file.write(b"\xff\xfeHello, world!\n")
        tmp_file_path = tmp_file.name

    try:
        with pytest.raises(SystemExit) as exc_info:
            with redirect_stderr(io.StringIO()) as err_stream:
                cli_parse.main([tmp_file_path])

        assert exc_info.value.code == 1, "Expected abnormal exit code for UTF-8 decode error"
        assert 'Cannot decode file' in err_stream.getvalue()
        assert "UTF-8" in err_stream.getvalue()
    finally:
        pathlib.Path(tmp_file_path).unlink()


