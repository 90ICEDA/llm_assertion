# Research28：两类 valid 保持缺口已完成自动修复与独立回放

本轮只执行 1 次获授权的真实 Highway/Qwen 72B 请求。模型修改 a4，原生历史门控接受；其他四条性质（含 research27 复位保护）保留。未使用第二次额度。

| 项目 | 修改前 | 修改后 |
|---|---:|---:|
| 开发场景数 | 131 | 131 |
| 开发确认违例检出 | 250 | 258 |
| 开发漏报 | 8 | 0 |
| 开发有效触发义务记录 | 20298 | 20298 |
| 新独立场景数 | 26 | 26 |
| 独立确认违例检出 | 44 | 52 |
| 独立漏报 | 8 | 0 |
| 独立持续背压 valid 撤销检出 | 0/4 | 4/4 |
| 独立解除边界 valid 撤销检出 | 0/4 | 4/4 |

开发及独立误报、当前归因 unknown 均为 0。计数是义务—采样记录，不是独立 Bug 数。两类机制的深度/复位/随机数据变体只算重复验证。

原始 a4：
```systemverilog
(mvalid && !mready) |=> mdata == $past(mdata)
```
模型修改后的 a4：
```systemverilog
(mvalid && !mready) |=> mvalid && mdata == $past(mdata)
```

该非重叠蕴含在背压后的下一拍同时检查 valid 和数据，包括 ready 恢复的那一拍。运行器提供 posedge 时钟、reset disable、assert 及真实前件 cover；模型未修改其他四条性质。

开发案例一：Depth 2 周期 12→13，ready 0→0、valid 1→0、数据 3509692673 不变。原集合已触发但漏报，新集合原生检出。
开发案例二：Depth 2 周期 13→14，ready 0→1、valid 1→0、数据 2427132938 不变。原集合漏报，新集合原生检出。实际接受事务和正确 FIFO 对照保存在主报告 results.json 的 examples。

冻结哈希 `2607e416ed0bf4a96b55af757352c2ec63e1d4131fea5235dfbbef300efb67c8`；冻结后才生成 seed 523922415 的 26 场景（Depth 4/8、Pipeline 2），未参与模型反馈或选择。105 历史开发输入和 18 个已公开测试的原样转开发均已核验。

模型输入 13368、输出 151 tokens。主闭环 12 次原生编译、640 次执行（含 12 次 smoke）。计入两次资格实验，合计 16 次编译、676 次执行（含 16 次 smoke）；无形式化调用，金额不可用。

主闭环原始产物 8767 文件哈希核验通过；模型原始响应、组装结果、提示采样来源、冻结哈希及测试隔离全部通过核验。

1479 条开发后续归因 unknown、318 条独立后续归因 unknown 继续保留。独立排空义务没有目标和触发，不能声称五项义务全部保护。实际 RTL 加人工边界故障不是上游历史修复复现；有限回放不等于全局证明。

实际执行命令（已运行；原目录禁止覆盖。重跑须新目录及绑定新目录的有效授权记录）：
```powershell
wsl -- python3 scripts/research28_campaign.py run --out deliverables/research28_valid_closed_loop_20261020_r01 --max-model-calls 2 --authorization-record deliverables/research28_valid_status_20261020_r01/authorization.json
```

只读报告核验命令：
```powershell
wsl -- python3 scripts/research28_report.py --run deliverables/research28_valid_closed_loop_20261020_r01
```

主报告：`../research28_valid_closed_loop_20261020_r01/report/SUMMARY.md`。模型流式原文、命令、波形、接受决策、冻结候选及独立测试均在该运行目录。
r01 资格实验的目录布局错误和零模型调用记录保留，没有把失败试验排除出实际成本。
