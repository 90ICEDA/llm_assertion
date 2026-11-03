# AssertionForge 修复保护实验：修正协议补跑

本报告从保存的请求、checker 结果、独立义务和预算记录重新生成。原封存目录保留。

## 设置与权限

冻结 6 个既有人工变异父 bug、8 个方法臂。模型为原 digest 的 Qwen2.5 coder 7B，CPU、seed=20261009、temperature=0.2、192 输出 token。复用 12 个通过权限核查的初始生成槽；spill/中断规格描述修订后重新生成 6 槽。所有修复均为新的二消息请求，无工具、文件、历史对话；原污染候选不参与。
独立验收器可读完整波形和规格；模型只获得白名单接口字段、接口规格及允许的反馈。原始 compiler 日志、RTL、注释和 debug 波形不进入模型请求。实际请求审计见 permission_audit.json。
run_results 的 status 表示工具执行状态；旧执行器 candidate 内的逐周期统计只对应主参考解释。多解释下的语义验收应读取 obligation_acceptance、conditional_results 和 parent_results，不能把仿真 ok 当作合约成功。本次未调用 Claude Code。
协议 2.1 的唯一执行前澄清：合法负控制不强求目标 antecedent 触发；基础 delay=1 已有一位历史，因此细化搜索保守地从完整一拍端口历史开始。修订发生在首次新模型请求之前，旧冻结快照保留。

## 实际规模

新物理模型调用 78 次，状态 {'generated': 53, 'unsupported_syntax': 25}；运行记录 731，状态 {'ok': 452, 'unsupported_syntax': 279}。新模型请求累计 989.81s；编译/仿真累计 40.57s。这些不是形式求解时间。

## 方法比较（父 bug；未知排除在成功率分母之外）

| 方法 | 通过 | 已知 | 未知 | 编译 | 仿真 | 输入 token | 输出 token |
|---|---:|---:|---:|---:|---:|---:|---:|
| first | 0 | 1 | 5 | 24 | 12 | 1534 | 298 |
| equal_budget_select | 0 | 3 | 3 | 72 | 40 | 4602 | 832 |
| existing_feedback | 0 | 2 | 4 | 72 | 44 | 5566 | 914 |
| obligation_loop | 0 | 2 | 4 | 72 | 44 | 9350 | 940 |
| generic_diff | 0 | 2 | 4 | 72 | 44 | 8960 | 866 |
| no_fp_check | 0 | 2 | 4 | 36 | 20 | 8284 | 944 |
| no_observation_refinement | 0 | 2 | 4 | 72 | 44 | 9526 | 940 |
| equal_information_control | 0 | 2 | 4 | 72 | 44 | 9472 | 1040 |

成功仅指预封存有限场景/控制集合内的修复目标保护；不是全状态空间证明。每个父 bug 只计一次，规格未决、语法不支持、未激活义务或缺少必要见证都不能计完整通过。不同方法已知父集合可能不同，不能直接比较各自分母的成功率。多种失败标记保留。

## 预算与消融

预算主轴为真实 compiler 调用，另报真实仿真、输入/输出 token、耗时、共享池成本和缓存。resource_matched_comparisons 给出所有臂都有输出的精确实际编译数检查点；token/仿真以共同额度取已完成输出，同时列实际消耗和余量。无公共正仿真检查点时保留不可比较；没有用无效调用或等待填满预算。相同编译数不等于相同语义验证量，也不等于 token/时间相等。
generic-diff 只改反馈为允许端口上的 RTL 执行差异；接受规则和候选更新与义务闭环相同。no_fp 在方法侧不执行 fixed 验证或产生 FP 反馈；最终验收仍执行。no_observation 只关闭细化。额外历史由已有漏报和严格训练冲突触发，等信息臂从首次修复获得义务臂实际授权的历史深度。原始 refinement 证据和授权时点已保存。

## 观察冲突及旧签名

原 20 个见证已逐一裁定，所有列明解释下严格保留 8 个；其余降级或列解释条件。新增 filter 控制枚举 128 条七位输入序列，实际运行两种 RTL。完整允许历史相同且严格标签相反的默认端口冲突数为 0，结论仅限检查集合。各有限历史深度的冲突、完整两侧输入/历史、pending 处理及细化成本见 observations/。输入-only 与 onehot Boolean 抽象仍单列控制；只有原列明的 16 个真值函数空间可称有限范围无解。
第 1 组复用未改变的原始 RTL/checker 波形，在修订义务的各解释下重裁同签名对；slot 06/07 和原 FP/TP 签名保留，slot 08 不进入自然候选结论。不同报警次数只标执行差异。第 2 组原 12 个窗口比较、0 排名变化保留：该执行层结论不受规格解释变化影响。

## 回归和规格边界

最终断言与训练 checker 模板先冻结，之后才读取新的预封存 hidden 输入。最终输出及资源检查点输出使用同一独立验收集合；相同表达式可复用实际 checker 结果，映射和缓存单列。连续事务、FIFO 停顿、复位取消、IRQ 清除/测试、边界值、参数重编译、onehot StrictCheck 合法行为变体、等价结构改写均单列。隔离变异只用于对应父 bug 的义务验收，不增加父样本数。
spill 的 invalid payload 可见性与中断同拍/寄存器后采样仍无法由现有文字唯一裁定，两种解释均有结果，父级保持规格未决。FIFO 仅限案例明确的 Depth=0 接口，不能宣称适配器与完整上游 FIFO 全功能等价。统计流水线 fixed 在连续不同长度下可能违反独立规格，不能把这些合法目标报警误标 FP。没有可追溯历史修复提交；6 例均为已有人工变异。

补充工程控制在同一新输入上验证 onehot/FIFO 的检测能力及 StrictCheck 合法行为变化，单列 calibration_results，不进入任何模型方法的成功统计。所有方法本轮完整通过数为零；onehot 输出仍含不支持的 popcount，stat 多数输出仍使用不支持的两拍 delay，不能把语法未知改判为语义失败。FIFO 输出在 pop=1 分支缺少保护；filter 即使获得三拍历史仍存在误报或漏报。没有证据支持义务闭环独有收益。
阶段总墙钟见 phase_wall_times（日志时间分辨率 1 秒）；逐方法另给实际产物时间区间，未冒充独立仪表测得的精确方法总时间。Ollama 未提供完整服务端 prompt 缓存统计，该项明确未知；请求/响应原始 eval token 与 duration 均保留。额外观察成本是授权位数及实际使用的历史名字，不是综合后的面积测量。

## 复现

```powershell
wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/contract_v2_report.py
wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/contract_v2_audit.py
```

重新生成汇总只读取保存的原始数据；audit 在独立目录实际重编译复现代表结果与观察冲突，不调用模型。每个 runs 目录另有 reproduce.sh。完整执行顺序：run_contract_v2.py freeze → pool → methods；contract_v2_observations.py；contract_v2_hidden.py；contract_v2_calibration.py；contract_v2_close_windows.py；contract_v2_report.py；contract_v2_audit.py。已有完成模型请求被缓存，不会冒充新调用。

### 收尾窗口修订

中断原输入末尾持续 enable=0，每拍都产生下一拍待检义务。审计后对 7 个实际验收运行追加两拍 enable=1 的合法收尾，并重新编译仿真；原有输入前缀逐样本不变，原运行完整归档于 window_closure_archive。新尾段属于记录在案的后续 testbench 窗口修复，不能称作首次协议预封存内容。没有修改候选、模型调用、训练证据或通过规则；两种规格解释仍分别报告，中断父级仍是规格未决。

### 独立核验

一致性检查 3067 项，全部通过=True；独立表达式核对 {'matched': 449, 'audit_grammar_unsupported': 3}；严格观察见证重核 32 对。四次独立重编译复现覆盖目标检测、合法参考误报和冲突双方。工程 onehot 控制使用算术/位运算，超出本次独立 Boolean 解释器的子集，其三条记录明确标作 audit_grammar_unsupported，并未据此宣称所有表达式已独立解释。
审计器曾因重复目录扫描中止一次，并在四次重放后的结果写出阶段遇到漏导入 stamp 的 NameError；已修复并完整重跑。过程证据见 audit_interruption.json、audit_serialization_failure.json 和 audit_attempt_before_stamp_fix。前次重放耗时缺失保留未知，不记为零。
