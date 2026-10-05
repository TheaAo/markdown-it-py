"""Create the English counterpart of Analysis.ipynb without recomputing results.

Only narrative text, comments, and runtime messages are translated. Existing
executed tables and chart outputs are retained from the corresponding Chinese
notebook. Both versions use the same source data and output directories.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re
from textwrap import dedent

import nbformat


INTERVAL_DESCRIPTION = """### Between-group differences and uncertainty

Blue points represent AI-minus-Manual mean differences. Horizontal lines show
95% bootstrap confidence intervals. Estimates are labelled above the points;
lower and upper limits are labelled below the endpoints. Each outcome has an
independent horizontal axis, and proportions are displayed as percentage points.
These plots use the full statistical sample, including participant 6, unlike the
individual plots that hide participant 6. Holm correction still applies jointly
to the three prespecified primary endpoints across the outcome dimensions.
"""

MARKDOWN = {
    0: """# Phase 1 Analysis — Organized by Interim Report Table 4.1

Reading order: **Effectiveness → Efficiency → Maintainability → Questionnaire**.
Each outcome dimension presents participant data, descriptive statistics,
between-group comparisons, figures, and the relevant sensitivity analyses.
The statistical sample consists of 14 Phase 1 participants (AI 6, Manual 8).

| Table 4.1 dimension | Outcome order in this notebook |
|---|---|
| Effectiveness | Syntax / Runtime / Function Error Rate; Branch / Statement Coverage; Mutation Score; Assertion Score |
| Efficiency | Generation / Execution Time; Generation Efficiency (Branch / Statement / Mutation); Execution Efficiency (Branch / Statement / Mutation) |
| Maintainability | Test Smell Density; smell-type counts as a descriptive supplement |
| Questionnaire | Pre-survey background summary; separate AI and Manual post-surveys; open-response coding table |

**Execution:** run from top to bottom. By default, statistics are recalculated
from `results/phase1/`. The missing mutation CSV was restored from the existing
archived `Mutation score` worksheet in the summary workbook. `RESTORATION.md`
beside the CSV documents this restoration; the mutation experiment was not rerun.
Set `REBUILD_FROM_RAW = False` to display previously saved statistical tables only.
Figures are saved to `outputs/figures/table41/`, separately from the legacy
notebook's figures. Both language versions share these same output files.

**Individual-plot rule:** participant 6 is considered not usable for presentation
and is hidden from participant plots only. Statistical analyses retain the full
sample. Means and medians in individual plots describe the displayed subset and
must not be treated as full-sample means. Difference-interval plots retain the
full statistical sample, and questionnaires summarize the original valid responses.
**Participant 8 manual review:** `test_file` is a confirmed non-trivial assertion,
with score = 1 and uncertain count = 0. Assertion-coding sensitivity analysis has
therefore been removed.

**Statistical conventions:** differences are AI minus Manual. The prespecified
primary endpoints are adjusted mutation score, mutation generation efficiency,
and test smell density. They remain one Holm-correction family regardless of
chapter placement. Other tests are exploratory. Confidence intervals use 20,000
within-group bootstrap resamples. Missing values remain NA. Adjusted mutation
score is estimated from the sampled equivalent-mutant review.
""",
    1: """## 0. Setup and data sources

This section prepares shared data and plotting helpers. The four substantive
sections follow below.
""",
    5: """## 1. Effectiveness

Following Table 4.1, this section covers three error rates, branch/statement
coverage, mutation score, and assertion score. Error rates describe the error
burden among all submitted tests; coverage and assertion score use valid tests.
Participants 4 and 6 have no valid tests, so their coverage/assertion outcomes
remain NA and mutation scores retain the collected values. Tables store
proportions on a 0–1 scale; plots convert them to percentages. Mutation score is
this dimension's prespecified primary endpoint.
""",
    7: """### Figure 1. Participant-level effectiveness outcomes

Each dot is one participant. Hollow diamonds indicate means, and horizontal
lines indicate medians. The seven outcomes have independent vertical axes.
""",
    9: INTERVAL_DESCRIPTION,
    11: """### Effectiveness sensitivity analysis

Compare raw and adjusted mutation scores. Participant 8's assertion has been
reviewed, so alternative assertion classifications are no longer compared.
""",
    13: """## 2. Efficiency

Following Table 4.1, generation/execution time is presented first, followed by
three generation-efficiency and three execution-efficiency measures.
Efficiency is effectiveness score divided by time in seconds, rather than test
count divided by time. Mutation generation efficiency is a prespecified primary
endpoint; other efficiency outcomes are exploratory. Time tables retain seconds,
while the generation-time relationship plot uses minutes. Efficiency plots retain
per-second rates.
""",
    15: """### Figure 2. Generation time and execution time

Lower generation time indicates faster task completion. Execution time should
be interpreted together with test count.
""",
    17: """### Figure 3. Generation efficiency and execution efficiency

The first row shows generation efficiency; the second shows execution efficiency.
Columns show branch coverage, statement coverage, and mutation score, respectively.
Each panel is scaled independently.
""",
    19: INTERVAL_DESCRIPTION,
    21: """### Figure 4. Generation time and mutation effectiveness

Examine individual differences in speed and quality together. Participant labels
can be traced back to the participant data table.
""",
    23: """### Figure 5. Execution time and expanded test count

The horizontal axis uses a logarithmic scale. Participant 11's 656 pytest items
form an influential observation requiring separate examination.
""",
    25: """### Efficiency sensitivity analysis

Check whether excluding participant 11 or log-transforming time changes the results.
""",
    27: """## 3. Maintainability — Static structural risk

The Table 4.1 outcome is test smell density. The current operational definition
is confirmed source-test/smell pairs divided by eligible source tests multiplied
by the seven frozen smell definitions. Lower values are preferable. Participants
4 and 6 have no valid tests, and the primary analysis retains NA for their density.
Smell-type counts are a descriptive supplement. Static Phase 1 structural
indicators do not directly measure actual Phase 2 maintenance cost.
""",
    29: """### Figure 6. Participant-level test smell density""",
    31: INTERVAL_DESCRIPTION,
    33: """### Figure 7. Confirmed test smells by type

Counts summarize confirmed pairs across participants; they are not causal
between-group comparisons.
""",
    35: """### Maintainability sensitivity analysis

Assign density = 1 to submissions without valid tests as an extreme stress test.
This scenario does not replace the primary complete-case analysis.
""",
    37: """## 4. Questionnaire — Background and subjective experience

Present pre-survey background summaries first, followed by separate AI and Manual
post-survey figures. The post-survey versions ask different questions, so equal
numeric scores are not directly compared and items are not combined into an
unvalidated scale. Open responses retain columns for manual coding; themes are
not inferred automatically.
""",
    38: """### 4.1 Pre-survey background summary

These items describe some background covariates in Table 4.1. They are presented
descriptively and have not been used to adjust the between-group results.
""",
    40: """### 4.2 Post-survey item statistics""",
    42: """### Figure 8. AI post-survey Likert distributions

Each row is one question. Colored segments represent the percentages of responses
from 1 to 5. Negatively worded questions must be interpreted according to their wording.
""",
    44: """### Figure 9. Manual post-survey Likert distributions

Colors match the AI version, but question content differs. Interpret each version separately.
""",
    46: """### 4.3 Open responses and interpretation boundaries

The table below retains columns for manual thematic coding. The randomization
record is unavailable, so findings describe group differences in the current
Phase 1 sample. Longitudinal maintenance and crossover conclusions require Phase 2 data.
""",
}

TRANSLATIONS = {
    "False：展示已有统计快照。True：从完整的 Phase 1 原始数据重新计算。":
        "False: display saved statistics. True: recalculate from complete Phase 1 input data.",
    "原始数据尚未齐备，无法重新计算：":
        "Source files are incomplete; statistics cannot be recalculated:",
    "两种模式都读取同一套输出结构，明确区分计算来源。":
        "Both modes read the same output structure; their calculation provenance is stated explicitly.",
    "展示排除与统计排除不同：这里仅隐藏个体图中的 6 号。":
        "Presentation exclusion differs from statistical exclusion: hide participant 6 in individual plots only.",
    "数据模式：": "Data mode:",
    "已从原始数据重新计算": "Recalculated from source data",
    "已保存的统计快照（未重新计算）": "Saved statistical snapshot (not recalculated)",
    "Phase 1 原始数据目录：": "Phase 1 source directory:",
    "图表输出目录：": "Figure output directory:",
    "样本数：": "Sample sizes:",
    "此处展示的是快照生成时的核验，不代表再次核验当前原始文件。":
        "Validation describes the generation of these tables; snapshot-only mode does not revalidate current source files.",
    "Table 4.1 的内容顺序与 SAP 的主要/次要统计角色是两个独立分类。":
        "Table 4.1 presentation order and SAP primary/secondary roles are separate classifications.",
    "明确按论文指标顺序排列，而不是按 CSV 中主要/次要顺序排列。":
        "Order results by thesis outcome sequence rather than primary/secondary CSV order.",
    "按 Table 4.1 顺序展示参与者数据；NA 保留为缺失，不能当成零。":
        "Display participant data in Table 4.1 order; retain NA as missing, never as zero.",
    "同一维度内先看描述统计，再看组间比较；保留主要/探索性角色。":
        "Within each dimension, show descriptions before comparisons and retain primary/exploratory roles.",
    "七个有效性指标全部展示，按 Table 4.1 排序；最后一个空面板关闭。":
        "Show all seven effectiveness outcomes in Table 4.1 order and hide unused panels.",
    "独立坐标轴避免比例、秒和每秒速率混在同一尺度。":
        "Use independent axes to avoid mixing proportions, seconds, and per-second rates on one scale.",
    "数字跟随其实际横坐标，估计值置于上方，两个端点置于下方。":
        "Position labels at their actual x-coordinates: estimate above, endpoints below.",
    "时间指标单独展示，避免与效率比值混在一组坐标轴中。":
        "Plot time outcomes separately from efficiency ratios.",
    "六种比值全部展示；需与前面的分子分数、时间和有效样本数一起阅读。":
        "Show all six ratios; interpret them with their numerator scores, times, and available sample sizes.",
    "分母是源测试函数和七种 smell 类型，不是展开后的 pytest item 数。":
        "The denominator uses source-test functions and seven smell types, not expanded pytest items.",
}


def build() -> Path:
    """Translate narrative cells while retaining matching computations and outputs."""
    directory = Path(__file__).resolve().parent
    notebook = deepcopy(nbformat.read(directory / "Analysis.ipynb", as_version=4))
    actual_markdown = {i for i, cell in enumerate(notebook.cells) if cell.cell_type == "markdown"}
    if actual_markdown != set(MARKDOWN):
        raise ValueError("Chinese notebook structure changed; update the English narrative mapping.")
    for index, cell in enumerate(notebook.cells):
        if cell.cell_type == "markdown":
            cell.source = dedent(MARKDOWN[index]).strip()
        else:
            for chinese, english in TRANSLATIONS.items():
                cell.source = cell.source.replace(chinese, english)
                # Only translate authored runtime messages. Source survey responses,
                # numeric tables, and image outputs retain their original content.
                for output in cell.get("outputs", []):
                    if output.output_type == "stream":
                        output.text = output.text.replace(chinese, english)
        if re.search(r"[\u4e00-\u9fff]", cell.source):
            raise ValueError(f"Untranslated authored text in cell {index}")
    notebook.metadata["language_variant"] = "English"
    notebook.metadata["translation_source"] = "Analysis.ipynb"
    target = directory / "Analysis_EN.ipynb"
    nbformat.validate(notebook)
    nbformat.write(notebook, target)
    return target


if __name__ == "__main__":
    print(build())
