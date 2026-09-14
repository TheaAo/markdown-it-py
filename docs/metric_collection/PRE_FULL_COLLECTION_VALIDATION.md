# Pre-Full-Collection Validation

Date: 2026-09-07 (Europe/Stockholm)

## Decision

The Mutation Score collector is ready for an explicitly approved serial
cross-branch collection. The version-controlled formal execution policy is frozen
in `docs/metric_collection/formal_collection_policy.json`; an identical copy is
kept with the local formal results.
The selected timeout multiplier is 6 with constant 0.5 and one timeout retry.

This is a content-hash freeze, not a Git commit freeze. The collector changes are
still uncommitted, so the recorded source hashes must be checked before the formal
run and preserved with the final artifacts.

## Timing Backfill

The `experiment-11` schema-v3 backfill ran all 4,725 catalog mutants. It retained
the existing reliable-kill evidence and recorded execution metadata without
inventing durations for the 262 `no_tests` outcomes. Rows with `no_tests` have an
estimated duration and Mutmut exit code but no actual test execution duration.

## Timeout-Increase Pilot

Changing the timeout multiplier from 5 to 6 reused 4,579 completed outcomes and
reran exactly the 146 prior timeout outcomes. No non-timeout outcome was rerun due
to policy. Three timeouts became reliably killed, leaving 143 timeouts. The final
counts were 3,023 killed, 1,297 survived, 262 no-tests, and 143 timeout, for a
Mutation Score of 0.6597555652553471.

The selective run exposed an empty-placeholder metadata bug in reused rows. The
collector now selects metadata from the execution that supplied each status, and
regression tests cover both reused and rerun rows. The affected formal raw result
was repaired only from its exact archived predecessor. The repair provenance,
source hash, and pre-repair archive are recorded in the raw result.

## Interruption and Resume Pilot

A disposable 200-mutant catalog of known fast kills was run with confirmation
batches of one. The process group was interrupted with SIGINT immediately after
five reliable-kill records had been atomically persisted.

After interruption:

- all five records remained valid and readable;
- no partial participant raw result was published;
- the temporary Git worktree was removed.

On restart, the collector reused the five persisted confirmations and confirmed
only the remaining 195. The final artifact contained 200 confirmed kills and
complete execution metadata.

Resume operates at two granularities: completed participants are reused from their
raw result, while reliable-kill confirmations are persisted after each configured
batch. If a participant is interrupted before its final raw result is published,
that participant's mutation statuses run again, but completed reliable-kill
confirmations do not.

## Verification

- `tests/metric_collection`: 78 passed.
- `tests/`: 334 passed.
- Python compilation passed.
- Focused `git diff --check` passed.
- Ruff, tox, and pre-commit were unavailable in the installed environments.
- The all-directory pytest invocation could not collect `benchmarking/` because
  `pytest-benchmark` is not installed; this was an environment collection error,
  not a failing test.

## Frozen Full-Collection Command

Do not run this command without explicit approval for the full cross-branch run.

```bash
.venv-mutmut/bin/python scripts/metric_collection/collect_all_mutation_scores.py \
  --catalog results/mutation_score/full-sut/catalog/task_relevant_mutant_catalog.json \
  --python .venv-mutmut/bin/python \
  --baseline origin/experiment-base \
  --output-dir results/mutation_score/full-sut/formal \
  --max-children 4 \
  --timeout-multiplier 6 \
  --timeout-constant 0.5 \
  --timeout-retry-count 1 \
  --confirmation-batch-size 25 \
  --resume \
  --confirm-kills
```

Participants 13 and 15 remain `not_participated`. Collection must be serial and
must continue to archive replaced artifacts by content hash.
