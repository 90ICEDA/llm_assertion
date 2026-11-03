# AssertionForge 最终验收包

本目录集中保存八项任务的最终验收产物。所有文件均为自包含副本，并由 `artifact_inventory.csv` 和 `SHA256SUMS.txt` 冻结。

## 验收目录

1. **新增数据验收定版** — `accepted` — `01_dataset_acceptance/` — 730 files
2. **新独立case主实验** — `accepted` — `02_main_experiment/` — 7 files
3. **统计显著性与稳定性** — `accepted` — `03_statistics_stability/` — 7 files
4. **Trace与RTL机制分析** — `accepted` — `04_mechanism_analysis/` — 18 files
5. **同预算visible-only选择** — `accepted` — `05_equal_budget_selection/` — 15 files
6. **Failure-guided repair** — `accepted` — `06_failure_guided_repair/` — 683 files
7. **过拟合挑战与泛化数据** — `accepted_controlled_semantic_scope` — `07_overfit_generalization/` — 37 files
8. **跨模型成本与复现** — `accepted` — `08_cross_model_repro/` — 14 files

## 使用说明

- 先查看 `acceptance_overview.xlsx` 或 `acceptance_matrix.csv`。
- 逐项数据使用对应编号目录。
- 文件完整性使用 `SHA256SUMS.txt` 或 `artifact_inventory.csv` 验证。
- 第7项为受控语义过拟合挑战集，不应描述为真实项目RTL重新综合实验。
- 第8项的一键脚本和复现文档已复制进对应目录。
