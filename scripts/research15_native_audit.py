"""Read-only re-adjudication and isolation audit of actual native FIFO runs.

Outputs are separate from experiment records; never selects or changes SVA.
"""
import argparse
import hashlib
import json
from pathlib import Path
from research15_pipeline import ROOT, OUT, dump, read
from research15_evidence import paired_ledger
from research15_acceptance import inspect, sha

BASE=ROOT/'deliverables/research15_native_20261015_r01'


def counts(group):
    data=inspect(group['ledger'])
    return {key:len(data[key]) for key in ('rows','unknown','false_positives','detections','misses','triggers')}


def initialization():
    results=[]
    parent=BASE/'initial_qualification'
    folders=list(parent.iterdir() if parent.exists() else [])
    folders += [BASE/'initial_temporal_continuation']
    for folder in sorted(folders):
        if not (folder/'correct/replay.json').exists() or not (folder/'corrupt/replay.json').exists():continue
        fixed=read(folder/'correct/replay.json');mutant=read(folder/'corrupt/replay.json')
        group=paired_ledger(fixed,mutant,'initial_qualification:d2:p0:s2026101501')
        prior=read(folder/'qualification.json') if (folder/'qualification.json').exists() else None
        current=counts(group)
        qualified=not current['unknown'] and not current['false_positives'] and current['detections']>0
        record=dict(version=folder.name,original_qualification=prior,current_counts=current,
                    current_order_qualification=qualified,candidate_sha256=sha(fixed['candidate']),
                    artifacts=str(folder.relative_to(ROOT)))
        results.append(record)
        dump(OUT/'native_readjudication'/folder.name/'ledger.json',group)
    summary=dict(results=results,qualification_status_unchanged=all(r['original_qualification'] is None or
        r['original_qualification']['qualified']==r['current_order_qualification'] for r in results),
        policy='Corrected observation audit only; no assertion edit, model feedback, selection or holdout tuning.',
        adapter_sha256=hashlib.sha256((ROOT/'scripts/research15_evidence.py').read_bytes()).hexdigest())
    dump(OUT/'native_readjudication/initialization_summary.json',summary)
    print(json.dumps(dict(initializations_audited=len(results),status_unchanged=summary['qualification_status_unchanged'])))
    return summary


def isolation():
    checks=[]
    def check(name,passed,**details):checks.append(dict(name=name,passed=bool(passed),**details))
    if not (BASE/'all_arms_freeze.json').exists():
        dump(OUT/'native_isolation_audit.json',dict(status='incomplete',reason='all-arm freeze unavailable',checks=[]))
        return
    freeze=read(BASE/'all_arms_freeze.json')
    requests={arm:read(BASE/'arms'/arm/'model_call/request.json') for arm in 'ABCD'}
    contexts={arm:json.loads(requests[arm]['messages'][-1]['content']) for arm in 'ABCD'}
    check('same_model_options',all(requests[a]['model']==requests['A']['model'] and requests[a]['options']==requests['A']['options'] for a in 'ABCD'))
    check('same_initial_assertion_set',len({sha(contexts[a]['current_assertions']) for a in 'ABCD'})==1)
    treatment_fields={'current_assertions','counts','issues','task','acquired_new_evidence'}
    backgrounds={a:{k:v for k,v in contexts[a].items() if k not in treatment_fields} for a in 'ABCD'}
    check('same_public_background',len({sha(v) for v in backgrounds.values()})==1)
    check('acquisition_visibility_switch',all(contexts[a]['acquired_new_evidence']==(a in 'BD') for a in 'ABCD'))
    check('paired_factorial_prompts_AC_BD',contexts['A']==contexts['C'] and contexts['B']==contexts['D'])
    for arm in 'ABCD':
        folder=BASE/'arms'/arm
        check('candidate_freeze_'+arm,sha(read(folder/'frozen_candidate.json'))==freeze[arm]['candidate_sha256'])
        check('sva_freeze_'+arm,hashlib.sha256((folder/'frozen_candidate.sva').read_bytes()).hexdigest()==freeze[arm]['sva_sha256'])
        before=read(folder/'before_ledger.json')
        scenarios={r.get('scenario_id') for r in before['ledger']}
        check('before_ledger_visibility_'+arm,all(s and s.startswith('common:') for s in scenarios) if arm in 'AC' else any(s and not s.startswith('common:') for s in scenarios),scenarios=sorted(s for s in scenarios if s))
        holdout=BASE/'holdout'/arm/'ledger.json'
        if holdout.exists():
            held=read(holdout)
            devhash={r['stimulus_sha256'] for r in before['ledger']}
            heldhash={r['stimulus_sha256'] for r in held['ledger']}
            check('separate_holdout_ids_'+arm,not devhash & heldhash)
            check('holdout_split_labels_'+arm,all(r['split']=='independent_test' for r in held['ledger']))
        else:check('holdout_present_'+arm,False)
    # Hashes above are the strong freeze check. Timestamps provide only an
    # additional operational ordering record, not cryptographic chronology.
    freeze_ns=(BASE/'all_arms_freeze.json').stat().st_mtime_ns
    model_results=list((BASE/'arms').glob('*/model_call/result.json'))
    check('all_arm_model_results_precede_test_freeze',all(p.stat().st_mtime_ns<=freeze_ns for p in model_results),timestamp_evidence_only=True)
    all_test_schedules=list((BASE/'holdout').glob('*/*/*_stimulus/stimulus.json'))
    check('test_inputs_materialized_after_freeze',bool(all_test_schedules) and all(p.stat().st_mtime_ns>=freeze_ns for p in all_test_schedules),timestamp_evidence_only=True,files=len(all_test_schedules))
    result=dict(status='passed' if all(c['passed'] for c in checks) else 'failed',checks=checks,
        scope='Artifact and visibility audit only. Same generator families and engineered FIFO faults; no global correctness or external distribution claim.')
    dump(OUT/'native_isolation_audit.json',result)
    print(json.dumps(dict(status=result['status'],checks=len(checks))))
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['initialization','isolation']);args=p.parse_args()
    globals()[args.action]()
