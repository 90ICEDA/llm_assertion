## UB-001 — 40-parent selection 与 60/46 集合完全不相交

- 首次观察：2026-08-29，样本流转审计。
- 原始直觉：四个数字可能代表 `60 → 46 → 40 → 30` 的连续筛选。
- 实际结果：selection40 与 initial60、accepted46 的 parent ID 交集均为 0；latest30 分别只与它们部分重叠。
- 影响：任何线性 funnel 图都会错误地为 40 和 30 中的缺席 parent 虚构“排除原因”。
- 最终原因：40-parent asset 来自 scale120 canonical-parent selection 分支；60/46 来自 cases 451–510 acceptance 分支；30-parent Pilot 又混合 scale120 与两代 scale210 admission pool。
- 最终状态：已解释，保留为实验资产命名/叙述风险。

## UB-002 — 普通 Windows 遍历报告缺少 530 个 probe verdict

- 首次观察：2026-08-29，第一版完整性审计。
- 原始结果：普通 `Path.glob` 只读到 14,830/15,360 个 `result.json`，表面上缺少 case506 的 512 个和 case465 的 18 个。
- 当时影响：初版报告将 530 个单元记为 raw grid 缺失。
- 后续核查：PowerShell 能看到 case506 文件；使用 Windows `\\?\` 长路径逐个读取后，case506 的 512 个全部存在。
- 最终原因：case506 的深层路径超过普通 Windows/Python glob 的可靠路径长度，属于读取脚本问题，不是 formal 缺失。
- 最终状态：误判已纠正；审计脚本改为长路径安全读取。原始误判保留在此。

## UB-003 — case465 确有 18 个 verdict 缺失

- 首次观察：2026-08-29，长路径核查后。
- 实际缺失：probe_001 缺 slot 07–08；probe_037、probe_061 各缺全部 8 candidates。
- 伴随现象：同一 parent 已有缓存中存在 12 个 timeout stage。
- 处置：按最小范围通过 WSL/Icarus 补跑 18 个单元，没有重跑其余 15,342 个。
- 最终结果：15,360/15,360 verdict 可读；缓存 fp/tp 与 raw fail-hit 重算一致。
- 最终状态：已修复；保留为 timeout/中断导致的缓存不完整案例。

## UB-004 — 第一次 formal repair 已生成文件但没有写 completion log

- 首次观察：2026-08-29，18 单元补跑。
- 现象：第一次 WSL 调用没有返回脚本 JSON completion；随后检查发现缺失 result 文件已经全部生成，但 `formal_repair_log.json` 尚不存在。
- 后续核查：第二次调用按“目标已存在则跳过”运行，确认 18/18 均存在，并补写验证日志。
- 可能原因：外层命令会话在脚本写最终汇总前中断或未回传 stdout，而逐单元 result 已在此前原子步骤写入。
- 最终状态：结果文件与 verdict 已逐项验证；无法从现有证据进一步确定外层会话中断点，标记为 tool/session anomaly。

## UB-005 — 低 disagreement score 优先更早遇到全部 timeout

- 首次观察：2026-08-29，probe 顺序敏感性重放。
- 结果：low→high 在 budget 8 前已覆盖全部 48 个 timeout stage；high→low 在 budget≤32 没有覆盖 timeout；random 的 timeout 暴露随 seed/budget 变化。
- 影响：budget 内 resolution 差异同时包含排序信息和 timeout 暴露，不能纯粹解释为 disagreement score 的因果效果。
- 完整 pool 核查：64 probes 全部使用后，所有策略和 seed 的最终 resolved set 相同，均为 546/840。
- 最终状态：未发现最终集合不一致；timeout 是预算内比较的明确混杂因素。

## UB-006 — 增加 probe 后 dominance 数量可能下降

- 首次观察：2026-08-29，budget 8/16/32 关系统计。
- 表面矛盾：resolved pair 数随 probe 增加而单调上升，但 dominance count 并不单调。
- 最终原因：新增 probe 可使原先嵌套的 FP/TP set 变成交叉集合，从 dominance 转为 crossing incomparable；只有 resolved/equal 的边界具有单调性。
- 最终状态：统计逻辑正确；报告中明确关系类别不是累积事件数。

## UB-007 — “FP/TP 签名完全相同”中 34/60 仍有可重放行为差异

- 首次观察：2026-08-29，人工可分性盲审。
- 原始标签：60 对在完整当前 pool 上具有相同的布尔 FP/TP set。
- 盲审结果：其中 34 对在合法、可达、已编译的同一 probe 下具有不同 fail-hit 行为；20/20 隐藏 control 也全部成功。
- 最终原因：当前签名把 fail count 压缩为 `fail_hits > 0` 的布尔 FP/TP，丢失了失败次数和行为强度信息。
- 影响：不能把 equal FP/TP signature 表述为“行为完全相同”；应称“二值 FP/TP set 相同”。
- 最终状态：已解释，是表示/统计口径不足，不是 raw verdict 不一致。

## UB-008 — 不同指标出现相同 0% 或 100%

- 首次观察：2026-08-29，指标来源表。
- 示例：unseen-family Non-vacuity 与 Compile 都是 25/25；多个 SCS@1 与 Family Recall 同为 0%，但分母分别是 query 和 bug family。
- 影响：只比较百分比字符串会把不同统计单位误判为重复指标。
- 最终原因：数值碰巧相同，统计单位和公式不同。
- 最终状态：已在 `metric_sources.csv` 中拆分 numerator、denominator 和 statistical_unit。

## UB-009 — selection/variant 资产容易把同一 parent 多次计数

- 首次观察：2026-08-29，parent manifest 审计。
- 现象：selection 原始表含 variant-level case rows；只有 `case_id == parent_bug_id` 的 canonical rows 构成 40-parent primary scope。
- 风险：直接按 case row 统计会把同一 parent 的多个 variant 当作独立样本。
- 最终状态：统一脚本显式使用 parent_bug_id，并保留 variant-level 表只作 sensitivity view。

## UB-010 — 统一归档 inventory 首次构建在长路径 `stat` 阶段失败

- 首次观察：2026-08-29，统一交付构建。
- 现象：tar 写入使用长路径后可以开始归档，但 inventory 仍调用普通 `Path.stat()`；遇到 case457 深层 checker 路径时抛出 `FileNotFoundError`，留下不完整 archive。
- 处置：保留 `build_error.log` 作为原始失败证据；归档器的读取、stat 和 hash 全部改为 `\\?\` 长路径安全调用，并从头覆盖不完整 archive。
- 最终结果：完整 archive 含 37,225 个文件，解压前 9,010,514 bytes、解压后 143,839,654 bytes；archive 与 inventory 均生成 SHA-256。
- 最终状态：已修复并验证；属于与 UB-002 同类但发生在归档 inventory 阶段的脚本问题。
