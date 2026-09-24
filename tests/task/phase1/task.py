from contextlib import redirect_stdout
import io
import json
import pathlib
import tempfile
from pathlib import Path
from unittest.mock import patch
import re

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
    with open("tests/task/phase1/materials/spec.md","r", encoding="utf-8") as test_file:
        # text = "# This is a heading"
        # 使用 commonmark 的规则初始化该 parser
        
        # print(test_file.read(1000))
        # tokens = md.parse(test_file)
        html_text = md.render(test_file.read())
        # print("hey")

        Path("output.html").write_text(html_text, encoding="utf-8")


    with open('output.html', encoding="utf-8") as file1, open('tests/task/phase1/materials/test_file.html', encoding="utf-8") as file2:
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
    with open('tests/task/phase1/materials/commonmark.json', encoding="utf-8") as f:
        test_json = json.load(f)
        def _normalize(s: str) -> str:
            s = s.strip()
            # collapse inter-tag whitespace/newlines to a single boundary
            s = re.sub(r">\s+<", "><", s)
            return s

        for case in test_json:
            rendered = md.render(case['markdown'])
            if _normalize(rendered) != _normalize(case['html']):
                assert rendered == case['html'], (
                    "markdown content rendered result inconsperancy: example %r" % case.get('example')
                )
        

# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
def test_core_after():
    calls: list[str] = []

    def custom_core_rule(state):
        # mark that custom rule ran
        calls.append("custom")

    def plugin(md: MarkdownIt) -> None:
        # insert custom rule after normalize
        md.core.ruler.after("normalize", "new_rule", custom_core_rule)

    md = MarkdownIt("commonmark")

    # locate the original normalize function and wrap it to record execution
    active_names = md.core.ruler.get_active_rules()
    try:
        pos = active_names.index("normalize")
    except ValueError:
        pytest.skip("normalize rule not present")

    active_fns = md.core.ruler.getRules("")
    orig_normalize = active_fns[pos]

    def wrapped_normalize(state):
        calls.append("normalize")
        return orig_normalize(state)

    # replace normalize with our wrapper
    md.core.ruler.at("normalize", wrapped_normalize)

    # register plugin that inserts custom rule after normalize
    md.use(plugin)

    # run parser to trigger core rules
    md.parse("a")

    # verify custom rule was called
    assert "custom" in calls

    # verify normalize ran before custom
    assert calls.index("normalize") < calls.index("custom")


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



