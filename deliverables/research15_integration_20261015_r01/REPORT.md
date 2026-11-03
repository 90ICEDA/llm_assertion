# 2026-10-15 实际完成情况与续作结果

**整体任务尚未完成，期待的完整证据链尚未成立。** 本轮实际修改代码、调用本地模型、运行原生SVA和复杂FIFO搜索，并新增历史RTL复现。负结果、unknown及未执行项均保留。

## 完成矩阵

| 要求 | 状态 | 实际结果及限制 |
|---|---|---|
| 真实LLM→原生SVA反馈链 | 已运行，未通过 | 3次真实模型生成/修改均原生编译执行并拒绝；无可接受最终版本。 |
| 契约反馈驱动四法搜索 | 已验证有限运行，负结果 | 48查询/240原生回放；首个真实候选固定；无可导出的有效tail-loss细化见证。 |
| 原11对候选四法对比 | 此前已运行，本轮复用 | 旧36/37/43/43独立候选缺口；不是本轮原生结果，无总体优势结论。 |
| 多SVA义务证据库/接受门 | 已实现与定向资格检查，完整机制未验证 | 12个门检查+13个适配器检查；实际模型版本无历史有效保护可供完整集合细化验收。 |
| 复杂FIFO及复位取消 | 已验证有限工程范围 | 本轮Depth2与Depth5(实际8)、pipeline0/1；明确人工reset residue和tail loss故障，不能计原始presented bug成功。 |
| 原生四组消融 | 仅实现，尚未执行 | 缺少通过资格检查的公共初始候选，且严格搜索treatment_witness为空；旧stat过程检查器四臂不能替代。 |
| 最终冻结断言独立测试 | 尚未执行 | 没有接受版本；未生成或查看预定本轮holdout，不以历史工程测试替代。 |
| Ibex原始RTL案例 | 已验证模块级有限范围 | #166新增，#54扩展新边界；手写原生SVA/独立ISA oracle，尚未纳入LLM细化。 |
| 六原始父Bug完整保护 | 未完成，0/6已证完整成功 | stat来源接口不符；FIFO presented未见证；spill/intr部分语义unknown；其余未完成原生整体验收。 |

## 真模型初始化与修改轨迹

同一 qwen2.5-coder:7b-instruct 实际调用3次。输入包含共享RTL、人工修复前后边界RTL、规格和义务；公开参考队列是工程脚手架。前两次公共初始化预算失败后，第三次作为单列额外时序修复，不能称原预算成功。

| 版本 | 模型实际property | 合法误报 | 有效对照检出 | 首违例未检出 | 归因unknown | 结果 |
|---|---|---:|---:|---:|---:|---|
| initial | `mvalid && mready \|-> sdata == ref_expected` | 59 | 0 | 0 | 3 | 拒绝 |
| initial_semantic_repair | `mvalid && mready \|=> mdata == ref_expected` | 2 | 0 | 3 | 0 | 拒绝 |
| initial_temporal_repair | `mvalid && mready \|=> mdata == $past(ref_expected)` | 59 | 0 | 3 | 0 | 拒绝 |

每版798条“义务×采样周期”证据行，不是798笔事务或独立缺陷。第一版把当前输入sdata当输出，第二版错误使用下一拍，第三版仍下一拍并增加$past。全部可编译、可执行、有原生前件cover，却语义失败。原始第一版曾将同时误报合法对照的3个报警计检出，独立复核已更正为unknown；原始记录保留，拒绝结论不变。

原生前件cover从实际property提取，取消信任模型单独声明trigger；覆盖资格真实观察到2次触发、1次失败。12项接受门与13项适配器检查仅为逻辑资格，不算端到端成功。证据库拒绝遗漏历史记录、新FP、丢失已确认检出/触发及当前目标未修复。触发保留是有限观察代理，不能证明逻辑相关性或全局无退化。

逐版真实样本和原生失败：`evidence_examples.json`。完整模型请求/原始响应/usage、candidate.sva、TB、trace/oracle、wave.vcd、编译执行日志位于native目录。修正归属另存`native_readjudication/`，不覆写失败版本。

## 四法搜索：真实候选的负结果

4方法×2参数/种子×6查询=48查询；每查询同输入correct+4人工故障=240原生回放，另2次编译默认短执行。固定首个真实模型候选，未挑选较好的失败候选。Depth=2/pipeline=0及Depth=5/pipeline=1（RAM实际8）。所有数据均为开发数据。

| 方法 | 查询 | 同一误报类 | 独立漏报缺口类 | 对照检出事件 | 归因unknown事件 |
|---|---:|---:|---:|---:|---:|
| ordinary | 12 | 1 | 0 | 1 | 1205 |
| candidate_disagreement | 12 | 1 | 0 | 2 | 997 |
| raw_difference | 12 | 1 | 0 | 0 | 1240 |
| contract_coverage | 12 | 1 | 0 | 0 | 1053 |

全部方法都找到同一误报类。零独立漏报缺口不代表保护完整：候选误报破坏合法前缀，目标归因大量unknown。普通/分歧方法少数对照检出只是一项reset-residue/order义务上的有限现象，不消除该候选的合法误报。契约策略没有显示优势。工具/输入unknown查询为0，与上述归因unknown不是同一指标。

契约策略已按本方法历史义务检查、有效cover和检出缺口更新下一测试选择；选择前状态、反馈可见范围及原始结果均保存。442项预算/输入/冻结候选/策略状态审计通过。单property没有候选分歧对，该臂明确退化为均匀探索；不能代替旧11对完整比较。

工程资格实际验证了跨复位残留（接受5→取消28→复位解除后重现30）及四次请求丢最后一个响应的tail-loss。它们是人工边界故障，工程SVA不冒充模型产物。契约搜索的tail-loss输入确有独立oracle违例，但模型在合法对照上也报警，故`treatment_witness.json`为null，不能构造成功细化链。

## 原始历史RTL与规格审计

- Ibex #166：固定前后提交原始decoder字节与补丁吻合；115事务、458采样×3配置，每版本1374检查。before423违例/42事务，after0；两条修复义务均有代表。423不是423个Bug。
- Ibex #54：119条此前223边界+5锚点中未出现的低16编码；32条C.SLLI rd=x0 HINT before违例、after0；87条控制前后通过。另5条旧锚点单列。
- 以上使用手写原生SVA及独立ISA oracle，属于原始模块复现；尚非LLM生成断言独立验证，更不是全核或形式证明。
- stat标注的真实上游是AXI统计模块，不含本地frame_done/stat_valid四信号接口，无法确认本地两拍示例的历史映射及重叠语义。继续unknown。
- 35条历史筛选记录中其余33条未执行；FIFO presented、spill invalid-payload及intr mask/timing继续保留未确认状态。

## 成本、数据与复现

本轮模型3次全部返回：输入23274 tokens，输出272 tokens；约391.51秒，无重试。形式化调用0，金额/能耗不可用。

| 模块 | 实际编译 | 实际执行 | 编译墙时秒 | 执行墙时秒 |
|---|---:|---:|---:|---:|
| native | 4 | 10 | 39.395 | 0.175 |
| search | 3 | 250 | 33.724 | 5.407 |
| history | 4 | 4 | 67.661 | 0.076 |
| regression | 4 | 4 | 0.128 | 0.101 |

物理成本包括工程/tool资格及编译附带的短执行，查询预算另算；不把编译缓存重复收费。onehot/Depth0仅4次旧输入回归，结果一致。旧49项封存清单哈希不变。工作区无有效Git HEAD，交付源码快照以SHA256标识；首两次初始化适配器进程版本与事后源码快照不混称，详见重审记录。

统一入口（在仓库目录运行；NEW_*替换为未使用目录名）：

```powershell
wsl -- python3 scripts/research15_pipeline.py audit
wsl -- python3 scripts/research15_pipeline.py qualify
wsl -- python3 scripts/research15_pipeline.py report
wsl -- python3 scripts/research15_pipeline.py search --run NEW_SEARCH --candidate deliverables/research15_native_20261015_r01/model_calls/initial/candidate.json --budget 6
wsl -- python3 scripts/research15_pipeline.py native --run NEW_NATIVE --stage initial
wsl -- python3 scripts/research15_pipeline.py native --run NEW_NATIVE --stage qualify
wsl -- python3 scripts/research15_pipeline.py native --run NEW_NATIVE --stage temporal
wsl -- python3 scripts/research15_pipeline.py history --run NEW_HISTORY --stage prepare
wsl -- python3 scripts/research15_pipeline.py history --run NEW_HISTORY --stage run
wsl -- python3 scripts/research15_pipeline.py history --run NEW_HISTORY --stage report
```

模型命令会真实调用本地Ollama。统一调度器复用本轮实际运行模块；新调度分支未额外重复昂贵模型实验。没有shared_initial时baseline/arms应停止，不能把unqualified候选默认为接受。

## 未完成与具体阻塞

1. 真实FIFO局部order初始SVA仍未合格，三个实际模型输出分别错误处理数据身份/采样时刻；这不是凭据缺失或工具不能编译。下一阶段应针对生成接口/采样语义改进，并保持真实反馈轨迹。
2. 原生四组消融仅代码存在，尚未执行；公共初始资格失败且有效treatment为空。不能用旧stat过程检查器实验或本轮工程SVA代替。
3. 没有可接受的最终集合，所以新冻结独立测试未执行。旧全部观测属开发数据，历史119新向量不冒充学习后holdout。
4. 六原始父Bug完整保护仍0/6得到本流程确认；义务局部结果、工程故障和原始历史模块复现分开统计。通用远程模型、原生形式化和更多历史案例仍未验证。
5. 证据链停在“无法得到可接受初始模型断言/可用搜索细化见证”；尚不能证明两个机制在自动细化后保留历史有效保护并通过新独立场景。框架保持不变，不修改成功标准。
