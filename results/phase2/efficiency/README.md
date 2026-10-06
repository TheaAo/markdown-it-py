# Phase 2 efficiency

All eight continuing participants used Copilot. These are derived metrics from
frozen evidence; no participant tests, coverage or mutation campaigns are rerun.
The same six ratios as Phase 1 are reported:

| Output | Numerator | Denominator |
|---|---|---|
| Statement generation efficiency | Participant-only statement coverage | Total task time in seconds |
| Branch generation efficiency | Participant-only branch coverage | Total task time in seconds |
| Mutation generation efficiency | Specified adjusted Mutation Score | Total task time in seconds |
| Statement execution efficiency | Participant-only statement coverage | Median execution time in seconds |
| Branch execution efficiency | Participant-only branch coverage | Median execution time in seconds |
| Mutation execution efficiency | Specified adjusted Mutation Score | Median execution time in seconds |

Scores use fractions from 0 to 1. Coverage is reconstructed from exact covered/total
counts in the frozen manifest to avoid propagating the six-decimal CSV rounding.
The baseline project's own tests and combined coverage are not used as numerators.
Generation time includes comprehension, maintenance, new test development and
debugging, as specified by the researcher. It is not a per-task-group duration.

`generation_efficiency.csv` and `execution_efficiency.csv` preserve scores,
denominators, phase-1 origin group, phase-2 group, participant SHA and valid count.
Execution denominators use the researcher's latest `new-run`, promoted unchanged
to `../execution_time/formal/`. The eight medians are 0.209486583, 0.192340542,
0.211481625, 0.344106625, 0.205841291, 0.211854083, 0.270549042 and 0.210641500
seconds in ascending participant order. All CVs are below 5%; their actual values,
review flags and Q1/Q3 remain in the output. No participant-specific best values
are selected and no timing datasets are pooled.

Mutation efficiency interval bounds divide the score's approximate 95% bounds
by a fixed observed time. Their names include `conditional`: they describe only
Mutation Score estimation uncertainty. They do not include execution-time
uncertainty or self-reported task-time uncertainty and are not complete efficiency
confidence intervals. The underlying Mutation Score retains its single-reviewer
limitation. No new inferential significance or causal AI comparisons are claimed.

Task-group efficiencies are unavailable because separate group durations were not
collected. Using full-suite time for maintenance-only or generation-only scores
would define a different metric. The current outputs describe the complete valid
participant suite. Cross-phase interpretation also requires accounting for SUT,
workload, Python environment and test-layout differences.

`collection_manifest.json` records SHA-256 hashes of every input and output,
identity checks and the numerator/denominator policies. Before writing output the
collector checks matching baselines, frozen validity manifests, participant commits,
cohort IDs, valid counts, mutation catalog and generation-time conversions. Missing
or nonpositive durations are not converted to zero efficiencies.

Reproduce from the repository root:

```bash
python scripts/metric_collection_phase2/collect_efficiency.py
```

The default inputs are the Phase 2 coverage and mutation manifests, generation-time
CSV, and authoritative `execution_time/formal/collection_manifest.json`. Only the
derived efficiency outputs are written. Source inputs are left unchanged. To use
another explicitly selected complete timing dataset, supply `--timing-dir` and a
separate `--output-dir`; do not silently replace the authoritative denominator.
