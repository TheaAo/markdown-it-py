# Phase 2 assertion score

## Inputs and reuse

`scripts/metric_collection_phase2/collect_assertion_score.py` consumes the frozen
Phase 2 error-rate manifest and raw reports. It exports the same participant
commits, verifies recorded source/material hashes and uses existing instance
classifications. It does not execute tests again or change participant code.

The Phase 1 `_report_from_results` AST analyzer is reused without modifications.
The adapter passes the actual selected function names for each file, rather than
the Phase 1 five-function default. This includes the relocated non-UTF8 test in
`tests/test_cli.py` without analyzing untouched upstream CLI tests. File path plus
function name provides a unique source identity, even when names repeat across files.

## Counting and interpretation

Each submitted source function is counted once. A parameterized function with
at least one valid instance is eligible; mixed valid/invalid instances are retained
as `partially_valid`. Functions with no valid instance are excluded from the score
denominator and recorded as invalid. Commented declarations without test bodies
remain missing-submission records rather than invented source functions.

`assertion_score = non_trivial_test_count / eligible_test_count`.
Classification precedence and evidence rules are unchanged from Phase 1:
non-trivial, uncertain, trivial, then assertionless. A function is non-trivial when
the analyzer identifies at least one non-trivial oracle. An empty eligible pool has
an unavailable score. Missing expected tasks do not become passing tests, and extra
tests cannot establish task completion.

Whole-suite, per-file and maintenance/new-generation/retained-legacy/additional group
summaries are preserved. The raw records include generated node IDs, source validity,
assertion counts, line-numbered evidence and reasons. CSV scores are fractions
between 0 and 1, rounded to six decimals.

`uncertain` means the static analyzer could not establish the relevant dependency;
it does not establish that the oracle is ineffective. As in Phase 1, uncertain
functions remain in the eligible denominator but do not enter the non-trivial
numerator. Scores are automated results pending review of these cases, rather than
manual judgments of requirement satisfaction. A passing runtime test is also not
proof of a useful oracle.

## Reproduce

```bash
.tox/py311/bin/python scripts/metric_collection_phase2/collect_assertion_score.py
```

Only Python and the existing repository analyzer are needed for this static step.
Use a new `--output-dir` for another run; existing output directories are protected.
Outputs are `collection_manifest.json`, `assertion_score.csv` and per-participant
`raw/` records. Collector source, input manifest and input raw hashes are recorded.
`review_candidates.csv` is an additional audit export derived from raw records in
this collection: it lists uncertain and trivial functions with their unchanged
automated classifications and pending review status. It does not override scores.

The final CSV now applies the frozen adjudications by default when
`manual_review/adjudications.json` exists. `--adjudications` can select another
review file. Commit and original-classification mismatches fail the export.
Manifest `summary` and raw records preserve automated evidence; `final_summary`
and the final CSV include reviewed decisions. The pre-review CSV was deleted.

## Collection on 2026-10-05

All eight participants were collected at the same commits as error rate and
coverage. This dataset contains 58 source functions and 58 valid instances:
52 non-trivial, 2 trivial and 4 uncertain. There are no invalid, assertionless or
partially valid functions in the current cohort. Participant 08's omitted
`test_parse_fail` remains separately recorded.

| Participant | Non-trivial / eligible | Automated score |
| --- | --- | --- |
| 02 | 7 / 7 | 1.000000 |
| 03 | 6 / 7 | 0.857143 |
| 04 | 7 / 7 | 1.000000 |
| 05 | 6 / 7 | 0.857143 |
| 07 | 7 / 7 | 1.000000 |
| 08 | 5 / 8 | 0.625000 |
| 09 | 7 / 8 | 0.875000 |
| 12 | 7 / 7 | 1.000000 |

The four uncertain functions are participant 03's `test_core_after`, participant
08's `test_file` and `test_core_after`, and participant 09's `test_core_after`.
Their evidence reports unclear SUT-to-assertion dependency and needs manual review.
The two trivial classifications are participant 05's `test_parse_fail` (asserting
the truthiness of a `pytest.raises` context object without executing a SUT call)
and participant 08's `test_default_fence_exists` (a callable check classified
trivial by the existing dependency analysis). Both are included in the audit export.

## Source review on 2026-10-05

Codex inspected the four uncertain functions and ran targeted execution probes in
temporary frozen snapshots. All four were adjudicated `non_trivial`; the analyzer
missed callback side effects or file write/read dependencies. The automated data
above remains unchanged. `assertion_score.csv` contains the adjusted
scores with the original automated scores retained. See
[source review and limitations](ASSERTION_SCORE_REVIEW.md), including participant
08's file-length oracle defect and the preserved verification evidence.
