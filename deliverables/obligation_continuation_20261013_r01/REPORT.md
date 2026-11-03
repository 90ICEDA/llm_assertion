# 设计义务指导搜索与断言细化：续作结果

本轮完成可执行的剩余实验，包括接口修复、40条逐项续诊、31条局部最小化、stat 修正对照、完整四组细化、新隔离验收，以及 Ibex #54 真实历史生成／修复对照。实验完成不等于断言验收通过；没有父 bug 整体验收通过，也不据局部命中宣称 D 总体优于对照。

## 范围与冻结

沿用历史648次主查询、72次补充查询和11/11反馈碰撞复现，不重做无关部分。旧三法均局部区分9/11对；filter自然池仍仅1/3可执行，未改池或冒称自然分歧目标有效。旧FIFO最终误报39/0/19/39仍为历史记录。新stat控制单独版本；108次必要补查得到11/11/11个缺口，旧13/13/8保留且不混计。

同一模型 qwen2.5-coder:7b-instruct，同一digest、温度0、种子20261013、384输出token、420秒超时、无重试；每父每臂2次模型调用、14次实际开发查询。A/B/C/D共同初始检查和每次修改后合法／违例回归不变。A固定补测与旧反馈；B普通变异搜索FP/FN；C义务查询且主动FN；D义务查询FP/FN。查询获得的信息按臂隔离。单个模型种子、两轮预算不支持总体统计优越性结论。

原三个人工父案例使用自然候选；其18条新保留输入、3个人工同类故障在正式细化前冻结。Ibex另外6条保留序列，64种新低16位编码，与开发及历史223条向量无编码交集；HINT架构等价不计为新独立bug。仅通过明确JSON接口发送公开契约和各臂开发反馈；私有监视器、补丁、保留输入及答案不发送。最终版本固定选择第二轮最后可执行提案，验收后未修断言。

## 接口、诊断与工具

Ibex共享初始生成共4次真实调用。v1的3次调用均因模型使用未声明imm6/bit12而正确拒绝，属于候选错误，该区块按预算结束失败。另建v2，只要求生成一条断言并强调概念字段名不是端口，同一模型生成首个可执行结果；所有组共享这个新候选。全部失败与初始生成成本单独保留，正式每组2次调用不变。

10次历史接口拒绝均来自公开复位标量的权限遗漏；原提案不改写后23/23有响应提案可编译执行。1次180秒历史超时无响应和token，无法证明是服务故障还是资源耗尽。现有请求JSON、流式响应、AST提取、编译、执行、反馈、成本记录经3次真实调用全链预检；预检不混入正式结果。候选不支持的点号内部信号语法仍拒绝，不放宽语义制造成功。

31条见证均做到固定最初两拍复位、原目标和触发身份下的单样本删除局部最小；117次尝试＝60次物理执行＋57次显式缓存复用。输入值未最小化，不宣称全局最短。9条无语义见证逐条映射到48次分支执行尝试（24次filter静态语法拒绝、24次intr执行）及4次额外可达性配对查询：filter记录属于不支持语法，intr八条仍受采样规格限制。

spill invalid-payload与intr mask采样按用户明确决定保持未决；分别保存条件结果。RTL现状不替代规格。原生工具重新探测发现 Windows ModelSim 10.4 可编译探针，但推进时间即终止，不含断言的基准同样失败；因此属于执行环境限制。Icarus原生SVA语法探针失败；过程checker资格检查及异步历史复位检查完成，不能称原生SVA交叉验证完成。

## 逐父案例诊断与验收状态

| 父案例 | 原已知失败 | 原未知 | 局部最小见证 | 本轮状态 |
|---|---:|---:|---:|---|
| onehot | 0 | 0 | 0 | 历史范围保留；本轮无新增细化 |
| filter | 7 | 1 | 7 | 完整四组与独立验收已执行；整体通过未建立 |
| fifo | 8 | 0 | 8 | 完整四组与独立验收已执行；整体通过未建立 |
| spill | 0 | 8 | 8 | 条件实验完成，规格未决 |
| stat | 8 | 0 | 8 | 完整四组与独立验收已执行；整体通过未建立 |
| intr | 0 | 8 | 0 | 条件实验完成，规格未决 |
| ibex | 0 | 0 | 0 | 完整四组与独立验收已执行；整体通过未建立 |

intr条件检查：

| RTL版本标签 | 条件解释 | 违例/检查 |
|---|---|---:|
| buggy | same_sample_mask | 144/156 |
| buggy | registered_mask | 120/132 |
| correct | same_sample_mask | 36/156 |
| correct | registered_mask | 0/132 |

spill全部8次运行的共同valid义务无违例；无效数据总线改动在raw-zero假设下产生差异，详见conditional_results.json。此处的correct/buggy只是版本标签，不是独立正确性结论。

## 独立验收：最终断言

FP分母为合法前缀采样；首次／后续FN分母为独立监视器判定的目标违例事件。此前已误报或未确认事务归属的fail-hit只进入“归属未知”，不算成功保护。相同合法控制在两个人工故障队列重复，不应相加为新的独立样本。

| 父案例 | 队列 | 组 | FP/合法拍 | 首次FN/目标 | 后续FN/目标 | 因果确认检测 | 归属未知 |
|---|---|---|---:|---:|---:|---:|---:|
| fifo | new_artificial_sibling | A | 0/168 | 0/18 | 0/64 | 18 | 64 |
| fifo | original_target | A | 0/168 | 16/16 | 16/16 | 0 | 0 |
| fifo | new_artificial_sibling | B | 0/168 | 0/18 | 0/64 | 18 | 64 |
| fifo | original_target | B | 0/168 | 16/16 | 16/16 | 0 | 0 |
| fifo | new_artificial_sibling | C | 0/168 | 0/18 | 0/64 | 18 | 64 |
| fifo | original_target | C | 0/168 | 16/16 | 16/16 | 0 | 0 |
| fifo | new_artificial_sibling | D | 82/168 | 18/18 | 64/64 | 0 | 0 |
| fifo | original_target | D | 82/168 | 2/16 | 0/16 | 0 | 30 |
| filter | new_artificial_sibling | A | 131/168 | 0/18 | 0/53 | 0 | 71 |
| filter | original_target | A | 131/168 | 0/18 | 0/34 | 0 | 52 |
| filter | new_artificial_sibling | B | 131/168 | 0/18 | 0/53 | 0 | 71 |
| filter | original_target | B | 131/168 | 0/18 | 0/34 | 0 | 52 |
| filter | new_artificial_sibling | C | 131/168 | 0/18 | 0/53 | 0 | 71 |
| filter | original_target | C | 131/168 | 0/18 | 0/34 | 0 | 52 |
| filter | new_artificial_sibling | D | 131/168 | 0/18 | 0/53 | 0 | 71 |
| filter | original_target | D | 131/168 | 0/18 | 0/34 | 0 | 52 |
| stat | new_artificial_sibling | A | 98/168 | 0/12 | 0/6 | 0 | 18 |
| stat | original_target | A | 98/168 | 0/18 | 0/76 | 0 | 94 |
| stat | new_artificial_sibling | B | 120/168 | 0/12 | 0/6 | 0 | 18 |
| stat | original_target | B | 120/168 | 0/18 | 0/76 | 0 | 94 |
| stat | new_artificial_sibling | C | 98/168 | 0/12 | 0/6 | 0 | 18 |
| stat | original_target | C | 98/168 | 0/18 | 0/76 | 0 | 94 |
| stat | new_artificial_sibling | D | 110/168 | 0/12 | 0/6 | 0 | 18 |
| stat | original_target | D | 110/168 | 0/18 | 0/76 | 0 | 94 |
| ibex | real_historical | A | 0/174 | 12/12 | 54/54 | 0 | 0 |
| ibex | real_historical | B | 0/174 | 12/12 | 54/54 | 0 | 0 |
| ibex | real_historical | C | 0/174 | 12/12 | 54/54 | 0 | 0 |
| ibex | real_historical | D | 0/174 | 12/12 | 54/54 | 0 | 0 |

## 主要配对比较

D−B为因果确认义务种数差；不是整体必要义务通过数。D−C为误报拍数差，正数表示D更差。每行6对保留场景。

| 父案例 | 队列 | D−B义务种数 | D独有 | B独有 | D−C误报 |
|---|---|---:|---|---|---:|
| fifo | new_artificial_sibling | -1 | 无 | nonempty_when_present | 82 |
| fifo | original_target | 0 | 无 | 无 | 82 |
| filter | new_artificial_sibling | 0 | 无 | 无 | 0 |
| filter | original_target | 0 | 无 | 无 | 0 |
| ibex | real_historical | 0 | 无 | 无 | 0 |
| stat | new_artificial_sibling | 0 | 无 | 无 | 12 |
| stat | original_target | 0 | 无 | 无 | 12 |

初始到最终的全部配对变化见 `delivery/initial_final_deltas.json`。FIFO的A/B/C在新同类故障上从0增加到18次因果确认检测，合法误报从136降至0；原始目标仍有首次16次、后续16次漏报，不能称FIFO整体修好。filter没有改善；stat各组误报均高于初始60次，未建立保护增益。

逐次修改对全部已取得开发输入的回归见 `delivery/regression_protection.json`；明确保存新增误报及丢失的已确认因果保护，不将此前的误报屏蔽误当作保护。各义务／分支漏报、因果确认及归属未知见 `*_acceptance_detail.json` 的obligation_results；前件零触发单列untriggered_variant_assertions，不计空洞通过。

## 实际模型成本

未知tokens不记零；耗时为调用耗时之和，不是并行任务的总历时。编译、仿真、周期和失败成本另见physical_costs.json。

| 阶段 | 调用 | 状态 | 已知输入tokens | 已知输出tokens | tokens不可得调用 | 秒 |
|---|---:|---|---:|---:|---:|---:|
| formal | 24 | {'parsed': 24} | 71268 | 3860 | 0 | 2191.50 |
| historical_formal | 8 | {'candidate_language_error': 2, 'parsed': 6} | 21980 | 3032 | 0 | 817.21 |
| historical_generation_failed_v1 | 3 | {'candidate_language_error': 3} | 2967 | 804 | 0 | 144.36 |
| historical_generation_v2 | 1 | {'parsed': 1} | 795 | 103 | 0 | 36.81 |
| preflight | 3 | {'parsed': 3} | 3395 | 506 | 0 | 174.95 |

## 最小复现与日志入口

stat原始19/73复现：从仓库根目录运行 `sh deliverables/obligation_completion_audit_20261013_r01/replays/stat_overlap/reproduce.sh`。两拍复位后t2输入19、t3输入73，t4应输出19而旧RTL输出73。新对照见 `stat_control/patch.diff` 与 `runs/stat_control/19_73/stat/correct/reproduce.sh`；补丁属于本研究人工修复，不冒充真实历史提交。每笔事件按触发时捕获长度，期限trigger+2，复位取消，重叠分别配对。

最终FIFO B/D最小对照：两拍复位后push=1、pop=0、data=199，合法控制empty=0；新同类故障错误输出empty=1。B接受合法控制并报出目标违例，D反而误报合法控制。见 `final_examples/fifo_B_D.json`；运行 `sh deliverables/obligation_continuation_20261013_r01/runs/final_examples/fifo_B/fifo/buggy/reproduce.sh`。这2次配对查询是已消耗保留集的说明性复现，不是新增独立泛化证据。

逐条最小复现命令、输入、原见证、缩减见证、波形、逐周期独立判定及成本映射见 `delivery/problem_ledger.json`、`minimization/index.json`。义务来源及必要分支见 `frozen/*/contract.json`；新验收的义务／分支明细见 `delivery/*_acceptance_detail.json`，逐轮回归见两个区块的 `postfreeze_regression/`。

真实历史：`historical_formal/` 保存 Ibex #54来源、修复前后原始RTL、原始回归引用、独立旗标监视器资格检查、共享模型生成初始候选、8次正式调用、保留验收。生成器只见公开ISA契约和端口，不见修复补丁。范围为五类RV32C指令的合法性／压缩标志；解码数据补丁的原始回归单独保留，不宣称全ISA保护。

协议与哈希：`formal/freeze.json`、`historical_formal/freeze.json`及各自`final_freeze.json`。所有模型请求／响应、接口错误、候选修改、查询及回归均保留；`delivery/model_costs.json`、`physical_costs.json`按阶段分别计账。人工澄清2问、1条答复，人工耗时不可得。

## 完成状态与剩余外部条件

可执行的四组与真实案例实验已完整执行；方法失败、退化和未知照实保留。未完成的是可工作的原生SVA执行交叉验证，以及未决规格下的无条件验收；所需最小输入分别是能运行noassert.sv的原生工具环境、正式spill/intr规格决定。用户已要求后两项保持未决，故本轮不再请求擅定。没有以人工修复替代模型结果，也没有因结果不理想停止某组。

重建统计：从仓库根目录运行 `python3 scripts/obligation_continuation_delivery.py deliver --output-name rebuilt_01`；输出到新的目录，不覆盖封存报告。历史封存完整性见 `historical_integrity.json`。主实验脚本分别为 `obligation_continuation_experiment.py`、`obligation_ibex_experiment.py`；新实验须使用新的run编号，避免覆盖。
