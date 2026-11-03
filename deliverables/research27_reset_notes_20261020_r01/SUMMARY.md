# 复位后无请求输出保护：本轮结果

真实模型 `qwen/qwen-2.5-72b-instruct`（`configured-qwen-relay`）细化接受次数：1；运行状态：`development_resolved`。
其余四条断言原文保留：True。

旧 a3：
```systemverilog
(mvalid && mready) |-> $past(ref_count > 0)
```

最终 a3：
```systemverilog
mready && mvalid |-> (ref_count > 0 && mdata == ref_expected)
```

| 数据 | 义务 | 检出 | 漏报 | unknown | 误报 | 触发行 |
|---|---|---:|---:|---:|---:|---:|
| development_before | no_unsolicited_output | 26 | 8 | 0 | 0 | 4668 |
| development_before | reset_cancellation | 28 | 8 | 3 | 0 | 4670 |
| development_after | no_unsolicited_output | 34 | 0 | 0 | 0 | 4668 |
| development_after | reset_cancellation | 39 | 0 | 0 | 0 | 4673 |
| independent_initial | no_unsolicited_output | 4 | 2 | 0 | 0 | 675 |
| independent_initial | reset_cancellation | 4 | 2 | 1 | 0 | 675 |
| independent_core | no_unsolicited_output | 6 | 0 | 0 | 0 | 675 |
| independent_core | reset_cancellation | 7 | 0 | 0 | 0 | 676 |

上述分母为“义务—采样行”，同一事务可能同时违反两项义务，不是两个独立 Bug。
105 个开发场景包含 90 个已公开旧测试；新独立测试在最终冻结后生成。

另保留开发集 1177 条、独立集 160 条后续违例归因 unknown；没有计为通过或已确认检出。

## 开发证据轨迹

ref_count 为 0 时 ref_expected 没有有效队首语义；此时应由事务不存在性拒绝输出，不以该残留数值作为合法性的依据。

- `promoted26:independent21:s303212944:d8:p2:fresh_random:reset_residue`，cycle 19，ref_count=0，mvalid=1，mready=1，mdata=3921049764，ref_expected=3074676196。修改前：triggered_without_confirmed_detection，归因 confirmed；修改后：归因 confirmed，原生断言记录 `[{"id": "a3", "trigger": true, "failed": true, "causal_detection": true}]`。
- `promoted26:independent21:s2083465286:d8:p2:fresh_random:reset_residue`，cycle 55，ref_count=4，mvalid=1，mready=1，mdata=728067716，ref_expected=907173892。修改前：triggered_without_confirmed_detection，归因 unknown；修改后：归因 confirmed，原生断言记录 `[{"id": "a3", "trigger": true, "failed": true, "causal_detection": true}]`。

## 产物与限制

- [完整原生日志、修改及独立回放报告](../research27_closed_loop_20261020_r06/report/REPORT.md)
- [实际执行命令](../research27_closed_loop_20261020_r06/execution.command.json)
- [冻结 SVA](../research27_closed_loop_20261020_r06/core/frozen_candidate.sva)
- [全部失败尝试与本轮总成本](../research27_reset_campaign_20261020_r01/SUMMARY.md)
- [机器可读结果](RESULTS.json)

本轮只验收有限样本中的复位相关保护。完整五义务、valid 背压保持、原始历史缺陷闭环仍不能据此宣称完成。仿真通过不等于形式化证明；历史回放通过不等于全局无退化。

实际成本：`{"model_calls": 2, "prompt_tokens_known_subtotal": 21535, "completion_tokens_known_subtotal": 307, "usage_unavailable_calls": 0, "prompt_tokens_total": 21535, "completion_tokens_total": 307, "model_wall_seconds_known_subtotal": 21.384078257999988, "model_wall_seconds_unavailable_calls": 0, "model_status": {"response_received": 2}, "native_compile_calls": 16, "native_execute_calls": 718, "compile_smoke_execute_calls": 16, "native_compile_wall_seconds": 152.41355196999984, "native_execute_wall_seconds": 15.723064763998991, "native_commands_failed_or_timed_out": 0, "tool_version_query_calls": 16, "formal_calls": 0}`。
