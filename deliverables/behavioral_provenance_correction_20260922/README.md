# 既有 behavioral 实验来源标签更正（2026-09-22）

此目录是**不改写冻结原件**的勘误侧表。原 JSONL、报告、哈希及历史指标均保留；没有重训。原始文件路径、SHA-256 与行号/报告字段路径是可复查的连接键。`row_provenance.csv` 覆盖 v1 两种 preference、v1/v2 training corpus、balanced edge/anchor pool 与各个 ordered schedule；`source_file_summary.csv` 汇总每个源文件；`report_row_corrections.csv` 逐个标注 v1/v2 final、balanced dev 及 Phase-B OOD 的指标行所对应的来源（probe-ablation 行为 preference/probe 来源，其余为训练来源）。标签不表示评估 query 本身的来源，也不证明 checkpoint 实际存在或训练已完成。`parent_split_24_6.jsonl` 不是候选行，`safe_detect_anchors_dev6.jsonl` 为空；汇总中保留两者的零行记录，不强行赋予候选来源标签。

分类规则：slot 01–07 候选为 `natural`，slot 08 是特意改变生成指令的 `synthetic control`。单候选 SFT 行继承候选标签；双候选 preference/DPO 行若两侧不同，标 `mixed`。报告指标行只要依赖的训练 corpus/schedule 同时含 natural 与 synthetic，就标 `mixed`，不能写成 natural-only。纯 natural pair 不因同一文件存在其它 mixed pair 而改标 mixed；这是**行级**与**实验级**标签的区别。

Phase-B `anchor_20_all30.jsonl` 的 4,058 个**计划**训练行中：3,329 行 `natural`，0 行纯 `synthetic control`，729 行 `mixed`。受影响行的精确行号、pair ID、parent ID、chosen/rejected 槽位与原始行 SHA-256 见 `phase_b_729_affected_rows.csv`；行号最小 4、最大 4,055，分布不连续，涉及 17 个 parent、36 个不同 pair。重复 schedule 行保留，因此“729”是计划训练行数，不是独立 preference pair 数。完整 schedule 的实验级来源为 `mixed`。

例如 disagreement-guided preference 有 484 对：330 对 `natural`、154 对 `mixed`；ordinary SFT corpus 有 240 行：210 行 `natural`、30 行 `synthetic control`。Pilot v1/v2 的相应整体训练实验及结果报告均须按 `mixed` 解读。balanced dev 的三个 schedule 也均为 `mixed`，具体计数见汇总表。

Phase-B 执行仍为 **UNKNOWN / 无法实证**：schedule 可核，但原始 `train_log.jsonl`、`training_result.json` 和末次 adapter checkpoint 缺失。现有 OOD 指标仅作为历史报告保存，不得据此宣称 4,058 步确已运行或该 adapter 权重已独立核验。证据边界详见 `deliverables/phase_b_edge_lineage_20260922/README.md`。

复核命令：`pwsh -NoProfile -File scripts/label_behavioral_provenance_20260922.ps1`。该脚本只读取既有源文件并重建更正侧表，不触发训练。
