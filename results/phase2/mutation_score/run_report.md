# Final Phase 2 Mutation Score

Completed: 2026-10-05T14:15:56.637534+00:00

The primary outcome is `specified_estimated_adjusted_score` in `mutation_score.csv` (0–1 fractions). It is a stratified equivalent-adjusted estimate, not an exact census of equivalent mutants. Raw proportions and extended-only/combined results are retained in the same file.

| Participant | Raw score | Final adjusted estimate | Approximate 95% CI |
| --- | ---: | ---: | ---: |
| 02 | 68.76% | 72.46% | 70.27%–74.79% |
| 03 | 69.50% | 73.24% | 71.03%–75.60% |
| 04 | 69.75% | 73.50% | 71.28%–75.87% |
| 05 | 69.22% | 72.95% | 70.74%–75.30% |
| 07 | 69.63% | 73.38% | 71.16%–75.75% |
| 08 | 69.48% | 73.22% | 71.01%–75.58% |
| 09 | 68.63% | 72.33% | 70.14%–74.67% |
| 12 | 69.67% | 73.42% | 71.20%–75.78% |

The corrected full-SUT inventory has 7,520 mutants; reference coverage selects 5,051 task-relevant mutants (5,045 specified and six extended-only). All eight frozen participants completed execution using the same 58 valid test instances as error rate and coverage. Timeouts are retried once and then excluded from each eligible denominator; 175 mutants time out for every participant. No timeout is treated as an equivalent mutant.

Global independent kill evidence establishes 3,407 non-equivalent mutants. The remaining 1,469 candidates form the frozen stratified review frame. Seed 20261005 selects 100 mutants by workload layer and operator family. Source review confirms 16 equivalent invariants and 84 non-equivalent behavioral witnesses. Horvitz–Thompson weighting estimates equivalent counts; the reported intervals use the reused worst-case finite-population variance bound and normal approximation. The preplanned four-look Bonferroni stopping interval uses 98.75% confidence and has maximum primary half-width 0.029254, meeting the 0.05 target without expansion.

Review method: one Codex source reviewer with executable semantic counterexamples; no independent secondary review or agreement statistic. Matching probes alone were never used as an equivalence proof. Confidence intervals reflect sampling uncertainty, not potential review error. Full decisions and concrete witnesses are in `global/equivalent_review_sample_stage1/`.

Participant 08 was fully rerun with one worker because its fixed output.html was unsafe under parallel mutation execution. One prior killed/flaky observation changes to survived; the final run has zero flaky kills. Invalid parallel observations and the original incorrect coordinate scope are preserved in history, but do not define the final result. The final collector defaults to one worker and enforces serial execution for 08.

The shared source mapper originally misaligned top-level functions, leading comments and overload declarations. All 7,520 patches now have a unique verified source alignment; two independent corrected scope derivations agree. Phase 1 archived results were not modified and must have their scope rechecked before a cross-phase Mutation Score comparison.

Reproduction and input identities: see `final/finalization_manifest.json`, `formal/collection_manifest.json`, `catalog/source_mapping_correction.json`, `parallel_file_race_correction.json`, and the tracked Phase 2 mutation methodology document. Relevant collection tests: 189 passed.

Publication: the canonical catalogs, final outputs, formal raw/audit records, global aggregation and final review artifacts are committed. Historical runs, migration caches, provisional review preparation and the disposable review-source checkout remain local and ignored. The review source can be reconstructed from the recorded baseline Git commit.
