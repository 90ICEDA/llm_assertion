# 人工可分性盲审

## 冻结协议

- 60 个当前二值 FP/TP 签名完全相同的候选对：30 个 parent 各 2 对。
- 20 个隐藏 control：分布在 20 个不同 parent。
- 总计覆盖 30 个 parent、29 个 bug family；每个 parent 最多 3 对。
- 单对上限 8 分钟。
- 审查时隐藏 candidate 来源、输入表示、probe strategy、当前分类和 control 身份；80 条记录全部冻结后才连接 sealed map。
- 保留 SVA/PropertyIR、接口信号、clock/reset、RTL/TB 路径和原环境约束。

## 结果

| 解封后的类别 | n | 成功 | 失败 |
|---|---:|---:|---:|
| 当前 FP/TP 签名相同 | 60 | 34 | 26 |
| 隐藏 control | 20 | 20 | 0 |

54 个成功案例均满足：candidate checker 与 probe 已编译执行、没有增加 assumption、现有仿真到达触发/失败场景、A/B verdict 或 fail-hit 行为不同，并保存 probe、两侧 result 和原始 replay command。

34 个“签名相同但人工可分”的成功并非二值 FP/TP verdict 翻转，而主要是同一合法 probe 下 fail-hit 数不同。这说明当前签名把 `fail_hits > 0` 压缩为布尔 FP/TP 后丢失了可解释的行为差异。它们不应继续表述为“行为完全相同”，更准确的说法是“当前二值 FP/TP set 相同”。

## 失败保留

| Failure reason | n |
|---|---:|
| suspected_equivalent_in_current_scope | 10 |
| scenario_unreachable | 9 |
| difference_visible_but_no_legal_input_constructed | 7 |

失败没有被删除或改写为成功。矛盾 antecedent 被记为不可达；有明显 SVA 语义差异但没有合法 stimulus witness 的对，保留为“能看出差异但无法构造合法输入”；只有 antecedent、implication 和 consequent scope 高度重合且没有 witness 的对才标为“怀疑当前 scope 等价”，不声明已证明等价。

## 解释边界

成功 witness 来自冻结 common legal probe pool，并复制为独立可重放证据包；没有读取原 random/disagreement policy 顺序，也没有在审查阶段读取 control/equal 标签。因而本轮直接检验的是“现有二值签名是否掩盖更细行为差异”，不是对 26 个失败对完成无界等价证明。后续若要继续区分这 26 对，应优先为 7 个 visible-difference 对人工编写新 stimulus，再对 10 个 suspected-equivalent 对做有界等价/互蕴证明。
