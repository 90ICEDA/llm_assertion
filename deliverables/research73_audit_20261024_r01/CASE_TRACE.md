# 回顾性真实提案：普通接受与历史拒绝

候选来自既有真实模型原始响应，本次原样重新执行。不是新随机化实验；恢复对照不进入新的细化请求。

## c04：deliverables/research36_real_20261022_r01/core/v1/model_call/candidate.json

```systemverilog
a0: mvalid && mready && ref_count > 0 |-> mdata == ref_expected
a1: drain_due && ref_count > 0 |-> $past(mvalid && mready && ref_count > 0) && mdata == ref_expected
a2: mvalid && !mready && $past(mvalid && !mready) |-> mdata == $past(mdata)
a3: mready && mvalid |-> (ref_count > 0 && mdata == ref_expected)
a4: (svalid && !mready && mvalid) |=> (mvalid && (mdata == ref_expected))
```
普通范围固定为14个公共场景；完整历史为105场景。普通通过后增加历史检查才拒绝，旧规则没有放宽。

{'index': 4, 'source': 'deliverables/research36_real_20261022_r01/core/v1/model_call/candidate.json', 'ordinary_pass': True, 'public': {'rows': 13838, 'unknown': 0, 'triggers': 5298, 'false_positives': 0, 'detections': 3, 'misses': 0, 'count_unit': 'obligation-by-sampled-cycle evidence rows, not independent discoveries or transactions', 'later_attribution_unknown': 151}, 'historical': {'rows': 69124, 'unknown': 22, 'triggers': 16113, 'false_positives': 46, 'detections': 161, 'misses': 31, 'count_unit': 'obligation-by-sampled-cycle evidence rows, not independent discoveries or transactions', 'later_attribution_unknown': 1177}, 'regressions': {'confirmed_lost_detection': 31, 'unconfirmed_detection_loss': 22, 'new_legal_false_positive': 46, 'lost_required_trigger': 356}, 'extra_rejection': True}

基线原生历史214个目标检出，误报/漏报/关键unknown为0；拒绝后active版本哈希与基线相同。仍有1177条后续归因unknown，范围不扩大。

代表证据 confirmed_lost_detection：fifo:021c02ca56951d576ef03f8181100d055a18cf6a35a58cdf830526ee970758ef；义务 stall_stability；故障机制 stall_glitch。
采样周期 8；原始回放路径 /mnt/d/AssertionForge-main1/deliverables/research73_discriminating_20261024_r01/c04/history/case_86/stall_glitch。

代表证据 new_legal_false_positive：fifo:091c49612f95b16dc1e5686bb5426b54e1b7833d332f44f1a6e59e30dda0d680；义务 stall_stability；故障机制 drop。
采样周期 22；原始回放路径 /mnt/d/AssertionForge-main1/deliverables/research73_discriminating_20261024_r01/c04/history/case_65/drop。

## 归档恢复对照

对所有普通和历史检查均通过的归档提案做配对回放比对；没有从独立结果选择恢复版本。

c04 → c01：确认漏报恢复31/31，合法误报消除46。来源 deliverables/research32_real_20261021_r01/s3209/core/v0/model_call/candidate.json。

c04 → c05：确认漏报恢复31/31，合法误报消除46。来源 deliverables/research41_real_20261022_r01/s4103/core/v0/model_call/candidate.json。

c04 → c06：确认漏报恢复31/31，合法误报消除46。来源 deliverables/research41_real_20261022_r01/s4133/core/v1/model_call/candidate.json。

这些结果只证明已有真实模型性质能够在相同开发记录上恢复保护，未证明本次拒绝反馈会促成修复。新的有界真实继续细化尚待执行；旧成功性质不得送入请求。
