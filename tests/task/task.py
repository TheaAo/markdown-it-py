from pathlib import Path

import pytest

from markdown_it import MarkdownIt
from markdown_it.cli import parse as cli_parse


def test_non_utf8(tmp_path, capsys):
    bad_file = tmp_path / "bad-utf8.md"
    bad_file.write_bytes(b"\x80not-valid-utf8")

    with pytest.raises(SystemExit) as exc_info:
        cli_parse.main([str(bad_file)])

    assert exc_info.value.code == 1, "Expected abnormal exit code for invalid UTF-8 input"

    captured = capsys.readouterr()
    assert "Cannot decode file" in captured.err
    assert "UTF-8" in captured.err


def test_core_after():
    order: list[str] = []

    def custom_core_rule(state):
        order.append("custom_core_rule")

    def plugin(md: MarkdownIt):
        md.core.ruler.after("normalize", "custom_core_rule", custom_core_rule)

    md = MarkdownIt("commonmark")
    md.use(plugin)

    core_rules = md.get_all_rules()["core"]
    assert core_rules.index("custom_core_rule") > core_rules.index("normalize")

    md.parse("Hello, **world**!")
    assert "custom_core_rule" in order
