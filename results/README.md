# Experiment Results

Generated research data is organized by metric:

- `error_rates/` stores the cross-participant collection manifest, raw participant
  records, and the error-rate summary. The raw records also contain coverage and
  assertion evidence because all three metrics share the same valid-test filter.
- `coverage/` stores the analysis-ready statement and branch coverage summary.
- `assertion_score/` stores the analysis-ready assertion-score summary.
- `mutation_score/` stores mutation catalogs, dry-run inventories, participant
  executions, review artifacts, and mutation-score summaries.
- `execution_time/` stores pilot and formal execution-time measurements.
- `test_smells/` stores test-smell evidence, tool output, and summary tables.

Mutation-score working data is ignored because its catalogs and raw execution
records are large. The smaller frozen datasets for the other metrics remain
version-controlled research evidence.
