# research69 实际修改轨迹

本轮真实模型仅替换 a4；其他四条性质保持原样。结构化 AST 只做语法组装，没有人工修改谓词。

原性质：
```systemverilog
(mvalid && !mready) |=> mdata == $past(mdata)
```

模型新性质：
```systemverilog
((mvalid && (!(mready)))) |=> (((mdata == $past(mdata)) && (mvalid == $past(mvalid))))
```

|证据|前件周期|检查周期|新性质触发/失败|正确侧触发|
|---|---|---|---|---|
|fifo:44c2b402dfcda624d739b5829628689cfa3946fdf5362489ea237dd8390eac20|6|7|True/True|True|
|fifo:79e16bbf6afcc7e2e841a7773712c92f990b7748d909fbc78c07fdf3a0b08851|16|17|True/True|True|

开发门控原始记录：/mnt/d/AssertionForge-main1/deliverables/research69_pilot_20261024_r01/core/v0/target_native

历史回放：/mnt/d/AssertionForge-main1/deliverables/research69_pilot_20261024_r01/core/v0/history_native

完整接受=True；新独立验收=True。每个样本对应的独立义务判断和旧断言状态保存在 case_trace.json，完整波形在原生目录的 wave.vcd。

解除边界属于公共已知缺口；持续背压见证来自契约搜索，虽未由本轮公共反馈曝光，但已经是历史已知人工故障。其他搜索方法也找到同一去重缺口，因此本例不证明契约独有收益。

本提案同时通过普通目标门控与历史门控，后者没有额外拒绝它。历史保护保持不等于防退化机制具有已证实的增量收益。模型接口、组件生成和传输调整均属于公共辅助措施。

独立测试仅用于冻结后验收，不反馈或选择候选；后续归因 unknown 保留。结论限实际 FIFO RTL 加人工故障的有限仿真范围，不能当作原始历史缺陷复现、全局无退化或形式化证明。
