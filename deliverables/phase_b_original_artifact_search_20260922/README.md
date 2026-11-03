# Phase-B 原训练产物只读查找（2026-09-22）

结论：在当前可访问的本地范围内，未找到 `checkpoint-004058/adapter_model.safetensors`、`training_result.json`、`train_log.jsonl` 或 `latest_checkpoint.txt`。四项继续标为 `MISSING`（见 `MISSING.csv`），不是“确认历史上从未存在”。未重新训练、未生成替代 checkpoint。

查找范围：仓库根目录和 `deliverables/` 下全部现有 tar.gz/zip，共 34 个归档、239,996 个成员（包括 3.7 GB 的 Python 环境归档及嵌套证据归档）；逐归档字节数、SHA-256、成员数和命中数见 `archive_inventory.csv`。另递归列举 v1/v2 behavioral 输出、Phase-B OOD 输出、`outputs/checkpoints`、`deliverables`、`analysis`、`scripts`、`src` 等共 10 个目录、131,442 个现存文件，目标命中为零（见 `directory_inventory.csv`）。`archive_target_members.csv` 与 `directory_target_files.csv` 为空表，表示这些限定范围内没有目标文件。

另一份本地 `D:\AssertionForge-main` 存在，但没有对应的 `outputs/behavioral_preference_pilot_v2/balanced_behavioral_objective_v1/phase_b_refit_all30_v1` 或 `outputs/phase_b_ood_eval_v1` 目录。本机 WSL Ubuntu 可访问；脚本中声明的 `/root/autodl-tmp/AssertionForge-main1` 经 WSL root 只读 `ls -ld` 检查为 `No such file or directory`。这是当前本机 WSL 的结果，**不能**等同于曾经的远端 AutoDL 机器已经查过或其文件从未存在。未取得远端运行机/外部存储的可访问路径。

冻结的 `frozen_ood_top1_v1/query_manifest.json` 声明了 `checkpoint-004058` 的 adapter 路径、adapter SHA-256 `c1bc4c54f64a50acbdec3288de3325cffb6a05ed61a94a3c7a6df0ffd34bdb3a`，以及 `training_result.json` 的 SHA-256。`src/generate_balanced_behavioral_phase_b_ood.py` 的代码会先核对 adapter hash 再调用 `PeftModel.from_pretrained`；现存 `generation_run_manifest.json` 也记录了同一 adapter hash。但这些都是**路径、预期 hash 与运行声明**，缺少实际 adapter 字节和原始训练日志时无法独立复算 hash、证明本地可复现加载，或证实 4,058 个 schedule 步骤已执行。状态仍为训练执行 `UNKNOWN`、实际 adapter 字节 `MISSING`、本地复现加载 `NOT DEMONSTRATED`。

可重跑的只读扫描：`pwsh -NoProfile -File scripts/search_phase_b_original_training_artifacts_20260922.ps1`。它不启动训练，也不解包或覆盖归档；只列成员并计算归档 hash。
