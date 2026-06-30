from contextlib import redirect_stdout
import io
import json
import pathlib
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from markdown_it import MarkdownIt
from markdown_it.cli import parse

md_file_path = 'tests/task/materials/spec.md'
html_file_path = 'tests/task/materials/test_file.html'
# Please test the program’s parsing and rendering behavior when processing the complete CommonMark specification file.
# Requirements:
# - Read the full content of `spec.md`;
# - Render it into HTML using the CommonMark configuration;
# - Compare the rendered result with the full content of `test_file.html`;
# - This test can serve as an overall regression test for the parsing and rendering functionality.
def test_file():
    md = MarkdownIt()
    with open(md_file_path, 'r', encoding='utf-8') as f:
        md_content = f.read()

    with open(html_file_path, 'r', encoding='utf-8') as f:
        expected_html = f.read()

    rendered_html = md.render(md_content)

    assert rendered_html.strip() == expected_html.strip()

# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
def test_spec():
    md = MarkdownIt()
    with open("tests/task/materials/commonmark.json", "r") as file:
        json_data = json.load(file)

    for data in json_data:
        #print(f"markdown: {data["markdown"]}, html: {data["html"]}")
        rendered_html = md.render(data["markdown"])
        assert rendered_html == data["html"]

# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# Requirements:
# - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by printing a fixed string;
# - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# - Verify that the custom rule is actually called.
def core_rule(state):
    print("the rule has been executed")
    return False
def test_core_after(capsys):
    def _plugin(_md: MarkdownIt) -> None:
        _md.core.ruler.after("normalize", "core_rule", core_rule)

    MarkdownIt().use(_plugin).parse("[")
    assert "the rule has been executed" in capsys.readouterr().out


# Please test the program’s behavior when processing a non-existent file path.
# Requirements:
# - Provide a non-existent file path as input;
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code.
def test_parse_fail():
    non_exist_file = "./non_exist.json"

# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.
#def test_non_utf8():



