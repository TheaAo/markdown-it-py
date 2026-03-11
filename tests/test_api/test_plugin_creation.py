"""Test basic plugin creation functionality:
that they can be added and are called correctly
"""

from markdown_it import MarkdownIt

# before/after/at 是往某条规则链（ruler）里放规则的位置控制方法。

# 可以把规则链想成一个有顺序的列表，解析时会按这个顺序依次执行。
# 这三个方法的区别就是：你想把新规则插到哪里。

# before("text", "new_rule", rule_fn)
# 把新规则插到已有规则 text 前面

# after("text", "new_rule", rule_fn)
# 把新规则插到已有规则 text 后面

# at("text", rule_fn)
# 替换名为 text 的那条规则，让这个位置执行你的新函数


def inline_rule(state, silent):
    print("plugin called")
    return False


def test_inline_after(capsys):
    def _plugin(_md: MarkdownIt) -> None:
        _md.inline.ruler.after("text", "new_rule", inline_rule)

    MarkdownIt().use(_plugin).parse("[")
    assert "plugin called" in capsys.readouterr().out


def test_inline_before(capsys):
    def _plugin(_md: MarkdownIt) -> None:
        _md.inline.ruler.before("text", "new_rule", inline_rule)

    MarkdownIt().use(_plugin).parse("a")
    assert "plugin called" in capsys.readouterr().out


def test_inline_at(capsys):
    def _plugin(_md: MarkdownIt) -> None:
        _md.inline.ruler.at("text", inline_rule)

    MarkdownIt().use(_plugin).parse("a")
    assert "plugin called" in capsys.readouterr().out


def block_rule(state, startLine, endLine, silent):
    print("plugin called")
    return False


def test_block_after(capsys):
    def _plugin(_md: MarkdownIt) -> None:
        _md.block.ruler.after("hr", "new_rule", block_rule)

    MarkdownIt().use(_plugin).parse("a")
    assert "plugin called" in capsys.readouterr().out


def test_block_before(capsys):
    def _plugin(_md: MarkdownIt) -> None:
        _md.block.ruler.before("hr", "new_rule", block_rule)

    MarkdownIt().use(_plugin).parse("a")
    assert "plugin called" in capsys.readouterr().out


def test_block_at(capsys):
    def _plugin(_md: MarkdownIt) -> None:
        _md.block.ruler.at("hr", block_rule)

    MarkdownIt().use(_plugin).parse("a")
    assert "plugin called" in capsys.readouterr().out


def core_rule(state):
    print("plugin called")


def test_core_after(capsys):
    def _plugin(_md: MarkdownIt) -> None:
        _md.core.ruler.after("normalize", "new_rule", core_rule)

    MarkdownIt().use(_plugin).parse("a")
    assert "plugin called" in capsys.readouterr().out


def test_core_before(capsys):
    def _plugin(_md: MarkdownIt) -> None:
        _md.core.ruler.before("normalize", "new_rule", core_rule)

    MarkdownIt().use(_plugin).parse("a")
    assert "plugin called" in capsys.readouterr().out


def test_core_at(capsys):
    def _plugin(_md: MarkdownIt) -> None:
        _md.core.ruler.at("normalize", core_rule)

    MarkdownIt().use(_plugin).parse("a")
    assert "plugin called" in capsys.readouterr().out
