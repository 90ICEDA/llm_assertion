# research73：可区分历史门控的真实候选筛选

固定已有14个公共场景及普通接受规则，筛选9套不重复的历史真实模型提案；普通通过后再执行完整105历史回放。未使用独立测试选择候选或调整规则。

|候选|普通通过|历史额外拒绝|确认丢失检出|新增合法误报|必检触发丢失|
|---|---|---|---:|---:|---:|
|c00|False|False|未执行|未执行|未执行|
|c01|True|False|0|0|0|
|c02|False|False|未执行|未执行|未执行|
|c03|False|False|未执行|未执行|未执行|
|c04|True|True|31|46|356|
|c05|True|False|0|0|0|
|c06|True|False|0|0|0|
|c07|False|False|未执行|未执行|未执行|
|c08|False|False|未执行|未执行|未执行|

普通通过 4/9；历史额外拒绝 1。回顾性筛选不能作为新随机实验的机制收益估计。

每个真实提案均核对上游原始响应、模型编辑的程序渲染以及原生采样、独立事务判定、触发和失败日志。旧性质原样执行，无人工改写。

退化点按原因/义务/人工故障机制归组；采样点数量不是独立缺陷数。unknown单列，不把未知检出丢失当作确认漏报。回放结论仅限有限开发数据和人工故障。

拒绝后当前运行写入持久版本记录，保留基线；这验证当前回放的状态行为，不补造旧实验回滚历史。基线部分有效，不声称完整保护。

本轮没有新模型调用，未完成统一预算内拒绝后自动恢复。已知成功提案只能作回顾性可达性对照，不能充当下一轮模型响应。

原始日志复核 1330 份；审计检查 86 项通过。实际成本：{'model_calls': 0, 'prompt_tokens_known_subtotal': 0, 'completion_tokens_known_subtotal': 0, 'usage_unavailable_calls': 0, 'prompt_tokens_total': 0, 'completion_tokens_total': 0, 'model_wall_seconds_known_subtotal': 0, 'model_wall_seconds_unavailable_calls': 0, 'model_status': {}, 'native_compile_calls': 30, 'native_execute_calls': 1360, 'compile_smoke_execute_calls': 30, 'native_compile_wall_seconds': 283.7796746770001, 'native_execute_wall_seconds': 29.63941610600014, 'native_commands_failed_or_timed_out': 0, 'tool_version_query_calls': 30, 'formal_calls': 0}。参考判定随原生执行完成，单独耗时不可用；复核耗时 118.246 秒。

research72 与 research63 的受保护JSON哈希保持不变；未读取独立结果用于候选筛选，没有新独立测试通过声明。

复核命令（新输出目录）：
```powershell
wsl -- python3 scripts/research73_result_audit.py --run deliverables/research73_discriminating_20261024_r01 --out deliverables/research73_audit_NEW
```
