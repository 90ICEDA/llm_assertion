# RTL/SVA 本轮真实实验汇总（2026-10-18）

**本轮取得新模型自动细化的实际局部成功，但完整五项义务保护仍未完成。** r05新生成初始断言，随后新模型提出的排空与背压互补断言通过开发原生执行和历史保护验收；冻结后独立测试表明背压性质仍漏报。复位/非请求输出修改未通过，拒绝版本保留。

真实主设计为 axis_fifo，故障是显式人工输出边界变异。新增背压变异不改变接口规范，但不是历史缺陷发现。仿真有限证据不构成形式证明，历史保护保持不构成全局防退化。

## 验收矩阵

| 要求 | 状态 | 证据与限制 |
|---|---|---|
| 真实模型生成并原生执行 | 已验证 | r05新初始生成与原生资格检查通过；完整远程响应字节与模型表达式留存。 |
| 独立契约判定有效漏报 | 已验证于人工故障模型 | 固定开发输入的两参数配对原生执行，独立接受事务队列确认drop、reset_residue、stall_glitch缺口。 |
| 自动细化与历史防退化 | 局部已验证 | r05排空与背压两条新模型编辑开发验收接受，全部历史回放；复位两次及r06一次拒绝。 |
| 复杂FIFO时序 | 已执行 | 开发depth2/pipeline0与depth5/pipeline1，独立depth4/pipeline2；连续握手、重叠、背压、复位与多周期响应。 |
| 冻结后独立验证 | 已执行且保留失败 | r05、r06两批新输入。背压独立仍漏报；复位/非请求输出未补齐；r05保留unknown。 |
| 完整五项功能义务保护 | 未完成 | 不能把三个有检出标签当作完整规范证明，剩余漏报与unknown明确保留。 |
| 四组消融与多种子对比 | 本轮未新增 | 初始/最终冻结回放是候选比较，不是四组消融；不同模型的失败尝试不构成公平机制对比。 |
| 真实历史父Bug闭环 | 未完成 | 人工输出边界故障不能计原始历史FIFO或stat成功。 |

## 六次实际运行（失败全部保留）

| 运行 | 终态 | 模型 | 真模型调用 | 输入/输出 tokens | 原生编译/执行 | 新接受编辑 |
|---|---|---|---:|---:|---:|---:|
| research20_closed_loop_20261018_r01 | development_partial | qwen2.5-coder:7b-instruct | 1 | 8731/116 | 5/105 | 0 |
| research20_closed_loop_20261018_r02 | development_partial | qwen2.5-coder:7b-instruct | 7 | 73507/925 | 5/129 | 0 |
| research20_closed_loop_20261018_r03 | initial_unqualified | qwen2.5-coder:7b-instruct | 2 | 18678/208 | 2/6 | 0 |
| research20_closed_loop_20261018_r04 | initial_unqualified | qwen/qwen-2.5-72b-instruct | 2 | 17536/272 | 0/0 | 0 |
| research20_closed_loop_20261018_r05 | development_partial | qwen/qwen-2.5-72b-instruct | 5 | 52113/533 | 9/177 | 2 |
| research20_closed_loop_20261018_r06 | development_partial | qwen/qwen-2.5-72b-instruct | 1 | 11109/177 | 4/126 | 0 |

r01初始成功但六次细化在分词预检阶段被拒绝，没有提交模型；r02真实局部模型调用的编辑全部拒绝；r03两次初始性质原生资格失败；r04远程两次响应被性质接口拒绝；r05远程五次调用取得初始与两条新编辑接受；r06复用r05冻结集合，仅新增一次复位修改调用，仍被拒绝，未新增接受。

r05与r06的初始含义不同：r05从新生成单义务候选开始，r06从r05已接受集合开始。复用不算新生成，r06独立候选比较相同集合也不能算新改善。

r05初始生成任务明确只要求 `order_payload`，属于受控局部候选；其他义务在后续步骤补充。因此初始/最终改善不能证明优于“一次性依据全部规格生成完整断言集合”，也不是公平机制优越性比较。

## 两条真实模型修改轨迹

r05真实初始断言：
```systemverilog
mvalid && mready && ref_count > 0 |-> mdata == ref_expected
```

### drain_no_loss：core/v0

模型实际理由：Ensures that at a fair-drain checkpoint, if there are outstanding accepted inputs, the last output must match the oldest outstanding input. This complements the existing property by focusing on the condition where the drain is due and there are outstanding inputs.

模型新增/修改的性质原文：
```systemverilog
drain_due && ref_count > 0 |-> $past(mvalid && mready && ref_count > 0) && mdata == ref_expected
```

开发回放：检出 7→9，漏报 8→6，误报 0，unknown 0。原生历史验收接受；表达式原样组装核验 True。

证据是已接受尾部事务在周期111的有限公平排空检查仍未完成，正确对照已响应。接受只说明当前证据被检出；模型表达式并不等同于普遍的 `ref_count==0` 规格，不能从几个样本推断逻辑等价。

### stall_stability：core/v3

模型实际理由：Ensures that the output data (mdata) remains stable during backpressure (mready is low) across consecutive cycles, as required by the stall_stability obligation.

模型新增/修改的性质原文：
```systemverilog
mvalid && !mready && $past(mvalid && !mready) |-> mdata == $past(mdata)
```

开发回放：检出 9→11，漏报 6→4，误报 0，unknown 0。原生历史验收接受；表达式原样组装核验 True。

人工背压故障在开发周期6/7改变未被接受输出的数据；请求实际周期3已接受，正确响应周期10。新增性质检查连续两拍仍受背压时的数据保持，但没有完整覆盖valid保持，也没有覆盖解除背压当拍。独立测试确实保留了漏报，不能称这条完整链成功。

### r06最后一次真实修改仍被拒绝

r06从r05已接受集合出发，仅尝试尚未解决的复位/非请求输出义务；不是重新生成初始候选。

实际模型提案：
```systemverilog
mvalid && mready && ref_count == 0 |-> mdata == 0
rst && $past(mvalid) && $past(mready) && $past(ref_count) > 0 |-> mdata == 0
```
拒绝原因：[{"kind": "model_or_interface_failure"}]
该提案因 `interface_unknown:rst` 未进入原生执行；本次模型调用及原已接受冻结集合的开发/独立回放计入成本。冻结集合保留上一次已接受版本。

## 冻结后的独立结果

两批独立结果在所有模型工作结束后才被读取。没有据此再改候选。表中“检出/漏报/误报/unknown/触发”为去重后的义务记录，不是独立Bug数量。

| 运行 | 冻结候选 | 义务 | 目标违例分母 | 正确控制行 | 检出/漏报/误报/unknown/触发 |
|---|---|---|---:|---:|---|
| research20_closed_loop_20261018_r05 | core | order_payload | 26 | 538 | 26 / 0 / 0 / 0 / 557 |
| research20_closed_loop_20261018_r05 | core | drain_no_loss | 1 | 538 | 1 / 0 / 0 / 0 / 1 |
| research20_closed_loop_20261018_r05 | core | no_unsolicited_output | 4 | 538 | 0 / 4 / 0 / 0 / 0 |
| research20_closed_loop_20261018_r05 | core | stall_stability | 7 | 538 | 5 / 2 / 0 / 0 / 204 |
| research20_closed_loop_20261018_r05 | core | reset_cancellation | 4 | 538 | 0 / 3 / 0 / 1 / 0 |
| research20_closed_loop_20261018_r05 | core | 后续归因 unknown（另存） | — | — | 453 |
| research20_closed_loop_20261018_r05 | core | 原始/去重义务记录 | 19307/8547 | — | 漏报采样事件 6 |
| research20_closed_loop_20261018_r05 | initial | order_payload | 26 | 538 | 26 / 0 / 0 / 0 / 557 |
| research20_closed_loop_20261018_r05 | initial | drain_no_loss | 1 | 538 | 0 / 1 / 0 / 0 / 0 |
| research20_closed_loop_20261018_r05 | initial | no_unsolicited_output | 4 | 538 | 0 / 4 / 0 / 0 / 0 |
| research20_closed_loop_20261018_r05 | initial | stall_stability | 7 | 538 | 0 / 7 / 0 / 0 / 0 |
| research20_closed_loop_20261018_r05 | initial | reset_cancellation | 4 | 538 | 0 / 3 / 0 / 1 / 0 |
| research20_closed_loop_20261018_r05 | initial | 后续归因 unknown（另存） | — | — | 453 |
| research20_closed_loop_20261018_r05 | initial | 原始/去重义务记录 | 19307/8547 | — | 漏报采样事件 12 |
| research20_closed_loop_20261018_r06 | core | order_payload | 18 | 541 | 18 / 0 / 0 / 0 / 545 |
| research20_closed_loop_20261018_r06 | core | drain_no_loss | 1 | 541 | 1 / 0 / 0 / 0 / 1 |
| research20_closed_loop_20261018_r06 | core | no_unsolicited_output | 2 | 541 | 0 / 2 / 0 / 0 / 0 |
| research20_closed_loop_20261018_r06 | core | stall_stability | 4 | 541 | 3 / 1 / 0 / 0 / 178 |
| research20_closed_loop_20261018_r06 | core | reset_cancellation | 2 | 541 | 0 / 2 / 0 / 0 / 0 |
| research20_closed_loop_20261018_r06 | core | 后续归因 unknown（另存） | — | — | 474 |
| research20_closed_loop_20261018_r06 | core | 原始/去重义务记录 | 18882/8062 | — | 漏报采样事件 3 |
| research20_closed_loop_20261018_r06 | initial | order_payload | 18 | 541 | 18 / 0 / 0 / 0 / 545 |
| research20_closed_loop_20261018_r06 | initial | drain_no_loss | 1 | 541 | 1 / 0 / 0 / 0 / 1 |
| research20_closed_loop_20261018_r06 | initial | no_unsolicited_output | 2 | 541 | 0 / 2 / 0 / 0 / 0 |
| research20_closed_loop_20261018_r06 | initial | stall_stability | 4 | 541 | 3 / 1 / 0 / 0 / 178 |
| research20_closed_loop_20261018_r06 | initial | reset_cancellation | 2 | 541 | 0 / 2 / 0 / 0 / 0 |
| research20_closed_loop_20261018_r06 | initial | 后续归因 unknown（另存） | — | — | 474 |
| research20_closed_loop_20261018_r06 | initial | 原始/去重义务记录 | 18882/8062 | — | 漏报采样事件 3 |

背压负例：`research20_closed_loop_20261018_r05`，`test:d4:p2:s1790196238:random:stall_glitch`，周期 84。
上一拍输出受背压，本拍解除背压；已接受模型性质额外要求本拍仍 !mready，因此本拍不检查稳定性。

实际采样：
```json
[
  {
    "cycle": 83,
    "rst": 0,
    "ref_count": 5,
    "ref_expected": 747904516,
    "drain_due": 0,
    "svalid": 0,
    "sready": 1,
    "sdata": 961855636,
    "mvalid": 1,
    "mready": 0,
    "mdata": 747904517
  },
  {
    "cycle": 84,
    "rst": 0,
    "ref_count": 5,
    "ref_expected": 747904516,
    "drain_due": 0,
    "svalid": 1,
    "sready": 1,
    "sdata": 96520468,
    "mvalid": 1,
    "mready": 1,
    "mdata": 747904516
  },
  {
    "cycle": 85,
    "rst": 0,
    "ref_count": 5,
    "ref_expected": 1607029604,
    "drain_due": 0,
    "svalid": 1,
    "sready": 1,
    "sdata": 2896080820,
    "mvalid": 1,
    "mready": 0,
    "mdata": 1607029605
  }
]
```
这是一份测试后诊断记录，没有用于本轮生成或重新挑选冻结候选。

背压负例：`research20_closed_loop_20261018_r06`，`test:d4:p2:s493182668:random:stall_glitch`，周期 32。
上一拍输出受背压，本拍解除背压；已接受模型性质额外要求本拍仍 !mready，因此本拍不检查稳定性。

实际采样：
```json
[
  {
    "cycle": 31,
    "rst": 0,
    "ref_count": 1,
    "ref_expected": 4223083860,
    "drain_due": 0,
    "svalid": 0,
    "sready": 1,
    "sdata": 1720857332,
    "mvalid": 1,
    "mready": 0,
    "mdata": 4223083861
  },
  {
    "cycle": 32,
    "rst": 0,
    "ref_count": 1,
    "ref_expected": 4223083860,
    "drain_due": 0,
    "svalid": 1,
    "sready": 1,
    "sdata": 759474052,
    "mvalid": 1,
    "mready": 1,
    "mdata": 4223083860
  },
  {
    "cycle": 33,
    "rst": 0,
    "ref_count": 1,
    "ref_expected": 759474052,
    "drain_due": 0,
    "svalid": 0,
    "sready": 1,
    "sdata": 1556738420,
    "mvalid": 0,
    "mready": 0,
    "mdata": 2652297556
  }
]
```
这是一份测试后诊断记录，没有用于本轮生成或重新挑选冻结候选。

## 资格检查和实际总成本

| 检查 | 通过 | 原生编译/执行 |
|---|---|---|
| 既有故障模型的九组开发案例原生审计 | True | 2/20 |
| 多个义务标签与原生证据映射资格检查 | True | 1/3 |
| 人工背压故障的合法输入与漏报资格检查 | True | 2/6 |
| 真实反馈投影与上下文压缩检查 | True | 0/0 |
| 远程请求构造及历史真实响应解析；当时没有网络调用 | True | 0/0 |
| 初始接口拒绝反馈保留及直接性质语法检查 | True | 0/0 |

六次运行及资格实验合计：真实模型调用 **18**（本地 10、远程 8）；输入 tokens 已知小计 **181674**，输出 **2231**，用量不可用调用 0。原生编译 **30**、执行 **572**（包含编译smoke 30），形式化调用 **0**。金额不可用。

远程授权8次已使用完。最初被审批拦截的命令未启动，计0请求。失败调用计入，预检拒绝不计模型生成，r06来源历史成本不重复加总；provider usage和归一化tokens不双计。

## 可复现命令与产物

以下为实际执行记录；重新执行必须更换输出目录。资格审计及每次运行的源码、参数、请求响应、日志和波形由对应报告清单索引。

```powershell
wsl -- python3 scripts/research20_loop.py --out deliverables/research20_closed_loop_20261018_r05 --seed 2026101805 --iterations 2 --max-model-calls 6 --stall-fault --direct-property --backend configured-qwen-relay
wsl -- python3 scripts/research20_loop.py --out deliverables/research20_closed_loop_20261018_r06 --seed 2026101806 --iterations 1 --max-model-calls 1 --stall-fault --direct-property --backend configured-qwen-relay --source-core deliverables/research20_closed_loop_20261018_r05 --only-stage reset
wsl -- python3 scripts/research20_campaign_report.py --out deliverables/research20_campaign_20261018_r02
wsl -- python3 scripts/research20_campaign_report.py --out deliverables/research20_campaign_20261018_r01 --verify
```

各运行报告：
- [research20_closed_loop_20261018_r01](../research20_closed_loop_20261018_r01/report/REPORT.md)
- [research20_closed_loop_20261018_r02](../research20_closed_loop_20261018_r02/report/REPORT.md)
- [research20_closed_loop_20261018_r03](../research20_closed_loop_20261018_r03/report/REPORT.md)
- [research20_closed_loop_20261018_r04](../research20_closed_loop_20261018_r04/report/REPORT.md)
- [research20_closed_loop_20261018_r05](../research20_closed_loop_20261018_r05/report/REPORT.md)
- [research20_closed_loop_20261018_r06](../research20_closed_loop_20261018_r06/report/REPORT.md)

## 明确未完成

- 复位取消与非请求输出保护尚未通过严格验收；冻结集合继续保留旧版本。
- 背压数据保持只在部分条件上改善，独立仍漏报；valid保持和解除背压当拍未完整保护。
- r05独立unknown与所有后续归因unknown保留，不排除困难样本来声称全通过。
- 完整五项义务、整个父案例、真实历史缺陷闭环仍未完成；stat与原始FIFO历史问题仍unknown。
- 本轮没有新四组消融、真正候选对分歧比较、多种子公平机制比较或形式化证明。
- 远程调用预算已用完；下一轮改进需要新实验预算并重新准备未见独立数据。已读取的本轮测试若用于修改，须转开发数据。
