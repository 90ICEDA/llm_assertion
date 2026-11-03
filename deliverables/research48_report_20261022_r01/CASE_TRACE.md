# research48：计划正确后，性质仍未通过接受检查

research47实际模型计划在11个开发窗口上通过，但本轮SVA没有通过。三次真实请求中，两次产生可执行性质，一次HTTP400没有候选；失败调用用量不可用。

## 原性质与两次实际提案

原a4：
```sv
(mvalid && !mready) |=> mdata == $past(mdata)
```

v0实际模型性质：
```sv
((mvalid && (!(mready)) && $past(mvalid) && (!(rst)))) |-> ((mdata == $past(mdata)))
```
当前证据：{"rows": 2150, "unknown": 2, "triggers": 635, "false_positives": 16, "detections": 3, "misses": 0, "count_unit": "obligation-by-sampled-cycle evidence rows, not independent discoveries or transactions", "later_attribution_unknown": 95}
历史拒绝：{"unconfirmed_replay": 61, "new_legal_false_positive": 918, "lost_target_detection": 75, "lost_obligation_trigger": 1092}

实际目标cycle 23：
```json
[
  {
    "cycle": 22,
    "rst": 0,
    "mvalid": 1,
    "mready": 0,
    "mdata": 1102837798
  },
  {
    "cycle": 23,
    "rst": 0,
    "mvalid": 0,
    "mready": 0,
    "mdata": 1102837798
  }
]
```

实际目标cycle 31：
```json
[
  {
    "cycle": 30,
    "rst": 0,
    "mvalid": 1,
    "mready": 0,
    "mdata": 1102837798
  },
  {
    "cycle": 31,
    "rst": 0,
    "mvalid": 0,
    "mready": 1,
    "mdata": 1102837798
  }
]
```

v2实际模型性质：
```sv
((mvalid && (!(mready)) && $past((mvalid && (!(mready)))))) |-> ((mdata == $past(mdata)))
```
当前证据：{"rows": 2150, "unknown": 0, "triggers": 619, "false_positives": 0, "detections": 3, "misses": 2, "count_unit": "obligation-by-sampled-cycle evidence rows, not independent discoveries or transactions", "later_attribution_unknown": 95}
历史拒绝：{"lost_target_detection": 31, "lost_obligation_trigger": 1048}

实际目标cycle 23：
```json
[
  {
    "cycle": 22,
    "rst": 0,
    "mvalid": 1,
    "mready": 0,
    "mdata": 1102837798
  },
  {
    "cycle": 23,
    "rst": 0,
    "mvalid": 0,
    "mready": 0,
    "mdata": 1102837798
  }
]
```

实际目标cycle 31：
```json
[
  {
    "cycle": 30,
    "rst": 0,
    "mvalid": 1,
    "mready": 0,
    "mdata": 1102837798
  },
  {
    "cycle": 31,
    "rst": 0,
    "mvalid": 0,
    "mready": 1,
    "mdata": 1102837798
  }
]
```

## 原生执行说明

v0继续在当前拍要求mvalid成立，并比较mdata与过去一拍；已接受输出切换新事务时出现误报，valid提前撤销时不能形成目标因果检出。当前16误报、2关键unknown，不能把misses=0写成补上漏报。
v2新增过去一拍也背压的条件。当前误报降为0、unknown降为0，但两个原始目标仍漏报；native_target_gate记录这两个故障目标的a4均未触发。解除背压边界的合法配对也未触发。11个已通过模型适用性窗口中仍有4个必需窗口未被性质覆盖。
v2在105场景历史中丢失31条原有检出和1048条触发证据，故防退化拒绝。该结论来自同一开发/历史证据回放，不是四组消融的机制收益估计。

## 保留状态和具体限制

最后保留原初始断言哈希0403e89b8e64798cd758cbb4df8d2def7ccd8a79920b973080927c217873a5b1。没有新接受版本，也没有新独立测试。research46/47结果和旧冻结版本不变。
每个提案的当前后续归因unknown95、历史后续归因unknown1177均保留；它们不是通过数。各义务分项见parent_result.json，完整映射在运行目录core/v*/obligation_mapping.json。
第二次HTTP400的具体服务端原因不可用，不能确定为上下文长度、接口语法或其他原因。该调用不会冒充原生失败或已知零成本。
事后发现无候选服务错误覆盖了最近详细原生诊断。未来版本已增加显式保留最近原生反馈的逻辑；本次原请求和结果不追改，新逻辑仅做本地记录验证，未追加真实调用。

## 实际运行命令

以下是已执行记录，目录不可覆盖，旧授权不可重复消耗；实际源码在运行目录source_snapshot中。
```powershell
wsl -- python3 scripts/research48_sva_campaign.py run --prepared deliverables/research48_prepare_20261022_r02 --out deliverables/research48_real_20261022_r01 --authorization deliverables/research48_authorization_20261022_r01.json
```

后续需要重新准备采用保留原生反馈逻辑的请求，并明确新的SVA额度。本轮3次已耗尽，不能用原条件性消融额度继续。
