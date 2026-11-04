"""Execute only previously reserved inputs against frozen PR242 controls.

Four physical native jobs are shared by five fixed assertion controls. This is
input generalization within one real historical bug, not unseen-fault evidence.
"""
import argparse
import copy
import fcntl
import hashlib
import json
from pathlib import Path
import time
import research195_history_case as h
from research194_metrics import temporal_detection

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--frozen',default='deliverables/research195_history_qualification_20261103_r01/frozen_protocol.json')
    parser.add_argument('--out',required=True)
    args=parser.parse_args();original=Path(args.frozen).resolve();out=Path(args.out).resolve()
    frozen=json.loads(original.read_text());bindings=frozen['source_hashes']
    assert all(sha(p)==v for p,v in bindings.items()),'frozen_source_changed'
    assert frozen['controls']==h.controls(),'frozen_controls_changed'
    assert frozen['independent_reservation']['values']==[[12,7],[2,5]],'reservation_changed'
    queries=h.query_pool(h.CASE,split='independent')
    assert len(queries)==2 and all(q['split']=='independent' for q in queries)
    assert [[q['rows'][2]['data'],q['rows'][3]['delta']] for q in queries]==frozen['independent_reservation']['values']
    assert not ({q['semantic_key'] for q in queries}&{q['semantic_key'] for q in frozen['development']}),'input_overlap'
    names=['initial','improved','exception_initial','exception_improved','complete'];bundle=[]
    for name in names:
        for a in frozen['controls'][name]:bundle.append({**a,'label':name+'_'+a['label']})
    h.validate(h.CASE,bundle)
    out.mkdir(parents=True,exist_ok=False)
    source_hash=sha(__file__)
    h.dump(out/'frozen_protocol.json',dict(original_freeze=str(original),original_freeze_sha256=sha(original),
        controls=frozen['controls'],source_hashes=bindings,queries=queries,bundle=bundle,bundle_sha256=h.digest(bundle),
        driver_sha256=source_hash,scope='handwritten frozen input generalization; same historical parent and source versions; no new fault instances',
        native_budget=4,model_calls=0))
    lockpath=h.ROOT/'deliverables/research195_active_native_execution.lock'
    h.dump(out/'outcome.json',dict(status='waiting_for_native_lock',lock=str(lockpath)))
    waitstart=time.monotonic()
    with lockpath.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        wait_seconds=time.monotonic()-waitstart
        assert all(sha(p)==v for p,v in bindings.items()),'source_changed_while_waiting'
        h.dump(out/'outcome.json',dict(status='running',lock_wait_seconds=wait_seconds))
        try:
            measurement=h.evaluate(h.CASE,bundle,out/'native',queries=queries,split='independent')
        except BaseException as exc:
            h.dump(out/'outcome.json',dict(status='interrupted',error=repr(exc),lock_wait_seconds=wait_seconds))
            raise
        finally:fcntl.flock(lock,fcntl.LOCK_UN)
    assert measurement['cost']['native_compile_attempts']<=4
    assert measurement['cost']['native_execution_attempts']<=4
    rows=[]
    for name in names:
        labels={name+'_'+a['label'] for a in frozen['controls'][name]}
        projected=copy.deepcopy(measurement)
        for ev in projected['evidence']:ev['assertions']=[a for a in ev['assertions'] if a['assertion'] in labels]
        unknown=[u for u in measurement['critical_unknown'] if not u.get('assertion') or u['assertion'] in labels]
        projected['detected_ids']=sorted({e['id'] for e in projected['evidence'] if e['status']=='confirmed' and e['label']=='violation' and e['counted_target'] and any(a['failure'] for a in e['assertions'])})
        temporal=temporal_detection(projected)
        detected_tx={e['transaction_id'] for e in projected['evidence'] if e['id'] in temporal['transaction_detected_ids']}
        fp=sorted({(e['query_id'],e['variant'],e['cycle'],str(e['obligation'])) for e in projected['evidence'] if e['status']=='confirmed' and e['label']=='legal' and any(a['failure'] for a in e['assertions'])})
        triggers={variant:sum(m['id'] in labels for j in measurement['executions'] if j['variant']==variant for m in j['result'].get('triggers',[])) for variant in ['correct','primary']}
        row=dict(control=name,candidate=frozen['controls'][name],native_complete=measurement['native_complete'],reference_complete=not unknown,
            targets=len(measurement['targets']),target_transactions=len(measurement['target_transaction_ids']),
            detected_obligation_transactions=len(temporal['transaction_detected_ids']),detected_transactions=len(detected_tx),
            legal_fp_samples=len(fp),legal_fp_alarm_set=fp,critical_unknown=unknown,triggers=triggers,temporal=temporal,
            all_required_targets_detected=set(measurement['targets'])<=set(temporal['transaction_detected_ids']),
            complete_acceptance=measurement['native_complete'] and bool(measurement['targets']) and not fp and not unknown and set(measurement['targets'])<=set(temporal['transaction_detected_ids']))
        rows.append(row);h.dump(out/(name+'_projection.json'),dict(**row,evidence=projected['evidence']))
    correct={j['query_id']:not j['reference']['unknown'] and all(c['passed'] for c in j['reference']['checks']) for j in measurement['executions'] if j['variant']=='correct'}
    before={j['query_id']:dict(reference_unknown=j['reference']['unknown'],reachable=any(not c['passed'] for c in j['reference']['checks'])) for j in measurement['executions'] if j['variant']=='primary'}
    source_unchanged=all(sha(p)==v for p,v in bindings.items()) and sha(__file__)==source_hash and sha(original)==json.loads((out/'frozen_protocol.json').read_text())['original_freeze_sha256']
    no_exposure=[q for q,v in before.items() if not v['reference_unknown'] and not v['reachable']]
    report=dict(scope='Independent reserved input qualification of five handwritten frozen controls; not a model comparison or unseen-fault generalization',
      parent_bug=h.PARENT,parent_bug_count=1,queries=len(queries),source_unchanged=source_unchanged,
      candidate_unchanged=measurement['candidate_sha256']==h.digest(bundle),native_complete=measurement['native_complete'],
      paired_fixed_legal=correct,original_bug_reachability=before,no_exposure_queries=no_exposure,rows=rows,cost=measurement['cost'],lock_wait_seconds=wait_seconds,
      limitations=['Before/after are the same historical PR242 source pair as development; only input values differ.',
      'Candidate named complete is a bundle name, not proof of complete protection. Sticky-hold failures remain missed when the broken RTL never raises overflow.',
      'Unbound alarms of the wrong same-cycle candidate remain unknown and receive no violation detection credit.',
      'Physical cost is shared once across control projections; multiple failed cycles do not create multiple parent bugs.'])
    h.dump(out/'report.json',report)
    lines=[report['scope'],'parent_bug='+h.PARENT,'control | detected obligation/transaction targets | detected transactions | legal FP | unbound unknown | before triggers']
    for r in rows:lines.append(f"{r['control']} | {r['detected_obligation_transactions']}/{r['targets']} | {r['detected_transactions']}/{r['target_transactions']} | {r['legal_fp_samples']} | {len(r['critical_unknown'])} | {r['triggers']['primary']}")
    lines+=report['limitations'];(out/'report.txt').write_text('\n'.join(lines)+'\n')
    outcome=dict(status='completed' if source_unchanged and measurement['native_complete'] else 'failed_qualification',source_unchanged=source_unchanged,
      report=str(out/'report.json'),cost=measurement['cost'])
    h.dump(out/'outcome.json',outcome);print(json.dumps(outcome,indent=2))

if __name__=='__main__':main()
