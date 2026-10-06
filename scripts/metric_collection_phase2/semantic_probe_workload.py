"""Researcher-controlled semantic witnesses; never part of participant scores."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
import importlib
import io
import json
import logging
from pathlib import Path
import re
import signal
import sys
from typing import Any

# A disposable pristine/patched SUT takes precedence over installed editable copies.
sys.path.insert(0, str(Path.cwd()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materials", type=Path, required=True)
    args = parser.parse_args()
    import markdown_it
    from markdown_it import MarkdownIt
    from markdown_it.cli import parse
    from markdown_it.common import utils
    from markdown_it.ruler import Ruler
    from markdown_it.rules_block.state_block import StateBlock
    from markdown_it.rules_block.table import escapedSplit
    from markdown_it.rules_inline.state_inline import StateInline

    assert Path(markdown_it.__file__).is_relative_to(Path.cwd())
    observations: list[dict[str, Any]] = []

    def timeout_handler(signum: int, frame: Any) -> None:
        raise TimeoutError("semantic witness exceeded two seconds")

    signal.signal(signal.SIGALRM, timeout_handler)

    def observe(name: str, function: Callable[..., Any], *values: Any) -> None:
        signal.setitimer(signal.ITIMER_REAL, 2)
        try:
            value = function(*values)
        except (Exception, SystemExit) as exc:  # noqa: BLE001 - exception type/message are observable probe outcomes
            value = {"exception": type(exc).__name__, "message": str(exc)}
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        observations.append({"name": name, "value": value})

    md = MarkdownIt("commonmark")

    def token_snapshot(src: str) -> list[Any]:
        return [token.as_dict() for token in md.parse(src)]

    def preset_render(preset: str, src: str) -> Any:
        return MarkdownIt(preset).render(src)

    cases = json.loads((args.materials / "commonmark.json").read_text())
    for index, case in enumerate(cases):
        src = case["markdown"]
        observe(f"commonmark_html_{index}", md.render, src)
        observe(f"commonmark_tokens_{index}", token_snapshot, src)
    for preset in ("commonmark", "default", "zero", "gfm-like", "gfm-like2"):
        for index, src in enumerate(
            (
                "x",
                "~~x~~",
                "www.example.com",
                "a|b\n-|-\nx|y\n",
                "- [x] task\n",
                "> [!NOTE]\n> x\n",
            )
        ):
            observe(f"preset_{preset}_{index}", preset_render, preset, src)
    for index, src in enumerate(("x", "\tfoo\n", "x\n", "", "\n\nx\n")):

        def block_fields(src: str = src) -> dict[str, Any]:
            state = StateBlock(src, md, {}, [])
            return {
                name: getattr(state, name)
                for name in (
                    "bMarks",
                    "eMarks",
                    "tShift",
                    "sCount",
                    "bsCount",
                    "lineMax",
                )
            }

        observe(f"public_block_state_{index}", block_fields)

        def inline_fields(src: str = src) -> dict[str, Any]:
            state = StateInline(src, md, {}, [])
            return {
                name: getattr(state, name)
                for name in (
                    "pos",
                    "posMax",
                    "level",
                    "pending",
                    "pendingLevel",
                    "backticksScanned",
                    "linkLevel",
                )
            }

        observe(f"public_inline_state_{index}", inline_fields)
    for index, src in enumerate(("", "a|b", r"a\|b", "a|", "|", r"\\|", "a||b")):
        observe(f"escaped_split_{index}", escapedSplit, src)
    for code in (
        0,
        1,
        8,
        9,
        10,
        13,
        31,
        32,
        65,
        127,
        128,
        0xD800,
        0xDFFF,
        0xFDD0,
        0xFDEF,
        0xFDF0,
        0xFFFE,
        0xFFFF,
        0x10000,
        0x10FFFF,
        0x110000,
    ):
        observe(f"entity_code_{code}", utils.isValidEntityCode, code)
    for src in (
        "&AElig;",
        "&#10;",
        "&#0010;",
        "&#x41;",
        "&#x10FFFF;",
        "&invalid;",
        "&#xFDD0;",
        "&#65535;",
    ):
        observe(f"unescape_{src}", utils.unescapeAll, src)
    for operation in ("after", "before", "at"):

        def missing_anchor(operation: str = operation) -> Any:
            ruler: Ruler[Any] = Ruler()
            ruler.push("base", lambda *_: None)
            if operation == "at":
                return ruler.at("missing", lambda *_: None)
            return getattr(ruler, operation)("missing", "new", lambda *_: None)

        observe(f"missing_rule_{operation}", missing_anchor)
    for preset in ("commonmark", "default", "zero", "gfm-like", "gfm-like2"):
        observe(
            f"public_preset_{preset}",
            getattr(markdown_it.presets, preset.replace("-", "_")).make,
        )
    observe("default_softbreak", MarkdownIt().render, "a\nb\n")
    observe("public_enable_missing", md.enable, "missing")
    observe("public_enable_ignore", md.enable, "paragraph", True)

    def title_fields(src: str, maximum: int) -> dict[str, Any]:
        state = md.helpers.parseLinkTitle(src, 0, maximum)
        return {
            name: getattr(state, name)
            for name in ("ok", "pos", "str", "marker", "can_continue")
        }

    for src in ('"abc\\x', "(x(y)", '"x"'):
        for maximum in range(1, len(src) + 1):
            observe(f"title_{src}_{maximum}", title_fields, src, maximum)

    def empty_lines(src: str) -> int:
        state = StateBlock(src, md, {}, [])
        return state.skipEmptyLines(0)

    for src in ("", "\n", "\n\n", "x\n"):
        observe(f"skip_empty_{src}", empty_lines, src)

    def reference_environment() -> dict[str, Any]:
        env: dict[str, Any] = {}
        md.parse('[x]: /a "a"\n[x]: /b "b"\n\n[x]\n', env)
        return env

    observe("public_duplicate_reference_env", reference_environment)

    def highlight_override() -> Any:
        custom = MarkdownIt("commonmark", {"highlight": lambda *_: "<pre>custom</pre>"})
        return custom.render("```x\na\n```\n")

    observe("highlight_pre_override", highlight_override)

    def debug_logs() -> list[str]:
        records: list[str] = []

        class Capture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                try:
                    message = record.getMessage()
                except (TypeError, ValueError) as exc:
                    message = f"format_error:{type(exc).__name__}:{exc}"
                records.append(re.sub(r"0x[0-9a-fA-F]+", "0xADDRESS", message))

        logger = logging.getLogger("markdown_it")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        handler = Capture()
        logger.addHandler(handler)
        try:
            MarkdownIt().render(
                "# h\n\n- item\n\n> quote\n\n```x\na\n```\n\n    code\n\n---\n\n<div>x</div>\n\nx\n===\n\n[x]: /url\n"
            )
        finally:
            logger.removeHandler(handler)
            logger.setLevel(logging.WARNING)
        return records

    observe("enabled_debug_logging", debug_logs)

    def ruler_enable(name: str, ignore: bool) -> dict[str, Any]:
        ruler: Ruler[Any] = Ruler()
        ruler.push("base", lambda *_: None)
        ruler.disable("base")
        result = ruler.enable(name, ignore)
        return {"result": result, "active": ruler.get_active_rules()}

    observe("ruler_enable_missing_false", ruler_enable, "missing", False)
    observe("ruler_enable_base_ignore_true", ruler_enable, "base", True)

    def exact_fence() -> list[Any]:
        make_fence_rule = importlib.import_module(
            "markdown_it.rules_block.fence"
        ).make_fence_rule

        custom = MarkdownIt("commonmark")
        custom.block.ruler.at("fence", make_fence_rule(exact_match=True))
        return [token.as_dict() for token in custom.parse("```\na\n```\nb\n")]

    observe("configured_exact_fence", exact_fence)

    def public_inline_push() -> dict[str, Any]:
        state = StateInline("x", MarkdownIt(), {}, [])
        state.push("open", "x", 1)
        token = state.push("close", "x", -1)
        return {"level": state.level, "token": token.as_dict()}

    observe("public_inline_push_close", public_inline_push)

    def public_html_link_level() -> int:
        from markdown_it.rules_inline.html_inline import html_inline

        state = StateInline("<a>", MarkdownIt(), {}, [])
        html_inline(state, False)
        return state.linkLevel

    observe("public_html_link_level", public_html_link_level)

    def adjacent_text() -> list[Any]:
        from markdown_it.rules_inline.fragments_join import fragments_join
        from markdown_it.token import Token

        state = StateInline("ab", MarkdownIt(), {}, [])
        state.tokens = [
            Token("text", "", 0, content="a"),
            Token("text", "", 0, content="b"),
        ]
        fragments_join(state)
        return [token.as_dict() for token in state.tokens]

    observe("public_fragments_join", adjacent_text)

    def block_extension_state(src: str) -> list[Any]:
        custom = MarkdownIt("commonmark")
        captures: list[Any] = []

        def capture(state: StateBlock, start: int, end: int, silent: bool) -> bool:
            captures.append(
                {
                    "parent": state.parentType,
                    "sCount": state.sCount.copy(),
                    "bsCount": state.bsCount.copy(),
                }
            )
            return False

        custom.block.ruler.before(
            "paragraph",
            "capture",
            capture,
            {"alt": ["paragraph", "reference", "blockquote"]},
        )
        custom.parse(src)
        return captures

    for index, src in enumerate(
        (
            "> a\n continuation\n",
            "> a\n> b\n",
            "> a\n>\nx\n",
            "> a\n>\t b\n",
            ">\t a\n",
            "[a]: /url\n continuation\n",
            "one\n\ntwo\n",
        )
    ):
        observe(f"block_extension_state_{index}", block_extension_state, src)
        observe(f"block_boundary_html_{index}", MarkdownIt().render, src)
    for src in (
        "<a@b.com>X",
        "[x]: /url 'bad' junk\n",
        "[x]: /url 'bad' \t junk\n",
        "[x\\a]: /url\nnext\n",
        "a\n# h\n---\n",
    ):
        observe(f"boundary_render_{src}", MarkdownIt().render, src)
    observe("public_rule_configuration", MarkdownIt("commonmark").get_active_rules)

    def paragraph_parent() -> str:
        from markdown_it.rules_block.paragraph import paragraph

        state = StateBlock("one\n", MarkdownIt(), {}, [])
        paragraph(state, 0, state.lineMax, False)
        return state.parentType

    observe("public_paragraph_parent", paragraph_parent)

    def next_line_state(indented: bool) -> dict[str, Any]:
        from markdown_it.rules_block.reference import getNextLine

        custom = MarkdownIt()
        captures: list[Any] = []

        def capture(state: StateBlock, start: int, end: int, silent: bool) -> bool:
            captures.append(state.parentType)
            return False

        custom.block.ruler.push("capture", capture, {"alt": ["reference"]})
        state = StateBlock(
            "one\n" + ("    two\n" if indented else "two\n"), custom, {}, []
        )
        result = getNextLine(state, 1)
        return {"result": result, "parent": state.parentType, "callbacks": captures}

    observe("public_reference_next_line", next_line_state, False)
    observe("public_reference_indented_continuation", next_line_state, True)
    observe(
        "reference_title_rollback",
        MarkdownIt().render,
        "[x]: /url  \n 'bad' junk\n\n[x]\n",
    )

    def custom_attribute_renderer() -> Any:
        from markdown_it.renderer import RendererHTML
        from markdown_it.token import Token

        class Custom(RendererHTML):
            @staticmethod
            def renderAttrs(token: Token) -> str:
                return f' data-type="{token.type!r}"' + RendererHTML.renderAttrs(token)

        return MarkdownIt("commonmark", renderer_cls=Custom).render("```x\na\n```\n")

    observe("supported_custom_renderer_attrs", custom_attribute_renderer)
    observe("public_md_utils", lambda: md.utils.__name__)
    for path in (
        args.materials / "spec.md",
        args.materials / "missing-semantic-probe.md",
    ):

        def cli(path: Path = path) -> dict[str, Any]:
            out, err = io.StringIO(), io.StringIO()
            code: int | str | None = 0
            with redirect_stdout(out), redirect_stderr(err):
                try:
                    parse.convert_file(str(path))
                except SystemExit as exc:
                    code = exc.code
            return {"stdout": out.getvalue(), "stderr": err.getvalue(), "exit": code}

        observe(f"cli_{path.name}", cli)
    print(
        json.dumps(
            observations,
            ensure_ascii=True,
            sort_keys=True,
            default=lambda obj: {"object_type": type(obj).__name__},
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
