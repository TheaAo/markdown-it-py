from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.rules_block.fence import make_fence_rule


def test_make_fence_after():
    md = MarkdownIt()
    colon_rule = make_fence_rule(
        markers=(":",),
        token_type="colon_fence",
        disallow_marker_in_info=(),
    )
    md.block.ruler.after("fence", "colon_fence", colon_rule)

    tokens = md.parse(":::\nfoo\n:::\n")
    assert len(tokens) == 1
    assert tokens[0].type == "colon_fence"
    assert tokens[0].content == "foo\n"
    assert tokens[0].markup == ":::"

    tokens = md.parse("```\nfoo\n```\n")
    assert len(tokens) == 1
    assert tokens[0].type == "fence"
    assert tokens[0].content == "foo\n"
    assert tokens[0].markup == "```"


def test_make_fence_at():
    md = MarkdownIt()
    md.block.ruler.at(
        "fence",
        make_fence_rule(
            markers=(":",),
            token_type="colon_fence",
            disallow_marker_in_info=(),
        ),
    )

    tokens = md.parse(":::\nfoo\n:::\n")
    assert len(tokens) == 1
    assert tokens[0].type == "colon_fence"
    assert tokens[0].content == "foo\n"
    assert tokens[0].markup == ":::"

    tokens = md.parse("```\nfoo\n```\n")
    assert not any(token.type == "fence" for token in tokens)
