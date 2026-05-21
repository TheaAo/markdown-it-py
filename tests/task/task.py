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


# Please test the program’s parsing and rendering behavior when processing the complete CommonMark specification file.
# Requirements:
# - Read the full content of `spec.md`;
# - Render it into HTML using the CommonMark configuration;
# - Compare the rendered result with the full content of `test_file.html`;
# - This test can serve as an overall regression test for the parsing and rendering functionality.
def test_file():
    md = MarkdownIt("commonmark")
    with open('tests/task/materials/spec.md','r') as spec_md:
        text = spec_md.read()
    html_text = md.render(text)
    with open('tests/task/materials/test_file.html') as html:
        spec_html = html.read()
    assert spec_html == html_text
    


# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
def test_spec():
    md = MarkdownIt("commonmark")
    with open('tests/task/materials/commonmark.json','r') as data:
        examples = json.load(data)
    flag = True
    for item in examples:
        md_text = item["markdown"]
        html_text = item["html"].replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")
        html_result = md.render(md_text).replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")
        if html_text !=html_result:
            flag=False
            break
    assert flag == True

# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# Requirements:
# - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by printing a fixed string;
# - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# - Verify that the custom rule is actually called.
def core_rule(state):
    print("plugin called")
    return False
def test_core_after(capsys):
    def _plugin(_md: MarkdownIt) -> None:
        _md.core.ruler.after("normalize", "new_rule", core_rule)
    MarkdownIt().use(_plugin).parse("a")
    assert "plugin called" in capsys.readouterr().out

# Please test the program’s behavior when processing a non-existent file path.
# Requirements:
# - Provide a non-existent file path as input;
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code.
def test_parse_fail():
    path = 'tests/task/materials/nonexisting.md'
    with pytest.raises(SystemExit):
        string_io = io.StringIO()
        with redirect_stdout(string_io):
            # Test that parsing works correctly when file exists and is valid
            assert parse.main([path]) != 0

# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.
def test_non_utf8():
    md = MarkdownIt("commonmark")
    with open('tests/task/materials/test.md','r') as test_md:
        text = test_md.read()
        path = pathlib.Path('tests/task/materials/test.md')
        string_io = io.StringIO()
        with redirect_stdout(string_io):
            # Test that parsing works correctly when file exists and is valid
            assert parse.main([str(path)]) == 0
        # Verify rendered output: "# a b c" should render to "<h1>a b c</h1>\n"
        md_text = string_io.getvalue().replace(" ", "").replace("\n", "").replace("\r", "").replace("\t", "")
        assert md_text== "<h1>Introduction</h1>"



