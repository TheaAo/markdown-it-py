# Reducing Equivalent-Mutant Review Effort

Date: 2026-09-15

## Scope

This note evaluates ways to reduce manual review of the 1,684 globally surviving
mutation candidates after full execution has already completed. It is a research
note, not a change to the frozen collection or current statistical protocol.

The key distinction is between:

- reducing mutant generation or execution, which no longer saves work in this
  completed study; and
- reducing the number of human equivalence judgements while retaining an explicit
  statistical estimand and uncertainty interval.

## Conclusion

Reviewing 313 distinct candidates is not the only defensible design. That number is
the finite-population, worst-case planning size for estimating one proportion with
95% confidence and a margin of error of five percentage points. It is deliberately
conservative because it assumes an equivalent-mutant proportion of 0.5.

The most defensible lower-effort design for this study is:

1. Run a bounded, reproducible differential-witness campaign before sampling.
   Stable distinguishing inputs prove global non-equivalence; a failed search leaves
   a candidate `unknown`.
2. Start with a probability sample of 100 candidates, retaining the existing
   workload-layer and operator-family strata.
3. Make the maximum half-width of the pre-specified participant Mutation Score
   intervals the stopping criterion, rather than requiring a five-point interval
   for the overall equivalent proportion.
4. Estimate within-stratum variances after the first stage and allocate any added
   sample using a valid two-phase or Neyman allocation. Use pre-specified looks and
   simultaneous/sequentially valid intervals.
5. Use one primary reviewer for all sampled candidates. Require executable witness
   evidence for non-equivalence where obtainable; send all proposed-equivalent and
   uncertain cases to a second independent reviewer. Alternatively, double-code a
   random quality-control subsample and report the resulting agreement and
   misclassification sensitivity explicitly.

This design does **not** guarantee that 100 will be enough. It makes 100 the first
formal look and adds review only if the actual participant-score intervals require
it. A hard cap below 300 requires either wider target intervals or an explicit
decision that residual uncertainty is acceptable.

## Implemented Outcome

The pre-specified 100-mutant first look was completed on 2026-09-15. The primary
review classified 12 mutants as `confirmed_equivalent` and 88 as
`non_equivalent`. An independent second reviewer re-examined all 12 proposed
equivalents and ten deterministically selected non-equivalent quality-control rows;
there were no disagreements and the quality-control raw agreement was 1.0. Because
the second-review workload was targeted, full-sample Cohen's kappa is not claimed.

The design-weighted estimate is 214.885 equivalent mutants in the 1,684-mutant
review frame, or an estimated proportion of 0.127604. The conservative nominal 95%
count interval is 50.792--378.978. More importantly for the pre-specified primary
endpoint, the largest Bonferroni-adjusted stopping half-width across specified-layer
participant scores is 0.033405. This meets the 0.05 stopping target at the first
look, so the sample is not expanded to 150, 225, or 313.

## What Large Studies Actually Do

### Probability sampling rather than a census

Kushigian et al. manually classified 1,992 mutants sampled from seven projects,
rather than classifying the complete population of 1,193,633 mutants. Their target
was a per-project equivalent-mutant rate with 95% confidence and a 2.5-percentage-
point margin. They used test execution to create uncovered, covered-and-killed, and
covered-and-live strata, then used optimal allocation to reduce variance. A killed
mutant's equivalent-mutant rate is known to be zero, so separating that stratum
substantially reduced the amount of manual work. The work still took more than 160
hours, averaging five minutes per mutant. Each project had one assigned coder, and
only the roughly 2% of uncertain cases were resolved through discussion
([paper](https://homes.cs.washington.edu/~rjust/publ/equi_mutants_ems_issta_2024.pdf),
[DOI](https://doi.org/10.1145/3650212.3680310)).

This is the closest direct precedent for the present study. However, its largest
variance reduction came from giving already-killed mutants a known equivalent rate
of zero. The present frame has already applied the analogous reduction: 3,041
reliably killed mutants were removed, leaving only 1,684 live candidates. Therefore,
the same paper supports sampling and optimal allocation, but it does not imply that
its sample fractions can be copied directly to this survivor-only frame.

Schuler and Zeller likewise did not census all survivors. They manually classified
a sample of 140 surviving mutants across seven Java programs. Classification took
about 15 minutes per mutant on average. Their coverage-impact classifier achieved
75% precision and 56% recall, which is useful for prioritisation or stratification
but is not accurate enough to assign equivalent labels automatically
([paper](https://www.st.cs.uni-saarland.de/publications/files/schuler-stvrbis-2013.pdf),
[DOI](https://doi.org/10.1002/stvr.1473)).

Yao, Harman, and Jia manually analysed 1,230 mutants from 18 programs and found that
equivalence and stubbornness were distributed very unevenly across mutation
operators. This supports operator-aware strata and pilot-informed allocation rather
than a single uniform sample
([paper](https://citeseerx.ist.psu.edu/document?doi=a1c60549ab872c0dbb1aaa5f5f8d1ea07f161bda&repid=rep1&type=pdf),
[DOI](https://doi.org/10.1145/2568225.2568265)).

### Small samples with explicit uncertainty

Gopinath et al. evaluated random mutant sampling on 158 Java projects. For raw
Mutation Score, samples of 100 mutants had a mean absolute error of 2.56% and an
empirical 95% error range of approximately plus or minus 7.2 percentage points.
Samples of 1,000 had a mean absolute error of 0.62%. The authors emphasise confidence
reporting and present probabilistic, rather than exact, treatment of remaining
equivalence
([paper](https://stairs.ics.uci.edu/papers/2015/How_hard_does_mutation_analysis_have_to_be_anyway.pdf),
[DOI](https://doi.org/10.1109/ISSRE.2015.7381815)).

Those numerical results cannot be transferred directly: they concern raw Mutation
Score across other projects, while this study estimates an equivalent-adjusted score
from a survivor-only frame. They do show that 100 is a literature-supported first
stage, provided that this study computes and reports its own design-based intervals.

Cornejo, Pastore, and Briand use fixed-width sequential confidence intervals: sample
mutants iteratively and stop when the interval reaches its specified width. Their
experiments compare proportional, fixed-size, and sequential sampling on systems
with thousands to tens of thousands of mutants. This supplies a direct mutation-
analysis precedent for reviewing in stages rather than committing to a maximum
sample in advance
([paper](https://orbilu.uni.lu/bitstream/10993/47861/1/Cornejo-MutationAnalysis-TSE.pdf),
[DOI](https://doi.org/10.1109/TSE.2021.3107680)).

Applying sequential sampling to manual equivalence labels is an inference from their
execution-sampling design. Optional stopping must still be handled by pre-specified
looks, alpha spending, a confidence sequence, or another method with simultaneous
coverage; repeatedly inspecting ordinary 95% intervals is not sufficient.

### Common but weak shortcuts

Some mutation-selection experiments classify every mutant not killed by the
available test pool as equivalent. Zhang et al. explicitly report this as a
construct-validity threat. Their 5% sampling result primarily reduces mutant
execution, which has already occurred here
([paper](https://lingming.cs.illinois.edu/publications/ase2013.pdf),
[DOI](https://doi.org/10.1109/ASE.2013.6693070)).

Accordingly, treating all 1,684 survivors as equivalent would be inexpensive but
would not be an accurate equivalent-adjusted analysis.

## Smaller Sample Sizes and Their Trade-offs

For a finite population of 1,684 candidates, a 95% normal-approximation planning
calculation with worst-case proportion 0.5 gives the following single-proportion
sample sizes:

| Desired half-width | Approximate sample |
| --- | ---: |
| 5 percentage points | 313 |
| 6 percentage points | 231 |
| 7 percentage points | 176 |
| 7.5 percentage points | 156 |
| 8 percentage points | 138 |
| 10 percentage points | 91 |
| 12 percentage points | 65 |

These figures answer only, "How precisely is the overall equivalent proportion
estimated under the worst case?" They do not answer the study's more relevant
question, "How precisely is each participant's adjusted Mutation Score estimated?"

A read-only sensitivity calculation using the frozen participant matrix shows why
this matters. Around an equivalent proportion of 0.5, uncertainty of plus or minus
10 percentage points in the candidate equivalent rate translates to at most about
3.3 percentage points of uncertainty in a primary specified-layer participant score;
participants 04 and 06 remain exactly zero under `no_tests`. This is an approximate
diagnostic, not a replacement for the stratified estimator. It indicates that the
313-mutant overall-proportion target is likely stricter than needed for a five-point
participant-score target.

A second read-only calculation ran the implemented stratified estimator against the
frozen participant matrix and deterministic seed under three planning scenarios:
none, half, or all of the sampled candidates are equivalent. For a four-look plan,
the largest 98.75% Bonferroni stopping half-width across primary participant scores
was:

| First-look sample | None equivalent | Half equivalent | All equivalent |
| --- | ---: | ---: | ---: |
| 75 | 1.88 pp | 5.31 pp | 6.24 pp |
| 100 | 1.59 pp | 4.40 pp | 5.34 pp |
| 125 | 1.39 pp | 3.93 pp | 4.68 pp |
| 150 | 1.25 pp | 3.56 pp | 4.22 pp |

Thus 100 is a reasonable low-cost first look but is not guaranteed to stop: the
all-equivalent planning extreme remains slightly above five points. A 125-item first
look meets the target in all three planning extremes under the current estimator and
matrix. These are design diagnostics, not estimates of the true equivalence rate.

The actual sample requirement depends on the observed equivalent rates within the
strata. A small first stage provides those variance estimates. If rates are far from
0.5 or concentrate in a few operator families, optimal allocation can substantially
reduce the second-stage sample. If rates remain near 0.5 throughout all important
strata, the study must either review more candidates or accept wider intervals.

## Automatic Reduction Before Human Review

### Differential witnesses

Any reproducible input for which the original and mutant programs have observably
different behaviour is a sound certificate of non-equivalence. Researcher-controlled
CommonMark examples, grammar-based fuzzing, and property-based inputs can therefore
remove candidates from the manual-equivalence frame. Generated inputs are global
classification evidence only; they must not be added to participant test suites or
used to change participant kill outcomes.

This route is asymmetric: finding a witness proves non-equivalence, but failing to
find one proves nothing. It is attractive for this Python parser because it avoids
having to model all Python semantics.

### Restricted equivalence proofs

Papadakis et al.'s Trivial Compiler Equivalence compares optimised object code. In
their C experiments it eliminated more than 7% of all mutants as equivalent and more
than 21% as duplicates, and detected approximately 30% of manually known equivalent
mutants
([paper](https://mpapad.github.io/publications/pdfs/ICSE2015B.pdf),
[DOI](https://doi.org/10.1109/ICSE.2015.103)).

Medusa encodes a restricted subset of JVM bytecode as SMT constraints. A satisfiable
query yields a non-equivalence witness; an unsatisfiable query proves equivalence for
the supported model. Its prototype supports loop-, heap-, and call-free programs
using primitive types, with only limited references and calls
([paper](https://homes.cs.washington.edu/~rjust/publ/medusa_icst_2019.pdf),
[DOI](https://doi.org/10.1109/ICSTW.2019.00035)).

The recent Equivalent Mutant Suppression study implemented ten targeted Java static
analyses and detected about 29% of equivalent mutants in its ground-truth set. The
authors manually validated suppressed ground-truth mutants, while also acknowledging
that not every rule had a formal soundness proof. This is promising evidence for
language- and context-specific patterns, not a ready-made Python proof system
([paper](https://homes.cs.washington.edu/~rjust/publ/equi_mutants_ems_issta_2024.pdf)).

For this repository, a Python AST, bytecode, or SMT rule should therefore remove a
candidate only when its supported subset and soundness assumptions are explicit and
validated. Otherwise its result must remain `unknown`. Building a broad Python
equivalence engine solely to save this review is unlikely to be the lowest-effort
option.

### Machine-learning and LLM triage

Tian et al. evaluated LLM-based classifiers on 3,302 Java mutant pairs. Fine-tuned
representations outperformed comparison classifiers, but prompting produced 176 and
65 unique incorrect detections in the zero- and few-shot settings. These are
predictive classifiers, not semantic proofs
([paper](https://arxiv.org/abs/2408.01760),
[DOI](https://doi.org/10.1145/3650212.3680395)).

An LLM or learned model may rank candidates, suggest inputs, or define sampling
strata. Its verdict must not be used as an automatic equivalent label. If model-based
oversampling is used, inclusion probabilities and design weights must account for it.

## Methods That Do Not Solve This Post-execution Problem

Dynamic mutant subsumption and minimal-mutant sets describe redundancy relative to
an observed test set. Ammann, Delamaro, and Offutt explicitly distinguish dynamic
subsumption from the all-input relation; an observed relation can change when tests
change. Identical kill vectors therefore cannot prove semantic equivalence
([paper](https://www.albany.edu/faculty/offutt/research/papers/MiniMutant-ICST2014.pdf),
[DOI](https://doi.org/10.1109/ICST.2014.13)).

Selective operators, higher-order mutants, mutant prioritisation, and learned
mutation operators can reduce future generation and execution. They change the
mutant population, however, and cannot retrospectively provide equivalent labels for
the already frozen first-order catalogue. Gopinath et al. additionally found that
the theoretical improvement available to mutation-reduction strategies over random
sampling was limited in their real-world subjects
([paper](https://agroce.github.io/icse16.pdf),
[DOI](https://doi.org/10.1145/2884781.2884787)).

These approaches can be reported as sensitivity analyses or future protocol choices,
but they should not replace the current estimand silently.

## Recommended Decision for This Study

Replace the planned first look of 313 with a staged design whose first look contains
100 distinct candidates. Preserve all 313 previously selected candidates as the
nested reserve, so no generated work or reproducibility information is lost. A
reasonable pre-specified sequence is 100, 150, 225, and 313, with a simultaneous
coverage adjustment across looks. Stop as soon as every primary specified-layer
participant score meets the chosen half-width; do not require the overall equivalent
proportion to meet the same width unless it is itself a primary thesis endpoint.

For reviewing effort, use this hierarchy:

1. automatically discharge sampled candidates with reproducible non-equivalence
   witnesses or a validated restricted proof;
2. have one primary human review the remainder;
3. independently re-review all proposed-equivalent and uncertain labels;
4. independently review a random subset of the remaining labels for quality control;
5. adjudicate disagreements without manufacturing agreement statistics.

If the thesis requires symmetric, independent double review of every sampled item,
retain it, but begin with 100 rather than 313. If the thesis permits the closest
large-study precedent, one coder plus targeted discussion substantially reduces the
number of judgements, but the limitation and absence of full-sample inter-rater
reliability must be stated.

The protocol, seed, sample schedule, reviewer allocation, stopping rule, and primary
score endpoints must be fixed before looking at any real labels. Any pilot labels
may count toward the final estimate only if they were selected probabilistically and
their inclusion probabilities remain valid in the two-phase design.
