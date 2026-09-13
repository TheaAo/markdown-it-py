"""Forty-two executable cases for the seven-smell aligned pilot."""

from __future__ import annotations

import pytest

from markdown_it import MarkdownIt


EXPECTED_EMPTY = ""
EXPECTED_HEADING = "<h1>title</h1>\n"
EXPECTED_PARAGRAPH = "<p>text</p>\n"


# Assertion Roulette: multiple bare assertions are positives.
def test_ar_two_bare_positive() -> None:
    assert "a".upper() == "A"
    assert "b".upper() == "B"


def test_ar_three_bare_positive() -> None:
    assert "a".isalpha()
    assert "b".islower()
    assert "C".isupper()


def test_ar_pytest_rewriting_positive() -> None:
    # Pytest rewriting improves diagnostics, but the fixed literature rule remains.
    assert "markdown".startswith("mark")
    assert "markdown".endswith("down")


def test_ar_single_bare_control() -> None:
    assert "markdown".isalpha()


def test_ar_messages_control() -> None:
    assert "a".upper() == "A", "uppercase conversion"
    assert "b".upper() == "B", "second uppercase conversion"


def test_ar_single_message_control() -> None:
    assert MarkdownIt().render("") == EXPECTED_EMPTY, "empty input rendering"


# Magic Number Test: numeric literals in assertion expressions are positives.
def test_magic_number_integer_positive() -> None:
    value = 17
    assert value == 17, "unexpected level"


def test_magic_number_large_integer_positive() -> None:
    value = 42
    assert value < 100, "value should remain below the undocumented limit"


def test_magic_number_tuple_positive() -> None:
    dimensions = (2, 3)
    assert dimensions == (2, 3), "unexpected dimensions"


def test_magic_number_named_constant_control() -> None:
    result = MarkdownIt().render("")
    assert result == EXPECTED_EMPTY, "named expected value"


def test_magic_number_conventional_values_control() -> None:
    values = (-1, 0, 1)
    assert values[0] == -1, "negative sentinel"
    assert values[1] == 0, "zero sentinel"
    assert values[2] == 1, "one sentinel"


@pytest.mark.parametrize("actual, expected", [(17, 17), (42, 42)])
def test_magic_number_parameter_data_control(actual: int, expected: int) -> None:
    assert actual == expected, "parameter data supplies the expected value"


# Unknown Test: positives execute code but contain no supported oracle.
def test_unknown_render_without_oracle_positive() -> None:
    MarkdownIt().render("text")


def test_unknown_assignment_without_oracle_positive() -> None:
    rendered = MarkdownIt().render("text")
    rendered.strip()


def test_unknown_helper_without_oracle_positive() -> None:
    def render_text() -> str:
        return MarkdownIt().render("text")

    render_text()


def test_unknown_direct_oracle_control() -> None:
    rendered = MarkdownIt().render("text")
    assert rendered == EXPECTED_PARAGRAPH, "rendered paragraph"


def test_unknown_pytest_raises_control() -> None:
    with pytest.raises(TypeError):
        MarkdownIt().render(None)  # type: ignore[arg-type]


def test_unknown_local_helper_oracle_control() -> None:
    def verify_rendered() -> None:
        assert MarkdownIt().render("") == EXPECTED_EMPTY

    verify_rendered()


# Conditional Test Logic: statement-level control flow is included.
def test_conditional_if_positive() -> None:
    value = "markdown"
    if value:
        assert value == "markdown", "value should be preserved"


def test_conditional_for_positive() -> None:
    result = ""
    for value in ["markdown"]:
        result = value
    assert result == "markdown", "loop result"


def test_conditional_while_positive() -> None:
    values = ["markdown"]
    while values:
        value = values.pop()
    assert value == "markdown", "loop result"


def test_conditional_match_positive() -> None:
    value = "markdown"
    match value:
        case "markdown":
            result = "matched"
        case _:
            result = "unmatched"
    assert result == "matched", "match result"


def test_conditional_ternary_control() -> None:
    result = "yes" if True else "no"
    assert result == "yes", "ternary expressions are excluded by protocol"


def test_conditional_comprehension_control() -> None:
    result = [value.upper() for value in ["markdown"]]
    assert result == ["MARKDOWN"], "comprehensions are excluded by protocol"


# Eager Test: two distinct production entry points feed independent oracles.
def test_eager_render_and_parse_positive() -> None:
    parser = MarkdownIt()
    rendered = parser.render("text")
    tokens = parser.parse("text")
    assert rendered == EXPECTED_PARAGRAPH, "render output"
    assert tokens[0].type == "paragraph_open", "parse output"


def test_eager_render_and_parse_inline_positive() -> None:
    parser = MarkdownIt()
    rendered = parser.render("text")
    tokens = parser.parseInline("text")
    assert rendered == EXPECTED_PARAGRAPH, "render output"
    assert tokens[0].type == "inline", "inline parse output"


def test_eager_parse_and_render_inline_positive() -> None:
    parser = MarkdownIt()
    blocks = parser.parse("text")
    rendered = parser.renderInline("text")
    assert blocks[0].type == "paragraph_open", "block parse output"
    assert rendered == "text", "inline render output"


def test_eager_same_method_twice_control() -> None:
    parser = MarkdownIt()
    first = parser.render("text")
    second = parser.render("# title")
    assert first == EXPECTED_PARAGRAPH, "first render"
    assert second == EXPECTED_HEADING, "second render"


def test_eager_one_call_multiple_oracles_control() -> None:
    tokens = MarkdownIt().parse("text")
    assert tokens[0].type == "paragraph_open", "opening token"
    assert tokens[-1].type == "paragraph_close", "closing token"


def test_eager_configuration_call_control() -> None:
    parser = MarkdownIt()
    parser.core.ruler.after("normalize", "pilot_noop", lambda state: None)
    rendered = parser.render("text")
    assert rendered == EXPECTED_PARAGRAPH, "only one production result is tested"


# Duplicate Assert: structurally identical assertion conditions are positives.
def test_duplicate_exact_positive() -> None:
    result = "markdown"
    assert result == "markdown", "same check"
    assert result == "markdown", "same check"


def test_duplicate_formatting_positive() -> None:
    result = "markdown"
    assert result.startswith("mark"), "first check"
    assert result.startswith(
        "mark"
    ), "formatting does not change the assertion structure"


def test_duplicate_different_messages_positive() -> None:
    result = "markdown"
    assert result.endswith("down"), "first explanation"
    assert result.endswith("down"), "different explanation"


def test_duplicate_different_expected_control() -> None:
    result = "markdown"
    assert result != "markup", "first condition"
    assert result != "mark", "different expected value"


def test_duplicate_different_operator_control() -> None:
    result = "markdown"
    assert result == "markdown", "equality"
    assert result != "markup", "inequality"


@pytest.mark.parametrize("value", ["markdown", "text"])
def test_duplicate_parameterized_control(value: str) -> None:
    assert value, "one source assertion despite multiple generated instances"


# Exception Handling: manual try/except is positive; framework oracles are not.
def test_exception_manual_flag_positive() -> None:
    caught = False
    try:
        int("not-an-int")
    except ValueError:
        caught = True
    assert caught, "manual exception flag"


def test_exception_manual_fail_positive() -> None:
    try:
        int("not-an-int")
    except ValueError:
        pass
    else:
        pytest.fail("ValueError was not raised")


def test_exception_local_helper_positive() -> None:
    def catches_value_error() -> bool:
        try:
            int("not-an-int")
        except ValueError:
            return True
        return False

    assert catches_value_error(), "helper manually handles the exception"


def test_exception_pytest_raises_control() -> None:
    with pytest.raises(ValueError):
        int("not-an-int")


def test_exception_try_finally_control() -> None:
    resource = []
    try:
        resource.append("used")
    finally:
        resource.clear()
    assert resource == [], "cleanup-only try/finally is excluded"


def test_exception_word_in_string_control() -> None:
    description = "try: and except ValueError are documentation"
    assert description.startswith("try"), "strings are not exception handlers"
