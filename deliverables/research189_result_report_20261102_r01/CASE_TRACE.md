# 真实提案与事务轨迹

以下均来自本次真实响应和原生执行。

初始部分集合：
```json
[
  {
    "label": "first_stalled",
    "antecedent": "first_present && !m_axis_tready",
    "consequent": "input_complete && input_count <= DEPTH",
    "timing": "same_sample",
    "obligations": [
      "oversize_frame_atomic_drop"
    ]
  }
]
```

shared模型原始结果：
```json
{
  "assertions": [
    {
      "label": "first_stalled",
      "antecedent": "first_present && !m_axis_tready",
      "consequent": "input_complete && input_count <= DEPTH",
      "timing": "same_sample",
      "obligations": [
        "oversize_frame_atomic_drop"
      ]
    },
    {
      "label": "ready_first_legal",
      "antecedent": "first_present && m_axis_tready && input_complete && input_count <= DEPTH",
      "consequent": "input_complete && input_count <= DEPTH",
      "timing": "same_sample",
      "obligations": [
        "oversize_frame_atomic_drop"
      ]
    },
    {
      "label": "ready_first_oversize",
      "antecedent": "first_present && m_axis_tready && input_complete && input_count > DEPTH",
      "consequent": "!first_present",
      "timing": "same_sample",
      "obligations": [
        "oversize_frame_atomic_drop"
      ]
    }
  ],
  "reason": "Added two ready-first properties to cover the current missed first-presentation checks. ready_first_legal preserves legal nonoversize frames by requiring input_complete and input_count <= DEPTH when first_present and m_axis_tready are both true. ready_first_oversize enforces atomic drop of oversize frames by forbidding first_present when input_count > DEPTH. The existing first_stalled property is retained unchanged to preserve earlier valid stalled-first protection."
}
```

逐事务采样、接受及握手周期见 transaction_traces.json；没有新独立结果，不拼接旧独立测试。
