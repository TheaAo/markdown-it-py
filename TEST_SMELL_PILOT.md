# Test Smell Pilot Protocol and Results

## Final decision

The formal metric uses seven smells:

1. Assertion Roulette;
2. Magic Number Test;
3. Unknown Test;
4. Conditional Test Logic;
5. Eager Test;
6. Duplicate Assert;
7. Exception Handling.

Test Maverick is deliberately excluded. The experiment uses five function-style
pytest tests without a common class-level setup fixture, so the smell has no stable
unit of interpretation. Its exclusion is based on experimental structure, not only
on PyNose being unavailable.

The final detector is a versioned AST rule engine that scans every eligible source
test for all seven smells. pytest-smell is retained as the main external reference;
TEMPY cross-checks only Conditional Test Logic, Unknown Test, and Exception
Handling. Tool outputs are evidence, not a candidate gate and not the final metric.

## Benchmark design

Protocol version 2 aligns the benchmark with all seven formal smells. It contains
42 source test functions: six per smell, including clear positives, clear controls,
and task- or pytest-specific boundary cases. There are 22 positive
`(source test, smell type)` labels across the complete `42 × 7` decision space.

All labels were fixed in `gold_labels.json`. Pytest expands two parameterized
functions, so executing the benchmark produces 44 passing instances while the
analysis unit remains 42 source functions.

The old 30-case, four-smell pilot is superseded. Its results may only be described
as an engineering smoke test and must not support claims about the seven formal
smells.

## Frozen operational definitions

### Assertion Roulette

Report when a source test contains at least two `assert` statements without an
explicit message. Pytest assertion rewriting reduces severity but does not change
the literature-aligned occurrence rule. Record this limitation in the thesis.

### Magic Number Test

Report a numeric literal in an assertion expression, excluding booleans,
`-1`, `0`, `1`, subscript indices, named constants, parameter data, and required
task exit codes.

### Unknown Test

Report when no supported oracle is reachable. Supported oracles include `assert`,
`pytest.raises`, `pytest.warns`, `pytest.fail`, unittest assertion methods,
regression/snapshot checks, and assertions in statically visible local helpers.

### Conditional Test Logic

Report statement-level `if`, `for`, `async for`, `while`, or `match`. Exclude
ternary expressions, comprehensions, and generator expressions.

### Eager Test

Report when at least two distinct `markdown_it` production entry methods produce
results that feed independent oracles. Repeated use of one method, multiple
assertions over one result, configuration calls, and input-construction helpers do
not qualify.

### Duplicate Assert

Report at least two structurally identical assertion conditions in one source test.
Compare normalized AST, retaining names, operators, constants, and call arguments
while ignoring formatting, source locations, and assertion messages.

### Exception Handling

Report manual `try/except` handling used in place of a framework exception oracle.
Exclude `pytest.raises`, `pytest.warns`, and cleanup-only `try/finally`.

For Unknown Test and Eager Test, local helpers may be followed to find oracles or
production calls. Other structural smells are scoped to the source function and
nested functions; shared fixtures are not copied to every test. Unresolved cases
must be marked `uncertain` in formal collection.

## Executed tools

- AST rule engine version `1` in `scripts/detect_test_smells_ast.py`;
- pytest-smell `1.0.5`;
- TEMPY commit `4c945d121d645b52fefb8f1b4f3e6caeec7c9095`;
- PyNose current CLI `081e5f9dcc416da4a290bcc5102ce46f104afefa`;
- PyNose headless `490a4a4d96ef5ca5d31c721bd3c0ddc92a0350cd`.

Each runnable path was executed twice and produced identical standardized output.
PyNose remained unavailable because both official command-line paths failed to
resolve the drifting `plugin-utilities` dependency; the headless branch also had
incompatible Java targets.

## Seven-smell results

pytest-smell was evaluated across all seven formal smells:

| Smell | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Assertion Roulette | 3 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| Magic Number Test | 3 | 5 | 0 | 37.5% | 100.0% | 54.5% |
| Unknown Test | 3 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| Conditional Test Logic | 3 | 2 | 1 | 60.0% | 75.0% | 66.7% |
| Eager Test | 0 | 0 | 3 | 0.0% | 0.0% | 0.0% |
| Duplicate Assert | 1 | 0 | 2 | 100.0% | 33.3% | 50.0% |
| Exception Handling | 3 | 2 | 0 | 60.0% | 100.0% | 75.0% |
| **Micro total** | **16** | **9** | **6** | **64.0%** | **72.7%** | **68.1%** |

TEMPY was evaluated only on the three formal smells its current execution path
supports:

| Smell | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Unknown Test | 3 | 3 | 0 | 50.0% | 100.0% | 66.7% |
| Conditional Test Logic | 3 | 0 | 1 | 100.0% | 75.0% | 85.7% |
| Exception Handling | 3 | 2 | 0 | 60.0% | 100.0% | 75.0% |
| **Micro total for three supported smells** | **9** | **5** | **1** | **64.3%** | **90.0%** | **75.0%** |

The AST engine matched all 22 frozen benchmark labels, giving 100% protocol
conformance on this regression corpus. This is not a claim of 100% accuracy on
unseen participant code: the rules and benchmark were developed together. The
formal collection therefore must retain `uncertain` results and include a manual
audit after rules are frozen.

## Interpretation

The aligned pilot rejects the earlier idea that pytest-smell can serve as the final
detector. It completely missed the benchmark's Eager Test examples and missed two
of three normalized Duplicate Assert examples. Its keyword and line-based logic
also produced false positives for Magic Number, Conditional Test Logic, and
Exception Handling.

TEMPY provides useful independent evidence for three smells but cannot validate the
other four. It missed `match` and treated `pytest.raises`, cleanup-only
`try/finally`, and text containing exception keywords incorrectly in boundary
cases.

The evidence supports this closed design:

- AST engine: complete seven-smell scan and final versioned decision;
- pytest-smell: external evidence for all seven supported categories;
- TEMPY: independent evidence for three shared categories;
- PyNose: excluded from automation;
- no voting, score averaging, or union-based candidate restriction.

## Source-function validity

For maintenance metrics, aggregate Error Rate instances into:

```text
all instances valid                 -> fully_valid
at least one but not all valid      -> partially_valid
zero valid instances                -> invalid
```

Both `fully_valid` and `partially_valid` are eligible for Assertion Score and Test
Smell analysis. Store `valid_instance_count`, `total_instance_count`, and
`validity`. Execution metrics such as Coverage still execute only valid pytest
instances.

## Formal outputs

Count one binary `(source test, smell type)` pair. Multiple occurrences of one
smell in the same source test count once.

```text
Smelly Test Rate
= eligible source tests with at least one confirmed smell / eligible source tests

Mean Smells per Test
= confirmed (source test, smell type) pairs / eligible source tests

Test Smell Density
= confirmed pairs / (eligible source tests * 7 formal smell types)
```

Smelly Test Rate and Test Smell Density are bounded in `[0, 1]`; Mean Smells per
Test preserves the unnormalized number of distinct smell types per eligible test.
When there are no eligible source tests, all three are `null`. Preserve raw tool
evidence, AST evidence, final decision, decision reason, and rule/tool versions.

## Reproduction

```bash
python scripts/detect_test_smells_ast.py \
  tests/metric_collection/fixtures/test_smell_pilot/test_pilot_cases.py

python scripts/evaluate_test_smell_pilot.py
```

Evidence files are under `tests/metric_collection/fixtures/test_smell_pilot/`.

## Literature

- Wang et al. (2021), [PyNose](https://arxiv.org/abs/2108.04639).
- Bodea (2022), [pytest-smell](https://doi.org/10.1145/3533767.3543290).
- Fernandes et al. (2022), [TEMPY](https://doi.org/10.1145/3555228.3555280).
- Alves et al. (2024), [Python test smells in LLM-generated
  tests](https://doi.org/10.5753/sbes.2024.3561).
