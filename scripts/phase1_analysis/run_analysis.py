"""Run the complete Phase 1 statistical analysis from the command line.

Usage from the repository root::

    python3 scripts/phase1_analysis/run_analysis.py

The command never changes source data under ``results/``.  It rebuilds the
analysis tables and manifest under ``scripts/phase1_analysis/outputs/``.  Figure
generation intentionally lives in ``phase1_analysis.ipynb`` so each chart can be
run and inspected one step at a time.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from analysis_utils import (
    all_metric_metadata,
    analyze_metrics,
    descriptive_statistics,
    load_phase1_data,
    participating_data,
    questionnaire_outputs,
    run_sensitivity_analyses,
    validate_phase1_data,
)
from config import (
    BOOTSTRAP_REPLICATES,
    FIGURE_DIR,
    OUTPUT_DIR,
    PRIMARY_METRICS,
    RANDOM_SEED,
    RESULTS_DIR,
    SECONDARY_METRICS,
    TABLE_DIR,
)
SOURCE_FILES = [
    "error_rates/error_rates.csv",
    "coverage/coverage.csv",
    "assertion_score/assertion_score.csv",
    "assertion_score/manual_review.csv",
    "mutation_score/full-sut/formal/global/equivalent_review_sample_stage1/"
    "final/mutation_scores.csv",
    "generation_time/generation_time.csv",
    "generation_time/generation_efficiency.csv",
    "execution_time/formal/summary/execution_time.csv",
    "execution_time/execution_efficiency.csv",
    "test_smells/summary/test_smell.csv",
    "questionnaire/pre_survey.csv",
    "questionnaire/post_survey_ai_group.csv",
    "questionnaire/post_survey_manual_group.csv",
]


def _sha256(path: Path) -> str:
    """Return a source-file checksum recorded in the analysis manifest."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_data_completeness(data: pd.DataFrame) -> pd.DataFrame:
    """Summarize the available participant count and missing IDs for each metric."""

    rows: list[dict[str, Any]] = []
    for metric, metadata in all_metric_metadata().items():
        available = data[metric].notna()
        rows.append(
            {
                "metric": metric,
                "label": metadata["label"],
                "available_n": int(available.sum()),
                "ai_n": int((available & data["group"].eq("AI")).sum()),
                "manual_n": int((available & data["group"].eq("Manual")).sum()),
                "missing_participant_ids": ",".join(
                    data.loc[~available, "participant_number"].astype(str)
                ),
            }
        )
    return pd.DataFrame(rows)


def build_data_dictionary() -> pd.DataFrame:
    """Document the analysis endpoint definitions and missing-value rules."""

    definitions = {
        "specified_estimated_adjusted_mutation_score": (
            "Estimated specified-layer killed-mutant proportion after design-weighted "
            "equivalent-mutant adjustment; not an exhaustive exact score."
        ),
        "mutation_generation_efficiency_per_second": (
            "Estimated adjusted mutation score divided by self-reported total "
            "generation time in seconds."
        ),
        "test_smell_density": (
            "Confirmed (eligible source test, smell type) pairs divided by eligible "
            "source tests times seven frozen smell types."
        ),
        "syntax_error_rate": "Syntax-error pytest items divided by generated pytest items.",
        "runtime_error_rate": "Runtime-error pytest items divided by generated pytest items.",
        "function_error_rate": "Function-error pytest items divided by generated pytest items.",
        "participant_statement_coverage": "Statements covered by valid participant tests divided by measurable statements.",
        "participant_branch_coverage": "Branches covered by valid participant tests divided by measurable branches.",
        "assertion_score": "Eligible source test functions with a non-trivial SUT-related oracle divided by eligible source test functions.",
        "generation_time_seconds": "Self-reported total task time, including comprehension time, in seconds.",
        "execution_time_seconds": "Median wall-clock seconds from 15 fresh pytest-process measurements of valid participant tests.",
        "statement_generation_efficiency_per_second": "Statement coverage divided by generation time in seconds.",
        "branch_generation_efficiency_per_second": "Branch coverage divided by generation time in seconds.",
        "statement_execution_efficiency_per_second": "Statement coverage divided by median execution time in seconds.",
        "branch_execution_efficiency_per_second": "Branch coverage divided by median execution time in seconds.",
        "mutation_execution_efficiency_per_second": "Estimated adjusted mutation score divided by median execution time in seconds.",
    }
    rows: list[dict[str, Any]] = []
    for role, metrics in (("primary", PRIMARY_METRICS), ("secondary", SECONDARY_METRICS)):
        for metric, metadata in metrics.items():
            rows.append(
                {
                    "variable": metric,
                    "analysis_role": role,
                    "label": metadata["label"],
                    "unit_or_scale": metadata["scale"],
                    "higher_is_better": metadata["higher_is_better"],
                    "definition": definitions[metric],
                    "missing_value_rule": (
                        "NA when undefined; never replace with zero in the primary analysis."
                    ),
                }
            )
    return pd.DataFrame(rows)


def write_manifest() -> None:
    """Record source checksums and fixed randomness parameters."""

    manifest = {
        "analysis_scope": "Phase 1 only",
        "random_seed": RANDOM_SEED,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "exact_permutation_test": True,
        "mean_difference_direction": "AI minus Manual",
        "individual_plot_excluded_participant_ids": [6],
        "statistical_sample_excluded_participant_ids": [],
        "mutation_csv_restoration": "Restored from the archived Mutation score worksheet; see RESTORATION.md beside the CSV.",
        "source_files": {
            relative: _sha256(RESULTS_DIR / relative) for relative in SOURCE_FILES
        },
    }
    (OUTPUT_DIR / "analysis_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def run() -> dict[str, pd.DataFrame]:
    """Execute statistics, write tabular outputs, and return core result tables."""

    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    master = load_phase1_data()
    validation = validate_phase1_data(master)
    data = participating_data(master)

    all_metrics = list(PRIMARY_METRICS) + list(SECONDARY_METRICS)
    descriptive = descriptive_statistics(data, all_metrics)
    primary = analyze_metrics(data, PRIMARY_METRICS, apply_primary_holm=True)
    secondary = analyze_metrics(data, SECONDARY_METRICS)
    sensitivity = run_sensitivity_analyses(data)
    completeness = build_data_completeness(data)
    dictionary = build_data_dictionary()
    baseline, likert, open_text = questionnaire_outputs()

    # CSV is used for generated tables because it is transparent, diffable, and
    # does not add a second manually maintained workbook to the research record.
    tables = {
        "participant_master": data,
        "data_validation": validation,
        "data_completeness": completeness,
        "data_dictionary": dictionary,
        "descriptive_statistics": descriptive,
        "primary_results": primary,
        "secondary_results": secondary,
        "sensitivity_results": sensitivity,
        "questionnaire_baseline": baseline,
        "questionnaire_likert": likert,
        "questionnaire_open_text_coding": open_text,
    }
    for name, frame in tables.items():
        frame.to_csv(TABLE_DIR / f"{name}.csv", index=False)

    write_manifest()
    return {
        "master": master,
        "validation": validation,
        "descriptive": descriptive,
        "primary": primary,
        "secondary": secondary,
        "sensitivity": sensitivity,
        "likert": likert,
    }


if __name__ == "__main__":
    results = run()
    print("Phase 1 analysis completed.")
    print(results["primary"].to_string(index=False))
