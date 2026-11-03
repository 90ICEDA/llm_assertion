# 过去实验记录补全报告

本轮补齐此前列出的5类历史记录缺口。2项已恢复并验证，2项部分补齐，1项确认来源不匹配且缺少历史推导，提供明确解决路径。未执行新的模型或RTL实验，未改写旧封存记录。

| 缺口 | 状态 | 补全结果 |
|---|---|---|
| historical_python_source | recovered_and_reproduced | 从原始编辑日志重建2文件7个源码状态；三份原始ledger全JSON一致；启动命令时序与版本相符。 |
| fifo_upstream_revision | recovered_and_verified | 精确提交48ff7a7e2ef782cf778d47910cf85835c64b1bce；本地Git blob与GitHub固定URL下载字节一致；实验源码仅CRLF/LF不同。 |
| root_experiment_git_commit | partially_recovered_original_commit_unavailable | 找到相邻旧仓库49da13029efe7d0080866457d75a3a5bf68811c9，但它没有本轮研究代码。为3份关键历史运行补建内容寻址版本清单。 |
| cancelled_call_usage | partially_recovered_final_usage_unavailable | 补录HTTP服务耗时258秒、截断前18354与截断后16383的日志计数、slot释放值8196；最终usage仍null。 |
| stat_upstream_derivation | unrecoverable_from_checked_records_mismatch_confirmed | 官方固定源码再次核验通过，确认与本地8行pipeline接口不同；已追加有效来源更正，历史admission=false。 |

## 已恢复：旧适配器执行版本

从本地原始工具调用记录提取相关代码补丁，重建research15_evidence.py及research15_acceptance.py，共7个源码状态。只保存相关源码编辑、记录位置和哈希，不复制无关会话。最终重建文本与现存文件一致。

2026-10-15 13:23:41（UTC+8）启动initial资格进程时，适配器v005已写入；13:25:41修改到v006后，原进程仍使用已导入的旧模块。13:27:44额外时序修复启动时使用新版本。这与三份原始结果完全匹配。

| 历史运行 | 恢复适配器 | 恢复接受门 | 原始ledger复算 |
|---|---|---|---|
| original | v005 | v004 | 全JSON一致 |
| semantic_repair | v005 | v004 | 全JSON一致 |
| initial_temporal_continuation | v006 | v004 | 全JSON一致 |

这是历史重建，不是事后取得旧进程内存快照。重建能解释旧错误：original旧版仍输出3条所谓detections，修正版本将它们降为unknown。恢复错误版本仅用于可复现性，不能恢复其错误科学结论。具体源码、补丁、调用记录和校验哈希见source_history/。

## 已恢复：FIFO精确上游版本

本地external/verilog-axis的HEAD与shallow记录均为48ff7a7e2ef782cf778d47910cf85835c64b1bce。该提交axis_fifo.v的Git blob为dfa465792f052486ac6f8d4c483318d4a338076d。
GitHub固定提交文件下载与本地Git对象SHA256一致：aefddc67fc3552d919280424606fc6b048e61d7df9ee7ee0f8801c082c1cfc39。实验工作文件SHA256为b29a492b29dcb6b060a3d40d77206e490533433b23d2a954d3b84b08985db16e；仅CRLF/LF差异，规范化文本一致。20261014及20261015实验记录的source_sha256与该工作文件匹配。
官方来源：[固定提交axis_fifo.v](https://raw.githubusercontent.com/alexforencich/verilog-axis/48ff7a7e2ef782cf778d47910cf85835c64b1bce/rtl/axis_fifo.v)。WSL首次下载失败保留，Windows成功下载和哈希验证另存official_download/windows_result.json。

## 部分补齐：项目Git版本

当前工作区.git为空。只读检查相邻D:/AssertionForge-main，找到2026-07-01提交49da13029efe7d0080866457d75a3a5bf68811c9，但研究适配器、原生闭环及stat案例都不在其中，故不能把它填为实验HEAD。检查27个较小归档目录成员，未发现可用项目Git历史；发现的stat成员主要是既有实验/训练结果。3.7GB Python运行环境归档未搜索内容，此限制记录在inventory。

已建立content_versions.json：为三个关键运行关联模型请求/响应/SVA、实际编译TB/命令/工具版本、实际RTL回放和恢复Python版本，生成内容寻址ID。它可作为历史产物版本标识，但不是Git提交。

仍需的解决方案：若有当时项目完整备份或远端分支，恢复其.git并核验每个实验输入哈希；若无，保留root_git_commit=null，使用此次内容版本清单及已有封存快照。后续另建版本控制和运行前快照，只能记录未来，不得倒填过去。

## 部分补齐：被取消模型调用成本

原始请求、attempt及cancellation已归档。服务task129日志补出截断前prompt=18354、调度后16383、最后进度7168、释放slot n_tokens=8196、HTTP500及服务耗时4m18s。
服务耗时258秒与提交/结束墙钟差254秒不同；旧388.651028秒是记录区间上界。三者分字段保留，不能混为精确客户端调用耗时。slot计数不是最终prompt_eval_count，不能把8196直接当实际输入token。没有最终usage回执，输入/输出实际消耗继续null，未收到完整响应也不等于生成token必为0。

仍需的解决方案：寻找原模型服务最终task usage或按请求统计回执；如果没有则无法精确恢复。统计中保留1次取消调用、实测服务耗时及token不可用项。未来在发请求前创建日志，逐块flush响应并在finally/SIGINT写取消终态；服务进度计数与正式usage分开保存。重跑只能产生新成本，不能补成旧成本。

## 无法补成真实来源：stat

官方axis_stat_counter.v固定提交与本地依赖换行规范化一致，但本地case505是不同接口的8行模型。元数据原称actual_rtl_logic_change/final_verified_admitted，当前没有原始推导证明。已写stat_origin/effective_provenance.json覆盖来源解释：local_synthetic_pipeline_with_unverified_upstream_mapping，historical_admission=false；原元数据留存。

可选解决方案：
1. 保留为人工工程案例，由明确的规格定义采样延迟、长度捕获和重叠行为；不能据此声称上游历史修复。
2. 找回生成脚本/原始补丁、输入源码blob、约简假设和事件映射，验证后再讨论历史接入；仅提供新的规格文字不能补出历史来源。
3. 另选真实上游前后提交，在原AXI接口复现；这属于新的案例实验，不能追认旧案例。

## 验收与用法

两轮旧交付清单合计91项均未改变。恢复产物另存本目录，现有模型拒绝结果、unknown和未执行实验状态保持。
复算历史版本：`wsl -- python3 scripts/recover_research_records.py replay_source_history`。
核验补充档案：`wsl -- python3 scripts/recover_research_records.py verify`。
机器可读入口：recovery_status.json；完整性清单：manifest.json；历史版本：content_versions.json。
