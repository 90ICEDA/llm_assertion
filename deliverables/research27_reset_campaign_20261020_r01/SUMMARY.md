# 背压解除边界与复位后无请求输出：本轮实测汇总

本轮沿用已冻结真实模型断言集合，执行新模型细化；没有重新生成初始集合。真实 axis_fifo RTL 加明确人工输出边界故障，父案例分母为 1。完整五义务保护和原始历史 Bug 修复均未建立。

服务请求、模型响应、接口组装、原生执行和接受分别记录；接口拒绝不是原生违例，中止后的部分回放不作为验收。有限仿真未发现问题不等于形式证明；历史保护保持仅限已回放证据。

| 运行 | 终态 | 后端/模型 | 实际调用 | 新接受编辑 | 新目标链 | 独立测试 |
|---|---|---|---:|---:|---|---|
| deliverables/research27_closed_loop_20261020_r01 | development_partial | qwen2.5-coder:7b-instruct | 2 | 0 | False | completed |
| deliverables/research27_closed_loop_20261020_r02 | development_partial | qwen2.5-coder:7b-instruct | 2 | 0 | False | completed |
| deliverables/research27_closed_loop_20261020_r03 | execution_interrupted_during_model_load |  | 0 | 0 | False | not_completed |
| deliverables/research27_closed_loop_20261020_r04 | execution_interrupted_during_model_load |  | 0 | 0 | False | not_completed |
| deliverables/research27_closed_loop_20261020_r05 | development_partial |  | 0 | 0 | False | completed |
| deliverables/research27_closed_loop_20261020_r06 | development_resolved | qwen/qwen-2.5-72b-instruct | 2 | 1 | True | completed |

模型或后端不同不能作为受控算法消融比较；多次失败全部保留，不挑选成功结果。

离线词法 schema 检查与服务后端 grammar 执行分开；历史后端拒绝约束后仍返回文本的情况，不能只当成模型未遵守格式。后端没有报错也仅表示该调用日志未见错误。

## 两项重点问题的独立回放

下表为各运行冻结后本批输入的去重统计，不混成一个共享测试集；旧公开测试进入开发数据后不得再次计为独立。

### deliverables/research27_closed_loop_20261020_r01

| 候选 | 义务 | 目标行 | 检出 | 漏报 | 误报 | unknown | 触发 |
|---|---|---:|---:|---:|---:|---:|---:|
| core | stall_stability | 10 | 10 | 0 | 0 | 0 | 152 |
| core | no_unsolicited_output | 7 | 5 | 2 | 0 | 0 | 432 |
| core | reset_cancellation | 8 | 6 | 2 | 0 | 0 | 433 |
| initial | stall_stability | 10 | 10 | 0 | 0 | 0 | 152 |
| initial | no_unsolicited_output | 7 | 5 | 2 | 0 | 0 | 432 |
| initial | reset_cancellation | 8 | 6 | 2 | 0 | 0 | 433 |

实际冻结哈希：`696baa1749a9e317abc8e730f3d42daa274f4aeb3f64f24816f15a1fd911c230`。后续归因 unknown：{'core': 157, 'initial': 157}。

完整原始 SVA、提案原文、相邻样本、历史门控和接受/拒绝轨迹：[本运行报告](../research27_closed_loop_20261020_r01/report/REPORT.md)。

### deliverables/research27_closed_loop_20261020_r02

| 候选 | 义务 | 目标行 | 检出 | 漏报 | 误报 | unknown | 触发 |
|---|---|---:|---:|---:|---:|---:|---:|
| core | stall_stability | 9 | 9 | 0 | 0 | 0 | 136 |
| core | no_unsolicited_output | 6 | 4 | 2 | 0 | 0 | 446 |
| core | reset_cancellation | 6 | 4 | 1 | 0 | 1 | 445 |
| initial | stall_stability | 9 | 9 | 0 | 0 | 0 | 136 |
| initial | no_unsolicited_output | 6 | 4 | 2 | 0 | 0 | 446 |
| initial | reset_cancellation | 6 | 4 | 1 | 0 | 1 | 445 |

实际冻结哈希：`696baa1749a9e317abc8e730f3d42daa274f4aeb3f64f24816f15a1fd911c230`。后续归因 unknown：{'core': 196, 'initial': 196}。

完整原始 SVA、提案原文、相邻样本、历史门控和接受/拒绝轨迹：[本运行报告](../research27_closed_loop_20261020_r02/report/REPORT.md)。

### deliverables/research27_closed_loop_20261020_r03

未完成独立测试；不能记作零漏报。

### deliverables/research27_closed_loop_20261020_r04

未完成独立测试；不能记作零漏报。

### deliverables/research27_closed_loop_20261020_r05

| 候选 | 义务 | 目标行 | 检出 | 漏报 | 误报 | unknown | 触发 |
|---|---|---:|---:|---:|---:|---:|---:|
| core | stall_stability | 8 | 8 | 0 | 0 | 0 | 196 |
| core | no_unsolicited_output | 5 | 4 | 1 | 0 | 0 | 458 |
| core | reset_cancellation | 5 | 4 | 1 | 0 | 0 | 458 |
| initial | stall_stability | 8 | 8 | 0 | 0 | 0 | 196 |
| initial | no_unsolicited_output | 5 | 4 | 1 | 0 | 0 | 458 |
| initial | reset_cancellation | 5 | 4 | 1 | 0 | 0 | 458 |

实际冻结哈希：`696baa1749a9e317abc8e730f3d42daa274f4aeb3f64f24816f15a1fd911c230`。后续归因 unknown：{'core': 193, 'initial': 193}。

完整原始 SVA、提案原文、相邻样本、历史门控和接受/拒绝轨迹：[本运行报告](../research27_closed_loop_20261020_r05/report/REPORT.md)。

### deliverables/research27_closed_loop_20261020_r06

| 候选 | 义务 | 目标行 | 检出 | 漏报 | 误报 | unknown | 触发 |
|---|---|---:|---:|---:|---:|---:|---:|
| core | stall_stability | 9 | 9 | 0 | 0 | 0 | 152 |
| core | no_unsolicited_output | 6 | 6 | 0 | 0 | 0 | 391 |
| core | reset_cancellation | 7 | 7 | 0 | 0 | 0 | 392 |
| initial | stall_stability | 9 | 9 | 0 | 0 | 0 | 152 |
| initial | no_unsolicited_output | 6 | 4 | 2 | 0 | 0 | 391 |
| initial | reset_cancellation | 7 | 4 | 2 | 0 | 1 | 391 |

实际冻结哈希：`0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1`。后续归因 unknown：{'core': 160, 'initial': 160}。

完整原始 SVA、提案原文、相邻样本、历史门控和接受/拒绝轨迹：[本运行报告](../research27_closed_loop_20261020_r06/report/REPORT.md)。

真实接受轨迹 `core/v1`，目标 `['no_unsolicited_output', 'reset_cancellation']`：

```systemverilog
mready && mvalid |-> (ref_count > 0 && mdata == ref_expected)
```

开发回放：`{'rows': 69124, 'unknown': 3, 'triggers': 16466, 'false_positives': 0, 'detections': 195, 'misses': 16, 'count_unit': 'obligation-by-sampled-cycle evidence rows, not independent discoveries or transactions', 'later_attribution_unknown': 1177}` → `{'rows': 69124, 'unknown': 0, 'triggers': 16469, 'false_positives': 0, 'detections': 214, 'misses': 0, 'count_unit': 'obligation-by-sampled-cycle evidence rows, not independent discoveries or transactions', 'later_attribution_unknown': 1177}`；门控记录：`{'accepted': True, 'gate_enforced': True, 'reasons': []}`。独立结果须以上表为准，开发接受不自动表示独立通过。

背压新增的数据保持性质没有增加 valid 保持检查；复位性质采用 $past 队列计数时，不能将有限样本通过视为与当前拍未取消事务存在性的规范等价。缺少排空目标分母也不能算保护通过。

## 实际成本（互不重复）

| 类别 | 模型请求 | 输入 tokens 已知小计 | 输出 tokens 已知小计 | 用量未知请求 | 编译 | 执行 | 形式化 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 本轮运行 | 6 | 64668 | 852 | 0 | 48 | 2016 | 0 |
| 本轮资格检查 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 此前中止尝试（单列） | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

编译 smoke 执行包含在执行次数内。不同类别目录重复会被拒绝；不递归加入运行报告内的来源成本。输入/输出用量缺失保持不可用。模型管理/服务加载和实际生成分开，不将模型服务可用等同于生成成功。

## 未完成与范围限制

- 完整五义务语义保护、全局无退化及形式证明未建立。
- 本轮没有受控四组消融或搜索基线优势结论。
- stat 及原始 FIFO presented 仍 unknown；仅人工边界故障工程案例计入当前分母。
- 独立失败若用于以后修改，须转开发数据并另建新独立测试。
