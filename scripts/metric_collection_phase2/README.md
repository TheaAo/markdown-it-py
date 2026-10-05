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
