import math

import pytest

from scripts.metric_collection_phase2.collect_efficiency import (
    efficiency_row,
    index_rows,
    ratio,
)


def test_zero_scores_and_missing_or_invalid_times() -> None:
    assert ratio(0.0, 10.0) == 0
    assert ratio(None, 10.0) is None
    assert ratio(0.5, 0.0) is None
    assert ratio(0.5, -1.0) is None
    with pytest.raises(ValueError, match="Non-finite"):
        ratio(0.5, math.nan)


def test_reject_duplicate_or_missing_participant_ids() -> None:
    rows = [{"participant_number": n} for n in (2, 3, 4, 5, 7, 8, 9, 12)]
    assert len(index_rows(rows)) == 8
    with pytest.raises(ValueError, match="eight"):
        index_rows(rows[:-1])
    with pytest.raises(ValueError, match="eight"):
        index_rows([*rows, rows[0]])


@pytest.mark.parametrize("kind", ["generation", "execution"])
def test_conditional_intervals_retain_components_and_scale_with_time(kind: str) -> None:
    base = {
        "participant_statement_coverage": 0.8,
        "participant_branch_coverage": 0.4,
        "specified_estimated_adjusted_mutation_score": 0.6,
        "specified_mutation_score_ci95_lower": 0.5,
        "specified_mutation_score_ci95_upper": 0.7,
    }
    fast = efficiency_row(base, 2, kind)
    slow = efficiency_row(base, 4, kind)
    assert all(fast[key] == value for key, value in base.items())
    assert fast[f"mutation_{kind}_efficiency_per_second"] == 0.3
    assert fast[f"mutation_{kind}_efficiency_conditional_ci95_lower_per_second"] == 0.25
    for key in fast:
        if key.endswith("per_second"):
            assert slow[key] == fast[key] / 2
