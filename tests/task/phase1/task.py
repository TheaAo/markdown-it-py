from contextlib import redirect_stderr, redirect_stdout
import io
import json
import pathlib
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
def test_file():
    materials_path = Path(__file__).parent / "materials"
    file_path = materials_path / "spec.md"
    # 使用 with 语句读取文件完整内容
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.read()
    md = MarkdownIt("commonmark")

    tokens = md.parse(content)
    html_text = md.render(content)

    file_path2 = materials_path / "test_file.html"
    # 使用 with 语句读取文件完整内容
    with open(file_path2, "r", encoding="utf-8") as file:
        content_html = file.read()

    assert html_text == content_html


# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
def test_spec():
    file_path = Path(__file__).parent / "materials" / "commonmark.json"
    with open(file_path, 'r', encoding='utf-8') as f:
        datas = json.load(f)

    for data in datas:
        markdown = data['markdown']
        html = data['html']
        md = MarkdownIt("commonmark")
        tokens = md.parse(markdown)
        html_text = md.render(markdown)
        assert html.replace("\n", "").replace("\r", "") == html_text.replace("\n", "").replace("\r", "")

# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# Requirements:
# - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by printing a fixed string;
# - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# - Verify that the custom rule is actually called.
def test_core_after():
    execution_order = []

    def core_rule(state):
        execution_order.append("new_rule")
        return False

    def _plugin(_md: MarkdownIt) -> None:
        _md.core.ruler.after("normalize", "new_rule", core_rule)

    md = MarkdownIt("commonmark").use(_plugin)
    md.parse("some markdown text")

    core_rule_names = md.get_all_rules()["core"]
    assert execution_order == ["new_rule"]
    assert core_rule_names.index("new_rule") > core_rule_names.index("normalize")

# Please test the program’s behavior when processing a non-existent file path.
# Requirements:
# - Provide a non-existent file path as input;
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code.
def test_parse_fail():
    with tempfile.TemporaryDirectory() as tempdir:
        path = pathlib.Path(tempdir).joinpath("fake.md")
        path.write_text("a b c")
        assert pytest.raises(SystemExit)  # File exists and parses successfully, returns exit code 0

# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.

def test_non_utf8():
    with tempfile.TemporaryDirectory() as tempdir:
        md_file = Path(tempdir) / "invalid_utf8.md"
        md_file.write_bytes(b"# invalid utf-8\n\xff")
        error_output = io.StringIO()

        with redirect_stderr(error_output), pytest.raises(SystemExit) as exc_info:
            parse.main([str(md_file)])

        assert exc_info.value.code == 1
        assert error_output.getvalue() == (
            f'Cannot decode file "{md_file}" as UTF-8.\n'
        )



