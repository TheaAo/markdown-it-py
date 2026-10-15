"""Build the Table 4.1 notebook, retaining the original chart implementations.

Run from the repository root with:
    python3 scripts/phase1_analysis/build_analysis_notebook.py

The original phase1_analysis.ipynb remains available as the source for six chart
cells and the shared plotting helpers. Analysis.ipynb is the dimension-oriented
reading entry point. This builder never reads or changes experimental source data.
"""

from __future__ import annotations

from pathlib import Path
from inspect import cleandoc
import re

import nbformat


def build() -> Path:
    """Generate an unexecuted notebook grouped by the thesis outcome dimensions."""
    directory = Path(__file__).resolve().parent
    original = nbformat.read(directory / "phase1_analysis.ipynb", as_version=4)
    cells = []

    def markdown(text: str) -> None:
        cells.append(nbformat.v4.new_markdown_cell(cleandoc(text)))

    def code(text: str) -> None:
        source = cleandoc(text).replace(
            "participant_dot_panel(ax, participants,", "participant_dot_panel(ax, plot_participants,"
        )
        cells.append(nbformat.v4.new_code_cell(source))

    def chart(title: str, index: int) -> None:
        markdown(title)
        source = original.cells[index].source
        # Individual plots omit P6 only; interval plots still use full-sample tests.
        source = re.sub(r"\bparticipants\b", "plot_participants", source)
        code(source)

    def dimension_tables(name: str, metrics: str, extra: str = "") -> None:
        code(f'''# 按 Table 4.1 顺序展示参与者数据；NA 保留为缺失，不能当成零。
{name}_data = participants[["participant_number", "group", {extra}*{metrics}]].copy()
display({name}_data)
# 同一维度内先看描述统计，再看组间比较；保留主要/探索性角色。
display(descriptive.loc[descriptive["metric"].isin({metrics})])
display(ordered_results({metrics}))''')

    def intervals(name: str, metrics: str) -> None:
        markdown("### 组间差异与不确定性\n\n蓝点为 AI − Manual 均值差，横线为 95% bootstrap 区间。点上方标注估计值，两端下方标注下限和上限。每个指标使用独立横轴；百分比指标转换为百分点。此图使用统计表的完整样本（含 6 号），与隐藏 6 号的个体图不同。Holm 校正仍针对跨维度的三个预设主要结局。")
        code(f'''# 独立坐标轴避免比例、秒和每秒速率混在同一尺度。
rows = ordered_results({metrics})
fig, axes = plt.subplots(len(rows), 1, figsize=(9, 2.0 * len(rows)), squeeze=False)
for ax, (_, row) in zip(axes.flat, rows.iterrows()):
    multiplier = 100.0 if row["scale"] == "proportion" else 1.0
    estimate = row["mean_difference_ai_minus_manual"] * multiplier
    lower = row["bootstrap_ci95_lower"] * multiplier
    upper = row["bootstrap_ci95_upper"] * multiplier
    ax.axvline(0, color="#111827", linestyle="--", linewidth=1)
    ax.errorbar(estimate, 0, xerr=[[estimate - lower], [upper - estimate]],
                fmt="o", color=GROUP_COLORS["AI"], capsize=4)
    # 数字跟随其实际横坐标，估计值置于上方，两个端点置于下方。
    number = lambda value: f"{{value:.3g}}" if 0 < abs(value) < 0.01 else f"{{value:.2f}}"
    for value, label, offset in [(estimate, "Estimate", 14), (lower, "Lower", -20), (upper, "Upper", -20)]:
        ax.annotate(f"{{label}}: {{number(value)}}", (value, 0),
                    xytext=(0, offset), textcoords="offset points", ha="center",
                    va="bottom" if offset > 0 else "top", fontsize=8,
                    bbox=dict(facecolor="white", edgecolor="none", alpha=0.9, pad=1))
    ax.set_ylim(-1, 1)
    ax.margins(x=0.18)
    ax.set_yticks([])
    ax.set_title(str(row["label"]), loc="left")
    unit = {{"proportion": "percentage points", "seconds": "seconds", "rate": "per second"}}[row["scale"]]
    ax.set_xlabel(f"AI minus Manual ({{unit}})")
    p_text = f"exact p={{row['exact_permutation_p_value']:.4f}}"
    if pd.notna(row["holm_adjusted_p_value"]):
        p_text += f"; Holm p={{row['holm_adjusted_p_value']:.4f}}"
    ax.text(0.99, 0.8, p_text, transform=ax.transAxes, ha="right", fontsize=8)
    ax.grid(axis="x", alpha=0.22)
    ax.grid(axis="y", visible=False)
fig.tight_layout()
save_figure(fig, "{name}_difference_intervals")
plt.show()
plt.close(fig)''')

    markdown('''# Phase 1 Analysis — 按中期报告 Table 4.1 整理

    阅读顺序：**Effectiveness → Efficiency → Maintainability → Questionnaire**。
    每个结果维度依次展示参与者数据、描述统计、组间比较、图表和相关敏感性分析。
    分析范围是 Phase 1 的 14 名参与者（AI 6、Manual 8）。

    | Table 4.1 维度 | 本 notebook 的指标顺序 |
    |---|---|
    | Effectiveness | Syntax / Runtime / Function Error Rate；Branch / Statement Coverage；Mutation Score；Assertion Score |
    | Efficiency | Generation / Execution Time；Generation Efficiency（Branch / Statement / Mutation）；Execution Efficiency（Branch / Statement / Mutation） |
    | Maintainability | Test Smell Density；smell 类型数量作为描述性补充 |
    | Questionnaire | Pre-survey 背景摘要；AI 和 Manual post-survey 分开展示；开放式回答编码表 |

    **运行方式：**从上到下运行。默认从 `results/phase1/` 重算统计结果。
    缺失的 mutation CSV 已从汇总 Excel 的原有 `Mutation score` 存档工作表恢复，
    恢复说明在 CSV 同目录的 `RESTORATION.md`，没有重新运行 mutation 实验。
    将 `REBUILD_FROM_RAW` 改为 `False` 可仅展示已保存的统计表。
    新图表保存到 `outputs/figures/table41/`，与旧 notebook 的图表分开。

    **个体图展示规则：**6 号 not usable，从参与者点图中隐藏；统计分析仍保留完整样本。
    个体图中的均值/中位数也基于展示子集，不能当作完整样本统计表的均值。
    差异区间图保留完整统计样本；问卷按原始有效回答汇总。
    **8 号人工复核：**`test_file` 已确认为 non-trivial assertion，score = 1，
    uncertain count = 0，因此移除 assertion 编码敏感性分析。

    **统计约定：**差异均为 AI − Manual；三个预设主要结局分别是 adjusted mutation
    score、mutation generation efficiency 和 test smell density，Holm 校正保持同一检验族，
    不随章节划分改变。其他检验为探索性。置信区间使用 20,000 次组内 bootstrap。
    缺失值保留为 NA；调整后的 mutation score 来自等价变异体抽样复核估计。
    ''')
    markdown("## 0. 运行准备与数据来源\n\n本节只准备共享数据和绘图工具，四个内容章节从下方开始。")
    setup = original.cells[2].source.replace(
        "from config import FIGURE_DIR, GROUP_COLORS, GROUP_ORDER, PRIMARY_METRICS",
        "from config import FIGURE_DIR as BASE_FIGURE_DIR, TABLE_DIR, RESULTS_DIR, GROUP_COLORS, GROUP_ORDER, PRIMARY_METRICS\nfrom IPython.display import display\n\nFIGURE_DIR = BASE_FIGURE_DIR / 'table41'",
    )
    setup = setup.replace("from analysis_utils import all_metric_metadata, load_phase1_data, participating_data, validate_phase1_data", "from analysis_utils import all_metric_metadata")
    # Long efficiency labels must wrap inside each panel rather than overlap.
    setup = setup.replace(
        'ax.set_title(str(metadata.get("short_label", metadata["label"])))',
        'ax.set_title(fill(str(metadata.get("short_label", metadata["label"])), width=30))',
    )
    code(setup)
    code('''# False：展示已有统计快照。True：从完整的 Phase 1 原始数据重新计算。
    REBUILD_FROM_RAW = True
    if REBUILD_FROM_RAW:
        from run_analysis import SOURCE_FILES
        missing_sources = [str(RESULTS_DIR / name) for name in SOURCE_FILES
                           if not (RESULTS_DIR / name).is_file()]
        if missing_sources:
            raise FileNotFoundError("原始数据尚未齐备，无法重新计算：\\n" + "\\n".join(missing_sources))
        run()

    # 两种模式都读取同一套输出结构，明确区分计算来源。
    participants = pd.read_csv(TABLE_DIR / "participant_master.csv")
    # 展示排除与统计排除不同：这里仅隐藏个体图中的 6 号。
    plot_participants = participants.loc[participants["participant_number"].ne(6)].copy()
    descriptive = pd.read_csv(TABLE_DIR / "descriptive_statistics.csv")
    primary = pd.read_csv(TABLE_DIR / "primary_results.csv")
    secondary = pd.read_csv(TABLE_DIR / "secondary_results.csv")
    sensitivity = pd.read_csv(TABLE_DIR / "sensitivity_results.csv")
    likert = pd.read_csv(TABLE_DIR / "questionnaire_likert.csv")
    baseline = pd.read_csv(TABLE_DIR / "questionnaire_baseline.csv")
    open_text = pd.read_csv(TABLE_DIR / "questionnaire_open_text_coding.csv")
    validation = pd.read_csv(TABLE_DIR / "data_validation.csv")
    print("数据模式：", "已从原始数据重新计算" if REBUILD_FROM_RAW else "已保存的统计快照（未重新计算）")
    print("Phase 1 原始数据目录：", RESULTS_DIR)
    print("图表输出目录：", FIGURE_DIR)
    print("样本数：", participants.groupby("group").size().to_dict())
    # 此处展示的是快照生成时的核验，不代表再次核验当前原始文件。
    display(validation)
    display(pd.read_csv(TABLE_DIR / "data_completeness.csv"))
    ''')
    code('''# Table 4.1 的内容顺序与 SAP 的主要/次要统计角色是两个独立分类。
    EFFECTIVENESS_METRICS = [
        "syntax_error_rate", "runtime_error_rate", "function_error_rate",
        "participant_branch_coverage", "participant_statement_coverage",
        "specified_estimated_adjusted_mutation_score", "assertion_score",
    ]
    EFFICIENCY_METRICS = [
        "generation_time_seconds", "execution_time_seconds",
        "branch_generation_efficiency_per_second", "statement_generation_efficiency_per_second",
        "mutation_generation_efficiency_per_second",
        "branch_execution_efficiency_per_second", "statement_execution_efficiency_per_second",
        "mutation_execution_efficiency_per_second",
    ]
    MAINTAINABILITY_METRICS = ["test_smell_density"]
    metric_metadata = all_metric_metadata()
    results = pd.concat([
        primary.assign(analysis_role="Primary"),
        secondary.assign(analysis_role="Exploratory"),
    ], ignore_index=True)
    result_columns = [
        "label", "analysis_role", "n_ai", "n_manual", "mean_ai", "mean_manual",
        "mean_difference_ai_minus_manual", "bootstrap_ci95_lower", "bootstrap_ci95_upper",
        "cliffs_delta", "exact_permutation_p_value", "holm_adjusted_p_value", "scale",
    ]

    def ordered_results(metrics: list) -> pd.DataFrame:
        # 明确按论文指标顺序排列，而不是按 CSV 中主要/次要顺序排列。
        return results.set_index("metric").loc[metrics, result_columns].reset_index()

    def sensitivity_for(metrics: list) -> pd.DataFrame:
        return sensitivity.loc[sensitivity["metric"].isin(metrics)].copy()
    ''')

    markdown('''## 1. Effectiveness — 测试有效性

    按 Table 4.1 整理三种错误率、branch/statement coverage、mutation score 和 assertion score。
    错误率反映全部提交测试的错误负担；coverage 和 assertion 只对有效测试计算。
    参与者 4、6 无有效测试，其 coverage/assertion 为 NA，mutation score 保留采集结果。
    比例数据表使用 0–1，图中转换为百分比。Mutation score 为此维度的预设主要结局。
    ''')
    dimension_tables("effectiveness", "EFFECTIVENESS_METRICS", '"valid_test_count", ')
    markdown("### 图 1. Effectiveness 个体分布\n\n每点代表一位参与者；空心菱形为均值，横线为中位数。七个指标使用独立纵轴。")
    code('''# 七个有效性指标全部展示，按 Table 4.1 排序；最后一个空面板关闭。
    fig, axes = plt.subplots(3, 3, figsize=(12, 10))
    for ax, metric in zip(axes.flat, EFFECTIVENESS_METRICS):
        participant_dot_panel(ax, participants, metric, metric_metadata[metric])
    for ax in list(axes.flat)[len(EFFECTIVENESS_METRICS):]:
        ax.set_visible(False)
    fig.suptitle("Effectiveness: participant-level outcomes", y=1.01)
    fig.tight_layout()
    save_figure(fig, "effectiveness_outcomes")
    plt.show()
    plt.close(fig)''')
    intervals("effectiveness", "EFFECTIVENESS_METRICS")
    markdown("### Effectiveness 敏感性分析\n\n比较 raw/adjusted mutation score。8 号 assertion 已完成复核，不再比较替代编码。")
    code('''display(sensitivity_for(EFFECTIVENESS_METRICS + ["specified_raw_mutation_score"]))''')

    markdown('''## 2. Efficiency — 测试效率

    先展示生成/执行时间，再展示三种生成效率和三种执行效率，与 Table 4.1 一致。
    效率 = 有效性分数 ÷ 时间（秒），不是测试数量 ÷ 时间。
    mutation generation efficiency 是预设主要结局，其他效率指标为探索性。
    时间表保留秒；关系图将生成时间转换为分钟。效率图保留每秒速率。
    ''')
    dimension_tables("efficiency", "EFFICIENCY_METRICS", '"valid_test_count", ')
    markdown("### 图 2. 生成时间与执行时间\n\n生成时间越低表示完成任务越快；执行时间应结合测试数量一起解释。")
    code('''# 时间指标单独展示，避免与效率比值混在一组坐标轴中。
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.8))
    for ax, metric in zip(axes, EFFICIENCY_METRICS[:2]):
        participant_dot_panel(ax, participants, metric, metric_metadata[metric])
    fig.tight_layout()
    save_figure(fig, "efficiency_times")
    plt.show()
    plt.close(fig)''')
    markdown("### 图 3. 生成效率与执行效率\n\n第一行为生成效率，第二行为执行效率；列依次为 branch coverage、statement coverage、mutation score。各面板独立缩放。")
    code('''# 六种比值全部展示；需与前面的分子分数、时间和有效样本数一起阅读。
    fig, axes = plt.subplots(2, 3, figsize=(12, 7.5))
    for ax, metric in zip(axes.flat, EFFICIENCY_METRICS[2:]):
        participant_dot_panel(ax, participants, metric, metric_metadata[metric])
    fig.tight_layout()
    save_figure(fig, "efficiency_rates")
    plt.show()
    plt.close(fig)''')
    intervals("efficiency", "EFFICIENCY_METRICS")
    chart("### 图 4. 生成时间与 mutation effectiveness\n\n结合速度和质量观察个体差异；标签可追溯到参与者数据表。", 17)
    chart("### 图 5. 执行时间与展开后的测试数量\n\n横轴为对数尺度。参与者 11 的 656 个 pytest items 是需单独审查的高杠杆观测。", 19)
    markdown("### Efficiency 敏感性分析\n\n检查排除参与者 11 和对时间取对数后，结果是否变化。")
    code('''display(sensitivity_for(EFFICIENCY_METRICS + ["log_generation_time", "log_execution_time"]))''')

    markdown('''## 3. Maintainability — 静态可维护性风险

    Table 4.1 的指标是 test smell density。当前操作定义为确认的 source-test/smell
    配对数 ÷（eligible source tests × 7 种冻结的 smell 定义），数值越低越好。
    参与者 4、6 没有有效测试，主要分析保留 NA。类型数量为描述性补充。
    Phase 1 的静态结构指标不能直接代表 Phase 2 的真实维护成本。
    ''')
    dimension_tables("maintainability", "MAINTAINABILITY_METRICS", '"eligible_test_count", "confirmed_pair_count", "uncertain_pair_count", ')
    markdown("### 图 6. Test smell density 个体分布")
    code('''# 分母是源测试函数和七种 smell 类型，不是展开后的 pytest item 数。
    fig, ax = plt.subplots(figsize=(5.5, 4))
    participant_dot_panel(ax, participants, "test_smell_density", metric_metadata["test_smell_density"])
    fig.tight_layout()
    save_figure(fig, "maintainability_density")
    plt.show()
    plt.close(fig)''')
    intervals("maintainability", "MAINTAINABILITY_METRICS")
    chart("### 图 7. 各类 test smell 的确认数量\n\n汇总全体参与者的配对数，不是实验组间的因果比较。", 23)
    markdown("### Maintainability 敏感性分析\n\n将无有效测试的提交极端地赋值为 density = 1，仅用于压力测试，不替代主要完整案例结果。")
    code('''display(sensitivity_for(MAINTAINABILITY_METRICS))''')

    markdown('''## 4. Questionnaire — 背景与主观体验

    先展示 pre-survey 背景摘要，再分别展示 AI 和 Manual post-survey 图表。
    两版 post-survey 的题目不同，不直接比较同一数字分数，也不合并为未经验证的量表。
    开放式回答保留人工编码列；当前不自动推断主题。
    ''')
    markdown("### 4.1 Pre-survey 背景摘要\n\n对应 Table 4.1 的部分背景协变量；此处仅作描述，未据此调整组间结果。")
    code("display(baseline)")
    markdown("### 4.2 Post-survey 题目统计")
    code('''display(likert[["survey", "item_order", "item", "n", "median", "first_quartile", "third_quartile"]])''')
    chart("### 图 8. AI post-survey Likert 分布\n\n每行一道题，色块表示 1–5 分回答比例。负向题需按题意解释。", 27)
    chart("### 图 9. Manual post-survey Likert 分布\n\n颜色与 AI 版一致，但题目内容不同，应分别解读。", 29)
    markdown("### 4.3 开放式回答与解释边界\n\n以下表保留人工主题编码位置。缺少随机分配记录，结果解释为当前 Phase 1 样本的组间差异；长期维护和 crossover 结论需 Phase 2 数据。")
    code("display(open_text)")

    notebook = nbformat.v4.new_notebook(cells=cells, metadata=original.metadata)
    target = directory / "Analysis.ipynb"
    nbformat.validate(notebook)
    nbformat.write(notebook, target)
    return target


if __name__ == "__main__":
    print(build())
