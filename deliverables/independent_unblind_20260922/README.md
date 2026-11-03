# 两-parent 独立盲评：封存复验与解盲对照（2026-09-22）

解盲前先复验三个外层封存文件：盲评工作区 `SEAL_SHA256.csv` 为 `860537ac86c9b0d22039e955fe2e287e3e7bd6221a19d1a1b8a9bf5051ce9ddd`（1,507 个封存文件、1,497 个原始来源哈希均通过）；审阅清单 `SEAL_MANIFEST.csv` 为 `9fa3f1e6bf05c4caf4d6214bc8b640f70cf240bb59f435e60f090965db0b284f`（6 个审阅文件大小/hash 均通过）；选择范围 `PRE_UNBLIND_FREEZE.json` 为 `38d43c12d8600fffac779de34d76750b115972b059c1e0b0816091532af0404e`（131 个历史决策文件 hash 均通过）。这些是文件完整性与流程顺序证据；单靠哈希不能独立证明审阅者此前从未接触旧反馈。

抽中 `case455_prim_crc32_set_enable_coupling`、`case115_prim_edge_both_edges_collapsed`。封存时有 14 条 assertion、42 条无序 pair 判断。解盲后分别按 `random_legal` 和 `disagreement_guided` 对照旧 `parent_result.json` 的**完整 FP probe ID 集合与 TP mutant ID 集合**，得到 `pairwise_feedback_comparison.csv` 的 84 条行。源 `parent_result.json`、旧 probe manifest、历史 dev 选择 JSON 和评估规则源码已逐字节保存于 `raw_originals/`，路径、大小、SHA-256 见 `source_inventory.csv`。

结果：明确判断 `RIGHT_BETTER` 的 5 对均来自 case115 slot06 对 slot01–05；两策略下的 10 条旧反馈均可区分（slot06 旧 FP=0、TP=32；slot01–05 旧 FP=32、TP=0）。34 条旧完整反馈并列中，6 条的盲评关系为 `EQUIVALENT`，28 条为 `INCOMPARABLE`；**没有**“盲评明确质量不同，但旧完整反馈相同”的 pair。这里的 `NOT_FOUND_AFTER_CHECK` 只指本次 42 对 × 两策略的精确对照，不指完整 30-parent 框架或所有可能的新 witness。没有对其它 pair 主动构造新 witness，记 `NOT_ATTEMPTED`。

历史 train-dev 变体选择须另行判断。`historical_variant_selection_check.csv` 从原 `dev_metrics_and_selection.json` 复核：门槛为 Fixed-Safe≥1/6、Target Detect≥3/6；合格变体为 `anchor_20`、`anchor_25`，规则选择 `anchor_20`。盲评判断针对两个**训练 parent 的候选 assertion**；它们不是六个 dev parent 的 30 条模型输出或该历史决策的直接输入。没有改变历史决策日志的证据，也没有在固定规则下做因果干预。因此“本次质量判断影响历史 `anchor_20` 选择”状态为 **NOT ESTABLISHED**，绝不由旧反馈并列推导。原 Phase-B 训练日志与 adapter 缺失，亦不能补称实际训练影响。

`historical_timeout_by_object.csv` 逐对象检查这两个 parent 的 1,024 个既存历史 probe `result.json`、4,096 个 correct/buggy 编译与仿真阶段：明确 timeout 0、缺字段 0；不推广到其它运行。`status_ledger.csv` 分开记录 `NOT_FOUND_AFTER_CHECK`、`NOT_ATTEMPTED`、`NOT_ESTABLISHED` 和限定范围内无超时。

只读重建命令：`pwsh -NoProfile -File scripts/unblind_independent_review_20260922.ps1`。该脚本复验既有封存、读取旧反馈、复制原件并生成对照表；不重训、不修改原判断。
