# research81：恢复流程对照准备与实跑资格

状态：本地实现与原生资格验证完成；真实对照尚未执行，需新授权。新接受模型版本0，新独立验收0。

## 固定协议

|组|第一调用|第二调用条件|最终标准|
|---|---|---|---|
|P 完整计划流程|输出完整规则和11窗口答案|完整判断通过后生成一次SVA；失败即停|5窗口场景＋14公共＋105历史|
|D 直接生成流程|直接生成SVA|首版拒绝后依据自己的原生/接口诊断细化一次；接受即停|完全相同|

固定种子8107、Qwen72B、temperature0.2、输出上限2048 tokens、每次输入64000字符、300秒总超时。两组各最多2次，总计最多4次；不重试、不挪用额度，传输/执行异常全局停止。
两组共用逐字一致的公共开发内容：RTL、规格、初始候选、接口、开发观察和11窗口。每个请求中阶段任务与输出格式不同；P的实际通过计划是该流程自己的处理产物，不泄露给D。
这是固定两次调用预算下的辅助流程比较，不是仅移除一个门控开关的纯因果实验：D最多两次性质提案，P将一次额度用于计划。必须同时报告性质机会数、调用、tokens和原生成本。单种子结果不能证明稳定效应，也不是两个核心机制的增量验证。

## 本地实跑资格

预算/门控/隔离检查31项；新增原生日志复核258份。

|归档对照|接受|窗口检出/漏报|公共检出/漏报|历史检出/漏报|
|---|---|---|---|---|
|archived_positive|True|12/0|3/0|214/0|
|archived_queue_head_negative|False|7/2|未执行|未执行|

以上是归档模型版本的本地正负对照，不是本轮真实生成成功；成功性质未进入任何模型请求。关键unknown与后续归因unknown分别保留，具体数值见qualification.json。
准备成本：原生编译13次，执行271次（启动自检13次），模型0次，形式化0次。

## 接受、冻结与停止

两组均必须实际通过原生目标检出、必要触发、合法误报和105历史保护检查。unknown不算通过；重复可执行性质在编译前拒绝。拒绝继续保留公共基线。
两组都终止并冻结后，仅在至少一个新接受版本存在时生成同一批全新56场景，覆盖Depth2/4/8及五义务；同哈希只物理回放一次。已有开发与旧独立输入按哈希排除，新测试不反馈、不选候选。新独立失败或无新接受即停止，不追加种子或提示修正。
research80的原失败保持不变：B/C/D规则可执行正确并不等于完整模型判断通过，也不能推断未生成SVA的结果。完整门控究竟有利于生成尚未得到本轮对照结果。

## 入口

```powershell
wsl -- python3 scripts/research81_recovery_comparison.py verify --prepared deliverables/research81_prepare_20261025_r01
# 获得本协议专用授权并保存绑定记录后才可运行；既有research80剩余额度不能转用。
wsl -- python3 scripts/research81_recovery_comparison.py run --prepared deliverables/research81_prepare_20261025_r01 --authorization deliverables/research81_prepare_20261025_r01/authorization.json --out deliverables/research81_real_20261025_r01
wsl -- python3 scripts/research81_audit.py --prepared deliverables/research81_prepare_20261025_r01 --run deliverables/research81_real_20261025_r01 --out deliverables/research81_audit_20261025_r01
```

来源与代码版本通过SHA256封存；当前工作区没有可用Git历史，不补造过去提交号。
