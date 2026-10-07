# Phase 2 mutation collection

Current status (2026-10-07): eight-participant finalization is complete. The
corrected task-relevant catalog contains 5,051 mutants; the 100-mutant review sample
has 16 confirmed equivalent and 84 non-equivalent decisions. Review used one Codex
source reviewer without independent secondary review. See
[collection status](COLLECTION_STATUS.md). Intermediate records below retain
their historical scope.


## Frozen inputs and reuse

The eight participant commits and 58 valid instances come from the final frozen
error-rate evidence. Participant tests retain original paths, including participant
08's relocated CLI test. Reference workloads only define catalog task membership;
they are never included in participant mutation scores.

Mutmut 3.7.0 and Python 3.11.6 are reused from the existing mutation environment.
Phase 1's catalog generation, diff normalization, source mapping, execution,
timeout retry, independent kill confirmation and cache/evidence implementations
are reused. Phase 2 adapters supply relocated materials, changed CLI behavior,
ordered core-rule checks and fence factory after/at requirements.

The catalog builder scopes compatibility hooks to its invocation; it does not
modify the Phase 1 reference workload files. It records all five reference/support
file hashes, including the imported Phase 1 reference modules. Traceability is
updated for Phase 2. The references include all provided CommonMark examples.

The participant engine has an optional `--original-nodeids` input. Without it, the
existing Phase 1 isolated-file behavior is unchanged. With it, the complete original
test tree is copied but only the frozen valid node IDs are selected. It rejects
missing/extra/duplicate node IDs and invalid paths. The execution context uses
`phase2_original_paths_valid_instances_v1` and hashes the original test tree,
resources, selected instances and catalog. Old Phase 1 catalogs or kill caches are
not imported into the Phase 2 output tree.

## Execution stages

1. Reference workload preflight on the common Phase 2 SUT.
2. A bounded dry-run of `ruler.py` and `rules_block/fence.py` for mapping and tool
   checks. Its catalog is not the formal full-SUT catalog.
3. Full-SUT generation twice, requiring matching semantic catalog hashes, input
   hashes and deterministic coverage membership. Derive specified/extended-only
   task-relevant census from the complete inventory.
4. A 30-mutant module/operator round-robin pilot for participants 02 and 08. This
   deterministic execution pilot is not a probability sample or score estimator.
5. If pilot execution succeeds, full task-relevant execution for all eight frozen
   submissions. The final participant run uses one worker child, timeout multiplier 5,
   constant 0.5 seconds, one retry of timeouts and independent kill confirmation.
6. Global aggregation and equivalent-mutant assessment produce the
   final adjusted Mutation Score. Survivors are not automatically equivalent;
   timeout and infrastructure failures must not be silently counted as valid kills.

Each participant has a persisted log and result; the stage manifest is updated
before and after execution. Confirmed reliable-kill evidence is saved incrementally
by the reused engine. Matching successful participant results can resume through
the existing context and policy validation. Raw mutation summaries remain execution
results until the global equivalence step is completed.

## Commands

```bash
python scripts/metric_collection_phase2/build_mutant_catalog.py \
  --mutmut-python /path/to/mutation-environment/bin/python \
  --full-sut --max-children 4

python scripts/metric_collection_phase2/run_mutation_collection.py \
  --python /path/to/mutation-environment/bin/python
```

The second command waits up to one hour for the reproducible catalog if generation
is still running, then executes pilot and formal stages in order. It stops if a
stage fails. Progress is in `results/phase2/mutation_score/pipeline_status.json` and
stage `collection_manifest.json` files. Generated mutation work data remains ignored
by Git, as in Phase 1; scripts and documentation are tracked separately.

## Final adjusted score

```bash
python scripts/metric_collection_phase2/finalize_mutation_score.py --prepare-review
# Apply completed source-review decisions using the recorded review method:
python scripts/metric_collection_phase2/finalize_mutation_score.py
```

The finalizer requires exactly the eight completed formal submissions and matching
catalog, SUT, baseline and execution-policy identities. Flaky kills and unresolved
infrastructure outcomes prevent finalization. Mutants that time out for all eight
participants are already outside every participant's eligible denominator; they
remain in the unresolved audit and need no equivalence label for scoring. The
finalizer accepts this case only after checking all eight statuses are `timeout`.
It makes no claim about their semantic equivalence. The global pool excludes mutants with
reliable confirmed kills; the remaining candidates receive a reproducible
workload-layer/operator stratified sample and source-based equivalence review.

The frozen protocol uses seed 20261005, an initial sample of 100, at least two
per stratum, and planned sample sizes 100, 150, 225 and 313. The reused Phase 1
estimator applies probability weights and reports nominal 95% confidence intervals.
Its stopping rule uses intervals adjusted for the four planned looks and requires
half-width at most 0.05 for every participant's primary specified-workload score.
The finalizer refuses export when this criterion is unmet. Survivors alone are
not evidence of equivalence.

To expand, run `--prepare-review --review-sample-size 150` (then 225 or 313
if needed), complete the expanded review, and finalize with the same
`--review-sample-size`. Each stage has a separate review directory and uses the
same frozen global frame and sampling seed. Carry forward prior review decisions
only for matching mutant IDs and unchanged catalog identities; new rows require
review. Expanded templates are initially blank and do not invent decisions.

The final result is `results/phase2/mutation_score/mutation_score.csv`, accompanied
by estimation details and a source-hash manifest in `final/`. Specified is the
primary scope; extended-only and combined scopes remain supplementary. These are
equivalence-adjusted estimates, not an exact census of equivalent mutants.

## Initial launch on 2026-10-05 (historical)

Reference preflight passed all 675 cases. The bounded dry-run completed with 288
raw mutants, 227 task-relevant mutants (224 specified and 3 extended-only), no
normalization failures and zero source-mapping failures. The reused dry-run report
contains a legacy Phase 1 participant-count budget estimate; that estimate is not
the Phase 2 eight-person execution budget.

Full-SUT two-generation catalog collection and the waiting pilot/formal coordinator
were started at that time. This launch record precedes the completed finalization
described below; use the final manifest and CSV for current results.

## Verified source-mapping correction

Source review found that the reused mapper treated top-level `x_function__mutmut_N`
names as module mutations. It also ignored leading comments in Mutmut function
diffs and treated overload declarations as competing implementations. These errors
affect coverage-based scope even when the mutant execution itself is valid.

The shared helper now recognizes top-level functions, selects the implemented
method rather than `@overload` stubs, and verifies every old-side diff hunk against
the frozen source. All 7,520 original mutants have a unique verified alignment.
`repair_mutant_catalog.py` reuses the twice-generated exact name/diff inventory and
repeats both reference coverage runs and the corrected derivation independently.
Both derivations match; no new mutation bodies are generated.

The corrected census contains 5,051 task-relevant mutants: 5,045 specified and six
extended-only. Compared with the coordinate-v1 census, 4,393 executable mutants
remain, 658 enter the scope, and 557 are excluded. Coordinate-v1 artifacts are
preserved under `history/source_mapping_v1/` and do not define the final scores.

`migrate_corrected_mutation.py` requires identical mutant names, modules, diffs,
SUT, baseline, tool/runtime, reference inputs and participant test contexts. It
preserves the old observations and proof identities with explicit migration
provenance; missing observations remain unexecuted placeholders. The reuse planner
rejects unavailable and flaky rows even under an unchanged execution policy.
Each participant therefore reruns 658 new mutants; participant 08 additionally
reruns its three flaky observations. Migration caches and original history remain
available to audit every reused result. Final summaries are recomputed from the
corrected catalog, never copied from the coordinate-v1 summaries.

Phase 1 archived scores have not been modified. Their scope should be rechecked
before using them in a cross-phase Mutation Score comparison.


## Shared-file execution correction

Participant 08's frozen `test_file` writes a fixed `output.html`. Parallel mutant
processes in the same working directory can overwrite this file. All of 08's
parallel outcomes were invalidated and archived under
`history/parallel_file_race_v1/`; the complete corrected 5,051-mutant catalog was
rerun serially, including timeout retries and independent kill confirmation.
The other seven participants use independent temporary files and their matching
observations remain reusable. The correction and proof-cache filtering are in
`parallel_file_race_correction.json`. No participant tests were edited.

The Phase 2 collector defaults to one worker and forces participant 08 to one
worker even when a larger worker count is requested. The final formal manifest
records the worker count; the source actually used for its serial run is retained
in `formal/collector_source/`. Reference catalog generation can still use four
workers because its researcher workloads have independent temporary paths.

## Primary source review

`semantic_probe_workload.py` and `probe_mutant_semantics.py` compare fresh frozen
SUT copies with the exact sampled catalog patches. They cover CommonMark HTML and
public tokens, presets, helpers, parser states, supported block plugins, custom
renderers and enabled DEBUG logging. These researcher witnesses never enter the
participant test pool or kill numerator. A difference is inspected as a concrete
non-equivalence witness; matching finite probes alone cannot establish equivalence.
Equivalent labels require an all-input source invariant recorded in the decisions.

`apply_primary_mutant_review.py` validates explicit source decisions against the
actual frozen sample and exact patch hashes. It records empty secondary-review
columns, `primary_source_review_only`, and no agreement statistic. This documents
a single Codex reviewer; no independent secondary review is implied.


## Final collection (2026-10-05)

All eight participants completed the corrected formal catalog. Participant 08's
serial run replaces every unsafe parallel observation and has zero flaky kills;
one previously killed/flaky observation is now survived. The final sample matches
the prepared source-review IDs and exact patch hashes, so valid semantic witnesses
are reused with their original source hash rather than rerun unnecessarily.

The global frame contains 3,407 automatically witnessed non-equivalent mutants,
1,469 review candidates and 175 all-participant timeouts. The fixed 100-mutant
sample resolves to 16 confirmed equivalents and 84 non-equivalents. All primary
stopping intervals meet the predeclared precision target; maximum half-width is
0.029254. No sample expansion was needed. The final primary adjusted estimates
range from 0.723320 to 0.735024. These are sampling-based estimates with approximate
95% intervals; the 98.75% stopping intervals account for four planned looks.
Intervals describe sampling uncertainty and do not include possible review error.

The final CSV is `results/phase2/mutation_score/mutation_score.csv`; interpretation,
per-participant values, corrections and review limitations are in the generated
`run_report.md`. `final/finalization_manifest.json` records completion and output
hashes. Relevant collection tests pass (189 cases); mutation adapters and review
utilities pass targeted Ruff and strict Mypy checks. Frozen reference workloads
retain their exact collection bytes and intentional test re-export aliases.


The committed result bundle includes canonical catalogs, formal raw/audit records,
execution manifests and proof evidence, global aggregation, final source-review
artifacts, and final estimates. History, migration caches, provisional review
preparation and the disposable baseline checkout remain local and ignored.
Historical-path references in correction metadata describe those local archives;
they are not required to read or reproduce the final result from frozen inputs.
