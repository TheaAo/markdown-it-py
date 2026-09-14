# Experiment Results

Generated research data is organized by metric:

- `error_rates/` stores the cross-participant collection manifest, raw participant
  records, and the error-rate summary. The raw records also contain coverage and
  assertion evidence because all three metrics share the same valid-test filter.
- `coverage/` stores the analysis-ready statement and branch coverage summary.
- `assertion_score/` stores the analysis-ready assertion-score summary.
- `mutation_score/` stores mutation catalogs, dry-run inventories, participant
  executions, review artifacts, and mutation-score summaries.

Only this index is tracked by Git. Generated contents below `results/` are ignored.
