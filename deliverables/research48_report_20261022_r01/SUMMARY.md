# research48：真实SVA细化与原生接受检查

终态：sva_rejected_previous_version_retained。新版本接受：False。

|轮次|接受|重复已拒性质|当前结果|历史结果|拒绝原因|
|---|---|---|---|---|---|
|v0|False|False|detections=3/misses=0/false_positives=16/unknown=2/later_attribution_unknown=95|detections=139/misses=14/false_positives=918/unknown=61/later_attribution_unknown=1177|current_gap_not_confirmed_repaired,history_native_unhealthy,legal_window_false_alarm,lost_obligation_trigger,lost_target_detection,native_or_sampling_or_legal_control_failure,new_legal_false_positive,required_transition_not_triggered,target_not_causally_detected,unconfirmed_replay,validated_required_window_not_triggered,visible_false_positives,visible_native_or_legal_control_failure,visible_unknown|
|v1|False|False|不可用|不可用|history_native_unhealthy,history_unavailable,native_window_check_unavailable,unusable_model_output|
|v2|False|False|detections=3/misses=2/false_positives=0/unknown=0/later_attribution_unknown=95|detections=183/misses=31/false_positives=0/unknown=0/later_attribution_unknown=1177|current_gap_not_confirmed_repaired,lost_obligation_trigger,lost_target_detection,required_transition_not_triggered,target_not_causally_detected,validated_required_window_not_triggered,visible_misses|

计数为义务×采样周期证据行，不是独立Bug；后续归因unknown保留。历史防退化仅限实际回放证据。本阶段无新独立测试；接受新版本也不等于独立验收通过或形式化证明。

实际成本：

```json
{
  "model_calls": 3,
  "prompt_tokens_known_subtotal": 54855,
  "completion_tokens_known_subtotal": 559,
  "usage_unavailable_calls": 1,
  "prompt_tokens_total": null,
  "completion_tokens_total": null,
  "model_wall_seconds_known_subtotal": 50.455463841000025,
  "model_wall_seconds_unavailable_calls": 0,
  "model_status": {
    "response_received": 2,
    "service_http_error": 1
  },
  "native_compile_calls": 12,
  "native_execute_calls": 444,
  "compile_smoke_execute_calls": 12,
  "native_compile_wall_seconds": 113.37139317299996,
  "native_execute_wall_seconds": 9.820783481000376,
  "native_commands_failed_or_timed_out": 0,
  "tool_version_query_calls": 12,
  "formal_calls": 0
}
```

只读审计 445/445 通过。请求、响应、各版SVA、原生工具日志和波形见运行目录core/v*/；义务映射见各轮obligation_mapping.json。
