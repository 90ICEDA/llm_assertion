# case510 witness 命令直录（2026-09-22）

本目录重放已有 `tb_held_flush.v`，不是训练或新 probe 选择。`command_runs.json` 保存六项命令的**实际 argv、退出码、原始 stdout/stderr 路径与 SHA-256**：`iverilog -V`、`vvp -V`、correct/buggy 各一次编译和仿真。`*.stdout.raw`、`*.stderr.raw` 是从进程管道直接保存的完整原始字节；同名 `*.txt` 仅供阅读（WSL 启动警告的文本编码可能在 UTF-8 视图中显示为乱码，raw 文件为准）。工具版本输出也在原始流中，不只依赖人工摘录。

`input_hashes.csv` 列出 correct RTL、buggy RTL 和 testbench 的路径、字节数、SHA-256；`compiled_output_hashes.csv` 列出新编译产物。两次编译和两次仿真，以及两个版本查询，退出码均为 0。correct 仿真 stdout 的 `SUMMARY slot06_fail=0 slot07_fail=1` 与 buggy 仿真的 `SUMMARY slot06_fail=1 slot07_fail=1` 是本次命令直接捕获；两份 stdout 的 SHA-256 分别与原保存的 `fixed_stdout.log`、`buggy_stdout.log` **完全一致**。stderr 中有 WSL localhost/NAT 警告，不能因其存在就当作编译失败，也不能删去。

本次完成的命令未设显式 timeout 限额；只能说本次观察到命令完成，不能据此推广历史 probe 或其它 witness 的 timeout 状态。命令由 `pwsh -NoProfile -File scripts/capture_case510_witness_20260922.ps1` 产生，重跑会更新本目录的**后补重放**文件，不会修改原 2026-09-21 封存。
