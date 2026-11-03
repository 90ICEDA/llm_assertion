# 义务映射多性质本地资格验收

已移除新接口及两处OP触发门控中的位置假设；同一义务可以有多条性质，顺序不决定义务。总集合仍限2–6条，每条声明一个已知义务，必须包含两项义务。
原research51组装/账本本已支持多对一；research54固定BRANCH的旧流程使research55/59用a0以外代表OP，research135/136据此限制槽位。旧脚本和旧结果没有修改。

|对象|普通O/完整H|完整151检出|漏报|账本误报|关键unknown|丢失旧检出|
|---|---|---:|---:|---:|---:|---:|
|split|[True, True]|690/690|0|0|0|0|
|permuted|[True, True]|690/690|0|0|0|0|
|duplicate|[True, True]|690/690|0|0|0|0|
|branch_first_only|[False, False]|420/690|270|0|0|270|
|wrong_labels|[False, False]|0/690|690|0|0|270|
|legal_false_alarm|[False, False]|690/690|0|2224|0|0|
|historical_loss|[True, False]|549/690|141|0|0|141|
|archived136_exact|[True, True]|690/690|0|0|0|0|

split/permuted/duplicate为本地正对照，成功不计为模型成功；重复性质没有增加有效证据数。缺失保持周期、错误义务标签、全性质合法误报仍被拒绝，历史损失夹具仍为O接受/H拒绝。
archived136_exact是旧模型响应逐字段不变的回顾性原生诊断。它不是新生成、恢复或前瞻试验，绝不追改research136接口失败。详情及原生波形见对应目录。
每项义务的每条性质分别记录触发/违例证据；独立ISA判定和所有性质误报检查保持不变。原始RTL、当前9、搜索36、历史115及420OP+270BRANCH要求未改变。
本轮59项执行核查、33888条原生记录复核；48次编译、48次实际仿真，模型0、形式化0、独立测试0。局部损坏账本/unknown检查是标明的程序负测试，不冒充原生结果。
请求预览仅更改输出映射约定，其余开发信息、候选、模型和采样相同。封存本地协议与代码；尚未封存或启动新的远程先导。未来接入须同样替换完整执行及审计入口，不可只放宽JSON接口。旧条件性额度不用于本轮。

复核封存（无模型调用）：
```powershell
wsl -- python3 scripts/research140_mapping_qualification.py verify --prepared deliverables/research140_mapping_prepare_20261027_r01
```
重新执行本地原生资格（新输出目录）：
```powershell
wsl -- python3 scripts/research140_mapping_qualification.py run --prepared deliverables/research140_mapping_prepare_20261027_r01 --out deliverables/research140_native_recheck
```
