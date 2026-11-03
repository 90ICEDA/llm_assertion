# 解盲前固定的“最终选择”口径

本次“最终选择”特指 **balanced behavioral train-dev 的模型变体选择**，即在冻结的 6 个 dev parent 上比较 `anchor_10`、`anchor_20`、`anchor_25` 与两个基线，由 `src/evaluate_balanced_behavioral_dev_top1.py` 写出 `dev_metrics_and_selection.json` 的 `selection.selected_variant`。这是一个**实验级变体选择**，不是从 30 个训练 parent 的 7 条 natural assertion 中逐 parent 选一条，也不是 OOD Top-1 输出、Phase-B 排程中的 anchor 行，或训练完成的证明。

## 当时固定的规则

输入为 `dev_top1_v1/query_manifest.json` 中冻结的 6 个 train-dev parent，以及每种方法各 6 个 one-shot 生成和对应的 30 个逐项执行评估记录。生成协议为严格五键 JSON AST、贪心 Top-1、每 query 一次，无 repair/reranker/selector。失败记录计为 false，不删除。指标定义来自 `frozen_metric_definitions_v1.json`。

先筛选：变体 `Fixed-Safe` 不低于 `scalar_score_dpo`，且 `Target Detect` 不低于 `full_disagreement_dominance_dpo`。合格者按 `SCS@1` 降序、`Fixed-Safe` 降序、`Target Detect` 降序、anchor 百分比升序排列；第一名为 selected variant。无合格者为 NO-GO，不进行 all30 refit 或 OOD。不得使用 OOD 结果调整本次选择。

现存原始选择结果为 `anchor_20`；基线门槛分别为 1/6 和 3/6，合格变体是 `anchor_20`、`anchor_25`。30 个逐项评估记录、30 组生成的 AST/raw response/evidence、原 query manifest、指标定义、评估日志、规则源码及最终 JSON 均已定位；具体路径与哈希见 `HISTORICAL_DECISION_FILES.csv`。`materialize_balanced_behavioral_phase_b.py` 固定期待该 JSON 的 SHA-256，并且 Phase-B 冻结 manifest 引用同一哈希。这支持**历史上选择了 anchor_20 作为计划 refit 变体**。

## 影响措辞的边界

盲评抽中的是训练 parent 的自然候选。它们的逐 assertion/逐 pair 判断不能直接改写六个 dev parent 的 30 个生成评估记录；因此当前证据**不支持**声称盲评差异改变了上述历史实际变体选择。若以后替换训练偏好或候选、再按同一规则重算，那只能称为**反事实选择影响**，并须同时说明哪些输入被替换、哪些固定、如何处理 `INCOMPARABLE/UNKNOWN`。不得把重算结果冒充历史决策日志。

case510 的既有证据仅支持其候选被纳入**计划** Phase-B anchor 排程；缺少原始 Phase-B `train_log.jsonl`、`training_result.json`、checkpoint 实体及指针，不能据此声称实际训练消费了这些行，更不能声称影响最终模型或 OOD Top-1。当前新盲评没有抽中 case510。

`HISTORICAL_DECISION_FILES.csv` 只索引上述 dev 变体选择的现存文件。它不是新审阅者可见材料，旧 Pilot 候选反馈在此阶段未解盲。
