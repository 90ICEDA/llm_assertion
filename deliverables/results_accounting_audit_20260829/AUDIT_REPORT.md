# 样本流转与统计口径审计

## 结论

60→46 是有证据的 admission 流程；40-parent selection 与 30-parent Pilot 是不同实验资产/分支，不能写成 46→40→30 的线性筛选。四套集合计数为 {'initial60': 60, 'accepted46': 46, 'selection40': 40, 'latest_train30': 30}。精确交集见 `set_relationships.csv`，完整 ID 见 `parent_id_sets.csv`。

## 证据与排除

`parent_membership_and_exclusions.csv` 对 60→46 的 14 个排除逐一给出 gate 原因和证据；对 40、30 仅记录跨实验 membership，不把“不在该集合”虚构为排除。流程图源文件为 `sample_flow.mmd`。

## 统计口径

`metric_sources.csv` 逐项记录 numerator、denominator、statistical unit、dataset、formula 和 source。`integrity_findings.csv` 标出相同分数、相同分子分母、单位差异、重复与缺失。candidate×probe incidence 不是 candidate 或 parent；family recall 的分母是 family；TOR 的分母是 primary-success query。

## 完整性发现

240 个 candidate evidence 齐全，dominance JSONL 的 pair 数、pair ID 唯一性和冻结 SHA-256 均通过。使用 Windows 长路径安全读取后，probe 网格为 15,360/15,360，缺 0 个；此前普通 glob 漏读长路径不能作为 verdict 缺失证据。

## 重算

运行：

```powershell
python scripts/rebuild_results_audit.py
```

脚本只读逐行 CSV、JSONL、candidate/probe result evidence 和冻结 manifest，并重建本目录全部 CSV/JSON/Markdown；不重新执行仿真、训练、OOD 或扩展 pairs。
