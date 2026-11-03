# research81：固定预算恢复流程对照结果

实际终态：qualified_no_expansion。最多4次调用，实际2次；无自动扩展。

|里程碑|新增|
|---|---:|
|接受版本（不同哈希）|1|
|完成105历史回放|1|
|新独立验收通过（组）|1|
|两个核心机制增量证据|0|

|组|实际调用|新版本接受|新独立验收|
|---|---:|---|---|
|P|1|False|False|
|D|1|True|True|

D首轮直接生成即通过，未发生本轮拒绝后细化。因此本轮不能证明历史拒绝反馈促成了恢复；若P计划失败，也不能据此断言逐窗口门控一般有害。

P为完整计划后生成；D为直接生成、必要时真实反馈细化一次。两组初始候选、公共开发信息和最终原生标准一致；每组上限2次，但P将一次额度用于计划，D最多有两次性质机会。实际不同响应不是共享提案，不能将结果当成纯门控因果估计。

## 真实修改轨迹

共同初始集合：

```systemverilog
a0: mvalid && mready && ref_count > 0 |-> mdata == ref_expected
a1: drain_due && ref_count > 0 |-> $past(mvalid && mready && ref_count > 0) && mdata == ref_expected
a2: mvalid && !mready && $past(mvalid && !mready) |-> mdata == $past(mdata)
a3: mready && mvalid |-> (ref_count > 0 && mdata == ref_expected)
a4: (mvalid && !mready) |=> mdata == $past(mdata)
```

### P / plan

接受：False。
实际规则执行正确2/11；窗口答案正确9/11。
拒绝原因：[{"kind": "incorrect_rule_binding", "field": "reset_cancellation"}, {"kind": "rule_vs_certificate", "id": "w0"}, {"kind": "window_vs_certificate", "id": "w0"}, {"kind": "rule_vs_window", "id": "w0"}, {"kind": "rule_vs_certificate", "id": "w1"}, {"kind": "rule_vs_window", "id": "w1"}, {"kind": "rule_vs_certificate", "id": "w2"}, {"kind": "window_vs_certificate", "id": "w2"}, {"kind": "rule_vs_window", "id": "w2"}, {"kind": "rule_vs_certificate", "id": "w3"}, {"kind": "rule_vs_window", "id": "w3"}, {"kind": "rule_vs_certificate", "id": "w4"}, {"kind": "rule_vs_window", "id": "w4"}, {"kind": "rule_vs_certificate", "id": "w5"}, {"kind": "rule_vs_window", "id": "w5"}, {"kind": "rule_vs_certificate", "id": "w6"}, {"kind": "rule_vs_window", "id": "w6"}, {"kind": "rule_vs_certificate", "id": "w9"}, {"kind": "rule_vs_window", "id": "w9"}, {"kind": "rule_vs_certificate", "id": "w10"}, {"kind": "rule_vs_window", "id": "w10"}]

### D / generate

接受：True。

实际模型性质（原样组装）：

```systemverilog
a0: mvalid && mready && ref_count > 0 |-> mdata == ref_expected
a1: drain_due && ref_count > 0 |-> $past(mvalid && mready && ref_count > 0) && mdata == ref_expected
a2: mvalid && !mready && $past(mvalid && !mready) |-> mdata == $past(mdata)
a3: mready && mvalid |-> (ref_count > 0 && mdata == ref_expected)
a4: ((mvalid && (!(mready)) && (!(rst)))) |=> ((mvalid && (mdata == $past(mdata))))
```

|阶段|检出|漏报|合法误报|关键unknown|后续归因unknown|
|---|---:|---:|---:|---:|---:|
|windows|12|0|0|0|139|
|public|3|0|0|0|151|
|history|214|0|0|0|1177|

实际接受/拒绝理由：[]

## 冻结后的独立测试

两组终止并冻结后才生成共同新批次；没有根据独立结果改写候选或选择版本。相同候选哈希只物理测量一次，统计点不是独立Bug数。

P冻结哈希：`0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1`。

```json
{
  "metrics": {
    "healthy": true,
    "counts": {
      "rows": 34913,
      "unknown": 0,
      "triggers": 6988,
      "false_positives": 0,
      "detections": 48,
      "misses": 20,
      "count_unit": "obligation-by-sampled-cycle evidence rows, not independent discoveries or transactions",
      "later_attribution_unknown": 556
    },
    "scenarios_total": 56,
    "scenarios_with_first_attributable_target": 50,
    "scenarios_without_first_attributable_target": [
      "independent29:s715060862:d2:p0:legal_three",
      "independent29:s715060862:d2:p0:reset_cancels_tail",
      "independent29:s715060862:d4:p1:legal_three",
      "independent29:s715060862:d4:p1:reset_cancels_tail",
      "independent29:s715060862:d8:p2:legal_three",
      "independent29:s715060862:d8:p2:reset_cancels_tail"
    ],
    "obligations": {
      "order_payload": {
        "detections": 15,
        "misses": 0,
        "unknown": 0,
        "false_positives": 0,
        "triggers": 2007
      },
      "drain_no_loss": {
        "detections": 12,
        "misses": 0,
        "unknown": 0,
        "false_positives": 0,
        "triggers": 12
      },
      "no_unsolicited_output": {
        "detections": 6,
        "misses": 0,
        "unknown": 0,
        "false_positives": 0,
        "triggers": 1998
      },
      "stall_stability": {
        "detections": 9,
        "misses": 20,
        "unknown": 0,
        "false_positives": 0,
        "triggers": 973
      },
      "reset_cancellation": {
        "detections": 6,
        "misses": 0,
        "unknown": 0,
        "false_positives": 0,
        "triggers": 1998
      }
    }
  },
  "all_five_pass_on_first_attributed_evidence": false,
  "distinct_inputs": 48,
  "scenarios": 56,
  "scope": "Finite first-attribution evidence only; subsequent attribution unknowns remain. Not a global proof."
}
```

D冻结哈希：`d26cff98c4196dc916da4642a29d8417f4aec2fb154fe0ba5fb22eece398bc47`。

```json
{
  "metrics": {
    "healthy": true,
    "counts": {
      "rows": 34913,
      "unknown": 0,
      "triggers": 6988,
      "false_positives": 0,
      "detections": 68,
      "misses": 0,
      "count_unit": "obligation-by-sampled-cycle evidence rows, not independent discoveries or transactions",
      "later_attribution_unknown": 556
    },
    "scenarios_total": 56,
    "scenarios_with_first_attributable_target": 50,
    "scenarios_without_first_attributable_target": [
      "independent29:s715060862:d2:p0:legal_three",
      "independent29:s715060862:d2:p0:reset_cancels_tail",
      "independent29:s715060862:d4:p1:legal_three",
      "independent29:s715060862:d4:p1:reset_cancels_tail",
      "independent29:s715060862:d8:p2:legal_three",
      "independent29:s715060862:d8:p2:reset_cancels_tail"
    ],
    "obligations": {
      "order_payload": {
        "detections": 15,
        "misses": 0,
        "unknown": 0,
        "false_positives": 0,
        "triggers": 2007
      },
      "drain_no_loss": {
        "detections": 12,
        "misses": 0,
        "unknown": 0,
        "false_positives": 0,
        "triggers": 12
      },
      "no_unsolicited_output": {
        "detections": 6,
        "misses": 0,
        "unknown": 0,
        "false_positives": 0,
        "triggers": 1998
      },
      "stall_stability": {
        "detections": 29,
        "misses": 0,
        "unknown": 0,
        "false_positives": 0,
        "triggers": 973
      },
      "reset_cancellation": {
        "detections": 6,
        "misses": 0,
        "unknown": 0,
        "false_positives": 0,
        "triggers": 1998
      }
    }
  },
  "all_five_pass_on_first_attributed_evidence": true,
  "distinct_inputs": 48,
  "scenarios": 56,
  "scope": "Finite first-attribution evidence only; subsequent attribution unknowns remain. Not a global proof."
}
```

## 成本与结论范围

```json
{
  "model_calls": 2,
  "prompt_tokens_known_subtotal": 31202,
  "completion_tokens_known_subtotal": 1390,
  "usage_unavailable_calls": 0,
  "prompt_tokens_total": 31202,
  "completion_tokens_total": 1390,
  "model_wall_seconds_known_subtotal": 57.989656571000005,
  "model_wall_seconds_unavailable_calls": 0,
  "model_status": {
    "response_received": 2
  },
  "native_compile_calls": 19,
  "native_execute_calls": 491,
  "compile_smoke_execute_calls": 19,
  "native_compile_wall_seconds": 181.70067236000017,
  "native_execute_wall_seconds": 11.385327930999892,
  "native_commands_failed_or_timed_out": 0,
  "tool_version_query_calls": 19,
  "formal_calls": 0
}
```

准备阶段的13次编译、271次执行另见准备目录cost.json，不混入本次生成策略成本。货币账单不可用。
单种子、一个已观察的开发恢复任务不支持稳定成功率结论。任何通过只适用于有限原生仿真范围；后续归因unknown保留，不是全局无退化或形式化证明。
本轮检验辅助生成流程，未新增契约搜索独有缺口或防退化前瞻性多种子收益证据。不会自动追加同模型调用、第二种子或机制比较。

## 只读复核

```powershell
wsl -- python3 scripts/research81_audit.py --prepared deliverables/research81_prepare_20261025_r01 --run deliverables/research81_real_20261025_r01 --out deliverables/research81_audit_recheck_20261025_r01
wsl -- python3 scripts/research81_result_summary.py --prepared deliverables/research81_prepare_20261025_r01 --run deliverables/research81_real_20261025_r01 --audit deliverables/research81_audit_recheck_20261025_r01
```
