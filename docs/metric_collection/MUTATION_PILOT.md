# Mutation Tool Pilot

## Objective

This pilot evaluates whether MutPy, Mutmut, and Cosmic Ray can execute the same
participant-authored pytest suite against a fixed SUT under Python 3.11. It is a
tool-selection benchmark, not a comparison of participant mutation scores.

The fixed setup is:

- SUT: `pilot-metric`, limited to `markdown_it/ruler.py`;
- tests: `origin/experiment-11:tests/task/task.py`;
- baseline: 656 passing expanded pytest cases;
- execution: local and serial;
- catalog check: generate each tool's catalog twice and compare semantic mutant
  identifiers while ignoring random session IDs.

Each tool uses its native default mutation operators. Therefore, mutant counts and
raw mutation scores are not directly comparable across tools. A common operator
catalog must be defined after selecting the final runner.

## Results

| Tool | Version | Mutants | Killed | Survived | Other | Time | Catalog stable | Python 3.11 assessment |
| --- | --- | ---: | ---: | ---: | --- | ---: | --- | --- |
| MutPy | 0.6.1 | 72 | 0 | 1 | 71 incompetent | 1.2 s | yes | unsuitable without repairing its AST mutation layer |
| Mutmut | 3.7.0 | 167 | 66 | 33 | 66 no-tests, 2 timeout | 24.1 s | yes | compatible |
| Cosmic Ray | 8.7.0 | 236 | 54 | 182 | none | 231.0 s | yes | compatible |

Times are single-run wall-clock observations on the pilot machine and should not be
treated as general performance measurements. MutPy appears fast because 71 of 72
mutants are incompetent and never execute tests.

## Interpretation

MutPy successfully collects all fixtures and parameterized tests, but 98.6% of its
generated mutants are incompetent on this Python 3.11 target. Its reported mutation
score is therefore not valid for this experiment. Stable mutation numbers do not
compensate for this compatibility failure.

Mutmut is the fastest viable runner in this pilot and exposes stable, readable
mutant names. Its coverage-guided execution labels mutants outside this participant
suite's observed dependency set as `no_tests`; the final metric definition must say
whether these are excluded or retained as non-killed mutants.

Cosmic Ray provides the clearest fixed-catalog model: `init` creates a reusable
SQLite session before any participant tests run, and semantic catalog entries were
identical across two sessions. It is substantially slower with the serial local
distributor, but it gives explicit operator, occurrence, source span, diff, and test
outcome data for every mutant.

## Decision

Exclude MutPy 0.6.1 from the final Python 3.11 pipeline unless a maintained fork is
validated separately. Use Mutmut 3.7.0 as the formal collection runner because it
is compatible, substantially faster, and provides stable names plus practical
manual-review commands. Use Cosmic Ray only to cross-check a deterministic subset
of at most 50 matching normalized mutant diffs.
