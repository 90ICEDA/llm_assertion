"""Read-only reclassification of native fault runs under conservative legal feedback.

No native execution or model calls. Preserve original measurements and ledgers.
Verify current bench and independent monitor against archived native artifacts.
"""
import argparse
import copy
import hashlib
import html
import json
from pathlib import Path
import time
import research194_cases as c


def read(path):return json.loads(path.read_text())


def run(source,out):
    started=time.monotonic()
    out.mkdir(parents=True,exist_ok=False);rows=[];feedback={};checks=[]
    oldrows=read(source/'results.json')
    first=source/oldrows[0]['case']/oldrows[0]['strategy']/str(oldrows[0]['index'])
    initial_runtime_snapshot=first/'source_snapshot'
    actual_loaded_source=next(initial_runtime_snapshot.glob('*_research194_cases.py'))
    runtime_hash=hashlib.sha256(actual_loaded_source.read_bytes()).hexdigest()
    for row in oldrows:
        folder=source/row['case']/row['strategy']/str(row['index']);m=read(folder/'measurement.json');protocol=read(folder/'protocol.json');candidate=protocol['candidate']
        if not any(f['id']==row['mutant']['id'] for f in c.FAULTS[row['case']]):c.FAULTS[row['case']].append(copy.deepcopy(row['mutant']))
        validated=True
        for job in m['executions']:
            q=next(q for q in protocol['queries'] if q['id']==job['query_id']);oldjob=Path(job['folder'])
            bench_equal=c._bench(row['case'],candidate,q['rows'],job['variant'])==(oldjob/'tb.sv').read_text()
            monitor_equal=c.reference(row['case'],job['trace'])==job['reference']
            generated=c._sources(row['case'],out/'source_verification'/row['case']/row['strategy']/str(row['index'])/job['variant'],job['variant'])
            rtl_equal=all(p.read_bytes()==(oldjob.parent/(job['variant']+'_rtl')/p.name).read_bytes() for p in generated)
            checks.append(dict(case=row['case'],strategy=row['strategy'],index=row['index'],variant=job['variant'],bench_equal=bench_equal,monitor_equal=monitor_equal,rtl_equal=rtl_equal))
            validated=validated and bench_equal and monitor_equal and rtl_equal
        changed=0
        for e in m['evidence']:
            if e['label']=='legal' and e['variant']!='correct':
                changed+=e['status']=='confirmed';e['status']='unknown'
        m['false_positives']=[e for e in m['false_positives'] if e['variant']=='correct']
        source_notes=[u for u in m['critical_unknown'] if u.get('reason')==['source_changed_during_execution']]
        m['critical_unknown']=[u for u in m['critical_unknown'] if u.get('reason')!=['source_changed_during_execution']]
        if not validated:m['critical_unknown'].append(dict(reason=['regrade_bench_or_monitor_mismatch']))
        m['reference_complete']=not m['critical_unknown'];m['source_unchanged']=validated
        m['reclassification']=dict(original_measurement=str(folder/'measurement.json'),original_runtime_case_source_sha256=runtime_hash,
          original_runtime_source_snapshot=str(actual_loaded_source),current_cases_source_sha256=hashlib.sha256(Path(c.__file__).read_bytes()).hexdigest(),
          native_bench_and_independent_monitor_equal=validated,legal_mutant_records_changed_to_unknown=changed,
          original_source_binding_notices=source_notes,new_native_queries=0,new_model_calls=0,
          cost_semantics='cost is imported actual original execution cost, not re-execution cost',
          reason='Module was loaded before on-disk classification correction. Later per-job source file hashes may describe new disk content; first captured runtime snapshot binds original loaded code. Actual generated bench and reference output are verified.')
        target=out/row['case']/row['strategy']/str(row['index'])/'measurement.json';c.dump(target,m)
        nr=copy.deepcopy(row);nr.update(measurement=str(target),false_positives=len(m['false_positives']),reference_complete=m['reference_complete'],regrade_verified=validated);rows.append(nr)
        if row['strategy']=='obligation_guided':
            public_faults=c.get_case(row['case'])['faults'];fault=public_faults[row['index']]
            feedback.setdefault(row['case'],[]).append(dict(fault_id=fault['id'],order=row['index'],valid_reachable_fault=row['valid_reachable_fault'] and validated,
              queries=protocol['queries'],measurement=str(target),native_cost=m['cost'],
              evidence=[e for e in m['evidence'] if e['status']=='confirmed' and (e['label']=='violation' and e.get('counted_target') or e['label']=='legal' and e['variant']=='correct')],
              selection='fixed obligation-guided manifest order; no ranking by search result',visibility='development_only'))
    summary=[]
    for case in sorted({r['case'] for r in rows}):
        for strategy in ('random','seeded_region','obligation_guided'):
            rr=[r for r in rows if r['case']==case and r['strategy']==strategy]
            summary.append(dict(case=case,strategy=strategy,mutants=len(rr),valid=sum(r['valid_reachable_fault'] for r in rr),
              gap_obligations=sorted({o for r in rr for o in r['gap_obligations']}),
              compile_attempts=sum(r['cost']['native_compile_attempts'] for r in rr),execution_attempts=sum(r['cost']['native_execution_attempts'] for r in rr),
              native_seconds=sum(r['cost']['native_seconds'] for r in rr),all_regrade_verified=all(r['regrade_verified'] for r in rr)))
    c.dump(out/'results.json',rows);c.dump(out/'checks.json',checks);c.dump(out/'summary.json',summary)
    c.dump(out/'obligation_guided_feedback.json',dict(cases=feedback,independent_faults_exposed=False,new_native_queries=0,new_model_calls=0))
    c.dump(out/'audit_notes.json',dict(original_source=str(source),reclassification_only=True,
      split_claim='Reserved independent concrete RTL sites are excluded. Random assignment XOR shares broad XOR operator family with a reserved output-XOR fault, so do not claim complete operator-family holdout.',
      original_preregistration_correction='The split_rule sentence claimed both sites and operators excluded; only the concrete site guarantee applies across all three policies.',
      cost='All original actual costs retained once; this report creates zero new query outcomes.',reclassification_wall_seconds=time.monotonic()-started,historical_repair_region=False,independent_test_executed=False))
    table=''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in (r['case'],r['strategy'],str(r['valid'])+'/'+str(r['mutants']),', '.join(r['gap_obligations']),r['compile_attempts'],r['execution_attempts'],round(r['native_seconds'],2),r['all_regrade_verified']))+'</tr>' for r in summary)
    artifact_links=''.join('<li><a href="'+str(Path(r['measurement']).relative_to(out)).replace('\\','/')+'">'+html.escape(r['case']+'/'+r['strategy']+'/'+str(r['index']))+'</a></li>' for r in rows)
    (out/'report.html').write_text('<!doctype html><meta charset="utf-8"><title>Fault-family native comparison</title><style>body{font:15px system-ui;max-width:1250px;margin:40px auto}td,th{border:1px solid #ccc;padding:9px}table{border-collapse:collapse}</style><h1>Fault-family native comparison</h1><p>Real upstream RTL; artificial obligation faults. Seeded region means the artificial injection site, not a confirmed historical repair. Frozen handwritten initial SVA, zero model calls.</p><p>Each policy receives three mutants per design and two actual native jobs per mutant. Compile and run times are measured. Gap sets count distinct parent/obligation requirements, not failing cycles. Independent reserved fault sites have not been executed.</p><table><tr><th>Design</th><th>Policy</th><th>Valid/reachable</th><th>Unprotected obligations</th><th>Compile attempts</th><th>Runs</th><th>Native seconds</th><th>Replay verified</th></tr>'+table+'</table><p>This artifact reclassifies existing logs; it creates zero new native queries. All legal evidence and false positives use the independently legal correct RTL. Mutant passing fragments remain unknown. Generated RTL, assertion bench and independent reference outputs are checked against archived jobs.</p><p>Holdout limitation: concrete RTL locations are disjoint. A random XOR assignment shares a broad operator family with a reserved output-XOR fault. Do not claim full operator-family independence or generalization from development mutants.</p><p><a href="audit_notes.json">Audit notes</a> · <a href="checks.json">Artifact equality checks</a> · <a href="obligation_guided_feedback.json">Development-only feedback</a></p><ul>'+artifact_links+'</ul>',encoding='utf-8')
    print(json.dumps(dict(rows=len(rows),verified=sum(r['regrade_verified'] for r in rows),new_native_queries=0)))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.source.resolve(),a.out.resolve())
