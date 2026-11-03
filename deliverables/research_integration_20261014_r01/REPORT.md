# 2026-10-14 研究与实现续作报告

这是有实际运行产物的阶段性交付，未宣称全部研究完成。旧目录和旧负结果保留。工作区 `.git` 为空，Git 版本不可得；新代码快照与 SHA256 见 source_manifest.json。

## 核查及实际改动

- 历史已有真实 Ollama 请求/响应、11对候选、四组实验和 Ibex 原始RTL回放，不能重新包装为本轮首次完成。
- 历史接受逻辑仅检查能否执行，未拒绝语义退化；旧C/D也不是独立的防退化开关。本轮新增稳定证据键的集合接受门和真正搜索×门的2×2实验。
- 原生工具由本轮局部解包的 Verilator 5.020 提供；保留初次路径配置失败及修正后的资格检查。Icarus过程检查器结果与原生SVA结果分表。
- 复用真实 axis_fifo RTL、原独立监视器、模型流式接口与旧候选，新增复杂FIFO、四法搜索、原生闭环、统一入口和历史复跑，不改旧封存内容。

## 搜索比较：同池、同种子、同查询预算

每方法216查询（6父×3种子×12）；每查询执行buggy/fixed。所有查询均属于开发数据。缺口键按父案例、候选、FP/FN和义务去重；不是独立Bug数。普通差分的波形差异仅作搜索奖励，必须经独立契约裁定才计有效证据。

| 方法 | 去重候选缺口 | 区分11对 | 规格unknown查询/216 |
|---|---:|---:|---:|
| ordinary | 36 | 6/11 | 72/216 |
| disagreement | 37 | 6/11 | 72/216 |
| differential | 43 | 8/11 | 71/216 |
| contract | 43 | 8/11 | 60/216 |

契约策略相对普通差分在spill增加一个collision_empty漏报缺口，同时在filter少找到一个qualified_value缺口。本轮不支持契约策略总体优于普通差分。逐对新增与遗漏、重复、代表原始证据见 [搜索报告](../research_search_20261014_r01/REPORT.md)、[逐对结果](../research_search_20261014_r01/pair_results.json)、[真实见证示例](../research_search_20261014_r01/EVIDENCE_EXAMPLES.md)。

stat原始文字支持两拍延迟及原长度，但没有明确重叠允许语义；搜索将相关查询降为unknown。过程检查器unsupported和空触发仍在分母：10944项中576 unsupported、10042有触发、326空触发。

## 复杂FIFO与原生SVA

FIFO以 valid && ready 握手识别接受，独立队列按顺序配对响应，显式记录accept_cycle/response_cycle/latency/reset取消。背压下仅呈现请求不计接受。请求Depth=2/3/4，实际RAM容量分别2/4/4，不能把Depth=3视为新的容量；流水级另占存储。
96次Icarus RTL执行：24个correct运行无执行范围内违例，72个明确人工边界故障有合法同激励对照，去重后4类mutation/obligation缺口。新种子开发/工程独立测试各48次；不是LLM最终断言通过96次。详见 [FIFO报告](../research_fifo_20261014_r01/REPORT.md)。

两次原生工程控制展示负例：next-cycle有效断言在correct上9次误报；稳定性断言38次触发且无失败，却漏掉64次payload违例。这些SVA来自工程控制，不冒充模型产物。[逐事务例子](../research_fifo_20261014_r01/supplement/NATIVE_EXAMPLE.md)。复位取消经过正常轨迹，但未注入专门跨复位残留故障。

原生工具资格检查：正向 |=>、反向 |=>、$past 已实际运行；合法 ##2 sequence 在该工具不支持，不能归为模型语法错误。首次配置路径失败保留于probes，修复后见probes_r02。仿真无违例不是形式证明。

### 真实模型→原生SVA闭环

结果来自独立的真实FIFO人工故障轨迹，与过程检查器消融分开。请求含共享RTL、修复前后边界RTL、Bug含义、协议和已声明义务。使用公开辅助队列状态，工程脚手架不属于模型自动推导成果。

```json
{
  "status": "native_revision_executed_rejected_proposal_diagnostic_holdout",
  "initial": {
    "status": "ok",
    "false_positives": 45,
    "detections": 0,
    "misses": 78,
    "attribution_unknown": 65,
    "effective_triggers": null,
    "diagnostic_trigger_keys": 139,
    "trigger_semantics": "mismatch; actual native effective trigger coverage unavailable",
    "legal_prefix_samples_by_mode": {
      "correct": 134,
      "corrupt": 26,
      "duplicate_payload": 39,
      "drop": 65
    },
    "false_positives_by_mode": {
      "correct": 29,
      "corrupt": 3,
      "duplicate_payload": 6,
      "drop": 7
    },
    "legal_prefix_samples": 264,
    "missed_fault_obligation_classes": [
      "corrupt/order_payload",
      "drop/drain_no_loss",
      "drop/order_payload",
      "duplicate_payload/order_payload"
    ],
    "causal_detection_classes": []
  },
  "final_development": {
    "status": "ok",
    "false_positives": 45,
    "detections": 0,
    "misses": 78,
    "attribution_unknown": 65,
    "effective_triggers": null,
    "diagnostic_trigger_keys": 139,
    "trigger_semantics": "mismatch; actual native effective trigger coverage unavailable",
    "legal_prefix_samples_by_mode": {
      "correct": 134,
      "corrupt": 26,
      "duplicate_payload": 39,
      "drop": 65
    },
    "false_positives_by_mode": {
      "correct": 29,
      "corrupt": 3,
      "duplicate_payload": 6,
      "drop": 7
    },
    "legal_prefix_samples": 264,
    "missed_fault_obligation_classes": [
      "corrupt/order_payload",
      "drop/drain_no_loss",
      "drop/order_payload",
      "duplicate_payload/order_payload"
    ],
    "causal_detection_classes": []
  },
  "independent_test": {
    "status": "ok",
    "false_positives": 61,
    "detections": 0,
    "misses": 79,
    "attribution_unknown": 75,
    "effective_triggers": null,
    "diagnostic_trigger_keys": 156,
    "trigger_semantics": "mismatch; actual native effective trigger coverage unavailable",
    "legal_prefix_samples_by_mode": {
      "correct": 134,
      "corrupt": 27,
      "duplicate_payload": 42,
      "drop": 45
    },
    "false_positives_by_mode": {
      "correct": 37,
      "corrupt": 5,
      "duplicate_payload": 8,
      "drop": 11
    },
    "legal_prefix_samples": 248,
    "missed_fault_obligation_classes": [
      "corrupt/order_payload",
      "drop/drain_no_loss",
      "drop/order_payload",
      "duplicate_payload/order_payload"
    ],
    "causal_detection_classes": []
  },
  "attribution_unknown": {
    "initial": 65,
    "final_development": 65,
    "independent_test": 75
  },
  "unprotected_obligations": [
    "drain_no_loss",
    "order_payload"
  ],
  "frozen_sva_sha256": "5863dcda93e79fd9f9d543bb95098ee9335b9d08d0e85ebcf4fba22ee5459096",
  "model_cost": {
    "actual_attempts": 3,
    "completed_calls": 2,
    "cancelled_calls": 1,
    "retries": 0,
    "known_prompt_tokens": 15483,
    "known_completion_tokens": 428,
    "prompt_tokens": null,
    "completion_tokens": null,
    "unknown_usage_attempts": 1,
    "completed_wall_seconds": 445.1194507370003,
    "cancelled_wall_seconds_upper_bound": 388.651028,
    "cancelled_service_duration_display": "4m18s",
    "cancelled_service_seconds_approx": 258,
    "monetary_cost": "unavailable_local_inference"
  },
  "native_cost": {
    "compile_calls": 3,
    "simulation_calls": 12,
    "compile_wall_seconds": 71.20467238699962,
    "simulation_wall_seconds": 0.26523232800059304
  }
}
```

原始请求、响应、每版SVA、原生编译/执行命令、拒绝理由、冻结和独立结果见 [native汇总](../research_native_20261014_r01/summary.json) 和 [完整报告](../research_native_20261014_r01/REPORT.md)。初始真实候选位于closed_loop，过长revision调用取消并保留；compact_continuation是单独增加的第三次尝试，不能称原2调用预算成功。触发计数是诊断标记，不是native cover证明；同周期报警不足以记因果检出。

真实初始性质 `mdata[0] == $past(mdata[0])` 把顺序约束误解成跨周期bit稳定，且模型trigger与无前件性质不对应。紧凑续作生成三条重复的相同性质，未增加互补保护。原生编译执行成功不等于义务验收成功；没有可接受版本时冻结测试仅为诊断。归因复核区分合法前缀FP和已有违例后的未知报警，原始计数不覆盖。

## 防退化集合接受与2×2实际消融

A=普通反馈；B=普通反馈+新契约证据；C=普通反馈+接受门；D=两者。每组同一初始自然候选、同一模型采样配置、2次真实调用；模型新增证据仅本组可见。所有组都支付自己的历史重放，C/D将检查结果用于拒绝。

| 组 | 模型调用 | 输入/输出tokens | 开发查询 | 接受提案 |
|---|---:|---:|---:|---:|
| A | 2 | 5472/297 | 10 | 0 |
| B | 2 | 7274/278 | 20 | 2 |
| C | 2 | 5489/303 | 10 | 0 |
| D | 2 | 9979/277 | 14 | 0 |

统计包含接口失败，实际tokens/查询不强行对齐。A/C候选错误未执行提案重放，因此少付查询成本；D反馈包含拒绝信息，会增加提示tokens。r01普通组的下一轮只含错误状态而缺具体越权identifier；不能把错误失败归为搜索机制劣势。运行后已修复未来实验的错误反馈和配置字段，只验证prepare流程，未混入r01结果。config_errata.json列出不可变config内继承过时字段；实际成本以query ledger为准。r01执行源码以该实验目录根部冻结.py为准。

实际轨迹：原stat断言为 `frame_done_i |-> stat_valid_o`。模型提案加入 `frame_done_i |-> ##2 stat_len_o` 及以 `rst_ni` 为前件的valid/length检查，未正确比较捕获长度，产生新误报。B允许可执行提案替换；D第0轮实际拒绝并保留原版本。详见 development/*/checkpoint_*.json（含每条新增FP证据键、当前目标、模型原因与重放映射）。

接受门只保证指定本轮缺口和已确认历史保护在已重放证据范围内；effective_triggers是输出相关求值代理，不证明语义蕴含。非目标未归因报警、后续事务和未覆盖义务仍需单列，不得宣称全局防退化或父Bug通过。stat试验依赖工程化重叠契约，仅条件实验；不是原历史规格已确认。

### 冻结后的新测试（过程检查器、条件stat范围）

| 组 | 队列 | 初始→最终FP | 初始→最终首次FN | 最终因果检出 | 最终归属unknown |
|---|---|---:|---:|---:|---:|
| A | original_target | 59→59/198 | 0→0/18 | 0 | 146 |
| A | new_payload_fault | 59→59/198 | 0→0/18 | 0 | 97 |
| B | original_target | 59→103/198 | 0→0/18 | 0 | 146 |
| B | new_payload_fault | 59→103/198 | 0→0/18 | 0 | 97 |
| C | original_target | 59→59/198 | 0→0/18 | 0 | 146 |
| C | new_payload_fault | 59→59/198 | 0→0/18 | 0 | 97 |
| D | original_target | 59→59/198 | 0→0/18 | 0 | 146 |
| D | new_payload_fault | 59→59/198 | 0→0/18 | 0 | 97 |

6条新37周期序列在细化前隔离保存，最终哈希冻结后才执行；初始/最终×4组×2故障队列共96次配对查询。新payload故障为人工故障；无独立测试反馈进入模型。若后续据此修改，这批数据必须转为开发数据。

所有组因果确认检出为0，原始目标/新数据故障分别有146/97个违例采样的报警归属unknown（各含18个首次违例）；因此零first_misses不是零漏报。stat区块没有已确认的历史成功检出可供保持，只验证了拒绝新增误报的执行作用。B0/D0请求与响应逐字相同，D0拒绝了69个新增误报证据键；C全部是接口拒绝，不能作为语义接受门成功。两故障队列重复使用相同合法控制，198合法采样不能跨队列相加当新独立样本。[只读审计](audit_gate.json)。

## 六父与历史RTL状态（不排除困难项）

| 父案例 | 本轮范围 | 完整保护 |
|---|---|---|
| onehot | 仅搜索回归 | 本轮未做新独立整体验收 |
| filter | 四法新搜索；契约相对差分遗漏一项 | 未建立 |
| FIFO presented/Depth0 | 搜索回归，见证仅idle；presented原始目标缺见证 | unknown |
| spill | collision_empty可判定；invalid payload未决 | unknown |
| stat | isolated scoped搜索；重叠条件模型实验 | 原始完整时序规格未确认，未通过 |
| intr | mask采样语义未决，保留两对unknown | unknown |
| Ibex #54（另列真实案例） | 新复跑4个原始RTL/测试组合全部符合前失败后通过且日志一致 | 原始回归可复现；生成SVA完整保护未建立 |

Ibex来源PR #54，base cd15ce88beba8ed8496f414af361f664764f47e2，fix 687952e42f3eff68348770ae0c55bc5c0f036d3e，merge 5319734180ac4844e43d31ad19dc108aac503037。保存的来源、文件哈希和新命令见 [Ibex复跑](../research_ibex_20261014_r01/summary.json)。不能把复杂FIFO边界人工故障并入真实历史成功率。

## 复现命令

从 `D:\AssertionForge-main1` 的 PowerShell 运行；NEW目录必须未使用。原生工具沿用当前产物tools，迁移环境须重新配置VERILATOR。

```powershell
wsl -- python3 scripts/research_pipeline.py report
wsl -- python3 scripts/research_pipeline.py qualify
wsl -- python3 scripts/research_pipeline.py fifo --run research_fifo_NEW
wsl -- python3 scripts/research_pipeline.py search --run research_search_NEW --action prepare
wsl -- python3 scripts/research_pipeline.py search --run research_search_NEW --action run
wsl -- python3 scripts/research_pipeline.py search --run research_search_NEW --action report
wsl -- python3 scripts/research_pipeline.py gate --run research_gate_NEW --action prepare
wsl -- python3 scripts/research_pipeline.py gate --run research_gate_NEW --action develop
wsl -- python3 scripts/research_pipeline.py gate --run research_gate_NEW --action acceptance
wsl -- python3 scripts/research_pipeline.py native --run research_native_NEW
wsl -- python3 scripts/research_pipeline.py ibex --run research_ibex_NEW
```

如需严格复现旧r01 stat运行而非修正后的入口，使用该产物目录根部的冻结脚本并设置 `PYTHONPATH=/mnt/d/AssertionForge-main1/scripts`，指定新--run；原模型服务、digest与工具版本仍须匹配。不要重用已消耗测试来开发新版本。

全部成本见results.json/gate_costs.csv及各子实验命令日志。搜索1728编译+1728仿真；并行运行wall_seconds之和不是实际历时。未知金额、token、CPU均标null/不可用，不当作零成本。形式化调用为0。

## 未完成与具体限制

- Native four-arm search x non-regression factorial on complex FIFO not executed.
- Full confirmed repair-obligation coverage for six parent bugs and generated assertions on historical Ibex not established.
- spill invalid-payload and intr mask semantics remain unresolved; stat overlap historical semantics unconfirmed.
- FIFO presented original defect remains unknown without a definitive original-target violation witness.
- Contract search remains a finite scheduling policy, not a complete general obligation-solving engine.
- No formal proof runs; supported native SVA simulation is bounded to Verilator feature subset.
- No additional historical bug admitted beyond freshly replayed Ibex #54.

模型总成本另见model_costs.json：11次实际尝试（10次返回、1次取消），已知输入/输出tokens为43697/1583，取消调用用量不可得。

未来native统一入口现调用research_native_safe.py：完整RTL/规格不变，反馈每类2代表并保留总数和外部全量记录；加入上下文预算预检。本次只静态核验请求从56482字节缩至30635字节，新增调用0次，不计为修复实验成功。

下一阶段应在支持的原生SVA子集上做复杂FIFO完整四组实验，补专门复位残留故障与更多历史RTL案例；stat/spill/intr需要可靠规格依据。单次局部改善、工程控制和已重放历史保护均不能替代上述完成标准。
