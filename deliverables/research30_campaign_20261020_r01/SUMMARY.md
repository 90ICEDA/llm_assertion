# Research30：固定候选后的搜索比较与四组真实消融

本轮按顺序完成四类搜索比较和四组真实模型消融。保留所有失败、平局和后续归因 unknown；没有修改被冻结的候选或事后放宽验收。

搜索比较：同一原生候选对、三个种子、每方法每种子四次查询，每次两候选 × 正确及七类故障，共 16 次原生执行。所有方法最终均发现两类 valid 保持缺口。契约搜索相对普通补测和候选对分歧新增独立缺口为 0；首次发现较普通补测快一条查询的种子有两个。普通差分在一个种子预算内没有发现。

四组真实消融：每组一次 Highway/Qwen 72B 请求，A/C 提示相同，B/D 提示相同。新搜索证据只提供给 B/D。每组终止后冻结，所有组冻结后再执行共同历史审计及同一批新独立输入。

| 组 | 实际处理 | 历史原有检出保留 | 新搜索漏报剩余 | 独立检出/漏报 | 独立误报/当前 unknown |
|---|---|---:|---:|---:|---:|
| A 普通反馈 | 拒绝修改，保留初始 | 214/214 | 2 | 34/8 | 0/0 |
| B 搜索 | 接受修改 | 214/214 | 0 | 42/0 | 0/0 |
| C 防退化 | 拒绝修改，保留初始 | 214/214 | 2 | 34/8 | 0/0 |
| D 搜索＋防退化 | 拒绝修改，保留初始 | 214/214 | 2 | 34/8 | 0/0 |

A 返回两个蕴含运算符，未通过接口约束，没有进入该候选的原生编译；不能称为原生语法错误。B 将 a2 替换为下式，模型表达式未经人工修改：

原 a2：
```systemverilog
mvalid && !mready && $past(mvalid && !mready) |-> mdata == $past(mdata)
```

模型修改后的 a2：
```systemverilog
mvalid && !mready |=> mvalid && mdata == $past(mdata)
```

C、D 均只生成数据保持表达式，未增加 valid 保护。D 的两条新漏报未修复，拒绝有实际依据。C 的拒绝仅来自两条历史触发减少。

对减少触发逐条检查发现，前一拍复位已取消待完成的背压保持义务，独立检查器在该周期没有对应检查。不能把这两条拒绝算作保住了必要检查。对 B 的实际冻结候选执行只读门控复算，也被同一规则拒绝，表明门控存在过度保守问题；该复算不改变任何实验组结果。

相同提示、相同采样配置仍产生了不同模型输出，因此单次 B/D 差异不能完全归因于门控。当前实验证明搜索证据可驱动一次有效修复，尚未证明防退化提高了最终效果或两机制稳定优于基线。

新独立输入 seed 1457709376，共 26 场景。各组后续归因 unknown：

- A：329；历史审计后续归因 unknown 1224。
- B：329；历史审计后续归因 unknown 1224。
- C：329；历史审计后续归因 unknown 1224。
- D：329；历史审计后续归因 unknown 1224。

两个实际修改案例（事务明细与原始 native 行见消融报告 case_examples.json）：

- valid_withdraw_stalled：周期 7 的 valid/ready 为 1/0，下一周期 8 为 0/0，数据仍为 4239894500。当时有 4 个已接受、尚未完成或取消的事务；旧 a4 已触发但只约束数据，漏掉 valid 撤销。B 的新 a2 经原生执行检出；新独立输入中的对应义务结果 `{'detections': 4, 'misses': 0, 'false_positives': 0, 'unknown': 0}`。
- valid_withdraw_release：周期 9 的 valid/ready 为 1/0，下一周期 10 为 0/1，数据仍为 4239894500。当时有 6 个已接受、尚未完成或取消的事务；旧 a4 已触发但只约束数据，漏掉 valid 撤销。B 的新 a2 经原生执行检出；新独立输入中的对应义务结果 `{'detections': 4, 'misses': 0, 'false_positives': 0, 'unknown': 0}`。

本批独立输入的排空义务是否曝光，逐组列出，零曝光不能算验收通过：

- A：`{'detections': 0, 'misses': 0, 'unknown': 0, 'false_positives': 0, 'triggers': 0}`。
- B：`{'detections': 0, 'misses': 0, 'unknown': 0, 'false_positives': 0, 'triggers': 0}`。
- C：`{'detections': 0, 'misses': 0, 'unknown': 0, 'false_positives': 0, 'triggers': 0}`。
- D：`{'detections': 0, 'misses': 0, 'unknown': 0, 'false_positives': 0, 'triggers': 0}`。

原 research28 冻结版本及 research29 的 12/12 排空丢失验收保持原记录；本轮消融使用 research27 作为共同起点，并未替换项目已验收版本。

物理总成本：`{'model_calls': 4, 'prompt_tokens_total': 42850, 'completion_tokens_total': 779, 'usage_unavailable_calls': 0, 'native_compile_calls': 58, 'native_execute_calls': 2966, 'compile_smoke_execute_calls': 58, 'formal_calls': 0}`。完整分阶段成本见 cost.json。B/D 各计逻辑 64 次搜索执行，实际共享采集已计入搜索阶段，不重复相加。金额不可用，形式化查询为 0。

本轮是一种已知真实 FIFO RTL 上的人工边界故障任务，搜索有三个种子，模型消融只有一个种子。不是跨父 Bug 稳定性、形式证明或全局无退化结论。

可复核命令（报告入口只读原实验，不调用模型）：

```powershell
wsl -- python3 scripts/research30_report.py --run deliverables/research30_search_compare_20261020_r01
wsl -- python3 scripts/research30_ablation_report.py --run deliverables/research30_ablation_20261020_r01
wsl -- python3 scripts/research30_campaign_report.py --out deliverables/research30_campaign_20261020_r01
```

实际搜索及消融命令分别保存在原运行 execution.command.json；原目录不可覆盖重跑。新的模型实验需另建输出目录并取得相应调用额度。

完整来源：

- 搜索逐项发现、同预算和去重核验：D:\AssertionForge-main1\deliverables\research30_search_compare_20261020_r01\report\SUMMARY.md
- 四组原始响应、每版断言、决定、历史和独立统计：D:\AssertionForge-main1\deliverables\research30_ablation_20261020_r01\report\SUMMARY.md
- 实际 B 候选的只读门控复算：D:\AssertionForge-main1\deliverables\research30_ablation_20261020_r01\report\counterfactual_gate_on_B.json
- 本目录 results.json：完成状态和仍未建立的结论。
