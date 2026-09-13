# Experiment Metrics Collection

This document describes how to collect error-rate, coverage, assertion-score,
test-smell, and execution-time metrics from participant test submissions.

Test Smell research documents:

- [TEST_SMELL_PILOT.md](TEST_SMELL_PILOT.md): pilot evidence and tool choice;
- [TEST_SMELL_HANDOFF.md](TEST_SMELL_HANDOFF.md): implementation handoff.
- [TEST_SMELL_AUDIT.md](TEST_SMELL_AUDIT.md): frozen-rule participant audit.

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

## Single Submission

Collect one test file with:

```bash
venv/bin/python scripts/collect_error_rates.py \
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
venv/bin/python scripts/collect_coverage.py \
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
venv/bin/python scripts/collect_assertion_score.py \
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
venv/bin/python scripts/collect_all_branches.py \
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
venv/bin/python scripts/collect_all_branches.py \
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
venv/bin/python scripts/summarize_metrics.py \
  results/error_rates/collection_manifest.json \
  --output-dir results/error_rates/summary
```

This creates:

```text
results/error_rates/summary/
├── assertion_score.csv
├── error_rates.csv
└── coverage.csv
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

The existing Assertion Score result files were not regenerated during Test Smell
collection. Because the current protocol admits `partially_valid` source tests,
the owning workflow must eventually regenerate Assertion Score to add the new
validity provenance before a combined final dataset is frozen. The saved dataset
contains no partially-valid source function, so this protocol change does not alter
any existing Assertion Score value. It also does not invalidate the saved Error
Rate, Coverage, or Test Smell results.

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
