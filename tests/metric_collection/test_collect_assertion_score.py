import json
from pathlib import Path

import pytest

from scripts.collect_assertion_score import (
    _error_results_from_json,
    _report_from_results,
    collect_assertion_score,
)
from scripts.collect_error_rates import TestCaseResult as ErrorTestCaseResult


def _valid(nodeid: str, source_test: str) -> ErrorTestCaseResult:
    return ErrorTestCaseResult(
        nodeid=nodeid,
        source_test=source_test,
        classification="valid",
        returncode=0,
        reason="passed on original SUT",
    )


def test_assertion_score_classifies_fully_valid_generated_items(
    tmp_path: Path,
) -> None:
    test_path = tmp_path / "test_participant.py"
    test_path.write_text(
        """\
import io
from contextlib import redirect_stdout

import pytest
from markdown_it import MarkdownIt

def normalize(value):
    return value.strip()

@pytest.mark.parametrize("source", ["a", "b"])
def test_direct(source):
    rendered = MarkdownIt().render(source)
    assert normalize(rendered) == "<p>expected</p>"

def test_exception(tmp_path):
    from markdown_it.cli import parse
    with pytest.raises(SystemExit) as exc_info:
        parse.main([str(tmp_path / "missing.md")])
    assert exc_info.value.code == 1

def test_output(capsys):
    MarkdownIt().render("text")
    output = capsys.readouterr().out
    assert "plugin called" in output

def test_control_flow():
    matches = True
    rendered = MarkdownIt().render("text")
    if rendered != "<p>expected</p>":
        matches = False
    assert matches is True

def test_redirected_output(tmp_path):
    from markdown_it.cli import parse
    source = tmp_path / "input.md"
    source.write_text("text")
    with redirect_stdout(io.StringIO()) as output:
        parse.main([str(source)])
    assert "expected" in output.getvalue()

def test_trivial():
    value = MarkdownIt().render("text")
    assert value is not None

def test_assertionless():
    MarkdownIt().render("text")

def test_uncertain():
    flag = False
    MarkdownIt().render("text")
    assert flag is True
""",
        encoding="utf-8",
    )
    valid_results = [
        _valid("test_participant.py::test_direct[a]", "test_direct"),
        _valid("test_participant.py::test_direct[b]", "test_direct"),
        _valid("test_participant.py::test_exception", "test_exception"),
        _valid("test_participant.py::test_output", "test_output"),
        _valid("test_participant.py::test_control_flow", "test_control_flow"),
        _valid(
            "test_participant.py::test_redirected_output",
            "test_redirected_output",
        ),
        _valid("test_participant.py::test_trivial", "test_trivial"),
        _valid("test_participant.py::test_assertionless", "test_assertionless"),
        _valid("test_participant.py::test_uncertain", "test_uncertain"),
    ]

    report = _report_from_results(test_path, valid_results)

    assert report.total_source_tests == 8
    assert report.invalid_test_count == 0
    assert report.eligible_test_count == 8
    assert report.non_trivial_test_count == 5
    assert report.trivial_test_count == 1
    assert report.assertionless_test_count == 1
    assert report.uncertain_test_count == 1
    assert report.assertion_score == pytest.approx(5 / 8)
    direct_result = report.test_cases[0]
    assert direct_result.classification == "non_trivial"
    assert direct_result.generated_test_count == 2
    assert direct_result.valid_instance_count == 2
    assert direct_result.total_instance_count == 2
    assert direct_result.validity == "fully_valid"
    exception_result = report.test_cases[1]
    assert exception_result.non_trivial_assertion_count == 2
    assert {item.oracle_type for item in exception_result.evidence} == {
        "assert",
        "pytest_context",
    }


def test_zero_valid_source_is_invalid(tmp_path: Path) -> None:
    test_path = tmp_path / "test_empty.py"
    test_path.write_text("def test_nothing():\n    pass\n", encoding="utf-8")

    report = _report_from_results(test_path, [])

    assert report.total_source_tests == 1
    assert report.invalid_test_count == 1
    assert report.assertion_score is None
    result = report.test_cases[0]
    assert result.generated_nodeids == []
    assert result.valid_instance_count == 0
    assert result.total_instance_count == 0
    assert result.validity == "invalid"
    assert result.classification == "invalid"


def test_partially_valid_parameterized_source_remains_eligible(
    tmp_path: Path,
) -> None:
    test_path = tmp_path / "test_parameterized.py"
    test_path.write_text(
        """\
import pytest
from markdown_it import MarkdownIt

@pytest.mark.parametrize("source", ["a", "b"])
def test_render(source):
    assert MarkdownIt().render(source) == "expected"
""",
        encoding="utf-8",
    )
    results = [
        _valid("test_parameterized.py::test_render[a]", "test_render"),
        ErrorTestCaseResult(
            nodeid="test_parameterized.py::test_render[b]",
            source_test="test_render",
            classification="function_error",
            returncode=1,
            reason="assertion failed",
        ),
    ]

    report = _report_from_results(test_path, results)

    assert report.total_source_tests == 1
    assert report.invalid_test_count == 0
    assert report.eligible_test_count == 1
    assert report.assertion_score == 1.0
    result = report.test_cases[0]
    assert result.classification == "non_trivial"
    assert result.generated_nodeids == [
        "test_parameterized.py::test_render[a]",
        "test_parameterized.py::test_render[b]",
    ]
    assert result.generated_test_count == 2
    assert result.valid_instance_count == 1
    assert result.total_instance_count == 2
    assert result.validity == "partially_valid"


def test_missing_expected_test_is_invalid(tmp_path: Path) -> None:
    test_path = tmp_path / "test_missing.py"
    test_path.write_text(
        "from markdown_it import MarkdownIt\n\n"
        "def test_file():\n"
        "    assert MarkdownIt().render('text')\n",
        encoding="utf-8",
    )

    report = _report_from_results(
        test_path,
        [_valid("test_missing.py::test_file", "test_file")],
        expected_tests=("test_file", "test_spec"),
    )

    assert report.total_source_tests == 2
    assert report.eligible_test_count == 1
    assert [item.classification for item in report.test_cases] == [
        "non_trivial",
        "invalid",
    ]
    assert [item.validity for item in report.test_cases] == [
        "fully_valid",
        "invalid",
    ]


def test_collection_uses_only_five_fixed_source_functions(tmp_path: Path) -> None:
    test_path = tmp_path / "task.py"
    test_path.write_text(
        "from markdown_it import MarkdownIt\n\n"
        "def test_file():\n"
        "    assert MarkdownIt().render('text')\n\n"
        "def test_extra():\n"
        "    assert MarkdownIt().render('extra')\n",
        encoding="utf-8",
    )

    report = collect_assertion_score(
        test_path,
        [
            _valid("task.py::test_file", "test_file"),
            _valid("task.py::test_extra", "test_extra"),
        ],
    )

    assert [item.source_test for item in report.test_cases] == [
        "test_file",
        "test_spec",
        "test_core_after",
        "test_parse_fail",
        "test_non_utf8",
    ]


def test_error_results_are_loaded_from_existing_json(tmp_path: Path) -> None:
    error_path = tmp_path / "metrics.json"
    error_path.write_text(
        json.dumps(
            {
                "metrics": {
                    "case_level": {
                        "test_cases": [
                            {
                                "nodeid": "tests/task/task.py::test_file[a]",
                                "source_test": "test_file",
                                "classification": "valid",
                                "returncode": 0,
                                "reason": "passed on original SUT",
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    results = _error_results_from_json(error_path)

    assert len(results) == 1
    assert results[0].nodeid == "tests/task/task.py::test_file[a]"
    assert results[0].classification == "valid"
