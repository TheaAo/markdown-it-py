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

	colon_tokens = md.parse(":::\ncolon content\n:::\n")
	assert colon_tokens[0].type == "colon_fence"
	assert colon_tokens[0].content == "colon content\n"

	backtick_tokens = md.parse("```\nbacktick content\n```\n")
	assert backtick_tokens[0].type == "fence"
	assert backtick_tokens[0].content == "backtick content\n"


def test_make_fence_at():
	md = MarkdownIt()
	colon_rule = make_fence_rule(
		markers=(":",),
		token_type="colon_fence",
		disallow_marker_in_info=(),
	)
	md.block.ruler.at("fence", colon_rule)

	colon_tokens = md.parse(":::\ncolon content\n:::\n")
	assert colon_tokens[0].type == "colon_fence"
	assert colon_tokens[0].content == "colon content\n"

	backtick_tokens = md.parse("```\nbacktick content\n```\n")
	assert not any(token.type == "fence" for token in backtick_tokens)