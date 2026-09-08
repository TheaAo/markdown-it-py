from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.rules_block.fence import make_fence_rule

def _make_colon_fence_md() -> MarkdownIt:
    """Create a MarkdownIt instance with a colon fence rule (like colon_fence plugin)."""
    md = MarkdownIt()
    colon_rule = make_fence_rule(
        markers=(":",),
        token_type="colon_fence",
        disallow_marker_in_info=(),
    )
    md.block.ruler.after(
        "fence",
        "colon_fence",
        colon_rule,
        {"alt": ["paragraph", "reference", "blockquote", "list"]},
    )
    return md

def test_make_fence_after():
    md = _make_colon_fence_md()
    tokens = md.parse(":::\nfoo\n:::\n")
    assert len(tokens) == 1
    assert tokens[0].type == "colon_fence"
    assert tokens[0].content == "foo\n"
    assert tokens[0].markup == ":::"

    tokens = md.parse("```\nfoo\n```\n")
    assert tokens[0].type == "fence"
    assert tokens[0].content == "foo\n"

def _make_only_colon_fence_md() -> MarkdownIt:
    md = MarkdownIt()
    colon_rule = make_fence_rule(
        markers=(":",),
        token_type="colon_fence",
        disallow_marker_in_info=(),
    )
    md.block.ruler.at(
        "fence",
        colon_rule,
    )
    return md

def test_make_fence_at():
    md = _make_only_colon_fence_md()
    tokens = md.parse(":::\nfoo\n:::\n")
    assert len(tokens) == 1
    assert tokens[0].type == "colon_fence"
    assert tokens[0].content == "foo\n"
    assert tokens[0].markup == ":::"

    tokens = md.parse("```\nfoo\n```\n")
    assert not tokens[0].type == "fence"