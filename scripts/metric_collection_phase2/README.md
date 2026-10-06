# Phase 2 metric collection

Implementation and collection order:
[`COLLECTION_PLAN.md`](../../docs/metric_collection_phase2/COLLECTION_PLAN.md).

Start by inspecting locally available submissions:

```bash
python scripts/metric_collection_phase2/inventory_submissions.py
```

This creates `results/phase2/inventory/submissions.json`. It does not execute tests
or declare submissions valid. Resolve inventory findings before metric collection.
Reuse engines from `scripts/metric_collection_phase1/`; keep Phase 2-specific
submission mapping, task scopes and orchestration here.

Error-rate collection is implemented in `collect_error_rates.py` and accepts only
standard `experiment-xx-phase2` branches. See
[`ERROR_RATES.md`](../../docs/metric_collection_phase2/ERROR_RATES.md) for counting,
reproduction and current collection status.

`collect_coverage.py` consumes the frozen error-rate valid pool and reuses the
Phase 1 coverage engine. See [`COVERAGE.md`](../../docs/metric_collection_phase2/COVERAGE.md)
for scopes, units, evidence and reproduction.

`collect_assertion_score.py` reuses the Phase 1 AST analyzer with the frozen
instance classifications, source-file identity and actual selected functions.
See [`ASSERTION_SCORE.md`](../../docs/metric_collection_phase2/ASSERTION_SCORE.md)
for scoring and manual-review candidates.

`build_mutant_catalog.py`, `collect_mutation_score.py` and
`run_mutation_collection.py` adapt the existing mutation engines for Phase 2
reference workloads and original-path valid instances. See
[`MUTATION_SCORE.md`](../../docs/metric_collection_phase2/MUTATION_SCORE.md).
`finalize_mutation_score.py` validates the completed cohort, prepares the frozen
equivalence-review sample, and exports adjusted scores after completed review.


Final primary Mutation Scores are now available in
`results/phase2/mutation_score/mutation_score.csv`. Source review and statistical
provenance are preserved under `global/` and `final/`; the report describes the
single-reviewer limitation. The collector defaults to serial execution and always
runs participant 08 serially because its frozen tests share `output.html`.
