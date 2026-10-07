# Experiment Results

Research data is separated by experimental phase:

- `phase1/` contains the existing frozen results, questionnaires and summary workbook.
- `phase2/` contains completed eight-person primary metric tables and evidence.
  See [current Phase 2 status](../docs/metric_collection_phase2/COLLECTION_STATUS.md)
  for remaining review and analysis work.

The original result files were moved without modifying their contents. Historical
paths, commits and hashes inside those files identify the original collection run.
Resolve relative output paths from the relocated manifest directory.

Within each phase, generated data is organized by metric:

- `error_rates/` stores the cross-participant collection manifest, raw participant
  records, and the error-rate summary. Phase 1 raw records also contain coverage
  and assertion evidence; Phase 2 uses separate collectors sharing the frozen valid pool.
- `coverage/` stores the analysis-ready statement and branch coverage summary.
- `assertion_score/` stores the analysis-ready assertion-score summary.
- `generation_time/` stores the self-reported comprehension and total generation
  times and normalized seconds. Phase 2 uses total task duration, including
  comprehension, maintenance, generation and debugging.
- `mutation_score/` stores mutation catalogs, dry-run inventories, participant
  executions, review artifacts, and mutation-score summaries.
- `execution_time/` stores timing evidence. Phase 2 `formal/` is the selected latest
  complete run; earlier formal observations were replaced at researcher request.
- Phase 2 `efficiency/` stores all six generation/execution ratios and provenance;
  Phase 1 efficiency outputs retain their existing metric-directory locations.
- `test_smells/` stores test-smell evidence, tool output, and summary tables.

Large mutation-score historical working data and caches are ignored. Phase 2
canonical final tables and review evidence are tracked alongside the other frozen
metric datasets. Preserve recorded hashes and historical paths when organizing data.
