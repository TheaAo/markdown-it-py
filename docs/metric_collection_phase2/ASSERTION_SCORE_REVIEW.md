# 二阶段 Assertion Score 源码复核

复核日期：2026-10-05。复核者：Codex，依据冻结提交源码和临时副本中的针对性执行验证。
本次只裁定自动分析器标记的四个 `uncertain`，不修改参与者代码或自动采集结果。

自动分类的共同触发条件是：分析器已检测到 SUT 执行，但断言表达式未被静态
依赖分析关联到 SUT。`uncertain` 是分析器未能解析依赖，不是断言无效的结论。

| 参与者与函数 | 原因 | 源码复核结论 |
| --- | --- | --- |
| 03 `test_core_after`，第 94 行 | `normalize` 包装回调和自定义规则回调向 `execution_order` 写入事件，分析器未追踪回调副作用 | `non_trivial`。断言完整序列为 `["normalize", "core_test_rule"]`，检查执行和先后顺序 |
| 08 `test_file`，第 39 行 | `md.render()` 的结果写入 `output.html` 后再读取；分析器未贯通文件写入、读取和循环变量之间的数据流 | `non_trivial`。逐行比较实际渲染结果与参考 HTML，但存在长度检查缺陷 |
| 08 `test_core_after`，第 115、118 行 | SUT 调度的回调修改 `calls` 列表，分析器未识别其副作用 | `non_trivial`。检查自定义规则确实执行，且 `normalize` 的记录位于其前面 |
| 09 `test_core_after`，第 67 行 | 回调将 `state.src` 写入 `events`，分析器未追踪 SUT 状态到外部列表的依赖 | `non_trivial`。输入含 CRLF，断言观察到 LF 规范化结果，并检查恰好一次回调记录；间接验证执行发生在规范化之后 |

## 针对性验证

原始测试此前均已在冻结 SUT 上通过。复核时，仅在临时导出的副本中通过 pytest
插件临时替换 SUT 行为，参与者文件及正式 SUT 均未修改。证据保存在
`results/phase2/assertion_score/manual_review/`。

- 03、08、09 的 `test_core_after`：将 `MarkdownIt.parse` 临时改为不执行规则，
  三个测试均出现断言失败，证实断言依赖实际规则执行。
- 09 的 `test_core_after`：让 `normalize` 规则不做处理，测试断言失败，证实其
  确实能检测未规范化的 CRLF 输入。
- 08 的 `test_file`：将渲染结果改为错误的非空 HTML，测试断言失败，证实比较
  对实际渲染内容敏感。
- 08 的 `test_file`：将渲染结果改为空字符串，测试仍通过。`zip(file1, file2)`
  在任一文件结束时停止；空输出不会执行断言，额外或缺失尾部行也可能漏检。
  因此这是有实质内容比较但不完整的 oracle，不能解释为完整文件回归验证。

这些是用于判断断言性质的针对性验证，不是正式 Mutation Score 数据。
原始 source-function 评分规则要求至少一个非平凡 oracle；它不要求断言能捕获
所有错误。因此 08 的长度缺陷单独记录，不将其降为平凡断言，也不修改提交代码。

## 复核后结果与可追溯性

`raw/` 保留原始自动证据；复核前的汇总表已删除。
`assertion_score.csv` 纳入四项裁定，并保留 `automated_assertion_score`。
`manual_review/adjudications.json` 记录冻结提交、源位置、理由和复核者；
`probe_results.json`、探针模板和 pytest 输出保存验证证据，
`review_manifest.json` 记录原始输入及裁定、验证、复核表的哈希。

| 参与者 | 自动评分 | 纳入本次复核后的评分 |
| --- | --- | --- |
| 03 | 6/7 = 0.857143 | 7/7 = 1.000000 |
| 08 | 5/8 = 0.625000 | 7/8 = 0.875000 |
| 09 | 7/8 = 0.875000 | 8/8 = 1.000000 |

其余参与者分数不变。剩余两个自动 `trivial` 分类不在本次四项裁定范围内，
`review_candidates.csv` 保留其待复核状态。全体自动 `uncertain` 已完成本次源码复核。
