from contextlib import redirect_stdout
import io
import pathlib
import tempfile
from unittest.mock import patch

import pytest

from markdown_it.cli import parse


def test_parse():
    with tempfile.TemporaryDirectory() as tempdir:
        path = pathlib.Path(tempdir).joinpath("test.md")
        path.write_text("a b c")
        assert parse.main([str(path)]) == 0

def test_print_heading():
    with patch("builtins.print") as patched:
        parse.print_heading()
    patched.assert_called()


def test_interactive():
    def mock_input(prompt):
        raise KeyboardInterrupt

    with patch("builtins.print") as patched, patch("builtins.input", mock_input):
        parse.interactive()
    patched.assert_called()


def test_main_no_args_is_interactive():
    with patch("markdown_it.cli.parse.interactive") as mock_interactive:
        assert parse.main([]) == 0
    mock_interactive.assert_called_once()


def test_parse_output():
    with tempfile.TemporaryDirectory() as tempdir:
        path = pathlib.Path(tempdir).joinpath("test.md")
        path.write_text("# a b c")
        string_io = io.StringIO()
        with redirect_stdout(string_io):
            assert parse.main([str(path)]) == 0
        assert string_io.getvalue() == "<h1>a b c</h1>\n"


def test_stdin():
    with patch("sys.stdin", io.StringIO("# a b c")):
        string_io = io.StringIO()
        with redirect_stdout(string_io):
            assert parse.main(["--stdin"]) == 0
        assert string_io.getvalue() == "<h1>a b c</h1>\n"


def test_interactive_render():
    # Simulate user typing '# hello', pressing Ctrl-D (renders), then Ctrl-C (exits)
    # This is needed to break the infinite loop in interactive mode on EOF.
    mock_input = patch(
        "builtins.input", side_effect=["# hello", EOFError, KeyboardInterrupt]
    )
    string_io = io.StringIO()
    with redirect_stdout(string_io), mock_input:
        parse.interactive()

    output = string_io.getvalue()
    assert "markdown-it-py" in output  # from print_heading
    # The rendered output is prefixed by a newline
    assert "\n<h1>hello</h1>\n" in output
    assert "Exiting" in output
