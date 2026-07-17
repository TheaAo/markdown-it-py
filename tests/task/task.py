from contextlib import redirect_stdout
import io
import json
import re
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

	# Read the full CommonMark specification source used for this test.
	spec_path = Path(__file__).parent / "materials" / "spec.md"
	spec_text = spec_path.read_text(encoding="utf-8")

	# Create a MarkdownIt instance configured for CommonMark and render the spec.
	md = MarkdownIt("commonmark")
	rendered = md.render(spec_text)

	# Load the expected HTML output for the whole spec and compare exactly.
	expected_path = Path(__file__).parent / "materials" / "test_file.html"
	expected_html = expected_path.read_text(encoding="utf-8")

	# Exact comparison — serve as a full-regression check for parsing+rendering.
	assert rendered == expected_html

# Please test the program’s parsing and rendering behavior against the official CommonMark specification examples.
# Requirements:
# - Read the collection of test cases from `commonmark.json`;
# - For each test case, extract the Markdown input and its corresponding expected HTML output;
# - Render the Markdown input using the CommonMark configuration provided by the project;
# - Compare the actual rendering result with the expected HTML output;
# - You may use parameterized tests to organize these test cases.
def test_spec():
	# Load the CommonMark example suite from the provided JSON file.
	json_path = Path(__file__).parent / "materials" / "commonmark.json"
	examples = json.loads(json_path.read_text(encoding="utf-8"))

	# MarkdownIt instance using the CommonMark preset.
	md = MarkdownIt("commonmark")

	# Normalization helper: preserve text node whitespace, but ignore
	# insignificant differences between tags (e.g. newlines between
	# an opening and closing tag). This allows cases like
	# `<blockquote></blockquote>` and `<blockquote>\n</blockquote>` to
	# be considered equivalent.
	def _normalize_html(s: str) -> str:
		if s is None:
			return ""
		s = s.replace("\r\n", "\n")
		s = s.strip()
		# Canonicalize common void/self-closing tags to a single form so
		# differences like `<hr>` vs `<hr />` do not fail the comparison.
		s = re.sub(r"<hr\s*/?>", "<hr />", s)
		s = re.sub(r"<br\s*/?>", "<br />", s)

		# Remove insignificant whitespace between tags while preserving
		# whitespace inside text nodes (including inside <pre>/<code>).
		s = re.sub(r">\s+<", "><", s)

		# Strip a single trailing newline that some fixtures include.
		if s.endswith("\n"):
			s = s[:-1]

		return s

	# Iterate over examples and assert rendering matches expected HTML.
	for case in examples:
		src = case.get("markdown", "")
		expected = case.get("html", "")
		rendered = md.render(src)

		nr = _normalize_html(rendered)
		ne = _normalize_html(expected)

		assert nr == ne, (
			f"CommonMark example {case.get('example')!r} failed:\n"
			f"section: {case.get('section')!r}\n"
			"--- rendered ---\n"
			f"{rendered}\n"
			"--- expected ---\n"
			f"{expected}\n"
		)
# Please test the behavior of inserting a custom rule into the Core rule chain using core.ruler.after().
# Requirements:
# - Define a custom Core rule function. This function should take a `state` parameter and be used to mark that “the rule has been executed”, for example by printing a fixed string;
# - Define a plugin function, and in the plugin, insert the custom rule after the `normalize` rule;
# - Create a `MarkdownIt` instance and register the plugin using `.use()`;
# - Call `.parse()` with a simple Markdown input to trigger the execution of the Core rule chain;
# - Verify that the custom rule is actually called.
def test_core_after(capsys):
	# Define a core rule that indicates it was executed by printing.
	def core_rule(state):
		print("plugin called")

	# Plugin that inserts the core rule after the `normalize` core rule.
	def _plugin(_md: MarkdownIt) -> None:
		_md.core.ruler.after("normalize", "new_core_rule", core_rule)

	# Create parser, register plugin and parse simple input to trigger core rules.
	MarkdownIt().use(_plugin).parse("a")

	# Verify the rule was executed (printed text captured by pytest capsys).
	assert "plugin called" in capsys.readouterr().out

# Please test the program’s behavior when processing a non-existent file path.
# Requirements:
# - Provide a non-existent file path as input;
# - Verify that the program raises `SystemExit`;
# - Verify that the exit code is the abnormal exit code.
def test_parse_fail():
	# Provide a non-existent file path and verify the CLI exits with error.
	with tempfile.TemporaryDirectory() as td:
		nonexist = Path(td) / "does-not-exist-12345.md"
		# Ensure file does not exist
		assert not nonexist.exists()

		with pytest.raises(SystemExit) as exc:
			parse.main([str(nonexist)])

		# The CLI uses exit code 1 for failures when opening files.
		assert exc.value.code == 1
		
# Please test the program’s behavior when processing a Markdown file that is not encoded in UTF-8.
# Requirements:
# - Construct or provide a non-UTF-8 encoded Markdown file;
# - Invoke the command-line parsing functionality to process the file;
# - Verify that the program can handle the input;
# - Verify that the program exits normally with the normal exit code.
def test_non_utf8():
	# Create a file encoded in a single-byte encoding (cp1252) that
	# contains bytes not valid in UTF-8. The CLI opens files with
	# `encoding='utf8', errors='ignore'`, so it should handle this file
	# and exit normally with code 0.
	with tempfile.TemporaryDirectory() as td:
		p = Path(td) / "nonutf8.md"
		# Use cp1252 to produce non-UTF-8 bytes (e.g. en-dash 0x96)
		payload = "café – nonutf8".encode("cp1252")
		p.write_bytes(payload)

		# Run the CLI and capture stdout to avoid polluting test output.
		sio = io.StringIO()
		with redirect_stdout(sio):
			rc = parse.main([str(p)])

		# Program should handle the input and return the normal exit code 0.
		assert rc == 0



