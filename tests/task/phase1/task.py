from contextlib import redirect_stderr
import json
import tempfile
from pathlib import Path

import pytest

from markdown_it import MarkdownIt
from markdown_it.cli import parse


# Please test the program’s parsing and rendering behavior when processing the complete CommonMark specification file.
# Requirements:
# - Read the full content of `spec.md`;
# - Render it into HTML using the CommonMark configuration;
# - Compare the rendered result with the full content of `test_file.html`;
# - This test can serve as an overall regression test for the parsing and rendering functionality.
def test_file():

    materials = Path(__file__).parent / "materials"
    text_file_line = (materials / "test_file.html").read_text(encoding="utf-8")
    text_lines = (materials / "spec.md").read_text(encoding="utf-8")

    md = MarkdownIt("commonmark")
    html_text = md.render(text_lines)

    assert html_text == text_file_line

# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
def test_spec():
    materials = Path(__file__).parent / "materials"
    json_data = json.loads((materials / "commonmark.json").read_text(encoding="utf-8"))

    m_h = dict((item["markdown"], item["html"]) for item in json_data)

    for k, v in m_h.items():
        md = MarkdownIt("commonmark")
        html_text = md.render(k)

        assert ''.join(html_text.split()) == ''.join(v.split())

# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# Requirements:
# - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by printing a fixed string;
# - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# - Verify that the custom rule is actually called.
def test_core_after():
    events = []

    def custom_rule(state):
        events.append(state.src)

    def plugin(md):
        md.core.ruler.after("normalize", "custom_rule", custom_rule)

    md = MarkdownIt("commonmark").use(plugin)
    md.parse("first\r\nsecond")

    assert events == ["first\nsecond"]

# Please test the program’s behavior when processing a non-existent file path.
# Requirements:
# - Provide a non-existent file path as input;
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code.
def test_parse_fail():
    filepath = Path(__file__).parent / "materials" / "AAA.json"
    with pytest.raises(SystemExit) as exc_info:
        parse.main([str(filepath)])
    assert exc_info.value.code == 1
    
# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.
def test_non_utf8():
    with tempfile.TemporaryDirectory() as tempdir:
        path = Path(tempdir) / "invalid.md"
        path.write_bytes(b"valid markdown\xff\n")
        error_output = tempfile.SpooledTemporaryFile(mode="w+")

        with pytest.raises(SystemExit) as exc_info:
            with redirect_stderr(error_output):
                parse.main([str(path)])

        error_output.seek(0)
        assert exc_info.value.code == 1
        assert f'Cannot decode file "{path}" as UTF-8.' in error_output.read()
    
def test_parse():
    with tempfile.TemporaryDirectory() as tempdir:
        path = Path(tempdir).joinpath("test.md")
        path.write_text("a b c")
        assert parse.main([str(path)]) == 0  # File exists and parses successfully, returns exit code 0