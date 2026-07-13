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
    md = MarkdownIt('commonmark')

    # read file
    spec_path = Path(__file__).parent.joinpath("materials", "spec.md")
    text = Path(spec_path).read_text(encoding="utf-8")

    expected_html_path = Path(__file__).parent.joinpath("materials", "test_file.html")
    expected_html = Path(expected_html_path).read_text(encoding="utf-8")
    
    # render
    tokens = md.parse(text)
    rendered_html = md.render(text)

    # assert
    assert rendered_html == expected_html


# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
def load_test_data():
    json_path = Path(__file__).parent.joinpath("materials", "commonmark.json")
    with open(json_path, 'r', encoding="utf-8") as json_file:
        data = json.load(json_file)
        return data

@pytest.mark.parametrize("test_case", load_test_data())
def test_spec(test_case):
    md = MarkdownIt("commonmark")

    text = test_case['markdown']
    expected_html = test_case['html']
    # 用parseInline替换render是规范化处理blockquote吗 —— 看起来不是
    tokens = md.parseInline(text)
    rendered_html = md.render(text)

    assert rendered_html == expected_html


# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# Requirements:
# - Define a custom Core rule function. This function should take a `state` parameter 
# and be used to mark that “the rule has been executed”, for example by printing a fixed string;
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
    
    MarkdownIt().use(_plugin).parse("[")
    assert "plugin called" in capsys.readouterr().out


# Please test the program’s behavior when processing a non-existent file path.
# Requirements:
# - Provide a non-existent file path as input;
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code.
def test_parse_fail():
    with pytest.raises(SystemExit) as excinfo:
            path = pathlib.Path(__file__).joinpath("not_existed_file.md")
            parse.main([str(path)])
    assert excinfo.value.code == 1

# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.
def test_non_utf8():
    file_path = Path(__file__).parent.joinpath("materials", "nonutf8.md")
    parse.main([str(file_path)])
    string_io = io.StringIO()
    with redirect_stdout(string_io):
        assert parse.main([str(file_path)]) == 0
    assert string_io.getvalue() == "<h1>你好世界</h1>\n"

def test_injected_runtime_error():
    undefined_runtime_value  # noqa: B018, F821


def test_injected_function_error():
    assert MarkdownIt("commonmark").render("# injected") == "<p>wrong</p>\n"


def test_injected_syntax_error():
    if True print("broken syntax")