# 复杂 FIFO 冻结验收矩阵（只读历史盘点）

核验 18 个物理测试批次、12 个不同冻结哈希；360 个版本×参数×义务单元。包括失败和回退版本。
本轮模型调用0、原生执行0、新接受版本0、新独立测试0。重算已有证据账本，未把归档结果用于 research123 选择或反馈；不重新声称旧测试对未来实验仍独立。

对象为 axis_fifo 实际 RTL 加明确人工故障。通过仅指该批首个可归因证据；后续归因 unknown 保留，不能称全局完整保护或形式化证明。

|版本|冻结哈希前12位|检出/曝光|误报|关键unknown|后续unknown|归档有限通过|
|---|---|---:|---:|---:|---:|---|
|research40_interface_continuation_20261022_r01|47779dad50a3|70/70|0|0|546|True|
|research41_real_20261022_r01/s4103|551bf158f726|62/62|0|0|604|True|
|research41_real_20261022_r01/s4111|8d64a4c281be|67/67|0|0|575|True|
|research41_real_20261022_r01/s4127|8d64a4c281be|67/67|0|0|575|True|
|research41_real_20261022_r01/s4133|aa97b37a39d3|67/67|0|0|575|True|
|research43_real_20261022_r01/evaluation/0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1|0403e89b8e64|48/68|0|0|565|False|
|research50_real_20261022_r01/evaluation/0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1|0403e89b8e64|38/58|0|0|580|False|
|research69_pilot_20261024_r01|ef3974b9ac0d|74/74|0|0|548|True|
|research71_real_20261024_r01/evaluation/0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1|0403e89b8e64|50/70|0|0|573|False|
|research71_real_20261024_r01/evaluation/4e39b137d62e5175ec0c54dd65e9c157c3e5506436dc2f9e5b71b00c43e016a9|4e39b137d62e|70/70|0|0|573|True|
|research71_real_20261024_r01/evaluation/657708ba1a574f21b1d5413587d2f942018d2142ccc60a85261b54c21f6cdf1c|657708ba1a57|70/70|0|0|573|True|
|research71_real_20261024_r01/evaluation/7ef93130c405c00b2fe19ad655f9492fbcf2ca2f740e57a713294538a223e5d8|7ef93130c405|70/70|0|0|573|True|
|research72_real_20261024_r01/evaluation/0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1|0403e89b8e64|59/79|0|0|522|False|
|research72_real_20261024_r01/evaluation/329a5c435b28da95f8e8c3ef883e689e576aa462589a085a9b68cddb408572ab|329a5c435b28|79/79|0|0|522|True|
|research72_real_20261024_r01/evaluation/32afe40ab46c48f73aebf803b0441492f6251839b8c46e6256a7ea02a1362aba|32afe40ab46c|79/79|0|0|522|True|
|research72_real_20261024_r01/evaluation/657708ba1a574f21b1d5413587d2f942018d2142ccc60a85261b54c21f6cdf1c|657708ba1a57|79/79|0|0|522|True|
|research81_real_20261025_r01/independent_by_hash/0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1|0403e89b8e64|48/68|0|0|556|False|
|research81_real_20261025_r01/independent_by_hash/d26cff98c4196dc916da4642a29d8417f4aec2fb154fe0ba5fb22eece398bc47|d26cff98c419|68/68|0|0|556|True|

逐参数全部义务见 MATRIX.md / matrix.json；0曝光标为 not_exposed，不随总体通过继承为通过。原生执行异常、关键unknown与后续归因unknown分别记录。
没有按收益选择版本；无法绑定冻结的记录和其他格式见 inventory.json。相同哈希、重复测试或共同测试不构成独立成功样本，不能将本表比例用作模型生成／恢复成功率。

复核命令：
```powershell
wsl -- python3 scripts/research127_fifo_frozen_matrix.py --out deliverables/research127_fifo_matrix_NEW
```
