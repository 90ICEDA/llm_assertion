# AssertionForge v3：表达能力修复与统一比较

本轮保留 v1/v2 封存数据。六个既有人工变异父 bug、八个方法，复用同一 18 槽初始池；无重新生成池、无新增父 bug。独立义务与两种未决规格解释延续 v2。模型版本 digest、配置、权限和隐藏输入在新请求前冻结。

## checker 能力与边界

新增 popcount(允许的 unsigned packed signal)，宽度 1–256，32 位无符号返回值，X/Z 传播；任意表达式参数不支持。delay=2 使用真实两拍 antecedent 队列，consequent 在到期拍取值，未替换为一拍或捕获数据。复位清空队列；pN 是显式零填充历史。其余表达式用 Icarus SV 类型/位宽规则。11 组最小测试、664 条预期检查通过；独立 Python 逐位计数、事件到期表和手写失败周期作为依据。

## 单纯能力修复（同一旧候选、旧输入、旧 RTL）

重放 731 条旧运行；原不支持 279 条，其中 221 条现在可执行。旧已支持运行的非预期变化 0 条。非法赋值、禁止历史、占位层级名等继续单列未知。
旧最终输出的 32 个未知 method×parent 单元中，14 个转为已知：8 个有限合约通过，6 个语义失败。多种误报/漏报/未触发标记见 old_final_candidate_transitions；这些标记可重叠，不能相加作为样本数。
上述转为已知的单元中，误报标记 0、漏报标记 6、必要条件未触发标记 4。

## 新反馈下重新比较

实际新模型请求 72 次；最终 8 个通过、23 个已知失败、17 个未知（48 个 method×parent 单元，只有 6 个独立父 bug）。

| 方法 | 通过 | 已知 | 未知 | 有效仿真 | 周期 | 编译尝试 | 输入/输出 token |
|---|---:|---:|---:|---:|---:|---:|---:|
| first | 1 | 3 | 3 | 20 | 356 | 24 | 1534/298 |
| equal_budget_select | 1 | 4 | 2 | 60 | 1066 | 72 | 4602/832 |
| existing_feedback | 1 | 4 | 2 | 68 | 1208 | 72 | 6248/870 |
| obligation_loop | 1 | 4 | 2 | 64 | 1142 | 72 | 10507/863 |
| generic_diff | 1 | 4 | 2 | 64 | 1138 | 72 | 10440/850 |
| no_fp_check | 1 | 4 | 2 | 32 | 569 | 36 | 8915/882 |
| no_observation_refinement | 1 | 4 | 2 | 60 | 1076 | 72 | 10428/884 |
| equal_information_control | 1 | 4 | 2 | 60 | 1076 | 72 | 10593/1052 |

所有方法通过的父案例相同：onehot。本轮没有义务闭环独有的完整成功；恢复这些成功首先来自统一 checker 能力修复。共同预算的逐对结果见 common_budget_pairwise。

表中资源只含方法侧（共享池生成按实际消耗槽逻辑归属）；隐藏验收、旧记录重放、能力测试和独立复现成本在 physical_validation_costs 中分开。无 SMT/形式求解；Ollama 完整缓存用量未知，原始 token/duration 保留。
各方法的已知父集合可能不同，不能直接比较各自排除未知后的成功率。所有通过仅来自同一个父 bug；八个方法的八条成功不是八个独立成功样本。

## 共同预算

主要资源为完整执行并产生全部 TRACE/CHECK 的有效仿真，未触发也计数。预定检查点为 2/4/6/8/12 次及 48/96/144/192/288 周期；只取首次恰好达到该点的完整候选评估输出。未到达明确记 unreached，未填平预算。每行保留设计、参数、输入哈希、周期与事务规模；no_fp 的工作负载缺少 fixed，是该消融定义，不能声称其同次数工作内容相同。token、编译失败和耗时同时报告，未声称全维度相等。
first 在首个评估后停止；因此不存在所有方法都能到达的高预算点。比较须读取 common_effective_budget_checkpoints 的 reached、available_methods 和 workload，不能拿最终输出表直接宣称等有效预算优势。
有效仿真的主计数是物理完整执行数；固定两次提案流程可能再次产生同一表达式。budget_ledger 同时列出按 checker/设计/输入内容去重的验证单位和重复执行数，重复执行不代表新增语义证据；没有为补齐检查点另外增加调用或验证。

## 结论限制

工具修复能够把原来的部分语法未知转成可检验的语义结果。任何方法之间的收益都须与同父 bug、同实际资源检查点和权限对照一起解释；不预设义务闭环胜出。spill invalid payload 与中断采样时序仍规格未决，不计完整通过。所有通过仅限封存有限输入、参数和变异控制；没有新增历史修复样本或全状态证明。
stat 原候选的当前输入比较与“捕获触发时长度”是不同语义；本轮保留原表达，通过独立义务暴露差异，没有人为改成 p2 值。隐藏验收结果未进入模型反馈。
run_results.status 表示工具执行状态，旧执行器的单条候选分类只采用主解释；完整合约结论应读取 parent_results、conditional_results 和逐义务数据。继承的少量描述性标签澄清见 implementation_notes.json，冻结候选与协议原字节未改动。

## 复现

```powershell
wsl -d Ubuntu -- sh /mnt/d/AssertionForge-main1/deliverables/repair_contract_v3_20261010/qualification/popcount_w65/reproduce.sh
wsl -d Ubuntu -- sh /mnt/d/AssertionForge-main1/deliverables/repair_contract_v3_20261010/qualification/delay_overlap_reset_boundary/reproduce.sh
wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/contract_v3_report.py
```
每条实际仿真目录另有 reproduce.sh；最终独立重编译和逐周期交叉核验见 audit.json。重新汇总不调用模型。

独立审计：11181 项一致性检查，通过=True；表达式逐周期交叉核验 {'matched': 1267, 'reference_grammar_unsupported': 3}。超出独立解释器的表达式单列，未冒充已核验。
