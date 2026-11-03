# research46：独立周期门控准备记录

用户已明确授权将research45剩余额度中的最多4次转用于本轮，授权记录见authorization.json。实际运行目录为 `../research46_real_20261022_r01/`，结果以其中outcome.json及终态报告为准；以下本地检查不代替真实模型验收。

实际终态：两次真实周期判断均因w5的check拍reset事件字段错误而拒绝，适用性标签均11/11正确。SVA和独立测试未启动。详见 `../research46_report_20261022_r01/CASE_TRACE.md`；剩余2次仅限通过周期门控后的SVA阶段，未转作追加周期判断。

复用research34的原生记录证书、research36的事件/适用性验证器、research44的原样AST接口及research45的原生反馈与历史回放。本轮没有重建一套时序规格，也不复用旧成功的模型计划或SVA作为新输出。

开发数据全部来自已执行记录：长背压期间与解除边界的两个valid违例、配对fixed样本、research45误报的14→15拍合法事务切换，以及空闲、已接受输出、持续背压、ready上升、复位取消和复位释放。按原始窗口去重后共11个窗口。顺序固定打乱；第一阶段只提供前一拍的rst/valid/ready和检查拍cycle/rst，不提供本地期望标签、当前valid或待评估SVA。

模型必须逐项返回pending、reset、anchor_cycle、check_cycle、applicability。每项布尔值、周期及标签均由现有独立端口队列/复位检查重新核验，missing/unknown/错误均不通过。代码里的verified_sva_request会拒绝未通过或失效的模型计划，不只靠提示词要求模型先判断。

计划通过后才发送SVA请求，并且只附加实际通过的模型计划。生成性质须在对应RTL上执行；新增native_window_gate将每个required窗口映射到性质的实际前件周期并核查原生cover。还须通过当前目标因果检出、105场景历史保护，才冻结并生成新的56场景独立测试。

本地31项检查通过，包括错误事件、错误周期、缺失/重复/unknown、错误布尔类型，以及未通过计划不能创建SVA请求。使用research45实际失败性质的原生记录，新窗口门控检出4个必需窗口不触发及1个合法窗口误报。这是本地验证器测试和真实记录复核，不是新模型成功；新模型调用0，新增原生执行0。

## 封存产物

- plan_request.preview.json：第一阶段真实请求预览。
- sva_request.template.json：第二阶段请求基底；尚无通过的模型计划，不能直接作为已通过后的请求发送。
- windows.public.json / expected.private.json：公开采样与仅本地证书表。
- known_failed_property_window_gate.json：旧失败性质在新窗口门控下的真实记录诊断。
- protocol.json / prepared_hashes.json / source_snapshot：调用预算、阶段条件、来源与代码绑定。

拟转用research45未使用8次中的最多4次：周期判断最多2次，全部通过后SVA最多2次，无传输重试。原8次只授权用于先导通过后的消融，因此转用需要用户明确授权；其余4次维持原限制。

```powershell
# 授权后实际运行；使用绑定的授权文件，不得重复旧调用。
wsl -- python3 scripts/research46_cycle_gate.py run --prepared deliverables/research46_prepare_20261022_r01 --out deliverables/research46_real_20261022_r01 --authorization deliverables/research46_prepare_20261022_r01/authorization.json
# 终态后的只读审计。
wsl -- python3 scripts/research46_report.py --run deliverables/research46_real_20261022_r01 --out deliverables/research46_report_NEW
```
