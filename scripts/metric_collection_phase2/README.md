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
