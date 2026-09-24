# Phase 1 统计分析说明

## 1. 已完成的工作

本目录实现了 Phase 1 的可重复统计分析。分析对象为 14 名实际参与者，其中 AI 组 6 人、Manual 组 8 人。原始结果文件保持只读，分析过程会从 `results/` 下的指标 CSV 重新构建参与者级主表。

已完成的内容包括：

1. 合并 error rate、coverage、assertion score、mutation score、generation time、execution time、efficiency、test smell 和问卷数据。
2. 执行 15 项数据完整性检查，包括参与者分组、错误数量恒等式、预期缺失值、mutation review 精度，以及参与者 8 和 11 的特殊情况。
3. 对每个指标计算分组样本量、均值、标准差、中位数、四分位距、最小值和最大值。
4. 计算 AI 组均值减去 Manual 组均值、20,000 次组内 bootstrap 95% 区间、Cliff's delta 和双侧精确置换检验。
5. 对三个预先指定的主要结果进行 Holm 多重比较校正。
6. 实施 mutation 原始分数、无有效测试、参与者 8 assertion、参与者 11 execution time 和对数时间等敏感性分析。
7. 分别汇总两份不同版本的 post-survey。没有把题意不同的问题直接作组间比较。
8. 导出开放式回答编码表，保留空白的 `theme_codes` 和 `coding_notes` 列供后续人工主题分析。
9. 将全部图表生成代码直接写入 notebook。每张图对应一个独立代码单元，运行该单元时同时显示图形并保存 PNG 和 SVG。

## 2. 主要结果

所有差异均定义为 **AI 减去 Manual**。

| 主要结果 | AI 均值 | Manual 均值 | 均值差及 bootstrap 95% 区间 | Cliff's delta | 精确 p 值 | Holm p 值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 估计调整后 mutation score | 69.09% | 34.84% | +34.25 个百分点 [16.06, 53.14] | 1.000 | 0.0087 | 0.0130 |
| Mutation generation efficiency | 0.357/1000 秒 | 0.081/1000 秒 | +0.276/1000 秒 [0.197, 0.358] | 1.000 | 0.00033 | 0.0010 |
| Test smell density | 3.33% | 12.70% | -9.37 个百分点 [-16.19, -3.65] | -0.917 | 0.0065 | 0.0130 |

在当前 Phase 1 数据中，AI 组的主要有效性和生成效率指标更高，test smell density 更低。样本很小，因此论文应同时报告原始参与者点、差异大小和区间，不能只报告 p 值。

敏感性分析提示以下边界：

- 使用未调整的 raw mutation score 时，组间差异方向和精确 p 值不变。
- 将参与者 4、6 的无有效测试套件极端地设为 test smell density = 1 后，方向仍有利于 AI，但精确置换 p 值变为 0.0686。这个压力测试表明可维护性结论依赖于如何解释“没有可维护测试产物”。
- 将参与者 8 唯一的 uncertain assertion 当作 non-trivial 后，assertion score 的精确 p 值由 0.0152 变为 0.0606，因此 assertion score 只能作为探索性结果谨慎解释。
- 排除参与者 11 后，execution time 的组间差异仍不清楚；mutation execution efficiency 的结果会明显变化，说明该效率指标受 656 个展开 pytest items 影响。

## 3. 主要脚本及作用

### `phase1_analysis.ipynb`

主分析 notebook。按数据核验、主要结果、次要结果、敏感性分析和问卷结果的顺序展示分析过程。图表代码不再隐藏在外部 `.py` 文件中：完成 setup 和统计分析单元后，可以按顺序逐个运行 Figure 1 到 Figure 8，每个代码单元只生成一张图。

### `analysis_utils.py`

负责数据读取、参与者级主表合并和统计计算。主要功能包括：

- 验证数据完整性和预期缺失值；
- 计算描述性统计；
- 实现精确置换检验、bootstrap 区间和 Cliff's delta；
- 实现 Holm 校正；
- 执行预先指定的敏感性分析；
- 生成问卷分布和开放式回答编码表。

### `run_analysis.py`

统计分析命令行入口。运行一次可重新生成所有表格和 source checksum manifest；它不再生成图形，图形由 notebook 中的独立单元生成：

```bash
python3 scripts/phase1_analysis/run_analysis.py
```

### `config.py`

集中定义仓库路径、随机种子、bootstrap 次数、分组颜色，以及主要和次要指标的名称、单位与方向。

### `self_check.py`

验证 Cliff's delta、精确置换检验、Holm 校正和完整数据检查：

```bash
python3 scripts/phase1_analysis/self_check.py
```

## 4. 生成文件

`outputs/tables/` 包含：

- `participant_master.csv`：每位参与者一行的分析主表；
- `data_validation.csv`：数据核验结果；
- `data_completeness.csv`：每个指标的有效样本数和缺失 ID；
- `data_dictionary.csv`：指标定义、单位、角色和缺失值规则；
- `descriptive_statistics.csv`：分组描述统计；
- `primary_results.csv`：三个主要结果及 Holm 校正；
- `secondary_results.csv`：探索性次要结果；
- `sensitivity_results.csv`：特殊数据处理下的结果；
- `questionnaire_baseline.csv` 和 `questionnaire_likert.csv`：问卷定量摘要；
- `questionnaire_open_text_coding.csv`：开放式回答人工编码模板。

`outputs/figures/` 包含主要结果原始点图、差异区间图、次要有效性图、时间关系图、test smell 类型图和两组独立的 Likert 分布图。每张图同时提供 PNG 和 SVG，且都由 `phase1_analysis.ipynb` 中相应的 Figure 单元直接生成。

`outputs/analysis_manifest.json` 保存固定随机种子、bootstrap 次数及所有输入文件的 SHA-256，用于确认后续运行是否使用了相同数据快照。

## 5. 解释限制

1. 当前缺少分层随机和实际分配过程记录，因此本轮不进行基于随机化分层的调整，也避免作过强的因果解释。
2. 本分析只覆盖 Phase 1。Test smell density 只能解释为静态可维护性风险，不能替代 Phase 2 的真实维护成本和纵向结果。
3. Mutation score 是等价变异体抽样复核后的估计调整值，而不是对所有等价变异体进行穷尽式人工确认后的精确值。
4. Post-survey 的 AI 和 Manual 版本题目不同，因此分别描述，不构造跨版本合成量表。
5. 开放式回答仍需要人工编码、反例检查和主题复核；脚本没有用词频自动生成结论。
