# research77 实际判断与失败轨迹

本轮按授权完成1次真实 Highway/Qwen 72B 判断，未通过完整一致性检查，按封存协议停止；无重试、无SVA生成。归档的模型响应没有被人工修改。

| 检查 | 实际结果 |
| --- | --- |
| 起始周期触发 | 正确：anchor 上 rst=0、mvalid=1、mready=0 |
| 检查周期保持 | 正确：check 上 mvalid=1，mdata 保持为 anchor.mdata |
| 复位取消 | 错误：模型返回 check.rst=0，应为有效复位 rst=1 才取消 |
| 窗口判断与独立证书 | 9/11；w0、w2 错误 |
| 执行统一规则与独立证书 | 2/11 |
| 执行统一规则与模型窗口标注 | 2/11 |

模型把复位未生效作为取消条件，按其规则执行时，8个正常待保持窗口被取消，真正复位的w10反而没有取消。w7、w8没有待保持输出，因此规则计算恰好与正确判断一致。上述分母是开发窗口，不是独立Bug。

w0：起始数据3883009061，检查数据3883009060；模型再次把期望值写成检查数据并判为satisfied。

w2：起始数据267114574，检查数据267114575；模型同样把变化后的数据当成期望值并判为satisfied。

w5：模型窗口能识别valid撤销，但其全局复位规则会取消该检查。程序实际执行模型规则后暴露了这个矛盾，而不是只检查文字中是否出现正确采样名称。

这证明新一致性门控实际拒绝了互相矛盾的输出，但不证明模型完成修复，也不属于契约搜索或历史防退化机制的受控增量收益。与research76相比，触发/保持的规则位置已正确，但窗口判断由11/11退至9/11；不能仅根据规则字段改善宣称整体进展成功。

未执行原生SVA目标、105历史或新独立测试。终态保留哈希 `0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1` 是旧部分保护基线，不是本轮接受的新版本。旧失败及旧独立结果没有被覆盖。

实际成本：1次模型调用，输入11814、输出1069 tokens；原生编译0、执行0、形式化0。金额不可用。准备阶段30份原生日志复核不计为新执行。

剩余1次仅限完整判断通过后的SVA，未使用。下一轮应使用本次真实诊断核验复位有效电平及两处跨周期数据变化；不得人工改写结果或拼接research76/77的正确片段，完整计划仍须一次性通过。追加判断调用需重新确定用途和额度。

## 已执行命令与只读复核

```powershell
wsl -- python3 scripts/research77_rule_consistency.py run --prepared deliverables/research77_prepare_20261024_r01 --authorization deliverables/research77_prepare_20261024_r01/authorization.json --out deliverables/research77_real_20261024_r01
```

上行为执行归档，不可重复消耗已用额度。可执行下列只读审计，输出目录须不存在：

```powershell
wsl -- python3 scripts/research77_result_audit.py --prepared deliverables/research77_prepare_20261024_r01 --run deliverables/research77_real_20261024_r01 --out deliverables/research77_audit_recheck
```

原始回答与流：`../research77_real_20261024_r01/plan/v0/model_call/`。
逐窗口规则执行：`../research77_real_20261024_r01/plan/v0/decision.json`。
本地审计：`audit.json`；具体诊断：`diagnosis.json`；实际成本：`cost.json`。
