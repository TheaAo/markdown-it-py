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
    materials = Path(__file__).resolve().parent / "materials"
    with open(materials / "spec.md", encoding="utf-8") as spec_file:
        spec = spec_file.read()
    with open(materials / "test_file.html", encoding="utf-8") as html_file:
        expected_html = html_file.read()

    html_text = MarkdownIt("commonmark").render(spec)

    assert expected_html == html_text


# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
def test_spec():
    # read .json , extact input and html output
    materials = Path(__file__).resolve().parent / "materials"
    with open(materials / "commonmark.json", encoding="utf-8") as jsonfile:
        data = json.load(jsonfile)

    md = MarkdownIt("commonmark")
    for example in data:
        html_text = md.render(example["markdown"])
        expected_html = example["html"].replace(
            "<blockquote>\n</blockquote>\n", "<blockquote></blockquote>\n"
        )
        assert expected_html == html_text


# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# Requirements:
# - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by printing a fixed string;
# - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# - Verify that the custom rule is actually called.
def test_core_after(capsys):
    calls = []

    def core_rule(state):
        calls.append("new_rule")

    def plugin(md: MarkdownIt) -> None:
        md.core.ruler.after("normalize", "new_rule", core_rule)

    md = MarkdownIt("commonmark")
    md.use(plugin).parse("some markdown text")

    core_rule_names = md.get_all_rules()["core"]

    assert calls == ["new_rule"]
    assert core_rule_names.index("new_rule") == core_rule_names.index("normalize") + 1


# Please test the program’s behavior when processing a non-existent file path.
# Requirements:
# - Provide a non-existent file path as input;
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code.
def test_parse_fail(tmp_path):
    path = tmp_path / "missing.md"

    with pytest.raises(SystemExit) as exc_info:
        parse.main([str(path)])

    assert exc_info.value.code == 1


# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.
def test_non_utf8(capsys):
    with tempfile.TemporaryDirectory() as tempdir:
        path = pathlib.Path(tempdir) / "invalid.md"
        path.write_bytes(b"# invalid UTF-8: \xff\n")

        with pytest.raises(SystemExit) as exc_info:
            parse.main([str(path)])

    assert exc_info.value.code == 1
    assert capsys.readouterr().err == f'Cannot decode file "{path}" as UTF-8.\n'





