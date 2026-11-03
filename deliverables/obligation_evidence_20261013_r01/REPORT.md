# 义务指导证据搜索：实际运行报告

本轮未修改候选。自然旧池与 filter 补充自然池分开；六个父案例均为人工变异。所有数字由原始日志重算。

## 统计来源与基线

{"parent_count": 6, "method_parent_cells": 48, "counts": {"failure": 23, "unknown": 17, "pass": 8}, "pairs_total": 25, "pairs_natural": 21, "focused_pairs": 11, "meaning": "40 problematic method-parent cells in v3; 11 previously distinguished pairs from 25 v1 pairs; separate cohorts, not a one-to-one mapping", "no_history_claim": true, "git": "no usable HEAD"}

{"runs": 151, "identical": 151, "mismatches": [], "statuses": {"ok": 151}, "cells": 40, "original_states": {"known_failure": 23, "unknown": 17}, "reclassified": {"confirmed_scoped_failure": 23, "unresolved": 1, "unknown_full_contract": 16}}

| 父案例 | 原通过单元 | 原失败单元 | 原未知单元 |
|---|---:|---:|---:|
| onehot | 8 | 0 | 0 |
| filter | 0 | 7 | 1 |
| fifo | 0 | 8 | 0 |
| spill | 0 | 0 | 8 |
| stat | 0 | 8 | 0 |
| intr | 0 | 0 | 8 |

## 冻结候选搜索

每父案例每方法三个预定种子，每种子 12 次实际查询。查询包括双 RTL 执行，所有候选批量求值。错误/超时/无效输入也收费；无重试、缓存或求解器调用。

| 父案例 | 方法 | 查询 | 编译 | 周期 | 原始/去重证据 | 候选义务缺口 | 秒 |
|---|---|---:|---:|---:|---:|---:|---:|
| onehot | ordinary | 36 | 72 | 1728 | 2011/1535 | 14 | 52.32 |
| onehot | disagreement | 36 | 72 | 1728 | 1980/1186 | 14 | 52.57 |
| onehot | obligation | 36 | 72 | 1728 | 1739/1584 | 14 | 52.20 |
| filter | ordinary | 36 | 72 | 0 | 0/0 | 0 | 16.72 |
| filter | disagreement | 36 | 72 | 0 | 0/0 | 0 | 16.82 |
| filter | obligation | 36 | 72 | 0 | 0/0 | 0 | 16.68 |
| fifo | ordinary | 36 | 72 | 1728 | 2525/2195 | 18 | 52.45 |
| fifo | disagreement | 36 | 72 | 1728 | 3223/2283 | 18 | 52.86 |
| fifo | obligation | 36 | 72 | 1728 | 1778/1136 | 18 | 52.34 |
| spill | ordinary | 36 | 72 | 1728 | 1364/1026 | 15 | 51.65 |
| spill | disagreement | 36 | 72 | 1728 | 1696/1023 | 15 | 51.92 |
| spill | obligation | 36 | 72 | 1728 | 667/484 | 14 | 51.75 |
| stat | ordinary | 36 | 72 | 1728 | 795/683 | 24 | 52.53 |
| stat | disagreement | 36 | 72 | 1728 | 974/508 | 24 | 52.01 |
| stat | obligation | 36 | 72 | 1728 | 396/72 | 12 | 51.46 |
| intr | ordinary | 36 | 72 | 1728 | 0/0 | 0 | 52.14 |
| intr | disagreement | 36 | 72 | 1728 | 0/0 | 0 | 51.84 |
| intr | obligation | 36 | 72 | 1728 | 0/0 | 0 | 51.84 |

缺口数按候选 × 义务 × FP/FN 去重，不是独立 bug 数；完整证据另按 reset-to-witness 输入输出前缀去重。无反例不等于正确。spill 仅确认 collision_empty；intr 两解释未决，不并入明确收益。

## 未完成和限制

第3项 A/B/C/D 新模型细化：未执行。历史八臂不是本次四臂，不替代本次结果。模型访问记录见 model_access.json。
第4项最终断言独立泛化：未执行；quarantine 在搜索前封存，尚未提供给生成器或评估。旧 v3 hidden 已用于诊断，不能再声称是新泛化集。
原生 SVA：见 baseline/native_sva/capability.json；实验使用 Icarus 过程 checker，非形式证明。
所有同拍报警均未计作独立事务命中。候选双方有缺陷时不强行排序。工具故障不归为候选语义失败。

## 复现

`python3 scripts/run_obligation_evidence.py --run obligation_evidence_20261013_r01 report` 从查询日志重建统计；新运行使用新 --run，依次 prepare、baseline、search、report。
每条新运行有 input.json、trace.json、wave.vcd、checker_*_cycles.json、independent_reference.json、independent_evidence.json、编译/仿真命令与 reproduce.sh。
源文件原哈希及副本见 source_manifest.json / source_snapshot；问题台账见 problem_ledger.json；查询成本见 search/queries.jsonl。
