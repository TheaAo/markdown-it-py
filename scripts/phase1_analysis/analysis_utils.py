"""Data preparation and statistical methods for the Phase 1 analysis.

The module keeps raw result files read-only.  Every transformation produces a new
participant-level table, with one row per participant, before group comparisons are
performed.  Statistical functions are implemented here (rather than hidden in the
notebook) so that their assumptions and edge-case handling can be inspected.
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from config import (
    BOOTSTRAP_REPLICATES,
    PRIMARY_METRICS,
    RANDOM_SEED,
    RESULTS_DIR,
    SECONDARY_METRICS,
)


def _read_csv(relative_path: str, results_dir: Path) -> pd.DataFrame:
    """Read a result CSV without modifying the source file."""

    return pd.read_csv(results_dir / relative_path)


def _merge_selected(
    master: pd.DataFrame,
    frame: pd.DataFrame,
    columns: Sequence[str],
) -> pd.DataFrame:
    """Left-join selected participant columns and reject duplicate participant IDs."""

    if frame["participant_number"].duplicated().any():
        duplicates = frame.loc[
            frame["participant_number"].duplicated(), "participant_number"
        ].tolist()
        raise ValueError(f"Duplicate participant rows: {duplicates}")
    return master.merge(
        frame[["participant_number", *columns]],
        on="participant_number",
        how="left",
        validate="one_to_one",
    )


def load_phase1_data(results_dir: Path = RESULTS_DIR) -> pd.DataFrame:
    """Build the analysis master table from frozen metric-specific CSV files.

    The generation-time table is used as the participant registry because it
    contains all 16 allocated IDs, participation status, and treatment group.  The
    returned table retains the two non-participants for auditability; use
    :func:`participating_data` for inferential analyses.
    """

    generation = _read_csv("generation_time/generation_time.csv", results_dir)
    master = generation[
        [
            "participant_number",
            "status",
            "group",
            "comprehension_time_seconds",
            "generation_time_seconds",
        ]
    ].copy()

    error_rates = _read_csv("error_rates/error_rates.csv", results_dir)
    master = _merge_selected(
        master,
        error_rates,
        [
            "suite_collectable",
            "total_generated_test_cases",
            "valid_test_count",
            "syntax_error_count",
            "runtime_error_count",
            "function_error_count",
            "syntax_error_rate",
            "runtime_error_rate",
            "function_error_rate",
        ],
    )

    coverage = _read_csv("coverage/coverage.csv", results_dir)
    master = _merge_selected(
        master,
        coverage,
        [
            "valid_tests_included",
            "invalid_tests_excluded",
            "participant_statement_coverage",
            "participant_branch_coverage",
        ],
    )

    assertion = _read_csv("assertion_score/assertion_score.csv", results_dir)
    master = _merge_selected(
        master,
        assertion,
        [
            "invalid_test_count",
            "non_trivial_test_count",
            "trivial_test_count",
            "assertionless_test_count",
            "uncertain_test_count",
            "assertion_score",
        ],
    )

    mutation = _read_csv(
        "mutation_score/full-sut/formal/global/"
        "equivalent_review_sample_stage1/final/mutation_scores.csv",
        results_dir,
    )
    # Normalize the collector's concise column names to the explicit names used by
    # the efficiency tables and the analysis plan.
    mutation = mutation.rename(
        columns={
            "specified_estimated_adjusted_score": (
                "specified_estimated_adjusted_mutation_score"
            ),
            "specified_estimated_ci95_lower": "specified_mutation_score_ci95_lower",
            "specified_estimated_ci95_upper": "specified_mutation_score_ci95_upper",
        }
    )
    master = _merge_selected(
        master,
        mutation,
        [
            "specified_raw_mutation_score",
            "specified_estimated_adjusted_mutation_score",
            "specified_mutation_score_ci95_lower",
            "specified_mutation_score_ci95_upper",
            "specified_interval_half_width",
            "specified_stopping_interval_half_width",
            "all_primary_intervals_within_target",
        ],
    )

    execution = _read_csv(
        "execution_time/formal/summary/execution_time.csv", results_dir
    )
    execution = execution.rename(columns={"metric_status": "execution_metric_status"})
    master = _merge_selected(
        master,
        execution,
        [
            "execution_metric_status",
            "execution_time_seconds",
            "coefficient_of_variation",
            "cv_review_required",
        ],
    )

    generation_efficiency = _read_csv(
        "generation_time/generation_efficiency.csv", results_dir
    )
    master = _merge_selected(
        master,
        generation_efficiency,
        [
            "statement_generation_efficiency_per_second",
            "branch_generation_efficiency_per_second",
            "mutation_generation_efficiency_per_second",
            "mutation_generation_efficiency_ci95_lower_per_second",
            "mutation_generation_efficiency_ci95_upper_per_second",
        ],
    )

    execution_efficiency = _read_csv(
        "execution_time/execution_efficiency.csv", results_dir
    )
    master = _merge_selected(
        master,
        execution_efficiency,
        [
            "statement_execution_efficiency_per_second",
            "branch_execution_efficiency_per_second",
            "mutation_execution_efficiency_per_second",
            "mutation_execution_efficiency_ci95_lower_per_second",
            "mutation_execution_efficiency_ci95_upper_per_second",
        ],
    )

    smells = _read_csv("test_smells/summary/test_smell.csv", results_dir)
    master = _merge_selected(
        master,
        smells,
        [
            "eligible_test_count",
            "smelly_test_count",
            "confirmed_pair_count",
            "uncertain_pair_count",
            "assertion_roulette_count",
            "magic_number_test_count",
            "unknown_test_count",
            "conditional_test_logic_count",
            "eager_test_count",
            "duplicate_assert_count",
            "exception_handling_count",
            "smelly_test_rate",
            "mean_smells_per_test",
            "test_smell_density",
        ],
    )

    return master.sort_values("participant_number").reset_index(drop=True)


def participating_data(master: pd.DataFrame) -> pd.DataFrame:
    """Return the 14 participants who completed Phase 1."""

    return master.loc[master["status"].eq("collected")].copy().reset_index(drop=True)


def validate_phase1_data(master: pd.DataFrame) -> pd.DataFrame:
    """Run explicit data-integrity checks and return an auditable check table."""

    participants = participating_data(master)
    checks: list[dict[str, str]] = []

    def record(name: str, condition: bool, detail: str) -> None:
        checks.append(
            {"check": name, "status": "PASS" if condition else "FAIL", "detail": detail}
        )

    record(
        "Allocated participant IDs",
        master["participant_number"].tolist() == list(range(1, 17)),
        "Expected IDs 1-16 exactly once.",
    )
    record(
        "Participation count",
        len(participants) == 14,
        f"Observed {len(participants)} participants.",
    )
    group_counts = participants["group"].value_counts().to_dict()
    record(
        "Treatment group counts",
        group_counts == {"Manual": 8, "AI": 6},
        f"Observed {group_counts}.",
    )
    nonparticipants = master.loc[
        master["status"].eq("not_participated"), "participant_number"
    ].tolist()
    record(
        "Non-participant IDs",
        nonparticipants == [13, 15],
        f"Observed {nonparticipants}.",
    )

    error_total = participants[
        [
            "valid_test_count",
            "syntax_error_count",
            "runtime_error_count",
            "function_error_count",
        ]
    ].sum(axis=1)
    error_invariant = np.allclose(
        error_total.to_numpy(dtype=float),
        participants["total_generated_test_cases"].to_numpy(dtype=float),
    )
    record(
        "Error-rate count invariant",
        bool(error_invariant),
        "valid + syntax + runtime + function errors equals generated tests.",
    )

    no_valid = participants.loc[
        participants["valid_test_count"].eq(0), "participant_number"
    ].tolist()
    record(
        "No-valid-test participants",
        no_valid == [4, 6],
        f"Observed {no_valid}.",
    )

    for metric in (
        "participant_statement_coverage",
        "assertion_score",
        "execution_time_seconds",
        "test_smell_density",
    ):
        missing_ids = participants.loc[
            participants[metric].isna(), "participant_number"
        ].tolist()
        record(
            f"Missingness: {metric}",
            missing_ids == [4, 6],
            f"Missing for participant IDs {missing_ids}.",
        )

    mutation_missing = participants.loc[
        participants["specified_estimated_adjusted_mutation_score"].isna(),
        "participant_number",
    ].tolist()
    record(
        "Adjusted mutation-score completeness",
        not mutation_missing,
        f"Missing for participant IDs {mutation_missing}.",
    )

    mutation_efficiency_missing = participants.loc[
        participants["mutation_generation_efficiency_per_second"].isna(),
        "participant_number",
    ].tolist()
    record(
        "Mutation generation-efficiency completeness",
        not mutation_efficiency_missing,
        f"Missing for participant IDs {mutation_efficiency_missing}.",
    )

    uncertain_assertions = participants.loc[
        participants["uncertain_test_count"].fillna(0).gt(0),
        ["participant_number", "uncertain_test_count"],
    ]
    record(
        "Assertion uncertainty",
        uncertain_assertions.empty
        and bool(participants.loc[participants["participant_number"].eq(8), "assertion_score"].eq(1).all())
        and bool(participants.loc[participants["participant_number"].eq(8), "non_trivial_test_count"].eq(1).all()),
        f"Observed {uncertain_assertions.to_dict('records')}.",
    )
    record(
        "Test-smell uncertainty",
        float(participants["uncertain_pair_count"].fillna(0).sum()) == 0.0,
        "No uncertain source-test/smell pairs expected.",
    )
    record(
        "Mutation review precision target",
        bool(
            participants["all_primary_intervals_within_target"]
            .dropna()
            .astype(bool)
            .all()
        )
        and participants["all_primary_intervals_within_target"].notna().all(),
        "All participant specified-layer intervals must satisfy the stopping rule.",
    )

    result = pd.DataFrame(checks)
    failed = result.loc[result["status"].eq("FAIL")]
    if not failed.empty:
        names = ", ".join(failed["check"].tolist())
        raise ValueError(f"Phase 1 data validation failed: {names}")
    return result


def descriptive_statistics(
    data: pd.DataFrame,
    metrics: Iterable[str],
) -> pd.DataFrame:
    """Compute group-wise participant-level descriptive statistics."""

    rows: list[dict[str, Any]] = []
    for metric in metrics:
        for group in ("AI", "Manual"):
            values = data.loc[data["group"].eq(group), metric].dropna().astype(float)
            rows.append(
                {
                    "metric": metric,
                    "group": group,
                    "n": int(values.size),
                    "mean": values.mean(),
                    "standard_deviation": values.std(ddof=1),
                    "median": values.median(),
                    "first_quartile": values.quantile(0.25),
                    "third_quartile": values.quantile(0.75),
                    "minimum": values.min(),
                    "maximum": values.max(),
                }
            )
    return pd.DataFrame(rows)


def cliffs_delta(ai_values: np.ndarray, manual_values: np.ndarray) -> float:
    """Calculate Cliff's delta; positive values mean larger values in the AI group."""

    comparisons = ai_values[:, None] - manual_values[None, :]
    return float((np.sum(comparisons > 0) - np.sum(comparisons < 0)) / comparisons.size)


def bootstrap_mean_difference(
    ai_values: np.ndarray,
    manual_values: np.ndarray,
    *,
    replicates: int = BOOTSTRAP_REPLICATES,
    seed: int = RANDOM_SEED,
) -> tuple[float, float]:
    """Return a percentile bootstrap 95% interval for AI minus Manual means."""

    rng = np.random.default_rng(seed)
    ai_samples = rng.choice(ai_values, size=(replicates, ai_values.size), replace=True)
    manual_samples = rng.choice(
        manual_values, size=(replicates, manual_values.size), replace=True
    )
    differences = ai_samples.mean(axis=1) - manual_samples.mean(axis=1)
    lower, upper = np.quantile(differences, [0.025, 0.975])
    return float(lower), float(upper)


def exact_permutation_p_value(
    ai_values: np.ndarray,
    manual_values: np.ndarray,
) -> tuple[float, int]:
    """Enumerate all group allocations for a two-sided mean-difference test."""

    pooled = np.concatenate([ai_values, manual_values]).astype(float)
    ai_size = ai_values.size
    observed = float(ai_values.mean() - manual_values.mean())
    extreme = 0
    total = 0
    all_indexes = np.arange(pooled.size)

    # With at most 14 observations there are only C(14, 6)=3003 allocations, so
    # enumeration is preferable to a Monte Carlo approximation.
    for ai_indexes_tuple in combinations(range(pooled.size), ai_size):
        ai_indexes = np.fromiter(ai_indexes_tuple, dtype=int)
        manual_indexes = np.setdiff1d(all_indexes, ai_indexes, assume_unique=True)
        difference = pooled[ai_indexes].mean() - pooled[manual_indexes].mean()
        if abs(difference) >= abs(observed) - 1e-15:
            extreme += 1
        total += 1
    return extreme / total, total


def analyze_metric(
    data: pd.DataFrame,
    metric: str,
    *,
    seed: int = RANDOM_SEED,
) -> dict[str, Any]:
    """Analyze one metric after dropping only observations where it is undefined."""

    subset = data.loc[data[metric].notna(), ["participant_number", "group", metric]]
    ai = subset.loc[subset["group"].eq("AI"), metric].to_numpy(dtype=float)
    manual = subset.loc[subset["group"].eq("Manual"), metric].to_numpy(dtype=float)
    if ai.size == 0 or manual.size == 0:
        raise ValueError(f"Metric {metric} lacks observations in one treatment group")

    mean_difference = float(ai.mean() - manual.mean())
    ci_lower, ci_upper = bootstrap_mean_difference(ai, manual, seed=seed)
    p_value, allocations = exact_permutation_p_value(ai, manual)
    return {
        "metric": metric,
        "n_ai": int(ai.size),
        "n_manual": int(manual.size),
        "mean_ai": float(ai.mean()),
        "mean_manual": float(manual.mean()),
        "mean_difference_ai_minus_manual": mean_difference,
        "bootstrap_ci95_lower": ci_lower,
        "bootstrap_ci95_upper": ci_upper,
        "cliffs_delta": cliffs_delta(ai, manual),
        "exact_permutation_p_value": p_value,
        "permutation_allocations": allocations,
    }


def holm_adjust(p_values: Sequence[float]) -> list[float]:
    """Apply Holm's step-down family-wise error correction."""

    values = np.asarray(p_values, dtype=float)
    order = np.argsort(values)
    adjusted_sorted = np.empty(values.size, dtype=float)
    running_max = 0.0
    for rank, index in enumerate(order):
        adjusted = (values.size - rank) * values[index]
        running_max = max(running_max, adjusted)
        adjusted_sorted[rank] = min(running_max, 1.0)
    adjusted = np.empty(values.size, dtype=float)
    for rank, index in enumerate(order):
        adjusted[index] = adjusted_sorted[rank]
    return adjusted.tolist()


def analyze_metrics(
    data: pd.DataFrame,
    metrics: Mapping[str, Mapping[str, object]],
    *,
    apply_primary_holm: bool = False,
) -> pd.DataFrame:
    """Analyze a declared metric set and attach labels and interpretation metadata."""

    rows: list[dict[str, Any]] = []
    for offset, (metric, metadata) in enumerate(metrics.items()):
        row = analyze_metric(data, metric, seed=RANDOM_SEED + offset)
        row.update(
            {
                "label": metadata["label"],
                "scale": metadata["scale"],
                "higher_is_better": metadata["higher_is_better"],
            }
        )
        rows.append(row)
    result = pd.DataFrame(rows)
    if apply_primary_holm:
        result["holm_adjusted_p_value"] = holm_adjust(
            result["exact_permutation_p_value"].tolist()
        )
    else:
        result["holm_adjusted_p_value"] = np.nan
    return result


def run_sensitivity_analyses(data: pd.DataFrame) -> pd.DataFrame:
    """Run the pre-specified special-case analyses from the analysis plan."""

    rows: list[dict[str, Any]] = []

    def add(scenario: str, metric: str, frame: pd.DataFrame) -> None:
        row = analyze_metric(frame, metric, seed=RANDOM_SEED + len(rows) + 100)
        row["scenario"] = scenario
        rows.append(row)

    add(
        "Primary adjusted mutation score",
        "specified_estimated_adjusted_mutation_score",
        data,
    )
    add("Raw mutation score", "specified_raw_mutation_score", data)

    # Treating no artifact as maximum smell density is deliberately extreme.  It
    # is a stress test, not a replacement for the primary complete-case analysis.
    worst_smell = data.copy()
    no_valid = worst_smell["valid_test_count"].eq(0)
    worst_smell.loc[no_valid, "test_smell_density"] = 1.0
    add("No-valid-test suites assigned smell density 1", "test_smell_density", worst_smell)

    # Participant 8's assertion was manually resolved as non-trivial; there is
    # no remaining lower/upper assertion-classification scenario to test.
    without_11 = data.loc[~data["participant_number"].eq(11)].copy()
    add("Execution time excluding participant 11", "execution_time_seconds", without_11)
    add(
        "Mutation execution efficiency excluding participant 11",
        "mutation_execution_efficiency_per_second",
        without_11,
    )

    log_times = data.copy()
    log_times["log_generation_time"] = np.log(log_times["generation_time_seconds"])
    log_times["log_execution_time"] = np.log(log_times["execution_time_seconds"])
    add("Log-transformed generation time", "log_generation_time", log_times)
    add("Log-transformed execution time", "log_execution_time", log_times)

    result = pd.DataFrame(rows)
    return result[
        [
            "scenario",
            "metric",
            "n_ai",
            "n_manual",
            "mean_ai",
            "mean_manual",
            "mean_difference_ai_minus_manual",
            "bootstrap_ci95_lower",
            "bootstrap_ci95_upper",
            "cliffs_delta",
            "exact_permutation_p_value",
            "permutation_allocations",
        ]
    ]


def load_questionnaires(
    results_dir: Path = RESULTS_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load the common pre-survey and the two condition-specific post-surveys."""

    pre = _read_csv("questionnaire/pre_survey.csv", results_dir).rename(
        columns={"No": "participant_number", "Group": "group"}
    )
    ai = _read_csv("questionnaire/post_survey_ai_group.csv", results_dir).rename(
        columns={"ID": "participant_number"}
    )
    manual = _read_csv("questionnaire/post_survey_manual_group.csv", results_dir).rename(
        columns={"ID": "participant_number"}
    )
    return pre, ai, manual


def likert_summary(
    frame: pd.DataFrame,
    columns: Sequence[str],
    *,
    survey: str,
) -> pd.DataFrame:
    """Return counts, percentages, median, and IQR for 1-5 Likert items."""

    rows: list[dict[str, Any]] = []
    for order, column in enumerate(columns, start=1):
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if not values.between(1, 5).all():
            raise ValueError(f"Likert item contains values outside 1-5: {column}")
        row: dict[str, Any] = {
            "survey": survey,
            "item_order": order,
            "item": column,
            "n": int(values.size),
            "median": float(values.median()),
            "first_quartile": float(values.quantile(0.25)),
            "third_quartile": float(values.quantile(0.75)),
        }
        for score in range(1, 6):
            count = int(values.eq(score).sum())
            row[f"score_{score}_count"] = count
            row[f"score_{score}_percent"] = count / values.size * 100
        rows.append(row)
    return pd.DataFrame(rows)


def questionnaire_outputs(
    results_dir: Path = RESULTS_DIR,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Prepare numeric questionnaire summaries and open text for manual coding."""

    pre, ai, manual = load_questionnaires(results_dir)

    ai_likert_columns = list(ai.columns[5:14])
    manual_likert_columns = list(manual.columns[3:12])
    likert = pd.concat(
        [
            likert_summary(ai, ai_likert_columns, survey="AI post-survey"),
            likert_summary(manual, manual_likert_columns, survey="Manual post-survey"),
        ],
        ignore_index=True,
    )

    # Baseline variables are descriptive only because the randomization details
    # are unavailable.  Numeric self-ratings are summarized by assigned group.
    pre_numeric_columns = [
        pre.columns[index]
        for index in [4, 6, 7, 8, 9, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25]
    ]
    baseline_rows: list[dict[str, Any]] = []
    for column in pre_numeric_columns:
        for group in ("AI", "Manual"):
            values = pd.to_numeric(
                pre.loc[pre["group"].eq(group), column], errors="coerce"
            ).dropna()
            baseline_rows.append(
                {
                    "item": column,
                    "group": group,
                    "n": int(values.size),
                    "median": float(values.median()),
                    "first_quartile": float(values.quantile(0.25)),
                    "third_quartile": float(values.quantile(0.75)),
                }
            )
    baseline = pd.DataFrame(baseline_rows)

    open_rows: list[dict[str, Any]] = []
    for survey, group, frame, start in (
        ("AI post-survey", "AI", ai, 14),
        ("Manual post-survey", "Manual", manual, 12),
    ):
        for _, response in frame.iterrows():
            for column in frame.columns[start:]:
                value = response[column]
                if pd.notna(value) and str(value).strip():
                    open_rows.append(
                        {
                            "survey": survey,
                            "group": group,
                            "participant_number": int(response["participant_number"]),
                            "question": column,
                            "response": str(value).strip(),
                            "theme_codes": "",
                            "coding_notes": "",
                        }
                    )
    open_text = pd.DataFrame(open_rows)
    return baseline, likert, open_text


def all_metric_metadata() -> dict[str, dict[str, object]]:
    """Return primary and secondary metric metadata in reporting order."""

    return {**PRIMARY_METRICS, **SECONDARY_METRICS}
