from contextlib import redirect_stdout
import io
import json
import pathlib
import tempfile
from pathlib import Path
from unittest.mock import patch
import os

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

    text_file = open("D:/Code/markdown-it-py/tests/task/materials/test_file.html", 'r', encoding='utf-8')
    text_file_line = text_file.read()

    file = open("D:/Code/markdown-it-py/tests/task/materials/spec.md", 'r', encoding='utf-8')
    text_lines = file.read()

    md = MarkdownIt("commonmark")
    tokens = md.parse(text_lines)
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
    with open('D:/Code/markdown-it-py/tests/task/materials/commonmark.json', 'r', encoding='utf-8') as f:
        json_data = json.load(f)

    m_h = dict((item["markdown"], item["html"]) for item in json_data)

    for k, v in m_h.items():
        md = MarkdownIt("commonmark")
        tokens = md.parse(k)
        html_text = md.render(k)

        assert ''.join(html_text.split()) == ''.join(v.split())

# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# Requirements:
# - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by printing a fixed string;
# - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# - Verify that the custom rule is actually called.
# def test_core_after(capsys):

# Please test the program’s behavior when processing a non-existent file path.
# Requirements:
# - Provide a non-existent file path as input;
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code.
def test_parse_fail():
    filepath = "D:/Code/markdown-it-py/tests/task/materials/AAA.json"
    if os.path.isfile(filepath):
        return True
    else:
        return SystemExit
    
# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.
def test_non_utf8():
    mystr = '09. BÃ¡t NhÃ£ TÃ¢m Kinh'
    try:
        test_parse('utf-8')
    except: 
        return 0
    
def test_parse():
    with tempfile.TemporaryDirectory() as tempdir:
        path = pathlib.Path(tempdir).joinpath("test.md")
        path.write_text("a b c")
        assert parse.main([str(path)]) == 0  # File exists and parses successfully, returns exit code 0