# 本地整理与验证记录

日期：2026-11-03（Asia/Shanghai）。此文件由本次整理产生，历史研究结果不属于本次重跑结果。

## 副本范围

- 保留 36,065 个项目文件（不含本报告与哈希清单），约 681.7 MiB。
- 保留 `src/`、`scripts/`、`configs/`、`analysis/`、全部 `rtl_cases*` 基准集合、必要 trace/VCD/规格/测试平台、Markdown 文档、四份 requirements、根许可证和第三方许可证。第三方源码含 OpenTitan、common_cells、verilog-axis 及它们已有的锁文件。
- `outputs/` 与 `deliverables/` 保留 2986 项显式引用的固定输入/小型历史资料；兼容 RTL 是特意保留的运行资源。它们不是完整实验归档。
- 排除所有 Git 元数据、虚拟环境、node_modules、缓存、日志、编译/仿真可执行文件、模型权重、工具安装副本、重复压缩包、根目录调试波形、生成的 Office 汇报与调试预览。保留配置明确引用的表格例外并去除作者元数据。
- 原目录的 `.git` 不能被 Git 识别，整理以文件快照为准。未对目标初始化 Git，未创建远程仓库、提交或推送。

## 敏感信息与配置

- `.secrets/` 的 3 份本地凭据文件、真实 `.env`、私钥/证书类文件均未复制；`.env.example` 只有占位符。
- 检查真实已知凭据的重复出现、常见令牌格式、私钥头及凭据文件名；最终剩余匹配为 0。有 0 个文本文件进行了凭据替换，另清理了本机用户目录信息。
- 排除 85 份个人运行授权 JSON。历史作者、论文和许可证署名保持原样。
- 第三方 PEM 文件未包含，1 个源码注释中的 PEM 测试密钥块已清理，公开的数值密码学测试向量继续保留；仅含 PEM 格式识别字符串的解析源码原样保留。本副本不是 OpenTitan 全套固件签名测试的完整分发包；本项目所用 RTL 源码和头文件已保留。
- 第三方源码自带的小型二进制测试输入属于必要 fixture，特意保留；3 份编译后的 ELF 已排除。通用 env 忽略规则已限定到项目根目录，避免漏掉 SystemVerilog 验证环境源码；上游锁文件和固定测试输入添加了精确例外。
- 两份 repair_regression 配置已改成相对于项目根目录的路径。其他研究脚本中的历史绝对路径仍需按机器调整。
- 扫描为文件内容/格式规则检查，不等同于覆盖任意编码形式的人工安全审计。原项目中的敏感文件没有修改。

## 实际验证

- 项目 Python 文件语法解析：826 份，错误 0；JSON 解析：3270 份，错误 0。未把第三方 Python 项目作为本项目测试。
- 已有 unittest 离线测试：退出码 0，Python 3.13.13；详细输出如下。
- 复制后逐文件 SHA-256 校验：36065 份全部匹配；文件集合一致。
- Git ignore 检查：保留文件被忽略 0；目标无 `.git`、虚拟环境、依赖安装目录或真实密钥文件；无超过 50 MiB 的单文件。
- 原项目纳入清单的文件哈希保持不变：True。适用路径未发现 AGENTS.md：True。
- 最终副本 case01 的 correct/buggy RTL 均执行 Icarus 编译及 vvp 仿真：通过。此检查只证明基础编译和运行，不证明 SVA 生成质量或完整基准正确性。
- 基准结构检查发现 0 个没有 paired buggy.v/tb.v 的位置；见下方既有缺项记录，不能据此声称所有基准可直接运行。

```text
test_partial_response_preserved_without_inventing_final_usage (test_model_cancellation_record.CancellationRecord.test_partial_response_preserved_without_inventing_final_usage) ... ok
test_missing_native_trace_not_success (test_research17_fifo_feedback.SamplingChecks.test_missing_native_trace_not_success) ... ok
test_post_update_value_cannot_masquerade_as_sample (test_research17_fifo_feedback.SamplingChecks.test_post_update_value_cannot_masquerade_as_sample) ... ok
test_pre_update_simultaneous_push_pop_and_reset (test_research17_fifo_feedback.SamplingChecks.test_pre_update_simultaneous_push_pop_and_reset) ... ok

----------------------------------------------------------------------
Ran 4 tests in 0.029s

OK
```

## 未验证与后续配置

未联网安装完整依赖、下载模型、调用付费 API、跑模型生成/训练、完整基准、JasperGold 或 Verilator SVA 流程。WSL 的 PATH 中发现 Python 与 Icarus，未发现 JasperGold/Verilator；如使用原生 SVA 请另装工具并设置 `VERILATOR`。GraphRAG 模板、设计 PDF、知识图谱、商业工具许可及模型由使用者提供。

部分旧脚本依赖运行时拼接的历史目录及完整归档；此副本只做显式引用的资源保留，不承诺所有历史续跑命令可直接重现。裁剪及路径脱敏后，旧实验 SHA256 清单不能当成本副本的完整性清单；使用本次 `COPY_MANIFEST.sha256`。JavaScript 导出需要原代码所用外部 artifact runtime，未验证。

原始 LICENSE.txt 及第三方许可证已原样保留；发布时继续保留这些文件及原有署名。
