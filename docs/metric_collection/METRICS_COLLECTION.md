# Experiment Metrics Collection

This document describes how to collect error-rate, coverage, assertion-score,
mutation-score, test-smell, and execution-time metrics from participant test
submissions.

Test Smell research documents:

- [TEST_SMELL_PILOT.md](../../TEST_SMELL_PILOT.md): pilot evidence and tool choice;
- [TEST_SMELL_HANDOFF.md](../../TEST_SMELL_HANDOFF.md): implementation handoff.
- [TEST_SMELL_AUDIT.md](../../TEST_SMELL_AUDIT.md): frozen-rule participant audit.

## Environment

Run the commands from the repository root on the `pilot-metric` branch. The Python
environment must contain pytest and the project testing dependencies.

Create the environment if it does not already exist:

```bash
python3 -m venv venv
venv/bin/python -m pip install -e '.[testing]'
```

Before collecting participant branches, update the remote-tracking refs:

```bash
git fetch --prune origin
```

The collectors execute participant-authored Python code. Only run them on trusted
experiment branches and in the dedicated experiment environment.

## Directory Layout

- `scripts/metric_collection/` contains only the research data collectors,
  workload definitions, summarizers, and review tools.
- `tests/metric_collection/` contains their regression tests.
- `docs/metric_collection/` contains the current methodology and usage documents.
- `results/error_rates/` contains the cross-participant collection manifest and raw
  records. Those records also carry coverage and assertion evidence so that the
  valid-test classification is performed only once.
- `results/coverage/` contains the analysis-ready coverage table.
- `results/assertion_score/` contains the analysis-ready assertion-score table.
- `results/mutation_score/` contains mutation catalogs, execution records, reviews,
  and analysis-ready mutation tables.
- `results/execution_time/` contains pilot and formal timing measurements.
- `results/test_smells/` contains detector evidence and test-smell summaries.
- `results/mutation_score/` is ignored by Git so its large catalogs and raw
  execution records are not accidentally committed. The smaller frozen datasets
  for the other metrics remain version-controlled research evidence.

Catalog and score commands use project-local result paths by default. Temporary
directories are used only as isolated execution workspaces and are removed after a
run; reviewable outputs are written under the metric-specific directories above.

## Single Submission

Collect one test file with:

```bash
venv/bin/python scripts/metric_collection/collect_error_rates.py \
  tests/task/task.py \
  --timeout 120 \
  > metrics.json
```

The report contains two levels:

- `suite_level` describes whether the original submitted test module can be
  collected by pytest without modification.
- `case_level` isolates top-level `test_*` functions so that one syntax error does
  not prevent classification of the other tests.

Parameterized tests are counted as separate generated test cases after pytest
expands them. For example, `test_spec[test_case217]` is one test case.

Collect statement and branch coverage together with the error-rate classification:

```bash
venv/bin/python scripts/metric_collection/collect_coverage.py \
  tests/task/task.py \
  --repo-root . \
  --python venv/bin/python \
  --source markdown_it \
  --project-tests tests \
  --timeout 120 \
  --format json \
  > coverage_metrics.json
```

Omit `--format json` for a human-readable terminal report. The JSON output contains
`error_rates`, `coverage`, and `assertion_score`, so error-rate classification is not
run a second time by the batch collector.

Collect assertion score without coverage with:

```bash
venv/bin/python scripts/metric_collection/collect_assertion_score.py \
  tests/task/task.py \
  --error-rates metrics.json \
  > assertion_score.json
```

## Error Metrics

The case-level classifications are mutually exclusive:

- `valid`: the test executes and passes on the original, fault-free SUT.
- `syntax_error`: the isolated test function cannot be parsed as Python.
- `runtime_error`: the test is syntactically valid but fails during collection,
  setup, execution, or teardown with a non-assertion error.
- `function_error`: the test executes but an assertion or explicit `pytest.fail`
  fails on the original SUT.

The rates use the number of expanded generated test cases as the denominator:

```text
Syntax Error Rate   = syntax_error_count / total_generated_test_cases
Runtime Error Rate  = runtime_error_count / total_generated_test_cases
Function Error Rate = function_error_count / total_generated_test_cases
```

The following invariant must hold for every successful report:

```text
valid_test_count
+ syntax_error_count
+ runtime_error_count
+ function_error_count
= total_generated_test_cases
```

Execution metrics such as coverage and mutation score use only generated pytest
instances classified as `valid`. Source-level maintenance metrics aggregate those
instances back to each source function: `fully_valid` means all instances are
valid, `partially_valid` means at least one but not all are valid, and `invalid`
means none are valid. Both `fully_valid` and `partially_valid` source functions are
eligible for Assertion Score and Test Smell analysis.

The raw unit must not be conflated with the participant-level output. Error Rate
and per-test Execution Time classify expanded pytest items. Assertion Score and
Test Smell classify the five source functions because parameterization does not
create additional test code. Coverage and Mutation Score are execution-set
metrics: valid pytest items determine the executed set, but covered statements,
branches, and killed mutants are aggregated over that set rather than averaged as
independent item scores. Every metric is finally summarized once per participant.

## Coverage Metrics

Coverage is measured with branch tracking enabled and only valid participant tests
are included in the participant scope:

- participant statement coverage is the proportion of executable source statements
  executed by valid participant tests;
- participant branch coverage is the proportion of measured control-flow branches
  executed by valid participant tests;
- all-tests-combined coverage runs the original project tests together with valid
  participant tests, making it possible to compare participant-only coverage with
  the complete regression suite;
- `valid_tests_included` and `invalid_tests_excluded` document exactly how many
  generated participant cases contributed to coverage.

Each coverage metric stores `covered`, `total`, and `rate`. CSV rate values use the
range 0 to 1. A participant with no valid tests has empty participant-only coverage
cells; this must not be interpreted as zero coverage.

## Assertion Score

Assertion score estimates the proportion of eligible source test functions that
contain at least one non-trivial oracle related to `markdown_it`:

```text
Assertion Score =
Non-trivial Source Tests / Eligible Source Tests
```

Unlike Error Rate, Assertion Score uses the five fixed source test functions
`test_file`, `test_spec`, `test_core_after`, `test_parse_fail`, and
`test_non_utf8` as its units of analysis. Pytest parameter instances are grouped
back into their source function and are used only to determine that function's
validity from existing Error Rate JSON:

- `fully_valid`: every generated instance is `valid`;
- `partially_valid`: at least one, but not every, generated instance is `valid`;
- `invalid`: zero generated instances are `valid`, including a missing function.

Both `fully_valid` and `partially_valid` functions enter the Assertion Score
denominator. Only `invalid` functions are excluded. When no eligible source tests
remain, the score is unavailable (`null`) rather than zero. The Assertion Score
collector never reruns pytest; standalone collection requires an existing Error
Rate JSON file through `--error-rates`.

The collector performs conservative static analysis over each submitted test and
its local helpers. It tracks imported `markdown_it` symbols, assignments, returned
values, method calls, simple helper transformations, `pytest.raises` and
`pytest.warns` contexts, assertion methods, and captured output. Each eligible
source test is classified into exactly one category:

- `invalid`: no generated parameter instance passed Error Rate;
- `non_trivial`: at least one oracle has a detected backward dependency on the SUT;
- `trivial`: all detected assertions are constants, self-comparisons, generic
  type/`None` checks, or otherwise unrelated to the SUT;
- `assertionless`: no supported assertion or exception oracle is present;
- `uncertain`: the SUT is executed or an oracle is present, but the dependency
  cannot be resolved confidently by the static analysis.

The five classifications are mutually exclusive. `eligible source tests` equals
`non_trivial + trivial + assertionless + uncertain`; `invalid` is excluded. The
reported score is a conservative lower bound because `uncertain` remains in the
denominator but not the numerator. Raw JSON records each source test's
`generated_nodeids`, `valid_instance_count`, `total_instance_count`, `validity`,
assertion classification, source line, oracle type, and reason. Review all
`uncertain` cases manually before final statistical analysis.

## Test Smell

The fixed protocol analyzes seven smells: Assertion Roulette, Magic Number Test,
Unknown Test, Conditional Test Logic, Eager Test, Duplicate Assert, and Exception
Handling. Test Maverick is excluded because the experiment uses function-style
pytest tests without a uniform class-level setup model.

A versioned AST rule engine scans every eligible source function for all seven
smells. pytest-smell 1.0.5 supplies external evidence, and pinned TEMPY supplies an
independent cross-check for Conditional Test Logic, Unknown Test, and Exception
Handling. External alerts do not restrict the AST scan and are not averaged or
voted into the result. See [TEST_SMELL_PILOT.md](TEST_SMELL_PILOT.md) for frozen
definitions and executed per-smell validation.

```text
Smelly Test Rate = Smelly Eligible Source Tests / Eligible Source Tests

Mean Smells per Test = Confirmed (Source Test, Smell Type) Pairs
                       / Eligible Source Tests

Test Smell Density = Confirmed (Source Test, Smell Type) Pairs
                     / (Eligible Source Tests * 7 Formal Smell Types)
```

One smell type counts at most once per source function. `smelly_test_rate` and
`test_smell_density` are bounded proportions in `[0, 1]`; `mean_smells_per_test`
retains the interpretable unnormalized result in `[0, 7]`. All three are `null`
when there are no eligible source functions. Raw tool alerts, AST evidence,
reasons, uncertain decisions, and rule/tool versions must be retained.

The formal collector never imports or executes participant code. It reads the
existing Error Rate JSON, obtains the exact participant source from its recorded
Git commit, and analyzes an isolated copy containing only eligible target tests and
static support code. Use:

```bash
python3 scripts/collect_test_smells_all_branches.py \
  --error-manifest results/error_rates/collection_manifest.json \
  --output-dir results/test_smells \
  --pytest-smell /path/to/pytest-smell \
  --tempy-root /path/to/TEMPY \
  --python /path/to/python \
  --timeout 60

python3 scripts/summarize_test_smells.py \
  results/test_smells/collection_manifest.json \
  --output results/test_smells/summary/test_smell.csv
```

pytest-smell must be version `1.0.5`. TEMPY must be checked out at commit
`4c945d121d645b52fefb8f1b4f3e6caeec7c9095`; a mismatched checkout is recorded as
a failure. A missing tool, failed tool, successful zero-alert run, and a skipped
run caused by zero eligible tests are distinct states. Neither external result
changes the versioned AST decision.

The completed collection produced 50 eligible source tests across the 14
participating submissions. Eighteen tests contain at least one confirmed smell and
there are 22 confirmed `(source test, smell type)` pairs: Smelly Test Rate `0.36`,
Mean Smells per Test `0.44`, and normalized Test Smell Density `0.062857`. Counts by
type are Assertion Roulette 5, Magic Number Test 0, Unknown Test 5, Conditional
Test Logic 10, Eager Test 0, Duplicate Assert 0, and Exception Handling 2. No pair
was marked uncertain. Participants 04 and 06 have zero eligible source tests, so
their three aggregate metric values are `null`.

## Execution Time

Execution time measures the complete wall-clock duration of a fresh pytest process
running only participant test cases classified as `valid`. It includes Python and
pytest startup, collection, fixture setup, test execution, teardown, and process
exit. It excludes error-rate classification, isolation-file generation, worktree
creation, coverage instrumentation, and mutation testing.

The primary field is `execution_time_seconds`; it is the median of the measured
runs. The raw JSON also preserves every duration as integer nanoseconds and reports
the mean, standard deviation, minimum, maximum, quartiles, interquartile range,
median absolute deviation, and coefficient of variation.

The default protocol performs one untimed validity check, three unreported warm-up
runs, and fifteen measured runs. Every run starts a new Python process. The
collector removes external `PYTEST_ADDOPTS`, fixes `PYTHONHASHSEED=0`, disables the
pytest cache provider, and runs serially. Do not run formal timing collection while
mutation testing, coverage collection, IDE indexing, backups, or other CPU- or
disk-intensive work is active.

The protocol was frozen after a three-participant pilot representing one, five, and
656 valid expanded test cases. Their coefficients of variation were 0.48%, 2.56%,
and 1.28%. Formal collection therefore retains three warm-ups and fifteen measured
runs, with `coefficient_of_variation > 0.05` triggering manual review. Crossing the
threshold does not remove, replace, or automatically rerun any observation.

Collect a single submission with:

```bash
venv/bin/python scripts/collect_execution_time.py \
  tests/task/task.py \
  --repo-root . \
  --python venv/bin/python \
  --timeout 120 \
  --warmups 3 \
  --measurements 15 \
  > execution_time.json
```

If no valid test cases remain, `execution_time_seconds` is unavailable rather than
zero. If a validation, warm-up, or measured run fails, the report preserves the
failure and does not silently replace that observation.

The execution-efficiency denominators use this same median time:

```text
Statement Execution Efficiency = Participant Statement Coverage / Execution Time
Branch Execution Efficiency    = Participant Branch Coverage / Execution Time
Mutation Execution Efficiency  = Mutation Score / Execution Time
```

Mutation execution efficiency uses ordinary execution time on the original SUT,
not the duration of the mutation campaign. Calculate the efficiency ratios only
after coverage and mutation policies are frozen, and retain the component score and
execution time alongside each ratio.

Collect all participant branches later, when the machine is otherwise idle:

```bash
venv/bin/python scripts/collect_all_execution_times.py \
  --baseline origin/experiment-base \
  --output-dir results/execution_time \
  --timeout 120 \
  --warmups 3 \
  --measurements 15
```

For a timing pilot, add `--participants` followed by the fixed representative
participant numbers. Do not choose or replace participants after inspecting timing
results.

Create the focused CSV without rerunning participant tests:

```bash
venv/bin/python scripts/summarize_execution_times.py \
  results/execution_time/collection_manifest.json \
  --output results/execution_time/summary/execution_time.csv
```

## All Participant Branches

Participant submissions use the remote branches `experiment-01` through
`experiment-16`. Participants 13 and 15 did not participate and are recorded as
`not_participated`.

Collect all branches serially with:

```bash
venv/bin/python scripts/metric_collection/collect_all_branches.py \
  --baseline origin/experiment-base \
  --output-dir results/error_rates \
  --timeout 120
```

Coverage and assertion-score collection are enabled by default. The command invokes
`collect_coverage.py` once per participating branch and obtains error-rate, coverage,
and assertion-score JSON from that invocation. Assertion analysis reuses the
error-rate result and does not execute pytest again. Use `--skip-coverage` only for
a faster, error-rate-only diagnostic run:

```bash
venv/bin/python scripts/metric_collection/collect_all_branches.py \
  --baseline origin/experiment-base \
  --output-dir results/error_rates \
  --timeout 120 \
  --skip-coverage
```

The batch collector does not switch the current working tree. It creates a detached
temporary Git worktree for each participant, invokes the configured metric collector
from `pilot-metric`, writes the result, and removes the worktree. This preserves
participant-added test materials and avoids disturbing local uncommitted changes.

Collection is serial to keep execution deterministic and to avoid resource
contention. This is especially important if execution-time metrics are added later.

## Mutation Tool Pilot

The phase-one benchmark compares MutPy, Mutmut, and Cosmic Ray on the same fixed SUT
module and participant test suite. Install each tool in a separate Python 3.11
environment, then run:

```bash
venv/bin/python scripts/metric_collection/benchmark_mutation_tools.py \
  --sut-ref pilot-metric \
  --participant-ref origin/experiment-11 \
  --mutpy-python /path/to/mutpy-venv/bin/python \
  --mutmut-python /path/to/mutmut-venv/bin/python \
  --cosmic-ray-python /path/to/cosmic-ray-venv/bin/python \
  --output-dir results/mutation_score/tool_pilot
```

The script runs each tool twice to verify semantic catalog reproducibility. It writes
`benchmark.json`, `benchmark.csv`, and raw tool logs. The tools use their native
operator sets, so their mutant counts and mutation scores must not be compared as if
they represented the same fault catalog. See
`docs/metric_collection/MUTATION_PILOT.md` for the fixed pilot
setup, observed results, and tool-selection decision.

## Mutation Score

Mutation Score uses Mutmut 3.7.0 under Python 3.11. A researcher-controlled workload
first creates a complete catalog from the common `origin/experiment-base` SUT. The
`specified` layer covers the five assignment requirements; `extended_only` covers
additional boundary and state behavior within the same scope. Catalog generation is
repeated twice and must reproduce the Mutmut name, normalized diff, source location,
workload layer, SUT hash, workload hashes, and catalog hash.

Create the tool environment and the `ruler.py` pilot catalog with:

```bash
python3.11 -m venv .venv-mutmut
.venv-mutmut/bin/python -m pip install 'mutmut==3.7.0' -e '.[testing]'
.venv-mutmut/bin/python scripts/metric_collection/build_mutant_catalog.py \
  --baseline-ref origin/experiment-base \
  --mutmut-python .venv-mutmut/bin/python \
  --only-mutate markdown_it/ruler.py \
  --output-dir results/mutation_score/catalog-pilot
```

The builder assigns a deterministic operator family from each normalized diff.
Existing catalogs can be annotated without changing mutant identity:

```bash
venv/bin/python scripts/metric_collection/classify_mutation_operators.py \
  results/mutation_score/catalog-pilot/mutant_catalog.json \
  --output results/mutation_score/catalog-pilot/classified_catalog.json \
  --review-csv results/mutation_score/catalog-pilot/operator_review.csv
```

### Sampling Protocol

The `specified` layer is sampled once and the frozen sample is shared by every
participant. The smaller `extended_only` layer is included as a census and reported
as a separate exploratory score. Sampling is without replacement and reproducible
from the source catalog hash, strategy, ratio or size, minimum-per-stratum rule, and
seed. It is forbidden to resample per participant or after inspecting participant
scores.

This follows the cost-reduction motivation of Zhang et al.'s operator-based and
random mutant-selection study, but does not copy its Java/Javalanche-specific 5%
choice. This project evaluates 5%, 10%, 20%, 30%, and 50%, twenty fixed seeds, and
five strategies for the specified sampling frame. The extended-only census has
inclusion probability 1 and sampling weight 1. The two layers are never combined as
a primary score, so no subjective cross-layer importance weight is introduced.
`scripts/metric_collection/mutation_sampling_protocol.json` pre-registers the
candidate values and acceptance thresholds. The formal strategy, effective sample
size, and seed must be frozen before full-SUT collection.

The `ruler.py` pilot itself runs all 74 mutants for every participant; sampling is
simulated offline so that the full scores remain the ground truth:

```bash
.venv-mutmut/bin/python scripts/metric_collection/collect_all_mutation_scores.py \
  --catalog results/mutation_score/catalog-pilot/classified_catalog.json \
  --python .venv-mutmut/bin/python \
  --baseline origin/experiment-base \
  --output-dir results/mutation_score/ruler-full \
  --max-children 4 --resume

venv/bin/python scripts/metric_collection/analyze_sampling_pilot.py \
  --catalog results/mutation_score/catalog-pilot/classified_catalog.json \
  --results results/mutation_score/ruler-full/raw \
  --output-dir results/mutation_score/sampling-pilot-specified-plus-extended-census
```

The analysis writes per-run errors, MAE, RMSE, adjusted R², Kendall tau-b,
Spearman rho, ranking changes, cross-seed standard deviation, and sampled/full cost
ratio. A strategy is recommendable only when its specified-layer median absolute
error is at most 0.05, 95th-percentile absolute error is at most 0.07, adjusted R²
is at least 0.95, and both rank correlations are at least 0.90.

The completed 74-mutant pilot collected all 14 participating branches. Under the
current 0.07 P95 threshold, none of the evaluated strategies at target ratios from
5% to 50% is acceptable. The previous function-stratified minimum sample of 30 had
a specified P95 absolute error of 0.0990 and is therefore retained only as historical
pilot evidence, not as an accepted formal sample. Higher ratios must be declared and
evaluated before a formal sample is frozen; the threshold must not be relaxed after
inspecting the new results.

After a strategy passes the revised protocol, create the formal shared sample using
the frozen values rather than the historical example values:

```bash
venv/bin/python scripts/metric_collection/sample_mutant_catalog.py \
  results/mutation_score/catalog/classified_catalog.json \
  --strategy <FROZEN_STRATEGY> \
  --ratio <FROZEN_RATIO> --seed <FROZEN_SEED> \
  --minimum-sample-size 30 --minimum-per-stratum 1 \
  --census-layer extended_only \
  --output-dir results/mutation_score/sampled-catalog
```

Specified function strata can have unequal sampling fractions. Every sampled
specified mutant therefore records `N_h/n_h`; the estimated specified score uses
those weights and includes a finite-population 95% interval. Extended-only mutants
have weight 1 because the layer is complete. Singleton sampled strata receive the
conservative interval [0, 1] rather than a false zero-width interval.

### Participant Collection and Aggregation

Collect the same frozen task-relevant catalog on all branches serially. Participants 13 and 15
are recorded as `not_participated`. Valid-only participant tests must pass the
unmutated baseline; catalog, SUT, workload, and Mutmut hashes must match. Use
`--confirm-kills` when every kill used as global evidence must be independently
rerun. Confirmations are persisted atomically in small batches.

```bash
.venv-mutmut/bin/python scripts/metric_collection/collect_all_mutation_scores.py \
  --catalog results/mutation_score/full-sut/catalog/task_relevant_mutant_catalog.json \
  --python .venv-mutmut/bin/python \
  --baseline origin/experiment-base \
  --output-dir results/mutation_score/full-sut/formal \
  --max-children 4 --timeout-multiplier 5 --timeout-constant 0.5 \
  --timeout-retry-count 1 --confirmation-batch-size 25 \
  --resume --confirm-kills

venv/bin/python scripts/metric_collection/aggregate_mutant_outcomes.py \
  --catalog results/mutation_score/full-sut/catalog/task_relevant_mutant_catalog.json \
  --results results/mutation_score/full-sut/formal/raw \
  --manifest results/mutation_score/full-sut/formal/collection_manifest.json \
  --reliable-kill-evidence results/mutation_score/full-sut/formal/reliable_kill_evidence.json \
  --output-dir results/mutation_score/full-sut/formal/global \
  --require-confirmed-kills
```

Mutation resume uses three separate identities. `catalog_hash` identifies the
frozen mutants, while `execution_context_hash` covers the catalog and SUT together
with the participant valid-only test artifact, test materials, Python, Mutmut, and
the valid-only isolation protocol. `execution_policy_hash` covers timeout and retry
settings, kill confirmation, and duplicate/equivalent handling. `max_children` is
performance-only and does not invalidate cached results.

Changing only timeout settings no longer clears confirmed kills. Increasing the
timeout reuses completed statuses and reruns prior timeouts. Decreasing it reuses
rows whose recorded duration fits the new limit and reruns rows that exceed the
limit or lack timing. Global reliable-kill evidence remains valid independently of
the participant's status under the current timeout policy. Each evidence record is
stored by mutant and execution context in `reliable_kill_evidence.json`; the legacy
`confirmed_kills.json` is retained as historical input and is never reset. Replaced
participant raw results are content-addressed under `history/`.

Legacy rows without timing metadata remain reusable during ordinary `--resume`.
Timing is collected only when explicitly requested with
`--backfill-missing-durations`. This maintenance mode reruns matching-context rows
whose execution duration, estimated duration, or Mutmut exit code is missing. A
`no_tests` result has no actual test execution duration by definition, so it is
complete when its estimated duration and exit code are present. The mode does not
change `execution_policy_hash`, and existing reliable kills are reused rather than
reconfirmed.

Every participant raw result reports `reused_results`,
`reused_confirmed_kills`, `rerun_previous_timeouts`,
`rerun_policy_affected`, `new_kills_to_confirm`, and
`invalidated_context_mismatch` under `cache_statistics`. Backfill runs additionally
report `backfill_missing_durations` and `rerun_missing_durations`.

A reliable kill requires successful collection, a passing valid-only baseline, no
infrastructure error, matching catalog/SUT/workload hashes, an explicit Mutmut
`killed` result, and—when required—a successful confirmation rerun. Flaky kills are
never global evidence. Any reliable kill makes the mutant `auto_non_equivalent` and
removes it from equivalent review, while each participant's original killed or
survived result remains unchanged. Mutants never reliably killed become one blinded
`review_candidate`; timeout-only cases become `execution_unresolved`.

In the completed `ruler.py` pilot, 52 of 74 mutants had at least one reliable kill.
The naive participant survivor/timeout union contained all 74 mutants, whereas the
never-killed protocol produced 22 review candidates and no execution-unresolved
mutants, reducing manual equivalent review by 52 mutants (70.27%).

For the fixed 33-mutant pilot sample, 21 mutants had a reliable kill and 12 were
never killed. Offline sampled participant results are derived from the already
completed full matrix rather than rerunning Mutmut:

```bash
venv/bin/python scripts/metric_collection/derive_sampled_mutation_results.py \
  --catalog results/mutation_score/sampled-catalog/sampled_mutant_catalog.json \
  --full-results results/mutation_score/ruler-full/raw \
  --full-manifest results/mutation_score/ruler-full/collection_manifest.json \
  --output-dir results/mutation_score/sampled-pilot
```

### Equivalent-Mutant Review

`review_candidates.csv` intentionally hides participant identities, scores, and kill
frequency. Two reviewers independently choose `non_equivalent`,
`confirmed_equivalent`, `duplicate`, or `unresolved` and provide reasons. Agreement,
Cohen's kappa, disagreements, adjudicated counts, and a review-artifact hash are
recorded. Only `confirmed_equivalent` is always excluded. `unresolved` remains in
the denominator. Duplicate exclusion is off by default and must be enabled
explicitly as a sensitivity policy.

The pilot also retains an AI-assisted preliminary review before and after file. It
classifies 10 candidates as non-equivalent, 1 as confirmed equivalent, and 1 as a
duplicate. This is not represented as two independent reviewers and must not be used
to report Cohen's kappa. A human should independently verify at least every proposed
equivalent exclusion before the formal analysis.

Prepare an inspectable, disposable worktree for one mutant with:

```bash
.venv-mutmut/bin/python scripts/metric_collection/prepare_mutation_review_workspace.py prepare \
  --catalog results/mutation_score/sampled-catalog/sampled_mutant_catalog.json \
  --mutant-id <MUTANT_ID> --mutmut-python .venv-mutmut/bin/python \
  --target /tmp/markdown-it-mutant-review
```

The generated `MUTATION_REVIEW.md` provides `show`, `tests-for-mutant`, rerun, and
`apply` commands. `apply` is permitted only inside that worktree; do not commit it.
Use the printed cleanup command afterwards.

Apply completed reviews to a new catalog and produce final participant scores:

```bash
venv/bin/python scripts/metric_collection/apply_global_mutant_reviews.py \
  --catalog results/mutation_score/sampled-catalog/sampled_mutant_catalog.json \
  --reviewer-1 results/mutation_score/formal/reviewer_1.csv \
  --reviewer-2 results/mutation_score/formal/reviewer_2.csv \
  --adjudication results/mutation_score/formal/adjudication.csv \
  --output-catalog results/mutation_score/formal/reviewed_catalog.json \
  --output-summary results/mutation_score/formal/review_summary.json \
  --output-decisions results/mutation_score/formal/review_decisions.csv

venv/bin/python scripts/metric_collection/summarize_mutation_scores.py \
  results/mutation_score/formal/collection_manifest.json \
  --reviewed-catalog results/mutation_score/formal/reviewed_catalog.json \
  --raw-dir results/mutation_score/formal/raw \
  --output results/mutation_score/formal/mutation_scores.csv
```

For each layer, timeout is reported and excluded. Confirmed equivalent mutants are
removed globally. The unweighted descriptive score and weighted estimate are:

```text
eligible = killed + survived + no_tests - confirmed_equivalent
MS = eligible_killed / eligible
EstimatedKilled = sum_h N_h * killed_h / n_h
EstimatedMS = weighted killed / weighted eligible
```

Specified and extended-only scores remain separate primary outcomes; combined score
is a sensitivity result. A participant with no valid tests receives zero through
`no_tests`; collection or environment failure remains unavailable rather than zero.

## Batch Output

Successful collection creates:

```text
results/error_rates/
├── collection_manifest.json
└── raw/
    ├── experiment-01.json
    ├── experiment-02.json
    └── ...
```

Test Smell uses a separate result tree so it can reuse the frozen Error Rate data
without rerunning Assertion Score or any participant test:

```text
results/test_smells/
├── collection_manifest.json
├── raw/
│   └── experiment-XX.json
├── summary/
│   └── test_smell.csv
└── tools/
    └── experiment-XX/
        ├── pytest-smell.csv
        ├── pytest-smell.stdout.txt
        ├── pytest-smell.stderr.txt
        ├── tempy.json
        ├── tempy.stdout.txt
        └── tempy.stderr.txt
```

Each Error Rate raw file contains:

- participant ID and branch;
- participant commit;
- baseline ref and commit;
- full suite-level and case-level metrics;
- participant-only and all-tests-combined statement and branch coverage;
- assertion score and per-node assertion evidence;
- detailed classification for every expanded pytest item.

`collection_manifest.json` records the collector and baseline commits, the Python
executable, changed files, collection status, output file, and a compact metric
summary for every participant number from 1 to 16.

Possible participant statuses include:

- `collected`: metrics were collected and validated.
- `not_participated`: participant 13 or 15 did not participate.
- `missing_branch`: the expected remote branch is unavailable.
- `no_submission`: the branch has no commit after the experiment baseline.
- `missing_task_file`: `tests/task/task.py` is absent.
- `incompatible_history`: the branch is not based on the configured baseline.
- `invalid_sut_modification`: the branch modifies `markdown_it/`, `pyproject.toml`,
  or `tox.ini`; collection is skipped to protect experimental consistency.
- `collection_timeout`: collection exceeded the configured time limit.
- `collection_failed` or `invalid_collector_output`: the collector failed or did
  not return valid metrics.

The command exits with code `0` only when all participating branches are collected
and participants 13 and 15 are recorded as `not_participated`. Other statuses are
preserved in the manifest and produce exit code `1` so that missing or invalid data
cannot be overlooked.

## Summary CSV Files

Convert the collection manifest into analysis-ready CSV files without rerunning the
participant tests:

```bash
venv/bin/python scripts/metric_collection/summarize_metrics.py \
  results/error_rates/collection_manifest.json \
  --output-dir results
```

This creates:

```text
results/
├── assertion_score/
│   └── assertion_score.csv
├── coverage/
│   └── coverage.csv
└── error_rates/
    ├── collection_manifest.json
    ├── error_rates.csv
    └── raw/
```

CSV does not support workbook tabs, so each metric family is written to a separate,
focused table. All tables use only `participant_number` and `status` as common
identity columns. `error_rates.csv` contains suite collectability, generated-test
counts, classification counts, and the three error rates. `coverage.csv` contains
the numbers of valid and invalid participant tests together with participant-only
and all-tests-combined statement and branch coverage rates.

`assertion_score.csv` contains one row per participant and one column for each of
the five fixed test functions. Every test-function cell contains exactly one of
`invalid`, `non_trivial`, `trivial`, `assertionless`, or `uncertain`. The final
`assertion_score` column contains the participant-level score. The table also keeps
the total source-test count and the number of tests in each of the five
classifications. Each function also has adjacent `validity`,
`valid_instance_count`, `total_instance_count`, and `generated_nodeids` columns for
traceability. Generate it from a manifest collected by the default cross-branch
command without `--skip-coverage`.

`test_smell.csv` contains eligibility counts, confirmed and uncertain pair counts,
per-smell counts and rates, Smelly Test Rate, Mean Smells per Test, and normalized
Test Smell Density. The corresponding raw JSON retains all eligible
source-test/smell decisions with line evidence and reasons, plus invalid source
records, validity counts, and external-tool agreement or disagreement.

The Assertion Score result files have been regenerated under the source-validity
protocol. The saved dataset contains no `partially_valid` source function, and the
regeneration did not alter any participant-level Assertion Score value. Raw JSON,
the collection manifest, and `assertion_score.csv` now retain the validity schema
and collector commit provenance. The Error Rate, Coverage, Mutation Score,
Execution Time, and Test Smell item or execution-set definitions are unchanged.

Participants who did not participate and branches that could not be collected
remain in all three tables, but their metric cells are empty rather than zero.
Select rows with `status` equal to `collected` before calculating descriptive
statistics.

Provenance fields such as branch names, commits, changed files, output paths, and
collection timestamps remain in `collection_manifest.json` and raw JSON instead of
being repeated in the analysis tables. When a new metric family is implemented, it
must receive its own focused CSV file with the same two common columns rather than
adding more columns to the existing tables.

All rate columns are numeric proportions from `0.000000` to `1.000000`, not
percentages. For example, `0.250000` represents 25%. The summarizer recomputes rates
from the counts and rejects a manifest when the four classification counts do not
sum to `total_generated_test_cases`.

## Reproducibility

Do not manually edit generated raw JSON files. Re-run the collector instead. Keep
the following information with any dataset used for analysis:

- `collection_manifest.json`;
- the `pilot-metric` collector commit;
- the `experiment-base` commit;
- participant branch commits;
- Python and dependency versions used for collection.

Do not compare branches evaluated against different baseline or collector versions.
