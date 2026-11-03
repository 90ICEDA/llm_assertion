# research179 真实受限先导：普通检查拒绝，按协议停止

本轮实际使用1/2次授权调用，新增接受版本0。真实模型补上当前目标2/2，并保持历史目标6/6，必要目标触发均有记录；但对合法多拍帧产生8条误报。普通与历史规则均拒绝，不存在额外历史拒绝机会。第二次调用未启动，未冻结新接受版本、未抽取或执行32个独立场景。

## 具体失败

模型新增 `finish && !prev_complete |=> frame_len_valid && frame_len == $past(beat_bytes)`，把“前一周期未完成帧”误当作“当前帧只有一拍”。该条件也适用于正常多拍帧的最后一拍，因此错误地只比较最后一拍字节数。

KEEP启用32位时，cycle12接受一个三拍帧的尾拍：此前累计8字节、当前3字节；cycle13原版与修复版均正确报告11，但模型性质要求3。另一个两拍帧cycle23接受尾拍，cycle24正确报告6、性质要求2。KEEP关闭8位时对应为3对1及2对1。两帧×两配置×前后版本，共8个误报采样点，不是8个独立Bug。逐拍接受、起始/检查采样及参考计数见 false_positive_witnesses.json。

模型还增加 `rst |-> ...`，但所有性质包装为 `disable iff(rst)`，该性质没有有效触发，不能计为复位保护。它不是本次接受失败的替代解释；已确认的8条合法误报足以使普通规则拒绝。

模型原始响应、修改理由、JSON性质、可执行tb.sv、工具版本、命令、原始日志及波形均在运行目录。最终调用 result.json 标记 expressions_preserved；transport_result.json 在接口解码之前写入，其 not_generated 是阶段状态，不能据此误判没有候选。未人工修改模型谓词。

## 接受决定与机制含义

O=false、H=false，终态 stop_ordinary_rejects。两组都保留初始部分集合及其6个旧检出；因此当前2个目标在活动旧版本上仍漏报。拒绝未接受提案不等于新问题已经修复。

额外历史拒绝0，条件恢复0/0不可估计，新独立通过数不可估计。该结果不证明防退化的增量恢复价值，也不是其失效结论；本轮没有进入可区分分支。H/R等价限制、576次搜索负结果和旧独立验收结果均未改变。

剩余1次仅用于本协议已限定的条件恢复；条件未成立，不能挪作追加生成或改提示重试。本路线本轮结束，不扩种子。

## 实际成本与核验

1次 DeepSeek V3-0324 调用，无重试；输入5539、输出494 tokens；模型等待5.603秒；4次原生编译、4次执行，编译34.274秒、执行0.078秒；形式化查询0。60项结果复核通过。仿真和手写接口预检不构成形式化证明或模型恢复成功。

实际执行命令（已完成；不要用此命令重试旧输出目录）：
```powershell
wsl -- python3 scripts/research179_frame_controller.py run --prepared deliverables/research179_frame_controller_prepare_20261029_r01 --out deliverables/research179_frame_controller_run_20261029_r01 --authorization deliverables/research179_authorization_20261029_r01.json
```

可复制的本地只读复核（报告目录必须未存在，无模型调用）：
```powershell
wsl -- python3 scripts/research179_result_audit.py --prepared deliverables/research179_frame_controller_prepare_20261029_r01 --run deliverables/research179_frame_controller_run_20261029_r01 --out deliverables/research179_result_recheck
```
