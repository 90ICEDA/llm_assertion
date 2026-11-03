# Trace 与 RTL context 机制分析（Final46）

## 实验口径

- 分析单位是 **parent bug**，共 46 个；同一 parent 的 trace variant 和 4 个候选不作为独立样本。
- 3 个模型（GPT、Claude、Qwen），每个模型×parent×机制生成 4 个候选；主指标是 parent 上“4 个候选至少 1 个成功”。
- Trace 共 17 个机制、9,384 条候选记录；RTL context 共 9 个机制、4,968 条候选记录。唯一键审计后缺失 0、重复 0。
- 显著性采用模型内、parent 配对的 exact McNemar；未校正多重比较，因此 `p<0.05` 应理解为探索性证据。效应量为配对成功率差（百分点）。

## 结论摘要

### 1. Trace：good+bad 是总体最稳的输入，单边 trace 会丢掉互补信息

三模型平均 parent 成功率：good+bad 44.9%，bad only 37.7%，good only 34.1%。Claude 上证据最清楚：bad only 比 good+bad 低 13.0 个百分点（25/46 对 31/46，p=0.031），good only 低 15.2 个百分点（24/46 对 31/46，p=0.016），且都没有新增成功 parent。具体丢失包括 case451、case480、case491、case494；good only 还丢失 case458、case492、case498。

GPT、Qwen 上单边输入差距未显著，且存在少量交换：例如 GPT bad only 新增 case468/case480/case498，但丢失 case478/case491/case497/case502/case510。这说明正反例的价值不是简单相加；good trace 约束“不要过强”，bad trace 提供触发和差异方向，两者共同降低 overfit/vacuity。

### 2. Window、signal subset、噪声与格式主要表现为模型敏感性，不是稳定主效应

- format perturbation 平均 42.8%，最接近原始 good+bad 的 44.9%；三模型均不显著。GPT 甚至新增 case462/case494/case498/case499，同时丢失 case478/case484/case502，说明模型对表面格式存在 case-level 抖动，但没有系统性崩溃。
- local window 平均 38.4%；Claude 低 10.9 个百分点（p=0.063，仅趋势），丢失 case458/case478/case480/case491/case502。局部窗口会去噪，也会删除建立延迟/持续时间所需的远程上下文。
- signal subset 平均 36.2%；GPT 低 15.2 个百分点（p=0.065，仅趋势），丢失 case491/case492/case497/case502/case510 等时序 case，但新增 case451/case458。信号裁剪对上下文噪声与信息删除同时起作用。
- noise signals 平均 39.9%，三模型均不显著。GPT 净差为 0，却新增 case451/case458/case494/case495/case498、丢失 case474/case484/case492/case502/case510，表明“平均不变”掩盖了明显的 per-case 重排。
- wrong pairing 平均 41.3%，三模型均不显著。它接近 baseline 不意味着配对无用：GPT 新增 case468/case494/case495/case498，同时丢失 case484/case497/case502/case505/case510；当前错误配对只旋转 bad trace 一步，仍保留大量边际波形信息，所以它是偏保守的负对照。

### 3. Temporal abstraction 的主要风险是错误/缺失 trigger，其次是 delay、duration、polarity 被错误消费

完整 temporal abstraction 平均成功率 31.9%，低于 raw good+bad 的 44.9%。GPT 低 15.2 个百分点（12/46 对 19/46，p=0.016），Claude 低 21.7 个百分点（21/46 对 31/46，p=0.002）；Qwen 差距不显著，且出现 3 个 temporal-only case。

信息删除中，no-trigger 最差（平均 27.5%）：GPT 低 21.7 个百分点、丢失 10 个且新增 0（p=0.002）；Claude 同样低 21.7 个百分点、丢失 10 个且新增 0（p=0.002）。case491 的 temporal 候选全部 vacuous，直接体现抽象后的 antecedent 没有命中；case466 的 8 个 raw/temporal 候选都使用未命中的 accepted-write-and-advance trigger，是 trigger→vacuity 的典型链条。

delay 删除也造成稳定损失：GPT -17.4pp（p=0.021），Claude -19.6pp（p=0.004）。case451 需要注册后的 `|=> timeout_o`；case458 需要 `load_i |=> !overflow_o`；case510 需要 `flush_i&&push_i |=> !valid_o`。抽象把这些关系折成 same-cycle 时会变成 too weak 或 too strong。

duration/polarity 删除在 Claude 上分别 -17.4pp（p=0.008）和 -17.4pp（p=0.008）；GPT/Qwen 上方向不稳定。case471 展示 duration 的模型依赖：Qwen temporal-only，因为抽象保住 ack pulse 关系；Claude raw-only，因为 temporal 候选过约束或 vacuous。case497 展示 polarity：GPT temporal 候选错误使用 `$fell(async_ack_i)`，而目标由 rising ack 触发，结果全部 vacuous。case495 同时混合 duration、polarity 与不支持的延迟语法。

严格删除并未形成简单单调退化，说明模型会从剩余文本重新推断甚至“补回”字段。例如 Claude strict-no-trigger 偶然恢复 case455，但仍净丢 7 个 parent（-15.2pp，p=0.039）；Qwen strict-no-delay 反而达到 28.3%，高于 temporal full 23.9%。因此字段消融衡量的是“提示中显式信息 + 模型重建行为”，不能解释为纯粹的信息论贡献。

### 4. RTL：two-hop slice 有方向性优势，但随机 slice 对照否定了强语义因果解释

三模型平均 parent 成功率：two-hop slice 38.4%，interface/legacy slice/random slice 都是 34.8%，full RTL 34.1%，signal list+two-hop 34.1%，one-hop 31.2%，wrong signal list 26.8%，signal list 26.1%。

two-hop 相对 full RTL：GPT +8.7pp（新增 case471/case491/case492/case494/case497/case510，亦有丢失，p=0.289）；Claude +4.3pp（新增 case462/case468/case491/case492/case497，p=0.727）；Qwen 0。均不显著，只能称趋势。

关键反证是 random slice：平均 34.8%，与 full RTL 几乎相同，并在 GPT 上新增 case471/case495/case497/case499/case505。因此“减少上下文长度/改变采样”本身就能带来收益，不能把 two-hop 的方向性提升全部归因于依赖相关性。case468 的 temporal-only 结果以及 RTL two-hop 在 Claude 上恢复该 case，均支持上下文噪声可能存在，但证据仍是 case-specific。

signal list 单独使用最弱之一；Claude -13.0pp（p=0.070，仅趋势），说明名字缺少赋值关系和状态转移信息。signal list+two-hop 可恢复到与 full RTL 相当，Claude 甚至 +4.3pp，表明 signal list 更适合做检索先验，而不是独立上下文。

wrong signal list 在 Claude 上显著低于 full RTL 19.6pp（15/46 对 24/46，p=0.012），丢失 case451/case471/case474/case482/case494/case500/case505/case507/case508/case509，只偶然新增 case502。这是“相关信号身份确有价值”的最强证据；但 GPT/Qwen 未复现，因此仍需跨 seed 验证。

## Raw–temporal 四象限

| 模型 | 两者成功 | raw 成功 / temporal 失败 | temporal 成功 / raw 失败 | 两者失败 |
|---|---:|---:|---:|---:|
| GPT | 12 | 7 | 0 | 27 |
| Claude | 21 | 10 | 0 | 15 |
| Qwen | 8 | 4 | 3 | 31 |
| 合计 | 41 | 21 | 3 | 73 |

raw-only 21 个模型×case，主要说明 temporal 文本会把正确的 trigger/delay/polarity/duration 消费错：case451、458、491、497、510 都有成功 raw candidate 作为正证据。temporal-only 只有 Qwen 的 case468、471、510：分别对应上下文去噪、pulse duration 抽象、恢复 next-cycle delay。两者都失败的 73 个单元不是单一原因；典型包括 case466（trigger 未命中→vacuity）、case482（复制观测组合→hardcoding/vacuity）、case493（same-cycle too strong + temporal 编译形式失败）、case495（duration/polarity/compile form 混合）。

## 人工 failure analysis（全量 97 个非双成功模型×case）

人工复核现已覆盖全部 97 个非双成功模型×case（38 个不同 parent）：raw-only 21/21、temporal-only 3/3、both-fail 73/73。主标签分布为 delay 51、trigger 24、duration 10、polarity 5、hardcoding 4、context noise 2、vacuity 1；次标签为 vacuity 33、compile form 28、too weak 16、too strong 15，另有 trigger/context noise/polarity/delay。每条均保留 golden relation、raw/temporal 四候选 outcome、判断依据和成功控制臂，见 `manual_failure_analysis.csv`。

| 机制链条 | 具体 case 证据 |
|---|---|
| trigger → vacuity | case491（GPT temporal 四候选全 vacuous）；case466（两种表示全部 antecedent 未命中） |
| delay → same-cycle too weak/strong | case451、case458、case510；raw 的 `|=>` 成功而 temporal same-cycle 失败 |
| polarity → vacuity/错误方向 | case497 使用 `$fell(async_ack_i)` 而目标为 rising ack；case455 Qwen 反转 CRC 外部极性 |
| duration 被保留或丢失 | case471 对 Qwen 有益、对 Claude 有害；case495 把精确两拍约束压成 same/next-cycle |
| context noise | case468 Qwen temporal-only；压缩后的 ordering relation 避免 raw antecedent 被波形细节带偏 |
| too strong | case493 raw 强制同周期状态改变；case471 raw 候选拒绝正确行为 |
| hardcoding | case482 复制 selector/ready 观测组合；case466 部分候选硬编码 step 值 |

## 可解释范围与限制

- 每个控制臂是一次固定 seed/temperature 的生成，生成随机性会造成 gained/lost 交换；当前 McNemar 只控制了 parent 配对，没有把模型调用随机性消除。
- 比较数量较多，p 值未做 multiplicity correction；最稳健的判断应看“方向、显著性、跨模型复现、具体 case 机制”四者是否一致。
- 97 个非双成功模型×case 已全部逐项人工复核；`failure_analysis_review_packet.csv` 与 `manual_failure_analysis.csv` 均为全覆盖，后者包含最终人工主/次标签和证据句。
- 当前证据支持：保留 good+bad；temporal 必须显式、可验证地保留 trigger/delay；RTL 优先 two-hop 作为候选上下文，但必须保留 random slice 对照，不能声称已证明语义切片因果增益。
