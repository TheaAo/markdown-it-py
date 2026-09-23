from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.rules_block.fence import make_fence_rule

def test_make_fence_after():
	md = MarkdownIt()
	colon_rule = make_fence_rule(
		markers=(":",),
		token_type="colon_fence",
	)
	md.block.ruler.after("fence", "colon_fence", colon_rule)

	colon_tokens = md.parse(":::\nfoo\n:::\n")
	assert colon_tokens[0].type == "colon_fence"
	assert colon_tokens[0].content == "foo\n"

	fence_tokens = md.parse("```\nbar\n```\n")
	assert fence_tokens[0].type == "fence"
	assert fence_tokens[0].content == "bar\n"


def test_make_fence_at():
	md = MarkdownIt()
	colon_rule = make_fence_rule(
		markers=(":",),
		token_type="colon_fence",
	)
	md.block.ruler.at("fence", colon_rule)

	colon_tokens = md.parse(":::\nfoo\n:::\n")
	assert colon_tokens[0].type == "colon_fence"
	assert colon_tokens[0].content == "foo\n"

	fence_tokens = md.parse("```\nbar\n```\n")
	assert not any(token.type == "fence" for token in fence_tokens)
	assert md.get_all_rules()["block"].count("fence") == 1