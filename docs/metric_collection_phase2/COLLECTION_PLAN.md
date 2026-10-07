# 二阶段数据采集方案与复用说明

更新日期：2026-10-07。主要指标已完成八人采集；当前结果与待收尾事项见
[采集进度](COLLECTION_STATUS.md)。本文保留采集顺序及初始迁移记录，供复现使用。

## 研究依据与范围

已阅读 `reference/Mid-report.pdf`、`Phase1-项目和任务说明.pdf`、
`Phase2-项目和任务说明.pdf`。研究比较 Copilot 辅助与手工测试的有效性、效率、
可维护性，并结合资历和问卷解释差异（RQ1–RQ3）。二阶段包含旧测试维护及新模块
测试生成，必须保留阶段、参与者及任务类型，不能把所有变化解释为维护效果。

### 实际设计更新（2026-10-04）

研究者确认：只有八人继续参加第二阶段，因此放弃原 crossover design，二阶段
所有参与者均使用 AI。保留中期报告 PDF 原文作为历史方案，当前采集及分析以此
更新为准。研究者在确认二阶段参与人数后决定全部使用 AI；这一确认说明了决策
依据，不额外推断决策时是否已接触结果。八人统一使用 Copilot，模型、模式、时间
限制和实验环境一致；后续采集 manifest 应记录具体版本及环境配置。

八人均维护自己在一阶段提交的代码。两阶段间隔约 2–3 个月，期间未修改代码。
因此可按参与者连接一阶段最终提交与二阶段维护提交，保留旧测试的来源组别。

耗时表和二阶段 post-experiment survey 的参与者集合一致：
`02, 03, 04, 05, 07, 08, 09, 12`。按一阶段耗时表中的原始组别：

| 一阶段组别 | 二阶段使用 AI 的参与者 | 人数 |
| --- | --- | --- |
| AI | 02、03、07、12 | 4 |
| Manual | 04、05、08、09 | 4 |

当前设计为有参与者流失的两阶段随访，第二阶段为所有人使用 AI 的维护与扩展任务。
一阶段的 AI/Manual 比较仍保留；第二阶段没有同期 Manual 对照组，不能估计
二阶段 AI 相对于 Manual 的处理效应，也不能作为 AB/BA crossover 分析。
`phase1_group` 与 `phase2_group` 单独保存，二阶段实际参与者的后者为 AI；
可描述 `AI→AI`、`Manual→AI` 的使用历史，但它们不是 crossover 序列。

二阶段重点报告维护任务完成、有效性、smell 变化、任务耗时及使用体验。参与者
均维护自己的旧测试，可探索原 AI 测试与原 Manual 测试在同样使用 AI 后的表现，
并核对进入二阶段时的测试质量；这两个四人子组不构成二阶段工具对照。
前后差值同时受任务、SUT、学习、时间间隔和参与者流失影响，不能直接归因于 AI。
资历相关结果以个体和探索性描述为主，避免八人样本承担复杂交互或大量检验。

若有现成记录，归档具体实验日期、设计变更日期、未继续参加的原因、Copilot
模型/模式及版本、统一时间限制、环境配置和实际使用记录；不据此阻断采集开发。

中期报告中的指标定义继续适用：错误率覆盖全部提交测试；coverage、mutation、
assertion score 和 smell 使用有效测试。计数单位保持一阶段口径：错误率以 pytest
实例计数，assertion/smell 以源测试函数计数，并记录部分有效的参数化函数。
通过测试并不意味着满足全部任务要求；另保留任务要求核验表，不能混入错误率定义。

| 范围 | 文件/函数 | 二阶段要求 | 分析用途 |
| --- | --- | --- | --- |
| 路径维护 | `tests/task/phase1/task.py`: `test_file`, `test_spec` | 测试及材料整体迁移后仍可正确读取 | 维护 |
| 行为维护 | 同文件: `test_non_utf8` | 验证 SystemExit、退出码 1、UTF-8 解码错误信息 | 维护 |
| 断言强化 | 同文件: `test_core_after` | 验证实际执行发生在 normalize 之后 | 维护 |
| 保留旧测试 | 同文件: `test_parse_fail` | 二阶段未要求修改，单独保留标记 | 回归背景 |
| 新功能生成 | `tests/task/task2.py`: `test_make_fence_after`, `test_make_fence_at` | 冒号 fence、内容及默认 fence 的保留/替换 | 生成 |

主表报告二阶段完整参与者测试套件；另外按维护、新生成及保留旧测试分组。
coverage 需对每组及完整套件分别测量，组间覆盖集合可能重叠，不能直接相加。
执行时间应测量两个文件的有效测试共同执行，不能相加两个文件的中位数。

## 本次目录调整

```text
scripts/
  metric_collection_phase1/   # 原采集目录以及散落根目录的计时/smell脚本和协议
  metric_collection_phase2/   # 二阶段编排与适配层，复用一阶段采集引擎
  profiler.py                # 上游开发工具，保持原路径
  build_fuzzers.py
results/
  phase1/                    # 原结果、问卷、汇总表；文件内容保持原样
  phase2/
    inventory/               # 本地提交盘点，尚非正式采集结果
    error_rates/, coverage/, assertion_score/, mutation_score/
    test_smells/, execution_time/, efficiency/
    generation_time/         # 八人正式耗时及秒数换算
    generation_time.csv      # 保留十六人布局的原始耗时表
    Post-experiment Survey (Phase 2).csv # 二阶段原始问卷导出
docs/
  metric_collection/         # 一阶段方法与历史协议
  metric_collection_phase2/  # 进度、方案及各指标方法
tests/
  metric_collection/         # 一阶段回归测试（已更新导入）
  metric_collection_phase2/  # 二阶段适配测试
```

一阶段 CLI 默认输出已改为 `results/phase1/`，导入及现行使用文档同步更新。
原始 JSON/CSV、哈希、采集时间和协议中的历史路径不改写；相对 `output_file` 仍可
在迁移后的 manifest 目录解析。历史绝对路径仅作溯源，消费者不能依赖其存在。
根目录 HANDOFF 文档加迁移说明，正文保持历史原貌。
大型 mutation 历史工作数据由 Git 忽略；二阶段正式结果及最终复核证据已跟踪。
初始目录迁移时，134 个已跟踪的结果文件逐个核对
与原 HEAD 内容一致；未跟踪的 mutation 工作目录同样整体移动，没有重算。

## 采集顺序与每一步的完成条件

1. **冻结输入及分组表。** 更新远程 refs 后固定每位参与者的两个阶段提交 SHA、
   二阶段开始提交、SUT baseline、材料/配置哈希和实际工具分组。运行下面的 inventory。
   根据缺失、分支别名、历史关系和 SUT 差异核验最终映射；不根据编号猜测分组。
   当前二阶段名单以研究者确认及耗时/问卷交叉核对的八人为准；一阶段剩余八人
   不纳入二阶段正式采集。预期标准分支 `experiment-NN-phase2`，
   正式采集已使用八人的标准分支；09 号拼写不同的历史 ref 未作为替代。
   SUT baseline 和参与者提交已冻结在各指标 manifest 中。
2. **建立二阶段测试清单及有效测试池。** 保持两个源文件及材料目录结构，逐文件
   错误分类，记录文件路径、函数名、参数化实例 nodeid、分类原因和源文件哈希。
   缺文件、未提交、缺函数、收集失败及零有效测试分别记录，不能用 0 分代替缺失。
   未修改占位函数也需核验任务完成度。通过原始 suite 收集与隔离结果比较检查
   fixture、跨文件导入、`__file__`、相对路径行为，防止采集器造成假错误。
3. **一次复用有效池采集 coverage 与 assertion。** 单独保留参与者覆盖率和与仓库
   原有测试合并后的覆盖率，避免将原有套件贡献计入参与者。assertion 分析使用
   每文件明确的预期函数集合，再按源身份汇总；核验新函数及异常断言的数据依赖。
4. **smell 采集。** 直接读取步骤 2 的有效性证据，无需再运行 pytest；沿用一阶段
   正式 AST 检测类别/版本，保留 partial-valid 状态及人工复核记录。工具辅助结果
   与正式指标分开。先检查新 fence 函数，避免仍按固定五函数计算分母。
5. **执行时间 pilot 后正式测量。** 使用同一机器、解释器及依赖，沿用预热、重复次数
   和统计口径；仅测共同有效套件，不开 coverage/mutation，不与重任务并发。
   从已核验的八人提交中覆盖一阶段不同来源组、参数化及无效测试情形作 pilot，
   随后冻结协议。二阶段参与者均使用 AI。
6. **mutation 最后执行。** 在已确认二阶段 SUT 上生成 catalog，重建任务相关
   specified/extended workload，加入 CLI 新行为和 fence after/at 可追踪要求。
   先 dry-run，再小样本核验预算、超时、有效池、确认执行及 catalog 完整性，
   再正式采集和等价 mutant 审查。沿用一阶段流程，不能沿用旧 catalog/kill cache。
7. **问卷、耗时与最终合并。** 二阶段问卷独立导入，按参与者及阶段连接，保留缺失。
   二阶段自报耗时应标为任务完成/维护与生成耗时，不能复制一阶段 generation time。
   仅在时长为正且指标可用时计算效率。输出完整套件表、任务分组表和配对长表，
   保留 phase1_group、phase2_group、使用历史、资历、任务范围和工具版本。

上述顺序为采集依赖与复现建议；主要指标已完成，无需重复执行已冻结的采集。
断言复核已收尾；当前待完成问卷缺失处理和论文分析，详见进度页。
一阶段保留 AI/手工比较；二阶段作描述性维护/扩展分析，按一阶段来源组探索差异。
阶段间以八名继续参加者配对并考虑资历、流失、任务范围和 SUT
变化。跨阶段 coverage/mutation 分母不同，原始分数差只能作为描述，不能直接解释
为维护造成的提升；如需共同范围比较，另定义可映射的共同模块/行为范围。

## 一阶段复用分析

| 现有脚本/模块 | 可复用部分 | 必要改动 |
| --- | --- | --- |
| `collect_error_rates.py` | 分块、语法/运行/功能错误分类、实例级结果 | 多文件编排、目录保留、一次缓存有效性结果 |
| `collect_coverage.py` | coverage JSON 解析、有效实例筛选、两种覆盖范围 | 接收既有有效池、两个文件联合测量及任务范围 |
| `collect_assertion_score.py` | AST 依赖传播、异常/capsys 断言、partial-valid | `_report_from_results` 已支持 `expected_tests`，二阶段适配器传入实际函数集合，不复制分析器 |
| `collect_all_branches.py` | Git/JSON 辅助函数、保护路径核验 | 单 TASK_PATH、固定参与者/排除名单及五函数验证器需配置化；暂不直接运行于二阶段 |
| `collect_test_smells*.py`, `detect_test_smells_ast.py` | detector 与读取错误率证据的流程 | 五函数集合改为清单驱动，使用文件+函数身份 |
| `collect_execution_time.py`, `execution_timing_protocol.json` | 计时器及重复测量统计 | 支持两个文件、接收有效池，避免再次错误分类 |
| mutation catalog/cache/review/summarize 脚本 | 生成、执行确认、等价抽样、加权估计及审计 | 二阶段 workload/材料路径/catalog；阶段和完整输入哈希隔离缓存 |
| summarize 脚本 | 表格字段、比例校验、输出函数 | 加 phase/task_scope，assertion 验证器取消固定五函数假设 |

二阶段目录负责适配与编排；各指标复用一阶段引擎或辅助函数，效率由冻结结果
直接计算。inventory 复用一阶段 Git/JSON 辅助函数。
当第二个消费者实际需要适配时，再把对应引擎提取到 `scripts/metric_collection_common/`
并保留一阶段薄入口。不提前复制整套脚本，也不为尚未使用的抽象大规模重构。
长期保存有效池及 provenance，coverage/计时/mutation 使用同一份实例选择；缓存键
包含 SUT、测试、材料、配置、依赖及协议哈希，不能仅凭参与者 ID 复用。

## 当前可执行步骤

```bash
python scripts/metric_collection_phase2/inventory_submissions.py
# 默认读取 results/phase1/error_rates/collection_manifest.json
# 默认输出 results/phase2/inventory/submissions.json
```

该命令仅查看本地 Git refs，不 fetch、不创建 worktree、不运行参与者测试。
`pending_submission_review` 表示文件及保护路径初检通过，不代表已经提交完成、
任务满足要求或测试有效。返回成功只说明盘点完成，所有异常仍保存在清单中。
正式采集已完成八人的错误率、coverage、assertion、mutation、smell、耗时和六项
效率。有效池为 58 个 pytest 实例，分类错误率均为 0；08 号迁移到
`tests/test_cli.py` 的 `test_non_utf8` 已纳入，未实现的 `test_parse_fail` 单独记录。
详见 [采集进度](COLLECTION_STATUS.md)及 [错误率方法](ERROR_RATES.md)。

### 初始盘点（历史预检）

首次本地盘点：5 个 `pending_submission_review`、1 个 `missing_task_file`、
10 个 `missing_branch`。`experiment-02-phase2` 缺少标准路径下的旧测试文件，
需要检查其实际布局；本地 refs 未刷新，这些状态不能解释为最终流失或不合格。
此首次盘点覆盖旧的十六人清单，属于历史预检；正式二阶段范围更新为上述八人。

### 二阶段耗时换算

`results/phase2/generation_time.csv` 保留原有列、行顺序及原始 `total_time`。
仅为 `status=collected` 的八人补齐两列，共十六个单元格：

- `total_time_seconds = hours * 3600 + minutes * 60 + seconds`。
- 研究者已确认总用时包含理解任务、维护旧测试、新测试编写及调试等全部过程。
  沿用一阶段既有口径，`generation_time_seconds = total_time_seconds`，表示
  完整任务用时，不表示扣除理解时间后的纯编写时间，也不能单独解释为维护耗时。
- `not_participated` 行的秒数列保持空白，即使原始耗时栏有内容也不纳入二阶段分析。
  不删除这些原始值；其来源需由研究者核实。
- 12 号原记录 `00:37:59` 为录入错误；根据研究者更正为 `00:09:25`，
  `total_time_seconds` 和 `generation_time_seconds` 均为 565 秒。

秒数以 CSV 数值保存，可直接供后续统计脚本使用。问卷导出内容保持不变。

初始迁移验证曾运行 `tox -e py311 -- tests/metric_collection tests/metric_collection_phase2`，
通过 162 项测试；该数字仅描述当时的迁移验证。各指标采集及验证记录以对应方法
文档和 manifest 为准。本次整理仅修改文档，不重算指标、不改写冻结证据。

## 其他可优化位置

- 后续将一阶段测试目录改为 `tests/metric_collection_phase1/`，与二阶段统一；
  本次保持测试/fixtures 原位置，避免无收益的额外迁移。
- 一阶段文档可归档到 `docs/metric_collection_phase1/`；其中冻结协议和历史源码哈希
  必须保留原值，并通过映射说明当前位置。
- 最终跨阶段分析放 `results/analysis/`，避免写进任一阶段的原始结果；二阶段
  `raw/summary/manifest` 层级沿用一阶段惯例，无需另一套表格体系。
- 问卷原件继续按阶段保存，建立列映射及匿名参与者键，不改写原始问卷来适配脚本。
