# Experiment Metrics Collection

This document describes how to collect error-rate, coverage, and assertion-score
metrics from participant test submissions.

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
  --repo-root . \
  --python venv/bin/python \
  --timeout 120 \
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

Coverage, mutation, assertion, and maintainability metrics should subsequently be
computed only from tests classified as `valid`.

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
back into their source function. A missing function, or a function with any
instance not classified as `valid` by Error Rate, is `invalid` and excluded from
the denominator. When no eligible source tests remain, the score is unavailable
(`null`) rather than zero.

The collector performs conservative static analysis over each submitted test and
its local helpers. It tracks imported `markdown_it` symbols, assignments, returned
values, method calls, simple helper transformations, `pytest.raises` and
`pytest.warns` contexts, assertion methods, and captured output. Each valid test is
classified into exactly one category:

- `invalid`: at least one generated parameter instance did not pass Error Rate;
- `non_trivial`: at least one oracle has a detected backward dependency on the SUT;
- `trivial`: all detected assertions are constants, self-comparisons, generic
  type/`None` checks, or otherwise unrelated to the SUT;
- `assertionless`: no supported assertion or exception oracle is present;
- `uncertain`: the SUT is executed or an oracle is present, but the dependency
  cannot be resolved confidently by the static analysis.

The five classifications are mutually exclusive. `eligible source tests` equals
`non_trivial + trivial + assertionless + uncertain`; `invalid` is excluded. The
reported score is a conservative lower bound because `uncertain` remains in the
denominator but not the numerator. Raw JSON records each source test, its generated
node IDs, classification, source line, oracle type, and reason. Review all
`uncertain` cases manually before final statistical analysis.

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

Each raw file contains:

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
classifications. Generate it from a manifest collected by the default cross-branch
command without `--skip-coverage`.

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
