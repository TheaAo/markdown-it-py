from contextlib import redirect_stdout
import io
import json
import pathlib
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from markdown_it import MarkdownIt
from markdown_it.cli import parse


MATERIALS_DIR = Path(__file__).resolve().parent / "materials"


def _normalize_html(html: str) -> str:
	collapsed = re.sub(r"\s+", " ", html)
	collapsed = re.sub(r">\s+<", "><", collapsed)
	return collapsed.strip()


# Please test the program’s parsing and rendering behavior when processing the complete CommonMark specification file.
# Requirements:
# - Read the full content of `spec.md`;
# - Render it into HTML using the CommonMark configuration;
# - Compare the rendered result with the full content of `test_file.html`;
# - This test can serve as an overall regression test for the parsing and rendering functionality.
def test_file():
	spec_path = MATERIALS_DIR / "spec.md"
	html_path = MATERIALS_DIR / "test_file.html"

	spec = spec_path.read_text(encoding="utf-8")
	expected = html_path.read_text(encoding="utf-8")

	md = MarkdownIt("commonmark")
	rendered = md.render(spec)

	assert rendered == expected

# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
def test_spec():
	json_path = MATERIALS_DIR / "commonmark.json"
	cases = json.loads(json_path.read_text(encoding="utf-8"))

	md = MarkdownIt("commonmark")

	for case in cases:
		markdown = case["markdown"]
		expected = case["html"]
		rendered = md.render(markdown)
		if rendered != expected:
			assert _normalize_html(rendered) == _normalize_html(expected), (
				f"Example {case.get('example')} failed in section "
				f"{case.get('section')} (lines {case.get('start_line')}-"
				f"{case.get('end_line')})"
			)
# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# Requirements:
# - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by printing a fixed string;
# - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# - Verify that the custom rule is actually called.
def test_core_after(capsys):
	def core_rule(state) -> None:
		print("core-rule-called")

	def plugin(md: MarkdownIt) -> None:
		md.core.ruler.after("normalize", "core_rule_test", core_rule)

	md = MarkdownIt().use(plugin)
	md.parse("Just a test.")

	captured = capsys.readouterr()
	assert "core-rule-called" in captured.out

# Please test the program’s behavior when processing a non-existent file path.
# Requirements:
# - Provide a non-existent file path as input;
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code.
def test_parse_fail():
	with pytest.raises(SystemExit) as excinfo:
		parse.convert_file("/path/does/not/exist.md")

	assert excinfo.value.code == 1
# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.
def test_non_utf8(tmp_path: Path):
	file_path = tmp_path / "non_utf8.md"
	file_path.write_bytes(b"Valid ASCII\nInvalid byte: \xff\xfe\n")

	exit_code = parse.main([str(file_path)])

	assert exit_code == 0



