# REGuard 研究更新：research192–199

本目录发布算法代码对应的精选实验结果，截至 2026-11-04。**这是历史实验结果的发布整理，不是本次 GitHub 更新重新执行的实验。** 完整原始归档没有全部纳入 Git。

## 代码入口

所有入口位于仓库 [scripts](../../scripts/) 中，沿用既有框架，没有替换主系统。

| 功能 | 入口 |
| --- | --- |
| 主动证据语义与搜索 | [research194_active_semantics.py](../../scripts/research194_active_semantics.py)、[research196_active_search.py](../../scripts/research196_active_search.py) |
| 定位、局部编辑和历史保护 | [research194_refinement.py](../../scripts/research194_refinement.py)、[research196_component_guard.py](../../scripts/research196_component_guard.py) |
| 窗口、延迟、事务匹配操作 | [research197_refinement.py](../../scripts/research197_refinement.py) |
| 自动局部优先与组合权限 | [research198_refinement.py](../../scripts/research198_refinement.py)、[research198_active_obligation_fix.py](../../scripts/research198_active_obligation_fix.py) |
| 最新路由×操作契约隔离 | [research199_refinement.py](../../scripts/research199_refinement.py) |
| 历史修复与多在途适配器 | [research197_cases.py](../../scripts/research197_cases.py) |

research199 将路由和操作契约分开切换：B0=旧路由+通用字段，B1=局部优先+通用字段，B2=旧路由+专用操作，B3=局部优先+专用操作。B 组固定相同开发证据。在线 A0/A1 使用基础反馈，A2/A3 使用新局部细化；A0/A2 使用 S0，A1/A3 使用 S3，候选更新后重新获取证据。各组不能与历史 R0–R3 或 S0–S3 的版本混称。

## 交付索引

| 内容 | 文件 | 实验范围 |
| --- | --- | --- |
| 完整 S0–S3、R0–R3、历史 A0–A3 表 | [tables.json](research197/tables.json) | research197，三个父案例、两个种子 |
| 搜索成本曲线与逐项分析 | [曲线](research197/search_cost_curves.png)、[分析](research197/search_analysis.json) | research197，不能称为 research199 新搜索曲线 |
| 最新因果隔离与在线组合表 | [paired.json](research199/paired.json)、[交互项](research199/interactions.json) | research199，48 条轨迹 |
| 成本截面 | [costs.json](research199/costs.json) | 完整轮次检查点，不是严格等实际耗时重跑 |
| 修改分类和回退 | [attempts.json](research199/attempts.json)、[fallback_paths.json](research199/fallback_paths.json) | 未尝试、接口失败、退化、空触发与无改善分开 |
| 跨故障独立验收 | [acceptance.json](research199/acceptance.json) | 102 条版本×故障记录，三个父案例 |
| 正反案例与证据链 | [案例卡](research199/cards.html)、[案例数据](research199/cards.json)、[链条](research199/linkage.json) | 12 张案例卡；关联不等于单条证据的因果效应 |
| 故障增强探索 | [摘要](research194/fault_augmentation.json) | 保留正负结果，未证明稳定第三创新 |

## 最新结果与结论边界

research199 使用 deepseek/deepseek-v3-0324，实际调用 139 次，累计 5,060,846 tokens，48 条轨迹。以下为最终完整轮次下的父案例平均值，成本匹配结果应另外查看 costs.json。

| 组别 | 父案例平均事务检出率 | 必要义务保护率 | 平均合法误报记录 |
| --- | ---: | ---: | ---: |
| B0 | 43.33% | 19.44% | 7.33 |
| B1 | 16.67% | 11.11% | 15.33 |
| B2 | 16.67% | 11.11% | 8.00 |
| B3 | 35.00% | 30.56% | 0.00 |
| A0 | 34.17% | 20.83% | 4.00 |
| A1 | 38.33% | 26.39% | 7.67 |
| A2 | 30.00% | 26.39% | 4.00 |
| A3 | 25.00% | 22.22% | 8.00 |

B3 在必要义务保护和误报方面有收益，但最终事务检出率未超过 B0。在线 A3 没有总体优势：事务检出率交互项约 −9.17 个百分点，必要义务保护率交互项约 −9.72 个百分点。不能把研究任务完成写成算法总体优越。

独立验收全部 102 条记录均为已知结果、查询已曝光；15 条完整通过属于不同版本，不能算 15 个独立 Bug。新窗口载荷故障和 ID Queue 空状态故障均未被检出，Counter 新故障仅部分版本检出。10 条在线新证据关联改善链覆盖两个父案例、三个义务类型；没有做逐条证据反事实实验。

真实模型中接受 17 次局部修改、2 次重新生成、8 次自由修改；组合接受为 0。观察到 5 条“局部部分改善→结构证书→组合→再生成”路径，纯局部直接拒绝后的完整三阶段链仍未观察到。没有为制造成功修改测试集。

历史源包括 common_cells PR #190 与 #242，修复前后 RTL 和公开提交信息在 deliverables/research197_history_sources_20261104_r01 与 deliverables/research195_history_sources_20261103_r01。ID Queue 使用真实上游 RTL，但故障是人工注入。完整 Ibex 异常流水线、同 ID 复用、一般无限窗口均不在验证范围。

## 离线检查与复现范围

从仓库根目录运行：

```bash
python -B scripts/check_reguard_release.py
```

该命令校验本次发布清单、加载已有的无外部归档依赖回归测试；不调用模型，不运行 RTL 仿真，不把构造测试当作原生实验结果。完整 unittest discover 会包含依赖未发布归档的历史测试，不能作为本裁剪仓库的默认检查。

原生 RTL 实验需要 Linux/WSL、对应 Verilator/Icarus 工具及新输出目录。scripts 中 prepare/execute/resume/recover/finish/audit 等历史入口保留归档路径和封存校验，不能直接当作一键复现实验命令；使用前需准备其所需归档、调整本机路径并自行配置服务。过去的个人调用授权没有发布，也不对新使用者生效。本次未调用远程模型、未重新仿真。

JSON 中 archive:// 与 deliverables/ 路径标识原始证据位置；本包仅保证本页的相对链接有效，不宣称包含所有被引用的原始波形。导出时只替换本机根路径，数值、候选、判定和内容哈希保持原值。来源和发布文件哈希见 [manifest.json](manifest.json)。

research199 原生验收曾因磁盘耗尽中断，后续使用同一冻结版本恢复；一个损坏的 acquisition 聚合记录由原始逐查询记录恢复，未重跑模型。中断阶段无法完整计量的成本保持未知，未记为零。完整恢复审计仍在原始归档中，发布摘要不是其替代品。

源码中旧的机器路径是历史约定；本更新保留仓库已有的相对路径配置和脱敏文件。根目录 COPY_MANIFEST.sha256、LOCAL_COPY_REPORT.md 描述上一版整理，本次增量以本目录清单为准。
