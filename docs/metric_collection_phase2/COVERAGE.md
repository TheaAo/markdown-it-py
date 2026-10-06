# Phase 2 coverage collection

## Inputs and reuse

`scripts/metric_collection_phase2/collect_coverage.py` consumes the frozen
`results/phase2/error_rates/collection_manifest.json` and per-participant raw reports.
It uses their exact valid pytest node IDs, participant commits and common baseline
commit. No branch tips are refreshed and no error classification is repeated.
All source/material hashes recorded by error-rate collection are verified before
execution. SUT and configuration must still match the common baseline.

The Phase 1 `_run_coverage` engine and coverage JSON metric parser are reused.
Tests execute at their original paths with original support code and materials.
The collector measures the whole `markdown_it` package, with branch measurement
enabled. A pytest hook verifies the package was imported from the exported
snapshot and records Python, pytest and coverage.py versions.

## Scopes and units

- `participant_tests_only`: all valid participant instances, including relocated
  and additional tests. Invalid instances are excluded. Missing unimplemented
  functions have no instance and remain separately recorded.
- `project_tests_only`: pristine baseline `tests/`, excluding `tests/task/`.
- `all_tests_combined`: union of the project's and participant's executed source
  lines and branch arcs, using `coverage combine`. These two suites run separately
  against identical SUT code. This measures coverage union, not fixture interaction
  or execution time of a joint pytest session. It avoids incorporating participant
  edits into the pristine project test suite. Relative coverage paths let data from
  different exported snapshot directories identify the same SUT files.
- Maintenance, new-generation, retained-legacy and additional test groups are
  also measured independently. Relocated `tests/test_cli.py::test_non_utf8` belongs
  to maintenance. Empty groups have unavailable coverage. Group scores cannot be
  added because their covered lines/arcs overlap.

Raw records and coverage JSON include integer covered/total counts. Summary CSV
columns use fractions between 0 and 1, rounded to six decimal places, as in Phase 1.
Raw `percent` values use the 0–100 scale. No Phase 2 group column is needed because
all participants used AI.

## Reproduce

```bash
.tox/py311/bin/python scripts/metric_collection_phase2/collect_coverage.py \
  --python .tox/py311/bin/python \
  --output-dir results/phase2/coverage
```

The interpreter needs the project test dependencies and coverage.py. Existing
output directories are protected: use a new output directory for a subsequent run.
Evidence retains coverage databases, full coverage JSON, pytest JUnit reports,
and SUT/tool provenance. The manifest records input manifest and collector hashes;
raw participant records also record their source error-rate report hashes.
Collection failures leave unavailable summary metrics and preserved evidence.

## Collection on 2026-10-05

All eight participants were collected at the same commits as error-rate collection.
The 58 valid instances all passed again under coverage. The pristine project suite
contains 326 passing tests. Python 3.11.6, pytest 9.1.1 and coverage.py 7.16.2 were used.
Every measured scope has the same SUT denominator: 3,622 statements and 1,394 branches.

Participant statement coverage ranges from 70.6516% to 70.9277%; participant branch
coverage ranges from 60.4735% to 60.6887%. Combined statement coverage ranges from
95.7758% to 95.8586%; combined branch coverage is 91.8938% for all participants.
The baseline project tests alone cover 93.9260% of statements and 87.6614% of branches.

The collected combined JSON was verified per source file: its executed lines and
branch arcs are exactly the set unions of baseline and participant coverage.
The missing `test_parse_fail` for participant 08 remains an omission record, rather
than an executed instance. Differences from Phase 1 use different baseline SUT
denominators and should be interpreted accordingly.
