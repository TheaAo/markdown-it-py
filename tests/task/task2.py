from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.rules_block.fence import make_fence_rule

def test_make_fence_rule_callable():
	rule = make_fence_rule()
	assert callable(rule), "make_fence_rule should return a callable rule"

def test_default_fence_exists():
	# the module exposes a default `fence` rule via make_fence_rule()
	from markdown_it.rules_block.fence import fence

	assert callable(fence), "default fence rule should be callable"


def test_make_fence_after():
	md = MarkdownIt()
	colon_rule = make_fence_rule(
		markers=(":" ,),
		token_type="colon_fence",
		disallow_marker_in_info=(),
	)
	# register colon fence after the default fence
	md.block.ruler.after(
		"fence",
		"colon_fence",
		colon_rule,
		{"alt": ["paragraph", "reference", "blockquote", "list"]},
	)

	# colon fence should be parsed
	tokens = md.parse(":::\nfoo\n:::\n")
	assert len(tokens) == 1
	assert tokens[0].type == "colon_fence"
	assert tokens[0].content == "foo\n"

	# default backtick fence should still work
	tokens = md.parse("```\nbar\n```\n")
	assert tokens[0].type == "fence"
	assert tokens[0].content == "bar\n"


def test_make_fence_at():
	md = MarkdownIt()
	colon_rule = make_fence_rule(
		markers=(":" ,),
		token_type="colon_fence",
		disallow_marker_in_info=(),
	)
	# replace the default fence rule with colon-only rule
	md.block.ruler.at("fence", colon_rule)

	# colon fence should be parsed
	tokens = md.parse(":::\nfoo\n:::\n")
	assert len(tokens) == 1
	assert tokens[0].type == "colon_fence"
	assert tokens[0].content == "foo\n"

	# backtick fence should no longer be recognized as `fence`
	tokens = md.parse("```\nbar\n```\n")
	assert not any(t.type == "fence" for t in tokens), "backtick fence should be disabled after replacement"