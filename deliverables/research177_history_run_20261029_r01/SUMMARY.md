# research177 新历史案例本地筛选

候选按预定提交顺序固定4项；不按预计机制收益替换。只做开发资格验证，模型调用0，没有模型先导或独立测试。

|案例|前后见证对|结论|
|---|---|---|
|pipeline_offbyone|2/3|source_and_functional_witness_qualified|
|pipeline_assignment|0/1|unknown_no_functional_pair_witness|
|switch_alignment|0/0|excluded_whitespace_only|
|frame_len_consecutive|2/2|source_and_functional_witness_qualified|

逐对结果：

|案例/配置|合法输入一致|旧版失败点|新版失败点|见证|
|---|---|---|---|---|
|pipeline_offbyone/2|True|2|0|True|
|pipeline_offbyone/3|True|0|0|False|
|pipeline_offbyone/4|True|2|0|True|
|pipeline_assignment/2|True|2|2|False|
|frame_len_consecutive/0|True|4|0|True|
|frame_len_consecutive/1|True|4|0|True|

来源：本地缓存的alexforencich/verilog-axis Git对象；每个原始文件核验Git blob和SHA256，保存直接父提交、修复提交、补丁、同提交README及工具日志。不宣称本轮重新联网核验上游。
未调参资格限于已检查的本地请求/计划/协议/脚本记录。完整查阅清单与命中在准备目录prior_usage_audit.json；不能排除已删除或外部云机记录。独立结果未用于筛选。
pipeline FIFO按各版实际握手建立队列，输入端口激励完全相同，容量变化可能导致接受数量不同；不把ready或延迟不同当违例。frame_len由独立接受拍累加及帧边界规则判定，手写SVA只作原生诊断，不计真实模型生成。
编译/工具失败与缺少真实前后违例均保留unknown；空白排版修复明确排除。失败点是有限采样，不是独立Bug数量；非形式化证明。
本轮未验证可编辑部分候选、旧保护＋当前漏报、非白名单区分和新独立余量，因此来源/见证通过不等于可以调用模型。H/R等价、条件恢复0/0及576次搜索负结果保持不变；stat及原始FIFO presented来源/见证unknown不变。

成本：{'model_calls': 0, 'network_calls': 0, 'formal_calls': 0, 'native_compiles': 12, 'native_executions': 12, 'compile_seconds': 102.97668951699973, 'execute_seconds': 0.23517799100000047}

执行命令（目录必须不存在）：
```powershell
wsl -- python3 scripts/research177_history_screen.py run --prepared deliverables/research177_history_prepare_20261029_r03 --out deliverables/research177_history_run_20261029_r01
```
