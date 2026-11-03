# research174 单独冻结后的独立验收

结果：failed_or_unresolved；场景37/40通过。

|分层|通过/总数|
|---|---|
|short_target|8/8|
|long_target|8/8|
|legal_transfer|13/16|
|reset_cancel|8/8|

原始KEEP目标曝光33点，漏报0；误报before/after=0/0；关键unknown=0。

独立范围固定为原始axis_adapter 8→32、输入KEEP禁用。新断言先冻结，再生成新场景；开发排除清单及实际轨迹新颖性逐项保存。不通过/重复/无曝光均保留，不补抽替换。
两类KEEP目标检出与背压/复位合法行为检查分开。没有注入背压或复位故障，因此其故障检出能力未曝光，不能算完整故障保护通过。也不代表其他参数、全模块证明或形式化证明。
research172仍为“两规则同时接受后停止”，此次为单独独立验收，不追认恢复链。条件恢复仍0/0、不可估计。

本轮模型0次；原生编译2次、执行2次；编译19.332s、执行0.075s。

候选和规则未根据本批结果修改。若未来使用本批失败调规则/模型/候选，整批应转为开发数据并重新准备独立测试。

本次执行命令：
```powershell
wsl -- python3 scripts/research174_independent_acceptance.py run --prepared deliverables/research174_independent_prepare_20261028_r01 --out deliverables/research174_independent_run_20261028_r01
```
运行目录不可重复使用，防止隐式重试。只读核验命令：
```powershell
wsl -- python3 scripts/research174_independent_acceptance.py verify --prepared deliverables/research174_independent_prepare_20261028_r01
```
