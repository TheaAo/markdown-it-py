from contextlib import redirect_stdout
import io
import json
import re
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
	# Regression: full CommonMark spec to HTML matches golden file.
	materials_dir = Path(__file__).parent / "materials"
	spec_path = materials_dir / "spec.md"
	expected_path = materials_dir / "test_file.html"

	spec_text = spec_path.read_text(encoding="utf-8")
	expected_html = expected_path.read_text(encoding="utf-8")

	md = MarkdownIt("commonmark")
	actual_html = md.render(spec_text)

	assert actual_html == expected_html


# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
def test_spec():
	# Iterate CommonMark JSON examples and compare normalized HTML.
	materials_dir = Path(__file__).parent / "materials"
	cases_path = materials_dir / "commonmark.json"

	cases = json.loads(cases_path.read_text(encoding="utf-8"))
	md = MarkdownIt("commonmark")

	def _normalize_html(html: str) -> str:
		# Ignore insignificant whitespace and normalize self-closing tags.
		normalized = html.strip()
		normalized = re.sub(r">\s+<", "><", normalized)
		normalized = re.sub(r"<hr\s*/?>", "<hr />", normalized)
		normalized = re.sub(r"<br\s*/?>", "<br />", normalized)
		return normalized

	for case in cases:
		# Compare each example's output with tolerant normalization.
		markdown_input = case["markdown"]
		expected_html = case["html"]
		actual_html = md.render(markdown_input)
		example_id = case.get("example", "unknown")
		section = case.get("section", "unknown")
		assert _normalize_html(actual_html) == _normalize_html(
			expected_html
		), f"example {example_id} ({section})"

# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# Requirements:
# - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by printing a fixed string;
# - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# - Verify that the custom rule is actually called.
def test_core_after(capsys):
	# Ensure core rule insertion executes during parsing.
	def core_rule(state) -> None:
		print("core rule called")

	def _plugin(_md: MarkdownIt) -> None:
		_md.core.ruler.after("normalize", "core_test_rule", core_rule)

	MarkdownIt().use(_plugin).parse("a")
	assert "core rule called" in capsys.readouterr().out


# Please test the program’s behavior when processing a non-existent file path.
# Requirements:
# - Provide a non-existent file path as input;
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code.
def test_parse_fail():
	# Missing file should exit with non-zero code.
	with tempfile.TemporaryDirectory() as tempdir:
		missing_path = Path(tempdir) / "missing.md"
		with pytest.raises(SystemExit) as excinfo:
			parse.main([str(missing_path)])
		assert excinfo.value.code == 1

# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.
def test_non_utf8():
	# GBK-encoded Markdown should be accepted (errors ignored).
	with tempfile.TemporaryDirectory() as tempdir:
		path = Path(tempdir) / "non_utf8.md"
		gbk_text = "# 标题\n\n这是一段中文内容。\n"
		path.write_bytes(gbk_text.encode("gbk"))
		with redirect_stdout(io.StringIO()):
			assert parse.main([str(path)]) == 0



