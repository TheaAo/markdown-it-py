# Phase 2 results

The actual Phase 2 cohort consists of participants 02, 03, 04, 05, 07, 08, 09 and
12. All eight used Copilot under the same model, mode, time limit and environment;
the crossover design was abandoned after confirming the Phase 2 participant count.
Each participant maintained their own Phase 1 submission after approximately 2–3
months, with no code changes during the interval.

- `generation_time.csv` stores the supplied durations and calculated seconds for
  the eight participating rows. `generation_time_seconds` follows the Phase 1
  convention of using total task duration, including comprehension, maintenance,
  new test development and debugging. Nonparticipant calculations
  remain blank; their original duration fields are preserved pending clarification.
- `Post-experiment Survey (Phase 2).csv` is the unmodified survey export for the
  same eight participants.
- `inventory/` contains submission preflight evidence only. Its initial inventory
  used the original sixteen-person list and local refs; it does not define the
  final Phase 2 cohort.

`error_rates/` contains the latest collection for all eight participants: 58 pytest
instances, all valid, with zero classified errors. Participant 08's relocated
`tests/test_cli.py::test_non_utf8` is included; its commented, unimplemented
`test_parse_fail` remains in missing expected functions, separately from error rates.
Participants 08 and 09 each have eight executed cases; the others have seven.
`error_rates_history/` preserves earlier collections unchanged.
See [Error Rate methodology](../../docs/metric_collection_phase2/ERROR_RATES.md).

`coverage/` contains the completed eight-participant coverage collection using the
same 58 valid instances. The summary CSV uses 0–1 fractions; raw records include
covered/total counts and percentage values. Evidence includes whole-suite and
task-group coverage, pristine project coverage and combined coverage unions.
See [Coverage methodology](../../docs/metric_collection_phase2/COVERAGE.md).

`assertion_score/` contains automated assertion-quality results for all eight
participants, using the same frozen submissions. The analyzer scores source
functions rather than pytest instances. All four uncertain classifications were
resolved as non-trivial by Codex source review with targeted execution probes.
The raw automatic evidence remains unchanged; `assertion_score.csv` contains
the adjusted scores, and `manual_review/` retains adjudications and evidence.
The two trivial classifications remain pending in `review_candidates.csv`. See
[Assertion Score methodology](../../docs/metric_collection_phase2/ASSERTION_SCORE.md).

`mutation_score/mutation_score.csv` contains the final eight-participant Mutation
Score. The primary column is `specified_estimated_adjusted_score` (0–1 fractions),
with raw scores, approximate 95% intervals and supplementary scopes retained.
The corrected catalog contains 5,051 task-relevant mutants. The fixed 100-mutant
stratified sample has 16 confirmed equivalent invariants and 84 non-equivalent
witnesses; all primary precision criteria pass. Equivalent decisions have one
Codex source reviewer and no independent secondary review. Participant 08's entire
catalog was rerun serially to eliminate a shared-file race; the final results have
zero flaky kills. See the generated `mutation_score/run_report.md` and
[Mutation Score methodology](../../docs/metric_collection_phase2/MUTATION_SCORE.md).
Mutation working data remains ignored, as in Phase 1. Archived Phase 1 Mutation
Scores require scope rechecking before direct cross-phase comparison.
Future metric directories follow the Phase 1 layout. Participant 12's duration was corrected by the researcher
from `00:37:59` to `00:09:25`; both seconds columns are 565.

See [the collection plan](../../docs/metric_collection_phase2/COLLECTION_PLAN.md).

`execution_time/formal/` now contains the researcher's latest complete `new-run`,
promoted unchanged at explicit request. Earlier formal timing data was replaced.
`efficiency/` contains all six full-valid-suite generation and execution ratios,
component scores/times, CV flags and conditional Mutation Score interval bounds.
See `efficiency/README.md`; generation time means total task time, and execution
uses only the selected latest dataset.
