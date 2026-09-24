"""Small deterministic checks for the analysis-specific statistical functions."""

from __future__ import annotations

import numpy as np

from analysis_utils import (
    cliffs_delta,
    exact_permutation_p_value,
    holm_adjust,
    load_phase1_data,
    validate_phase1_data,
)


def main() -> None:
    """Run algorithm checks plus the full source-data validation suite."""

    ai = np.array([2.0, 3.0])
    manual = np.array([0.0, 1.0])
    assert cliffs_delta(ai, manual) == 1.0
    p_value, allocations = exact_permutation_p_value(ai, manual)
    assert allocations == 6
    assert np.isclose(p_value, 2 / 6)
    assert np.allclose(holm_adjust([0.01, 0.03, 0.04]), [0.03, 0.06, 0.06])

    validation = validate_phase1_data(load_phase1_data())
    assert validation["status"].eq("PASS").all()
    print(f"All {len(validation)} source-data checks and statistical checks passed.")


if __name__ == "__main__":
    main()

