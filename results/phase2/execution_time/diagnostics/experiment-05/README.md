# Participant 05 execution-time diagnosis

Frozen participant commit: `18fd41b1b12246ff35950dd17fac7de826da9cd9`.
The participant submission and formal observations are unchanged. All interventions
were applied to temporary Git exports for diagnosis only.

The two heavyweight functions are `test_file` (205,025-byte specification) and
`test_spec` (652 CommonMark examples). Both call `md.parse(input)` and then
`md.render(input)`, although the returned `tokens` are not asserted. The frozen
SUT's `render` calls `parse` internally, so these inputs are parsed twice.
`test_spec` also constructs `MarkdownIt("commonmark")` inside the 652-iteration
loop; participant 02 instead constructs one instance outside its loop and calls
render once per input.

An initial full-pytest ablation retained three warmups and seven measurements for
four temporary variants. All executions passed, but CVs ranged from 26% to 38%
and timings drifted across variant blocks. Those results are exploratory and must
not be used to quantify attributable formal-time reductions.

A follow-up diagnostic executed only these two test bodies in one interpreter,
using randomly interleaved variant orders (seed 20261006), three predefined warmup
rounds and seven measured rounds. All assertions passed. Median body times in ms:

| Temporary variant | test_file | test_spec |
|---|---:|---:|
| Original submission | 85.35 | 121.37 |
| Remove unused standalone parse calls | 43.07 | 99.56 |
| Reuse one parser across examples | 86.65 | 41.42 |
| Apply both temporary changes | 43.96 | 22.69 |

The direct-body results exclude pytest startup, fixture machinery and all other
tests. They are supporting diagnostics, not replacements for formal execution
measurements. Reusing the parser leaves test_file unchanged by design. The two
interventions substantially reduce the corresponding workload in this diagnostic;
exact formal-time differences across participants also include other code and
system noise. No inference about relative test effectiveness follows from speed.

Evidence: `diagnostic_results.json`, `original_pytest.xml`, the four patches,
`body_diagnostic.json`, and both diagnostic runners/helpers.
