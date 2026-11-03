# AssertionForge 修复目标保护实验（2026-10-09）

本报告由逐次运行记录生成。统计单位是父 bug；窗口、输入轨迹和多条断言不会增加独立样本数。所有结果仅限实际仿真输入与检查范围。

## 设置与可复现范围

冻结 6 个父案例：onehot、filter-counter（case122）、Depth=0 FIFO、spill/flush、统计流水线、中断使能。先完成前三例的 fixed/buggy 六次试运行，再冻结扩展集。旧自然候选来自已有 Qwen3 slot 01–07；slot 08 是人为矛盾控制。filter-counter 不在旧 slot 池，旧签名实验中它仅作为明确标注的工程控制。新方法比较使用另外冻结的 Qwen2.5 7B 候选池。

仓库 `.git` 无有效 HEAD；版本用 SHA256 清单标识。已检索仓库及父目录，未找到 AGENTS.md；阅读 README、结果报告约束、旧碰撞审计与实际 checker。历史修复提交无法追溯，六例均按已有人工变异报告，不能称为历史修复样本。

工具：WSL Ubuntu、Python 3.12.3、Icarus 12.0；完整版本原始输出见 version_*.stdout/stderr。固定种子 20261009。Qwen CPU 实际配置见 runtime_amendment.json、每次 request.json 与 model_tags.json。GPU 18 次调用因 CUDA kernel image 错误失败，保留在 failed_model_calls_gpu；CPU 预检与失败调用不混入方法效果分母。

原始 assertion 与实际执行的 checker_tb.sv 分开保存。Icarus 执行显式过程监视器，不宣称原生 SVA/formal proof；支持当前与下一拍蕴含、明确 reset-to-zero 的 p1/p2/p3 观察寄存器。旧 slot AST 另由 Python 在保存的 RTL 轨迹上逐拍交叉核验。输入在下降沿驱动，上升沿 NBA 前采样。复位首样本的 X 不记有效违例，复位外 X 记未知。

## 1. 旧签名与语义差异

对冻结父案例中的 25 个旧 FP/TP 同签名对保留原始签名、两条 assertion 和来源。自然候选中 11 对在新合法输入上出现不同的合法行为接受集合或目标违例覆盖集合。这个数字表示集合差异，不是胜负或成功率；仅 fail-hit 大小不同不构成质量排序。slot 08 控制不计入自然候选结论。完整逐对依据见 collision_pairs.json。

- `case438_cc_fifo_protocol_suppress_2`：distinguished_on_checked_legal_inputs；原文 A：`assert property (@(posedge clk_i) disable iff (!rst_ni) (push_i) |=> (!empty_o));`；B：`assert property (@(posedge clk_i) disable iff (!rst_ni) (push_i) |=> ((empty_o == push_i)));`。
  证据 `deliverables/repair_contract_20261009/runs/e12/held_24/fifo/correct`：A 首败 None，B 首败 7；A/B 误报周期 [] / [7, 8, 9, 10, 11, 12, 13]；漏报周期 [] / []。

- `case505_axis_stat_counter_frame_pulse_early`：distinguished_on_checked_legal_inputs；原文 A：`assert property (@(posedge clk_i) disable iff (!rst_ni) (frame_done_i) |=> (!stat_valid_o));`；B：`assert property (@(posedge clk_i) disable iff (!rst_ni) (frame_done_i) |=> ((stat_valid_o == frame_done_i)));`。
  证据 `deliverables/repair_contract_20261009/runs/e12/held_24/stat/correct`：A 首败 4，B 首败 3；A/B 误报周期 [4, 5] / [3, 5]；漏报周期 [] / []。

- `case510_cc_spill_register_flush_push_priority`：distinguished_on_checked_legal_inputs；原文 A：`assert property (@(posedge clk_i) disable iff (!rst_ni) (flush_i) |=> (!valid_o));`；B：`assert property (@(posedge clk_i) disable iff (!rst_ni) (flush_i) |=> ((data_o == flush_i)));`。
  证据 `deliverables/repair_contract_20261009/runs/e12/held_24/spill/correct`：A 首败 None，B 首败 3；A/B 误报周期 [] / [3, 4, 5, 6, 7]；漏报周期 [] / []。

## 2. 窗口与事务

H=24、2H=48、4H=96；12 个父案例×RTL 比较检查了尾段输入保持不变，其中按 fail-hit 排序发生变化的比较为 0。事务增量对照独立执行 more_24/48/96。window_results.json 保存排名；每次 transactions.json 标注输入 episode 或接受事件，candidate_results.csv 给出首次失败周期与对应事务。

独立违例数统一保留 unknown：可数的是义务违反采样点、触发和接口接受事务，不能可靠把相邻报警归为独立因果事件。保持输入不变也可能产生连续被接受事务，因此保持窗口组与真实新增事务组的区别需读取 accepted_transactions；尤其不把 held-flush 每拍重复命令视为一次事件。

## 3. 观察信息与表达能力

observation.json 的实际执行对把观察限制为完整输入历史：相同输入驱动 fixed/buggy 而义务标签不同，增加输出信号后在已检查执行对上消除冲突。该受限观察实验与方法默认完整端口权限不同，不能据此宣称默认权限无解。history_refinement.json 则使用方法的全部允许端口，比较当前采样、1/2/3 拍记忆及完整复位后历史；每个冲突都保存两条实际执行引用与完整允许历史。

- case101_prim_onehot_multihot_suppressed：history=0 的冲突组=0, history=1 的冲突组=0, history=2 的冲突组=0, history=3 的冲突组=0, history=complete 的冲突组=0。
- case122_prim_filter_ctr_streak_reset_ignored：history=0 的冲突组=3, history=1 的冲突组=6, history=2 的冲突组=4, history=3 的冲突组=0, history=complete 的冲突组=0。
- case438_cc_fifo_protocol_suppress_2：history=0 的冲突组=0, history=1 的冲突组=0, history=2 的冲突组=0, history=3 的冲突组=0, history=complete 的冲突组=0。
- case510_cc_spill_register_flush_push_priority：history=0 的冲突组=5, history=1 的冲突组=0, history=2 的冲突组=0, history=3 的冲突组=0, history=complete 的冲突组=0。
- case505_axis_stat_counter_frame_pulse_early：history=0 的冲突组=4, history=1 的冲突组=2, history=2 的冲突组=0, history=3 的冲突组=0, history=complete 的冲突组=0。
- case135_prim_intr_enable_mask_ignored：history=0 的冲突组=3, history=1 的冲突组=0, history=2 的冲突组=0, history=3 的冲突组=0, history=complete 的冲突组=0。

受控 onehot 抽象只观察 boolean(oh_i) 与 err_o，实际枚举 16 个输入向量、两种 RTL，并检查两 Boolean 输入上的全部 16 个真值函数：finite_grammar_unsat。扩展到原始四位 oh_i 的检查错误数 0。有限语法无解仅限这个列明的真值函数空间；其他未找到冲突/候选的地方不宣称 UNSAT。没有执行通用 SMT/formal 搜索，因此通用表达能力与求解时间为未知/未使用。

## 4. 闭环与消融

所有方法的初始权限相同。第一候选只消耗一次初始生成；等预算选择使用三条冻结候选；现有反馈与各闭环使用一条初始候选加两次实际修复。闭环每次对训练与已积累 held 场景的 fixed/buggy 重查。义务闭环同时反馈漏报、合法参考误报与非空触发；消融分别使用通用 RTL diff、隐藏误报反馈并移除选择中的误报项、禁止历史细化。equal_information_control 从首次修复起得到相同三拍历史权限。

比较以三次模型调用和 12 个验证单元为预算上限；语法失败会使实际仿真单元更少，token 与墙钟时间也不同。budgets.csv 逐方法报告实际消耗，不能声称等 token/等耗时，更不能将更大观察权限的收益全部归于机制。各方法重用已生成的同一个初始候选，物理模型调用只发生一次，逻辑归账明确标注。

| 方法 | 完整通过父 bug | 已知父 bug | 未知父 bug |
|---|---:|---:|---:|
| equal_budget_select | 0 | 3 | 3 |
| equal_information_control | 1 | 4 | 2 |
| existing_feedback | 1 | 3 | 3 |
| first | 0 | 1 | 5 |
| generic_diff | 1 | 3 | 3 |
| no_fp_check | 1 | 4 | 2 |
| no_observation_refinement | 1 | 3 | 3 |
| obligation_loop | 1 | 4 | 2 |

完整通过要求全部已执行隐藏场景无合法参考误报、无目标漏报、至少一次触发且确有目标违例。未知不计成功或失败。此表为有限样本描述，不是统计显著改善结论。逐父结果与义务覆盖见 parent_results.csv；格式错误/无可执行属性保留未知。

## 5. 独立回归与限制

生成/选择/修复完成后冻结 assertion，随后加载此前未提供给模型的连续输入、背压/停顿、复位打断、中断测试/清除、0/最大值等场景。Depth=0 FIFO 的 DataWidth=4、filter 的 CntWidth=3（阈值5）实际重新编译并执行；不把 FIFO 专用适配器声称为其他 Depth 的测试。等价 RTL 内部重命名/无效线声明单列；onehot StrictCheck=0 是源模块文档明确允许的配置，实际改变 en_i=1、oh_i=0 时的错误输出，并重新构建运行。spill invalid-data=0xA5 只作为合法性尚未确定的探索控制：原始规格没有独立确认 invalid 数据是否可见，因此不把它当作已证实的合法变体，spill 完整合约结果全部记为未知。冻结的 validity-gated 义务解释保留作条件分析，不能据此主张完整保护。

统计流水线在连续不同长度事件上，当前 fixed RTL 的长度寄存器会覆盖前一事件。独立义务检查可能判定 fixed 本身违约；对应报警不是误报。中断原始一句话规格与 FlopOutput=1 的采样时刻存在歧义，此实验明确使用寄存器后一拍的屏蔽义务，不能混同旧 same-cycle 标签。

六个父 bug 是按可检查义务和代表机制选择的小集合，未扩展为完整仓库总体。无可追溯历史修复样本。没有 JasperGold 形式证明，没有完整参数空间覆盖，没有把时序样本当独立 bug。工程控制只用于流程验证、受控语法空间或观察分析。

## 运行规模与复现

当前重新编译运行记录 1072，状态 {"ok": 728, "unsupported_syntax": 344}；候选观察 1688。CPU 模型调用 91，状态 {"generated": 64, "unsupported_syntax": 27}。模型墙钟累计 2024.45s，编译+仿真累计 57.79s；这不是形式求解耗时。

最简抽查（仓库根目录，使用现有 WSL 虚拟环境）：

```powershell
wsl -d Ubuntu -- bash -lc 'source /mnt/d/AssertionForge-main1/.venv-pilot/bin/activate && python /mnt/d/AssertionForge-main1/scripts/run_repair_contract.py audit'
```

每个 runs/... 目录的 reproduce.sh 可直接重编译并仿真该原始输入与 checker；例如：

```powershell
wsl -d Ubuntu -- sh /mnt/d/AssertionForge-main1/deliverables/repair_contract_20261009/runs/e12/held_24/spill/correct/reproduce.sh
```

全流程 action 顺序：pilot → freeze → model-pool → experiments → methods → report → audit；脚本对已完成结果使用缓存，逐运行 reproduce.sh 才是强制实际重跑。GPU 环境故障恢复命令与配置见 recover_contract_model.py / runtime_amendment.json。最终补充表由 `python scripts/finish_repair_contract.py` 从运行记录生成。

audit.json 是亲自执行复现命令、checker 哈希、fail-hit 重算的一致性结果；legacy_checker_crosscheck.json 是独立 AST 逐周期交叉核验。artifact_manifest.json 给出最终主要证据 SHA256。

## 审计补充

观察细化按预定协议在第二轮开放 p1/p2/p3 端口历史；未实现自动可观察性求解器。相同信息对照从第一轮起拥有相同权限。因此只能讨论这套已执行协议，不能把结果泛化为任意义务驱动修复器。

义务覆盖是独立义务违例采样点与 assertion 报警的对应率，不能据此证明属性在未测试空间中逻辑蕴含完整契约。obligation_coverage.json 按义务分量给出检查、违反和报警周期；controlled_partial_coverage.json 则使用隔离义务的受控变异：统计案例 slot 06/07 均漏检后续有效脉冲缺失和长度破坏。

第一轮方法运行因缺少具体编译诊断而中止，原始调用、checker 和日志保存在 protocol_v1_missing_compile_feedback，并提供 reproduce_archived.sh。修正后的整轮比较重新从原冻结池执行，归账独立。failure_ledger.json 列出工具失败、过程修复前尝试及中断调用，均不作为成功/失败性能样本。

metrics.json 提供按父 bug 聚类的 95% bootstrap 区间（2000 次）；paired_statistics.json 只对双方均已知的父 bug 交集计算精确 McNemar。不同方法的已知集合可能不同，不能直接以各自分母的成功率声称优劣。少量且目的性选择的父 bug 不支持总体外推。

没有调用 Claude Code；所有命令由本轮脚本实际执行并核查。没有下载新模型或依赖。

候选装载器曾跳过统计案例 delay=2 的不支持输出；该轮归档于 protocol_v2_skipped_unsupported_slot。修正后第一候选严格指原始 slot 0，语法不支持仍占据其位置。受影响的统计案例按相同预算重新生成修复，其他父案例保留。全部物理调用（包括失败、被替代协议与中断）的已知耗时和未知 token 单列于 all_physical_model_costs.json。

FIFO 固定输入计划末尾若撤销了仍在停顿中的项，会在 input_legality_audit.json 标出并插入一次合法接收后重跑；原计划与错误运行归档保留，训练输入未修改。FIFO 合法性范围明确是本案例的 Depth=0 兼容契约，不能套用上游通用 Depth>0 的 ASSERT_INIT / full-write 约束后仍声称适配等价。

独立 AST 核验发现旧过程 checker 将多位 antecedent 直接赋给 1 位 ant_d，导致只取最低位。新 checker 改用显式非零布尔化，并重新执行全部可执行记录。旧 checker 与对应日志保留在 checker_lowering_v1；lowering_replay_audit.json 检查所有训练反馈是否不变，只有不变才保留已冻结模型选择。旧 FP/TP 签名仍按历史原值保存，不能用本次语义修正覆盖历史。

逐方法 budgets.csv 记录方法决策时实际验证耗时；对应原始结果若因 checker 修复重放而归档，可在 checker_lowering_v1 的同相对路径查找。最终结果引用修正后的实际 checker。全部物理编译/仿真消耗（含修复流程、重放和被替代协议）见 all_physical_validation_costs.json，不能把这些排除在研究实际总成本之外。

<!-- FINAL_SEAL -->

机制归因核对：六个修复/消融/等信息臂完整通过的父案例均只有 onehot；义务闭环没有取得其他臂未取得的完整通过。onehot 的首候选/选择基线因语法不支持为未知，修复后的可执行性提升不能归因于义务约束的独有效果。filter 的实际观察冲突在 3 拍历史、stat 在 2 拍、spill/中断在 1 拍时于本次有限轨迹集合中消失；这也不等于模型找到了合格断言。

最终人工驱动抽查完成：audit.json 中 2736 项一致性检查全部通过；独立 Python AST 与原始 slot 监视器的 704 个交叉核验全部吻合。重放 onehot、filter、FIFO、spill 四个代表命令，重新编译及逐周期日志与记录一致。onehot 合法参数变体确实产生不同错误输出，见 legal_variant_checks.json。

最终交付入口：summary.json（规模/状态）、candidate_results.csv（逐候选运行）、parent_results.csv（父 bug 验收）、budgets.csv（实际预算）、all_physical_model_costs.json（包括失败尝试的实际消耗）、REPORT.md（范围与解释）。
