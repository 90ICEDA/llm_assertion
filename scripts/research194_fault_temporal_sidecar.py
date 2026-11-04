"""Read-only any-violating-cycle versus first-violation fault-family accounting.

Does not modify prior results, execute queries, or generate independent inputs.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path
import time
import research194_metrics as metrics


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def run(source,out):
    started=time.monotonic();out.mkdir(parents=True,exist_ok=False)
    bindings={str(source/'results.json'):sha(source/'results.json'),str(Path(metrics.__file__).resolve()):sha(metrics.__file__)}
    rows=[]
    for old in read(source/'results.json'):
        path=source/old['case']/old['strategy']/str(old['index'])/'measurement.json'
        bindings[str(path)]=sha(path);m=read(path);t=metrics.temporal_detection(m)
        targets=set(m['targets']);timely=set(t['timely_detected_ids']);any_cycle=set(t['transaction_detected_ids'])
        late=set(t['late_detected_ids']);missed=set(t['transaction_missed_ids'])
        if not timely<=any_cycle:raise ValueError('timely_marker_not_present_in_any_cycle:'+str(path))
        by_id={e.get('evidence_id',e['id']):e for e in m['evidence'] if e['status']=='confirmed' and e['label']=='violation' and e.get('counted_target')}
        if not targets<=set(by_id):raise ValueError('target_missing_reference_evidence')
        timely_gap_obligations=sorted({by_id[e]['obligation'] for e in targets-timely})
        if timely_gap_obligations!=old['gap_obligations']:raise ValueError('original_timely_gap_mismatch')
        row=dict(case=old['case'],parent_bug=old['parent_bug'],strategy=old['strategy'],index=old['index'],mutant_id=old['mutant']['id'],
          valid_reachable_fault=old['valid_reachable_fault'],reference_complete=old['reference_complete'],
          original_measurement=str(path),original_measurement_sha256=bindings[str(path)],
          target_transaction_obligations=len(targets),timely_detected=len(timely),any_cycle_detected=len(any_cycle),
          late_only_detected=len(late),completely_missed=len(missed),
          late_only_transactions=len({by_id[e]['transaction_id'] for e in late}),
          completely_missed_transactions=len({by_id[e]['transaction_id'] for e in missed}),
          timely_gap_obligations=timely_gap_obligations,
          any_cycle_gap_obligations=sorted({by_id[e]['obligation'] for e in missed}),
          late_obligations=sorted({by_id[e]['obligation'] for e in late}),temporal=t,
          late_evidence=[dict(evidence_id=e,obligation=by_id[e]['obligation'],transaction_id=by_id[e]['transaction_id'],first_violation_cycle=by_id[e]['cycle'],delay_cycles=t['detection_delay_cycles'][e],log=by_id[e]['source_log'],vcd=by_id[e]['source_vcd']) for e in sorted(late)],
          original_actual_cost=old['cost'],new_native_queries=0,new_model_calls=0)
        rows.append(row)
    summaries=[];gap_sets={};timely_sets={}
    for strategy in ('random','seeded_region','obligation_guided'):
        rr=[r for r in rows if r['strategy']==strategy]
        gap_sets[strategy]={(r['parent_bug'],ob) for r in rr for ob in r['any_cycle_gap_obligations']}
        timely_sets[strategy]={(r['parent_bug'],ob) for r in rr for ob in r['timely_gap_obligations']}
        summaries.append(dict(strategy=strategy,mutants=len(rr),valid_reachable_faults=sum(r['valid_reachable_fault'] for r in rr),
          target_transaction_obligations=sum(r['target_transaction_obligations'] for r in rr),
          timely_detected=sum(r['timely_detected'] for r in rr),any_cycle_detected=sum(r['any_cycle_detected'] for r in rr),
          late_only_detected=sum(r['late_only_detected'] for r in rr),completely_missed=sum(r['completely_missed'] for r in rr),
          late_only_transactions=sum(r['late_only_transactions'] for r in rr),completely_missed_transactions=sum(r['completely_missed_transactions'] for r in rr),
          timely_obligation_gap_count=len(timely_sets[strategy]),any_cycle_obligation_gap_count=len(gap_sets[strategy]),
          any_cycle_obligation_gaps=[dict(parent_bug=p,obligation=o) for p,o in sorted(gap_sets[strategy])]))
    for row in summaries:
        other=set().union(*(v for k,v in gap_sets.items() if k!=row['strategy']))
        exclusive=gap_sets[row['strategy']]-other
        row['exclusive_any_cycle_obligation_gaps']=[dict(parent_bug=p,obligation=o) for p,o in sorted(exclusive)]
        row['exclusive_any_cycle_obligation_gap_count']=len(exclusive)
    verified=all(sha(path)==value for path,value in bindings.items())
    if not verified:raise ValueError('read_only_source_changed')
    dump(out/'results.json',rows);dump(out/'summary.json',summaries);dump(out/'source_bindings.json',bindings)
    dump(out/'audit.json',dict(source=str(source),source_unchanged=verified,new_native_queries=0,new_model_calls=0,
      sidecar_wall_seconds=time.monotonic()-started,
      count_unit='Each detector target is one oracle transaction and obligation; distinct parent/obligation gaps require at least one completely missed target. Target totals across mutants are descriptive instances, not independent parent-Bug successes.',
      original_report_interpretation='Original gap_obligations and report.html use first-violating-sample timely alarms. They must not be described as complete transaction misses.',
      new_interpretation='Any-cycle detection credits a real obligation-bound native alarm only at an independently confirmed violating sample in the same transaction. Late-only means detected this way but not at first violation.',
      cost='original_actual_cost is referenced original physical cost, never additional execution cost. Independent reserved faults remain unexecuted.',
      remaining_limitations=['Counter/arbiter monitors define each transition as a transaction; UART serial frame transactions span cycles. Comparisons retain these declared reference scopes.',
        'Any-cycle detection does not credit alarms at merely legal or unknown samples, or across obligations. Therefore it is conservative about alarms after the reference violation has ended.',
        'Fault validity and compile/reachability results are unchanged. This sidecar is not a new experiment.']))
    tr=''.join('<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in (r['strategy'],str(r['valid_reachable_faults'])+'/'+str(r['mutants']),r['timely_obligation_gap_count'],r['any_cycle_obligation_gap_count'],r['late_only_detected'],r['completely_missed'],r['exclusive_any_cycle_obligation_gap_count']))+'</tr>' for r in summaries)
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>故障族检出时序补充统计</title><style>body{font:16px system-ui;max-width:1150px;margin:40px auto}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:10px}</style><h1>故障族检出时序补充统计</h1><p>原报告的缺口采用“首违例周期及时告警”口径。本表把事务内晚检出与完全漏报分开；原始记录和报告均保持原样，没有新增查询或模型调用。</p><table><tr><th>策略</th><th>有效故障</th><th>原及时性义务缺口</th><th>任意违例周期完全漏报义务缺口</th><th>晚检出目标数</th><th>完全漏报目标数</th><th>独有完全漏报义务缺口</th></tr>'+tr+'</table><p>目标单位为事务×义务；义务缺口按父 Bug×义务去重，至少有一个事务完全漏报才计入。晚检出必须有同事务、同义务、被独立监视器确认违例周期上的真实 SVA 报警。不能把不同 mutant 的目标总数当独立父 Bug 成功数。</p><p><a href="summary.json">汇总与独有义务明细</a> · <a href="results.json">逐故障、晚检出周期和波形日志</a> · <a href="audit.json">口径与限制</a> · <a href="source_bindings.json">只读源校验</a></p>',encoding='utf-8')
    print(json.dumps(summaries,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.source.resolve(),a.out.resolve())
