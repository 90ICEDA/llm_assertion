"""Produce evidence-linked native SVA report from saved executions."""
import hashlib
import json
from pathlib import Path
import research_native_runner as native

ROOT, OUT = native.ROOT, native.OUT


def main():
    package=next((OUT/'tools').glob('verilator*.deb'))
    manifest=dict(package=package.name,sha256=hashlib.sha256(package.read_bytes()).hexdigest(),
        source='Ubuntu noble universe apt package verilator 5.020-1 amd64',
        installation_scope='unpacked only under experiment tools/unpack; no system install',
        reproduce=['cd deliverables/research_native_20261014_r01/tools',
                   'apt-get download verilator=5.020-1','dpkg-deb -x verilator_5.020-1_amd64.deb unpack'])
    native.dump(OUT/'tools/provenance.json',manifest)
    probes=json.loads((OUT/'probes_r02/result.json').read_text())
    lines=['# 原生 SVA 与真实模型闭环实验', '',
        '本目录只报告实际保存的运行。原生工具为本地解包的 Verilator 5.020；有支持子集，不是完整 SVA 工具，更不是形式证明。', '',
        '## 工具资格检查', '',
        '| 探针 | 编译 | 支持状态 | 性质结果 |', '|---|---|---|---|']
    for k,r in probes.items():lines.append(f'| {k} | {r["compile_status"]} | {r["tool_support_status"]} | {r["property_status"]} |')
    lines += ['', '原始 `probes/` 的失败是解包工具二进制定位错误，全部保留；修正后结果见 `probes_r02/`。`##2` 是工具明确报告的不支持构造。断言由 Verilator 原生编译执行；没有转成过程 checker。`TRIGGER` 是前件表达式的过程诊断计数，不能冒充原生 cover 或形式非空证明。', '',
        '## FIFO 资格与范围', '',
        '`engineering_qa/` 是明确标注的工程控制，不是 LLM 输出；实际运行真实 axis_fifo RTL，外接 corrupt/duplicate_payload/drop 人工故障。辅助参考队列只维护状态，判定由原生 assert property 执行；Python 端口事务 oracle 独立给出义务标签。该预检早期 evaluation 中 detections 是同周期症状命中，不能解读为独立因果发现，真实模型闭环采用更严格的首违例对齐口径。', '']
    summary_path=OUT/'summary.json'
    if summary_path.exists():
        r=json.loads(summary_path.read_text())
        concise={k:r[k] for k in ('status','initial','final_development','independent_test','model_cost','native_cost','duplicate_properties','adjudication_notes')}
        lines += ['## 真实模型闭环', '',f'状态：`{r["status"]}`。请求/响应在 `closed_loop/model_calls/` 与 `compact_continuation/model_call/`，每版 SVA、原生编译执行日志和 VCD 均保留。', '',
            '第一版真实模型错误地要求 `mdata[0] == $past(mdata[0])`，合法不同事务数据发生变化即报警。第一次细化因上下文超限取消；额外预算的紧凑反馈请求返回三条相同错误性质，没有添加互补保护。该提案被拒绝，冻结后仅作独立诊断测试，不能报告为最终被接受断言通过独立测试。', '',
            '合法前缀误报、未检出义务采样和因果未知是不同指标。采样计数不是独立缺口数量；去重后的缺口按 fault family / obligation 显示。原始 `evaluation.json` 曾把违例之后无法归因的报警归为 FP；`readjudication.json` 与根 summary 修正该报告口径，不改模型反馈、实际决策或冻结版本。', '',
            '```json',json.dumps(concise,ensure_ascii=False,indent=2),'```','']
    else:lines += ['真实模型闭环仍未产生 summary.json；不得依据代码存在宣称完成。','']
    lines += ['## 可复现入口', '', '在仓库根目录使用 WSL：', '', '```powershell',
        'wsl.exe python3 /mnt/d/AssertionForge-main1/scripts/research_native_runner.py probe --out /mnt/d/AssertionForge-main1/deliverables/research_native_20261014_r01/probes_reproduction',
        'wsl.exe python3 /mnt/d/AssertionForge-main1/scripts/research_native_closed_loop.py --out /mnt/d/AssertionForge-main1/deliverables/research_native_20261014_r01/closed_loop_reproduction',
        'wsl.exe python3 /mnt/d/AssertionForge-main1/scripts/research_native_audit.py',
        '```', '',
        '输出目录必须尚不存在，避免覆盖历史。模型服务需预先启动。可传 `--model --endpoint --provider --key-env --seed --temperature --max-tokens`。本次验证仅使用本地 Ollama；OpenAI-compatible 和其他 endpoint 适配仅实现，未实跑，不计已验证。', '',
        '## 尚未完成与限制', '',
        '- 未进行原生形式化；仿真无违例只适用于已执行范围。',
        '- 原生四组机制消融尚未完成；本次单链不能代替统一预算的四组比较。',
        '- boundary 故障是人工注入；不是原始 FIFO presented 缺陷的历史修复复现。',
        '- 触发诊断不能保证完整时序前件语义或全局非空触发；防退化只对已回放证据成立。',
        '- 独立测试只检验冻结版本、新随机场景和新参数；未根据测试结果修改 SVA。',
        '- 模型自身报告的 obligation 映射还须由独立 oracle 与原生首违例匹配；其他症状命中保留 attribution_unknown。', '']
    (OUT/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__=='__main__':main()
