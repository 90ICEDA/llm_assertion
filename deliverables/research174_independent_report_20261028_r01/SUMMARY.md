# research174 独立验收复核

**整批未通过：37/40。** 两类KEEP目标33/33检出，0漏报、0误报、0关键unknown；三个合法场景没有实际背压/解除曝光，按预封存标准保持未通过。没有修改候选、补抽场景或追改research172。

|项目|实际结果|结论|
|---|---|---|
|非尾拍KEEP|17个原始违例点；17检出、17必要触发|本批曝光范围通过|
|尾拍非零KEEP|16个原始违例点；16检出、16必要触发|本批曝光范围通过|
|合法传输|16/16无误报；14个合法部分尾拍实际输出；其中3场景缺背压/解除|按全部场景要求13/16通过|
|背压与解除|37/40场景有背压；29/32非复位场景有解除；两版各230个保持检查周期|未曝光三个场景；未注入保持故障，不能报告其故障检出通过|
|复位取消|8/8取消已接受请求及被背压阻塞的输出；复位后无请求且无输出|合法复位范围通过，未注入复位故障|

失败场景ID为1、7、22（13/7/6字节帧，输入间隔3，ready延迟14）。输出呈现周期恰好全部ready=1；虽然激励含周期性背压，实际事务未遇背压。具体采样见unexposed_scenarios.json。该结果是曝光不足，并非发现断言误报或目标漏报。

原始前后RTL各执行3840周期。40个实际事务轨迹均未重复开发记录，且每版内无重复；去重忽略数据值、种子与场景编号。参数固定8→32、输入KEEP禁用，未外推其他参数。
SVA失败来自Verilator原生执行；触发计数来自同一执行中的前件诊断及周期/复位对齐，并非native cover或形式化证明。五条性质每版触发数分别45、32、230、230、230，见trigger_mapping.json。

复核72项通过，仅说明记录和结论一致，不改变整批未通过结果。本地编译2次、执行2次，模型0次，形式化0次。
research172仍是普通与历史规则同时接受后停止。本次独立验收不能改称额外拒绝或恢复成功，条件恢复仍0/0、不可估计。
本批保持独立，不反馈修改。若后续据此调整候选或规则，须将整批转为开发数据，再单独冻结并生成新批次；不得把替代场景并入本批追认40/40。

## 产物与复核

- 冻结/排除清单：`deliverables/research174_independent_prepare_20261028_r01/`
- 执行命令、原始日志、波形、逐场景判定：`deliverables/research174_independent_run_20261028_r01/`
- 本报告、事务关联、触发映射和无曝光采样：本目录。

```powershell
wsl -- python3 scripts/research174_independent_acceptance.py verify --prepared deliverables/research174_independent_prepare_20261028_r01
wsl -- python3 scripts/research174_result_audit.py --prepared deliverables/research174_independent_prepare_20261028_r01 --run deliverables/research174_independent_run_20261028_r01 --out deliverables/research174_independent_report_recheck
```
复核输出必须使用不存在的目录；不会重跑仿真或调用模型。
