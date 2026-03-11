from markdown_it import MarkdownIt


INLINE_SENTINEL = object()
BLOCK_SENTINEL = object()
CORE_SENTINEL = object()


# 如何获取规则链里规则的位置？通过 ruler.__rules__ 可以拿到一个列表，里面是 Rule 对象，Rule.name 就是规则的名字。
# 需要写在任务说明里
def _rule_names(ruler):
    return [rule.name for rule in ruler.__rules__]


def _index_of(names, name):
    return names.index(name)


def _inline_rule(state, silent):
    return False


def _block_rule(state, startLine, endLine, silent):
    return False


def _core_rule(state):
    return None


def test_inline_before_inserts_rule_before_target():
    md = MarkdownIt()

    def _plugin(_md: MarkdownIt) -> None:
        _md.inline.ruler.before("text", "new_rule", _inline_rule)

    md.use(_plugin)
    names = _rule_names(md.inline.ruler)

    assert _index_of(names, "new_rule") == _index_of(names, "text") - 1


def test_inline_after_inserts_rule_after_target():
    md = MarkdownIt()

    def _plugin(_md: MarkdownIt) -> None:
        _md.inline.ruler.after("text", "new_rule", _inline_rule)

    md.use(_plugin)
    names = _rule_names(md.inline.ruler)

    assert _index_of(names, "new_rule") == _index_of(names, "text") + 1


def test_inline_at_replaces_rule_function_in_place():
    md = MarkdownIt()
    original_rule = md.inline.ruler.__rules__[_index_of(_rule_names(md.inline.ruler), "text")]
    assert original_rule.fn is not INLINE_SENTINEL

    def _plugin(_md: MarkdownIt) -> None:
        _md.inline.ruler.at("text", INLINE_SENTINEL)

    md.use(_plugin)
    names = _rule_names(md.inline.ruler)
    text_rule = md.inline.ruler.__rules__[_index_of(names, "text")]

    assert text_rule.name == "text"
    assert text_rule.fn is INLINE_SENTINEL


def test_block_before_inserts_rule_before_target():
    md = MarkdownIt()

    def _plugin(_md: MarkdownIt) -> None:
        _md.block.ruler.before("hr", "new_rule", _block_rule)

    md.use(_plugin)
    names = _rule_names(md.block.ruler)

    assert _index_of(names, "new_rule") == _index_of(names, "hr") - 1


def test_block_after_inserts_rule_after_target():
    md = MarkdownIt()

    def _plugin(_md: MarkdownIt) -> None:
        _md.block.ruler.after("hr", "new_rule", _block_rule)

    md.use(_plugin)
    names = _rule_names(md.block.ruler)

    assert _index_of(names, "new_rule") == _index_of(names, "hr") + 1


def test_block_at_replaces_rule_function_in_place():
    md = MarkdownIt()
    original_rule = md.block.ruler.__rules__[_index_of(_rule_names(md.block.ruler), "hr")]
    assert original_rule.fn is not BLOCK_SENTINEL

    def _plugin(_md: MarkdownIt) -> None:
        _md.block.ruler.at("hr", BLOCK_SENTINEL)

    md.use(_plugin)
    names = _rule_names(md.block.ruler)
    hr_rule = md.block.ruler.__rules__[_index_of(names, "hr")]

    assert hr_rule.name == "hr"
    assert hr_rule.fn is BLOCK_SENTINEL


def test_core_before_inserts_rule_before_target():
    md = MarkdownIt()

    def _plugin(_md: MarkdownIt) -> None:
        _md.core.ruler.before("normalize", "new_rule", _core_rule)

    md.use(_plugin)
    names = _rule_names(md.core.ruler)

    assert _index_of(names, "new_rule") == _index_of(names, "normalize") - 1


def test_core_after_inserts_rule_after_target():
    md = MarkdownIt()

    def _plugin(_md: MarkdownIt) -> None:
        _md.core.ruler.after("normalize", "new_rule", _core_rule)

    md.use(_plugin)
    names = _rule_names(md.core.ruler)

    assert _index_of(names, "new_rule") == _index_of(names, "normalize") + 1


def test_core_at_replaces_rule_function_in_place():
    md = MarkdownIt()
    original_rule = md.core.ruler.__rules__[_index_of(_rule_names(md.core.ruler), "normalize")]
    assert original_rule.fn is not CORE_SENTINEL

    def _plugin(_md: MarkdownIt) -> None:
        _md.core.ruler.at("normalize", CORE_SENTINEL)

    md.use(_plugin)
    names = _rule_names(md.core.ruler)
    normalize_rule = md.core.ruler.__rules__[_index_of(names, "normalize")]

    assert normalize_rule.name == "normalize"
    assert normalize_rule.fn is CORE_SENTINEL
