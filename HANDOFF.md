# Mutation Score Collection Handoff

Last updated: 2026-09-15
Repository: `/Users/ruoyur/Code/Chalmers/MasterThesis/markdown-it-py`
Current branch: `pilot-metric-mutation`

## Current Finalisation Status (2026-09-15)

This section is authoritative. Sections 9--15 are retained only as explicitly
labelled historical context from before the completed full collection.

- `pilot-metric` was fast-forwarded into `pilot-metric-mutation`; both local and
  remote branches were at `7c35b01` before the statistical-finalisation changes.
- Full collection finished on 2026-09-07 and global aggregation finished on
  2026-09-08. The fixed catalog contains 4,725 mutants across 14 reliable
  participants; experiments 13 and 15 did not participate.
- The formal collection manifest records 15,518.707 seconds total duration.
- Reliable kill evidence proves 3,041 mutants non-equivalent. The remaining 1,684
  review candidates contain no execution-unresolved mutants.
- Reliable kills are the only accepted automatic pre-screen for the frozen frame.
  No LLM, identical kill vector, AST/bytecode heuristic, or unvalidated duplicate
  representation is used as semantic-equivalence proof.
- Experiments 04 and 06 have no valid tests and correctly receive zero through
  `no_tests`. Participant timeouts remain excluded from score denominators.
- The selected finalisation route is statistical equivalent-mutant estimation, not
  a 1,684-mutant census and not automatic labelling of survivors as equivalent.
- The first review round is a reproducible 100-mutant probability sample with seed
  `20260915`, stratified by `workload_layer` and `operator_family`. The three
  singleton extended-only strata are censused. Automatic duplicate clustering is
  not used, so every mutant currently has cluster multiplicity one.
- The sampling implementation and tests are in
  `scripts/metric_collection/equivalent_mutant_sampling.py`,
  `scripts/metric_collection/summarize_equivalent_mutant_sample.py`,
  `scripts/metric_collection/targeted_mutant_review.py`, and their focused tests.
- The stage-one sample, audit manifest, reviewer files, and adjudication
  template are under
  `results/mutation_score/full-sut/formal/global/equivalent_review_sample_stage1/`.
  The earlier blank 313-item sample is retained under `equivalent_review_sample/`
  as an unused reserve; the 100 selected IDs form a strict subset of it.
- The primary reviewer checks all 100 rows. Only proposed-equivalent, duplicate,
  unresolved, and ten deterministically selected non-equivalent quality-control
  rows receive blinded secondary review. Targeted selection means full-sample
  Cohen's kappa is not claimed; quality-control raw agreement is retained.
- The primary review is complete: all 100 rows have non-empty reasons, with 12
  `confirmed_equivalent` and 88 `non_equivalent` decisions. The independent targeted
  secondary review is also complete for all 22 selected rows (all 12 proposed
  equivalents plus 10 deterministic quality-control rows). The two reviewers had no
  disagreements, and raw agreement in the random quality-control subset was 1.0.
  Full-sample Cohen's kappa is deliberately not reported because secondary selection
  was targeted. The selection-manifest hash is
  `8c828070cb64cd81bd7b2caf6f7019fa8960056d07fc50eebcd45ffd9f160649`.
- Final estimates use Horvitz--Thompson design weights and conservative nominal 95%
  finite-population intervals based on the binary worst-case variance. Sequential
  expansion uses pre-specified cumulative sizes 100, 150, 225, and 313 and a
  Bonferroni correction across the four looks (98.75% stopping intervals). It keeps
  the same frame and seed and must continue until every specified participant-score
  stopping interval has half-width at most 0.05, or the limitation is explicitly
  reported. The nominal participant intervals are marginal, not simultaneous 95%
  coverage claims. All catalog, SUT, policy, frame, sample, and manifest hashes are
  revalidated before estimates are written. Review-summary, decision-status, and
  participant-matrix hashes are also retained in the final outputs.
- The formal first-look estimate is complete. The stratified Horvitz--Thompson
  estimate is 214.885 equivalent mutants among the 1,684-candidate review frame
  (estimated proportion 0.127604; conservative nominal 95% count interval
  50.792--378.978). The sample contains 12 confirmed-equivalent and no unresolved
  decisions.
- The pre-specified stage-one stopping rule passed: the largest specified-layer
  participant stopping-interval half-width is `0.033405`, below the `0.05` target.
  No expansion to 150, 225, or 313 reviews is required. Experiment 07 has the widest
  primary interval; its estimated adjusted score is 0.692502 with nominal 95%
  interval 0.667301--0.719680.
- Final outputs are
  `results/mutation_score/full-sut/formal/global/equivalent_review_sample_stage1/final/mutation_scores.csv`
  and `mutation_score_estimates.json` in the same directory. The final review hash is
  `7fccc6f69321b576821e5d690f726b4c4b6a781c5f99fdf47b2cda6a7c0a89aa`.
- The finalisation changes described here are not committed or pushed. Do not
  commit or push them without explicit user approval.

Immediate next actions are final verification of the code and documentation, review
of the intended git diff, and commit/push only after explicit user approval. Generated
tests may provide global non-equivalence witnesses but must never be added to
participant test suites when computing participant scores.

## Historical Readiness Update (2026-09-07)

This update supersedes the earlier blocker and next-step sections below.

- Explicit timing backfill was implemented and completed for `experiment-11`.
- A real timeout increase from multiplier 5 to 6 reused 4,579 outcomes and reran
  exactly 146 prior timeouts; three became reliably killed and 143 remain timeout.
- The current counts are 3,023 killed, 1,297 survived, 262 no-tests, and 143
  timeout. The Mutation Score is `0.6597555652553471`.
- All 3,023 current kills have reliable evidence.
- A real 200-mutant interruption/resume test preserved five incrementally written
  confirmations, cleaned its worktree, reused those five after restart, and
  confirmed only the remaining 195.
- A selective-run metadata placeholder bug was found, fixed, regression-tested,
  and repaired from the exact archived predecessor with provenance retained.
- `tests/metric_collection` has 78 passing tests and `tests/` has 334 passing
  tests. Ruff, tox, pre-commit, and the pytest-benchmark plugin are unavailable.
- The formal candidate policy is frozen at timeout multiplier 6, constant 0.5,
  one retry, confirmation batch size 25, and max children 4. See
  `docs/metric_collection/formal_collection_policy.json` and
  `docs/metric_collection/PRE_FULL_COLLECTION_VALIDATION.md`.

The collector is ready for an explicitly approved serial full cross-branch run.
It has not been committed or pushed, and no full cross-branch run has started.

## 1. What This Work Is About

This repository is being extended with research data collectors for a Chalmers
master thesis. The experiment evaluates tests written by participants on branches
`experiment-01` through `experiment-16`; participants 13 and 15 did not participate.
The participant submission is normally `tests/task/task.py`.

The broader metrics work includes:

- syntax, runtime, and function error rates;
- statement and branch coverage;
- assertion score;
- Mutation Score;
- analysis-ready CSV summaries and documentation.

The current task is specifically the full-SUT Mutation Score collector. It uses a
fixed Mutmut catalog generated from the common experiment baseline, runs only each
participant's valid test cases, records per-mutant outcomes, reuses reliable cached
evidence, and supports global equivalent-mutant review.

The central methodological rule is:

> Timeout is an execution policy. A reliably confirmed kill is experimental
> evidence. Changing timeout must not erase or reconfirm that evidence.

## 2. Experimental Invariants

Do not violate these rules:

1. The fixed SUT comes from `origin/experiment-base` at commit
   `e5deff554777f059bca726e55bbcbfcc01c10620`.
2. The fixed SUT hash is
   `0e7e7bbc3888b630b3abbd5ae4e31f2cbdf3dc46aa19efa86c34138364383254`.
3. The task-relevant catalog hash is
   `ab4b3d2e06e961673a865c12dffbe5ea82e3ca405ec29cdb813366b44bb74462`.
4. Mutmut is version 3.7.0 under Python 3.11.6.
5. Never modify participant branches or the fixed SUT during collection.
6. Mutation operations run in isolated temporary directories/worktrees.
7. Only valid-only participant tests enter mutation testing. Syntax, runtime, and
   function-error cases are excluded; parameterized tests are isolated per case.
8. Participants 13 and 15 must be reported as `not_participated`.
9. Never silently delete old raw results or evidence. Archive old artifacts first.
10. Do not launch a complete all-participant run without explicit user approval.

## 3. Tool Selection Results

The tool pilot compared MutPy, Mutmut 3, and Cosmic Ray.

- MutPy 0.6.1 produced approximately 98.6% incompetent mutants on Python 3.11
  and was rejected for formal collection.
- Mutmut 3.7.0 was fast, generated stable names, and supports human inspection
  through `show`, `tests-for-mutant`, and `browse`. It is the primary runner.
- Cosmic Ray has a clear catalog representation but was approximately ten times
  slower in serial execution. It is retained only for small cross-validation.
- Pynguin was not selected because its mutation engine primarily supports generated
  tests and would require a custom runner for external participant pytest suites.

Do not restart the tool-selection debate unless a reproducible incompatibility is
found in Mutmut 3.7.0.

## 4. Catalog Work Already Completed

The full-SUT catalog was generated twice and its identity was checked.

- Raw full-SUT mutants: 7,057
- Task-relevant catalog: 4,725
- Specified layer: 4,722
- Extended-only layer: 3
- Out-of-scope and excluded: 2,332
- Full raw hash:
  `3ba48880a9df01313f70252cfcddbc9e6dee2bb62199ab465bf5c0374705fa0d`
- Catalog identity hash currently emitted by the cache layer:
  `84a5df1e2ce1fd79c98cbf2488c50c81650d28051b8c1a4205e6b736d121b613`

Important catalog artifacts:

- `results/mutation_score/full-sut/catalog/task_relevant_mutant_catalog.json`
- `results/mutation_score/full-sut/catalog/task_relevant_mutant_catalog.csv`
- `results/mutation_score/full-sut/catalog/full_sut_mutant_catalog.json`
- `results/mutation_score/full-sut/catalog/workload_traceability.csv`
- `results/mutation_score/full-sut/catalog/mutant_review.csv`

Do not regenerate or replace the formal catalog casually. All participants must use
the same catalog.

## 5. Existing Experiment-11 Results

The latest completed old-format collection for `experiment-11` is:

- Participant commit: `18f0f69f73c5dde0cb60e77dece882a6fd59b93a`
- Catalog total: 4,725
- Killed: 3,018
- Survived: 1,297
- No tests: 262
- Timeout: 148
- Eligible mutants: 4,577
- Mutation Score: `3018 / 4577 = 0.6593838759012454`
- Valid generated pytest cases: 656
- Invalid generated cases: 0 in this participant run
- Last completed collection duration: approximately 30.1 minutes
- Timeout configuration: multiplier 5, constant 0.5, one retry
- Old monolithic policy hash:
  `1a3d3a1d03396b1510831af4ad6f8bd69e4b34f370ed5ded757fad36682b9578`

The source raw result remains unchanged at:

- `results/mutation_score/full-sut/formal/raw/experiment-11.json`

The legacy list remains unchanged at:

- `results/mutation_score/full-sut/formal/confirmed_kills.json`

It contains 3,018 IDs. Do not clear or overwrite it.

## 6. Semantic Cache Implementation Completed

The previous implementation tied all reuse to one `collection_policy_hash`. A
timeout-only change therefore reset approximately 3,018 confirmations. This has
been redesigned.

### 6.1 Cache identities

`scripts/metric_collection/mutation_cache.py` now defines:

- catalog identity;
- execution context;
- execution policy;
- per-mutant reliable-kill evidence;
- timeout-aware reuse planning;
- strict legacy-result adoption and confirmation migration.

The execution context covers:

- catalog hash and catalog identity;
- SUT hash;
- valid-only test artifact hash;
- participant test-material hash;
- Python version;
- Mutmut version;
- valid-only isolation protocol.

The execution policy covers:

- timeout multiplier and constant;
- retry count;
- baseline and outer execution timeouts;
- kill-confirmation protocol;
- duplicate/equivalent handling.

`max_children` is deliberately excluded because it changes performance, not the
semantic experiment result.

### 6.2 Timeout reuse rules

- Same timeout: reuse all matching-context outcomes.
- Increased timeout: reuse killed, survived, and no-tests outcomes; rerun previous
  timeout mutants only.
- Decreased timeout: reuse only rows with a recorded duration within the new
  threshold; rerun rows over the threshold or without duration.
- Context mismatch: participant statuses are invalidated, but old artifacts and
  global reliable-kill evidence are retained as history.

### 6.3 Reliable-kill evidence

Reliable kills are stored per mutant in:

- `results/mutation_score/full-sut/formal/reliable_kill_evidence.json`

There are currently 3,018 migrated records. Each includes catalog/SUT/test context,
participant, Python and Mutmut versions, exit code, confirmation status, timestamps,
and source artifact provenance.

Legacy rows did not record duration or timeout used. These fields are `null` in
migrated evidence and the quality is explicitly marked
`verified_legacy_status_inferred_exit_code`. Do not invent missing timing data.

Evidence writes are atomic. Confirmation is persisted in small batches so an
interruption does not lose all prior confirmations. An empty new payload is not
allowed to overwrite a valid evidence artifact.

### 6.4 Cross-branch behavior

`scripts/metric_collection/collect_all_mutation_scores.py` now:

- passes the previous participant raw result into the collector;
- passes the shared reliable-evidence artifact;
- no longer initializes `confirmed_kills.json` to an empty list;
- archives replaced raw, manifest, audit, and test-review artifacts by content hash;
- records cache reuse statistics in participant results and the manifest.

### 6.5 Global analysis behavior

`scripts/metric_collection/aggregate_mutant_outcomes.py` now accepts
`--reliable-kill-evidence`. Global non-equivalence evidence is independent of the
current participant's timeout-dependent status. A participant may currently time
out or survive while a valid prior reliable kill still proves the mutant is not
equivalent.

## 7. Validation Already Performed

The metric collector test suite currently passes:

```bash
.venv-mutmut/bin/python -m pytest -q tests/metric_collection
```

Result:

```text
74 passed
```

Python compilation and focused `git diff --check` also passed. Ruff is not installed
in the current environment, so Ruff has not been run.

The tests cover at least:

1. timeout-only changes preserving reliable kills;
2. timeout increases rerunning only prior timeouts;
3. timeout decreases rerunning slow or durationless rows;
4. confirmation of only newly killed mutants;
5. participant test changes invalidating participant cache;
6. catalog/SUT changes invalidating participant cache;
7. `max_children` not invalidating cache;
8. interruption-safe evidence persistence;
9. empty output not overwriting existing evidence;
10. separation of global evidence and participant status;
11. strict participant-commit matching for legacy adoption;
12. content-addressed preservation of old artifacts.

## 8. Experiment-11 Migration Validation

An isolated no-Mutmut migration rehearsal was run against the exact
`experiment-11` commit. It rebuilt the valid-only test artifact, checked all context
information, migrated evidence, and reused the old outcomes.

Result:

- Reused participant outcomes: 4,725
- Migrated reliable kills: 3,018
- Reused reliable kills: 3,018
- Mutants rerun: 0
- Kills reconfirmed: 0
- Context-invalidated rows: 0
- Recomputed Mutation Score: `0.6593838759012454`

Reports:

- `results/mutation_score/full-sut/formal/cache_migration_report.json`
- `results/mutation_score/full-sut/formal/cache_policy_change_preview.json`
- historical migration versions under
  `results/mutation_score/full-sut/formal/history/cache-migration/`

An offline timeout-increase preview from multiplier 5 to 6 produced:

- reused results: 4,577;
- prior timeouts to rerun: 148;
- policy-affected non-timeouts to rerun: 0;
- existing reliable kills retained: 3,018;
- existing kills to reconfirm: 0.

An offline timeout decrease from multiplier 5 to 4 produced:

- reused results: 0;
- results to rerun: 4,725;
- existing reliable kills retained: 3,018;
- existing kills to reconfirm: 0.

The timeout-decrease result is intentionally conservative because all legacy
participant rows lack duration. Once duration is backfilled, later decreases can
reuse rows that completed within the new threshold.

The evidence-aware aggregation was also validated without running Mutmut:

- auto non-equivalent: 3,018;
- review candidates: 1,559;
- execution unresolved: 148.

## 9. Historical Blocker (superseded)

The code can migrate the old format and preserve reliable kills, but the old raw
participant rows do not contain:

- `duration_seconds`;
- `estimated_test_duration_seconds`;
- per-run Mutmut exit code.

These values cannot be reconstructed honestly from the old JSON. To fill them, each
of the 4,725 mutants must be executed once under the new collector. Existing 3,018
reliable kills must not be confirmed again.

A purely selective run of the existing 148 timeout mutants cannot simultaneously
backfill timings for the other 4,577 rows.

No formal timing backfill or real selective Mutmut rerun has been started yet.

## 10. Historical Implementation Plan (superseded)

### Phase A: approved cleanup

The user requested cleanup but has not yet approved the exact destructive action.
Do not delete anything until approval is received.

Proposed deletion list:

- all repository `.DS_Store` files;
- `results/mutation_score/historical-audit-threshold-0.10/`;
- `results/mutation_score/catalog-pilot/`;
- `results/mutation_score/ruler-full/`;
- `results/mutation_score/sampling-pilot-specified-plus-extended-census/`;
- `results/mutation_score/full-sut/preflight-ruler/`.

Keep:

- `.venv-mutmut/` because it is required;
- `full-sut/catalog/`, `full-sut/formal/`, and `full-sut/dry-run/`;
- legacy `confirmed_kills.json`;
- migration history;
- `metrics.json` and `tests/task/task.py` until the user explicitly identifies
  whether their uncommitted changes should be retained or reverted.

### Phase B: explicit timing-backfill mode

Add an opt-in option such as:

```text
--backfill-missing-durations
```

It should rerun matching-context rows only when duration or estimated duration is
missing. It must not be part of semantic execution policy and must never happen
silently during ordinary `--resume`.

The backfill run should:

1. archive the existing raw result;
2. run all 4,725 durationless participant outcomes once;
3. preserve and reuse the 3,018 global reliable kills;
4. skip confirmation for those old reliable kills;
5. confirm only genuinely new kills if any prior timeout/survivor changes to killed;
6. atomically write the schema-v3 raw result;
7. verify status totals and recompute Mutation Score.

Estimated duration: 15–25 minutes for `experiment-11`.

### Phase C: real selective-rerun validation

After timing backfill, change timeout in a controlled pilot and run only the affected
mutants. A timeout increase is the clearest first check: it should rerun approximately
the current 148 timeout mutants while reusing 4,577 completed outcomes and all 3,018
reliable kills.

Estimated duration: 5–10 minutes. Combined Phase B and C estimate: 20–35 minutes.

Before starting either real run, report the exact command and estimate to the user
and obtain approval. Do not start all participants.

### Phase D: review and formal collection

After the pilot succeeds:

1. inspect the new raw schema and cache statistics;
2. verify interruption/resume with a real small mutation batch;
3. obtain user approval for full cross-branch collection;
4. collect participating branches serially;
5. aggregate with the reliable-evidence artifact;
6. perform blinded equivalent-mutant review for never-killed mutants;
7. produce final Mutation Score CSV output.

## 11. Historical Cleanup and Worktree Status (superseded)

At the last check, no Mutation Score or Mutmut process was running.

Existing worktrees:

- main repository: branch `pilot-metric-mutation`;
- `/Users/ruoyur/Code/Chalmers/MasterThesis/markdown-it-py-execution` on
  `pilot-metric-execution`;
- `/Users/ruoyur/Code/Chalmers/MasterThesis/markdown-it-py-experiment-review`
  detached for participant review.

Do not remove the review worktree unless the user explicitly approves it.

## 12. Historical Git and Commit State (superseded)

The Mutation Score implementation has not been committed or pushed. The working
tree contains a large amount of accumulated work, including moved scripts and docs,
new mutation scripts/tests, generated local results, and pre-existing user changes.

Important: do not run `git add .`, do not reset the worktree, and do not commit all
changes blindly. Inspect every path and stage only the intended files.

The user explicitly requires Conventional Commits without emoji, for example:

```text
feat(metrics): add semantic mutation result caching
```

This user instruction overrides the emoji commit format in `AGENTS.md`.

Do not commit or push until the user explicitly approves the exact staged diff.

## 13. Historical Important Files (superseded)

Core implementation:

- `scripts/metric_collection/mutation_cache.py`
- `scripts/metric_collection/collect_mutation_score.py`
- `scripts/metric_collection/collect_all_mutation_scores.py`
- `scripts/metric_collection/aggregate_mutant_outcomes.py`
- `scripts/metric_collection/mutation_common.py`

Tests:

- `tests/metric_collection/test_mutation_cache.py`
- `tests/metric_collection/test_collect_mutation_score.py`
- `tests/metric_collection/test_collect_all_mutation_scores.py`
- `tests/metric_collection/test_mutation_global_review.py`
- `tests/metric_collection/test_full_sut_mutation_catalog.py`

Documentation:

- `docs/metric_collection/METRICS_COLLECTION.md`
- `docs/metric_collection/MUTATION_PILOT.md`

Current formal artifacts:

- `results/mutation_score/full-sut/formal/raw/experiment-11.json`
- `results/mutation_score/full-sut/formal/confirmed_kills.json`
- `results/mutation_score/full-sut/formal/reliable_kill_evidence.json`
- `results/mutation_score/full-sut/formal/cache_migration_report.json`
- `results/mutation_score/full-sut/formal/cache_policy_change_preview.json`

## 14. Historical Pitfalls That Must Not Be Repeated

### Never bind evidence validity to timeout policy

The original `collection_policy_hash` invalidated all reliable kills when timeout
changed. This caused approximately 3,018 unnecessary confirmations. Reuse must be
checked per mutant and per semantic context.

### Never clear the confirmation artifact at run start

The old cross-branch runner wrote an empty `confirmed_kills.json` when the policy
hash changed. A crash then risked losing all confirmation progress. Evidence must be
incremental and atomic.

### Never confuse global non-equivalence with participant outcome

A reliable kill proves a mutant is globally non-equivalent. It does not force every
participant's status to `killed`. Participant statuses remain timeout-policy-specific.

### Never invent missing duration

Legacy rows do not contain timings. Do not estimate and write fake durations. Use an
explicit one-time timing backfill.

### Never rerun all mutants for a timeout increase

For an increased timeout, only previous timeout mutants should rerun. Killed,
survived, and no-tests outcomes remain valid when context matches.

### Never reuse participant outcomes after context changes

SUT, catalog, participant valid-only tests, test materials, incompatible Python or
Mutmut versions, or isolation-protocol changes invalidate participant status reuse.
Preserve old artifacts, but do not silently treat them as current.

### Never use participant tests to define the catalog

The catalog must be fixed independently using the researcher-controlled workload.
Otherwise participants face different fault sets and scores are not comparable.

### Never treat parameterized source tests as one runtime result

The source test is one logical function for assertion reporting, but mutation and
error-rate validity operate on expanded pytest cases. Invalid parameter instances
must be excluded individually.

### Never mutate the main worktree for review

`mutmut apply` is allowed only in a disposable review worktree. Never commit mutated
SUT files.

### Never treat tool failure as score zero

No valid tests yields a Mutation Score of zero through `no_tests`. Infrastructure,
environment, or collection failures are `unavailable`, not zero.

### Never run all branches before a one-participant pilot

Full-SUT mutation is expensive. Validate schema, caching, timeout behavior, and
resume on `experiment-11` before expanding to all participants.

### Never rely only on percentage scores

Always retain the fixed catalog, per-mutant matrix, raw status, timing, evidence,
review status, and catalog/context hashes. Mutation Score without provenance is not
adequate for the thesis.

## 15. Historical Safe First Commands (superseded)

Use these read-only checks first:

```bash
git branch --show-current
git status --short
git worktree list
ps -axo pid,ppid,etime,command | \
  rg 'collect_(all_)?mutation_score|mutmut run|[ /]mutmut( |$)' || true
.venv-mutmut/bin/python -m pytest -q tests/metric_collection
```

Then read, in order:

1. this file;
2. `docs/metric_collection/METRICS_COLLECTION.md`;
3. `scripts/metric_collection/mutation_cache.py`;
4. `scripts/metric_collection/collect_mutation_score.py`;
5. `results/mutation_score/full-sut/formal/cache_migration_report.json`;
6. `results/mutation_score/full-sut/formal/cache_policy_change_preview.json`.

The immediate user decision still required is approval of the proposed deletion
list. After that, implement the explicit timing-backfill mode and report the exact
real-run command and 20–35 minute combined estimate before executing it.
