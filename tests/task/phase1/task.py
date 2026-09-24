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

    with open("tests/task/materials/spec.md","r") as test_file:
        # text = "# This is a heading"
        # 使用 commonmark 的规则初始化该 parser
        
        # print(test_file.read(1000))
        # tokens = md.parse(test_file)
        html_text = md.render(test_file.read())
        # print("hey")

        Path("output.html").write_text(html_text)


    with open('output.html') as file1, open('tests/task/materials/test_file.html') as file2:
        for file1Line, file2Line in zip(file1, file2):
            assert file1Line == file2Line, "markdown content rendered result inconsperancy"
            # if file1Line != file2Line:
            #     print(file1Line.strip('\n'))
            #     print(file2Line.strip('\n'))

    # with open('1.html') as file1, open('2.html') as file2:
    #     for file1Line, file2Line in zip(file1, file2):
    #         assert file1Line == file2Line, "markdown content rendered result inconsperancy"




# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
def test_spec():

    md = MarkdownIt("commonmark")

    with open('tests/task/materials/commonmark.json') as f:
        test_json = json.load(f)
        for i in test_json:
            # assert md.render(i['html']) == 0
            html_parsed = md.render(i['html'])
            # md_goal = i['markdown']
            print(i)
            print(i['markdown'])
            print(html_parsed)
            assert html_parsed == i['markdown'] , "markdown content rendered result inconsperancy"
        

# # Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# # Requirements:
# # - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by printing a fixed string;
# # - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# # - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# # - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# # - Verify that the custom rule is actually called.
# def test_core_after(capsys):


# # Please test the program’s behavior when processing a non-existent file path.
# # Requirements:
# # - Provide a non-existent file path as input;
# # - Verify that the program raises `SystemExit`;
# # - Verify that the exit code is the abnormal exit code.
# def test_parse_fail():

# # Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# # Requirements:
# # - Construct or provide a non-UTF-8 encoded Markdown file;
# # - Invoke the command-line parsing functionality to process the file;
# # - Verify that the program can handle the input;
# # - Verify that the program exits normally with the normal exit code.
# def test_non_utf8():



