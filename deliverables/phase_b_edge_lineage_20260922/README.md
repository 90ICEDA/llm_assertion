# Phase-B 逐边血缘审计（2026-09-22）

结论：`anchor_20_all30.jsonl` 是一份包含 4,058 行的有序**计划**，不是 4,058 步已执行的证明。现存训练文本 164/164 的字节和 SHA-256 与原 manifest 一致；4,058/4,058 行可关联到相应 preference/canonical/edge 或 anchor 来源；134/134 个 response 可按原始候选 evidence AST 重建并逐字节匹配。但原始训练日志、训练结果和末次 adapter checkpoint 缺失，因此实际训练步数、参数更新及 checkpoint 内容均为 **UNKNOWN / 无法实证**。没有重训或补造这些证据。

## 可复查文件

- `training_text_164_inventory.csv`：30 个 prompt + 134 个 response 的原始相对/绝对路径、字节数、现算 SHA-256、声明 SHA-256、副本路径和状态。
- `schedule_4058_lineage.csv`：每一有序 schedule 行，含 pair/example ID、上下游文件及行号、训练文本路径/hash、原始生成 evidence、trainer 分支和 natural/synthetic 标签。重复 schedule 行保留，不去重成“已执行”。
- `canonical_response_origin_validation.csv`：134 个 canonical response 与原始 evidence AST 的逐字节规范化检验（五键、紧凑 JSON、无尾换行）。
- `source_scripts_logs_and_missing.csv`：428 个找到的源文件/脚本/现有日志的路径、大小、hash、副本，以及 4 个明确的 `MISSING`。
- `raw_originals/`：原路径层级下的逐字节副本；复制后复算 SHA-256。包括原始 preference JSONL、canonical pair JSONL、edge/anchor pool、schedule、manifest、候选 evidence/prompt/SVA、相关 materializer/trainer/generator 脚本及 5 份现有日志。
- `audit_summary.json`：机器可读结论；`lineage_issues.csv` 为空表示未发现上述路径/内容关联问题，**不**表示训练已执行。
- `SHA256SUMS.csv`：交付文件的 SHA-256（不含自身）。

## 血缘与读取边界

`disagreement_guided_dominance_pairs.jsonl` 的 `pair_id` 和原始 JSONL 行 hash → `full_disagreement_dominance_dpo.jsonl` 的同一 pair 与 canonical response 路径 → `dpo_edges_all30.jsonl` → `anchor_20_all30.jsonl` 的原序行 → `train_balanced_behavioral_phase_b_qwen3.py` 委托 `train_balanced_behavioral_dev_qwen3.py`。后者先审计 schedule，再按文件顺序逐行读取：DPO 读 prompt/chosen/rejected，SFT anchor 读 prompt/response；`parts()` 对 response 增补 EOS，单行形成 batch size 1，并可能截断 prompt。这里验证的是**静态输入映射与代码行为**，没有可查的实际运行 batch 记录。

原始 preference 中的 candidate prompt/SVA/evidence 及其声明 hash 已核对并复制。canonical response 与 evidence AST 一致；canonical prompt 的现存字节与声明 hash 一致。抽样标签没有混淆：含 slot-8 的 729 个 schedule 行标 `MIXED_SYNTHETIC_CONTROL`，其余行标 `NATURAL_ONLY`；本文件不把混合行称为 natural。重复行计数不是独立候选数。

现有 5 份 `balanced_behavioral_phase_b_*` 日志属于 AST smoke validation 或 OOD evaluation，不是 trainer 的 `train_log.jsonl`。现有 generation manifest 声明 adapter 路径/hash，只能证明其**声明**，不能在缺失物理 adapter 时独立核验实际加载的权重字节。缺失路径逐项见 `source_scripts_logs_and_missing.csv`，包括 `train_log.jsonl`、`training_result.json`、`latest_checkpoint.txt` 和 `checkpoint-004058/adapter_model.safetensors`。因此不得把 schedule、生成 manifest 或评估结果写成“4,058 步确已执行”。

复现静态审计：在仓库根目录运行 `pwsh -NoProfile -File scripts/audit_phase_b_edge_lineage_20260922.ps1`。这只读取已有证据、复制原件并重算审计表；不调用训练。PowerShell 7 (`pwsh`) 是所需运行时。
