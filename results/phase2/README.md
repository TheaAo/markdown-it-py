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
Future metric directories follow the Phase 1 layout. Participant 12's duration was corrected by the researcher
from `00:37:59` to `00:09:25`; both seconds columns are 565.

See [the collection plan](../../docs/metric_collection_phase2/COLLECTION_PLAN.md).
