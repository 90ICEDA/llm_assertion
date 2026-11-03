# research46：先验收周期判断，再允许SVA

终态：applicability_rejected_no_sva。记录审计 202/202。

真实周期判断调用 2，判断通过 False；真实SVA调用 0，接受 False；独立验收已执行 False。

逐窗口判断、原生触发对应、拒绝原因及模型用量见results.json。失败与unknown不计通过，未达到的阶段不计完成。

```json
{
  "model_calls": 2,
  "prompt_tokens_known_subtotal": 19219,
  "completion_tokens_known_subtotal": 1140,
  "usage_unavailable_calls": 0,
  "prompt_tokens_total": 19219,
  "completion_tokens_total": 1140,
  "model_wall_seconds_known_subtotal": 37.192995349,
  "model_wall_seconds_unavailable_calls": 0,
  "model_status": {
    "response_received": 2
  },
  "native_compile_calls": 0,
  "native_execute_calls": 0,
  "compile_smoke_execute_calls": 0,
  "native_compile_wall_seconds": 0,
  "native_execute_wall_seconds": 0,
  "native_commands_failed_or_timed_out": 0,
  "tool_version_query_calls": 0,
  "formal_calls": 0
}
```
