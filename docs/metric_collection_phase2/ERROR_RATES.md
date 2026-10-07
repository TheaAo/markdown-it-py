# Phase 2 Error Rate

Current status (2026-10-07): all eight participants are collected, with 58 valid
pytest instances and zero classified errors. Participant 08's relocated non-UTF8
test is included; its unimplemented `test_parse_fail` is a separately recorded
omission. Earlier dated collections below are historical evidence. See
[collection status](COLLECTION_STATUS.md).


## Scope and execution

The cohort is 02, 03, 04, 05, 07, 08, 09 and 12, all using Copilot. Only
`origin/experiment-xx-phase2` branches are accepted. Branch tips and the common
`origin/experiment-base-phase2` SUT are resolved to immutable commits before tests
run. Changes to `markdown_it/`, `pyproject.toml` or `tox.ini` prevent collection.

The collector exports each commit into a temporary directory with `git archive`.
It runs submitted test files under `tests/task/` together. It also compares Python
files elsewhere under `tests/` with the frozen baseline and selects participant-added
or changed top-level `test_*` functions individually; unchanged upstream tests are
excluded. Selected external functions and their source hashes are recorded. All
actual relative paths, materials and support code remain intact. It does not repair participant
paths or assertions. A pytest hook checks that `markdown_it` was imported from
that snapshot, rather than the installed package in the collection environment.

The Phase 1 pytest report hook is reused for syntax/runtime/function/valid
classification; the count and ratio implementation is reused too. Phase 2 adds
multi-file execution, source-file identity, cohort selection and provenance.
The original Phase 1 collector is unchanged by this implementation.

## Counting and missing data

The summary CSV omits the redundant `phase2_group` column because all eight
participants used AI. The group is retained in raw provenance and manifests.
The 2026-10-05 CSV export removed this column without changing execution evidence;
historical snapshots remain unchanged.

- Each executed pytest instance is one case, including parametrized instances.
  File path plus pytest node ID distinguishes functions with identical names.
- Assertion failures and explicit pytest failures are function errors. Other
  exceptions, setup/teardown failures and skipped tests are runtime errors, following
  the Phase 1 convention.
- If a module cannot be collected, each recoverable declared source test in that
  module receives a syntax or runtime error. These cases are explicitly labelled
  `source_function_collection_fallback`; parametrized instances cannot be enumerated
  in this situation. Other collectable files still execute.
- Missing expected functions are recorded separately. They do not become passing
  tests or fabricated errors. An empty suite has unavailable rates, rather than zero.
- The known relocation of `test_non_utf8` to `tests/test_cli.py` satisfies that
  expected function when the participant submitted it there. A commented declaration
  without a body remains missing/unimplemented; it has no executable pytest instance.
- A missing branch or collection infrastructure failure produces unavailable
  metrics. A timeout is an infrastructure failure, not an inferred participant error.

The denominator is the number of classified submitted cases. Each error rate is
its error count divided by that denominator. `overall_error_rate` is the combined
syntax, runtime and function error count divided by the denominator. Passing tests
are executable-valid evidence; task completeness and assertion quality are separate
questions and are not established by an error rate of zero.

## Reproduce

Use an interpreter with the project's testing and linkify dependencies. For example,
after creating the repository's `py311` tox environment:

```bash
.tox/py311/bin/python scripts/metric_collection_phase2/collect_error_rates.py \
  --python .tox/py311/bin/python \
  --output-dir results/phase2/error_rates
```

The collector never fetches implicitly. Refresh refs explicitly before a new run.
Existing manifests are protected from overwrite; use a new output directory for
subsequent runs and retain the previous snapshot as history.

Outputs are the collection manifest, per-participant raw JSON, a CSV summary,
pytest JSON evidence and complete pytest output. Raw JSON includes source/material
SHA-256 hashes, valid node IDs, missing expected functions, per-file counts and
SUT import provenance. The manifest records collector source hashes in addition
to Git HEAD because collector development may be uncommitted.

## Initial collection on 2026-10-04

Seven standard branches were collected. Participants 02, 03, 04, 05, 07 and 12
each have seven valid tests and zero classified errors. Participant 08 has two
submitted tests, both runtime errors caused by `FileNotFoundError`: their code
still refers to `tests/task/materials/` after the directory migration. Five expected
functions are absent, including the two fence tests. Its runtime error rate is 1.

After refreshing origin, standard branch `experiment-09-phase2` was not available.
The similarly spelled `experimen-09-phase2` was deliberately not substituted.
Participant 09 is represented as `missing_branch`, with blank summary metrics,
pending confirmation of the standard branch. This is a partial cohort collection,
not a completed eight-person dataset.

## Recollection on 2026-10-04

After the researcher updated participant 08 and supplied the standard participant
09 branch, all eight standard branches were collected again. The collector and
interpreter were unchanged. Participant 08's commit is
`3716b54f5db80f79364d900d529d6e44543b1ff9`; participant 09's commit is
`0447bbf695fcf909a221322f59a919e5ecd9ce23`. The other six commits are unchanged.

The historical task-directory-only recollection contained 57 executed pytest
instances, all valid, with zero syntax, runtime and function errors. Seven
participants have seven instances each; participant 09 has eight. Participant 08
now has three legacy tests and four new-file tests, including two additional
fence checks. Its expected `test_parse_fail` and `test_non_utf8` functions remain
absent from `tests/task/phase1/task.py`. Missing functions are recorded separately
and do not change the error-rate denominator.

The prior partial collection was moved without changing any file contents to
`results/phase2/error_rates_history/20261004T200617050523Z/`. That recollection
was checked against their frozen Git artifacts and collector hashes before
replacing the active dataset.

## External-file scope correction on 2026-10-04

The researcher identified participant 08's added `tests/test_cli.py::test_non_utf8`.
The preceding task-directory-only run omitted this function. The collector now
selects added/changed top-level tests outside that directory by comparison with the
same frozen baseline. All eight participants were rerun at the same commits.

The corrected active dataset has 58 executed instances, all valid. Participants
08 and 09 each have eight; the remaining six have seven. Participant 09 submitted
an extra `tests/task/phase1/task.py::test_parse`. Participant 08 submitted two
extra fence checks (`test_make_fence_rule_callable`, `test_default_fence_exists`)
and six of the seven named expected functions, including the relocated non-UTF8
test. Its `test_parse_fail` consists only of a commented declaration without a
test body; that declaration was also commented in its frozen Phase 1 submission.
It is retained in `missing_expected_tests` and is not classified as an execution
error. Expected-function presence does not establish assertion quality or full
requirement satisfaction.

For analysis, report executable error rates alongside expected-task presence or
completion assessment. Extra passing tests must not compensate for omitted required
tasks. Incorporating omissions into a new combined failure metric would change the
metric definition and must be separately named and documented. No such change is
made here. The preceding 57-instance dataset is retained unchanged in
`results/phase2/error_rates_history/`.
