# Experiment Metrics Collection

This document describes how to collect syntax, runtime, and function error-rate
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

The batch collector does not switch the current working tree. It creates a detached
temporary Git worktree for each participant, invokes the error-rate collector from
`pilot-metric`, writes the result, and removes the worktree. This preserves
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

## Reproducibility

Do not manually edit generated raw JSON files. Re-run the collector instead. Keep
the following information with any dataset used for analysis:

- `collection_manifest.json`;
- the `pilot-metric` collector commit;
- the `experiment-base` commit;
- participant branch commits;
- Python and dependency versions used for collection.

Do not compare branches evaluated against different baseline or collector versions.
