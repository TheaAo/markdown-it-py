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
# def test_file():


# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
# def test_spec():

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
# def test_parse_fail():

# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.
def test_non_utf8(tmp_path, capsys):
    file_path = tmp_path / "non_utf8.md"
    file_path.write_bytes(b"Invalid UTF-8: " + bytes([0xFF, 0xFE]))

    with pytest.raises(SystemExit) as excinfo:
        parse.convert_file(str(file_path))

    assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert f'Cannot decode file "{file_path}" as UTF-8.' in captured.err


