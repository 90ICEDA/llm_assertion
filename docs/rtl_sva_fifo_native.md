# 真实模型与原生 FIFO SVA 实验

新鲜实验入口（research19，不复用旧初始候选或搜索结果）：

```powershell
wsl -- python3 scripts/research19_loop.py --out deliverables/research19_repro_new --contract-planning --native-profile --max-refinement-calls 2 --max-model-calls 12
wsl -- python3 scripts/research19_report.py --run deliverables/research19_repro_new
wsl -- python3 scripts/research19_report.py --run deliverables/research19_repro_new --verify
```

该入口使用已有本地模型，必要时启动 Ollama。模型先输出简短适用条件理由，再生成文本表达式；程序只做语法组装，不替换谓词。反馈优先展示目标义务的实际同周期正确/故障采样，然后给出合法控制误报和历史概要。初始候选仍明确限定为 `order_payload`，属于受控局部候选。

所有 research16–18 数据作为已见开发材料。新运行重新生成初始 SVA、执行搜索，并在所有实际执行的 core/消融候选冻结后才生成一批共享独立测试。活动运行不能生成报告；原生拒绝和 unknown 不按通过处理。本轮 research19 的 r01–r05 均保留；最终续跑为 `deliverables/research19_closed_loop_20261016_r05`，结果以各自 `outcome.json` 和终态报告为准。

若本次入口启动了服务，`service/server.log` 在服务运行期间可能继续变化。归档前应停止本次自行启动的服务或先建立不再变化的日志快照，再生成与核验产物清单；不得把仍在写入的日志声称为不可变版本。

可选扩展：`--contract-planning` 增加一次真实契约分析调用，分析原文交给完整 RTL 生成请求，两个调用均计费。`--native-profile` 开启已经原生 assert/cover 资格测试的布尔或与 `$rose`／`$past` 前件；默认旧模式不变，工具资格产物位于 `deliverables/research19_native_qualification_20261016_r01`。

`--source <终止运行目录>` 可复用其真实初始候选及严格验证的搜索见证。配合 `--retry-interface-edits` 时，程序按时间顺序重新组装该来源中“真实响应已到达、仅接口拒绝、尚无原生执行”的核心提案。表达式不得修改，旧请求/响应及哈希必须保存；重放不记为新生成，仍须重新原生执行与验收。该队列只供独立计费的核心 pilot 使用，不能泄露给四组消融。四组仍从同一初始候选独立调用模型。

从仓库根目录执行，依赖现有 WSL Python、Ollama Qwen 模型及仓库内保存的 Verilator。运行目录必须尚不存在，旧实验不会被覆盖。

```powershell
wsl -- python3 scripts/research18_continue.py --source deliverables/research17_closed_loop_20261016_r01 --out deliverables/fifo_native_new_run --max-refinement-calls 3 --max-model-calls 15
wsl -- python3 scripts/research18_report.py --run deliverables/fifo_native_new_run
wsl -- python3 scripts/research18_report.py --run deliverables/fifo_native_new_run --verify
```

此入口**复用** research17 已发生的真实初始生成和原生搜索，不将复用记作新调用。先核对初始候选及搜索事务见证，然后实际调用模型提出 AST 表达式编辑；通用组装器不修改表达式语义。每个提案在相应 RTL 上编译和执行，严格组再执行历史证据与触发保持验收。拒绝后保留上一个接受版本。核心修复成立后运行四组小规模比较；所有版本冻结后才生成同一批独立测试。

完整初始生成、搜索、细化与回放函数分别在 `research17_loop.initial/acquire/refine/holdout`，续跑入口复用这些模块。原始模型生成请求/响应由 `reused_source.json` 定位，开发证据由 `search/admitted_cases.json` 定位。模型接口另保留历史字符串模式，本轮使用 AST 模式。

## 实际产物

- `shared_initial.json`、`shared_initial_freeze.json`：共同初始候选及原始真实模型来源。
- `source_snapshot/`、`axis_fifo.v`：本次执行源码和 RTL 内容版本；缺失历史 Git 提交不补造。
- `core/v*/model_call/`：每次真实请求、流式响应、最终用量、候选及结构化编辑。
- `core/v*/native/`：编译/执行命令、版本、日志、事务轨迹、参考采样及波形。
- `core/v*/historical_gate_audit.json`、`decision.json`：新缺口、历史误报/漏报和触发检查。
- `arms/A..D/`：共同初始候选下四组独立修改记录。无搜索组不能接收搜索见证。
- `core_independent/`：所有最终版本冻结后产生的新输入、每组原生回放与逐义务结果。
- `report/`：机器可读结果、去重分母、成本、冻结核查及文件清单。

若运行中断，先检查后台进程与 `outcome.json`，不要重新使用已存在目录。取消调用可能没有服务最终用量；保持 null，不用缓存计数或重跑估算旧用量。`--previous-attempt` 和 `--backend-probe` 可重复指定，让报告保留先前失败与探针成本。

## 范围与验收

主案例使用真实 axis_fifo RTL 加人工输出边界故障，不等于复现原始 FIFO presented 历史缺陷。开发参数为深度 2/流水级 0、深度参数 5/流水级 1；后者内部 RAM 按设计取整为 8。独立参数为深度 4/流水级 2。

初始模型任务只要求一条 `order_payload`，因此是受控局部候选，不是自主覆盖全部义务的强基线。两种深度的尾部丢失按一个 `drop/drain_no_loss` 缺口类计数。所有结果是有限原生仿真证据，非形式化证明；历史回放通过不表示全局无退化。

后端曾因 Schema 中过大的字符串长度上限拒绝生成的 grammar，并继续无约束输出。已将传输中的简短理由限制改为 128，保留本地校验；真实后端探针在 `research18_backend_probe_20261016_r02`。探针不是 SVA 成功证据，正式结果以实验 `report/REPORT.md` 为准。

stat 的来源/时序规格及原始 FIFO presented 未找到见证的部分继续 unknown。完整五义务保护、真正候选对分歧比较及多历史父 Bug 的自动闭环应单独验收，不能由局部改进替代。

## 2026-10-16 research18 历史续跑结论

此前 research18 归档为 `deliverables/research18_closed_loop_20261016_r05`，终态 `core_unresolved`。启动命令保存在该目录的 `execution.command.json`；完整审计为 `report/REPORT.md`，机器可读结果为 `report/results.json`。此段保留历史失败，不能替代后续 research19 结果。复现时必须更换输出目录。

本次真实模型生成了一个互补断言，但仍把输出握手作为检查参考队列为空的条件。在合法输出采样时参考队列仍包含该事务，原生回放产生 73 条误报义务行；在丢失事务最终没有输出的时刻，该条件又不能触发。两个开发目标未被确认修复，防退化检查拒绝该版本，冻结原候选。此前两次完成原生语义回放的提案也被拒绝，不能报告成功细化。

新独立输入仅在冻结后生成，运行于 depth=4、pipeline=2。冻结候选检出 15 条目标违例义务行，漏报 3 条、误报 0 条，另保留 411 条后续归因 unknown。三个漏报义务行涉及两个事件：尾部丢失，以及复位残留输出同时违反两个义务。它们不是三个独立缺陷。各项分母及重复合法控制的去重结果以报告为准。四组消融因核心修复未成立而未启动。

本次 r05 新发生 1 次模型生成（输入 11897、输出 166 tokens）、5 次原生编译、57 次原生执行（含 5 次编译附带 smoke），形式化调用 0 次。此前失败运行、取消调用、格式探针及复用的 research17 初始生成/搜索分别记账。取消调用缺失的最终用量保持不可用。

后续应在新的、有界开发实验中比较模型配置或反馈表达，首先验证是否能够从接受周期、最终排空时刻和正常输出采样之间的区别生成正确时序条件；不能人工填入正确断言后计为自动修复。当前独立数据已公开，后续若利用这些结果修改候选，应将其转为开发数据，并在再次冻结后生成新的独立输入。仍需完成成功细化、四组消融、真正的候选对分歧比较和真实历史父案例闭环。

## 2026-10-16 research19 实际结果

最终续跑 r05 为 `core_and_four_arms_executed`。本轮实现并运行了真实契约分析调用、完整 RTL 生成调用、保留真实样本的接口失败反馈、原生前件语法资格测试，以及对历史真实响应的自动语法能力重验。新语法只显式开放已测的布尔或及 `$rose`/`$past` 前件；未人工修改模型谓词。r01 的失败反馈丢失已修复，54 项反馈资格检查通过。r02 的 Deepseek 加载中断及内存适配失败保留，未发生 SVA 生成，管理操作最终用量不可用。

核心成功是跨运行链条：r03 真实生成初始顺序断言、原生搜索两种参数的尾部丢失见证、真实生成互补 `$rose(drain_due) |-> ref_count == 0`，旧接口拒绝；r05 在原生能力资格验证后自动原样重验并接受。r05 core 新模型调用为 0，r03 原调用成本单独保存，不得称为 r05 新生成成功。原 a0 完整保留。开发回放 2970 条义务行中检出 3→5、漏报 2→0、误报 0，56 条后续归因 unknown 保留。两种参数仅算一个 `drop/drain_no_loss` 缺口类。检查点高值仅在所观察的最后周期出现，不能推断持续高检查点每周期保护。

实际命令（重现时换一个尚不存在的输出目录）：

```powershell
wsl -- python3 scripts/research19_loop.py --out deliverables/research19_closed_loop_20261016_r05 --source deliverables/research19_closed_loop_20261016_r03 --contract-planning --native-profile --retry-interface-edits --max-refinement-calls 1 --max-model-calls 8
wsl -- python3 scripts/research19_report.py --run deliverables/research19_closed_loop_20261016_r05
wsl -- python3 scripts/research19_report.py --run deliverables/research19_closed_loop_20261016_r05 --verify
```

四组确已独立运行，各 1 次真实契约分析和 1 次真实生成，均从同一初始候选开始，不能接收 core 的旧提案。A 选择 keep；B 生成恒真约束而未补上缺口，普通验收拒绝；C 引用不存在信号，接口拒绝且没有提案原生执行；D 同样生成恒真约束，严格门控拒绝。四组最后均保留初始版本，本轮没有建立四组机制效果改善，core 不能替代 D。

全部冻结后共执行 5 个候选各 40 次新独立回放（另有编译 smoke），depth=4、pipeline=2。core 的 `order_payload` 检出 14 条、`drain_no_loss` 检出 1 条，两项漏报/误报均为 0；其他义务仍漏报 2 条，属于同一个复位残留事件的两个义务，423 条后续归因 unknown 保留。A–D 都检出 14、漏报 3，其中额外漏报尾部丢失。这里是义务记录数量，不是独立 Bug 数量；完整去重分母在 r05 `report/REPORT.md`。没有形式化证明，也没有全五义务父案例通过。

仍需新实验解决：稳定的新生成细化成功（本轮 B/D 均未成功）、五义务完整保护、真正候选对分歧比较、更多模型种子及真实历史父案例。已公开独立结果若用于后续修改，应转为开发数据，并重新冻结及准备未见测试。历史 stat/FIFO presented unknown 不变。

## 2026-10-18 research20：真实新细化与复杂 FIFO 独立验证

本轮已实际执行新的初始生成、契约样本搜索、真实模型补充断言、原生编译/回放、防退化验收和冻结后测试。**整体仍为 partial；不能报告五义务完整保护。** 主运行是 `deliverables/research20_closed_loop_20261018_r05`，最后的定向复位续跑为 `research20_closed_loop_20261018_r06`，最终集合哈希相同。没有根据独立结果修改或选择候选。

统一入口 `scripts/research20_loop.py` 复用既有 RTL、独立事务参考模型、Verilator assert/cover、历史接受门控和独立测试。增加了完整表达式输出、多义务标签的显式 opt-in、反馈压缩及实际目标故障上下文、初始接口拒绝反馈修复，以及有界远程传输。标签本身不提供检出信用，27 项映射检查验证了这一点；反馈压缩 245 项、初始诊断 23 项检查保留实际样本/拒绝内容。完整模型表达式不由程序修正。

运行 r01/r02/r03 的本地 Qwen 7B 失败均保留：r01 初始通过但六次细化在生成前因上下文超限被拒绝；r02 六次真实细化均接口拒绝；r03 两次新初始候选原生误报。经用户明确授权，r04/r05/r06 使用仓库既有 Highway/Qwen 72B 配置，总共实际发出 **8 次**请求，均保存服务响应与最终用量。模型身份依据服务返回名称，远程权重摘要不可用。r04 两次请求因声明包装格式错误被拒绝；不能把这些失败排除成本。

r05 新初始顺序断言保护接受输出与最早未完成输入的数据一致性。11 个开发场景（深度 2/流水级 0、深度参数 5/流水级 1）在独立队列判据下产生 8 条有效漏报义务记录：尾部丢失 2 条、复位残留的两项义务共 4 条、背压数据扰动 2 条。按故障机制与义务去重是 4 类义务缺口、3 种故障机制，参数复现不算新增独立 Bug。背压模式是显式新增的人工输出边界故障，原始 FIFO RTL 和接口协议保持不变。

两个新增模型提案实际被接受：

```systemverilog
// a0：真实模型生成的初始断言
mvalid && mready && ref_count > 0 |-> mdata == ref_expected
// a1：真实模型生成，排空开发目标 2/2 检出
drain_due && ref_count > 0 |-> $past(mvalid && mready && ref_count > 0) && mdata == ref_expected
// a2：真实模型生成，背压数据开发目标 2/2 检出
mvalid && !mready && $past(mvalid && !mready) |-> mdata == $past(mdata)
```

上面是日志中的原表达式，非手写替换。实际 assert 和 cover 包装保存在 `core/frozen_candidate.sva`。每次接受都重新执行全部开发场景，并核对当前目标、历史合法输入误报、历史检出和触发记录。开发结果由检出 7/15、漏报 8/15 改为检出 11/15、漏报 4/15，误报均 0；这是违例义务记录分母，不是独立事务或 Bug 数量。199 条后续归因 unknown 另外保留。

复位提案两次被接口拒绝；r06 保留 r05 冻结集合，读取真实拒绝信息并用最后一次授权请求定向修复，仍因接口外 `rst` 被拒绝。r06 不是新初始生成成功，也没有新增接受版本。原模型将“无请求输出”误解为“可以输出零数据”的提案原文同样保留，未人工改正谓词。

冻结后使用新的随机输入和深度 4/流水级 2 执行：

| 独立批次 | 比较对象 | 已判定目标检出 | 漏报 | 误报 | 当前归因 unknown | 后续归因 unknown |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| r05 | 原始顺序候选 | 26/41 | 15/41 | 0 | 1 | 453 |
| r05 | 冻结集合 | 32/41 | 9/41 | 0 | 1 | 453 |
| r06 | 相同冻结集合的新一批回放 | 22/27 | 5/27 | 0 | 0 | 474 |

r05 排空目标独立检出 1/1，保留顺序目标检出 26/26；这形成了一条完整的、有限证据范围内的新模型细化链。背压独立仅检出 5/7，r06 为 3/4，故不能报告背压完整闭环成功。该表达式只检查连续两拍仍为背压时的数据，不能据此声称覆盖 valid 保持、解除背压当拍等全部子条件。复位与无请求输出仍未受保护。r06 的 `initial` 比较对象本身就是复用的三断言集合，不能把它与 r05 的原始单断言混淆。

实际执行的可复制命令（再次运行必须换新输出目录；远程请求需要有效的既有凭据及授权）：

```powershell
wsl -- python3 scripts/research20_loop.py --out deliverables/research20_closed_loop_20261018_r05 --seed 2026101805 --iterations 2 --max-model-calls 6 --stall-fault --direct-property --backend configured-qwen-relay
wsl -- python3 scripts/research20_loop.py --out deliverables/research20_closed_loop_20261018_r06 --source-core deliverables/research20_closed_loop_20261018_r05 --only-stage reset --seed 2026101806 --iterations 1 --max-model-calls 1 --stall-fault --direct-property --backend configured-qwen-relay
wsl -- python3 scripts/research20_report.py --run deliverables/research20_closed_loop_20261018_r05
wsl -- python3 scripts/research20_report.py --run deliverables/research20_closed_loop_20261018_r05 --verify
```

总交付位于 `deliverables/research20_campaign_20261018_r01`，各运行包含真实请求/逐块响应、每版 SVA、命令和工具版本、事务记录、VCD、逐版接受/拒绝、开发/测试划分、冻结哈希及机器可读报告。六次运行合计 18 次真实模型调用，输入 181674、输出 2231 tokens，最终用量均可用；原生编译 25 次、执行 543 次（含 smoke）。单独的案例/映射/背压资格实验再计 5 次编译、29 次执行，合计 30/572。失败尝试计入成本，生成前拒绝不冒充调用，形式化调用为 0，货币成本不可用。本轮没有新增四组机制消融或公平基线优势结论，也没有验证多种子稳定性或原始历史父 Bug。所有结果仍是实际 RTL 加人工边界故障的有限仿真；stat、原始 FIFO presented 和未复现的历史案例仍 unknown。

## 2026-10-20 research25：边界细化与必须保留的独立失败

`deliverables/research25_closed_loop_20261020_r01` 复用上述真实三断言集合，新发生两次本地 Qwen 模型调用，输入 23495、输出 270 tokens。模型增加以下两条原文，原生全开发回放后均被接受：

```systemverilog
// 复位/无请求输出：开发通过，随后独立测试失败
(mvalid && mready) |-> $past(ref_count > 0)
// 背压数据保持：包括下一拍 ready 变为 1 的解除边界
(mvalid && !mready) |=> mdata == $past(mdata)
```

15 个开发场景从检出 15/26、漏报 11/26 到检出 26/26、漏报 0/26，合法误报 0。冻结哈希为 `696baa1749a9e317abc8e730f3d42daa274f4aeb3f64f24816f15a1fd911c230`。冻结后新生成 18 个独立场景，Depth 4/8、Pipeline 2；结果为检出 37/41、漏报 4/41、误报 0，当前归因 unknown 0、后续归因 unknown 158。按义务：顺序 16/16、背压数据 9/9、无请求输出 6/8、复位取消 6/8；本批次没有排空违例曝光，不能算该义务独立通过。

只看 r25 同批独立数据中的实际解除背压边沿，原集合检出 0/5、新集合检出 5/5，二者均无合法误报；旧集合在这些边沿的触发数为 0。这是已有真实模型新增性质起作用的具体证据，不能把 r26 中相同集合的新回放称为 r26 新接受了一次编辑。

4 条漏报对应两个真实残留输出事务。单拍复位那一拍的 pre-NBA 队列计数仍非零，复位后队列已经清空，但 `$past(ref_count > 0)` 仍成立。原生前件 cover 已触发、assert 未失败；独立事务 oracle 确认无已接受且未取消的旧请求。因此不能把 research25 表述为复位保护完成，也不能因为开发全部通过而隐藏独立失败。

research22–24 的失败尝试、research25 三次后端能力探针分别保留。发现 Ollama 曾因 schema 正则转义失败而没有应用预期 grammar 后，research25 修正字符类，并逐调用存储服务日志片段与支持状态。工具探针不属于 FIFO 细化。当时六次新增远程调用额度已用完，research25 使用本地模型；后续 research26 r04 另获两次远程授权，见下一节，不将它混记为本地调用。

观察 research25 独立失败后，research26 将其整个 18 场景批次显式转为开发，与原 15 场景合计 33 场景。新模式允许模型替换一条已有性质，同时保留并回放其他四条。新模型修正及新独立测试的结果应另行报告；旧 research25 负结果保留不变。数据保持 SVA 没有单独检查 valid 保持，所有结果仍限于有限仿真及明确人工故障，不能据此宣称全五义务或真实历史父案例完成。

## 2026-10-20 research26：实际续跑，复位自动修复仍未完成

本轮完成单条模型性质替换、完整集合原生回放、公开测试转开发的来源核验、失败模型反馈继承、结构约束后端日志核验及中断记录恢复。未人工填入正确性质。六次运行均有独立目录：`research26_closed_loop_20261020_r01` 至 `r06`。

| 运行 | 实际结果 |
|---|---|
| r01 | 一次本地调用中断，只有部分流；无接受/冻结，最终用量不可用 |
| r02 | 两次本地生成重复错误修正，新增 180 条误报、16 条当前 unknown；两次均拒绝 |
| r03 | 消除新增/替换指令冲突后的一次本地调用仍重复错误修正；拒绝 |
| r04 | 用户新增授权的两次远程调用全部执行；第一版重复错误，第二版增加过去计数约束，产生 2376 条误报、37 条当前 unknown；均拒绝 |
| r05 | 上下文预检拒绝，零生成调用；后端审计又因模型目录未创建而失败，原失败保留，该失败处理已修复并通过五项回归 |
| r06 | 删除重复错误 JSON、保留真实计数对照并压缩重复采样后，发生一次真实本地调用；模型返回原性质，4 条开发漏报未修复，原生门控拒绝 |

r06 是在读取任何 research26 独立结果前，依据开发失败指定的最后续跑。之后没有修改或选择候选。最终冻结仍为 research25 的五断言集合，哈希 `696baa1749a9e317abc8e730f3d42daa274f4aeb3f64f24816f15a1fd911c230`。33 个开发场景检出 63 条已确认违例义务行、漏报 4 条、误报 0；4 条漏报属于两个事务。拒绝错误版本保留了已有保护，但没有补上复位缺口。

最终 r06 的 18 个新独立场景（Depth 4/8、Pipeline 2）结果：

| 义务 | 检出 | 漏报 | 当前归因 unknown | 误报 |
|---|---:|---:|---:|---:|
| 顺序/数据 | 17 | 0 | 0 | 0 |
| 背压数据保持 | 9 | 0 | 0 | 0 |
| 无请求输出 | 4 | 1 | 0 | 0 |
| 复位取消 | 4 | 1 | 2 | 0 |
| 排空不丢失 | 0 | 0 | 0 | 0 |

背压 9 条目标中，实际解除背压边沿为 4/4 检出，连续背压为 5/5 检出；不把总数 9 当作解除边界的分母。

排空没有目标曝光和触发，不能按通过统计。总计检出 34、漏报 2、当前 unknown 2，另保留 222 条后续归因 unknown。2 条漏报对应同一个事务：`core_independent/core/case_7/reset_residue` 的 `e1:t39` 在周期 68 接受、72 取消、73 再次输出；`a3` 实际触发但未失败。其 `$past(ref_count > 0)` 仍把复位边沿的旧非零计数当作依据。另两条复位取消 unknown 与顺序错误同时出现，未授予复位专属检出信用。

本系列实际 7 次模型请求，其中 1 次中断缺最终用量；已知小计输入 83985、输出 991 tokens，不当作完整总成本。新增远程授权 2 次均已使用，远程输入 29600、输出 358 tokens。原生编译 64 次、执行 1144 次（含 64 次编译 smoke），命令失败/超时 0；这不表示断言性质通过。没有形式化调用。本地服务在全部实验终态后按 PID、命令和日志归属核验关闭。更早失败成本见统一机器结果，失败和中断不排除。

实际端到端命令保存在 r06 `execution.command.json`；再次执行必须使用新输出目录。结果与源码哈希校验入口：

```powershell
wsl -- python3 scripts/research21_report.py --run deliverables/research26_closed_loop_20261020_r06 --verify
```

本轮仍不能报告“两个边界全部自动补齐”。背压解除的数据保持有真实模型性质及独立支持；valid 保持没有由新增性质单独保护。复位后的无请求输出仍漏报，自动细化未成功。下一步应独立解决“当前拍未取消事务存在性”的生成与验证，必要时建立明确标记的人工规格基准以隔离模型生成失败与工具问题；人工基准不得计作真实模型细化成功。若使用本轮已公开独立失败继续修正，须将对应批次转为开发并重新生成独立测试。

## 2026-10-20 research27：复位输出保护自动修复通过有限回放

本轮主结果为 `deliverables/research27_closed_loop_20261020_r06`。将 research25 r01 与 research26 r02/r03/r04/r06 的全部 90 个公开测试转为开发，连同原 15 个场景共 105 个，保留输入和来源哈希。新提示不重复旧错误谓词，而由模型从完整 RTL、测试平台、义务及实际空队列/非空队列反例重新综合 a3，其余四条原文保留。

用户新增授权的两次 Highway/Qwen 72B 调用均已使用。第一版检查所有 mvalid 周期，引入 288 条误报，原生门控拒绝；第二版为模型原文：

```systemverilog
mready && mvalid |-> (ref_count > 0 && mdata == ref_expected)
```

它替换旧的 `(mvalid && mready) |-> $past(ref_count > 0)`，由原运行器加时钟、复位屏蔽、原生断言及前件 cover。在输出握手接受的当前拍检查未取消输入的存在性和数据对应关系。105 个开发场景中，检出由 195 增至 214，16 条漏报和 3 条当前归因 unknown 消除，误报保持 0，历史检出及触发未丢失；1177 条后续归因 unknown 保留。计数单位是义务—采样行，不是独立 Bug。

冻结哈希为 `0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1`。冻结后生成 seed 1120995785 的 18 个独立场景，Depth 4/8、Pipeline 2。结果：无请求输出 6/6、复位取消 7/7、顺序 14/14、背压数据 9/9，误报及当前目标 unknown 均 0；旧集合在同批数据有 4 条漏报和 1 条 unknown。另有 160 条后续归因 unknown 保留。排空义务没有目标或触发曝光，不能算作独立通过。

完整原生报告见运行目录 `report/REPORT.md`，聚焦说明见 `deliverables/research27_reset_notes_20261020_r01/SUMMARY.md`。`execution.command.json` 保存实际端到端命令，重跑须使用新目录及重新授权的远程预算。本次两次远程调用输入 21535、输出 307 tokens；没有远程余额。四次失败本地 Qwen 生成、两次零生成加载中断、一次零生成上下文预检拒绝均保留在 r01–r05，不排除成本。量化 KV 缓存已使本地 DeepSeek 加载成功，但其本轮请求未通过上下文预算预检，不能算真实 SVA 生成。

核验入口：

```powershell
wsl -- python3 scripts/research21_report.py --run deliverables/research27_closed_loop_20261020_r06 --verify
```

本轮结论仅为实际 axis_fifo 加明确人工输出边界故障上的有限仿真；没有新增形式化证明、完整五义务保护、独立 valid 保持保护或真实历史父 Bug 结论。所有模型工作结束后才读取各轮独立结果；今后若使用这些已公开结果继续修改，应转为开发数据，并重新准备冻结后测试。

## 2026-10-20 research28 第一阶段：valid 保持漏报资格检查

以 research27 r06 已接受集合为起点，新增显式人工故障 `valid_withdraw_stalled` 和 `valid_withdraw_release`，分别在持续背压和 ready 恢复边界撤销 valid。数据、原始 FIFO RTL、驱动握手语义和独立事务检查器保持不变。原检查器已经要求上一拍 valid 且未接受时，下一拍继续 valid 且数据稳定；新增工作是构造能够单独暴露 valid 漏报的实际故障与测试。

`deliverables/research28_valid_audit_20261020_r02` 的原生执行覆盖 Depth 2/Pipeline 0、Depth 5/Pipeline 1，共 8 场景。8 条首次可归因违例均满足合法输入、同一接受输入序列、真实待完成事务、正确版本满足义务、故障版本 valid 撤销且数据不变、当前 SVA 未报告失败。它们归为两类边界机制，不计作 8 个独立 Bug。当前 unknown 和误报均 0；142 条后续归因 unknown 保留。

首次 r01 原生资格通过，但请求预览被既有开发路径隔离检查拒绝。r02 将开发回放放入 `core/before` 后完成预览；未放宽检查，r01 原产物保留。两次合计 4 次编译、36 次执行（含 4 次编译 smoke），真实模型调用和形式化查询均 0。

```powershell
wsl -- python3 scripts/research28_campaign.py audit --out deliverables/research28_valid_audit_NEW
```

请求预览为 r02 `request.preview.json`。资格检查阶段没有剩余远程额度，自动模型修改、131 场景开发历史回放（105 历史 + 18 公开测试转开发 + 8 新场景）和冻结后新独立测试尚未执行；该阶段不能计为 valid 保护补齐。后续获得新增授权后的实际结果如下。

## 2026-10-20 research28 第二阶段：valid 保持自动修复与新独立回放通过

用户新增授权最多 2 次 Highway/Qwen 72B 请求，实际只用了 1 次。运行目录为 `deliverables/research28_valid_closed_loop_20261020_r01`。模型原文将 a4 从：

```systemverilog
(mvalid && !mready) |=> mdata == $past(mdata)
```

修改为：

```systemverilog
(mvalid && !mready) |=> mvalid && mdata == $past(mdata)
```

其他四条性质保持原文，包含 research27 已验收的复位保护。131 个开发场景原生回放：检出 250→258，漏报 8→0，触发义务记录保持 20298，误报和当前 unknown 都为 0。历史防退化门控接受该修改；1479 条故障后续归因 unknown 保留。

冻结哈希 `2607e416ed0bf4a96b55af757352c2ec63e1d4131fea5235dfbbef300efb67c8` 后，才生成 seed 523922415 的 26 个新独立场景，Depth 4/8、Pipeline 2。新集合检出 52、漏报 0、误报 0、当前 unknown 0；旧集合在同批场景检出 44、漏报 8。其中持续背压 valid 撤销和解除边界 valid 撤销各 4/4 检出，旧集合各 0/4。独立顺序义务 18/18、无请求输出 8/8、复位取消 8/8，背压义务含数据与 valid 共 18/18；排空无目标、无触发，不能算通过。318 条后续归因 unknown 保留。

本轮形成了“两类有效漏报→真实模型补上 valid 检查→历史回放保持→冻结后独立场景有效”的有限证据链。实际模型输入 13368、输出 151 tokens。主闭环 12 次原生编译、640 次执行（含 12 次 smoke）；计入两次资格实验，合计 16 次编译、676 次执行。无形式化调用，金额不可用。原始模型流、逐字组装、实际提示采样、开发/测试隔离和 8767 个主运行产物文件均通过核验。

聚焦交付见 `deliverables/research28_valid_status_20261020_r01/SUMMARY.md`；机器结果、两个实际相邻周期案例和义务—断言映射见主运行 `report/results.json`。实际端到端命令保存在 `execution.command.json`，只读报告入口为：

```powershell
wsl -- python3 scripts/research28_report.py --run deliverables/research28_valid_closed_loop_20261020_r01
```

当前完成的是实际 FIFO RTL 加明确人工输出边界故障上的 valid 保持修复。没有新增全五义务、全局无退化、形式证明或原始历史父 Bug 成功结论。这批独立结果现已公开，后续若用于修改或选择候选，必须转为开发数据并重新准备独立测试。

## 2026-10-20 research29：保持 research28 冻结版本，补齐排空曝光

本轮不修改 SVA、RTL、握手驱动、独立事务检查器或故障模型，复用既有 mode3（隐藏每第 4 个原始输出）。原长流中的后续输出可能先暴露顺序错误，使排空违例落入后续归因 unknown；新场景使最后一个事务丢失后没有后续输出，以单独验证排空检查点。测试生成器不读取断言内容或旧测试结果，所有场景预先固定规则后一次执行，不按结果筛选。

research28 冻结哈希仍为 `2607e416ed0bf4a96b55af757352c2ec63e1d4131fea5235dfbbef300efb67c8`。绑定该冻结版本后生成 seed 646660228 的 18 个新独立场景。Depth 2/Pipeline 0、Depth 4/Pipeline 1、Depth 8/Pipeline 2 各包含：

- 四个丢失目标：孤立请求、连续请求、先背压后释放、复位后新事务。
- 两个合法对照：三个事务正常排空、复位取消未完成事务。

12/12 丢失目标都被原有 a1 实际触发并检出，6/6 合法对照通过；每个丢失目标另有同激励下的正确 FIFO 对照，独立事务队列确认正确版本已排空、故障版本恰有一个已接受但未响应且未取消的事务。实际公平后缀至少 18 拍（输出 ready、输入 idle、无 reset），排空是首个独立义务违例，之前没有 SVA 报警。本批漏报、误报、当前及后续归因 unknown 均为 0。

实际 Depth 8 案例中，事务 e1:t3 在周期 40 接受，正确版本周期 44 响应；故障版本到周期 64 排空检查点仍未响应，原生 a1 报警。复位后新事务案例 e2:t5 在周期 45 接受，正确版本周期 49 响应；故障版本在周期 69 被检出。实际事务和相邻采样保存在机器结果。

本批没有需要修改断言的失败，没有模型调用、没有转开发或重新选择候选。实际成本为 3 次原生编译、39 次执行（含 3 次 smoke），0 次形式化查询；628 个原始产物哈希、冻结绑定和新旧输入无重合检查均通过。

```powershell
wsl -- python3 scripts/research29_drain.py --out deliverables/research29_drain_independent_NEW
wsl -- python3 scripts/research29_report.py --run deliverables/research29_drain_independent_20261020_r01
```

最终报告为 `deliverables/research29_drain_independent_20261020_r01/report/SUMMARY.md`。这是同一个已知人工尾部丢失机制上的多场景、多参数独立输入验收，不是多个历史 Bug 或全局保护证明。research28 原有 1479/318 条后续归因 unknown 保持原记录。本批弥补“排空义务没有有效曝光”的缺口，其他义务沿用已有验收范围。若今后使用本批结果修改断言或挑选候选，仍须整批转开发并重新准备冻结后测试。

## 2026-10-20 research30：固定候选的公平搜索比较

`scripts/research30_search.py` 复用原生运行时、事务 oracle 和既有策略，固定 research27、research28 两个完整冻结集合。候选分歧由两个集合在同一输入上的实际报警周期异或计算，不再以单个集合内不同义务的性质差异代替候选对。普通补测、候选对分歧、普通 RTL 差分、契约覆盖搜索使用同一输入语法和公共信息，但只接收各自允许的策略反馈。

实际运行三个种子 3113、3119、3121，每方法每种子四次查询，每次两个候选 × 正确版本及七类人工故障，共 16 次执行、每次 112 拍、Depth 4/Pipeline 1。共同首个 overlap 查询计入预算。去重按初始候选哈希、误报/漏报、义务及故障机制，数据和波形变体不增加独立发现。

每方法均为 12 次查询、192 次执行；最终均发现持续背压 valid 撤销和解除边界 valid 撤销两类缺口。契约搜索相对普通补测和候选分歧没有新增独立缺口；其首次发现查询数为 2/2/2，普通补测为 2/3/3，候选分歧为 2/2/2，普通差分为 2/4/未找到。契约搜索相对普通差分在种子 3121 多找到两类，但不能据此称其全面优于基线。

物理总成本为 2 次编译、770 次执行（包含 2 次 smoke），模型和形式化调用为 0。9763 个产物的哈希及预算、候选哈希、共同输入、反馈隔离检查通过。报告为 `deliverables/research30_search_compare_20261020_r01/report/SUMMARY.md`。这是一个已知人工故障任务上的原生候选对试验；原有 11 对受限检查器候选没有被计入本轮原生结果。

```powershell
wsl -- python3 scripts/research30_search.py --out deliverables/research30_search_compare_NEW --budget 4
wsl -- python3 scripts/research30_report.py --run deliverables/research30_search_compare_20261020_r01
```

## 2026-10-20 research30：四组真实模型消融与门控负结果

资格阶段 `research30_ablation_prepare_20261020_r02` 确认公共初始候选在 105 个历史场景上无漏报、误报或当前 unknown，并确认两类搜索漏报。公共初始集合为 research27 的真实冻结集合；research28 的成功谓词没有提供给模型。A 普通反馈、B 加搜索、C 加防退化、D 两者启用，A/C 初始请求逐字相同、B/D 初始请求逐字相同；只有 B/D 获得本轮契约搜索的两条开发见证。

用户授权最多四次新调用，实际四组各一次 Highway/Qwen 72B，temperature 0、seed 3113、输出上限 1024 tokens，不重试。结果保存在 `deliverables/research30_ablation_20261020_r01`：

| 组 | 实际修改和决定 | 共同历史新增漏报剩余 | 新独立检出/漏报 |
|---|---|---:|---:|
| A 普通反馈 | 两个蕴含符，不满足接口约束，拒绝并保留初始 | 2 | 34/8 |
| B 加搜索 | a2 增加下一拍 valid 保持，原生当前证据通过，接受 | 0 | 42/0 |
| C 加防退化 | 只产生数据保持，因历史触发减少被拒绝 | 2 | 34/8 |
| D 两者启用 | 只产生数据保持，新漏报未修复且历史触发减少，拒绝 | 2 | 34/8 |

B 的原 a2 为 `mvalid && !mready && $past(mvalid && !mready) |-> mdata == $past(mdata)`，模型替换为 `mvalid && !mready |=> mvalid && mdata == $past(mdata)`，其他性质不变。这是模型原文经通用组装后实际执行的结果，没有人工修正表达式。

四组都冻结后才执行相同 107 场景历史审计，并生成 seed 1457709376 的 26 个新独立场景，包含 Depth 4/8、Pipeline 2。四组均保留原有 214/214 违例检出，无新增历史误报。B 将搜索见证的 2 条漏报修复，独立场景中两类 valid 撤销分别检出 4/4；其他组各遗漏 4+4。各组独立误报和当前 unknown 均为 0，后续归因 unknown 均为 329；历史审计后续归因 unknown 为 1224。独立批次的排空义务没有目标曝光，不能据此宣称全五义务通过；research29 的单独排空验收保持原范围。

门控的两条触发丢失均发生于上一拍复位、当前拍复位解除时。上一拍复位已取消背压保持义务，独立 oracle 没有相应检查；旧 a2 仍可产生前件 cover，替换后的非重叠性质不产生该触发。C 仅因这两条记录被拒绝，不能称为保护保留的收益。对 B 的实际冻结候选在共同历史证据上执行只读门控复算，同样仅因两条触发减少被拒绝，确认当前“保留所有历史触发”规则过度保守。原实验规则、决定和冻结版本均未事后修改。

相同提示和采样配置仍产生不同模型结果。B 优于 D 不能全部归因于门控，D 的模型表达式本身也没有补上 valid。单次四组结果尚不能建立两机制稳定收益；后续应独立验证基于义务适用条件的触发保持规则，并在新协议下作多种子重复。

消融实际使用输入 42850、输出 779 tokens，51 次原生编译、1977 次执行（含 51 次 smoke），形式化调用 0。准备和搜索成本另列，不能按消融成本代替整个任务成本。27415 个原始产物文件、原始模型响应、冻结绑定、提示隔离、开发/独立输入无重合及源码快照核验通过。

实际启动命令保存在运行目录 `execution.command.json`。完整报告、两条实际周期案例和对 B 的只读门控复算分别为 `report/SUMMARY.md`、`report/case_examples.json`、`report/counterfactual_gate_on_B.json`。只读报告入口如下，不产生模型调用：

```powershell
wsl -- python3 scripts/research30_ablation_report.py --run deliverables/research30_ablation_20261020_r01
wsl -- python3 scripts/research30_campaign_report.py --out deliverables/research30_campaign_20261020_r01
```

本轮完成的是固定已知 FIFO 任务上的公平搜索比较与一次四组真实消融；没有把它表述为跨父 Bug 稳定性、原始历史修复完成或形式证明。项目已有 research28 冻结版本及 research29 验收保持不变。

## 2026-10-20 research31：修正复位取消义务的触发门控

新增 `scripts/research31_gate.py`，保留 `research15_acceptance.decide` 原严格判定，只在前后两次原生回放均有证据确认“前一拍复位取消本拍背压保持义务”时，豁免对应的历史触发减少。确认依赖原生编译/执行状态、采样资格、独立 oracle、同激励哈希绑定和前后采样一致性，不读取待评估 SVA 文本判断义务适用性。

其他触发减少、适用性 unknown、缺少回放、执行 unknown、证据身份变化、历史违例检出丢失、新误报和当前缺口未修复仍按严格规则拒绝。该版本只对已确认的复位取消背压条件作豁免；其他义务没有适用性证明时仍保守处理。

`deliverables/research31_gate_validation_20261020_r01` 已实际运行五个开发场景、三套断言的原生回放：初始集合检出 13、漏报 2；真实模型 B 版本检出 15、漏报 0，新门控接受。人为屏蔽 a2 前件的明确负对照检出 13、漏报 2，因历史目标检出丢失和当前缺口未修复而拒绝。误报和当前 unknown 均为 0，103 条后续归因 unknown 保留。负对照不是模型生成结果。

对 research30 已存档的公共历史及搜索证据作开发复核，B 得到两个有据豁免后通过，D 仍因两个搜索漏报未修复被拒绝。C 在原先未包含搜索目标的历史范围内可接受，并不意味着 valid 缺口被修复。额外门控输入扰动检查确认，合法事务上真正适用的历史触发被删除仍会拒绝。research30 原实验的决定、冻结版本和独立测试结果保持原样。

`scripts/research31_multiseed.py` 已准备种子 3113/3119/3121 × 四组，共 12 个真实请求预览，路径 `deliverables/research31_multiseed_prepare_20261020_r01/s*/preview/`。105 个公共历史场景明确复用原已验证记录，各种子的两条搜索漏报重新原生验证。每种子 A/C 请求相同、B/D 请求相同；各组一次调用、无重试，所有提示预先固定。每种子四组冻结后才生成该种子的新独立批次，中途结果不得用于修改其他种子的提示或选择候选。

本地准备阶段没有发起模型调用。上一轮 4 次额度已耗尽，本轮 12 次调用需要新增明确授权；在新运行目录出现成功终态和独立测试前，不计为多种子消融完成。准备结果及状态报告为 `deliverables/research31_status_20261020_r01/SUMMARY.md`。

```powershell
wsl -- python3 scripts/research31_gate_validate.py --out deliverables/research31_gate_validation_NEW
wsl -- python3 scripts/research31_multiseed.py prepare --validation deliverables/research31_gate_validation_20261020_r01 --out deliverables/research31_multiseed_prepare_NEW
wsl -- python3 scripts/research31_report.py --validation deliverables/research31_gate_validation_20261020_r01 --prepared deliverables/research31_multiseed_prepare_20261020_r01 --out deliverables/research31_status_20261020_r01
```

## 2026-10-20 research31：新增授权后的三种子四组真实实跑

用户新增授权最多 12 次 Highway/Qwen 72B 调用后，`deliverables/research31_multiseed_20261020_r01` 已完成种子 3113/3119/3121 的四组实验。每组一次调用、无重试，全部实际请求与预先固定的预览一致。每个种子四组均冻结后，才生成该种子的 26 个新独立场景；三个独立种子分别为 136076227、1219616800、515967181。后续种子的提示未根据前面结果调整。

| 组 | 两类 valid 边界均检出的重复次数 | 独立可归因检出/漏报记录 | 独立误报/当前 unknown |
|---|---:|---:|---:|
| A 普通反馈 | 2/3 | 107/8 | 0/0 |
| B 加搜索 | 2/3 | 107/8 | 0/0 |
| C 加门控 | 1/3 | 99/16 | 0/0 |
| D 搜索加门控 | 2/3 | 107/8 | 0/0 |

分母是每种子两类 valid 边界的已曝光目标；所有组每种子都执行相同的 26 个场景，总计 78 个独立输入场景。检出/漏报是第一可归因义务记录，不是独立 Bug 数量或整个场景通过数。各组另有 1025 条后续归因 unknown（356+378+291），保留原记录。排空等义务的实际曝光分母另列，未曝光不能按通过处理。

三个种子中，A/B/D 的最终效果逐种子相同。A 在前两个种子仅凭公共规格及普通反馈也生成了有效 valid 保持；第三个种子的 A 没有实际补齐保护，B 的数据保持提案因新漏报仍存在被拒绝。C 的前两个种子、D 的第三个种子返回超出现有单蕴含接口约束的表达式，未进入对应候选的原生编译，不能称作原生 SVA 语法错误。

实际进入完整原生历史门控的自然提案只有三份（3113/D、3119/D、3121/C），均被新旧门控接受，没有使用复位触发豁免，也没有因真实历史保护退化而被拒绝的提案。门控修正已在上一阶段的实际开发回放和负对照上验证，但本次自然模型提案没有提供其历史保护收益的曝光。各组模型输出存在差异，不能把 C/D 的成功率差异全部归因于门控。

这批实跑没有证明搜索或两机制联合优于普通反馈。完整保存了三个接口失败、一个未解决当前缺口的提案、未改善保护的重复性质和所有成功版本，没有用补跑替代失败。原 research28 已验收版本及 research29 排空结果保持不变。

本次消融实际成本：12 次模型调用，输入 128616、输出 2239 tokens；143 次原生编译、5293 次执行（含 143 次 smoke），无执行命令失败，形式化调用 0。连同本轮门控开发验证和三种子资格准备，合计 158 次编译、5350 次执行。既有历史及搜索源实验的复用成本单列，不重复计为新执行；金额不可用。

最终只读报告为 `deliverables/research31_multiseed_report_20261020_r01/SUMMARY.md`。`multiseed_results.json` 保存逐种子对比、历史保护、各义务分母、成本及隔离检查；`case_examples.json` 保存每种子每组两类边界的实际完整轨迹；`counterfactual/` 是对 A/B 实际冻结候选的只读门控复算，不改变原实验决定。

79 项隔离与完整性检查全部通过，73650 个主运行文件哈希一致；全部 12 个冻结版本均保留公共历史 214/214 条违例检出，没有新增历史误报。复用成本另见最终报告目录 `reused_source_costs.json`：历史源已花费 4 次编译、214 次执行，三种子的契约采集源为 12 次查询、192 次执行；B/D 各按 64 次执行记逻辑搜索预算，六个搜索组共 384 次逻辑执行。这些旧源成本与本轮新增物理执行分开，不能重复相加或算作免费采集。

实际启动命令保存在主运行 `execution.command.json`。以下命令仅重新汇总，不调用模型：

```powershell
wsl -- python3 scripts/research31_report.py --validation deliverables/research31_gate_validation_20261020_r01 --prepared deliverables/research31_multiseed_prepare_20261020_r01 --run deliverables/research31_multiseed_20261020_r01 --out deliverables/research31_multiseed_report_20261020_r01
```

## 2026-10-21 research32：长背压搜索、同提案门控对照及多轮细化准备

本轮本地原生实验已完成，报告为 `deliverables/research32_report_20261021_r01/SUMMARY.md`。新增真实模型调用尚未执行；之前 12 次授权已用完，新的 3 个种子各最多 3 轮请求等待新增授权。不得将下述归档响应控制记作新模型生成。

`research32_runtime.py` 在原 axis_fifo 测试平台添加明确人工故障：连续八拍原始输出背压后，在继续背压或解除边界撤销 valid。原始 RTL、握手语义及独立事务 oracle 不变。四种方法均用同一 research27/28 完整候选对、同一输入范围、三个种子、每种子四查询，每查询 112 拍和六次原生执行。结果如下：

| 方法 | 种子 3203 / 3209 / 3217 缺口类别 | 合并去重 |
|---|---|---:|
| 普通补测 | 1 / 0 / 1 | 1 |
| 候选对分歧 | 2 / 0 / 0 | 2 |
| 普通波形差分 | 2 / 0 / 0 | 2 |
| 契约持续时间覆盖 | 2 / 2 / 2 | 2 |

契约策略根据自身正确侧已观测的连续背压长度，依次补齐公开的短、中、长持续时间桶。人工故障是已知研究对象，各方法可访问信息相同。该试验支持本例中种子内覆盖改善及相对普通补测的一类额外缺口，不支持比候选分歧/差分发现更多总类别，更不代表一般优越性。

`research32_gate_case.py` 原样重放 research27/v0 的真实模型提案，在回顾性选定的当前场景修复两条漏报，当前场景检查接受；同一提案在历史场景引入 38 个误报采样行，完整门控拒绝。保留 2 条当前归因 unknown、56 条后续 unknown。这是同一提案的机制对照，避免不同模型输出的混杂，但不是新的真实细化结果或退化发生率估计。

`research32_model.py` 让模型分别生成 Boolean 前件、后件和时序枚举，由接口只做语法拼装；不提供或改写正确谓词。`research32_campaign.py` 复用 `research21_loop.refine`，补充带候选/输入/结果哈希的资格基线复用、每个自然提案的当前检查与历史门控成对记录、三种子各三轮上限、首轮请求锁定及全部冻结后的新独立测试。拒绝后继续保留上一已接受集合并反馈实际诊断。

`research32_qualification_20261021_r01` 的本地归档响应控制确实执行了拒绝、回退和继续下一轮：4 条漏报最终均检出，误报/当前 unknown 为 0，84 条后续 unknown 保留。零模型调用，不作为真实模型稳定成功。

实际新增本地成本为 12 次原生编译、356 次执行（含 12 次编译 smoke），无命令失败，形式化查询 0。105 个旧公共历史场景复用，成本另列；三个种子的每组四条新/旧边界漏报均重新原生资格核查。11 项报告检查通过，完整配置、源码哈希、候选、波形、oracle、模型请求预览及成本清单已保存。研究28项目冻结版本保持不变。

```powershell
wsl -- python3 scripts/research32_search.py --out deliverables/research32_search_NEW
wsl -- python3 scripts/research32_gate_case.py --out deliverables/research32_gate_case_NEW
wsl -- python3 scripts/research32_campaign.py prepare --search deliverables/research32_search_20261021_r01 --out deliverables/research32_prepare_NEW
wsl -- python3 scripts/research32_qualification.py --prepared deliverables/research32_prepare_20261021_r01 --out deliverables/research32_qualification_NEW
# 新增授权落盘后才运行，最多 9 次调用：
wsl -- python3 scripts/research32_campaign.py run --prepared deliverables/research32_prepare_20261021_r01 --out deliverables/research32_real_20261021_r01 --authorization deliverables/research32_prepare_20261021_r01/authorization.json
```

## 2026-10-21 research32：新增授权后的真实三种子细化与独立验收

用户新增授权最多 9 次调用后，实际运行 `deliverables/research32_real_20261021_r01`，使用 7 次 Highway/Qwen 72B 调用，输入 86945、输出 945 tokens，无传输重试，另外 2 次额度未使用。每种子最多三轮，接受即停止。没有修改已固定的请求或执行代码来挑选成功结果。

| 种子 | 调用数 | 开发漏报（前→后） | 历史目标检出保持 | 新独立检出/漏报 | 误报/当前 unknown |
|---|---:|---|---|---|---|
| 3203 | 3 | 4 → 4 | 214/214 | 47/20 | 0/0 |
| 3209 | 1 | 4 → 0 | 214/214 | 67/0 | 0/0 |
| 3217 | 3 | 4 → 4 | 214/214 | 47/20 | 0/0 |

这批真实实验只有 **1/3 种子成功，稳定细化目标尚未达到**。两个失败种子三次都返回只检查数据保持的提案，原生回放确认 valid 撤销仍漏报，因此全部拒绝并保留原候选。诊断中实际存在 valid 从 1 到 0、数据不变、断言触发但未失败的样本；不能归因于缺少反馈或原生工具无法执行。本批结构化接口没有语法装配拒绝，但解决语法问题并不等于解决语义遗漏。不同种子和上下文与 research31 不同，不将两批成功率直接当受控算法比较。

种子 3209 的真实模型把 a2 从 `mvalid && !mready && $past(mvalid && !mready) |-> mdata == $past(mdata)` 改为 `(mvalid && !mready) |=> (mvalid && mdata == $past(mdata))`。开发四类短/长背压保持和解除漏报全部补上，历史 214 条目标检出保留，无新误报。门控依据双侧实际回放豁免两条复位取消的非适用触发；旧严格门控会误拒绝这一版本。本批自然提案没有出现“当前样例通过但完整历史门控拒绝”的新情况；前一阶段 research27 归档案例的防退化曝光单独保留。

三份最终集合全部冻结后，才生成种子 1758892 的 **30 条不同新输入、38 个参数/故障场景**，所有冻结版本执行相同批次。两个 fresh_random 输入各施加五种故障，故障场景不能重复当作不同输入。参数为 Depth=4、8，RAM_PIPELINE=2。每个版本另有 498 条后续归因 unknown，保留不排除；本批 drain_no_loss 目标曝光和触发为 0，不能声称排空通过或五义务完整案例通过。research29 的排空结果仍只适用于其原冻结版本和证据。

初版只读审计错误地要求每个故障场景输入唯一，失败告警保存在 `research32_real_report_20261021_r01`。修正版报告为 `deliverables/research32_real_report_20261021_r02/SUMMARY.md`，仅修正共享故障输入的分母和场景身份检查；没有修改断言、独立测试输入、接受决定或原生执行结果。逐轮原始响应拼装、拒绝反馈、冻结哈希、开发/测试隔离、每类边界计数和实际事务轨迹保存在该目录的 `results.json`、`case_examples.json` 和 `verification.json`。

本次真实运行新增 41 次原生编译、1795 次执行（含 41 次编译 smoke），没有命令失败或超时；形式化查询 0，金额不可用。连同本阶段此前本地搜索、门控案例、准备和归档控制，research32 合计 53 次编译、2151 次执行。旧源实验成本没有重复计入。研究28项目验收版本未替换；新成功版本的哈希为 `09d176be5e2e8045d3fb8c222c5f892cb76c74326070e1eb6d0dff884192a27d`。

以下命令只读复核，不调用模型或仿真；输出目录须不存在：

```powershell
wsl -- python3 scripts/research32_real_audit.py --run deliverables/research32_real_20261021_r01 --prepared deliverables/research32_prepare_20261021_r01 --out deliverables/research32_real_report_NEW
```

## 2026-10-21 research33：针对重复无效提案的改动（本地已验证，真实调用待确认）

`scripts/research33_model.py` 改为先展示四条开发反例的正确/故障逐周期对照，列出相同和不同的信号；移除旧性质文本，要求模型重新生成表达式并解释如何区分实际样本。提示词没有提供已成功的 SVA。保留原结构化装配器、对应 RTL、独立事务判定和完整历史门控。

新增性质词元、时序关系和义务映射指纹，仅识别去除空白、最外层括号和说明文本后的相同提案；不是一般语义等价检查。重复已知漏报提案在原生执行前拒绝并留档。`research21_loop.py` 将该情况单独分类，不再归为接口失败；新表达式仍须通过原生回放，不能凭文本不同接受。

最新准备产物为 `deliverables/research33_prepare_20261021_r02`，报告为 `deliverables/research33_local_report_20261021_r01/SUMMARY.md`。58/58 本地检查通过，6/6 历史重复提案可识别。归档成功版本作为明确标注的正对照，五个场景上漏报 4→0、误报0、后续归因 unknown 140；不是本轮模型生成成功。r02 新增4次编译、24次执行（含4次编译冒烟）；连同保留的 r01 准备，本轮合计8次编译、48次执行，模型调用0、形式化0。

r01 与 r02 的两份请求 SHA256 分别相同；r02 只更新重复拒绝的结果分类及代码快照。本轮针对两个历史失败种子各计划一次真实调用，不作为无偏成功率或四组消融。此前9次授权已用7次，剩余2次转用于新试验的确认已请求；授权文件尚未创建，尚未提交请求。两个版本终结并冻结后才准备新的独立输入，旧公开测试不再作为本轮独立结果。

```powershell
wsl -- python3 scripts/research33_campaign.py prepare --out deliverables/research33_prepare_NEW
wsl -- python3 scripts/research33_audit.py --prepared deliverables/research33_prepare_20261021_r02 --out deliverables/research33_local_report_NEW
```

## 2026-10-21 research33：两次真实重试已完成，仍未修复

用户明确授权转用剩余2次额度后，实际执行 `deliverables/research33_real_20261021_r01`，3203、3217 各调用一次，无重试。原9次额度累计使用9次，不再有剩余额度。请求与原预览一致，输入27494、输出260 tokens，两个响应ID不同，模型返回完全相同的新提案：

```systemverilog
(svalid && !sready && mvalid && mready) |=> (mvalid && mdata == ref_expected)
```

模型确实停止照抄旧数据保持性质，但上述前件错误地要求输出 ready 以及输入侧条件。原生回放确认：4条当前目标证据上均无有效触发、无因果检出。两个新提案各引入2条合法事务误报、丢失33条历史检出和1068条义务触发，并有2条关键回放 unknown；因此两者全部拒绝。计数单位为义务×采样周期证据行，不是独立故障数。没有将后件含有 mvalid 或文本变化当作修复成功。

两个终版均回退为原候选并冻结，哈希 `0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1`，开发历史214/214检出保留。research28 项目验收版本和 research32 的3209成功版本未替换。此次当前漏报检查本身也足以拒绝两个提案，因此虽然完整门控报告了历史退化，不能据此声称防退化机制相对仅检查当前缺口带来了额外接受决策收益。

全部冻结后生成独立种子2061654095，Depth=4、8，RAM_PIPELINE=2，共30条不同输入、38个参数/故障场景。两个回退版本分别检出38、漏报20、误报0、当前unknown0，另保留后续归因unknown594。独立边界验收0/2；排空义务未在该批有效曝光，不能报告整个案例或五项义务通过。没有根据新测试修改候选。

新真实运行14次原生编译、602次执行（含14次冒烟），无失败或超时命令，形式化0、金额不可用。连同本轮两版本地准备共22次编译、650次执行；原研究32的历史执行成本不重复计入。

只读审计134/134通过，报告：`deliverables/research33_real_report_20261021_r01/SUMMARY.md`。`results.json` 保存实际编辑与接受/拒绝原因；`case_examples.json` 保存每条原始漏报、提案回放、回退保护、事务关联及独立边界结果；`run_manifest.json` 保存运行产物哈希。该结果是提示改动未能修复语义问题的负结果，不能表述为稳定自动细化成功，也不能由两个选定失败种子的结果推断总体成功率。

实际执行命令（该输出目录已存在，不要覆盖或重复调用；现有授权已用完）：

```powershell
wsl -- python3 scripts/research33_campaign.py run --prepared deliverables/research33_prepare_20261021_r02 --out deliverables/research33_real_20261021_r01 --authorization deliverables/research33_prepare_20261021_r02/authorization.json
```

可复制执行的只读复核命令（不调用模型或仿真，使用新输出目录）：

```powershell
wsl -- python3 scripts/research33_audit.py --prepared deliverables/research33_prepare_20261021_r02 --run deliverables/research33_real_20261021_r01 --out deliverables/research33_audit_NEW
```

下一步应以本次实际的零触发反例约束模型先明确义务适用周期，再生成性质，并要求候选在目标前件触发及正确/故障配对回放上先过关；这只是下一轮待检验的改进方向，尚未实施或运行，不能列入本轮成功结果。本轮已公开的新测试若用于后续修改，须转入开发数据并重新准备独立测试。

## 2026-10-21 research34：义务适用周期与原生性质分阶段门控

已实现 `scripts/research34_applicability.py` 和 `scripts/research34_campaign.py`。流程是一次真实周期标注请求 → 独立标注验收 → 仅通过后才请求一次SVA → 小批原生触发及检出验收 → 仅通过后才执行完整历史回放 → 接受/回退及冻结。若接受，再生成新的独立测试；不以改写文本作为进展判据。

周期验收采用9个已运行的开发窗口：4条短/长背压保持与解除目标反例，加上合法解除、复位取消、复位后首拍、空闲和已接受输出等5条控制窗口。期望标签由独立端口事务 oracle 重新计算，并与实际采样及复位语义核对，不读取候选SVA来定义适用性。模型须逐项给出 anchor_cycle、check_cycle 和 required/cancelled/not_required；错位、漏项、重复和unknown均不能通过。本地答案文件不进入模型请求。

第二关检查新增/替换的具体性质，而不是让断言集合中的其他性质代替它通过：对四条当前反例核验原生前件触发周期、正确侧触发、故障侧因果检出及原生健康状态。正负对照执行结果：research33归档错误提案触发0/4、检出0/4，提前拒绝；research32归档成功提案触发4/4、检出4/4、正确侧触发4/4，小批门控通过。后者只是归档正对照，不是本轮新的模型细化成功。两组均保留后续归因unknown140，小批通过也不等于完整历史或整个案例通过。

实际准备产物：`deliverables/research34_prepare_20261021_r01`；报告：`deliverables/research34_local_report_20261021_r01/SUMMARY.md`。198项检查通过，592个准备产物纳入内容清单；实际新增4次原生编译、24次执行（含4次编译冒烟），模型调用0、形式化0。1个正确标注和5类错误标注是明确标注的校验器测试夹具，不能当作模型回答或模型成功率。

复用远程传输模块增加 `save_decoded_output` 输出钩子，让周期标注独立保存为 `applicability_plan.json`，不会假装生成SVA。兼容性检查在 `deliverables/research34_hook_regression_20261021_r01/verification.json`：归档原始响应核验、候选一致、SVA逐字一致、零调用及无提交记录5项通过。未更改模型表达式。

首轮真实请求固定在 `deliverables/research34_prepare_20261021_r01/plan_request.preview.json`；前一阶段额度已用完，本轮新增最多2次调用授权正在等待确认。第二份请求仅在实际模型标注通过后创建，增加经过验证的原始模型标注，不插入成功SVA。真实模型能否正确识别适用周期、继而修复前件尚未验证。

```powershell
# 本地准备：原生归档对照，不调用模型；输出目录须不存在。
wsl -- python3 scripts/research34_campaign.py prepare --out deliverables/research34_prepare_NEW
# 只读审计。
wsl -- python3 scripts/research34_audit.py --prepared deliverables/research34_prepare_20261021_r01 --out deliverables/research34_report_NEW
# 新授权落盘后才能运行；第一关失败则只消耗1次，不调用SVA生成。
wsl -- python3 scripts/research34_campaign.py run --prepared deliverables/research34_prepare_20261021_r01 --out deliverables/research34_real_20261021_r01 --authorization deliverables/research34_prepare_20261021_r01/authorization.json
```

## 2026-10-21 research34：真实周期标注7/9，第一关拒绝

用户授权新增最多2次调用后，执行 `deliverables/research34_real_20261021_r01`。实际仅提交1次周期标注请求，原始响应、事件流、终态和用量均已保存。模型返回完整9项且所有周期编号正确，但适用性分类只有7/9正确，门控按预定规则拒绝；第二次SVA生成没有提交，剩余1次额度未使用。该额度原定仅在标注全部通过后生成SVA，不能自动转作标注重试。

两个分类错误均保存于 `deliverables/research34_real_report_20261021_r01/results.json/window_results`：

- **w1，短背压期间 valid 撤销，7→8周期**：第7拍 `rst=0, mvalid=1, mready=0`，已建立下一拍保持输出的义务；第8拍未复位，`mvalid=0, mready=0`，数据未变。独立事务oracle确认需要检查且存在违例，正确侧在同一激励下满足义务。模型却标为 `not_required`。这是直接影响目标保护的适用性错误；不能把当前输出valid已经撤销当作允许遗漏检查的依据。模型未提供推理过程，不能据此断言其内部错误推理步骤。
- **w4，复位后首拍，2→3周期**：第2拍复位有效且无有效输出，第3拍复位释放，无之前已建立且在本拍取消的stall义务。按预先声明的标签语义应为 `not_required`，模型标为 `cancelled`。这是取消与不适用分类的混淆；两者在本窗口都不要求保持检查，不把此标签错误另算一个已发生的功能漏报。若只投影为“是否要求检查”，正确率为8/9，w1仍失败；本轮原三分类验收标准不变。

终态 `applicability_rejected_no_sva_generation`。没有执行本轮SVA生成、小批原生回放、完整历史回放或新独立测试，均不得报告为通过。原断言保留并冻结，哈希 `0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1`，未改动既有成功版本。

本次真实调用输入11363、输出357 tokens，无重试，服务报告用量完整，金额不可用；新增原生编译/执行/形式化均为0。此前research34本地归档正负对照的4次编译、24次执行单独保留，不冒充本轮模型执行。只读审计166/166通过，核验159个运行产物；报告为 `deliverables/research34_real_report_20261021_r01/SUMMARY.md`。该实验实际验证了阶段门控能在错误适用性判断时停止，尚未验证模型能生成有效的新SVA，更不构成机制优越性的受控比较。

可复制的只读复核命令（不消耗模型额度，输出目录须不存在）：

```powershell
wsl -- python3 scripts/research34_real_audit.py --prepared deliverables/research34_prepare_20261021_r01 --run deliverables/research34_real_20261021_r01 --out deliverables/research34_real_report_NEW
```

## research35：继续适用性修正、真实细化与同版本独立验收（准备已验证）

`scripts/research35_campaign.py` 复用现有模型传输、独立事务oracle、原生SVA回放和历史门控。适用性输入只投影真实前置周期的 rst/mvalid/mready 与当前周期复位；当前输出与输入侧活动不参与适用性标注，但完整观测保留用于后续性质验证。这一投影不创造信号值、不替模型填标签；旧模型的实际标注和实际拒绝理由作为开发反馈提供。

新增四个Depth=4/8、Pipeline=2的长背压开发场景，均实际执行对应RTL；与旧场景合并后共13个适用性窗口、8条确认目标漏报，完整历史回放计划为113场景。8条是义务采样证据，不是8个独立故障。归档错误提案在8条目标上触发0、检出0；归档成功提案触发8、检出8，小批门控通过，仍保留212条后续归因unknown。以上均不算本轮新模型细化成功。

真实流程设置最多两轮周期标注、仅通过后最多两轮SVA生成/细化；每次失败反馈均来自实际检查，达到验收即停止。若新版本通过目标反例和完整历史门控，先冻结，再生成38个短/长背压与复位/顺序场景，加18个公平排空场景；按同一冻结集合逐义务检查曝光、触发、检出、误报、漏报及unknown。没有根据独立结果继续选候选或修改。五项义务即使在首个可归因证据范围内通过，也不得宣称全局保护，后续归因unknown仍保留。

实际原生准备在 `deliverables/research35_prepare_20261021_r01`，新增10次编译、54次执行（含10次冒烟）、模型调用0、形式化0。随后只更正多轮模型反馈中不应固定宣称“已触发”的说明，并增加复用封存命令；通过AST比较确认原生准备、合并和独立生成函数未变，r02复用r01真实资格记录并保存新运行代码快照，没有重复仿真或重复计算成本。当前请求及运行配置以 `deliverables/research35_prepare_20261021_r02` 为准，r01源快照保留实际本地执行版本。

本地只读审计为 `deliverables/research35_local_report_20261021_r01/SUMMARY.md`，205/205项通过、1169个原生准备产物哈希核验。真实周期标注、真实新SVA和新独立测试尚未执行，不能表述为第1、2项已完成。已请求明确转用research34未用的1次额度并新增最多3次，总上限4次；新独立测试和完整本地答案表不发送，模型请求允许使用实际开发拒绝诊断。当前无新授权记录，不提交远程调用。

```powershell
# 新的本地原生准备，输出目录必须不存在。
wsl -- python3 scripts/research35_campaign.py prepare --out deliverables/research35_prepare_NEW
# 只读复核，不调用模型或仿真。
wsl -- python3 scripts/research35_audit.py --prepared deliverables/research35_prepare_20261021_r02 --out deliverables/research35_report_NEW
# 预算转用及新增额度确认并落盘后运行。
wsl -- python3 scripts/research35_campaign.py run --prepared deliverables/research35_prepare_20261021_r02 --out deliverables/research35_real_20261021_r01 --authorization deliverables/research35_prepare_20261021_r02/authorization.json
```

## 2026-10-22 research35：真实标注两轮均12/13，未进入SVA

用户明确授权转用research34剩余1次并新增最多3次后，实际执行最多两轮周期标注。两轮均返回完整13项、周期编号正确，“是否必须检查”的诊断投影均13/13，但预先固定的 required/cancelled/not_required 三分类均为12/13，因此没有通过第一关，也没有提交SVA生成请求。

- v0：此前 w1 的短背压必须检查问题已纠正；唯一错误仍是 w4（2→3周期，复位后首拍），将 not_required 标为 cancelled。
- v1：实际反馈v0的错误后，w4修正；但 w8（60→61周期，本拍复位取消之前成立的背压义务）由正确的 cancelled 改成 not_required。不能只看本轮修复了哪一项而忽略另一项新错误。

两个错误类别都属于不要求本拍执行保持检查的不同原因。因此这批记录支持“当前13个开发窗口的必须检查/无需检查划分已正确”，不能继续把它表述为仍遗漏必须检查的背压窗口；但也不能在看到结果后把三分类门控改成二分类、追认验收成功。尚未验证新模型SVA、原生目标检出、历史保护及新独立测试。13/13仅是开发窗口诊断，不是泛化结果。

终态 `applicability_unresolved`，保留原冻结哈希 `0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1`。实际2次模型调用，输入19768、输出1032 tokens，无传输重试；新增原生编译、执行、形式化均0。research35准备阶段的10次编译、54次执行单独保留，不冒充本轮模型生成后的回放。授权上限4次中未使用2次，原条件为周期标注全部通过后用于SVA细化，不能擅自转为第三轮标注或跳过门控。

最新报告：`deliverables/research35_real_report_20261022_r02/SUMMARY.md`。170/170记录与一致性检查通过。r01审计同样通过；r02仅增加“是否必须检查”的明确诊断投影和错误项说明，没有修改输入、模型响应、接受标准、决定或冻结版本。原始请求/流式响应/用量位于主运行的 `plan/v*/model_call`，逐轮模型标注及独立判定见 `results.json/plan_iterations`。实际运行目录沿用已经授权的20261021名称，用户侧执行日期为2026-10-22。

```powershell
# 只读复核，不再提交模型请求；输出目录须不存在。
wsl -- python3 scripts/research35_real_audit.py --prepared deliverables/research35_prepare_20261021_r02 --run deliverables/research35_real_20261021_r01 --out deliverables/research35_real_report_NEW
```

## 2026-10-22 research36：事件判断通过，原生防退化仍拒绝新SVA

新增 `scripts/research36_applicability.py`：先核验模型声明的“前一拍已建立输出保持义务”和“当前拍复位”，再核验原有 required/cancelled/not_required 三分类。两项事件必须来自原生采样，并与独立事务 oracle 的周期判断一致。没有放宽 research35 三分类条件，也不追认旧版本通过。新增34项本地正负检查通过；归档原生正、负对照复用 research35，未重复计作新仿真。

用户授权将 research35 剩余2次转用并新增2次后，research36实际调用4次：2次事件/适用性判断、2次真实SVA细化。第一轮模型标签13/13正确，但复位后首拍的当前复位布尔值错误，因此拒绝；第二轮收到实际拒绝后，13个窗口的事件、周期和三分类全部通过。第一项只在这些开发窗口上完成，不宣称一般规格理解能力。

原生SVA版本v0替换a4，使用输入侧条件 `svalid && !sready`，仅检出6/8目标；v1去掉 `!sready` 后检出8/8，但仍使用 `svalid` 和队列头值 `ref_expected`。v0/v1分别产生15/17条义务级误报、均丢失2条历史检出并留下2条关键unknown，均由小批防退化门控拒绝。这些数量是义务×采样证据，不是独立Bug或合法事务场景数。完整113场景回放和新独立测试未执行，不计为通过。

原集合保留，冻结哈希 `0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1`。214/214历史检出是原冻结集合已有记录，不是本轮重新回放的结果。真实输入/输出tokens为56744/1671，原生编译8次、执行44次（含8次冒烟），形式化0，金额不可用。4次授权额度全部使用。

报告：`deliverables/research36_report_20261022_r01/SUMMARY.md`，188/188审计项通过、1033个运行文件纳入内容清单。`case_examples.json`保留两轮每条目标的修改前后证据。审计通过不代替修复通过。

```powershell
# 只读复核，不重新调用模型；使用新输出目录。
wsl -- python3 scripts/research36_audit.py --prepared deliverables/research36_prepare_20261022_r01 --run deliverables/research36_real_20261022_r01 --out deliverables/research36_report_NEW
```

## 2026-10-22 research38：历史数值反馈与接口拒绝诊断

`scripts/research38_history_feedback.py`复用research36真实通过的事件计划，不重新生成计划。模型请求除已确认的漏报配对样本外，还包含实际历史义务级误报和unknown的数值采样；前一轮这部分主要只有证据ID。用户新增授权2次后，两次真实响应均生成含 `!rst` 的前件，触发现有项目属性接口的 `interface_unknown:rst`，没有原生编译或执行。项目接口将时钟/复位留给包装器；这不是原生仿真器不支持rst的证据。没有手工删去rst或修改模型表达式后追认成功。

两次实际响应的Boolean表达式及timing完全相同。发现第二次反馈只有笼统“输出不可用”，漏掉了具体candidate_error，因此新增 `complete_feedback` 转发真实接口/传输错误并标注是否实际原生回放；保留历史采样，避免无原生结果时把历史证据全部丢掉。增加替换操作和目标义务槽检查，防止keep/错误槽提案使后续原生门控崩溃。`deliverables/research38_feedback_check_20261022_r02/verification.json` 的9项检查通过，属于实际错误的反馈回放和明确测试夹具，不是新模型成功；修正后尚未获得新的远程模型验收结果。

真实运行：`deliverables/research38_real_20261022_r01`；报告：`deliverables/research38_report_20261022_r01/SUMMARY.md`。实际远程调用2次，输入31660、输出233 tokens，原生/形式化0。两次均拒绝，旧集合保持；没有新独立测试。与research36合计6次远程额度全部使用。

`deliverables/research36_case_analysis_20261022_r02`另存真实原生失败案例：v0/v1分别15/17条误报全部是输出数据前后相同、但不同于当前参考队列头的观测。沿用research32“仅当前目标所在场景”规则做事后影子判定，v1会被接受，实际包含历史的门控拒绝。这展示一个真实提案上的保护保持作用，但该影子规则不等于包含公共历史场景的完整A/B四组消融，不能扩大为受控机制收益。

```powershell
# 只读复核。
wsl -- python3 scripts/research37_audit.py --run deliverables/research38_real_20261022_r01 --out deliverables/research38_audit_NEW
# 重新准备当前代码对应的真实请求，不调用模型。run另需新的明确额度。
wsl -- python3 scripts/research38_history_feedback.py prepare --out deliverables/research38_prepare_NEW
```

## 2026-10-22 research37与本轮最终状态：第1项通过，第2/3项未完成

远程额度用完后进行了两次本地Qwen 7B有界真实尝试。此前r01/r02只做tokenizer预检，分别发现21752/17303 tokens的输入不能放入16K上下文，没有提交生成。去除重复诊断后仍保留完整RTL与全部配对采样，将上下文提高到24K。

- r03：一次真实调用在900秒超时，无返回文本，最终tokens不可用；进度与缓存计数不补作最终用量。
- r04：使用剩余一次本地尝试，上限1800秒。实际1742秒完成，输入17390、输出141 tokens，观察输入与预检一致，未截断。返回的a2前件为 `(mvalid && !mready) | rst`，后件为 `(mvalid && !mready) => (mvalid && mready)`；项目接口因rst拒绝，未进行原生编译。没有手工修正表达式。两个自启动服务均正常关闭。

本地终态审计：`deliverables/research37_report_20261022_r04/SUMMARY.md`，161项通过。这验证记录与拒绝一致，不是细化成功。原冻结集合保持，新的56场景独立验收没有启动。

最终汇总：`deliverables/research36_38_completion_20261022_r01/SUMMARY.md`，同目录 `task_matrix.json` 和 `results.json`。第1项在13个开发窗口上通过；第2项仍缺少被接受的新SVA；第3项因此未执行。总计6次远程、2次本地生成请求，已知输入/输出tokens小计105794/2045，另1次用量不可用；8次原生编译、44次执行（含8次冒烟），形式化0，金额不可用。4次空提示冷加载管理请求另列，不混为生成。

修复后的反馈与代码快照已准备于 `deliverables/research38_prepare_20261022_r03`，没有提交新远程调用、没有授权文件。继续真实细化需要新的明确额度；不能把当前实现和9项本地诊断测试当作后续模型成功。

```powershell
# 本轮实际最后一次本地调用（输出目录已存在，勿重复覆盖）。
wsl -- python3 scripts/research37_local.py --out deliverables/research37_local_20261022_r04 --iterations 1 --timeout 1800
# 只读复核，使用新报告目录。
wsl -- python3 scripts/research37_audit.py --run deliverables/research37_local_20261022_r04 --out deliverables/research37_audit_NEW
```

## 2026-10-22 research39：结构化 SVA 细化入口（尚待真实修复验收）

复用 `research17_model_schema.py`，新增 `research39_ast_refinement.py`：模型选择完整 Boolean 表达式树、目标槽位和时序关系，本地严格校验后仅添加括号并生成原生 SVA，不推断或替换表达式。两种时序关系及当前接口的采样函数仍可选择。`rst/clk` 继续由包装器处理，不追认旧接口拒绝。远端仍为 JSON 对象输出，不能宣称远端强制执行递归 schema。

新增反馈保留：接口失败、尚无本轮原生结果时，具体错误和上一轮实际历史数值证据一并带到下一轮。复用原有目标、历史、防退化、冻结和独立验收代码，未放宽 unknown 或合法事务误报条件。

本地资格检查 `deliverables/research39_qualification_20261022_r01/verification.json` 36/36 通过，实际 2 次编译、4 次执行（含 2 次冒烟）。这是任意语法夹具的接口/原生传输检查，不是模型细化成功。旧 research38 记录复核 167/167 通过，见 `deliverables/research39_legacy_regression_20261022_r01/`。

真实请求已准备在 `deliverables/research39_prepare_20261022_r01/request.preview.json`；此前远程额度已耗尽，新增最多 2 次授权待答复。第 2 项仍须取得原生目标及 113 场景历史门控接受的新版本，第 3 项只在接受后冻结并产生新的 56 场景、48 种不同激励。新独立样本不进入提示词，不用于候选选择。

```powershell
# 不调用模型，输出目录须不存在。
wsl -- python3 scripts/research39_qualification.py --out deliverables/research39_qualification_NEW
wsl -- python3 scripts/research39_ast_refinement.py prepare --out deliverables/research39_prepare_NEW
# 真实运行需要与输出目录/端点/模型绑定的新授权记录；不是已执行成功记录。
wsl -- python3 scripts/research39_ast_refinement.py run --prepared deliverables/research39_prepare_20261022_r01 --out deliverables/research39_real_20261022_r01 --authorization deliverables/research39_prepare_20261022_r01/authorization.json
```

## 2026-10-22 research39 实跑与 research40 接口续验

用户新增授权 2 次后，research39 实际调用 2 次，输入/输出 tokens 为 36488/514，无重试。两份真实 AST 都给 `&&` 三个参数并引用 `rst`，按原 schema 因二元参数数量拒绝，原生执行 0；原始结果保持拒绝，审计 174/174 通过。不能将后续接口改变追认为 research39 原试验成功。

随后新增显式选择的 `qualified_sampled_reset_v3` 属性接口：允许保留模型给出的 `rst`，并为多项逻辑 `&&/||` 提供等价语法渲染，其他运算符仍要求原有参数数量。没有删去复位条件、替换叶节点、修改时序或人工提供正确性质。旧 profile 仍拒绝 rst。辅助 Icarus 四态逻辑执行完成 256 项结合性检查；实际 FIFO 原生 SVA 复位操作数诊断通过。辅助表达式检查不替代后续原生 SVA。

research40 在运行前固定使用 research39 最新 v1 原始响应，未在旧候选之间搜索，未新增模型调用。其 a2 从当前拍仍 valid 才检查，改为模型选择的前拍保持条件、下一拍检查 valid 与数据保持。8/8 开发漏报在原生回放中触发并检出；113 个完整历史场景通过，214/214 旧检出保留，全部 8 条旧漏报补齐，新增误报和当前关键 unknown 为 0。

冻结哈希为 `47779dad50a32b04bf7d0825c8f9bae6495095b15f30c1758bdbae3d389e1647`。冻结后新生成 seed 762262618 的独立批次，共 56 场景、48 种激励，涵盖 Depth 2/4/8；五义务首个可归因证据共检出 70 条，漏报/误报/当前关键 unknown 均 0。具体检出：顺序 15、排空不丢失 12、无请求输出 7、背压保持 29、复位取消 7。另有 546 条后续违例保留为归因 unknown，不视为全部时间线已保护。没有将独立测试反馈给模型或据此选候选。

research40 原生编译 15 次、执行 372 次（包含 15 次冒烟），另 3 次辅助四态表达式诊断命令；形式化 0，费用金额不可用。真实模型调用成本记在 research39，不重复计算。运行目录 `deliverables/research40_interface_continuation_20261022_r01/`；审计与具体样本见 `deliverables/research40_report_20261022_r01/`。

这属于真实旧响应在明确扩展接口下的有限成功续验，不是新接口下重新生成的模型成功率，更不是多种子稳定性、全局防退化或真实历史父 Bug 已完成。原生 target/history 门控和独立测试的通过标准没有放宽；接口的可表示语法改变单独记录。

```powershell
# 实际执行过的本地续验；重跑请使用新输出目录，无远程调用。
wsl -- python3 scripts/research40_interface_continuation.py --out deliverables/research40_interface_continuation_NEW
# 只读审计，不调用模型、不重新仿真。
wsl -- python3 scripts/research40_audit.py --run deliverables/research40_interface_continuation_20261022_r01 --out deliverables/research40_report_NEW
```

## 2026-10-22 research41：固定新接口的真实细化与三种子复现

新增 `scripts/research41_fresh_campaign.py`，在任何调用前固定支持显式 `rst` 和多参数逻辑运算的 AST 接口、公共初始候选、开发证据及接受标准。沿用已验证的事件计划和契约搜索所得 8 条漏报见证；本轮不将这些旧见证重算为新搜索发现。新增完整历史拒绝反馈，并允许重复实验先全部冻结、再共用一批新独立测试。19 项接口资格检查、测试重用拒绝检查及旧 research39 的 174 项审计通过。

用户授权最多 8 次调用，实际使用 5 次 Highway/Qwen 72B 调用，无传输重试。先导种子 4103 首轮通过目标、113 场景历史回放和独立测试后，才运行固定的 4111/4127/4133 三个种子。前两个首轮成功；4133 首轮把 `$past(mvalid)` 写成信号名，被固定接口拒绝，第二轮根据实际错误自动生成合法 AST 并通过门控。没有运行中改变接口、人工替换性质或注入 research40 的成功答案。

原 a2 是 `mvalid && !mready && $past(mvalid && !mready) |-> mdata == $past(mdata)`。先导及前两个复现种子的真实修改为 `(mvalid && !mready && !rst) |=> ($stable(mvalid) && $stable(mdata))`；4133 第二轮为 `(mvalid && !mready && !rst) |=> (mvalid && mdata == $past(mdata))`。此处为去除冗余括号后的展示，精确原生表达式见各版本文件；时钟和 `disable iff(rst)` 仍由包装器提供。

四个被接受版本各自检出 8/8 开发目标，完整历史回放均保留 214/214 旧检出，旧漏报从 8 降至 0，无新增误报或当前关键 unknown。先导独立批次为 56 场景、48 种输入，检出 62 条，另保留 604 条后续归因 unknown。三个复现版本全部冻结后，在同一批新 56 场景、48 种输入上验证，覆盖 Depth 2/4/8：各检出 67 条，漏报/误报/当前关键 unknown 均 0，后续归因 unknown 各 575。五项义务的首个可归因检出分别为顺序 15、排空不丢失 12、无请求输出 5、背压保持 29、复位取消 6。

预定三个复现种子中，有界细化验收通过 3/3，首轮通过 2/3；先导不混入分母。4111 和 4127 的候选相同，三个接受版本只有两种表达式结构。共同测试批次不能乘以三个候选算作三份独立样本，服务端是否实际按请求 seed 控制随机性也未独立核验。这是当前固定任务上的有限复现，不证明一般模型稳定性、全局保护、机制相对基线收益或真实历史父 Bug 修复。

research40 原冻结版本、测试划分和结果的哈希保持不变；仅使用其输入哈希排除重叠，没有送入模型或转成开发数据。新测试同样没有反馈给模型。报告与原始轨迹见 `deliverables/research41_report_20261022_r01/`，运行目录为 `deliverables/research41_real_20261022_r01/`，预注册请求与授权为 `deliverables/research41_prepare_20261022_r01/`。

本轮实际输入/输出 tokens 为 90813/1257，用量均可获取；原生编译 56 次、执行 1480 次（含 56 次冒烟），形式化 0，金额不可用。获批 8 次中的剩余 3 次未使用，不自动转为其他实验预算。完整成本记录、每个请求、原始响应、编译/执行命令和日志随运行目录保存。

记录审计：四个子实验分别通过 183、183、183、189 项检查，跨种子统一审计 60/60 通过。`SUMMARY.md` 给出汇总，`CASE_TRACES.md` 展示先导及 4133 的真实修改轨迹，`task_matrix.json` 区分本轮完成项与尚未建立的结论。这些审计验证记录一致性，不扩大原生仿真的适用范围。

```powershell
# 实际执行命令；运行目录已经存在，不能覆盖，旧授权不用于重复调用。
wsl -- python3 scripts/research41_fresh_campaign.py run --prepared deliverables/research41_prepare_20261022_r01 --out deliverables/research41_real_20261022_r01 --authorization deliverables/research41_prepare_20261022_r01/authorization.json
# 只读复核，不调用模型、不重新仿真，使用不存在的新输出目录。
wsl -- python3 scripts/research41_report.py --run deliverables/research41_real_20261022_r01 --out deliverables/research41_report_NEW
```

## 2026-10-22 research42：搜索收益的公平复测与覆盖对照

在任何新查询前固定弱初始候选（hash `0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1`）、研究28完整比较候选、种子4201/4211/4217、每方法每种子4查询和112拍预算。普通补测、真正的候选对分歧、原始波形差分、契约曝光分别只使用预先声明的反馈。另在任何主结果出现前固定无反馈的时长覆盖对照，查询时长为0/1/4/16，避免把普通遍历收益误归因于契约语义。

实际四方法48查询均健康，覆盖对照另12查询均健康。普通/分歧/差分/契约/覆盖在三个种子的独立缺口数分别为4201：2/2/2/2/2，4211：0/2/2/2/2，4217：2/2/2/2/2；所有方法跨种子并集均为两类长背压 valid 撤销故障。契约只在4211相对普通多两类，对分歧/差分/覆盖没有新增。契约均在q3发现，分歧/差分在q1/q2/q1发现；本轮没有观察到契约语义独有收益或发现速度优势。不得看到负结果后修改策略再覆盖本轮记录。

全部见证由独立端口历史参考队列判断，原生 cover/failure记录区分a2不触发与a4已触发但约束不足。按候选/义务/故障机制去重，波形与种子变化不计新Bug。主实验当前unknown/误报为0、后续归因unknown803；覆盖对照后续unknown110，保留。该任务是已知人工故障族开发复测，不是新增上游历史Bug。

主实验2次编译、290次执行（含2次冒烟），覆盖对照另2次编译、74次执行（含2次冒烟）；模型/形式化均0。报告 `deliverables/research42_search_report_20261022_r02/SUMMARY.md`，274/274审计通过；r01报告的只读路径错误保留。六条合格处理见证见 `research42_search_20261022_r01/acquired_cases.json`；全部60查询的23种不同输入哈希见 `research42_search_inputs_20261022_r01/exposed_inputs.json`。

```powershell
wsl -- python3 scripts/research42_search.py prepare --out deliverables/research42_search_NEW
wsl -- python3 scripts/research42_search_report.py prepare-sweep --out deliverables/research42_search_sweep_NEW
wsl -- python3 scripts/research42_search.py run --out deliverables/research42_search_NEW
wsl -- python3 scripts/research42_search_report.py run-sweep --out deliverables/research42_search_sweep_NEW
wsl -- python3 scripts/research42_search_report.py report --run deliverables/research42_search_NEW --sweep deliverables/research42_search_sweep_NEW --out deliverables/research42_search_report_NEW
```

## 2026-10-22 research43：同提案的门控对照（已执行，机制效应尚不可估计）

新增 `scripts/research43_paired_ablation.py`、`research43_report.py` 与本地归因负对照 `research43_qualification.py`。三种子各生成普通反馈/带搜索反馈各一次，A/C及B/D分别共享同一个真实提案。全部组允许keep；普通当前门控先记录，历史门控是额外条件，不替代当前检查。只有普通检查接受、历史检查因已确认误报/检出丢失/必需触发丢失而拒绝，才计额外保护；unknown、缺失及身份变化不充作确定收益，9项本地负对照通过。

准备阶段封存六份请求，原生验证六条有效搜索漏报，复用105场景公共历史；A/C不接收搜索见证或13窗口计划。封存历史、资格回放和请求内容哈希。独立回放排除全部42搜索输入及已归档测试输入，所有12臂冻结后才生成共同新测试；完全相同候选共享物理执行，不能当作独立重复样本。

准备r01因开发回放目录未包含core而被旧反馈读取器拒绝，记录和2编译/8执行保留；r02调整新产物目录，未放宽读取器，4编译/18执行通过。准备没有远程调用。用户随后明确授权新增最多6次，research41剩余3次不转用。真实运行目录 `deliverables/research43_real_20261022_r01`；实际完成情况以其outcome和最终审计为准，不能把请求准备当作机制收益。

六次真实调用已全部执行，无重试。五份完整响应的reason分别长161/161/389/233/156字符，超过已封存schema的128字符限制，均接口拒绝；4201/search输出达到1024 tokens而截断。三个普通组均提出keep，两个完整搜索提案均重复a4数据保持性质。只读AST渲染诊断保存在 `deliverables/research43_diagnosis_20261022_r01/diagnosis.json`，没有缩短理由、修改性质或追认接受。后两份重复性质是文本诊断，不声称已执行这些被拒提案。

可进入原生候选验证的提案0/6，普通当前门控通过0/6，故历史门控额外效应分母为0，结果不可估计。A/B/C/D均接受0/3、完整独立验收0/3；不能据此宣称机制收益为0。全部十二臂保留同一弱初始版本，先冻结后执行共同56场景/48输入的新独立测试，物理回放只计一次。Depth2/4/8上，首次归因义务证据48检出、20漏报、0误报、0当前unknown；后续归因unknown565保留。20条漏报均属stall_stability，义务改善与整例通过分开：其余四义务在本批有限曝光下无漏报，整例未通过。证据行不能计为独立Bug数。

research43实际成本为6模型调用、输入124328/输出1685 tokens、5原生编译及117执行（含5冒烟）、形式化0，金额不可用。连同research42主实验/覆盖对照及两次准备，总计15编译、507执行（含15冒烟）。审计90/90通过，见 `deliverables/research43_report_20261022_r01/SUMMARY.md`。research40/41冻结及测试产物哈希未变；本批测试未反馈模型。

后续需另行预注册接口与细化协议：把说明文字长度与可执行AST合法性分开记录，保留完整原始理由；先确认结构接口资格，再在各组相同的迭代预算下把真实重复提案及执行结果反馈模型。本轮不能事后更改128字符规则，也不能只调整这个限制就宣称解决了重复无效提案。搜索侧需要能区分契约语义调度与固定覆盖调度的场景；当前结果只支持已知故障的有限复测。新试验不能复用本轮独立测试调优后仍将其标为独立数据。本次6次额度已用完。

```powershell
# 已获本次六次额度授权并执行；已有输出不可覆盖，旧授权不用于重复调用。
wsl -- python3 scripts/research43_paired_ablation.py run --prepared deliverables/research43_prepare_20261022_r02 --out deliverables/research43_real_20261022_r01 --authorization deliverables/research43_prepare_20261022_r02/authorization.json
# 运行完全终止后只读审计；新输出目录。
wsl -- python3 scripts/research43_report.py --run deliverables/research43_real_20261022_r01 --out deliverables/research43_report_NEW
```

## 2026-10-22 research44/45：接口修正后以真实执行诊断继续细化

`scripts/research44_interface.py` 将说明文字长度与AST合法性分开，原样保留reason。旧research43规则和结果不变。五份完整历史响应全部通过新接口并进入原生执行；三个keep仅通过公共当前证据，两份搜索响应各仍有两个valid漏报并被拒绝。30项资格检查通过，成本0模型、7编译、25执行（含7冒烟）、0形式化。完整结果在 `deliverables/research44_interface_20261022_r01/`。

`scripts/research45_campaign.py` 复用这次原生重复提案诊断进行有界细化，而非把人工修复性质作为模型输出。reason没有128字符语义拒绝，输出预算在首次调用前统一固定2048 tokens；可执行AST其他限制保留。先导最多3轮，每轮检查当前漏报和105场景历史保护；只在新版本接受并冻结后生成56场景新独立测试。独立验收失败则停止本轮后续消融，测试不反馈模型。

若先导独立验收通过，才运行固定种子4411的A/B/C/D四组，每组最多2次，各自真实调用。A/C、B/D首轮请求逐字相同，后续历史门控反馈仅C/D可见，搜索证据仅B/D可见；先导成功性质和诊断不提供给任何组。无门控组的历史保护只在全部冻结后测量。全部组冻结后共同进行新的56场景独立回放，相同候选共享物理执行。此设计是单种子的条件性小规模比较，不能表述为多种子稳定性结论。

首轮五份请求及封存实现：`deliverables/research45_prepare_20261022_r02/`；首版r01因后续完善来源绑定与审计而保留为未调用预览。五份请求的输出预算、二轮反馈隔离及旧独立输入排除预检通过，记录在 `deliverables/research45_qualification_20261022_r01/`。用户明确授权本轮新增最多11次；research41旧剩余额度未转用。实际运行目录 `deliverables/research45_real_20261022_r01/`，最终结果以outcome和报告为准。

```powershell
# 实际调用命令；已有产物不可覆盖，已用授权不能重复消耗。
wsl -- python3 scripts/research45_campaign.py run --prepared deliverables/research45_prepare_20261022_r02 --out deliverables/research45_real_20261022_r01 --authorization deliverables/research45_prepare_20261022_r02/authorization.json
# 终态后只读审计；不调用模型或仿真，使用尚不存在的新目录。
wsl -- python3 scripts/research45_report.py --run deliverables/research45_real_20261022_r01 --out deliverables/research45_report_NEW
```

实际终态为 `pilot_refinement_unresolved`：先导3次真实响应全部原生编译/执行，均为同一可执行AST、均拒绝，接受0/3。每轮当前证据16误报/2 unknown；105场景历史918误报/14漏报/61 unknown。采样行不能当独立Bug数，三轮同场景不能放大样本量。义务判断显示：已接受输出切换到下一事务被误报，valid撤销时前件仍不触发。新独立测试、四组消融都未启动，未用8次只保留作条件满足后的消融预算，不能改为追加先导。

首轮反馈曾因公共场景与历史回放的798个重复稳定证据ID而中断；改为分开保存当前/历史诊断并恢复已完成调用，完整修改记录见运行目录 `amendments/feedback_scope_v1/`。原首轮JSON哈希保持不变，没有重置预算或重跑已完成执行。恢复实际命令在前述run命令末尾增加 `--resume`；旧调用不能凭该参数重复运行。

research45成本3模型调用、输入86052/输出874 tokens、18编译/666执行（含18冒烟）、形式化0，金额不可用；加上research44本地接口验证，合计25编译/691执行。最终32/32记录审计通过，汇总、具体14→15及22→23拍失败轨迹和未完成矩阵见 `deliverables/research45_report_20261022_r01/SUMMARY.md`、`CASE_TRACE.md`、`task_matrix.json`。第1项接口修正完成；第2项有效新细化仍失败，后续两个阶段不能表述为完成。下一步应复用已有独立周期适用性判定流程，在各组信息范围内先验收事件判断，再验收SVA，而非继续只改说明文字。

## 2026-10-22 research46：先验收模型周期判断的执行门控

`scripts/research46_cycle_gate.py` 直接复用research34原生证书、research36事件/适用性验证器，建立11个真实开发窗口；包含research45的14→15合法换事务误报和22→23 valid撤销。第一阶段不含SVA、私有答案或当前valid线索。只有pending/reset布尔值、两个周期和适用标签全部通过独立检查，`verified_sva_request`才允许创建后续请求。模型计划不会被本地答案替换或修正。

SVA生成后另将11个窗口与原生cover/failure周期对应：required窗口必须在该性质的实际前件周期触发，合法窗口不能误报；之后仍须通过目标因果检出、105场景历史保护，才冻结并执行新的56场景独立测试。不是通过标签就接受性质。

准备目录 `deliverables/research46_prepare_20261022_r01/` 保存首轮计划请求、SVA请求基底、公开采样、本地证书和来源哈希。本地31项正负检查通过；新原生窗口门控复核research45已有失败记录，检出4个必需窗口不触发和1个合法窗口误报。准备阶段0模型调用、0新增仿真，不能计为真实模型判断成功。

最多2次周期判断，全部通过后最多2次SVA生成/细化，无传输重试。将research45未用8次中的4次从条件性消融改用于本阶段需要单独授权；其余预算不自动转用。真实结果以新运行的outcome为准。可执行命令及当前状态见准备目录SUMMARY.md，终态用 `scripts/research46_report.py` 独立复核。

用户已授权转用最多4次，实际使用2次周期调用。两轮适用性标签11/11、周期编号22/22、pending事件11/11正确，check拍reset事件10/11正确；均只在w5复位释放（anchor周期2 rst1、check周期3 rst0）返回reset=true。第二轮收到实际单条拒绝反馈仍未修正。该窗口pending=false，not_required标签本身正确，不能把辅助事件字段错误说成全部周期理解失败或新SVA漏报。但本轮既定规则要求全部字段正确，整体门控拒绝，未进入SVA/原生回放/新独立测试，原断言保留。

实际输入19219、输出1140 tokens，新增原生/形式化调用0，金额不可用。202/202记录审计通过。结果、明确采样表和预算范围见 `deliverables/research46_report_20261022_r01/SUMMARY.md`、`CASE_TRACE.md`、`task_matrix.json`。转用额度剩余2次仅用于周期判断通过后的SVA，原research45另外4次仍限条件性消融；没有追加第三次周期调用或事后放宽门控。

## 2026-10-22 research47：将事件字段绑定到明确采样位置

`scripts/research47_sample_binding.py` 新增 `anchor_reset`、`check_reset`、`anchor_pending` 输出字段，逐项绑定公开的 anchor/check 采样。复用 research34 原生证书与 research36 原有事件/标签检查，额外检查锚点复位及证书采样完整性。仅字段重命名投影到旧验证器，不修正模型的任何值。仍要求所有窗口的全部字段正确，包括没有待履行义务的复位释放窗口；research46 的拒绝结果不追改。

正负资格检查覆盖错误布尔值、布尔值类型、周期值与类型、缺失字段、交换两个采样的复位、重复/遗漏窗口、unknown、被改动的原生来源/证书，以及失败计划或伪造通过结果绕过 SVA 请求门控。全部使用已有开发记录和明确标记的本地验证器测试数据；不计为真实模型成功。固定 seed4601、temperature0.2、输出上限2048，与research46相同的11窗口。

本轮运行器仅支持最多2次真实周期判断，通过即停；只有完整通过的真实模型计划才能产生后续 `gated_sva_request.preview.json`。该文件是受门控的请求产物，不代表已调用模型生成SVA。当前任务不执行SVA调用、原生重放或独立验收。真实调用须有本轮明确授权，不能直接消耗research46剩余的SVA专用额度或research45的条件性消融额度。

```powershell
# 本地资格检查及封存，不调用远程服务。输出目录必须尚不存在。
wsl -- python3 scripts/research47_sample_binding.py prepare --out deliverables/research47_prepare_NEW
# 仅在本轮周期调用授权明确后执行；请求、代码和历史产物先验哈希核查。
wsl -- python3 scripts/research47_sample_binding.py run --prepared deliverables/research47_prepare_20261022_r01 --out deliverables/research47_real_20261022_r01 --authorization deliverables/research47_authorization_20261022_r01.json
# 实际调用结束后只读审计；不调用模型。
wsl -- python3 scripts/research47_sample_binding.py audit --run deliverables/research47_real_20261022_r01 --out deliverables/research47_report_NEW
```

实际准备和资格检查状态见 `deliverables/research47_prepare_20261022_r01/SUMMARY.md`、`qualification.json`；未产生真实运行结果前，不宣称周期门控已通过。

用户已明确授权将research46剩余2次转用于research47周期判断。实际首轮1次真实调用即通过全部11个开发窗口：周期编号22/22、三个事件布尔字段33/33、适用标签11/11，合计66/66字段正确。w5返回anchor_reset=true、check_reset=false、anchor_pending=false、not_required；原始响应一致性及23项结果审计通过。通过即停，第二次未调用。输入9414、输出669 tokens，调用耗时49.413秒，金额不可用；SVA调用、新增原生执行、形式化与独立测试均0。完整报告见 `deliverables/research47_report_20261022_r01/SUMMARY.md`。

运行目录通用初始化器曾写入旧protocol元数据，终态后保留原副本并恢复为调用前封存的research47协议，修改记录见 `research47_real_20261022_r01/amendments/protocol_metadata/`。未来运行器增加复制封存协议的修正；实际执行源码快照和所有模型记录保持原样，research46产物哈希不变。不能使用当前源码覆盖重跑已完成的旧授权实验。

该结果只完成开发窗口周期/事件门控。`gated_sva_request.preview.json`仅为通过后生成的后续请求，未执行SVA生成、未接受新断言、未开展新独立测试。剩余1次仍受本轮plan-only及通过即停限制，不自动转为SVA；research45另外4次保留原条件性消融限制。

## 2026-10-22 research48：通过周期门控后的SVA接受检查

`scripts/research48_sva_campaign.py` 复用research47实际通过的原始模型计划和受门控请求；每轮先核验原始响应及全部周期字段，再允许真实SVA调用。沿用现有断言集合及replace_one/keep AST接口，未新增互补断言操作。每个原生可执行提案均检查当前3场景、11个已验证窗口及105个历史场景；即使当前目标检查失败，也完成可执行提案的历史回放，将实际误报、漏报、未知和触发损失纳入下一轮诊断。最多3次SVA调用，无传输重试，通过即停；被拒版本和原因保留，继续保留上一接受集合。逐轮保存义务—断言—触发/违例证据映射，重复已拒可执行性质不接受。

准备r01保留：本地归档成功候选的控制检查最初误传固定a4，实际修改的是a2；RTL与SVA本身未改动。准备r02改为从候选与初始集合的实际性质差异确定修改编号，重新原生执行：旧失败候选a4仍拒绝，旧成功候选a2通过当前目标及窗口检查。二者仅是本地验收器回归对照，旧成功性质未添加到模型请求，不能计作research48新模型成功或完整历史接受。

最终准备在 `deliverables/research48_prepare_20261022_r02/`：14项本地检查通过，初始两个有效漏报经当前原生工具再次确认；research47真实计划与历史105场景绑定已核查。两次准备成本均保留，不将重跑隐藏。真实SVA调用尚待本轮用途明确的预算；research47剩余1次仍是周期专用，research45另外4次仍限原条件性消融。

```powershell
# 本地准备（不调用模型）；必须使用新的输出目录。
wsl -- python3 scripts/research48_sva_campaign.py prepare --out deliverables/research48_prepare_NEW
# 仅在本轮SVA调用额度明确授权后运行；不得覆盖旧输出。
wsl -- python3 scripts/research48_sva_campaign.py run --prepared deliverables/research48_prepare_20261022_r02 --out deliverables/research48_real_20261022_r01 --authorization deliverables/research48_authorization_20261022_r01.json
# 完整终态后只读审计；不重新调用模型或仿真。
wsl -- python3 scripts/research48_report.py --run deliverables/research48_real_20261022_r01 --out deliverables/research48_report_NEW
```

本阶段只验收开发目标与历史保护；接受后冻结也不等于新的独立测试已通过。实际结果须以真实运行目录的outcome、原始响应和原生记录为准。

用户已授权转用research47剩余1次并新增2次，research48实际3次调用结束：v0、v2生成可执行SVA，v1为HTTP400无候选。v0仍重复旧错误性质，当前16误报/2关键unknown，历史105场景918误报/14漏报/61关键unknown；v2加强前件后当前0误报/0关键unknown但仍漏掉2个目标，历史丢失31条检出和1048条触发。两版均拒绝，保留原断言哈希0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1，无新独立测试。完整轨迹、原始SVA、实测目标周期、义务映射见 `deliverables/research48_report_20261022_r01/CASE_TRACE.md`。

445项只读记录审计通过。真实阶段12编译/444执行（含12冒烟），加两次准备合计24编译/492执行（含24冒烟），形式化0；已知token小计输入54855/输出559，但HTTP400调用用量未知，故总用量保持不可用。每版当前后续归因unknown95、历史1177保留，不将其计为通过。

事后修正未来细化流程的一处反馈丢失：无候选的服务/结构错误现在显式保留最近实际原生诊断，并标明属于先前执行，防止覆盖成仅含传输失败的反馈。11项本地检查使用实际v0/v1记录通过，见 `deliverables/research48_feedback_fix_20261022_r01/`。该改动没有重跑模型或改写已完成research48结果；原协议无此修正，原源码快照保留，新逻辑需新的准备及真实调用验证。3次授权已用完，其他受限额度未动用。

## 2026-10-22 research50：受控机制比较

搜索比较复用research42真实原生记录，重新审计274项全部通过。3个固定种子、每方法每种子4次查询；普通补测、真实候选对分歧、原始差分和契约搜索均使用同一候选对、信息边界和预算，另保留固定覆盖对照。按义务与失效机制去重后共两类valid保持缺口。契约仅在种子4211相对普通补测多发现两类；候选分歧、差分和固定覆盖也发现了它们。契约没有显示相对后三者的独有缺口或更低首次发现成本。不能将波形重复数、后续归因unknown算成额外发现。当前只覆盖一个候选对和一个实际FIFO加人工故障，不代表全部11对候选或真实历史父Bug。

逐缺口成本与12项方法对照见 `deliverables/research50_search_audit_20261022_r01/PER_GAP_COMPARISON.md` 和 `incremental_evidence_and_cost.json`。本次审计不新增模型或原生查询；原实验实际成本保留。

新四组实验复用research43配对运行器，使用research44已经检查的接口，消除理由文字128字符阈值对可执行语义的错误拒绝。research43的旧失败结果不修改。research50固定3种子4201/4211/4217，每种子普通反馈和搜索反馈各一次真实调用；A/C共享普通提案，B/D共享搜索提案，用同一提案隔离历史门控决策效应。公共规格、初始候选、采样配置相同；只有B/D看到各自搜索证据。不提供旧成功性质、research47计划或旧/新独立测试。输出上限统一2048，无传输重试。

105历史场景对C/D是接受处理，对A/B是决定和冻结之后的测量，不反馈给模型。全部12逻辑组先冻结，再生成同一批56场景/48输入的独立测试；相同候选哈希共享实际执行，不能扩大统计样本量。keep、不可执行提案、当前检查失败、关键unknown全部保留；有效修改提案的分母单列，无合格修改时历史保护收益不可估计。此实验估计单轮配对接受决策，不等同于多轮自适应细化策略的完整消融。

```powershell
# 只读复核旧搜索；输出目录必须是新目录。
wsl -- python3 scripts/research42_search_report.py report --run deliverables/research42_search_20261022_r01 --sweep deliverables/research42_search_sweep_20261022_r01 --out deliverables/research50_search_audit_NEW
# 本地资格检查、保存输入哈希排除清单、封存请求；不调用模型。
wsl -- python3 scripts/research50_controlled_ablation.py prepare --out deliverables/research50_prepare_NEW
# 仅在新6次调用范围明确授权后执行，不得覆盖已完成目录。
wsl -- python3 scripts/research50_controlled_ablation.py run --prepared deliverables/research50_prepare_20261022_r01 --out deliverables/research50_real_20261022_r01 --authorization deliverables/research50_authorization_20261022_r01.json
# 实际运行终态后审计。
wsl -- python3 scripts/research50_ablation_report.py --run deliverables/research50_real_20261022_r01 --out deliverables/research50_report_20261022_r01
```

准备、运行、审计分开记录；存在脚本和封存请求不表示真实四组实验已执行。research48额度已用完，research45剩余4次仍限制原先导通过后的消融，不自动转用到本协议。

用户随后授权本协议新增最多6次调用，research50已实际完成全部6次、无重试。3次普通反馈均为keep；3次搜索反馈均产生原生可执行修改，但各在当前检查出现21条误报及4条关键unknown，历史105场景各出现1158条误报及109条关键unknown，均拒绝。A/C接纳的是原版本，B/D回退原版本；没有新修改通过。由于3份修改在当前门控已失败，历史门控额外保护收益不可估计，不能将历史拒绝重复计为增量收益。

全部12逻辑组冻结后生成同一新批次：56场景/48输入，Depth 2/4/8，seed 1742451792，与694种旧输入哈希无重叠。所有组保留同一候选，因此只物理回放一次。独立首个归因范围内38检出、20漏报、0误报、0关键unknown；另580条后续归因unknown和7个无首个可归因目标场景明确保留。排空等四项义务在已曝光范围内通过，背压稳定性仍漏20条，整例不通过。本批未用于修改模型或断言；后续若使用失败改善，则需转为开发数据并另做新独立测试。

109项核心结果审计、396项封存/接口附加核验通过，范围仍是单父人工故障FIFO、单轮配对机制实验。真实阶段输入123494/输出981 tokens，38编译/1434执行（含38冒烟）；连同准备42编译/1452执行（含42冒烟），形式化0，金额不可用。共享历史回放对A/B是冻结后测量、对C/D是接受处理；实际token不完全等量。详细结果见 `deliverables/research50_report_20261022_r01/SUMMARY.md`，两个实际失败轨迹见 `CASE_TRACE.md`，分阶段成本见 `cost_roles.json`。此次6次授权已用完，未转用其他受限额度。

```powershell
# 已执行的真实命令（本轮产物已完成，勿覆盖或以旧授权重复调用）：
wsl -- python3 scripts/research50_controlled_ablation.py run --prepared deliverables/research50_prepare_20261022_r01 --out deliverables/research50_real_20261022_r01 --authorization deliverables/research50_authorization_20261022_r01.json
# 从完成记录生成轨迹与成本说明；先运行上文只读audit入口生成新的report目录。
wsl -- python3 scripts/research50_delivery_report.py --run deliverables/research50_real_20261022_r01 --prepared deliverables/research50_prepare_20261022_r01 --report deliverables/research50_report_NEW
```

## 2026-10-22 research51：原始历史修复接入

选择Ibex #166（关联#163），使用父提交c96ece04296c3c69df578d760aa8a66f9b886fef与修复提交3bcbb50630a7cb0278623a8a1f5d262e0220dd86的原始decoder/package。固定URL重新下载的4份源码与归档哈希一致，GitHub提交元数据确认父子关系，补丁应用精确匹配。新原生复现为115事务、458采样、3参数配置：修复前1374检查中423违例，修复后相同检查0违例；两个明确义务均曝光。范围仅原始解码器模块，不是抽象DUT或人工注入，也不冒充整核异常处理复现。

`scripts/research51_history_loop.py`复用真实流式模型接口、原生SVA/cover、独立ISA判定与历史证据门控。初始生成、36事务搜索、115历史事务回放、至多2次细化、接受后冻结及96新指令独立验证通过同一入口运行。手写资格对照不发送模型。首轮文件驱动资格失败保留，第二轮直接周期赋值资格通过，另60项预检通过。完整状态、来源、成本和命令见 `deliverables/research51_report_20261022_r01/SUMMARY.md`。

当前真实模型调用仍为0，初始请求已封存在 `deliverables/research51_prepare_20261022_r02/request.preview.json`，等待新的最多3次用途明确授权。不能把原始RTL复现或本地控制通过写成完整模型历史闭环成功。stat与原始FIFO presented未确认部分继续unknown。

随后用户授权新增最多3次，research51已全部执行，无传输重试。v0接口拒绝；v1使用bit31代替义务要求的bit28，原生历史282漏报、搜索138漏报；v2收到真实开发诊断后新增相同bit31性质，回放无改善并拒绝。两个义务中BRANCH在开发范围内270/270违例检出，OP为0/420；整体没有接受版本，未冻结、未生成独立测试。搜索找到1类有效漏报，但历史已有同类，不能声称额外搜索收益；拒绝原因是未补上当前缺口，不是额外阻止了历史保护损失。原始RTL历史案例完整闭环尚未完成。

166项来源、模型流、原始原生日志及接受决策审计通过。3调用输入60490/输出636 tokens，8编译/8完整执行，形式化0；连同准备和原始复现共18编译/18完整执行。完整终态与实际案例见 `deliverables/research51_final_20261022_r02/SUMMARY.md` 和 `CASE_TRACE.md`。此前准备报告保留其当时状态，不追改为成功。

```powershell
# 本地重建终态审计；须使用不存在的输出目录，无模型调用。
wsl -- python3 scripts/research51_history_audit.py --prepared deliverables/research51_prepare_20261022_r02 --run deliverables/research51_real_20261022_r01 --out deliverables/research51_audit_NEW
```

## 2026-10-22 research52：Ibex位域与适用性门控

`scripts/research52_ibex_bit_gate.py`新增真实SVA生成之前的结构化判断门控，绑定12个原生开发采样，独立验证位号、opcode、funct3、bit28/31、采样/事务字段、前后输出及义务适用性。生成入口重新核验原生来源与判断，不接受伪造通过标志。重复性质在原生编译前拒绝；仅做空白/外层括号归一，不声称一般语义等价。

385项本地正负检查及95项封存/接口隔离检查通过；重新执行115历史、36搜索事务，4编译/4完整执行，复现270检出、420漏报、0误报、0关键unknown。没有新模型调用。最终请求封存在 `deliverables/research52_prepare_20261022_r02/plan_request.preview.json`；拟调用最多2次判断、通过后最多2次SVA，尚待用途明确的新额度。代码和资格通过不等于模型通过。详细任务矩阵、成本、命令见 `deliverables/research52_report_20261022_r01/SUMMARY.md`。

随后用户授权最多4次，research52实际使用2次判断后停止：两次均回答位号28，但各有24个实际数值/适用性错误和24个类型错误，第二次重复同一计划。完整门控未通过，SVA调用0，没有新接受版本。62项真实结果审计通过；输入43925/输出2698 tokens，无重试。剩余2次仅限判断通过后的SVA，未自动转用。详见 `deliverables/research52_final_20261022_r01/SUMMARY.md` 与逐字段 `plan_diagnosis.json`。

## 2026-10-22 research53：程序解码与模型条件选择分工

新增 `scripts/research53_decoded_applicability.py`，复用research52原生门控及调用流程，将确定性位提取改为程序执行，模型只选择义务条件并标注样本适用性。规格条件、独立标签和模型自身规则/标签一致性同时检查；计划不转译为SVA，只有真实计划通过才允许模型生成性质。新信息条件不等于模型自主解码能力提高。

12样本的程序解码与原生SystemVerilog位提取全部一致，1编译/1执行；103项本地正负检查、86项封存与接口检查通过。115历史及36搜索基线按哈希复用，不重复执行或记成本。真实首轮请求已封存在 `deliverables/research53_prepare_20261022_r01/plan_request.preview.json`，本阶段尚无新模型调用。完整状态与命令见 `deliverables/research53_report_20261022_r01/SUMMARY.md`。

2026-10-23用户授权后，research53实际使用2次判断：12标签及OP条件均正确，但两次BRANCH规则都为[3,1]而非[2,3]，整体门控拒绝，SVA调用0。72项终态审计通过，输入42592/输出694 tokens，无重试。终态见 `deliverables/research53_final_20261023_r01/SUMMARY.md`。

research54另建局部合成接口 `scripts/research54_complementary_sva.py`：固定原模型a0的270个BRANCH原生检出保护，仅复用实际正确的OP子判断，让模型生成OP性质。research53整体失败不追改；仍要求151事务完整原生接受，并增加不受义务声明过滤的所有性质误报检查。24项本地检查和89项预检通过，真实请求封存在 `deliverables/research54_prepare_20261023_r02/request.preview.json`，模型调用0。转用剩余2次需另行确认，详见 `deliverables/research54_report_20261023_r01/SUMMARY.md`。

2026-10-23用户明确授权后，research54转用2次均已执行，无重试：v0多一层output包装，v1使用未声明instr_new_i，均接口拒绝；两版性质仍引用bit31。没有新原生执行、接受版本或独立测试。输入46075/输出486 tokens，96项终态审计通过，本轮额度用完。新增 `scripts/research54_result_audit.py` 核对原始流、请求、拒绝和用量并提供具体离线诊断，不修改实际提案。终态与两版轨迹见 `deliverables/research54_final_20261023_r02/SUMMARY.md`、`CASE_TRACE.md`。这不是新保护成功，也不是防退化的增量收益。

```powershell
# 离线复核，无模型调用；输出目录须不存在。
wsl -- python3 scripts/research54_result_audit.py --prepared deliverables/research54_prepare_20261023_r02 --run deliverables/research54_real_20261023_r01 --out deliverables/research54_audit_NEW
```

research55新增 `scripts/research55_native_plan_alignment.py`：严格接口诊断之后，先用绑定的4个开发事务/12窗口在原始前后RTL上检查实际适用周期、触发与目标检出，通过才进入完整151事务接受。24项本地检查和200项原始日志/封存预检通过；正确本地对照通过，旧bit31、仅首周期和恒真后件对照均实际拒绝。8编译/8完整执行，模型调用0。请求封存在 `deliverables/research55_prepare_20261023_r01/request.preview.json`，新增最多2次模型调用尚待授权；正负对照不发送，不计作模型成功。详细结果与命令见 `deliverables/research55_report_20261023_r01/SUMMARY.md`。

随后授权2次均已执行：两版通过接口与原生编译执行，但每版OP仍0/12检出、24条必检未触发，均拒绝；v1仅重排同一组谓词。完整151事务及独立测试未启动，无接受版本。197项终态审计通过，真实阶段输入48622/输出410 tokens，4编译/4执行，形式化0，额度用完。终态、具体反例与成本见 `deliverables/research55_final_20261023_r01/SUMMARY.md` 和 `CASE_TRACE.md`。

```powershell
# 无新增模型或仿真调用；输出目录须不存在。
wsl -- python3 scripts/research55_result_audit.py --prepared deliverables/research55_prepare_20261023_r01 --run deliverables/research55_real_20261023_r01 --out deliverables/research55_audit_NEW
```

research56新增 `scripts/research56_fresh_op.py`，首轮仅保留固定BRANCH作为当前断言，要求模型从实际OP子判断、原始RTL与原生诊断重新生成OP；错误OP不再作为可编辑模板，但旧基线仍用于完整接受比较。顺序无关去重接入真实模型输出入口，可拒绝旧性质重排和轮内重复。22项本地检查及96项预检通过，复用未改变的research55原生门控；新模型/原生调用0。请求在 `deliverables/research56_prepare_20261023_r01/request.preview.json`，最多2次新调用尚待授权。详见 `deliverables/research56_report_20261023_r01/SUMMARY.md`。

research56随后实际使用2次授权请求：v0真实新性质通过小范围门控并完成151事务，OP420/420和BRANCH270/270，但历史226＋搜索84条合法误报而拒绝。v1反馈请求返回HTTP400，无提案、无重试。165项终态审计通过，6编译/6完整执行，已知tokens24703/367，失败调用usage不可用，总量保持null。没有接受、冻结或独立测试版本，额度耗尽。详见 `deliverables/research56_final_20261023_r02/SUMMARY.md`、`CASE_TRACE.md`；离线复核入口为 `scripts/research56_result_audit.py`。

research57增加真实合法误报事务的前置回放和有界反馈：过宽模型性质在扩展7事务上检出27目标但误报72条而拒绝，本地正确对照27检出且误报0；4编译/4执行。完整690目标证据保持清单仅存本地。最终r02请求73731字节，旧反馈重建79357字节，提交前上限79498；不据此声称HTTP400根因已确认。15项准备及182项预检通过，新模型调用0，最多2次新调用待授权。代码 `scripts/research57_legal_refinement.py`，请求 `deliverables/research57_prepare_20261023_r02/request.preview.json`，报告 `deliverables/research57_report_20261023_r01/SUMMARY.md`。

research57随后获批的2次真实调用均已完成，输入45090/输出544 tokens，无重试，额度用完。两版多带id字段，被封存接口拒绝；182项结果审计通过。新增 `scripts/research57_label_replay.py` 单独接受可选标签元数据，保持全部真实模型谓词、时序及固定BRANCH不变，不修改原失败记录。两版各完成151事务、3996记录的原始RTL回放与原生日志审计：OP318/420、BRANCH270/270；v0误报126、v1误报270，各丢失102个既有OP检出点、204必检未触发、0关键unknown，均拒绝。新增8编译/8执行，形式化0；没有接受、冻结或独立测试。具体真实轨迹、成本和本地复核命令见 `deliverables/research57_final_20261023_r01/SUMMARY.md` 与 `CASE_TRACE.md`。这些语义诊断是在两次调用后另行得到，不能声称已作为第二次模型反馈。

research58将这些实际误报和保护丢失样本绑定到联合反馈，正式接受可选id元数据且不修改谓词，增加funct3=2/3的真实漏报事务，并显式检查全部420OP＋270BRANCH检出ID保持。扩展9事务240记录原生前置回放：旧v0检出27/48、误报12；旧v1检出27/48、误报72；本地正对照48/48、误报0，均无unknown。6编译/6完整执行，模型0；92项准备和354项预检通过。首次请求大小超限记录保留，压缩重复代表后封存请求75788字节，未发送。最多2次新的真实调用尚待授权，旧额度未转用。详见 `deliverables/research58_report_20261023_r01/SUMMARY.md`，请求 `deliverables/research58_prepare_20261023_r01/request.preview.json`；仍无新接受、冻结或独立结果。

随后research58两次明确授权调用均已使用：首轮真实模型OP21/33、BRANCH15/15、误报0、目标漏报12、必检未触发24、unknown0，原生门控拒绝。同场景恢复21个检出点却丢失12个旧检出点。第二次请求最初在发送前超本地大小上限，另封存77428字节的去重诊断并在同一授权内用剩余1次；模型逐字重复首轮，编译前拒绝，无额外调用。首轮360项、继续调用34项结果审计通过。输入47647/输出694 tokens，真实2编译/2执行，含准备8/8；完整151、冻结、独立测试未执行，额度耗尽。结果和失败轨迹见 `deliverables/research58_final_20261023_r01/SUMMARY.md`、`CASE_TRACE.md`；继续运行脚本为 `scripts/research58_continue.py`，原封存运行失败不追改。

research59增加明确的12点首周期/保持阶段原生门控：0x50b1e633的4采样×3配置，首周期3点、保持9点，严格绑定instr_new、事务、phase及原始前后输出，不虚构decoder握手。原有9事务门控与完整151/690检出保持标准不变。真实research58模型重放0/12；本地正对照12/12、全9事务48/48且误报0；仅首周期对照3/12被拒绝。6编译/6执行，模型0；183项准备和363项预检通过，错误采样/缺行/unknown拒绝。首轮/已知失败反馈请求77137/78552字节，未发送。新额度待授权，正对照不作为模型成功。详见 `deliverables/research59_report_20261023_r01/SUMMARY.md` 与 `scripts/research59_phase_gate.py`。

research59随后获批2次均已提交：v0在180秒超时，无响应/用量；v1实际新性质原生执行后聚焦首周期0/3、保持0/9、必要触发0/24，全9事务36/48检出、12漏报、误报0、unknown0，拒绝。性质保留矛盾前件并追加条件，文本变化未形成新保护。356项真实结果审计通过，已知tokens23910/428、总量不可用；真实2编译/2执行，含准备8/8，形式化0，授权耗尽。完整151、冻结及独立测试未执行。详情 `deliverables/research59_final_20261023_r01/SUMMARY.md`、`CASE_TRACE.md`；只读复核入口 `scripts/research59_result_audit.py`。

research60实际尝试本地缓存模型：Qwen7B完整源码请求取消，精简源码的新生成及真实误报反馈均原生检出聚焦12/12（首3/3、保持9/9、必要触发24/24），全9事务48/48目标检出，但各有78条合法误报、unknown0，因此拒绝；反馈后逐字重复。DeepSeek6.7B返回未声明opcode，接口拒绝、未编译。新增4次本地生成提交（1取消、3完成）、4次加载管理请求，远程0、原生4编译/4执行、形式化0；已知tokens13558/462，取消用量未知，总量null。三项审计分别164/169/159项通过。未进入完整151、冻结或独立测试。精简输入为源文件绑定OP块和可逆差分，原生DUT保持完整源码；更换模型及输入范围属于探索性试验，不作为受控收益。报告 `deliverables/research60_final_20261023_r02/SUMMARY.md`、`CASE_TRACE.md`，复核 `scripts/research60_local_audit.py`。小范围门控仍未通过，旧失败与接受版本保持不变。

research61增加实际合法/违例解码对照，18组与240条原生记录逐项核验；两轮真实本地文本提案仍重复旧funct3性质，跨运行去重在编译前拒绝。复用research17语法树渲染器，真实Qwen随后选出bit28检查，首3/3＋保持9/9、触发24/24、全9事务48/48、误报0和unknown0，小范围门控首次在本轮通过；完整151事务保留420 OP＋270 BRANCH检出，却因缺少opcode适用范围而出现636条历史合法误报，搜索误报0，全部unknown0，最终拒绝。再向模型反馈实际历史合法BRANCH首/保持误报，仍逐字重复AST，编译前拒绝。新增本地生成4次、加载3次、远程0，原生6编译/6执行，形式化0，tokens26022/628。审计178/170/171项通过；旧记录不改写、没有新接受/冻结/独立测试版本。详情 `deliverables/research61_final_20261023_r01/SUMMARY.md`、`CASE_TRACE.md`。本地模板只读检查未发现固定硬件响应，但不能据此确定重复提案的模型内部原因；记录在 `deliverables/research61_model_metadata_20261023_r01/check.json`。

research62得到开发阶段新接受版本。两轮类别AST仅返回裸opcode字段，各在4236条开发分类检查中错分2304条，原生前拒绝；随后明确比较接口由真实本地Qwen选择field=instr[6:0]、comparison 为 ==、value=51、combine=&&，程序原样组合到research61真实模型bit28子AST，保留原BRANCH。类别4236/4236、小门首3/3＋保持9/9、必要触发24/24、误报/unknown0；完整115历史＋36搜索共3996条记录，420 OP＋270 BRANCH全部检出，误报/漏报/关键unknown及必要未触发均0，通过接受。新候选内容哈希 `1eadd56767c2cc9f1f4e1c8b7ff77f5683b9adf420a1cd9d0cfa4ce61e9f4043`，路径 `deliverables/research62_comparison_20261023_r01/accepted_candidate.json`。这是保留模型已生成子性质的组件细化，不是人工补齐opcode或自由重生成整条SVA。本次合计本地生成3次、加载管理2次、远程0、原生6编译/6执行、形式化0，tokens13449/244；失败审计173项、成功审计174项通过。旧636误报版本保留。尚未执行新冻结后独立测试，结论限原decoder有限开发范围。报告 `deliverables/research62_final_20261023_r01/SUMMARY.md`、`CASE_TRACE.md`；入口 `scripts/research62_comparison.py`，原始模型选择及实际SVA位于该运行v0/model_call。

research63执行冻结后独立验收，research62接受集合哈希1eadd56767c2cc9f1f4e1c8b7ff77f5683b9adf420a1cd9d0cfa4ce61e9f4043保持不变。先重新通过174项开发接受审计，核查225份事务/采样/请求文件，排除151个已用词。首批r01新96词原生检出960/960且误报/漏报/unknown为0，但预设曝光规则错误要求BRANCH首周期出现历史缺陷，因此仍记录未通过。原始源码证明该缺陷仅在BRANCH保持阶段出现；首周期应检查正确输出与实际触发。r01整批转为协议开发数据，不追改通过。新增scripts/research63_phase_qualified.py封存阶段适用规则，8项正负检查通过；排除247词、重新冻结后生成r02全新96词，覆盖四配置（新增E1/M0）、首周期/保持以及bit28=1合法BRANCH。r02实际4224条记录，OP528/528、BRANCH432/432，必要触发、合法控制、全性质归因检查通过，误报/漏报/unknown/必检未触发均0。原始日志逐行复核通过；r01和r02均保留冻结哈希、波形、工具命令及成本。本轮合计原生4编译/4执行、模型调用和tokens为0、形式化0。报告deliverables/research63_independent_20261023_r02/SUMMARY.md、CASE_TRACE.md；只读复核：wsl -- python3 scripts/research63_phase_qualified.py audit --out deliverables/research63_independent_20261023_r02。结论限原始decoder有限独立样本，不代表整核、FIFO或形式化证明；不据此声称两个研究机制的受控增量收益。

research64已完成公共反馈新颖性、反馈选样、候选/机制扩展及成本实跑。新增scripts/research64_search_value.py复用research15义务缺口Policy、research42双候选原生见证核验、现有FIFO运行器与事务oracle。采用research20、research27/41公共初始、research28三个不同真实模型集合，三主候选方向（不计方向仅两候选对）、Depth4/Pipeline1、两种子、五方法各四查询；三个方向均通过公共资格检查。先冻结overlap/短背压全部故障公共反馈，再执行120查询。原有解除边界valid漏报不重复计新；长短valid撤销合并为同一机制，共7故障模式/5种机制。契约24次选择有21次区别于固定覆盖；同随机状态的反馈反事实诊断有21次改变选样，诊断不算搜索发现。公共之外候选相关缺口并集：普通5、真正候选对分歧4、普通差分4、契约4、固定覆盖5；契约独有0，并遗漏普通/固定覆盖找到的stall_glitch缺口。部分种子首发现更早，但不能宣称总体优势。历史索引只覆盖审计的research30/42，未命中保留全历史新颖性unknown。较完整候选未找到新漏报。实际3编译/2019执行（96公共、1920搜索、3启动），模型/tokens/形式化0；2016次事务参考、2016次采样参考、882次配对义务判定全部实测计费，审计重算另列。508项审计复核2016份原生日志通过；关键归因unknown0，但五方法后续归因unknown分别1656/1479/1479/749/1605，全部保留。总报告deliverables/research64_final_20261023_r01/SUMMARY.md、CASE_TRACE.md，逐缺口首发现成本per_gap_first_cost.json；入口和复核命令见报告。未读取research63独立输入，旧无收益结果不改写。本轮仍是单父人工故障开发实验，未完成旧11对全原生验证或证明契约总体增量收益。

research65（2026-10-24）修正已曝光义务反复占用搜索预算：新增scripts/research65_search_policy.py，将确认缺口保存到细化队列、降低其获取证据的优先级；按场景族/背压时长记录尝试，公共及已执行动作不重复，保留未试边界，unknown不视为解决。原research64脚本与结果保持不变。33项本地检查通过后重新封存协议，新种子6503/6521、3个有向候选任务、7种策略、各4查询，增加普通不重复选择对照。168查询实际完成，3编译/2787执行（96公共+2688搜索+3启动），模型/tokens/形式化0；700项日志审计确认2784份原生记录，42组/168步策略重放一致。

实际结果：旧契约24次查询有11次重复已执行动作，新契约0次；公共之外候选相关去重缺口旧4、新5、普通不重复4、固定覆盖5、普通4、真正候选分歧3、普通差分0。新策略未减少总查询预算，只将其分配给未试动作；无新增缺口查询仍有19/24，不能把所有零新增查询直接判为浪费。新契约相比全部对照并集独有0：pre_valid/6503的新stall_glitch发现未在6521复现，后者由固定覆盖独有，不能宣称总体或稳定成本优势。关键归因unknown0，但后续归因unknown保留（新契约1374、旧契约753），不计为有效发现或全程保护。动作去重也可能错过同类场景换数据后的有效证据，属于有界探索取舍。

协议、逐步选择、公共缺口排除、波形、参考判定与全部成本位于deliverables/research65_search_value_20261024_r01；原生日志审计和具体轨迹位于deliverables/research65_audit_20261024_r01。总成本包含事务参考、采样参考、配对义务判断；审计重算另列。全部为单父axis_fifo人工故障开发比较（Depth4/Pipeline1），未修改SVA、未进行新模型细化、未读取冻结后的独立测试，也未推广为真实历史缺陷或形式化证明。复跑用新目录依次执行scripts/research65_search_value.py prepare、run；复核使用scripts/research65_result_audit.py --run <运行目录> --out <新的审计目录>。每条命令以wsl -- python3开头。

research66（2026-10-24）完成research61/62回顾性配对审计，不新增模型或仿真调用。新增scripts/research66_paired_audit.py，先封存回顾规则和原始源哈希，再复用真实响应流、AST转换和原生日志审计。固定R0为接口/去重＋当前9事务小门＋已获得36搜索事务；同一research61_ast/v0在R0下接受，加入115历史事务后拒绝，新增636条合法误报涉及26个指令字。若普通规则本身也读取完整151事务且要求零误报，则同样拒绝；仅删除相对新误报理由仍有绝对全范围检查拒绝。历史合法曝光有增量，但不能将同一批误报的多个拒绝理由当作多项机制收益，也不能声称当时实际运行了普通接受臂。

拒绝后原始共享集合保留BRANCH270/270、合法误报0，但OP仍0/420且840个必要采样未触发；这是部分可用组件，不是上一完整接受版本。原运行没有持久active-version/rollback日志，确认源文件保留和runner发布条件，不补造回滚事件。research62后续真实组件细化接受，OP420/420＋BRANCH270/270、误报/漏报/unknown/必检未触发0；从research61 AST提案起共5次生成（拒绝后4次），tokens24842/562、原生12编译/12执行、模型管理4次。各阶段1+1+2+1单独上限及表示接口改变，不能追认为统一预设预算成功；包括此前两次文本失败，research61+62全阶段共7次生成。

32项配对/状态、11项规则正负检查通过，4段真实运行共688项审计通过，另复核基线3996条原生记录。报告、候选哈希、逐条保护ID、误报样本及预算在deliverables/research66_paired_audit_20261024_r01/SUMMARY.md及同目录JSON。全程标明回顾性；新案例/种子、统一控制器/表示/预算、active版本日志及冻结后新独立测试的前瞻性验证尚待执行。复核依次运行wsl -- python3 scripts/research66_paired_audit.py prepare --out <新目录>与run --out <同目录>，无新增模型/原生执行。

research67（2026-10-24）继续受控验证，封存统一AST/组件接口、公共规格、原生周期门控及先导通过后才启动的三种子协议。明确区分共享真实提案的单轮门控决定效果与独立多轮四组策略效果。先导种子6703的五方法各4查询完成，公共2查询共用：搜索2编译/354执行（352查询执行＋2编译自检），352份原生日志及92项重算检查通过；355项配对、请求隔离、门槛与版本保留检查通过。契约搜索第1查询获得公共之外的持续背压valid撤销见证，但五方法各仅发现同一个去重缺口，契约独有0；普通不重复搜索同样0重复，不能把避免重复单独归于契约。关键unknown为0，后续归因unknown继续保留。

原生资格回放确认公共解除边界漏报1个、搜索新增持续背压漏报1个，二者均已在相应模型请求中出现。前三次本地编排失败保留在prepared、prepared_v2、prepared_v3；prepared_v4修复正确对照目录复用、扩展故障模式作用域及core开发路径适配，未放宽隔离或改写断言。新的最多3次先导授权实际发送1次，HTTP400，无候选、无token用量；第2个预算预留在发送前被保守token预算拦截，因此不能计为2次调用。继承传输器未保存HTTP错误正文，拒绝原因unknown。已新增、仅本地验证脱敏错误正文采集及传输失败即停适配器，未自动重试或转用余下2个授权槽。

先导未通过，105历史候选验收、新冻结独立测试、多种子及四组实验均未启动；原始部分保护基线仍保留。research63 r02按字节哈希保持不变，未用于请求或调参。最新报告为deliverables/research67_terminal_20261024_r01/SUMMARY.md；此前research67_audit报告只是模型调用前快照。协议和请求在deliverables/research67_controlled_20261024_r01/protocol.json及prepared_v4/s6703/search/request.preview.json，真实HTTP记录在pilot_run/refinement/core/v0/model_call。只读复核（新目录）：wsl -- python3 scripts/research67_terminal_audit.py --run deliverables/research67_controlled_20261024_r01 --out deliverables/research67_terminal_audit_NEW。下一步须解决服务拒绝并封存新先导；不能用本轮HTTP失败推断模型或两个机制的效果。

research68（2026-10-24）继续诊断research67服务拒绝。发现旧HTTP错误采集夹具只拦截urlopen，而真实传输走OpenerDirector.open；新增适配器在真实父类call路径用显式HTTP夹具核验采集和密钥脱敏。公共重复诊断由约211KB压缩到搜索请求46941字节，RTL、规格、AST接口、当前性质、原始目标相邻采样、模型与种子均保持，普通/搜索两组公共投影一致；9项本地检查通过。使用此前3次授权的第2个实际调用，服务在响应头返回前等待180秒后transport_timeout，没有候选、没有新增原生仿真或独立验收、token用量不可用，按规则立即停止，未自动重试。原HTTP400原因仍无法恢复，不能认定压缩请求已解决服务问题。

新增一次同源只读/openai/models查询约0.94秒成功，目录182项中仍列出qwen/qwen-2.5-72b-instruct；这只确认模型目录和认证可访问，不证明生成端点健康。结果分别在deliverables/research68_audit_20261024_r01/SUMMARY.md、research68_service_metadata_20261024_r01/result.json。本轮总先导实际调用累计2/3，余1次。research69_prepare_20261024_r01封存仅将180秒上限延至300秒的单次诊断请求，已逐字核对传输源码唯一差异；需显式确认将最后1次用于新用途，尚未调用。新原生日志审计入口对既有30份记录复算通过，不能算新模型修复或独立成功。先导目标、105历史和新独立验收通过前，多种子两类消融继续关闭；research63保持原状。

research69（2026-10-24）随后获准转用最后1次，真实请求在193.04秒返回，无重试；输入13065/输出313 tokens。模型仅将a4改为背压后下一采样同时保持mdata和mvalid，其余四条性质不变，未人工改写谓词。两处目标（公共解除边界与搜索持续背压）均经独立事务判断、原生触发及因果检出检查通过；15个开发场景共4个义务采样检出、0误报/漏报/关键unknown。105历史场景保持214检出、0误报/漏报/关键unknown，新集合正式接受。

冻结哈希ef3974b9ac0dd7a79f008564d7af4a43b77e9befdc1da93bfb4ba79543bca3da；排除553个已用输入哈希后，新生成56场景/48个不同输入，覆盖Depth2/4/8及各预定配置。独立五义务均有实际曝光：顺序19、排空12、无请求输出6、背压稳定30、复位取消7，共74检出，误报/漏报/关键unknown0，后续归因unknown548保留。先导通过有限第一违例归因范围的验收，不代表全局保护、真实历史缺陷或形式化证明。实际10编译、362执行（含10启动自检）、形式化0；本轮3次先导额度累计用完，之前HTTP400及180秒超时记录和未知用量继续保留，不倒推旧服务失败原因。

产物在deliverables/research69_pilot_20261024_r01，审计入口为scripts/research69_result_audit.py audit；只读复核命令：wsl -- python3 scripts/research69_result_audit.py audit --prepared deliverables/research69_prepare_20261024_r01 --run deliverables/research69_pilot_20261024_r01 --out deliverables/research69_audit_NEW。原排除扫描耗时较长，另建scripts/research69_exclusion_index.py，快速文件索引与原封存流程的哈希集合及来源逐项一致，记录在deliverables/research69_exclusion_index_20261024_r01/comparison.json；没有修改本轮封存执行规则。单个先导同时通过普通与历史门控，不是防退化额外拒绝收益；搜索的去重缺口也由对照找到，不能据此宣称两个机制已有受控优势。

research70（2026-10-24）在research69通过且352份原始记录、15项主审计与5项附加检查完成后，启动预先规定的6711/6719/6733三种子本地比较。共享原公共候选与反馈，五方法各4查询，共60搜索＋6公共查询；契约每种子第1查询发现1个公共之外持续背压缺口，普通与不重复选择也都在第1查询发现，三个种子相对全部对照并集的契约独有均0。缺口是已知人工故障，不能把三种子或波形变体算作三个独立Bug；没有稳定额外收益的结论保留。关键unknown0，后续归因unknown按方法保留。

三份新搜索见证各完成原生资格检查，六份普通/搜索请求封存在deliverables/research70_multiseed_20261024_r01/ready/s6711、s6719、s6733的ordinary/search/request.preview.json。固定AST/组件生成/原生周期检查/公共投影，搜索证据仅搜索组可见；不提供research69成功候选或独立测试。共12编译、1158执行（含12启动自检）、模型与形式化0；1146份原始记录及请求隔离审计通过。跨种子并行，墙钟时间不当作严格隔离性能优势。报告与成本在deliverables/research70_audit_20261024_r01/SUMMARY.md、cost_totals.json；只读复核入口scripts/research70_prepare_audit.py。

两类模型消融尚未运行：共享提案的单轮配对最多6次，独立多轮各组分别调用最多24次，目的与结论分开。旧先导3次额度已耗尽，本轮未自动使用任何其他旧额度；下一批须独立授权。各组冻结后才生成新的共同独立批次，不能把research69独立验收作为新组间验收。复用preflight适配器中failed_preparation/old_failure_preserved字段描述的是旧research67修正背景；本轮三个新种子没有失败准备，不能把该继承字段当作新增失败实验。

research71（2026-10-24）随后获得并用完明确授权的6次真实调用，三种子6711/6719/6733各普通、搜索一次，无重试、无传输失败。新增scripts/research71_paired_run.py复用封存的research70请求，19项本地检查通过；A/C与B/D共享真实提案，普通决定先保存，再检查105历史场景，持久记录接受或拒绝后的active版本。模型输出仅语法组装，不人工修改谓词。普通提案接受2/3、搜索1/3；加历史门控后分别仍为2/3、1/3。额外拒绝0/3（分母为普通规则接受的真实提案）；其余三份提案已被普通规则拒绝，历史检查虽发现更多误报与unknown，也不能计为增量拒绝收益。

12个组全部冻结后才生成共同新独立批次：种子676789395，38个边界场景（Depth4/8）及18个排空场景（Depth2/4/8）；排除既有开发与已用测试输入。四个完整候选哈希分别物理回放，共享同哈希结果不增加独立样本数。三份接受版本各保持105历史场景214个检出点，在新测试中五义务均有曝光，检出70/70、误报/漏报/关键unknown为0；各保留573条后续归因unknown。拒绝后保留的部分保护基线为50/70，20个漏报均属背压稳定性，无误报或关键unknown。因此A/C新独立通过各2/3，B/D各1/3。独立结论仅限预定第一违例归因范围，不是全局保护或形式化证明；该批测试未用于后续生成或选择。

实际成本：输入75331/输出1768 tokens，模型6次；原生50编译、1932执行（含50启动自检），形式化0，命令失败/超时0。模型耗时124.66秒，编译488.15秒、执行45.28秒；金额及原生回放内未单独计时的参考判定耗时不可用。搜索获取及资格成本另列research70，不能从本轮成本中隐藏。原生日志1882份、186项只读审计通过，research63及此前失败记录保持原状。

本轮未观察到契约搜索或历史门控的额外收益；搜索1/3与普通2/3是三个固定种子的描述结果，不能据此推出一般性负效应。共享提案实验只检验单轮接受决定，独立多轮策略效果尚未验证，额外最多24次调用未授权、未执行。结果与两个实际案例见deliverables/research71_audit_20261024_r01/SUMMARY.md及CASE_TRACE.md；完整请求、原生记录、冻结集合和波形在deliverables/research71_real_20261024_r01。只读复核（输出目录须不存在，不新增模型或原生调用）：

```powershell
wsl -- python3 scripts/research71_paired_audit.py --prepared deliverables/research71_prepare_20261024_r01 --run deliverables/research71_real_20261024_r01 --out deliverables/research71_audit_NEW
```

research72准备独立多轮策略消融，新增scripts/research72_policy.py及research72_policy_checks.py，复用research67/70已固定的三种子、四组、每组最多2次协议。12份首轮请求与research70对应请求一致；各组实际响应独立，历史诊断只反馈C/D，组内重复提案在编译前拒绝，传输失败即停且不重试。拒绝保留基线，全部12组冻结后才进行历史/搜索目标统一测量及共同新独立测试。r01仅控制流程夹具的非执行性质触发序列化错误，失败记录保留；修正夹具边界后r02的176项检查通过、300份原生日志重算通过，封存哈希复核通过。本轮真实模型调用0、原生新执行0，不将夹具结果算成模型成功。

research71结果保持不变，独立批次只参与输入哈希排除，排除清单689项；没有使用该批结果调整候选、请求或规则。实际最多24次调用尚待新授权，未创建授权记录或启动实验。准备报告、协议和12份首轮请求位于deliverables/research72_prepare_20261024_r02，第二轮请求仅在真实拒绝后按封存构造器产生。只读复核：wsl -- python3 scripts/research72_policy.py verify --prepared deliverables/research72_prepare_20261024_r02。

research72随后获批最多24次并实际执行21次，三种子×四组独立多轮实验全部完成，无重试、无传输失败。A/B/C/D新提案接受分别1/3、2/3、0/3、0/3，实际调用5/4/6/6。三份接受版本均首轮产生；九次第二轮均未接受，其中七次重复性质在编译前拒绝。C/D没有普通规则会接受的提案，额外历史拒绝分母0，不能声称验证了防退化增量，也不能认定门控无用。B本轮2/3高于A1/3只是小样本描述，普通版本也检出全部搜索目标，尚不能证明契约搜索稳定额外价值。没有将剩余3次转作额外尝试。

所有12组冻结后，四个不同完整候选哈希分别进行105历史、三种子搜索目标及新公共独立批次测量。独立种子834866262、56场景/48输入，边界Depth4/8、排空Depth2/4/8；三份新版本各79/79检出、五义务均有曝光、无误报/漏报/关键unknown，保留基线59/79、仍有20个背压漏报。各版本保留522条后续归因unknown。所有最终版本（包括部分基线）均保持历史214点，因此历史通过不能代替新缺口修复。历史和搜索测量后续归因unknown分别1177及2保留。新独立通过A/B/C/D分别1/3、2/3、0/3、0/3，同哈希共享回放不增加独立统计样本。

输入316393/输出5802 tokens，用量缺失0；实际78编译、3054执行（含78启动自检），命令失败/超时0，形式化0。新只读审计脚本scripts/research72_policy_audit.py复核2976份原生日志及433项检查通过，逐轮验证请求/原始响应、历史反馈隔离、接受与回退、全组冻结屏障及新输入排除。报告及真实接受/拒绝案例位于deliverables/research72_audit_20261024_r01/RESULTS.md和CASE_TRACE.md，原始产物位于deliverables/research72_real_20261024_r01。有限第一违例归因上的仿真通过不等于全局保证；仍是实际FIFO与人工故障任务。research71及research63保持原状，新独立测试没有参与后续修改。

```powershell
wsl -- python3 scripts/research72_policy_audit.py --prepared deliverables/research72_prepare_20261024_r02 --run deliverables/research72_real_20261024_r01 --out deliverables/research72_audit_NEW
```
