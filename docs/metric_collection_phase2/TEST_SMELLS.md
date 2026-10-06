# Phase 2 Test Smell Density

## Scope and method

Collection runs on branch `pilot-metric-phase2-maintainability`, created directly
from `pilot-metric-phase2` at `56852ac`. All eight participants are included:
02, 03, 04, 05, 07, 08, 09 and 12. All used Copilot in Phase 2.

The collector consumes the frozen Phase 2 error-rate manifest, validates its
participant and baseline commits against raw records, exports immutable Git
snapshots, and verifies source/material SHA-256 hashes before analysis. It does
not execute, relocate, rewrite or repair participant tests. Only declared
participant functions in the error-rate scope are analyzed, including the
participant-selected CLI function for 08 and additional functions for 08/09.
Missing required tests remain documented in raw evidence rather than being
invented as submitted tests.

The Phase 1 AST engine and rule version `1.0.0` are unchanged. The existing
Phase 1 collector now accepts an optional per-file function list; its default
five-function scope and scoring behavior are unchanged. Phase 2 orchestrates
that collector, retaining `(source_file, source_function)` identities instead of
combining files or conflating equal function names.

The seven formal categories are Assertion Roulette, Magic Number Test, Unknown
Test, Conditional Test Logic, Eager Test, Duplicate Assert and Exception Handling.
One category counts at most once per eligible source function. Eligibility means
at least one pytest instance was previously classified valid; partial validity
remains visible and parameterization does not expand the denominator.

```text
Test Smell Density   = confirmed pairs / (eligible source functions * 7)
Mean Smells per Test = confirmed pairs / eligible source functions
Smelly Test Rate     = functions with >= 1 confirmed smell / eligible functions
```

Uncertain pairs are reported separately and excluded from the numerator. With
zero eligible functions, ratios are null/blank rather than zero. Cohort summaries
pool counts and denominators, rather than averaging participant percentages.

The old pytest-smell 1.0.5 and TEMPY installations are no longer available at the
Phase 1 manifest's temporary paths. They were auxiliary evidence, not the formal
decision engine. This run explicitly records them as not configured; the frozen
AST decisions reproduce the formal Phase 1 results without those installations.

## Results

| Participant | Eligible source functions | Confirmed pairs | Test Smell Density |
| --- | ---: | ---: | ---: |
| 02 | 7 | 5 | 0.102041 |
| 03 | 7 | 4 | 0.081633 |
| 04 | 7 | 5 | 0.102041 |
| 05 | 7 | 5 | 0.102041 |
| 07 | 7 | 6 | 0.122449 |
| 08 | 8 | 7 | 0.125000 |
| 09 | 8 | 4 | 0.071429 |
| 12 | 7 | 6 | 0.122449 |

All 58 submitted source functions were eligible. Forty functions contain at least
one confirmed smell, and there are 42 confirmed pairs and zero uncertain pairs.
The pooled density is `42 / (58 * 7) = 0.10344827586206896`.

| Scope | Eligible functions | Confirmed pairs | Pooled density |
| --- | ---: | ---: | ---: |
| Full Phase 2 suite | 58 | 42 | 0.103448 |
| Maintenance (four required old-test tasks) | 32 | 24 | 0.107143 |
| New generation (fence after/at) | 16 | 17 | 0.151786 |
| Retained legacy (`test_parse_fail`) | 7 | 1 | 0.020408 |
| Additional submitted tests | 3 | 0 | 0.000000 |
| Legacy task scope (maintenance + retained legacy) | 39 | 25 | 0.091575 |

Confirmed pairs by category: Assertion Roulette 31, Conditional Test Logic 9,
Duplicate Assert 1, Exception Handling 1; the other three categories have zero.

The main CSV retains the Phase 1 column schema and six-decimal export precision.
Task-scope CSVs and aggregate JSON are supplemental. They distinguish maintenance
from generation and preserve changed suite composition. The legacy task scope is
closer to the Phase 1 tasks, but missing tests and changed requirements still
limit direct interpretation of a before/after difference. No claim of an AI
treatment effect follows from this all-AI second phase.

## Audit and interpretation

All 42 confirmed pairs were checked against their immutable source lines and the
frozen rules. Representative no-detection cases were also inspected:

- 03 `test_core_after`: one assertion, so no Assertion Roulette.
- 03 `test_parse_fail`: `pytest.raises` is a supported oracle and is not manual
  exception handling; required exit code 1 is exempt from Magic Number Test.
- 08 additional callable tests: assertion messages and no repeated bare asserts.
- 09 `test_core_after`: one recorded-output assertion, no statement-level branch.
- 09 additional `test_parse`: required exit code 0 remains exempt.

The audit confirmed protocol conformance. No rules or individual classifications
were changed. This is a collection-workflow audit, not independent blinded
validation of real-world maintainability.

Important frozen-rule limitations:

- All sixteen new fence functions contain at least two assertions without
  messages and are marked Assertion Roulette. Those assertions also address
  multiple required task behaviors. A smell flag is not a task-completion failure.
- 07 `test_make_fence_after` repeats structurally identical assertions over
  `tokens` after reassigning it to a different parse result. The Phase 1 Duplicate
  Assert definition compares normalized expression syntax, not variable versions
  or semantic redundancy. Its one confirmation is retained for consistency.
- 08 `test_core_after` has manual `try/except ValueError` followed by `pytest.skip`;
  that matches the frozen Exception Handling rule.
- Repeated use of the same parser method does not count as Eager Test under the
  frozen rule; list comprehensions are not statement-level Conditional Test Logic.

For comparability, none of these boundaries was tuned for Phase 2. Density is one
operational indicator of test-code design, not a complete maintainability measure.

## Reproduction and validation

```bash
python scripts/metric_collection_phase2/collect_test_smells.py
# Use --output-dir for a fresh destination when reproducing.
tox -e py311 -- tests/metric_collection tests/metric_collection_phase2
```

The CLI refuses to overwrite an existing output directory. Optional
`--pytest-smell` and `--tempy-root` paths enable auxiliary evidence. Main evidence:

- `results/phase2/test_smells/collection_manifest.json`
- `results/phase2/test_smells/raw/experiment-NN.json`
- `results/phase2/test_smells/summary/test_smell.csv`
- `results/phase2/test_smells/summary/by_task/maintenance.csv`
- `results/phase2/test_smells/summary/by_task/legacy_task_scope.csv`
- `results/phase2/test_smells/summary/aggregate.json`

Raw files retain source IDs, task groups, validity, decision lines/reasons and
original input hashes. Manifests record all collector hashes alongside the Git
commit, so uncommitted collector changes remain identifiable.

The `summary/` root holds the primary CSV and aggregate JSON. Supplemental
task-scope CSVs and their manifests live together in `summary/by_task/`.

Validation includes 194 passing regression tests, new coverage of partial/zero
validity, equal names in different files, artifact drift and uncertain pairs,
plus Ruff and strict mypy for the Phase 2 collector. Frozen Phase 1 input commits
were reanalyzed for all 14 collected participants: all formal summary metrics and
per-smell counts reproduce the stored dataset exactly.
