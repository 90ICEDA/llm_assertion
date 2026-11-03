# 原始 Ibex #54 部分候选本地资格

**本地资格成立，已封存待授权先导；模型调用 0。手写对照不是新模型提案，也不是模型恢复成功。**

从上轮固定三个案例中按实际保护行为选择 Ibex #54：同一真实修复涉及移位类与立即数类 HINT；adapter 缺已检出历史目标，pause FIFO 缺另一曝光漏报。新建手写部分基线检查移位 HINT 与直通，明确没有覆盖 LI/LUI。没有把完整 oracle 按指令字白名单屏蔽，没有修改原始 RTL。

476 个开发指令，69 个 LI/LUI 原始违例，27 个移位 HINT 原始违例。公共检查包含全部其余合法／保留编码及直通控制；历史追加移位 HINT 违例。原始前后采样与独立 ISA 规则逐项核验，修复后全部无违例。

|本地手写对照|公共目标检出|历史目标检出|误报采样|普通接受|历史接受|
|---|---:|---:|---:|---|---|
|baseline|0/69|27/27|0|False|False|
|replacement|69/69|0/27|0|True|False|
|complementary|69/69|27/27|0|True|True|
|overbroad|69/69|27/27|100|False|False|

replacement 按完整语义类别替换保护：修复当前 LI/LUI，同时删除旧移位检查。普通规则接受，历史规则因实际检出和触发丢失额外拒绝；不是靠公开指令字列表限制前件。拒绝后仍使用原部分基线，其哈希及原生检出证据在 retained_version.json。complementary 是人工正对照，只证明接口允许同时满足两组检查；不能算自动恢复。

所有性质可以编辑，支持同义务多性质。性质只能读取原始接口信号，无法读取样本编号、类别、期望值或私有参考答案；接口非法字段、赋值／注入和重复义务支持已本地检查。实际触发由逐样本原生前件标记辅助观测，失败来自原生 assert property；不是形式化覆盖证明。

公共／历史差别及全部原始采样在 *_evidence.json。缺口属于断言未触发；公开控制中的高位移位保留编码能拒绝 overbroad。不能仅用模型声明的 obligations 映射代替行为判定。

## 已封存边界

最多 2 次未来调用：共享真实提案 1 次；仅出现普通接受、历史拒绝且确认退化、无关键 unknown 时，历史反馈恢复 1 次。不重试，不扩种子。完整恢复接受后才冻结并生成新独立测试。当前无调用授权，不执行任何远程请求。

没有放入手写 replacement/complementary/overbroad 正负对照或其执行结果，也没有发送旧成功 SVA 或独立测试；请求仅含部分基线、原始 RTL、公共规格及公共开发诊断。先导用于增加历史检查的作用，H/R 等价限制不变。全部新样本是开发资格数据，绝非独立结果。

本轮原生编译 8、执行 8，编译墙钟 192.397s、执行 0.171s。模型 0、形式化 0。新模型接受版本／真实额外拒绝／恢复／独立通过均 0；条件恢复仍 0/0。

只在未来取得明确预算后执行封存先导；不能用这些手写对照声称已证实防退化的前瞻收益。576次搜索负结果与原有 FIFO 独立验收保持不变。

```powershell
wsl -- python3 scripts/research162_partial_candidate.py prepare --out deliverables/research162_prepare_new
wsl -- python3 scripts/research162_partial_candidate.py run --prepared deliverables/research162_prepare_new --out deliverables/research162_native_new
wsl -- python3 scripts/research162_partial_candidate.py report --prepared deliverables/research162_prepare_new --executed deliverables/research162_native_new --out deliverables/research162_report_new
```
