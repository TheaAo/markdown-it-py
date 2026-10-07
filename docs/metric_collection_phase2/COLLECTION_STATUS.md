# 二阶段采集进度

更新日期：2026-10-07。核对依据为 `pilot-metric-phase2` 合并后的结果提交
`00e5743` 中的 CSV、采集 manifest、复核记录及原始计时观测。

**八人的主要指标数据已齐全；断言复核已收尾；问卷缺失处理及论文分析仍需收尾。**
数据是否已采集、分类是否已复核和论文是否已完成分析是不同状态。

## 研究设计与有效测试范围

参与者为 02、03、04、05、07、08、09、12。一阶段 AI 来源组为 02、03、07、12，
Manual 来源组为 04、05、08、09。确认二阶段参与人数后放弃 crossover，八人均在
相同模型、模式、时间限制和环境下使用 Copilot，维护各自的一阶段提交。
两阶段间隔约 2–3 个月，期间未修改代码。

最终有效池为 58 个 pytest 实例；08、09 各八个，其余六人各七个。
08 号迁移到 `tests/test_cli.py` 的 `test_non_utf8` 已纳入；其未实现的
`test_parse_fail` 单独记录为缺失任务，不计作执行错误。零错误率不表示所有要求
均满足。当前 assertion/smell 数据也恰有 58 个源函数，但其计数单位仍是源函数，
不能因本次数量相等而与 pytest 实例混用。

## 指标与正式结果入口

以下路径均相对于 `results/phase2/`。

| 指标 | 当前状态 | 正式结果 |
| --- | --- | --- |
| Syntax / Runtime / Function Error Rate | 8/8；58 个有效实例，三类错误率均为 0 | `error_rates/error_rates.csv` |
| Statement / Branch Coverage | 8/8；保留参与者覆盖与项目测试合并覆盖 | `coverage/coverage.csv` |
| Assertion Score | 8/8 已导出；四项 uncertain 已裁定，两项 trivial 已由研究者确认 | `assertion_score/assertion_score.csv` |
| Mutation Score | 8/8；specified 调整后估计及区间已导出 | `mutation_score/mutation_score.csv` |
| Generation Time | 8/8；表示完整任务用时，12 号为 565 秒 | `generation_time/generation_time.csv` |
| Execution Time | 8/8；每人 15 次正式测量，全体 CV 小于 5% | `execution_time/formal/summary/execution_time.csv` |
| 三项 Generation Efficiency | 8/8；statement、branch、mutation 分数除以总任务秒数 | `efficiency/generation_efficiency.csv` |
| 三项 Execution Efficiency | 8/8；相应分数除以正式执行时间中位数 | `efficiency/execution_efficiency.csv` |
| Test Smell Density | 8/8；42 个确认配对、0 个 uncertain 配对；另有任务分组结果 | `test_smells/summary/test_smell.csv` |
| Post-experiment Survey | 八人均提交；两道量表题漏答 | `Post-experiment Survey (Phase 2).csv` |

`generation_time.csv` 根目录文件保留十六人原始表布局；`generation_time/` 中的
八人表用于效率计算。两份表的参加者记录一致。未参加者的原始耗时不纳入二阶段
统计。总任务用时包含理解、维护、新测试编写和调试，不能单独解释为纯维护耗时。

Execution Time 的正式数据是研究者选择的最新完整 `new-run`，已原样提升到
`formal/`；不混合早期观测，也不按参与者选择最佳运行。核验了 120 次正式观测
全部通过及八个重算中位数。环境、预热及跨阶段可比性见
[计时说明](../../results/phase2/execution_time/README.md)。

效率的输入与输出哈希、提交身份及比值已核对。Coverage 分子来自参与者独立
覆盖的精确计数；mutation 分子为 `specified_estimated_adjusted_score`。
方法见 [效率说明](../../results/phase2/efficiency/README.md)。

05 号 `tests/task/phase1/task.py::test_parse_fail` 与 08 号
`tests/task/task2.py::test_default_fence_exists` 已由研究者于 2026-10-07
确认 `trivial`，两项分数不变。六项复核候选均已结案；确认记录及对应证据哈希见
`assertion_score/manual_review/trivial_confirmations.json`。此前四项 Codex 复核记录保留。

## 待完成的收尾

1. **问卷缺失处理。** 03 号第 16 题和 07 号第 13 题漏答。保留原始空值；统计时
   说明处理方法及每题有效样本数，不能将空值当作 0 或中性评分。
2. **论文分析与方法同步。** 完成配对长表、统计和定性分析，并在论文方法中说明
   全 AI 随访、参与者流失、时间口径及复核限制。主要指标齐全不意味着这些分析
   已完成。本页不将未收集的分任务耗时列为已完成数据。

## 需要保留的解释限制

- Mutation Score 的修正后任务相关 catalog 含 5,051 个 mutant，specified 主范围为 5,045。
  固定分层样本 100 个，16 个 confirmed equivalent、84 个 non-equivalent，
  主范围精度条件均通过。等价性只有一位 Codex 源码复核者，没有独立二次复核；
  区间反映抽样不确定性，不包含可能的复核误差。超时按协议从 eligible 分母排除，
  不等同于证明等价。详见 [Mutation Score](MUTATION_SCORE.md)。
- 没有独立的任务分组耗时，因此维护/新生成任务的效率不可用；完整套件六项效率
  已齐全。mutation 效率区间条件于固定观测时间，不是包含耗时误差的完整区间。
- 一阶段与二阶段的 SUT、任务、测试布局和计时 Python 环境不同。二阶段没有同期
  Manual 对照，前后差值不能直接归因于 AI；一阶段来源组差异仅作探索。

## 方法文档与历史记录

[采集方案](COLLECTION_PLAN.md)记录研究设计、复用和采集顺序。各指标方法见
[Error Rate](ERROR_RATES.md)、[Coverage](COVERAGE.md)、
[Assertion Score](ASSERTION_SCORE.md)、[断言复核](ASSERTION_SCORE_REVIEW.md)、
[Mutation Score](MUTATION_SCORE.md)和 [Test Smells](TEST_SMELLS.md)。

初始 inventory、57 实例错误率结果、自动断言分类、旧 mutation 目录和执行修正
记录均属于历史证据。当前状态以本页和各指标正式 manifest 为入口；不改写历史
JSON、CSV、源码哈希或复核决定以消除历史差异。
