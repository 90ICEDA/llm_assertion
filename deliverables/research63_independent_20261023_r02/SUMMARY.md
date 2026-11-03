# research63：冻结后独立验收

结果：**通过**。冻结 research62 接受集合后生成 96 个新指令字，排除清单含 247 个已用或保守排除的编码，随机种子 `3756902630275473554`。

四类各24个指令字；每字2–9个采样，覆盖首周期和保持阶段。四种RV32E/RV32M配置，新增E1/M0。合法BRANCH含12个bit28=1编码，检查类别外误报；OP控制包括受RV32M配置影响的M编码。

|配置|义务/控制|阶段|实际违例曝光|检出|漏报|误报|unknown|必检未触发|
|---|---|---|---:|---:|---:|---:|---:|---:|
|E0M1|illegal_branch_persists|first|0|0|0|0|0|0|
|E0M1|illegal_branch_persists|held|108|108|0|0|0|0|
|E0M1|op_bit28_illegal|first|24|24|0|0|0|0|
|E0M1|op_bit28_illegal|held|108|108|0|0|0|0|
|E0M1|encoding_controls|first|0|0|0|0|0|0|
|E0M1|encoding_controls|held|0|0|0|0|0|0|
|E0M0|illegal_branch_persists|first|0|0|0|0|0|0|
|E0M0|illegal_branch_persists|held|108|108|0|0|0|0|
|E0M0|op_bit28_illegal|first|24|24|0|0|0|0|
|E0M0|op_bit28_illegal|held|108|108|0|0|0|0|
|E0M0|encoding_controls|first|0|0|0|0|0|0|
|E0M0|encoding_controls|held|0|0|0|0|0|0|
|E1M1|illegal_branch_persists|first|0|0|0|0|0|0|
|E1M1|illegal_branch_persists|held|108|108|0|0|0|0|
|E1M1|op_bit28_illegal|first|24|24|0|0|0|0|
|E1M1|op_bit28_illegal|held|108|108|0|0|0|0|
|E1M1|encoding_controls|first|0|0|0|0|0|0|
|E1M1|encoding_controls|held|0|0|0|0|0|0|
|E1M0|illegal_branch_persists|first|0|0|0|0|0|0|
|E1M0|illegal_branch_persists|held|108|108|0|0|0|0|
|E1M0|op_bit28_illegal|first|24|24|0|0|0|0|
|E1M0|op_bit28_illegal|held|108|108|0|0|0|0|
|E1M0|encoding_controls|first|0|0|0|0|0|0|
|E1M0|encoding_controls|held|0|0|0|0|0|0|

总体计数：`{"rows": 4224, "triggers": 2112, "detections": 960, "misses": 0, "false_positives": 0, "unknown": 0}`。全性质误报检查：0；归因unknown：0。

首批r01因我设置的曝光规则错误而未通过，原记录保留且全部96词转为协议开发数据。本批重新冻结并排除这些词。BRANCH首周期原始RTL本来正确，检查输出正确及实际触发；保持阶段才要求历史违例曝光。OP两阶段都要求真实违例曝光。没有修改断言。

计数单位是采样×配置×版本的证据点；不是独立Bug数。控制组实际违例曝光为0不代表目标义务缺少曝光。

实际成本：模型调用0、tokens 0；原生编译2次，执行2次；编译耗时合计26.566秒，执行0.044秒，形式化调用0。

断言、RTL、开发排除清单和规则先写入freeze.json，随后生成种子及新测试；原生日志、测试平台、波形位于independent/before和after。原断言及历史结果未修改。若未来利用本批结果细化，整批转为开发数据，另建独立测试。

仅支持原始decoder模块有限样本下的两项义务结论；不证明整核、FIFO、所有编码或形式化正确性，也不度量机制额外收益。新词与记录的项目数据不重叠，不等于模型预训练未见。

复核命令：
```powershell
wsl -- python3 scripts/research63_phase_qualified.py audit --out deliverables/research63_independent_20261023_r02
```

新运行（必须使用新目录，冻结后重新生成种子）：
```powershell
wsl -- python3 scripts/research63_phase_qualified.py run --out deliverables/research63_independent_NEW
```
