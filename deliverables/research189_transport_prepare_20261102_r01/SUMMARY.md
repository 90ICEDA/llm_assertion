# research189：research188远程传输绑定本地复核

**85项检查通过；真实模型调用0，新增原生执行0，新独立测试0。**

首轮发送载荷与research188封存请求完全一致；模型、采样参数、初始候选、接受规则、2次上限及1200秒控制器预算未改。继承传输器保存原始响应、用量及实际超时；初始化元数据180秒修正为实际300秒。旧代码和结果保持不变。

本地内存HTTP替身验证真实序列化/解析路径，覆盖正常响应、格式错误、HTTP拒绝、超时和截断；网络独立禁用，未读取密钥。替身记录均标为local fixture，不计真实模型调用或恢复。

端到端本地分支检查覆盖双方接受、普通拒绝、空触发、重复、格式失败、传输失败、条件恢复成功/失败/重复/超时及关键unknown。仅普通接受、历史拒绝且确认退化时允许第二次；历史拒绝保留初始部分集合。手写恢复分支只触发测试spy，没有生成独立样本。

恢复完整接受才冻结并选择32个新语义场景；除检出/触发/误报/unknown外，逐项检查32个目标是否实际曝光。无曝光不能通过，不补抽。1200秒总预算也约束原生进程，独立阶段可能因时限不足成为未完成/unknown，不能自动增加时间。

可申请新用途最多2次调用；此前授权不转用。申请后仍须将明确授权写成用途、封存哈希和输出目录绑定记录，才能使用run入口。条件恢复仍0/0不可估计，H/R等价；任务2/3和576次负结果不变。

本地复现：
```powershell
wsl -- python3 scripts/research189_drop_transport.py prepare --out deliverables/research189_recheck
```

取得明确授权后才可执行（当前没有授权文件）：
```powershell
wsl -- python3 scripts/research189_drop_transport.py run --prepared deliverables/research189_transport_prepare_20261102_r01 --out deliverables/research189_fifo_pilot_run_20261102_r01 --authorization <authorized-file.json>
```
