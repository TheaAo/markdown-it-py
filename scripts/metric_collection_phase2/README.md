# Phase 2 efficiency collection

`collect_execution_times.py` reads frozen effectiveness validity evidence and
reuses the Phase 1 subprocess timer and median estimator. Source export, original
multi-file instance selection and provenance checks are adapted to Phase 2.

Current protocol v3 prepares and verifies all snapshots before timing, then
measures in ascending participant-number order without a full-cohort warmup pass.
Each participant retains one baseline, three warmups and fifteen measurements.
Only the fifteen measurements contribute to summaries. The manifest records
execution order and protocol; global warmup fields are empty for this protocol.
See `results/phase2/execution_time/README.md` for results and comparability limits.
