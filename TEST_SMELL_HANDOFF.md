# Test Smell Metric Implementation Handoff

## Read first

The aligned pilot is complete. Read `TEST_SMELL_PILOT.md` before implementation.
Do not revert to the earlier four-smell comparison or describe its F1 values as
evidence for the formal catalog.

Work only in the `pilot-metric-test-smell` worktree at
`/Users/ruoyur/Code/Chalmers/MasterThesis/markdown-it-py-test-smell`. The main
worktree contains unrelated Mutation Score changes and must remain untouched.

Use Conventional Commits without emoji if committing, for example:

```text
feat(metrics): add test smell collector
```

## Fixed protocol

Formal smells:

1. Assertion Roulette;
2. Magic Number Test;
3. Unknown Test;
4. Conditional Test Logic;
5. Eager Test;
6. Duplicate Assert;
7. Exception Handling.

Test Maverick is excluded because the five target tests are function-style pytest
tests without a uniform class-level setup model. This is a protocol decision, not a
consequence of tool availability.

Analyze only `test_file`, `test_spec`, `test_core_after`, `test_parse_fail`, and
`test_non_utf8`. The unit is a source function, not a generated parameter instance.

Validity aggregation:

- `fully_valid`: all generated instances are valid;
- `partially_valid`: at least one, but not all, is valid;
- `invalid`: no generated instance is valid.

The first two states are eligible for source-level Assertion Score and Test Smell
analysis. Preserve `valid_instance_count`, `total_instance_count`, and `validity`.

## Detector architecture

The AST engine is the final detector and must scan every eligible source test for
all seven smells. Never limit AST evaluation to the union of external tool alerts.

External tools provide evidence:

- pytest-smell `1.0.5`: reference evidence for the seven categories;
- TEMPY `4c945d121d645b52fefb8f1b4f3e6caeec7c9095`: cross-check only
  Conditional Test Logic, Unknown Test, and Exception Handling;
- PyNose: excluded because official headless builds are not reproducible.

Do not vote or average tool outputs. Store agreement and disagreement alongside the
AST decision.

## Frozen rules

- Assertion Roulette: two or more `assert` nodes without a message. Pytest
  rewriting changes severity, not the occurrence definition.
- Magic Number Test: numeric literal in an assertion expression, excluding bool,
  `-1`, `0`, `1`, indices, named constants, parameter data, and required exit codes.
- Unknown Test: no reachable supported oracle. Recognize `assert`, pytest exception
  and warning contexts, `pytest.fail`, unittest assertions, regression checks, and
  visible local-helper assertions.
- Conditional Test Logic: include statement-level `if`, `for`, `async for`,
  `while`, and `match`; exclude ternaries and comprehensions.
- Eager Test: at least two distinct `markdown_it` production result methods feed
  independent oracles. Repeated use of one method and configuration calls do not
  count.
- Duplicate Assert: at least two assertion conditions with identical normalized
  AST, ignoring formatting, location, and message.
- Exception Handling: manual `try/except`; exclude framework exception oracles and
  cleanup-only `try/finally`.

Only Unknown Test and Eager Test follow file-local helpers for oracle/production
evidence. Shared fixtures are not copied to every test. Mark unresolved cases
`uncertain`.

## Pilot result that constrains implementation

The 42-function benchmark contains six cases per formal smell and 22 positive
pairs. It executes as 44 passing pytest instances.

- AST rule engine: TP 22, FP 0, FN 0 on the protocol regression corpus;
- pytest-smell: TP 16, FP 9, FN 6, F1 68.1%;
- TEMPY, only across three supported smells: TP 9, FP 5, FN 1, F1 75.0%.

pytest-smell has zero recall for the three Eager Test cases and only 33.3% recall
for Duplicate Assert. This is direct evidence that external candidates cannot gate
the AST scan. See `TEST_SMELL_PILOT.md` for per-smell results and limitations.

## Implemented workflow

The implementation is complete. `collect_test_smells.py` provides the reusable
source-level collector and rule version `1.0.0`. It consumes saved Error Rate JSON,
builds isolated static input, runs every AST rule independently, and records all
35 decisions with line evidence, reasons, and external-tool flags.

`collect_test_smells_all_branches.py` reads the existing Error Rate manifest and
the participant source at its recorded Git commit. It intentionally remains a
separate batch command: this permits Test Smell collection without rerunning Error
Rate, Coverage, or Assertion Score. `summarize_test_smells.py` writes the separate
analysis-ready CSV required by the metric-family output design.

pytest-smell raw CSV/stdout/stderr and normalized TEMPY JSON/stdout/stderr are
retained for every applicable participant. Tool statuses distinguish completed,
failed, not configured, and not run because no source test is eligible.

## Required final metrics

```text
Smelly Test Rate
= eligible source tests with at least one confirmed smell / eligible source tests

Mean Smells per Test
= confirmed (source test, smell type) pairs / eligible source tests

Test Smell Density
= confirmed pairs / (eligible source tests * 7 formal smell types)
```

One smell type counts at most once per source test. Two different smells count as
two pairs. Smelly Test Rate and Test Smell Density are bounded in `[0, 1]`; Mean
Smells per Test is bounded in `[0, 7]`. With no eligible tests, all three values are
`null`. Also report per-smell counts and the number of `uncertain` pairs.

## Validation and change control

- Keep all 42 benchmark source functions and their gold labels passing.
- Add collector-level tests for full, partial, and zero-valid parameterization.
- Verify strings, comments, ternaries, comprehensions, exit codes, local helpers,
  `pytest.raises`, and cleanup-only `try/finally` boundaries.
- Run all `tests/metric_collection`, tox, and pre-commit before committing.
- Freeze the rule version before participant-wide collection.
- After freezing, manually audit a documented sample that includes both detected
  and no-detection tests. Do not tune rules silently.
- If the audit reveals a systematic error, create a new rule version and rerun all
  participants once. Never patch selected participant results.

## Current files

- `TEST_SMELL_PILOT.md`: protocol, executed results, interpretation;
- `TEST_SMELL_AUDIT.md`: post-freeze participant audit and aggregate check;
- `scripts/detect_test_smells_ast.py`: initial complete AST rule engine;
- `scripts/evaluate_test_smell_pilot.py`: supported-scope and per-smell metrics;
- `scripts/collect_test_smells.py`: source-level formal collector;
- `scripts/collect_test_smells_all_branches.py`: Error Rate-reusing batch collector;
- `scripts/summarize_test_smells.py`: focused CSV generator;
- `tests/metric_collection/fixtures/test_smell_pilot/test_pilot_cases.py`: 42 cases;
- `tests/metric_collection/fixtures/test_smell_pilot/gold_labels.json`: oracle;
- `tests/metric_collection/fixtures/test_smell_pilot/observations.json`: recorded
  outputs and versions;
- `tests/metric_collection/test_evaluate_test_smell_pilot.py`: regression checks;
- `results/test_smells/`: completed participant raw data, tool evidence, manifest,
  and summary CSV.

The completed participant collection contains 50 eligible source tests, 18 smelly
tests, 22 confirmed pairs, and zero uncertain pairs. The aggregate Smelly Test Rate
is `0.36`, Mean Smells per Test is `0.44`, and normalized Test Smell Density is
`0.062857`.

Reproduce the formal collection and focused CSV with:

```bash
python3 scripts/collect_test_smells_all_branches.py \
  --error-manifest results/error_rates/collection_manifest.json \
  --output-dir results/test_smells \
  --pytest-smell /path/to/pytest-smell \
  --tempy-root /path/to/TEMPY \
  --python /path/to/python \
  --timeout 60

python3 scripts/summarize_test_smells.py
```

The AST benchmark result is protocol conformance, not an unbiased estimate of
accuracy on unseen participant code. Keep that distinction explicit in the thesis.
