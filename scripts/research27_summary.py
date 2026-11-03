"""Summarize the terminal reset repair from recorded native/model artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import research17_model as base
from research15_acceptance import inspect


def metrics(group):
    info=inspect(group['ledger'])
    return {o: {field:sum(info['rows'][k]['obligation']==o for k in info[field])
                for field in ('detections','misses','unknown','false_positives','triggers')}
            for o in base.SPECS}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();run=args.run.resolve();out=args.out.resolve()
    assert base.ROOT in run.parents and base.ROOT in out.parents
    outcome=base.read(run/'outcome.json')
    assert outcome['status']!='running'
    report=base.read(run/'report/results.json')
    old=base.read(run/'shared_initial.json')
    new=base.read(run/'core/frozen_candidate.json')
    history=base.read(run/'core/history.json')
    accepted=[h for h in history if h['decision']['accepted']]
    chosen=run/'core'/f"v{accepted[-1]['iteration']}"/'native' if accepted else run/'core/before'
    before=base.read(run/'core/before/result.json')
    after=base.read(chosen/'result.json')
    groups=dict(development_before=before['group'],development_after=after['group'])
    for label in ('initial','core'):
        groups['independent_'+label]=base.read(run/f'core_independent/{label}/independent_ledger.json')
    data=dict(run=str(run),status=outcome['status'],new_accepted_edits=len(accepted),
        model=report['protocol']['config']['model'],
        backend=report['protocol']['config'].get('backend'),
        old_candidate=old,new_candidate=new,freeze=base.read(run/'core/freeze.json'),
        metrics={name:metrics(g) for name,g in groups.items()},
        counts=dict(before=before['counts'],after=after['counts']),
        independent_counts=base.read(run/'core_independent/summary.json'),
        history=[dict(iteration=h['iteration'],decision=h['decision'],call=h['call']) for h in history],
        cost=report['cost']['total'],
        monetary_cost=None,
        monetary_cost_status='unavailable; provider token usage is recorded, billing amounts were not returned',
        scope='One axis_fifo parent with explicit artificial boundary mutations. Finite simulation and historical replay only; no formal proof or global non-regression.',
        whole_parent_pass=False,formal_calls=0)
    request=base.read(run/'core/v0/model_call/request.json')
    task=json.loads(request['messages'][1]['content'])['fresh_obligation_synthesis']
    final_rows=inspect(after['group']['ledger'])['rows']
    data['development_examples']=[dict(observation=p,after=final_rows[p['event']['evidence_id']])
                                  for p in task['observations']]
    data['old_a3']=next(a['property'] for a in old['assertions'] if a['id']=='a3')
    data['new_a3']=next(a['property'] for a in new['assertions'] if a['id']=='a3')
    data['other_properties_unchanged']=all(a==b for a,b in zip(old['assertions'],new['assertions']) if a['id']!='a3')
    out.mkdir(parents=True,exist_ok=True)
    base.dump(out/'RESULTS.json',data)
    lines=['# 复位后无请求输出保护：本轮结果','',
        f"真实模型 `{data['model']}`（`{data['backend']}`）细化接受次数：{len(accepted)}；运行状态：`{outcome['status']}`。",
        f"其余四条断言原文保留：{data['other_properties_unchanged']}。", '',
        '旧 a3：','```systemverilog',data['old_a3'],'```','',
        '最终 a3：','```systemverilog',data['new_a3'],'```','',
        '| 数据 | 义务 | 检出 | 漏报 | unknown | 误报 | 触发行 |',
        '|---|---|---:|---:|---:|---:|---:|']
    for name,obligations in data['metrics'].items():
        for obligation in ('no_unsolicited_output','reset_cancellation'):
            row=obligations[obligation]
            lines.append(f"| {name} | {obligation} | "+' | '.join(str(row[k]) for k in ('detections','misses','unknown','false_positives','triggers'))+' |')
    lines+=['','上述分母为“义务—采样行”，同一事务可能同时违反两项义务，不是两个独立 Bug。',
        '105 个开发场景包含 90 个已公开旧测试；新独立测试在最终冻结后生成。','',
        f"另保留开发集 {after['counts']['later_attribution_unknown']} 条、独立集 "
        f"{data['independent_counts']['core']['counts']['later_attribution_unknown']} 条后续违例归因 unknown；没有计为通过或已确认检出。",'',
        '## 开发证据轨迹','',
        'ref_count 为 0 时 ref_expected 没有有效队首语义；此时应由事务不存在性拒绝输出，不以该残留数值作为合法性的依据。','']
    for example in data['development_examples']:
        p=example['observation'];s=p['faulty_samples'][-1];row=example['after']
        lines+=[f"- `{p['scenario']}`，cycle {s['cycle']}，ref_count={s['ref_count']}，"
                f"mvalid={s['mvalid']}，mready={s['mready']}，mdata={s['mdata']}，ref_expected={s['ref_expected']}。"
                f"修改前：{p['event']['gap_observation']}，归因 {p['event']['attribution']}；"
                f"修改后：归因 {row['native']['attribution_status']}，"
                f"原生断言记录 `{json.dumps(row['native']['assertions'])}`。"]
    lines+=['','## 产物与限制','',
        f"- [完整原生日志、修改及独立回放报告](../{run.name}/report/REPORT.md)",
        f"- [实际执行命令](../{run.name}/execution.command.json)",
        f"- [冻结 SVA](../{run.name}/core/frozen_candidate.sva)",
        "- [全部失败尝试与本轮总成本](../research27_reset_campaign_20261020_r01/SUMMARY.md)",
        '- [机器可读结果](RESULTS.json)','',
        '本轮只验收有限样本中的复位相关保护。完整五义务、valid 背压保持、原始历史缺陷闭环仍不能据此宣称完成。'
        '仿真通过不等于形式化证明；历史回放通过不等于全局无退化。',
        '', '实际成本：`'+json.dumps(data['cost'])+'`。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    shutil.copy2(__file__,out/'summary_script.py')
    base.dump(out/'source_hashes.json',{str(p.relative_to(run)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (run/'report/results.json',run/'core/freeze.json',run/'core/history.json',
                  run/'core/v0/model_call/request.json',run/'core/frozen_candidate.json')})
    print(json.dumps(dict(status=data['status'],accepted=len(accepted),metrics=data['metrics'],cost=data['cost'])))


if __name__=='__main__':main()
