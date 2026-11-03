# 2026-10-15 核查与续作验收矩阵

本轮固定两项机制，不改研究方向。旧目录封存；本轮仅写 `research15_*`。`git` 版本不可用时保存执行源码快照和 SHA256。下表的“此前状态”来自上一轮原始摘要及失败记录，不以代码存在代替实验。

| 要求 | 此前状态与证据 | 本轮验收与负责文件 | 产物 |
|---|---|---|---|
| 真实模型生成→原生执行→反馈→修改→接受/拒绝 | 已执行但所有版本拒绝；模型复读错误 bit stability，实际前件与单独声明 trigger 不符 | `research15_native*.py`：实际调用、原生 antecedent cover、重复性质检查、逐义务/互补集合；接受版本与拒绝版本分别留存 | `research15_native_20261015_r01` |
| 四法契约搜索 | 旧11对已完成864查询，但策略仅模板曝光调度；36/37/43/43，不支持总体优势 | `research15_search*.py`：根据自有历史义务/触发缺口选择下一个测试；同初始候选、种子、grammar、预算；独立oracle、语义去重 | `research15_search_20261015_r01` |
| 原生四组消融 | 旧四臂是stat条件规格+过程检查器，因接口错误实际成本不齐 | 同真实初始FIFO候选、同模型配置，A反馈/B搜索/C门/D两者；不得向A/C泄露搜索证据，记录实际成本差异 | native目录中的各臂请求、响应、决策和回放 |
| 防退化断言集合 | 旧门能拒绝新FP；历史有效TP为空；存在未完整重放/unknown丢失风险 | `research15_acceptance.py`：固定证据身份、拒绝历史记录缺失、unknown、丢检、前件cover丢失、新FP和当前目标未修复；集合OR覆盖 | integration的资格检查 + native实际门决策 |
| FIFO Depth≥2 | 96执行、4个人工故障/义务类；Depth3实际容量4；未专门测试复位残留 | 新runtime输入重放；连续/重叠/背压/复位/不同深度；增加明确人工reset residue故障，复位期不误报 | search/native目录的trace、oracle、transactions、wave、tool logs |
| Ibex及其他真实案例 | Ibex54旧输入4次复跑；其他尚未接入 | `research15_history*.py`：可靠第二个原始修复或Ibex新的独立向量；原始前后源码/提交/来源/环境/见证 | `research15_history_20261015_r01` |
| 独立测试 | 旧holdout已见，仅属于未来开发数据；旧native测试的是拒绝版本 | 最终四臂冻结后生成新测试；新深度/流水/种子；失败保留、不得据此修改后继续称独立 | freeze、split、independent目录 |
| 六父Bug完整保护 | 未完成；stat overlap、intr mask、spill invalid payload与FIFO presented仍unknown | 逐父保留分母和状态；不能以人工边界故障、局部义务或Ibex复现替代六父成功 | 最终父Bug汇总 |
| 完整证据链 | 未成立 | 新缺口→真实搜索→真实LLM修改→原生补保护→历史无退化→冻结新测试；任一环节失败明确定位 | 完整轨迹与最终报告 |

## 预算、数据隔离与口径

- 模型服务由 native 子任务独占，所有真实调用保存原始输入输出和usage；其他任务不并发调用模型。
- 四法初始预算为4方法×2种子×6查询，每查询correct+4人工故障，共48查询/240次native执行；编译和执行成本分别记录，实际运行以配置/账本为准。
- 原生消融初始预算为公共初始候选1调用、最多1次接口修复、四臂各1次修改；额外调用必须单列，不冒充相同预算。
- 旧实验全部视开发数据。本轮搜索证据是实验处理，只给B/D；公共规格、初始候选与工具接口一致。
- 每条target必须由独立事务oracle确认，波形差异本身不计违例。相同缺口的波形变体只计重复。
- 单元资格检查不算真实机制实验。工程候选不算模型生成。人工故障不算上游历史Bug。仿真通过不算形式证明。
- 接受门仅保证已重放证据上的历史保护；native前件cover也不能证明性质逻辑相关性或全局不退化。

## 可执行入口

资格检查：`wsl -- python3 scripts/research15_acceptance_qualification.py --out deliverables/research15_integration_20261015_r01/gate_qualification.json`。
其他命令随实际CLI和运行记录补入本轮报告，不复写上一轮报告。
