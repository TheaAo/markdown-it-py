# Phase 2 execution time

Eight continuing participants (02, 03, 04, 05, 07, 08, 09, 12) all used Copilot.
The measured pool is the frozen instance-level valid pool from Phase 2
 effectiveness collection. All valid instances run together in original submitted
files, including participant-modified external test files where applicable.

- `input_error_rates/`: byte-for-byte validity evidence from effectiveness commit
  `56852ac8de04e216b48ab9b34445027216ba5a47`, with recorded SHA-256 hashes.
- `formal/`: the latest complete collection, manifest, raw observations and
  `summary/execution_time.csv`. Earlier formal data was replaced at user request.
- `new-run/`: an additional complete run generated separately; it does not
  replace `formal/`.
- `quality_review.json`: current dispersion, CV flags and verification counts.
- `environment.json`: interpreter, package versions and machine details.
- `diagnostics/`: temporary-copy investigations of participant 05. These are
  diagnostic evidence only; participant submissions and formal data are unmodified.

## Current protocol

Protocol v3 is saved in
`scripts/metric_collection_phase2/execution_timing_protocol.json`. All snapshots
are exported from immutable participant commits and verified before timing.
Formal collection is serial in ascending order: 02, 03, 04, 05, 07, 08, 09, 12.
There is no additional full-cohort warmup and no randomized order. Each participant
has one baseline, three warmups and fifteen formal measurements. Only the fifteen
formal measurements contribute to the summary; execution time is their median.
The timer and estimator are reused from Phase 1. Durations include complete
Python/pytest subprocess startup, imports, collection, fixture handling, test
execution and exit. Cacheprovider is disabled, PYTHONHASHSEED is 0 and external
PYTEST_ADDOPTS are removed. Timing is separate from coverage/mutation collection.

The latest collection on 2026-10-06 passed 120 measurements, 24 warmups and
8 baselines, with zero global warmups. Participants meeting the 5% CV threshold:
02, 04, 05, 07, 09.
Flagged participants: 03 (9.50%), 08 (10.99%), 12 (5.51%).
All formal observations remain in the summaries, including slow observations.
CV above 5% triggers review; it does not invalidate records or authorize automatic
reruns. Collection success does not establish stability for flagged records.

After source hashes, collector hashes, selected node IDs, all return codes and
recomputed medians/CVs were verified, the previous formal dataset was deleted and
replaced at user request. Historical pilot/validation/recollection timing datasets
had already been deleted at user request. Frozen validity evidence and separate
participant-05 diagnostics are retained. No earlier observations are pooled with
this run, and no participant-specific best run is selected.

## Comparability and reproduction

The protocol was iterated during Phase 2: v2 added one global warmup and a fixed
random participant order; v3 removes both at the researcher's request. Phase 1 and
v3 share the primary metric, baseline, three warmups, fifteen measurements, serial
ascending order and CV review threshold. Execution layout still differs: Phase 1
used isolated valid-test files; Phase 2 retains original files and fixture/relative
path behavior. Phase 1 formal records used a Python 3.10 environment; this run uses
Python 3.11.6. Tasks and SUT also differ, so direct phase differences cannot be
attributed exclusively to participant behavior or AI use.

Use a new staging directory, verify the complete run, then replace if authorized:

```bash
python scripts/metric_collection_phase2/collect_execution_times.py \
  --source-manifest results/phase2/execution_time/input_error_rates/collection_manifest.json \
  --output-dir results/phase2/execution_time/new-run \
  --python /path/to/experiment/python
```

The Phase 2 adapter and shared timer/CSV regression tests passed 12 tests via tox.
Ruff and strict mypy with imported modules skipped passed. Full imported-module
checking encounters a pre-existing duplicate-module mapping in Phase 1 fallback
imports.

The Phase 1 engine imports now use `scripts/metric_collection_phase1/` after
merging the Phase 2 directory migration. Saved collection manifests preserve the
original source paths and hashes from collection time; they are not rewritten.
