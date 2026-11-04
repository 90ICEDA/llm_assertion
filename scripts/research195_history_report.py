"""Read-only native qualification projection; creates a separate report sidecar."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from research195_history_case import controls, get_case, dump, ROOT, SRC, BEFORE, AFTER
from research194_metrics import temporal_detection

def build(source,out):
    source=Path(source).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    frozen=json.loads((source/'frozen_protocol.json').read_text())
    measurement=json.loads((source/'native/measurement.json').read_text())
    verified=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in frozen['source_hashes'].items())
    before=(SRC/BEFORE/'delta_counter.sv').read_text();after=(SRC/AFTER/'delta_counter.sv').read_text()
    exact_patch=before.replace('if(rst_ni) begin','if(!rst_ni) begin',1)==after
    native_legal={j['query_id']:not j['reference']['unknown'] and all(c['passed'] for c in j['reference']['checks']) for j in measurement['executions'] if j['variant']=='correct'}
    rows=[]
    for name in ['initial','improved','exception_initial','exception_improved','complete']:
        labels={name+'_'+a['label'] for a in controls()[name]}
        projected=copy.deepcopy(measurement)
        for ev in projected['evidence']:ev['assertions']=[a for a in ev['assertions'] if a['assertion'] in labels]
        projected['critical_unknown']=[u for u in measurement['critical_unknown'] if not u.get('assertion') or u['assertion'] in labels]
        projected['reference_complete']=not projected['critical_unknown']
        projected['detected_ids']=sorted({e['id'] for e in projected['evidence'] if e['status']=='confirmed' and e['label']=='violation' and e['counted_target'] and any(a['failure'] for a in e['assertions'])})
        temporal=temporal_detection(projected)
        detected_tx={e['transaction_id'] for e in projected['evidence'] if e['id'] in temporal['transaction_detected_ids']}
        alarmset=sorted({(e['query_id'],e['variant'],e['cycle'],str(e['obligation'])) for e in projected['evidence'] if e['status']=='confirmed' and e['label']=='legal' and any(a['failure'] for a in e['assertions'])})
        marker_counts={variant:sum(m['id'] in labels for j in measurement['executions'] if j['variant']==variant for m in j['result'].get('triggers',[])) for variant in ['correct','primary']}
        row=dict(control=name,candidate=frozen['controls'][name],model_generated=False,targets=len(projected['targets']),target_transactions=len(measurement['target_transaction_ids']),
          detected_obligation_transactions=len(temporal['transaction_detected_ids']),detected_transactions=len(detected_tx),fp_alarm_set=alarmset,false_positive_samples=len(alarmset),
          triggers=marker_counts,unknown=projected['critical_unknown'],reference_complete=projected['reference_complete'],temporal=temporal)
        rows.append(row)
        dump(out/(name+'_projection.json'),dict(**row,evidence=projected['evidence']))
    report=dict(source=str(source),source_unchanged=verified,exact_one_line_upstream_patch=exact_patch,correct_reference_legal=native_legal,
      parent_bug_count=1,case=get_case(),rows=rows,actual_cost=measurement['cost'],new_native_calls=0,new_model_calls=0,
      limitations=['Qualification uses handwritten assertions, so differences establish executable mechanism opportunities rather than measured LLM/active-selection benefit.',
      'The control named complete is an assertion bundle, not a complete protection result: 4 sticky_hold obligation targets remain undetected because broken RTL never raises the antecedent overflow flag.',
      'The initial same-cycle assertion alarms on pre-violation samples of before RTL. Six alarms remain unbound unknown; they receive no true-positive credit.',
      'Independent boundary inputs are reserved and have not been executed; this result is development reachability qualification, not independent input or unseen-fault generalization.',
      'Repeated bad cycles collapse to six transactions and one parent bug; ten obligation/transaction targets are not ten independent bugs.'])
    dump(out/'report.json',report)
    lines=['Confirmed real historical RTL repair qualification: common_cells PR242',
      'Official PR: https://github.com/pulp-platform/common_cells/pull/242',
      'Commit: https://github.com/pulp-platform/common_cells/commit/'+AFTER,
      'Parent: '+BEFORE,'Original RTL differs by exactly the upstream reset polarity line: '+str(exact_patch),
      '4 native compile/execute jobs; 2 public input queries; 1 parent bug; 6 violating transactions; 10 transaction-obligation targets.',
      'control | detected obligation targets | detected transactions | legal FP samples | before triggers | unknown alarms']
    for r in rows:lines.append(f"{r['control']} | {r['detected_obligation_transactions']}/10 | {r['detected_transactions']}/6 | {r['false_positive_samples']} | {r['triggers']['primary']} | {len(r['unknown'])}")
    lines += report['limitations']
    lines += ['Raw waveforms/logs: '+str(source/'native/q0/correct/wave.vcd'),str(source/'native/q0/primary/wave.vcd'),str(source/'native/q0/correct/execute.log'),str(source/'native/q0/primary/execute.log'),
      'Representative timing: cycle3 load-derived q=14 and en/delta3; fixed overflow=0 is legal before update; cycle4 fixed overflow=1, before overflow=0. Same-cycle capture is early; next-cycle capture detects the historical bug.',
      'Representative exception: cycle6 clear=1 while fixed overflow=1; cycle7 overflow=0 is legal. Unconditional sticky assertion alarms; clear/load guard removes this FP.']
    (out/'report.txt').write_text('\n'.join(lines)+'\n')
    assert verified and exact_patch and all(native_legal.values())
    print(json.dumps({k:v for k,v in report.items() if k in ('source_unchanged','exact_one_line_upstream_patch','correct_reference_legal','actual_cost')},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);a=p.parse_args();build(a.source,a.out)
