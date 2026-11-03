# research69：单次延长时限诊断与先导

实际终态：**pilot_passed**。新增真实请求1次，原先导累计3/3；本轮接受=True，新独立验收通过=True。

本轮是HTTP失败后的续接，压缩公共重复诊断并修复实际opener错误采集路径；未改变RTL、规格、AST接口、模型、种子或两个实际目标采样。辅助修正须同样用于未来所有组，不能当作两个核心机制的收益。旧HTTP400原因不能从本轮成功或请求大小倒推。

|版本|传输|目标|105历史|完整接受|
|---|---|---|---|---|
|v0|response_received|{'rows': 14814, 'unknown': 0, 'triggers': 5612, 'false_positives': 0, 'detections': 4, 'misses': 0, 'count_unit': 'obligation-by-sampled-cycle evidence rows, not independent discoveries or transactions', 'later_attribution_unknown': 151}|{'rows': 69124, 'unknown': 0, 'triggers': 16469, 'false_positives': 0, 'detections': 214, 'misses': 0, 'count_unit': 'obligation-by-sampled-cycle evidence rows, not independent discoveries or transactions', 'later_attribution_unknown': 1177}|True|

新独立场景56个，具体各义务曝光/检出/触发/误报/漏报/unknown见原始independent/summary.json。结论仅限有限第一违例归因范围，后续unknown保留，不是形式化证明。

实际成本：10编译/362执行，tokens输入/输出=13065/313，用量缺失调用=0，形式化0。本地HTTP夹具未计入真实请求或模型成功。

审计重算352份原始仿真记录，15项检查通过；采样、事务参考、原生trigger/failure标记和接受决定均复核。research63字节哈希保持不变，未读取其测试用于改进。

多种子两类消融尚未执行。仅在先导完整通过后才可开始；共享提案的单轮门控与独立多轮轨迹分开报告，各组最终冻结后生成新独立测试。不能把单个先导成功解释为受控机制收益。

只读复核（新目录）：
```powershell
wsl -- python3 scripts/research69_result_audit.py audit --prepared deliverables/research69_prepare_20261024_r01 --run deliverables/research69_pilot_20261024_r01 --out deliverables/research69_audit_NEW
```

本轮按单独批准将最后1次额度用于300秒诊断；消息、模型和采样不变，传输源码仅一处180→300改动。没有自动重试。research67、68失败均保留，辅助改动不计为机制收益。
