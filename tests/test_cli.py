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
        assert parse.main([str(path)]) == 0 # 文件存在且可解析时返回退出码 0 (见 parse.py main 返回值)


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
            # 测试整个解析过程是否顺利，当前情况（存在可解析的文件）应该正确
            assert parse.main([str(path)]) == 0
        # 测试解析结果是否正确，# a b c 正好对应 <h1>a b c</h1>\n
        assert string_io.getvalue() == "<h1>a b c</h1>\n"

# 测试从标准输入解析的情况，test_parse_output 是测试从文件解析
def test_stdin():
    with patch("sys.stdin", io.StringIO("# a b c")):
        string_io = io.StringIO()
        with redirect_stdout(string_io):
            assert parse.main(["--stdin"]) == 0
        assert string_io.getvalue() == "<h1>a b c</h1>\n"


def test_multiple_files():
    with tempfile.TemporaryDirectory() as tempdir:
        path1 = pathlib.Path(tempdir).joinpath("test1.md")
        path1.write_text("# file 1")
        path2 = pathlib.Path(tempdir).joinpath("test2.md")
        path2.write_text("* file 2")
        string_io = io.StringIO()
        with redirect_stdout(string_io):
            assert parse.main([str(path1), str(path2)]) == 0
        assert string_io.getvalue() == "<h1>file 1</h1>\n<ul>\n<li>file 2</li>\n</ul>\n"


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
