# Phase 1 Statistical Analysis Report

## 1. Scope and summary of findings

This report compares the AI-assisted and Manual groups in Phase 1 in terms of test effectiveness, generation efficiency, and static maintainability indicators. Participants are the independent units of analysis. Interpretation focuses on individual distributions, between-group mean differences, and bootstrap confidence intervals.

Update on 2026-10-05: the user confirmed participant 8's `test_file` as a reasonable non-trivial assertion. Their assertion score is now 1 and uncertain count is 0. The corresponding classification sensitivity analysis has been removed. Participant 6 is considered not usable for individual plots and is hidden from those plots only. Statistical tables and difference-interval plots retain the original statistical sample. Means and medians in individual plots describe the displayed subset and may therefore differ from full-sample statistics. Questionnaires retain the original valid responses. The missing mutation CSV was restored from the existing archived worksheet in the summary workbook, and statistical results have been recalculated.

The main findings are:

1. **Test effectiveness was higher overall in the AI-assisted group.** The mean difference in adjusted mutation score was **34.25 percentage points**, with a 95% bootstrap CI of **[16.06, 53.14] percentage points**. Every AI observation exceeded every Manual observation, giving Cliff's delta = 1.00.
2. **The AI-assisted group required substantially less generation time and achieved greater output per unit of time.** Mean generation time was approximately **33.8 minutes** in the AI group and **77.4 minutes** in the Manual group, a reduction of approximately **43.6 minutes**. For adjusted mutation score divided by generation time, the mean difference per 1,000 seconds was **0.276**, with a 95% CI of **[0.197, 0.358]**.
3. **Valid tests in the AI-assisted group had lower static test smell density.** The complete-case mean difference was **-9.37 percentage points**, with a 95% CI of **[-16.19, -3.65] percentage points**. This result depends on how submissions with no valid tests are treated. Assigning maximum smell density to those submissions preserved the direction and large effect, but the exact permutation p-value was no longer below 0.05.
4. **There was no stable between-group advantage in execution efficiency.** Participant 11's 656 expanded pytest items strongly influenced the AI group's execution-time mean. Excluding that observation left nearly identical mean execution times. Phase 1 provides evidence for improved generation efficiency, but does not establish faster execution.
5. **The findings concern static Phase 1 quality and do not establish long-term maintainability.** Test smells are proxies for structural risk. Actual maintenance cost, evolutionary stability, and regression-test maintenance require Phase 2 evidence.

## 2. Data and statistical methods

The principal effectiveness and generation-efficiency comparisons include 6 AI and 8 Manual participants. Test smell and execution-related outcomes are calculated only where valid tests exist, giving 6 participants per group in the main complete-case comparison. Participants 4 and 6 produced no valid tests, so test smell, coverage, and execution outcomes are undefined for them.

The analysis:

- reports group means, AI-minus-Manual mean differences, participant observations, and within-group distributions;
- uses participant-level bootstrap resampling for 95% confidence intervals of mean differences;
- uses exact permutation tests for small-sample between-group comparisons;
- reports Cliff's delta as a nonparametric effect size;
- applies Holm correction to the three prespecified primary endpoints;
- examines missing-test handling, raw versus adjusted mutation score, and influential execution-time observations in sensitivity analyses. Participant 8's assertion classification has been resolved and no alternative coding is used.

The randomization record is unavailable. Results are therefore presented as observed Phase 1 group differences and associations, rather than causal effects supported by a fully verified randomization procedure.

## 3. Primary endpoints

| Endpoint | AI mean | Manual mean | Mean difference (AI - Manual) | 95% bootstrap CI | Cliff's delta | Exact p | Holm p |
|---|---:|---:|---:|---:|---:|---:|---:|
| Adjusted mutation score | 69.09% | 34.84% | +34.25 pp | [16.06, 53.14] pp | 1.000 | 0.0087 | 0.0130 |
| Mutation generation efficiency (per 1,000 seconds) | 0.357 | 0.081 | +0.276 | [0.197, 0.358] | 1.000 | 0.0003 | 0.0010 |
| Test smell density | 3.33% | 12.70% | -9.37 pp | [-16.19, -3.65] pp | -0.917 | 0.0065 | 0.0130 |

All three primary confidence intervals exclude zero, and all Holm-adjusted p-values are below 0.05. Effect sizes are large. Cliff's delta = 1.00 for the first two outcomes means that every AI observation exceeded every Manual observation in this sample. The large negative delta for test smell density indicates lower values in the AI group.

### 3.1 Figure interpretation: participant-level primary outcomes

See [`primary_outcomes.png`](outputs/figures/primary_outcomes.png). The important visual finding is the difference in distribution shape, beyond the difference in means:

- **Adjusted mutation score:** AI scores cluster between 68.80% and 69.27%, with a median of 69.13%. Manual scores range from 0% to 68.69%, with a full-sample median of 40.94%. After hiding participant 6, the displayed Manual mean is 39.82% and median is 41.23%, which differ from the full-sample statistics. The group difference reflects both high AI performance and several low or unsuccessful Manual outcomes. Some Manual participants approach the AI group's scores, although Manual performance is substantially more variable.
- **Mutation generation efficiency:** all AI observations exceed all Manual observations, without overlap. The observed advantage is therefore consistent across participants rather than being driven by a single outlier.
- **Test smell density:** AI values cluster between 2.86% and 5.71%, whereas Manual values range from 4.76% to 28.57%. Manual values are generally higher and more variable, although some observations at the lower end overlap the AI range.

### 3.2 Figure interpretation: mean differences and intervals

See [`primary_difference_intervals.png`](outputs/figures/primary_difference_intervals.png) and the dimension-specific interval plots in the new notebook. The three primary intervals lie on one side of zero: above zero for mutation score and generation efficiency, and below zero for test smell density. This agrees with higher effectiveness and generation efficiency and lower static smell density in the AI group. The estimate is labelled above each blue point, and the lower and upper limits are labelled below the interval endpoints. Exact and Holm-adjusted p-values are also shown.

## 4. Further interpretation of effectiveness

See [`secondary_effectiveness.png`](outputs/figures/secondary_effectiveness.png).

### 4.1 Coverage and assertion score

- Statement coverage: AI mean 71.98%, Manual mean 60.55%; mean difference **+11.43 percentage points**, 95% CI **[2.55, 24.26]**, exact p = 0.0108.
- Branch coverage: AI mean 62.54%, Manual mean 46.30%; mean difference **+16.24 percentage points**, 95% CI **[3.97, 32.82]**, exact p = 0.0108.
- Assertion score: AI mean 1.00, Manual mean 0.628; mean difference **+0.372**, 95% CI **[0.122, 0.650]**, Cliff's delta = 0.667, exact p = 0.0606. This is the final result after participant 8's manual review. The direction favors AI, but the individual exact test does not reach 0.05.

AI coverage observations form almost a horizontal line, whereas Manual statement coverage ranges approximately from 33.06% to 71.97% and branch coverage from 12.44% to 62.52%. AI outcomes are both higher on average and more consistent in this sample. All AI assertion scores equal 1, whereas Manual scores range from 0 to 1.

These are secondary or exploratory endpoints outside the three-endpoint Holm family. Coverage provides supporting evidence in the same direction. Assertion score shows a favorable direction but cannot be described as a difference confirmed by the exact test. Its bootstrap interval excludes zero while its exact p-value is 0.0606. The two methods can produce different judgments with small, discrete samples containing ties, so both should be reported.

### 4.2 Error rates

All observed AI syntax, runtime, and function error rates are zero. Manual means are 0.100, 0.225, and 0.0938, respectively. The direction favors AI, but none of the individual exact tests reaches 0.05: p = 1.000, 0.165, and 0.473, respectively.

This does not establish the absence of a difference. It indicates insufficient evidence to confirm each error category separately in a small sample of discrete outcomes. A suitable interpretation is: **no such errors were observed in the AI group, whereas some error burden was observed in the Manual group, but evidence for individual error-rate differences remains uncertain.**

## 5. Efficiency findings and figure interpretation

### 5.1 Generation time

Mean generation time is 2,026 seconds, or approximately 33.8 minutes, in the AI group and 4,641 seconds, or approximately 77.4 minutes, in the Manual group. The mean difference is **-2,615 seconds**, equivalent to approximately **43.6 fewer minutes**, with a 95% CI of **[-54.0, -32.7] minutes**, exact p = 0.0007, and Cliff's delta = -1.00. Log-transforming generation time preserves the direction and conclusion (p = 0.0003), suggesting that the finding is not explained solely by skewness on the original time scale.

### 5.2 Figure interpretation: generation time and mutation score

See [`generation_time_vs_mutation.png`](outputs/figures/generation_time_vs_mutation.png). AI observations cluster in the upper-left region, combining shorter generation time with higher mutation score. Manual observations are more dispersed:

- some Manual participants approach AI mutation scores but require substantially more time;
- others spend considerable time yet achieve relatively low mutation scores;
- participant 4 has a mutation score of zero. Participant 6 also has a zero score but is hidden under the presentation rule. Both remain in full-sample statistics and influence the Manual mean and variability.

The plot supports an improved time-effectiveness combination with AI assistance in this task. It does not imply that every Manual participant produced poor tests. The observed contrast reflects stable high AI scores, shorter time, and low-scoring or unsuccessful outcomes within the Manual group.

### 5.3 Execution time

The original means suggest approximately 0.082 seconds longer execution time in the AI group. However, the 95% CI is [-0.066, 0.285] seconds and exact p = 0.591, providing no evidence of a stable difference.

See [`execution_time_vs_test_count.png`](outputs/figures/execution_time_vs_test_count.png). Participant 11 is clearly separated from the other observations, with 656 expanded pytest items and execution time of approximately 0.778 seconds. Most other participants have only 1-5 items. Excluding participant 11 gives a mean difference of approximately -0.011 seconds, a 95% CI of [-0.086, 0.053], and p = 0.810. The original mean is strongly influenced by test-count structure and this high-leverage observation.

The interpretations are distinct:

- **Generation efficiency:** the AI group has a strong and consistent advantage.
- **Execution efficiency:** no reliable group difference is established by the current data.
- **Coverage or mutation score normalized by execution time:** these results are sensitive to participant 11 and should not be the central efficiency conclusion.

## 6. Test smell composition and maintainability

See [`test_smell_types.png`](outputs/figures/test_smell_types.png). Across participants, the most frequent confirmed smell types are:

1. Conditional Test Logic: 10 pairs;
2. Unknown Test: 5 pairs;
3. Assertion Roulette: 5 pairs;
4. Exception Handling: 2 pairs;
5. Other checked types: none observed.

These are pooled counts, not a causal between-group comparison. Bar heights alone do not identify which group produced a particular smell. The figure can guide subsequent qualitative inspection and Phase 2 priorities, such as whether conditional logic increases comprehension cost, Unknown Test reduces diagnostic clarity, or multiple assertions complicate fault localization.

The main complete-case analysis indicates lower AI smell density, with an important boundary: participants 4 and 6 have no valid tests and hence no directly observed density. Under an extreme assignment of density = 1 for those submissions, the AI mean remains 3.33%, the Manual mean becomes 34.52%, and the difference is -31.19 percentage points, with Cliff's delta = -0.938. The exact p-value is 0.0686. The direction and large effect remain, but significance is unstable under the small sample, extreme assignments, and altered comparison configuration.

The most defensible conclusion is: **among participants who produced valid tests, the AI group has lower static test smell density. Including failed generation as a worst-case maintainability outcome preserves the direction, but the small-sample exact significance is unstable.**

## 7. Questionnaire interpretation

See [`likert_ai_post.png`](outputs/figures/likert_ai_post.png) and [`likert_manual_post.png`](outputs/figures/likert_manual_post.png). The AI and Manual post-surveys ask different questions. They should be described separately, without treating equal numeric responses as directly comparable measurements.

The AI survey shows:

- unanimous ratings of 5 for faster completion and overall usefulness;
- generally high ratings of 4-5 for test logic, oracles, and correctness;
- more varied ratings of 3, 4, and 5 for quality improvement, suggesting greater agreement about speed than quality;
- mixed confidence in identifying flaws in AI output, indicating that human review capability may remain an important condition for effective use;
- mostly ratings of 1-3 on the negatively worded hallucination-cost item, without consistent agreement that hallucinations frequently caused additional time.

The Manual survey shows:

- generally negative responses about whether the required effort was reasonable;
- mixed confidence in test outcomes and adequacy, including many neutral or disagreeing responses;
- more positive responses from some participants about future similar tasks and debugging, with substantial individual variation.

The perceived speed advantage agrees with the objective generation-time result. However, the sample is small and the survey versions differ. Questionnaire findings supplement the behavioral results rather than serving as the primary statistical evidence.

## 8. Key sensitivity analyses

1. **Mutation score definition:** raw mutation score gives AI mean 65.83%, Manual mean 33.20%, difference 32.63 percentage points, 95% CI [15.18, 50.60], and exact p = 0.0087. This agrees with the adjusted-score conclusion.
2. **No-valid-test smell handling:** worst-case assignment preserves the direction and large effect, but exact p = 0.0686 shows sensitivity of significance to the missing-outcome treatment.
3. **Participant 11's execution data:** exclusion leaves execution-time differences near zero but makes the mutation execution-efficiency contrast clearer. Execution-normalized measures are susceptible to test count and influential observations.
4. **Time transformation:** log-transformed generation time preserves the finding, while log-transformed execution time still shows no clear difference.

**Mutation effectiveness and generation efficiency provide the most robust findings.** The smell direction is stable but significance depends on failed-submission handling, and execution-normalized measures are sensitive to individual participants. Assertion score now uses a fixed reviewed classification. Its coding sensitivity analysis is no longer applicable, and its final exact p-value is not below 0.05.

## 9. Answers to the research hypotheses

### H01: Does AI assistance improve test effectiveness?

Phase 1 supports the direction of improved effectiveness, chiefly through the large adjusted mutation-score difference, complete separation of the groups, and supporting statement/branch coverage results. The reviewed assertion score and individual error rates favor AI in direction but have insufficient exact-test evidence. This answers the research question and does not mean that every metric-specific H01 null hypothesis has been rejected.

### H02: Does AI assistance improve efficiency?

Phase 1 strongly supports improved **generation efficiency**, with shorter generation time and greater mutation score and coverage per unit of generation time. It does not support a stable **execution-efficiency** advantage. These two concepts should be reported separately.

### H03: Does AI assistance improve maintainability?

Phase 1 provides partial support through lower static smell density among valid tests. The finding depends on how submissions without valid tests are treated, and smells are maintenance-risk proxies. Actual modification cost, diagnostic effort, and evolutionary stability require direct Phase 2 assessment.

### H04: Does experience or seniority moderate the effect of AI assistance?

The sample size and available design information do not support a reliable interaction analysis. Without complete allocation information, experience stratification, and a larger sample, current plots should not be used to infer moderation by seniority. Descriptive individual patterns may be reported, with formal testing reserved for Phase 2 or an expanded sample.

## 10. Limitations

- Small samples produce discrete exact p-values, and individual observations can substantially influence secondary findings.
- The randomization record is unavailable, so baseline differences and selection bias cannot be ruled out.
- Some metrics are defined only after successful generation of valid tests, creating missing outcomes related to failure mechanisms.
- Secondary and exploratory endpoints do not share a comprehensive multiplicity correction and should not receive strong confirmatory interpretations one by one.
- Highly concentrated AI mutation scores and coverage may reflect shared generation strategies, task ceilings, or templates and warrant artifact inspection.
- Static test smells cannot replace longitudinal evidence from maintenance tasks.
- Different survey versions prevent direct comparison of nominally equal item scores.
- A single codebase and task environment limit external validity.

## 11. Suggested wording for the thesis results section

In the Phase 1 sample, the AI-assisted group outperformed the Manual group in adjusted mutation score, mutation score per unit of generation time, and test smell density among valid tests. Bootstrap confidence intervals for all three prespecified primary endpoints excluded zero, and Holm-adjusted exact p-values were below 0.05. Participant distributions showed high, concentrated AI mutation scores and coverage, while Manual outcomes were more variable and included low-scoring or unsuccessful submissions. AI assistance reduced mean generation time by approximately 43.6 minutes. Execution time showed no reliable group difference and was influenced by a participant with an exceptionally large expanded test count. Following manual review of participant 8's assertion, the assertion-score difference was 0.372 with exact p = 0.0606 and cannot be described as a confirmed between-group difference. Sensitivity analyses identified mutation effectiveness and generation efficiency as the most robust findings, whereas smell results depended on the handling of failed submissions. Participant 6 was hidden only in individual plots and remained in the statistical sample. Given the small sample, unavailable allocation record, and static Phase 1 measurements, the findings provide preliminary evidence favoring AI assistance. Long-term maintainability and broader causal effects require subsequent validation.
