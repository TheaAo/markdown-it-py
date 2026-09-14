# Generation Time

`generation_time.csv` records the self-reported Phase 1 timing observations supplied
for the experiment participants.

- `comprehension_time` is the initial task-comprehension portion of the total time.
- `total_time` already includes `comprehension_time`; the two durations must not be
  added together.
- `generation_time_seconds` therefore equals `total_time_seconds` and is the
  denominator for generation-efficiency metrics.
- Text durations are normalized to `HH:MM:SS`. The source value `00:13:26:` for
  participant 5 is normalized to `00:13:26` as an obvious trailing-colon typo.
- Participants 13 and 15 did not participate and are retained as explicit
  `not_participated` rows with unavailable timing fields.

The source observations were supplied by the researcher on 2026-09-14. No timing
values were inferred or imputed.
