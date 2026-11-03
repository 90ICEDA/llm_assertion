# FIFO 未曝光与失败归因审计

仅本地只读审计及补测设计：模型0、仿真0、断言修改0、新独立验收0。旧结果与冻结版本保持不变。

复核18批、360个参数—义务单元、2016份原生执行记录；重新解析日志、事务参考判定、采样、原生触发/失败和全部账本/排除记录。

## 未曝光不是已经确认的漏报

|分类|单元数|
|---|---:|
|obligation_exercised_without_target_violation|144|
|violation_observed_but_after_first_epoch_violation|18|

Depth2/Pipeline0和Depth4/Pipeline1批次只配置drop尾部丢失测试；四项其他义务没有对应首违例。Depth4/Pipeline2排空违例发生在更早错误之后，保留归因unknown。不能将这些参数上的义务判为设计不适用，也不能用SVA触发数代替独立义务适用检查。

## 失败与后续归因

10个失败单元来自1个冻结哈希，合计100个有限漏报点；重复批次不是独立Bug。故障机制：long_valid_withdraw_release, long_valid_withdraw_stalled, valid_withdraw_release, valid_withdraw_stalled。
原生原因分布：{'triggered_but_insufficient': 100}。逐点起始/检查采样、真实属性及正确侧对照见failed_cells.json。
全部10060条后续归因记录均绑定到同复位区间更早的真实义务违例；分类{'same_obligation_after_first': 3391, 'different_obligation_after_first': 6669}。这是位置归因，不建立新的因果检出，全部仍为unknown。

## 固定补测对象

research69冻结哈希 `ef3974b9ac0dd7a79f008564d7af4a43b77e9befdc1da93bfb4ba79543bca3da`；依据开发目标+105历史门控（214个检出保留）固定，不按本轮独立成绩重新选优。
该版本当前矩阵20单元：9未曝光、0失败。补测清单见SUPPLEMENTAL_TESTS.md；不会拿失败的另一哈希替换这个版本，也不会覆盖旧失败。
本轮把参与归因和补测设计的18批输入登记为未来开发数据；旧独立结果保持历史事实，今后不能再次用作未见验收。新的独立测试须在补测/修改结束、最终版本冻结后另行生成。

复核：
```powershell
wsl -- python3 scripts/research129_fifo_gap_audit.py --out deliverables/research129_fifo_gap_audit_NEW
```
