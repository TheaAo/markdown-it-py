from markdown_it import MarkdownIt
from markdown_it.rules_block.fence import make_fence_rule


def test_make_fence_after():
	md = MarkdownIt()
	md.block.ruler.after(
		"fence",
		"colon_fence",
		make_fence_rule(markers=(":",), token_type="colon_fence"),
		{"alt": ["paragraph", "reference", "blockquote", "list"]},
	)
	tokens = md.parse(":::python\nprint('hello')\n:::\n")

	assert tokens[0].type == "colon_fence"
	assert tokens[0].content == "print('hello')\n"

	backtick_tokens = md.parse("```python\nprint('hello')\n```\n")

	assert backtick_tokens[0].type == "fence"


def test_make_fence_at():
	md = MarkdownIt()
	md.block.ruler.at(
		"fence",
		make_fence_rule(markers=(":",), token_type="colon_fence"),
	)

	tokens = md.parse(":::\nprint('hello')\n:::\n")

	assert tokens[0].type == "colon_fence"
	assert tokens[0].content == "print('hello')\n"

	backtick_tokens = md.parse("```\nprint('hello')\n```\n")

	assert not any(token.type == "fence" for token in backtick_tokens)