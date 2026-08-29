from __future__ import annotations

import argparse
import ast
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from typing import Literal, Sequence

try:
    from scripts.collect_error_rates import (
        _ensure_pytest_available,
        _split_test_file,
        ErrorRateReport,
        TestBlock,
        TestCaseResult,
        collect_error_rates,
    )
except ModuleNotFoundError:  # pragma: no cover - used when run as a script
    from collect_error_rates import (  # type: ignore[no-redef]
        _ensure_pytest_available,
        _split_test_file,
        ErrorRateReport,
        TestBlock,
        TestCaseResult,
        collect_error_rates,
    )


OracleClassification = Literal[
    "invalid", "non_trivial", "trivial", "assertionless", "uncertain"
]
EvidenceClassification = Literal["non_trivial", "trivial", "uncertain"]
EXPECTED_TEST_FUNCTIONS = (
    "test_file",
    "test_spec",
    "test_core_after",
    "test_parse_fail",
    "test_non_utf8",
)


@dataclass(frozen=True)
class AssertionEvidence:
    line: int
    oracle_type: str
    classification: EvidenceClassification
    reason: str


@dataclass(frozen=True)
class AssertionTestResult:
    source_test: str
    generated_nodeids: list[str]
    generated_test_count: int
    classification: OracleClassification
    assertion_count: int
    non_trivial_assertion_count: int
    evidence: list[AssertionEvidence]


@dataclass(frozen=True)
class AssertionScoreReport:
    test_path: str
    total_source_tests: int
    invalid_test_count: int
    eligible_test_count: int
    non_trivial_test_count: int
    trivial_test_count: int
    assertionless_test_count: int
    uncertain_test_count: int
    assertion_score: float | None
    test_cases: list[AssertionTestResult]


@dataclass(frozen=True)
class FunctionSummary:
    parameter_dependencies: frozenset[int]
    returns_sut_value: bool


def _call_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _root_name(node: ast.expr) -> str | None:
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _assigned_names(target: ast.expr) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        names: set[str] = set()
        for element in target.elts:
            names.update(_assigned_names(element))
        return names
    return set()


def _sut_aliases(trees: list[ast.Module]) -> set[str]:
    aliases: set[str] = set()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for imported in node.names:
                    if imported.name == "markdown_it" or imported.name.startswith(
                        "markdown_it."
                    ):
                        aliases.add(
                            imported.asname or imported.name.split(".", 1)[0]
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "markdown_it" or node.module.startswith(
                    "markdown_it."
                ):
                    aliases.update(
                        imported.asname or imported.name for imported in node.names
                    )
    return aliases


def _contains_name(node: ast.AST, names: set[str]) -> bool:
    return any(
        isinstance(child, ast.Name) and child.id in names
        for child in ast.walk(node)
    )


def _function_summaries(
    trees: list[ast.Module], sut_aliases: set[str]
) -> dict[str, FunctionSummary]:
    summaries: dict[str, FunctionSummary] = {}
    for tree in trees:
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            parameters = [
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            ]
            parameter_names = {parameter.arg for parameter in parameters}
            dependent: set[int] = set()
            returns_sut_value = False
            for child in ast.walk(node):
                if not isinstance(child, ast.Return) or child.value is None:
                    continue
                for index, parameter in enumerate(parameters):
                    if _contains_name(child.value, {parameter.arg}):
                        dependent.add(index)
                for call in (
                    item for item in ast.walk(child.value) if isinstance(item, ast.Call)
                ):
                    root = _root_name(call.func)
                    if root in sut_aliases:
                        returns_sut_value = True
            if parameter_names or returns_sut_value:
                summaries[node.name] = FunctionSummary(
                    parameter_dependencies=frozenset(dependent),
                    returns_sut_value=returns_sut_value,
                )
    return summaries


class TestAnalyzer:
    def __init__(
        self,
        sut_aliases: set[str],
        function_summaries: dict[str, FunctionSummary],
        line_offset: int,
    ) -> None:
        self.sut_aliases = sut_aliases
        self.function_summaries = function_summaries
        self.line_offset = line_offset
        self.tainted_names: set[str] = set()
        self.capture_names: set[str] = set()
        self.sut_executed = False
        self.evidence: list[AssertionEvidence] = []

    def _line(self, node: ast.AST) -> int:
        return getattr(node, "lineno", 1) + self.line_offset

    def _call_targets_sut(self, call: ast.Call) -> bool:
        root = _root_name(call.func)
        if root in self.sut_aliases or root in self.tainted_names:
            return True
        if isinstance(call.func, ast.Attribute) and self._is_tainted(call.func.value):
            return True
        summary = self.function_summaries.get(_call_name(call.func))
        return bool(summary and summary.returns_sut_value)

    def _is_tainted(self, node: ast.AST | None) -> bool:
        if node is None:
            return False
        if isinstance(node, ast.Name):
            return node.id in self.tainted_names
        if isinstance(node, ast.Call):
            if self._call_targets_sut(node):
                return True
            name = _call_name(node.func)
            if name.endswith(("capsys.readouterr", "capfd.readouterr")):
                return self.sut_executed
            root = _root_name(node.func)
            if root in self.capture_names and name.endswith(".getvalue"):
                return self.sut_executed
            summary = self.function_summaries.get(name)
            if summary:
                if summary.returns_sut_value:
                    return True
                for index in summary.parameter_dependencies:
                    if index < len(node.args) and self._is_tainted(node.args[index]):
                        return True
            return any(self._is_tainted(argument) for argument in node.args) or any(
                self._is_tainted(keyword.value) for keyword in node.keywords
            )
        return any(self._is_tainted(child) for child in ast.iter_child_nodes(node))

    def _contains_sut_call(self, node: ast.AST) -> bool:
        return any(
            self._call_targets_sut(child)
            for child in ast.walk(node)
            if isinstance(child, ast.Call)
        )

    def _is_trivial_assertion(self, expression: ast.expr) -> str | None:
        if isinstance(expression, ast.Constant):
            return "constant assertion"
        if isinstance(expression, ast.Call):
            name = _call_name(expression.func)
            if name == "isinstance":
                return "generic type check"
            if name.endswith("pytest.raises") or name == "pytest.raises":
                return "pytest.raises was not used as a context manager"
        if isinstance(expression, ast.Compare) and len(expression.ops) == 1:
            left = expression.left
            right = expression.comparators[0]
            if ast.dump(left) == ast.dump(right):
                return "self-comparison"
            if isinstance(expression.ops[0], (ast.Is, ast.IsNot)) and (
                isinstance(left, ast.Constant)
                and left.value is None
                or isinstance(right, ast.Constant)
                and right.value is None
            ):
                return "generic None check"
        return None

    def _record_assertion(self, node: ast.Assert) -> None:
        trivial_reason = self._is_trivial_assertion(node.test)
        if trivial_reason:
            classification: EvidenceClassification = "trivial"
            reason = trivial_reason
        elif self._is_tainted(node.test):
            classification = "non_trivial"
            reason = "asserted value has a backward dependency on markdown_it"
        elif self.sut_executed:
            classification = "uncertain"
            reason = (
                "SUT was executed, but data dependency to this assertion is unclear"
            )
        else:
            classification = "trivial"
            reason = "assertion has no detected dependency on markdown_it"
        self.evidence.append(
            AssertionEvidence(
                line=self._line(node),
                oracle_type="assert",
                classification=classification,
                reason=reason,
            )
        )

    def _is_exception_oracle(self, node: ast.With | ast.AsyncWith) -> bool:
        for item in node.items:
            if not isinstance(item.context_expr, ast.Call):
                continue
            name = _call_name(item.context_expr.func)
            if name.endswith(("pytest.raises", "pytest.warns")) or name in {
                "pytest.raises",
                "pytest.warns",
            }:
                return True
        return False

    def _record_exception_oracle(self, node: ast.With | ast.AsyncWith) -> None:
        body_has_sut_call = any(
            self._contains_sut_call(statement) for statement in node.body
        )
        classification: EvidenceClassification
        if body_has_sut_call:
            classification = "non_trivial"
            reason = (
                "expected exception or warning is produced by markdown_it execution"
            )
        else:
            classification = "uncertain"
            reason = "exception oracle has no statically resolved markdown_it call"
        self.evidence.append(
            AssertionEvidence(
                line=self._line(node),
                oracle_type="pytest_context",
                classification=classification,
                reason=reason,
            )
        )
        if body_has_sut_call:
            for item in node.items:
                if item.optional_vars:
                    self.tainted_names.update(_assigned_names(item.optional_vars))

    def _is_assertion_method(self, call: ast.Call) -> bool:
        if not isinstance(call.func, ast.Attribute):
            return False
        return call.func.attr.startswith("assert") and call.func.attr not in {
            "assertion_score"
        }

    def _record_assertion_method(self, call: ast.Call) -> None:
        receiver_tainted = (
            isinstance(call.func, ast.Attribute) and self._is_tainted(call.func.value)
        )
        arguments_tainted = any(self._is_tainted(argument) for argument in call.args)
        if receiver_tainted or arguments_tainted:
            classification: EvidenceClassification = "non_trivial"
            reason = "assertion method checks a value derived from markdown_it"
        elif (
            self.sut_executed
            and isinstance(call.func, ast.Attribute)
            and call.func.attr.startswith(("assert_called", "assert_awaited"))
        ):
            classification = "non_trivial"
            reason = "mock interaction assertion follows markdown_it execution"
        else:
            classification = "uncertain"
            reason = "assertion method dependency on markdown_it is unclear"
        self.evidence.append(
            AssertionEvidence(
                line=self._line(call),
                oracle_type="assertion_method",
                classification=classification,
                reason=reason,
            )
        )

    def _process_statement(
        self, statement: ast.stmt, control_tainted: bool = False
    ) -> None:
        if isinstance(statement, ast.Assert):
            self._record_assertion(statement)
            return
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            value = statement.value
            targets: list[ast.expr]
            if isinstance(statement, ast.Assign):
                targets = statement.targets
            else:
                targets = [statement.target]
            if self._contains_sut_call(value):
                self.sut_executed = True
            if control_tainted or self._is_tainted(value):
                for target in targets:
                    self.tainted_names.update(_assigned_names(target))
            return
        if isinstance(statement, (ast.With, ast.AsyncWith)):
            if self._is_exception_oracle(statement):
                self._record_exception_oracle(statement)
            for item in statement.items:
                if (
                    not isinstance(item.context_expr, ast.Call)
                    or not item.optional_vars
                ):
                    continue
                name = _call_name(item.context_expr.func)
                if name.endswith(("redirect_stdout", "redirect_stderr")):
                    self.capture_names.update(_assigned_names(item.optional_vars))
            for child in statement.body:
                self._process_statement(child, control_tainted)
            return
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            call = statement.value
            if self._is_assertion_method(call):
                self._record_assertion_method(call)
            if self._call_targets_sut(call):
                self.sut_executed = True
            return
        if isinstance(statement, (ast.If, ast.For, ast.AsyncFor, ast.While)):
            branch_tainted = control_tainted
            if isinstance(statement, (ast.If, ast.While)):
                branch_tainted = branch_tainted or self._is_tainted(statement.test)
            for child in [*statement.body, *statement.orelse]:
                self._process_statement(child, branch_tainted)
            return
        if isinstance(statement, ast.Try):
            for child in [*statement.body, *statement.orelse, *statement.finalbody]:
                self._process_statement(child, control_tainted)
            for handler in statement.handlers:
                for child in handler.body:
                    self._process_statement(child, control_tainted)

    def analyze(
        self, function: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> list[AssertionEvidence]:
        for statement in function.body:
            self._process_statement(statement)
        return self.evidence


def _parse_module(source: str, filename: str) -> ast.Module | None:
    try:
        return ast.parse(source, filename=filename)
    except SyntaxError:
        return None


def _analyze_block(
    block: TestBlock,
    support_tree: ast.Module | None,
    filename: str,
) -> list[AssertionEvidence]:
    block_tree = _parse_module(block.source, filename)
    if block_tree is None:
        return []
    trees = [tree for tree in (support_tree, block_tree) if tree is not None]
    aliases = _sut_aliases(trees)
    summaries = _function_summaries(trees, aliases)
    function = next(
        (
            node
            for node in block_tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == block.name
        ),
        None,
    )
    if function is None:
        return []
    analyzer = TestAnalyzer(
        sut_aliases=aliases,
        function_summaries=summaries,
        line_offset=block.start_line - 1,
    )
    return analyzer.analyze(function)


def _source_classification(
    evidence: list[AssertionEvidence],
) -> OracleClassification:
    if any(item.classification == "non_trivial" for item in evidence):
        return "non_trivial"
    if any(item.classification == "uncertain" for item in evidence):
        return "uncertain"
    if evidence:
        return "trivial"
    return "assertionless"


def _report_from_results(
    test_path: Path,
    results: list[TestCaseResult],
    expected_tests: Sequence[str] | None = None,
) -> AssertionScoreReport:
    support_source, blocks = _split_test_file(test_path)
    support_tree = _parse_module(support_source, str(test_path))
    evidence_by_source = {
        block.name: _analyze_block(block, support_tree, str(test_path))
        for block in blocks
    }
    results_by_source: dict[str, list[TestCaseResult]] = {}
    for result in results:
        results_by_source.setdefault(result.source_test, []).append(result)
    if expected_tests is None:
        source_order = [block.name for block in blocks]
        source_order.extend(
            source_test
            for source_test in results_by_source
            if source_test not in evidence_by_source
        )
    else:
        source_order = list(expected_tests)

    test_cases: list[AssertionTestResult] = []
    for source_test in source_order:
        source_results = results_by_source.get(source_test)
        is_invalid = not source_results or any(
            result.classification != "valid" for result in source_results
        )
        evidence = [] if is_invalid else evidence_by_source.get(source_test, [])
        classification: OracleClassification = (
            "invalid" if is_invalid else _source_classification(evidence)
        )
        test_cases.append(
            AssertionTestResult(
                source_test=source_test,
                generated_nodeids=[
                    result.nodeid for result in source_results or []
                ],
                generated_test_count=len(source_results or []),
                classification=classification,
                assertion_count=len(evidence),
                non_trivial_assertion_count=sum(
                    item.classification == "non_trivial" for item in evidence
                ),
                evidence=evidence,
            )
        )
    counts = {
        classification: sum(
            item.classification == classification for item in test_cases
        )
        for classification in (
            "invalid",
            "non_trivial",
            "trivial",
            "assertionless",
            "uncertain",
        )
    }
    total = len(test_cases)
    eligible = total - counts["invalid"]
    return AssertionScoreReport(
        test_path=str(test_path),
        total_source_tests=total,
        invalid_test_count=counts["invalid"],
        eligible_test_count=eligible,
        non_trivial_test_count=counts["non_trivial"],
        trivial_test_count=counts["trivial"],
        assertionless_test_count=counts["assertionless"],
        uncertain_test_count=counts["uncertain"],
        assertion_score=(
            counts["non_trivial"] / eligible if eligible else None
        ),
        test_cases=test_cases,
    )


def collect_assertion_score(
    test_path: Path,
    repo_root: Path,
    python_executable: str,
    timeout: float,
    error_report: ErrorRateReport | None = None,
) -> AssertionScoreReport:
    test_path = test_path.resolve()
    if error_report is None:
        error_report = collect_error_rates(
            test_path=test_path,
            repo_root=repo_root,
            python_executable=python_executable,
            timeout=timeout,
        )
    return _report_from_results(
        test_path,
        error_report.case_level.test_cases,
        expected_tests=EXPECTED_TEST_FUNCTIONS,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect a conservative non-trivial assertion score."
    )
    parser.add_argument("test_path", type=Path, help="Participant pytest file.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)

    try:
        _ensure_pytest_available(args.python, args.repo_root.resolve())
        report = collect_assertion_score(
            test_path=args.test_path,
            repo_root=args.repo_root,
            python_executable=args.python,
            timeout=args.timeout,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
