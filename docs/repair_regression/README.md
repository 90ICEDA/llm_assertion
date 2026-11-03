# RTL 修复驱动回归断言系统 v1

本系统将修复义务、行为证据、候选断言和回放接受决定分开。真实执行的是 WSL 内 Icarus 编译的 RTL 与受限 procedural monitor。输出 `assertions.sv` 供审查和后续绑定；本轮不声称原生 SVA 已通过或 Jasper 已证明。

本次另外探测了 Windows 工具：ModelSim 10.4 可编译简单原生 SVA，但运行报告 `FileWatch(fileName)` Tcl 错误（即使退出码为 0，也不记成功）。Windows Ollama 服务可访问，列出了 qwen3 和 qwen2.5-coder；WSL localhost 同端口拒绝连接。闭环显式选择离线模板，本次模型调用数为 0，不将模板输出写成模型生成，也不声称整台机器没有模型服务。原始探测位于 `deliverables/repair_regression_20261014/windows_tool_probe/`。

## 接口和调用关系

```
CaseInput → cases.extract → Obligation[]
          → refinement.initial → AssertionSet
          → search.search (三种 operation)
          → Backend.execute (buggy/fixed，同一输入，无候选)
          → evidence.adjudicate → EvidenceStore (evidence.jsonl)
          → refinement.propose → AssertionSet proposal
          → freeze snapshot → replay(old) + replay(proposal)
          → gate → RefinementAttempt → accept/reject
          → 下一轮搜索 → assertions.sv + Verdict
```

代码位于 `scripts/repair_regression/`，薄入口为 `scripts/run_repair_regression.py`。
`contracts.py` 为 CaseInput、Obligation、Evidence、AssertionSet、ReplayResult、RefinementAttempt、Verdict 提供版本 `1.0` 的 JSON Schema 和实际运行时校验。schema 文件由 `examples` 命令生成；onehot/FIFO 的全部接口实例也由真实运行产出，在 `interface_examples.json` 中列明。

- `cases.load_case(path)`：只在输入边界将 `correct` 规范化为 `fixed`；同时提供两种名称会拒绝。检查输入哈希、端口、参数和映射。现有适配仅接受已确认的固定参数和同名端口；不支持的配置明确拒绝。
- `cases.extract(case)`：读取并规范化既有确认义务，标记 `imported_confirmed`，不从候选反推规格。保留独立文字规格、源文件位置、哈希、时钟、复位、捕获、延迟、输入约束及判定器版本。
- `search.search(..., kind, seed, step, target, folder)`：统一调用三类操作；无差分、无误报和无缺口见证也保存搜索记录。`search_budget` 是每轮查询数；每次查询执行 buggy/fixed 各一次，候选评估另有仿真日志。
- `evidence.adjudicate(case, obligations, rows, run, provenance)`：只消费输入和端口 trace，不读取候选或 CHECK。`legal` 仅表示满足记录的修复义务范围，不表示全部 DUT 规格正确。
- `refinement.replay(...)`：逐证据返回状态、每条断言 ID/版本/内容哈希、触发、误报、漏报和有效归因。
- `refinement.attempt(...)`：冻结同一快照，在该快照上回放两套集合，记录差异、原因、结果路径；保持条件通过才更新集合。

## 复用清单与隔离边界

| 现有能力 | 实际复用位置 | 必要改动/限制 | 原先缺少的能力 |
|---|---|---|---|
| `repair_contract_cases.definition/sources` | `cases.example` | 历史路径只用于导入源 RTL；实际运行复制到新目录并冻结哈希 | 明确 CaseInput、输入文件清单 |
| `repair_contract_cases.controlled_candidate` | onehot 细化提案 | 明确为离线工程模板，接受结果不由模板决定 | 提案来源、版本和回放门禁 |
| `obligation_search_policy.guided/ordinary/disagreement/repair_environment` | `search.stimuli` | 新增合法复位边界和针对具体缺口的刺激 | 三类操作、预算、无见证记录 |
| `obligation_evidence_monitor.check_inputs` | `Backend.execute`、独立判定 | 只复用端口取值/保持约束检查；重新建立行为证据对象 | 候选无关标签、事务关联、去重 |
| `contract_v3_checker.normalize/tb_text` 及其 `run_repair_contract.tb_text` | `backend.py`、SVA 输出 | 将历史观察寄存器改为异步复位；不修改旧函数和全局变量 | 显式配置执行器、隔离路径、完整日志 |
| `obligation_checker_async`/continuation interface 的修复思路 | 新 backend 的局部 TB 转换 | 不导入其带实验依赖的执行流程；用本次 QA 重新验证 | 非采样边沿复位资格测试 |
| `gen_plan`、`utils_gen_plan`、`run_failure_guided_single_repair` | 检查后未导入运行 | FLAGS/saver/LLM、历史分数和数据依赖不适合本闭环；保持不变 | 规则后备生成器独立于证据接受 |
| `run_obligation_evidence`、isolated/refinement/continuation/public 系列 | 检查后不串联 | 依赖历史目录、全局 OUT、monkey patch、历史失效标记；`repair_contract_lowering.py` 有导入即移动目录的副作用 | 无隐式历史状态的恢复运行 |
| Jasper batch → `rtl_cases.jasper_antecedent_reachability.run_jasper_on_case` | 追踪到真实 `subprocess.run(jg -batch -proj ... -tcl ...)` | 本地未发现 jg，且没有已配置远程端点；未调用历史结果缓存代替证明 | 本轮形式化证明受阻 |

未发现适用 AGENTS.md。原目录 `.git` 无可用 HEAD，`git status` 报非 Git 仓库；本任务新增独立目录和入口，不修改历史实验文件。工作区 ACL 需要提升权限才能创建部分顶层新目录，实际写入范围仍限本仓库。

## 案例语义

**onehot**：4 位 oh_i，StrictCheck=1；每个有效 pre-NBA 上升沿，popcount(oh_i)>1 必须 err_o=1。同周期采样。zero/onehot 允许地址/使能检查合法报错，系统没有引入相反义务。初始离线种子只检查 oh_i==3；细化提案扩大为全部 multihot。两者都明确为工程模板，不冒充本次模型生成。

**FIFO**：Depth=0，DataWidth=8，使用仓库已有 compat RTL。`empty_when_idle` 和 `nonempty_when_present` 分别覆盖 `!push_i → empty_o` 与 `push_i → !empty_o`。后者包含 stalled/accepted 两个分支。数据在背压期间保持是**输入环境约束**：上一周期 push=1 且 pop=0 时，当前周期保持 push/data，直到接受或复位取消。它来自之前确认的实验接口，而非从待评估断言导出。

原始参数类型 RTL 中可见 Depth=0 时 empty=~push、full=~pop、data=data_i；compat RTL 的 usage 固定为 0，不声明其等价于上游所有内部计数行为。上游文件还有 Depth>0/full_write/empty_read 宏检查，本次明确采用先前确认的 Depth=0 适配接口。没有新增占用量、内部存储、满队列入队、重叠存储事务或输出 data/full 的断言；这些能力在本配置不适用或不在已确认义务范围。

## 证据、事务与接受条件

先检查 trace 长度、周期序号、输入值和四态完整性，再进行事务匹配。禁止平移波形。reset epoch 只在进入复位时递增；每个 onehot 样本独立，FIFO presentation 由 push 输入发起、stall 延续、accept 结束，复位切断关联。Depth=0 义务在每个采样点触发并到期，即使 presentation 跨多个周期也不改变延迟。

记录的 `alignment=matched` 表示采样/事务已匹配，响应数值不符仍是 `target_violation`。缺失/额外采样、四态值、环境不合法、工具不完整保留 unknown。zero/onehot 的 `expected_response=null` 表示该范围没有约束 err_o。

有效检出除了同周期失败，还要求：断言关联正确义务、在该触发点实际触发、delay=0，并且 consequent 是对应义务输出的可认证响应表达式。任意无关失败、历史失败、延后报警不会记作有效检出。更一般的时序归因尚未实现，不能借助平均分或同周期失败数补足。

证据身份由案例、参数、行为前缀和义务范围组成，不含 candidate_id。索引 append-only；重复发现追加带哈希链的来源合并版本。标签冲突写入 `label_conflicts.jsonl` 并拒绝静默覆盖；显式修订需给理由并保留旧版本。损坏/截断索引会报错，不能自动删除证据。当前仅支持单写入者，未提供跨进程并发调度。

每个提案须满足：

1. 冻结同一份证据快照，契约/环境哈希不变。
2. 不新增任何已确认合法样本误报。
3. 不丢失旧集合任何有效目标检出或既有触发覆盖。
4. 任一 error/timeout/unsupported/unknown 阻止“证据保持成立”的结论。
5. 永假前件没有有效触发，不能通过；候选不能修改 disable iff、环境假设或义务。

集合检出取有效检出的并集，集合误报取任意成员误报。允许去除既有误报且保留检出的中间版本；最终通过还要求全部当前合法证据无误报、目标证据无漏报、必要分支有实际触发。没有某分支违例见证时，报告 `no_target_violation_witness`，不将其描述为已验证检出能力。

## 实际命令（PowerShell）

已安装依赖：WSL Ubuntu、Python 3、jsonschema、iverilog/vvp。工作目录 `D:\AssertionForge-main1`。以下使用绝对 Linux 路径，避免 PowerShell/bash 多层引号。

```powershell
wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/run_repair_regression.py examples --out /mnt/d/AssertionForge-main1/configs/repair_regression

wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/run_repair_regression.py run --case /mnt/d/AssertionForge-main1/configs/repair_regression/onehot.json --out /mnt/d/AssertionForge-main1/deliverables/repair_regression_20261014/onehot_r01 --seed 20261014 --search-budget 6 --rounds 2 --backend iverilog

wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/run_repair_regression.py run --case /mnt/d/AssertionForge-main1/configs/repair_regression/fifo.json --out /mnt/d/AssertionForge-main1/deliverables/repair_regression_20261014/fifo_r01 --seed 20261014 --search-budget 6 --rounds 2 --backend iverilog

wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/run_repair_regression.py run --out /mnt/d/AssertionForge-main1/deliverables/repair_regression_20261014/onehot_r01 --resume
wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/run_repair_regression.py run --out /mnt/d/AssertionForge-main1/deliverables/repair_regression_20261014/fifo_r01 --resume

wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/run_repair_regression.py replay --out /mnt/d/AssertionForge-main1/deliverables/repair_regression_20261014/onehot_r01
wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/run_repair_regression.py replay --out /mnt/d/AssertionForge-main1/deliverables/repair_regression_20261014/fifo_r01

wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/run_repair_regression.py qa --out /mnt/d/AssertionForge-main1/deliverables/repair_regression_20261014/onehot_r01
wsl -d Ubuntu -- python3 /mnt/d/AssertionForge-main1/scripts/run_repair_regression.py qa --out /mnt/d/AssertionForge-main1/deliverables/repair_regression_20261014/fifo_r01
```

新运行目录必须不存在，重做请使用 r02 等新名称。恢复会验证代码、输入、义务和预算；不允许在旧运行中悄悄切换工具或语义。独立 replay 创建唯一新目录并真正重新编译/仿真，比较重新加载前后的逐证据结果。可用 `--assertion-set /absolute/path.json` 独立评估其他集合，结果不会覆盖当前集合或证据标签。

直接在 WSL 中运行时，将命令前缀 `wsl -d Ubuntu --` 去掉即可。

## 每次运行的产物

- 必需文件：`assertions.sv`、`obligations.json`、`evidence.jsonl`、`verdict.json`。
- 输入与版本：`case.original.json`、`case.json`、`inputs/`、`implementation.json`、`implementation_sources/`、`state.json`。
- 生成与回放：`initial_assertion_set.json`、`assertion_set.json`、`snapshots/`、`rounds/`、`refinement/`、`final_replay/`、`independent_replays/`。
- 每个原始执行目录：`stimulus.json`、`checker_tb.sv`、`wave.vcd`、`trace.json`、`checks.json`、`result.json`、compile/simulate 的 argv/状态/stdout/stderr、`reproduce.sh`。
- 搜索与工具：`search/<round>/<query>/search.json`、`tools/availability.json`。
- 受控机制验收：`qa/result.json`，包含各项通过/失败、提案、反例和真实工具日志；与实际细化结果分开。

`flow_completed` 只表示流程结束；`current_evidence_pass` 只表示当前有限证据满足条件；`bounded_search` 明示有界性；`native_sva` 与 `formal_proof` 单独报告，不能由前两项推导证明成立。
