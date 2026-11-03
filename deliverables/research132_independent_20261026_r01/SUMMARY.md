# research132 冻结FIFO的新独立验收

固定集合 `ef3974b9ac0dd7a79f008564d7af4a43b77e9befdc1da93bfb4ba79543bca3da`；候选及规则先封存，之后抽取新种子并生成输入。
执行 128/128 个场景，通过 120，失败 8；指定范围验收：False。
4种Depth/Pipeline配置；已知人工边界故障的新独立输入，非新故障类别或上游历史FIFO缺陷。
|Depth/Pipeline|义务|检出/曝光|漏报|误报|关键unknown|验收|
|---|---|---:|---:|---:|---:|---|
|2/0|order_payload|4/4|0|0|0|True|
|2/0|drain_no_loss|8/8|0|0|0|False|
|2/0|no_unsolicited_output|2/2|0|0|0|True|
|2/0|stall_stability|10/10|0|0|0|True|
|2/0|reset_cancellation|2/2|0|0|0|True|
|4/1|order_payload|4/4|0|0|0|True|
|4/1|drain_no_loss|8/8|0|0|0|False|
|4/1|no_unsolicited_output|2/2|0|0|0|True|
|4/1|stall_stability|10/10|0|0|0|True|
|4/1|reset_cancellation|2/2|0|0|0|True|
|4/2|order_payload|4/4|0|0|0|True|
|4/2|drain_no_loss|8/8|0|0|0|False|
|4/2|no_unsolicited_output|2/2|0|0|0|True|
|4/2|stall_stability|10/10|0|0|0|True|
|4/2|reset_cancellation|2/2|0|0|0|True|
|8/2|order_payload|4/4|0|0|0|True|
|8/2|drain_no_loss|8/8|0|0|0|False|
|8/2|no_unsolicited_output|2/2|0|0|0|True|
|8/2|stall_stability|10/10|0|0|0|True|
|8/2|reset_cancellation|2/2|0|0|0|True|

合并有限证据：{'rows': 70189, 'unknown': 0, 'triggers': 4654, 'false_positives': 0, 'detections': 104, 'misses': 0, 'count_unit': 'obligation-by-sampled-cycle evidence rows, not independent discoveries or transactions', 'later_attribution_unknown': 102}
物理成本：编译4次，实验回放240次，编译冒烟4次，总仿真244次；模型/形式化0。
后续归因unknown保留，不能把首违例检出推广到整个故障轨迹或全局完整保护。无曝光不能算通过；合法控制与目标违例、输入握手及取消均由独立事务模型与原生记录核验。
本批未用于提示、搜索、修改、筛选候选或规则。若以后依据结果修改，整批转为开发数据并另建独立测试。
不能由本次冻结版本验收推导模型恢复成功率、搜索增量或防退化增量。
失败项：[{'case': 'ind132:s3612600325353611429:d2p0:reset_cancels_tail', 'reasons': ['actual_reset_cancellation']}, {'case': 'ind132:s3612600325353611429:d4p1:reset_cancels_tail', 'reasons': ['actual_reset_cancellation']}, {'case': 'ind132:s3612600325353611429:d4p2:reset_cancels_tail', 'reasons': ['actual_reset_cancellation']}, {'case': 'ind132:s3612600325353611429:d8p2:reset_cancels_tail', 'reasons': ['actual_reset_cancellation']}, {'case': 'ind132:s2552425562399558864:d2p0:reset_cancels_tail', 'reasons': ['actual_reset_cancellation']}, {'case': 'ind132:s2552425562399558864:d4p1:reset_cancels_tail', 'reasons': ['actual_reset_cancellation']}, {'case': 'ind132:s2552425562399558864:d4p2:reset_cancels_tail', 'reasons': ['actual_reset_cancellation']}, {'case': 'ind132:s2552425562399558864:d8p2:reset_cancels_tail', 'reasons': ['actual_reset_cancellation']}]
原始SVA/模型来源：research69；本批不修改或重新生成。原生采样、事务、波形及逐项触发在cases/case_*/内。
