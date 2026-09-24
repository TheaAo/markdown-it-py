"""Configuration and metric metadata for the Phase 1 analysis."""

from __future__ import annotations

from pathlib import Path


ANALYSIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = ANALYSIS_DIR.parents[1]
RESULTS_DIR = REPO_ROOT / "results"
OUTPUT_DIR = ANALYSIS_DIR / "outputs"
TABLE_DIR = OUTPUT_DIR / "tables"
FIGURE_DIR = OUTPUT_DIR / "figures"

# The seed is fixed so that bootstrap intervals and jittered plot positions can be
# reproduced exactly on another machine.
RANDOM_SEED = 20260924
BOOTSTRAP_REPLICATES = 20_000

GROUP_ORDER = ("Manual", "AI")
GROUP_COLORS = {"Manual": "#6B7280", "AI": "#2563EB"}

# The primary endpoints follow the Statistical Analysis Plan.  `scale` controls
# presentation only; every rate remains stored internally on its original 0-1
# scale and every efficiency remains per second.
PRIMARY_METRICS: dict[str, dict[str, object]] = {
    "specified_estimated_adjusted_mutation_score": {
        "label": "Estimated adjusted mutation score",
        "short_label": "Adjusted mutation score",
        "scale": "proportion",
        "higher_is_better": True,
    },
    "mutation_generation_efficiency_per_second": {
        "label": "Mutation generation efficiency (score per second)",
        "short_label": "Mutation generation efficiency",
        "scale": "rate",
        "higher_is_better": True,
    },
    "test_smell_density": {
        "label": "Test smell density",
        "short_label": "Test smell density",
        "scale": "proportion",
        "higher_is_better": False,
    },
}

SECONDARY_METRICS: dict[str, dict[str, object]] = {
    "syntax_error_rate": {
        "label": "Syntax error rate",
        "scale": "proportion",
        "higher_is_better": False,
    },
    "runtime_error_rate": {
        "label": "Runtime error rate",
        "scale": "proportion",
        "higher_is_better": False,
    },
    "function_error_rate": {
        "label": "Function error rate",
        "scale": "proportion",
        "higher_is_better": False,
    },
    "participant_statement_coverage": {
        "label": "Statement coverage",
        "scale": "proportion",
        "higher_is_better": True,
    },
    "participant_branch_coverage": {
        "label": "Branch coverage",
        "scale": "proportion",
        "higher_is_better": True,
    },
    "assertion_score": {
        "label": "Assertion score",
        "scale": "proportion",
        "higher_is_better": True,
    },
    "generation_time_seconds": {
        "label": "Generation time (seconds)",
        "scale": "seconds",
        "higher_is_better": False,
    },
    "execution_time_seconds": {
        "label": "Execution time (seconds)",
        "scale": "seconds",
        "higher_is_better": False,
    },
    "statement_generation_efficiency_per_second": {
        "label": "Statement generation efficiency (coverage per second)",
        "scale": "rate",
        "higher_is_better": True,
    },
    "branch_generation_efficiency_per_second": {
        "label": "Branch generation efficiency (coverage per second)",
        "scale": "rate",
        "higher_is_better": True,
    },
    "statement_execution_efficiency_per_second": {
        "label": "Statement execution efficiency (coverage per second)",
        "scale": "rate",
        "higher_is_better": True,
    },
    "branch_execution_efficiency_per_second": {
        "label": "Branch execution efficiency (coverage per second)",
        "scale": "rate",
        "higher_is_better": True,
    },
    "mutation_execution_efficiency_per_second": {
        "label": "Mutation execution efficiency (score per second)",
        "scale": "rate",
        "higher_is_better": True,
    },
}

