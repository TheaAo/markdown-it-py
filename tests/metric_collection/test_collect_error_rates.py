from pathlib import Path

from scripts.collect_error_rates import _split_test_file


def test_split_test_file_keeps_multiline_parametrize_decorator(tmp_path: Path):
    test_path = tmp_path / "test_participant.py"
    test_path.write_text(
        """\
import pytest

CASES = [(1, 1), (2, 2)]

@pytest.mark.parametrize(
    \"value,expected\",
    CASES,
)
def test_values(value, expected):
    assert value == expected

def helper():
    return True
""",
        encoding="utf-8",
    )

    support_source, test_blocks = _split_test_file(test_path)

    assert len(test_blocks) == 1
    assert test_blocks[0].name == "test_values"
    assert test_blocks[0].source.startswith("@pytest.mark.parametrize(")
    assert "def helper" in support_source
    assert "@pytest.mark.parametrize" not in support_source
