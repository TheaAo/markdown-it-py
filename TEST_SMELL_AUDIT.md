# Test Smell Collection Audit

## Scope

This audit was performed after freezing AST rule version `1.0.0`. It checked the
source at each participant commit recorded by the Error Rate dataset. The audit did
not execute participant code and did not change individual results.

All 22 confirmed `(source test, smell type)` pairs were compared with the frozen
rule definitions. Representative no-detection boundaries were also inspected:
framework exception contexts, required exit codes `0` and `1`, repeated use of one
production method, multiple assertions over one result, and parameter expansion of
one source assertion. No protocol deviation was found, so no rule version change
or participant rerun was required.

This is a protocol-conformance audit by the collection workflow, not an independent
blinded accuracy study. The pilot limitation therefore still applies.

## Confirmed pairs

| Participant | Source test | Confirmed smell types |
|---|---|---|
| 01 | `test_spec` | Conditional Test Logic |
| 01 | `test_non_utf8` | Assertion Roulette |
| 02 | `test_spec` | Conditional Test Logic |
| 03 | `test_spec` | Conditional Test Logic |
| 05 | `test_spec` | Conditional Test Logic |
| 05 | `test_non_utf8` | Assertion Roulette; Exception Handling |
| 07 | `test_spec` | Conditional Test Logic |
| 08 | `test_file` | Conditional Test Logic |
| 09 | `test_parse_fail` | Unknown Test; Conditional Test Logic |
| 09 | `test_non_utf8` | Unknown Test; Exception Handling |
| 10 | `test_spec` | Conditional Test Logic |
| 11 | `test_non_utf8` | Assertion Roulette |
| 12 | `test_spec` | Conditional Test Logic |
| 12 | `test_parse_fail` | Assertion Roulette |
| 14 | `test_parse_fail` | Unknown Test |
| 16 | `test_spec` | Unknown Test; Conditional Test Logic |
| 16 | `test_core_after` | Unknown Test |
| 16 | `test_parse_fail` | Assertion Roulette |

The table contains 18 smelly source tests and 22 distinct smell pairs. There were
no Magic Number Test, Eager Test, or Duplicate Assert confirmations under the
frozen rules.

## Aggregate check

Across the 14 participating submissions, 50 source tests were eligible. The
collection contains:

```text
Smelly Test Rate      = 18 / 50       = 0.36
Mean Smells per Test  = 22 / 50       = 0.44
Test Smell Density    = 22 / (50 * 7) = 0.06285714285714286
Uncertain pairs       = 0
```

Participants 04 and 06 have zero eligible source tests. Their aggregate values are
`null`, not zero.
