from __future__ import annotations

import argparse
import ast
from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Literal, Sequence


RULE_VERSION = "1.0.0"
FORMAL_SMELLS = (
    "assertion_roulette",
    "magic_number_test",
    "unknown_test",
    "conditional_test_logic",
    "eager_test",
    "duplicate_assert",
    "exception_handling",
)
PRODUCTION_RESULT_METHODS = {"parse", "parseInline", "render", "renderInline"}
CONVENTIONAL_NUMBERS = {-1, 0, 1}
Decision = Literal["confirmed", "not_detected", "uncertain"]


@dataclass(frozen=True)
class SmellDecision:
    smell: str
    decision: Decision
    lines: list[int]
    reason: str


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _is_markdown_it_constructor(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and _call_name(node.func).endswith("MarkdownIt")


def _numeric_value(node: ast.AST) -> int | float | None:
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
        and not isinstance(node.operand.value, bool)
    ):
        return -node.operand.value
    return None


def _contains_magic_number(assertion: ast.Assert) -> bool:
    ignored_nodes: set[int] = set()
    for node in ast.walk(assertion.test):
        if isinstance(node, ast.Subscript):
            ignored_nodes.update(id(child) for child in ast.walk(node.slice))
    for node in ast.walk(assertion.test):
        if id(node) in ignored_nodes:
            continue
        value = _numeric_value(node)
        if value is not None and value not in CONVENTIONAL_NUMBERS:
            return True
    return False


class _DirectNodeVisitor(ast.NodeVisitor):
    """Walk one function body without entering nested definitions."""

    def __init__(self) -> None:
        self.nodes: list[ast.AST] = []

    def visit(self, node: ast.AST) -> None:
        self.nodes.append(node)
        super().visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return


def _direct_nodes(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    visitor = _DirectNodeVisitor()
    for statement in function.body:
        visitor.visit(statement)
    return visitor.nodes


def _local_functions(
    tree: ast.Module, test: ast.FunctionDef | ast.AsyncFunctionDef
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("test_")
    }
    for node in ast.walk(test):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node is not test
        ):
            functions[node.name] = node
    return functions


def _reachable_scopes(
    tree: ast.Module, test: ast.FunctionDef | ast.AsyncFunctionDef
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    helpers = _local_functions(tree, test)
    scopes: list[ast.FunctionDef | ast.AsyncFunctionDef] = [test]
    seen = {test.name}
    for scope in scopes:
        called = {
            _call_name(node.func).rsplit(".", 1)[-1]
            for node in _direct_nodes(scope)
            if isinstance(node, ast.Call)
        }
        for name in sorted(called):
            helper = helpers.get(name)
            if helper is not None and name not in seen:
                seen.add(name)
                scopes.append(helper)
    return scopes


def _oracle_lines(
    scopes: Sequence[ast.FunctionDef | ast.AsyncFunctionDef],
) -> list[int]:
    lines: set[int] = set()
    for scope in scopes:
        for node in _direct_nodes(scope):
            if isinstance(node, ast.Assert):
                lines.add(node.lineno)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    context = item.context_expr
                    if isinstance(context, ast.Call) and _call_name(context.func) in {
                        "pytest.raises",
                        "pytest.warns",
                    }:
                        lines.add(node.lineno)
            elif isinstance(node, ast.Call):
                name = _call_name(node.func)
                final_name = name.rsplit(".", 1)[-1]
                if (
                    name == "pytest.fail"
                    or final_name.startswith("assert")
                    or final_name in {"check", "check_file", "matches"}
                ):
                    lines.add(node.lineno)
    return sorted(lines)


def _production_method(call: ast.Call, parser_names: set[str]) -> str | None:
    function = call.func
    if not isinstance(function, ast.Attribute):
        return None
    if function.attr not in PRODUCTION_RESULT_METHODS:
        return None
    receiver = function.value
    if isinstance(receiver, ast.Name) and receiver.id in parser_names:
        return function.attr
    if _is_markdown_it_constructor(receiver):
        return function.attr
    return None


def _methods_in_expression(
    expression: ast.AST,
    parser_names: set[str],
    result_methods: dict[str, set[str]],
) -> set[str]:
    methods: set[str] = set()
    for node in ast.walk(expression):
        if isinstance(node, ast.Name):
            methods.update(result_methods.get(node.id, set()))
        elif isinstance(node, ast.Call):
            method = _production_method(node, parser_names)
            if method is not None:
                methods.add(method)
    return methods


def _oracle_method_edges(
    scopes: Sequence[ast.FunctionDef | ast.AsyncFunctionDef],
) -> list[tuple[int, set[str]]]:
    edges: list[tuple[int, set[str]]] = []
    for scope in scopes:
        nodes = _direct_nodes(scope)
        parser_names: set[str] = set()
        result_methods: dict[str, set[str]] = {}
        for node in nodes:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            if _is_markdown_it_constructor(value):
                parser_names.update(names)
            methods = _methods_in_expression(value, parser_names, result_methods)
            for name in names:
                if methods:
                    result_methods[name] = methods

        for node in nodes:
            if isinstance(node, ast.Assert):
                methods = _methods_in_expression(
                    node.test, parser_names, result_methods
                )
                if methods:
                    edges.append((node.lineno, methods))
    return edges


def _has_two_independent_oracles(edges: Sequence[tuple[int, set[str]]]) -> bool:
    for first_index, (_first_line, first_methods) in enumerate(edges):
        for _second_line, second_methods in edges[first_index + 1 :]:
            if any(
                first != second
                for first in first_methods
                for second in second_methods
            ):
                return True
    return False


def analyze_function(
    tree: ast.Module, function: ast.FunctionDef | ast.AsyncFunctionDef
) -> list[SmellDecision]:
    structural_nodes = list(ast.walk(function))
    assertions = [node for node in structural_nodes if isinstance(node, ast.Assert)]
    reachable_scopes = _reachable_scopes(tree, function)
    oracle_lines = _oracle_lines(reachable_scopes)
    eager_edges = _oracle_method_edges(reachable_scopes)

    bare_assertions = [node for node in assertions if node.msg is None]
    magic_assertions = [node for node in assertions if _contains_magic_number(node)]
    conditional_nodes = [
        node
        for node in structural_nodes
        if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Match))
    ]
    duplicate_counts = Counter(
        ast.dump(assertion.test, include_attributes=False) for assertion in assertions
    )
    duplicate_structures = {
        structure for structure, count in duplicate_counts.items() if count >= 2
    }
    duplicate_assertions = [
        assertion
        for assertion in assertions
        if ast.dump(assertion.test, include_attributes=False) in duplicate_structures
    ]
    exception_nodes = [
        node
        for node in structural_nodes
        if isinstance(node, ast.Try) and node.handlers
    ]

    occurrences: dict[str, tuple[bool, list[int], str, str]] = {
        "assertion_roulette": (
            len(bare_assertions) >= 2,
            [node.lineno for node in bare_assertions],
            "at least two assert statements have no explicit message",
            "fewer than two assert statements lack an explicit message",
        ),
        "magic_number_test": (
            bool(magic_assertions),
            [node.lineno for node in magic_assertions],
            "an assertion contains a non-conventional numeric literal",
            "no assertion contains a non-exempt numeric literal",
        ),
        "unknown_test": (
            not oracle_lines,
            [function.lineno] if not oracle_lines else oracle_lines,
            "no supported oracle is reachable from the source test",
            "a supported oracle is reachable from the source test",
        ),
        "conditional_test_logic": (
            bool(conditional_nodes),
            [node.lineno for node in conditional_nodes],
            "statement-level conditional or loop logic is present",
            "no statement-level conditional or loop logic is present",
        ),
        "eager_test": (
            _has_two_independent_oracles(eager_edges),
            [line for line, _methods in eager_edges],
            "distinct markdown_it result methods feed independent oracles",
            "fewer than two distinct production methods feed independent oracles",
        ),
        "duplicate_assert": (
            bool(duplicate_assertions),
            [node.lineno for node in duplicate_assertions],
            "normalized assertion conditions are duplicated",
            "normalized assertion conditions are unique",
        ),
        "exception_handling": (
            bool(exception_nodes),
            [node.lineno for node in exception_nodes],
            "manual try/except handling is present",
            "no manual try/except handling is present",
        ),
    }
    return [
        SmellDecision(
            smell=smell,
            decision="confirmed" if detected else "not_detected",
            lines=sorted(set(lines)),
            reason=positive_reason if detected else negative_reason,
        )
        for smell, (
            detected,
            lines,
            positive_reason,
            negative_reason,
        ) in occurrences.items()
    ]


def analyze_tree(
    tree: ast.Module, target_names: set[str] | None = None
) -> dict[str, list[SmellDecision]]:
    results: dict[str, list[SmellDecision]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        if target_names is not None and node.name not in target_names:
            continue
        results[node.name] = analyze_function(tree, node)
    return results


def analyze_file(
    path: Path, target_names: set[str] | None = None
) -> dict[str, list[SmellDecision]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return analyze_tree(tree, target_names)


def detect_file(path: Path) -> list[dict[str, str]]:
    """Compatibility output used by the frozen pilot evaluator."""
    return [
        {"test_name": test_name, "smell": decision.smell}
        for test_name, decisions in analyze_file(path).items()
        for decision in decisions
        if decision.decision == "confirmed"
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the versioned AST smell rules")
    parser.add_argument("test_file", type=Path)
    parser.add_argument(
        "--detailed", action="store_true", help="Emit all decisions and evidence."
    )
    args = parser.parse_args(argv)
    if args.detailed:
        payload = {
            "rule_version": RULE_VERSION,
            "tests": {
                name: [asdict(decision) for decision in decisions]
                for name, decisions in analyze_file(args.test_file).items()
            },
        }
    else:
        payload = detect_file(args.test_file)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
