"""Explain real event-to-property mismatch and obligation-level false alarms."""
import argparse
from pathlib import Path
import research17_loop as loop
from research34_applicability import portable
from research34_campaign import digest


def analyze(out):
    out.mkdir(parents=True,exist_ok=False)
    run=loop.ROOT/'deliverables/research36_real_20261022_r01'
    prep=loop.ROOT/'deliverables/research36_prepare_20261022_r01'
    rows=[]
    for version in ('v0','v1'):
        folder=run/'core'/version
        result=loop.read(folder/'target_native/result.json')
        info=loop.inspect(result['group']['ledger'])
        gate=loop.read(folder/'target_gate.json')
        false_alarms=[]
        for key in sorted(info['false_positives']):
            row=info['rows'][key]
            path=portable(row['source_directory'])/'replay.json'
            record=loop.read(path)
            samples={s['cycle']:s for s in record['reference_trace']}
            prev,now=samples[row['cycle']-1],samples[row['cycle']]
            false_alarms.append(dict(evidence_id=key,scenario=row['scenario_id'],cycle=row['cycle'],
                independent_oracle=row['oracle'],native=row['native'],samples=[prev,now],
                stable_payload=prev['mdata']==now['mdata'],
                current_queue_head_differs=now['mdata']!=now['ref_expected'],
                source=str(path),source_sha256=digest(path)))
        before=loop.inspect(loop.read(prep/'target_baseline.json')['group']['ledger'])
        current_scenarios={before['rows'][k]['scenario_id'] for k in before['misses']}
        current_rows=[r for r in result['group']['ledger'] if r['scenario_id'] in current_scenarios]
        current_info=loop.inspect(current_rows)
        shadow=bool(current_rows) and result['healthy'] and not any(current_info[k] for k in ('misses','false_positives','unknown'))
        rows.append(dict(version=version,edit=loop.read(folder/'model_call/model_edit.json'),
            target_triggered=sum(bool(r['edited_assertion'] and r['edited_assertion']['trigger']) for r in gate['target_rows']),
            target_detected=sum(bool(r['edited_assertion'] and r['edited_assertion']['causal_detection']) for r in gate['target_rows']),
            target_denominator=len(gate['target_rows']),false_alarm_rows=len(false_alarms),
            stable_payload_but_queue_head_differs=sum(r['stable_payload'] and r['current_queue_head_differs'] for r in false_alarms),
            new_false_positives=len(info['false_positives']-before['false_positives']),
            lost_history_detections=len(before['detections']-info['detections']),current_unknown=len(info['unknown']),
            current_scenario_shadow_accepts=shadow,
            current_scenario_counts={k:len(current_info[k]) for k in ('misses','false_positives','unknown')},
            accepted=gate['accepted'],false_alarm_examples=false_alarms[:2]))
    result=dict(versions=rows,scope='Actual development native replay. Counts are obligation/sample rows, not complete legal hardware scenarios or independent bugs. Payload stability and queue-head identity are different obligations; comparisons below are observations, not model-generated repairs.')
    loop.dump(out/'case_analysis.json',result)
    lines=['# research36 原生失败案例','',
           '|版本|目标触发|目标检出|新增义务级误报|历史检出丢失|关键unknown|接受|','|---|---:|---:|---:|---:|---:|---|']
    for r in rows:
        lines.append(f"|{r['version']}|{r['target_triggered']}/{r['target_denominator']}|{r['target_detected']}/{r['target_denominator']}|{r['new_false_positives']}|{r['lost_history_detections']}|{r['current_unknown']}|{r['accepted']}|")
    lines+=['','误报是按具体义务计算：故障RTL的某一拍可以违反数据顺序，同时满足输出保持。不能把另一个义务的失败当成保持义务的正确检出。']
    lines+=['','沿用research32已有当前场景判定规则进行事后影子检查（不更改实际决定）：']
    for r in rows: lines.append(f"- {r['version']}：当前场景接受 {r['current_scenario_shadow_accepts']}；{r['current_scenario_counts']}。只修复8个目标点不足以证明当前整个场景通过，也不能自动宣称防退化有增量收益。")
    for r in rows:
        lines+=['',f"{r['version']} 的 {r['false_alarm_rows']} 条义务级误报中，{r['stable_payload_but_queue_head_differs']} 条观测到前后输出数据相同、但与当前参考队列头不同。"]
        for e in r['false_alarm_examples']:
            prev,now=e['samples']
            lines += [f"- {e['scenario']}，{prev['cycle']}→{now['cycle']}：mdata {prev['mdata']}→{now['mdata']}，当前 ref_expected={now['ref_expected']}；独立义务判定 {e['independent_oracle']['verdict']}。"]
    lines+=['','完整证据ID、源文件哈希、原生标记及采样值见 case_analysis.json。没有手工修改性质或补写成功轨迹。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print([{k:v for k,v in r.items() if k not in ('edit','false_alarm_examples')} for r in rows],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    analyze(a.out.resolve())
