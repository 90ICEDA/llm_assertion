# AssertionForge 项目文件清单

本文档用于整理 `D:\AssertionForge-main` 的文件用途。由于仓库中包含大量重复结构的基准 case、生成产物、第三方镜像和依赖缓存，本文采用两种方式说明：

- 对需要维护的源码、脚本、文档：按文件级列出用途。
- 对批量重复的 case 文件、生成文件、第三方目录：按目录级和模板级列出用途。

## 1. 仓库整体结构

- `README.md`：项目总说明，介绍 AssertionForge 的两阶段流程、WSL2/Qwen/JasperGold MVP 跑法，以及新设计接入方式。
- `requirements.txt`：Python 运行依赖列表，覆盖 LLM、GraphRAG、PDF、图处理、数据处理等库。
- `LICENSE.txt`：许可证文本。
- `entity_extraction.txt`：实体抽取相关文本资产，供知识图谱/提示词流程参考。
- `8个case_trace_abstraction_prompts.docx`：trace abstraction 相关提示词文档产物。
- `reference_weekly_report.docx`：周报/参考汇报文档。
- `trace_abstraction_results.xlsx`：trace abstraction 实验结果表。
- `trace_abstraction_summary.docx`：trace abstraction 总结文档。

## 2. 顶层目录职责

- `.git/`：Git 元数据目录。
- `.agents/`：代理/自动化相关内部目录。
- `.secrets/`：本地 API 密钥目录。
- `docs/`：方法说明和实验汇总文档。
- `external/`：第三方外部代码镜像，目前主要是 `opentitan`。
- `node_modules/`：Node.js 依赖缓存目录。
- `outputs/`：脚本生成的文档、表格、中间 CSV/JSON、预览图和调试工件。
- `rtl_cases/`：10 个 mini RTL case 与对应评测/报告脚本。
- `rtl_cases_real/`：从真实 OpenTitan RTL 提取出的 mutation scaffold。
- `rtl_cases_real_active/`：当前启用的真实 RTL benchmark 集。
- `rtl_cases_real_admitted_20260619/`：2026-06-19 admitted 版本数据集。
- `rtl_cases_real_admitted_resume_20260619/`：admitted 集的 resume 续跑版本。
- `rtl_cases_real_iverilog_ready/`：已整理到可直接用 Icarus Verilog 跑通的真实 RTL 集合。
- `src/`：主程序源码、研究原型脚本、报表脚本、导出脚本。

## 3. `src/` 源码文件清单

当前 `src/` 共 85 个文件，其中源码主干和实验脚本都集中在这里。

### 3.1 入口与配置

- `src/main.py`：主入口，根据 `FLAGS.task` 分发到 `gen_plan`、`build_KG`、`use_KG`。
- `src/config.py`：主配置文件，集中定义任务类型、设计路径、模型参数、KG 开关、formal rerank 选项等。
- `src/config_mvp_qwen_wsl2_template.py`：WSL2 + 本地 Qwen + JasperGold 最小 MVP 配置模板。
- `src/command_line_args.py`：命令行参数解析与配置覆盖逻辑。

### 3.2 知识图谱与上下文构建

- `src/gen_KG_graphRAG.py`：构建知识图谱的主流程，负责 PDF 处理、GraphRAG 初始化、索引运行和日志目录检测。
- `src/doc_KG_processor.py`：文档知识图谱处理逻辑，负责文档侧实体/关系和上下文生成。
- `src/use_KG.py`：使用既有 KG 的入口逻辑。
- `src/kg_traversal.py`：知识图谱遍历辅助逻辑。
- `src/context_generator_BFS.py`：基于 BFS 的上下文生成器。
- `src/context_generator_path.py`：基于路径搜索的上下文生成器。
- `src/context_generator_rag.py`：基于 RAG 的上下文生成器。
- `src/context_generator_rw.py`：另一套随机游走/图遍历式上下文生成器。
- `src/context_pruner.py`：上下文裁剪与压缩。
- `src/design_context_summarizer.py`：为设计生成全局摘要，用于上下文增强。
- `src/dynamic_prompt_builder.py`：动态提示词拼装器，按信号/上下文构造 NL plan 与 SVA 提示。

### 3.3 RTL 解析与结构建模

- `src/rtl_parsing.py`：RTL 解析与结构提取。
- `src/rtl_analyzer.py`：较完整的 RTL 分析主模块，负责提取模块/信号/结构信息。
- `src/rtl_kg.py`：把 RTL 结构映射到图/知识表示。

### 3.4 计划生成、SVA 生成与 formal rerank

- `src/gen_plan.py`：核心流水线，负责读规范、加载 KG、初始化 LLM、生成 NL plans、生成候选 SVA、跑 JasperGold、formal rerank、保存报告。
- `src/sva_extraction.py`：从 LLM 输出块中抽取 SVA 文本。
- `src/utils_gen_plan.py`：`gen_plan` 的辅助函数，包含 proof status 抽取、覆盖率分析、TCL 文件定位等。
- `src/utils_LLM.py`：LLM 初始化与推理辅助逻辑。
- `src/utils_LLM_client.py`：较轻量的 LLM 客户端封装。

### 3.5 基础工具与保存

- `src/utils.py`：通用工具函数，含计时、路径、日志输出辅助等。
- `src/saver.py`：运行日志、异常、产物目录管理。

### 3.6 核心可视化/资产文件

- `src/KG_vis.png`：README 中展示的知识图谱可视化图片。

### 3.7 研究原型运行脚本

- `src/run_antecedent_repair_prototype.py`：前件修复实验原型主脚本。
- `src/run_multi_model_small_eval.py`：多模型小规模对比评测。
- `src/run_prompt_ablation_prototype.py`：提示词消融实验原型。
- `src/run_trace_abstraction_prototype.py`：trace abstraction 实验原型。
- `src/run_trace_selection_prototype.py`：trace 选择/打分实验原型。

### 3.8 研究分析脚本

- `src/build_antecedent_repair_artifacts.py`：整理前件修复实验产物。
- `src/build_clean_assertion_master_real.py`：构建真实 RTL 的 clean assertion 主表。
- `src/build_golden_deliverables.py`：生成 golden 相关交付物。
- `src/build_golden_docs.py`：生成 golden 说明文档。
- `src/build_multi_model_observation_doc.py`：生成多模型观察报告文档。
- `src/build_new_hard_cases_design.py`：构建新增 hard cases 设计主表。
- `src/build_new_hard_cases_doc.py`：生成新增 hard cases 说明文档。
- `src/build_prompt_ablation_docs.py`：生成提示词消融实验文档。
- `src/build_quadrant_analysis_real.py`：生成四象限分析数据。
- `src/build_quadrant_summary_docx.py`：生成四象限总结文档。
- `src/build_raw_vs_summary_analysis.py`：分析 raw trace 与 trace summary 的效果差异。
- `src/build_raw_vs_summary_case_notes.py`：生成 raw vs summary case notes 文档。
- `src/build_temporal_type_analysis.py`：按 temporal type 分析结果。
- `src/build_temporal_type_failure_examples.py`：生成 temporal type 失败样例文档。
- `src/build_trace_abstraction_artifacts.py`：整理 trace abstraction 实验产物。
- `src/build_trace_overfit_analysis_real.py`：分析 trace overfit 现象。
- `src/build_trace_overfit_docs.py`：生成 trace overfit 说明文档。
- `src/build_trace_selection_definition_doc.py`：生成 trace quality/selection 定义文档。
- `src/build_trace_tradeoff_analysis_real.py`：分析 trace tradeoff。
- `src/build_trace_tradeoff_docs.py`：生成 trace tradeoff 文档。
- `src/build_vacuity_analysis_real.py`：分析 vacuity/前件不触发问题。
- `src/build_vacuity_docs.py`：生成 vacuity 说明文档。
- `src/recheck_golden_wsl.py`：在 WSL 环境重跑/复查 golden 结果。
- `src/refresh_case119_case124_benchmark_impacts.py`：刷新 case119/case124 调整后对 benchmark 的影响。

### 3.9 表格导出脚本

- `src/export_antecedent_repair_xlsx.mjs`：导出前件修复结果为 Excel。
- `src/export_clean_assertion_deliverables.mjs`：导出 clean assertion 交付表。
- `src/export_golden_xlsx.mjs`：导出 golden 相关 Excel。
- `src/export_multi_model_small_eval_xlsx.mjs`：导出多模型小评测 Excel。
- `src/export_new_hard_cases_design_xlsx.mjs`：导出新增 hard cases 设计表。
- `src/export_prompt_ablation_results_xlsx.mjs`：导出提示词消融结果表。
- `src/export_quadrant_analysis_xlsx.mjs`：导出四象限分析表。
- `src/export_raw_vs_summary_xlsx.mjs`：导出 raw vs summary 对比表。
- `src/export_temporal_type_analysis_xlsx.mjs`：导出 temporal type 分析表。
- `src/export_trace_abstraction_results_xlsx.mjs`：导出 trace abstraction 结果表。
- `src/export_trace_overfit_report_xlsx.mjs`：导出 trace overfit 报告。
- `src/export_trace_selection_xlsx.mjs`：导出 trace selection 结果表。
- `src/export_trace_tradeoff_xlsx.mjs`：导出 trace tradeoff 结果表。
- `src/export_vacuity_analysis_xlsx.mjs`：导出 vacuity 分析表。

### 3.10 `__pycache__/`

- `src/__pycache__/`：Python 编译缓存，不属于手工维护源码。

## 4. `docs/` 文档目录

当前 `docs/` 共 19 个文件。

- `docs/wsl2_formal_rerank_mvp.md`：WSL2 Ubuntu 下运行 Qwen + JasperGold formal rerank MVP 的操作说明。

### 4.1 `docs/real_rtl_scaleout/`

该目录保存真实 RTL scale-out 评测的汇总材料，主要是清洗后的主表、覆盖率表、候选级/案例级汇总和报告。

- `antecedent_coverage_30cases.csv`：30 个案例的前件覆盖统计。
- `assertion_clean_master_iv12.csv`：清洗后的 assertion 主表。
- `assertion_clean_notes_iv12.md`：主表清洗说明。
- `assertion_clean_stats_iv12.csv`：清洗统计摘要。
- `dataset_inventory_30cases.csv`：30 case 数据集清单。
- `full_admitted_cloud_method_bugclass_candidate_level.csv`：按方法和 bug class 的 candidate-level 统计。
- `full_admitted_cloud_overall_candidate_level.csv`：总体 candidate-level 统计。
- `golden_self_check_active_30cases.csv`：active 30 case 的 golden 自检结果。
- `golden_status_30cases.csv`：golden 状态总表。
- `overfit_generalization_summary_iv12.csv`：overfit 泛化摘要。
- `requested_bundle_report_20260621.md`：按请求打包的交付报告。
- `resume_observed_trace_summary_candidate_rows.csv`：resume 附件中 observed trace summary 级别数据。
- `trace_overfit_detail_iv12.csv`：trace overfit 细节表。
- `trace_overfit_observed_from_resume_attachment.csv`：从 resume 附件观察到的 overfit 明细。
- `trace_summary_failure_attribution_resume_observed.csv`：trace summary 失败归因表。
- `trace_summary_miss_attribution_full_iv12.csv`：trace summary miss 归因表。
- `trace_summary_scaleout_report_20260621.md`：trace summary scale-out 报告。
- `trace_summary_vs_spec_plus_rtl_gap_candidate_level.csv`：trace summary 相对 spec+rtl 的差距分析。

## 5. `rtl_cases/` Mini benchmark 目录

当前 `rtl_cases/` 共 600 个文件。它既包含 10 个小型 RTL benchmark case，也包含用于评测、导出、总结、周报的脚本与表格。

### 5.1 顶层说明与管理文件

- `rtl_cases/README.md`：10 个 mini case 的结构说明、仿真流程、trace divergence summary、held-out policy 和 prompt experiment 说明。
- `rtl_cases/DELIVERABLES_INDEX.md`：交付物索引。
- `rtl_cases/METHOD_FLOWCHART.md`：方法流程图文档。
- `rtl_cases/PROMPT_INPUT_COMPARISON.md`：不同 prompt 输入对比说明。
- `rtl_cases/SVA_PROMPT_EXPERIMENT.md`：SVA prompt 实验说明文档。
- `rtl_cases/REAL_RTL_BENCHMARK.md`：真实 RTL benchmark 说明。

### 5.2 顶层脚本

- `rtl_cases/audit_golden_metadata.py`：审计 golden 元数据完整性。
- `rtl_cases/audit_trace_divergence_gate.py`：检查 trace divergence gating 结果。
- `rtl_cases/build_real_rtl_benchmark.py`：构建真实 RTL benchmark 根数据。
- `rtl_cases/check_case_hardness.py`：计算/检查 case 难度。
- `rtl_cases/check_golden_sva.py`：校验 golden SVA 质量与可用性。
- `rtl_cases/compare_strict_eval_reports.py`：比较不同 strict eval 报告。
- `rtl_cases/evaluate_generated_sva.py`：评估生成的 SVA。
- `rtl_cases/evaluate_generated_sva_v2.py`：早期/简化版 SVA 评测脚本。
- `rtl_cases/export_manual_golden_table_xlsx.mjs`：导出人工 golden 表为 Excel。
- `rtl_cases/generate_best_assertion_docx.py`：生成 best assertion 文档。
- `rtl_cases/generate_deliverables_docx.py`：生成交付文档。
- `rtl_cases/generate_eval_deliverables.py`：生成评测交付包。
- `rtl_cases/generate_real_rtl_testbenches.py`：给真实 RTL case 生成 testbench。
- `rtl_cases/generate_requested_bundle.py`：按请求打包所需报告/表格。
- `rtl_cases/generate_scaleout_report.ps1`：生成 scale-out 报告的 PowerShell 脚本。
- `rtl_cases/generate_sva_from_prompts.py`：从 prompt 生成 SVA。
- `rtl_cases/ollama_cli_bridge.py`：对接本地 Ollama CLI。
- `rtl_cases/postprocess_strict_eval_report.py`：清洗 strict eval 报告。
- `rtl_cases/prepare_prompt_assets.py`：为 prompt 实验准备输入资产。
- `rtl_cases/qwen_api_bridge.py`：对接 Qwen API。
- `rtl_cases/real_rtl_case_catalog.py`：真实 RTL case 目录与元数据主表逻辑。
- `rtl_cases/regenerate_waveforms.sh`：重建所有波形 CSV/VCD。
- `rtl_cases/regenerate_waveforms_for_root.py`：从指定根目录批量重建波形。
- `rtl_cases/rerun_sva_prompt_experiment.py`：重跑 prompt 实验。
- `rtl_cases/run_active_final_stamp.sh`：给 active 数据集做最终戳记/归档。
- `rtl_cases/run_cuda12_probe.sh`：环境探测脚本。
- `rtl_cases/run_full_admitted_iv12.sh`：运行 admitted iv12 评测。
- `rtl_cases/run_metric_probe_regression.py`：metric probe 回归检查。
- `rtl_cases/run_resume_generate.sh`：resume 版生成流程。
- `rtl_cases/run_resume_generate_casewise.sh`：按 case 的 resume 生成流程。
- `rtl_cases/run_waveforms_subset.sh`：只重建部分波形。
- `rtl_cases/summarize_strict_eval_by_method.py`：按方法汇总 strict eval。
- `rtl_cases/summarize_strict_eval_by_method_and_bug_class.py`：按方法和 bug 类汇总 strict eval。
- `rtl_cases/summarize_strict_eval_case_dedup_by_method_and_bug_class.py`：去重后按方法和 bug 类汇总 strict eval。
- `rtl_cases/summarize_trace_divergence.py`：生成 good/bad trace 差异摘要。
- `rtl_cases/sva_eval_grammar.py`：SVA 语法检查辅助。
- `rtl_cases/sva_static_filter.py`：SVA 静态质量过滤器。
- `rtl_cases/sync_cloud_strict_report.ps1`：同步云端 strict report。
- `rtl_cases/vcd_to_csv.py`：将 VCD 转成逐周期 CSV。
- `rtl_cases/vcd_to_trace_text.py`：把波形 CSV/VCD 转成文本 trace。

### 5.3 顶层数据/文档文件

- `rtl_cases/20260524_AssertionForge周报.md`：周报 Markdown。
- `rtl_cases/AssertionForge_Deliverables_20260530.docx`：交付文档。
- `rtl_cases/best_assertion.docx`：最佳断言说明文档。
- `rtl_cases/best_assertion_per_case.csv`：每 case 最佳断言表。
- `rtl_cases/BEST_ASSERTION_PER_CASE.docx`：最佳断言文档版。
- `rtl_cases/BEST_ASSERTION_PER_CASE.md`：最佳断言 Markdown 版。
- `rtl_cases/case_manifest.json`：mini case 元数据清单。
- `rtl_cases/case_method_review.csv`：case-method 评审表。
- `rtl_cases/case_method_review_current.csv`：当前评审表。
- `rtl_cases/case_method_review_current.md`：当前评审说明。
- `rtl_cases/case_method_review_latest.csv`：最新评审 CSV。
- `rtl_cases/case_method_review_latest.md`：最新评审说明。
- `rtl_cases/golden_eval_one.csv`：golden 评测样本结果。
- `rtl_cases/golden_eval_tmp.csv`：临时 golden 评测结果。
- `rtl_cases/golden_metadata_audit.csv`：golden 元数据审计表。
- `rtl_cases/golden_sva_check_report.csv`：golden SVA 检查结果。
- `rtl_cases/MANUAL_GOLDEN_SVA_TABLE.md`：人工 golden SVA 表说明。
- `rtl_cases/MANUAL_GOLDEN_SVA_TABLE.xlsx`：人工 golden SVA 表。
- `rtl_cases/metric_probe_regression_report.csv`：metric probe 回归报告。
- `rtl_cases/strict_eval_case04.csv`：某单 case strict eval 明细。
- `rtl_cases/strict_eval_case_dedup_by_method_and_bug_class_smoke.csv`：去重统计 smoke 表。
- `rtl_cases/strict_eval_case_dedup_rows_smoke.csv`：去重明细 smoke 表。
- `rtl_cases/strict_eval_comparison_rerun.csv`：rerun 对比表。
- `rtl_cases/strict_eval_comparison_rerun.md`：rerun 对比说明。
- `rtl_cases/strict_eval_comparison_rerun_by_method.csv`：按方法的 rerun 对比。
- `rtl_cases/strict_eval_comparison_rerun_by_method.md`：按方法的 rerun 说明。
- `rtl_cases/strict_eval_comparison_trace_clean_34.csv`：trace clean 34 对比表。
- `rtl_cases/strict_eval_comparison_trace_clean_34.md`：trace clean 34 说明。
- `rtl_cases/strict_eval_comparison_trace_clean_34_by_method.csv`：trace clean 34 按方法统计。
- `rtl_cases/strict_eval_comparison_trace_clean_34_by_method.md`：trace clean 34 按方法说明。
- `rtl_cases/strict_eval_comparison_trace_clean_heldout.csv`：held-out 对比表。
- `rtl_cases/strict_eval_comparison_trace_clean_heldout.md`：held-out 对比说明。
- `rtl_cases/strict_eval_comparison_trace_clean_heldout_by_method.csv`：held-out 按方法对比。
- `rtl_cases/strict_eval_comparison_trace_clean_heldout_by_method.md`：held-out 按方法说明。
- `rtl_cases/strict_eval_report.csv`：strict eval 总报告。
- `rtl_cases/strict_eval_report_rerun.csv`：rerun 后 strict eval 报告。
- `rtl_cases/strict_eval_report_trace_clean_34.csv`：trace clean 34 报告。
- `rtl_cases/strict_eval_report_trace_clean_heldout.csv`：held-out 报告。
- `rtl_cases/sva_eval_report.csv`：SVA 评测汇总。
- `rtl_cases/weekly_report_20260524.docx`：周报 Word 版。
- `rtl_cases/weekly_report_20260524.md`：周报 Markdown 版。
- `rtl_cases/人工断言.xlsx`：人工断言表。
- `rtl_cases/四种方法的汇总对比.xlsx`：四方法对比表。
- `rtl_cases/实验结果.xlsx`：实验结果总表。

### 5.4 10 个 mini case 子目录

每个 `rtl_cases/caseXX_*` 目录都代表一个小型可控 bug benchmark。目录名已经直接表达 bug 主题：

- `case01_reset_omission`
- `case02_grant_delay`
- `case03_valid_ready_or_bug`
- `case04_fsm_transition`
- `case05_counter_boundary`
- `case06_priority_encoder`
- `case07_fifo_full_boundary`
- `case08_pulse_width`
- `case09_addr_increment`
- `case10_hold_valid_until_ready`

每个 mini case 目录中的文件模板作用一致：

- `buggy.v`：带 bug 的 RTL。
- `correct.v`：正确 RTL。
- `tb.v`：训练/已见轨迹的 testbench。
- `tb_holdout.v`：held-out 未见轨迹的 testbench。
- `waveform_good.csv`：正确 RTL 在已见激励下的逐周期波形。
- `waveform_bad.csv`：错误 RTL 在已见激励下的逐周期波形。
- `waveform_good_holdout.csv`：正确 RTL 的 held-out 波形。
- `waveform_bad_holdout.csv`：错误 RTL 的 held-out 波形。
- `waveform_*.vcd`：对应原始 VCD 波形。
- `sim_*`：局部仿真产物。

每个 case 下的 `experiment/` 子目录也遵循统一模板：

- `spec.txt`：该 case 的自然语言规范。
- `trace_good.txt`：正确轨迹的文本版。
- `trace_bad.txt`：错误轨迹的文本版。
- `trace_good_holdout.txt`：held-out 正确轨迹文本。
- `trace_bad_holdout.txt`：held-out 错误轨迹文本。
- `trace_summary.txt`：good/bad 差异摘要文本。
- `trace_summary.json`：差异摘要 JSON。
- `generated/`：实验生成出的候选或中间产物。
- `prompts/`：喂给模型的 prompt 资产。

## 6. `rtl_cases_real*` 真实 RTL 数据集目录

这些目录的差别主要在于“同一批真实 RTL case 处于不同整理阶段”，单个 case 内的文件模板基本一致。

### 6.1 公共单 case 文件模板

在 `rtl_cases_real/`、`rtl_cases_real_active/`、`rtl_cases_real_admitted_20260619/`、`rtl_cases_real_admitted_resume_20260619/`、`rtl_cases_real_iverilog_ready/` 中，单个 case 一般包含：

- `buggy.v`：注入 bug 的真实 RTL 版本。
- `correct.v`：正确 RTL 版本。
- `STIMULUS_NOTES.md`：该 case 的激励构造说明。
- `tb.v`：主测试激励。
- `tb_holdout.v`：held-out 激励。
- `waveform_good.csv` / `waveform_bad.csv`：已见轨迹波形。
- `waveform_good_holdout.csv` / `waveform_bad_holdout.csv`：held-out 波形。
- `waveform_*.vcd`：原始 VCD。
- `experiment/spec.txt`：该 case 的自然语言规范摘要。
- `experiment/trace_good.txt` / `trace_bad.txt`：文本轨迹。
- `experiment/trace_good_holdout.txt` / `trace_bad_holdout.txt`：held-out 文本轨迹。
- `experiment/trace_summary.txt` / `trace_summary.json`：差异摘要。
- `experiment/prompts/`：prompt 素材。
- `experiment/generated/`：生成结果或中间结果。

### 6.2 各目录角色

- `rtl_cases_real/README.md`：说明这是从真实 OpenTitan RTL 抽取出的 mutation scaffold，尚未全部 admitted。
- `rtl_cases_real/`：原始真实 RTL scaffold，偏“候选池/素材库”。
- `rtl_cases_real_active/`：当前启用的 active benchmark 根目录，包含更多修订后的 active case 与检查报告。
- `rtl_cases_real_admitted_20260619/`：2026-06-19 admitted 集，适合作为固定评测快照。
- `rtl_cases_real_admitted_resume_20260619/`：对 admitted 集进行 resume 续跑后的结果快照。
- `rtl_cases_real_iverilog_ready/`：先整理到 Icarus Verilog 可跑通的基础版本，偏早期可仿真快照。

### 6.3 各真实 RTL 根目录下的管理文件

公共类型文件：

- `case_manifest.json`：该数据集版本的 case 元数据与索引。
- `compile_probe.csv`：编译探测结果。
- `golden_sva_check_report.csv`：golden SVA 检查结果。
- `hardness_check_report*.csv`：难度检查结果。
- `trace_divergence_gate_report*.csv`：轨迹差异 gating 检查结果。
- `strict_eval_report*.csv`：strict eval 总表。
- `README.md`：该版本说明。
- `generate_resume*.log`：resume 续跑日志，仅在 resume 目录出现。

## 7. `outputs/` 生成产物目录

当前 `outputs/` 下可见约 4092 个文件，主要是脚本自动生成的文档、Excel、CSV、JSON、预览图和调试文件，不建议手工逐个维护。

### 7.1 根层生成文档/表格

这些文件通常是“对外汇报版”或“最终交付版”：

- `antecedent_not_triggered_cases.docx`
- `antecedent_repair_cases.xlsx`
- `antecedent_repair_prompts.docx`
- `antecedent_repair_results.xlsx`
- `golden_by_temporal_type.xlsx`
- `golden_natural_language_explanation.docx`
- `golden_selfcheck_full.xlsx`
- `high_vs_low_quality_trace_results.xlsx`
- `literal_hardcoding_examples.docx`
- `llm_vs_golden_gap_analysis.docx`
- `multi_model_observation.docx`
- `multi_model_small_eval.xlsx`
- `prompt_ablation_design.docx`
- `prompt_ablation_results.xlsx`
- `prompt_ablation_summary.docx`
- `raw_vs_summary.xlsx`
- `raw_vs_summary_case_notes.docx`
- `structural_overfit_examples.docx`
- `temporal_type_analysis.xlsx`
- `temporal_type_failure_examples.docx`
- `trace_abstraction_results.xlsx`
- `trace_abstraction_summary.docx`
- `trace_overfit_report.xlsx`
- `trace_quality_scored_table.xlsx`
- `trace_quality_score_definition.docx`
- `trace_tradeoff_by_bug_class.xlsx`
- `trace_tradeoff_by_case.docx`
- `trace_tradeoff_by_metric.xlsx`
- `trace_tradeoff_summary.docx`
- `vacuity_failure_table.xlsx`
- `vacuous_overfit_examples.docx`
- `主表_clean.xlsx`
- `候选去重统计.xlsx`
- `四象限_by_bug_class.xlsx`
- `四象限_by_case.xlsx`
- `四象限总结一页.docx`
- `四象限总表.xlsx`
- `新增20个hard_cases设计表.xlsx`
- `每个case一页说明.docx`
- `每个case代表性失败例子.docx`

配套文件规律：

- `*.inspect.ndjson`：Excel/文档的结构化检查输出。
- `*_preview.png`：预览图。

### 7.2 数据子目录职责

- `antecedent_repair_data/`：前件修复实验的原始结果、候选汇总、prompt 与 runtime。
- `golden_analysis_data/`：golden 自检、解释、差距分析中间表。
- `multi_model_eval_data/`：多模型评测原始结果、prompt、runtime 和按模型拆分数据。
- `new_hard_cases_data/`：新增 hard case 设计主表和分组摘要。
- `prompt_ablation_data/`：提示词消融原始结果与 prompt 设计表。
- `quadrant_analysis_data/`：四象限分析中间 CSV 和 JSON。
- `raw_vs_summary_data/`：raw trace 与 summary 对比分析数据。
- `temporal_type_analysis_data/`：temporal type 分析数据。
- `trace_abstraction_data/`：trace abstraction 原始结果、prompt、selected cases。
- `trace_overfit_data/`：trace overfit 分析明细。
- `trace_selection_data/`：trace quality 打分与高低质量轨迹对比数据。
- `trace_tradeoff_data/`：trace tradeoff 中间表。
- `vacuity_analysis_data/`：vacuity/前件零触发分析数据。
- `*_render/`：文档渲染输出目录。
- `_debug_*`：局部问题调试目录。
- `_refresh_runtime/`：运行时刷新缓存与临时产物。

## 8. `external/` 第三方代码

- `external/opentitan/`：OpenTitan 源码镜像，用于真实 RTL case 抽取和 mutation 基准来源。

这是外部项目快照，内部包含大量：

- Bazel 构建文件
- GitHub CI 配置
- 文档
- 硬件 RTL
- DV/formal 文件
- 供应商 IP

这部分不建议按 AssertionForge 自研文件的标准逐个整理，建议标为“第三方只读依赖”。

## 9. `node_modules/` Node 依赖

- `node_modules/`：Node.js 包缓存，供 `.mjs` 导出脚本或文档/表格处理链使用。

不建议逐文件整理，建议统一归类为“前端/导出运行时依赖”。

## 10. `.secrets/` 本地敏感文件

- `.secrets/anthropic_api_key.txt`：Anthropic API Key。
- `.secrets/openai_api_key.txt`：OpenAI API Key。
- `.secrets/qwen_api_key.txt`：Qwen API Key。

这些文件属于敏感信息，不应进入公开提交或共享归档。

## 11. 整理建议

- `src/`、`docs/`、`rtl_cases/` 顶层脚本和说明文档属于“核心可维护文件”，建议优先建索引。
- `rtl_cases_real*` 目录适合按“数据集阶段”管理，而不是逐个版本混放。
- `outputs/`、`node_modules/`、`__pycache__/` 适合视为“生成物/缓存”，不纳入手工维护主清单。
- `external/opentitan/` 应单独标注为“第三方镜像”，避免与自研代码混淆。
