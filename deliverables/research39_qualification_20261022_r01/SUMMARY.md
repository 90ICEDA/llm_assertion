# research39：结构化细化接口资格检查

2026-10-22，本轮继续第 2 项新 SVA 细化和第 3 项冻结后独立验收。

已完成 36/36 项检查。复用 `research17_model_schema.py` 的表达式树，以信号、运算符、操作数和时序关系表示模型提案；只做语法渲染，不插入正确表达式。当前接口仍由包装器处理时钟/复位，非法信号、嵌入时序箭头、错误槽位、错误参数数量均拒绝。接口失败后仍保留实际历史数值反馈，避免下一轮丢失已有证据。

实际原生诊断包含 same_sample、next_sample 两种时序关系：2 次编译、4 次执行（包含 2 次编译冒烟），形式化 0 次，模型调用 0 次。使用任意语法夹具验证传输和执行，这些夹具不是模型输出、不作为修复成功、不进入细化提示词或独立测试。

旧 research38 原始运行重新审计通过 167/167 项，产物位于 `deliverables/research39_legacy_regression_20261022_r01/`。旧拒绝结果不变。

新真实请求固定在 `deliverables/research39_prepare_20261022_r01/request.preview.json`。截至本资格检查报告，尚未提交新模型请求，不能宣称新版本通过。此前明确远程额度已耗尽，新的最多 2 次调用授权待用户答复。

接受标准保持：模型事件计划原有 13 个开发窗口已通过；新断言必须在对应 RTL 上通过 8 条目标漏报及历史门控，再完成 113 场景历史回放；接受后冻结，再生成并回放新的 56 场景、48 种不同激励独立测试。关键 unknown 不算通过；没有新接受版本时不生成独立验收结果。

```powershell
# 输出目录必须不存在；命令不调用模型。
wsl -- python3 scripts/research39_qualification.py --out deliverables/research39_qualification_NEW
wsl -- python3 scripts/research39_ast_refinement.py prepare --out deliverables/research39_prepare_NEW
```

真实调用仍使用已有 Highway/Qwen 72B 服务；远端只承诺 JSON 对象输出，不宣称服务强制执行递归 schema。严格 AST 校验在本地进行，语法合格仍可能原生编译失败或产生语义错误。
