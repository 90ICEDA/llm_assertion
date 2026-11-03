# 新历史案例资格与封存结果

**三项本地资格均成立：部分保护、非白名单区分、未用时序场景容量。已封存axis_adapter先导协议和请求；模型调用0。**

范围是原始axis_adapter c1c3dc0修复前后，8→32位，输入KEEP禁用。没有改RTL、注入故障或调用旧独立测试挑选规则。原始Git blob复核通过。

|手写本地对照|当前末拍检出|历史全部目标检出|旧保护丢失|合法误报周期|普通／历史|
|---|---:|---:|---:|---:|---|
|baseline|0/8|12/20|0|0|False/False|
|replacement|8/8|8/20|12|0|True/False|
|complementary|8/8|20/20|0|0|True/True|
|overbroad|8/8|20/20|0|32|False/False|

基线已有非末拍实际检出，同时遗漏公共短帧末拍。替换对照依据TLAST语义，普通规则接受而历史规则额外拒绝，拒绝后保留原部分基线。互补正对照能同时满足两组检查。它们都是明确手写的资格夹具，不能计真实模型提案、自然退化概率或自动恢复成功。

33个开发场景、每场景96周期；原生SVA作用于原始RTL，独立握手队列检查字节、掩码、帧边界、排空、复位和背压。前后实际输入一致。修复版参考检查无失败，旧版失败来自原始KEEP缺陷。计数是违例采样，不是独立Bug。

## 独立余量已在调用前核查

|分层|去除重复ready波形后的结构余量|需要|
|---|---:|---:|
|current_target|48|8|
|historical_target|288|8|
|legal_control|336|16|

按单帧长度、输入间隔、实际ready控制序列与KEEP去重，不按payload/种子。排除了当前1/3/5/9长度、间隔0/1、背压周期4的开发形状，以及旧research159/160的两帧[2,2]。未来仍须冻结后才抽取32个场景，并检查实际接受轨迹不重复、两类原始目标实际曝光；不能把池容量当作独立通过。重复/无曝光/失败不补抽。

## 保留的错误与成本

首轮replacement/complementary误用了SystemVerilog保留字final作标签，4次编译失败、未执行。已保留原封存与错误日志；仅改名final_keep，逐字核对性质/激励/RTL完全不变，重新运行这4次，其余4次成功回放直接复用。
本轮合计编译12次（含失败4）、执行8次；编译73.028s、执行0.240s。模型/形式化0。

## 下一步边界

先导协议和请求在qualification/pilot/：最多2次真实调用，第一份共享提案仅在普通接受/历史拒绝且确认退化、无unknown时允许一次恢复；完整接受后冻结并独立验收，不重试不扩种子。
**实际预算控制器尚未接入这个新接口。下一步先完成本地控制器集成及分支预检，再申请明确模型授权。** 这与资格/协议封存分开报告。真实额外拒绝、恢复、独立通过均尚未发生，条件恢复仍0/0；H/R等价限制不变。

既有FIFO独立结果、stat来源unknown和576查询负结果保持不变，已知TKEEP问题不重新算作搜索收益。

```powershell
wsl -- python3 scripts/research166_adapter_label_correction.py report --prepared deliverables/research166_adapter_prepare_20261028_r01 --executed deliverables/research166_adapter_native_20261028_r01 --out deliverables/research166_report_recheck
```

资格详情和完整复跑命令见qualification/SUMMARY.md，最终先导协议见qualification/pilot/protocol.json。
