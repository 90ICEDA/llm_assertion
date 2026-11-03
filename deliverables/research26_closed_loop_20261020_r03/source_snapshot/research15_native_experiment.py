"""Same-initial, one-revision 2x2 native FIFO experiment, with held-out tests."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import research15_native_interface as interface
import research15_native_models as models
import research15_search_runtime as runtime
import research_fifo_experiment as old_fifo
from research15_acceptance import inspect,decide,sha
from research15_evidence import paired_ledger,merge_ledgers

OUT=interface.OUT;ROOT=interface.ROOT;dump=interface.dump
ARMS={'A':{'search':False,'gate':False},'B':{'search':True,'gate':False},
      'C':{'search':False,'gate':True},'D':{'search':True,'gate':True}}


def read(path):return json.loads(Path(path).read_text())


def counts(group):
    data=inspect(group['ledger'])
    result={k:len(data[k]) for k in ('rows','unknown','triggers','false_positives','detections','misses')}
    result['count_unit']='obligation-by-sampled-cycle evidence rows, not independent discoveries or transactions'
    result['later_attribution_unknown']=len(group.get('exclusions',[]))
    return result


def snapshot(folder):
    folder.mkdir(parents=True,exist_ok=False)
    names=['research15_native_experiment.py','research15_native_interface.py','research15_native_models.py',
        'research15_search_runtime.py','research15_acceptance.py','research15_evidence.py',
        'research_native_runner.py','research_native_model.py','obligation_continuation_interface.py',
        'research_native_closed_loop.py','research_fifo_experiment.py','research15_search_experiment.py']
    for name in names:shutil.copyfile(ROOT/'scripts'/name,folder/name)
    dump(folder/'hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob('*.py')})


def pair(compiled,folder,rows,mode,scenario):
    fixed=runtime.execute(compiled,folder/'correct',rows,'correct')
    mutant=runtime.execute(compiled,folder/mode,rows,mode)
    result=paired_ledger(fixed,mutant,scenario)
    dump(folder/'paired_ledger.json',result)
    return result


def baseline():
    initial=read(OUT/'shared_initial.json')
    assert initial is not None,'initial_generation_failed_no_template_fallback'
    rows=old_fifo.stimulus(2026101501)
    for row in rows:row['drain_due']=0
    compiled=runtime.build(initial,OUT/'baseline/compiled',2,0)
    result=pair(compiled,OUT/'baseline/replay',rows,'corrupt','common:d2:p0:s2026101501')
    dump(OUT/'baseline/stimulus.json',rows)
    dump(OUT/'baseline/summary.json',counts(result))
    protocol=dict(arms=ARMS,initial_sha256=sha(initial),options=models.OPTIONS,
        calls_per_arm=1,max_initial_calls=2,
        common_development='same ordinary correct/corrupt replay without drain_due; preexisting model context/specification identical',
        extra_search='B/D share one actual contract-search witness and its provenance, cost explicitly shared; A/C never receive it',
        acceptance='A/B require compilation and current-feedback target repair without current-evidence false positives; C/D additionally enforce full historical gate; all four record gate audit',
        holdout=[dict(seed=2026101591,family='random'),dict(seed=2026101592,family='tail_loss'),dict(seed=2026101593,family='reset_pending')],
        holdout_parameters={'depth':4,'pipeline':2},holdout_policy='Generate and execute only after all four accepted versions are frozen. No model calls or selection after holdout.',
        scope='One revision per arm, single parent artificial boundary fault family on actual FIFO. Finite replay; no formal proof.')
    dump(OUT/'protocol.json',protocol)
    print(json.dumps(counts(result)))


def feedback(group,initial,search_enabled):
    data=inspect(group['ledger'])
    issues=[]
    for field in ('false_positives','misses','unknown'):
        for key in sorted(data[field])[:2]:
            row=data['rows'][key]
            issues.append(dict(kind=field,obligation=row['obligation'],cycle=row.get('cycle'),
                mode=row.get('variant'),oracle=row['oracle'],violations=row.get('oracle_violation',[])))
    return dict(current_assertions=initial,counts=counts(group),issues=issues,
        task='Return a complete replacement assertion SET. Repair the independently observed gaps with complementary properties while retaining earlier protection. If no confirmed gap is exposed by this feedback, retain the initial property. Do not duplicate properties. Use at most three assertions. Only the feedback shown is available.',
        acquired_new_evidence=search_enabled)


def arms(witness_path):
    initial=read(OUT/'shared_initial.json');protocol=read(OUT/'protocol.json')
    assert sha(initial)==protocol['initial_sha256']
    snapshot(OUT/'execution_source_snapshot')
    common=read(OUT/'baseline/replay/paired_ledger.json');rows=read(OUT/'baseline/stimulus.json')
    initial_compiled=read(OUT/'baseline/compiled/compiled.json')
    digest=models.service()
    # The acquisition remains isolated from A/C prompts. Only B/D adapters read
    # its content; the full artifact and query costs remain in search provenance.
    witness=None;search_before=None
    for arm,config in ARMS.items():
        folder=OUT/'arms'/arm;folder.mkdir(parents=True,exist_ok=False)
        if config['search'] and witness is None:
            witness=read(witness_path)
            assert witness and witness.get('rows'),'no_actual_search_witness_do_not_substitute_template'
            assert witness['initial_candidate_sha256']==hashlib.sha256((OUT/'shared_initial.json').read_bytes()).hexdigest(),'search_initial_candidate_changed'
            dump(OUT/'treatment_witness_used.json',witness)
            depth,pipeline=witness.get('depth',2),witness.get('pipeline',0)
            witness={**witness,'scenario_id':f'search:d{depth}:p{pipeline}:'+witness['scenario_id']}
            search_compiled=initial_compiled if (depth,pipeline)==(2,0) else runtime.build(initial,OUT/'search_baseline/compiled',depth,pipeline)
            search_before=pair(search_compiled,OUT/'search_baseline/replay',witness['rows'],witness['mode'],witness['scenario_id'])
        before=merge_ledgers([common,search_before] if config['search'] else [common])
        dump(folder/'before_ledger.json',before)
        ctx=models.context();ctx.update(feedback(before,initial,config['search']))
        call,candidate=models.call(folder/'model_call',ctx,digest)
        accepted=initial;after=None;decision={'accepted':False,'reasons':[{'kind':'generation_or_interface_failure'}]}
        if candidate is not None:
            compiled=runtime.build(candidate,folder/'compiled',2,0)
            if compiled['native']['compile_status']=='passed':
                common_after=pair(compiled,folder/'common_replay',rows,'corrupt','common:d2:p0:s2026101501')
                current_after=common_after
                if config['search']:
                    depth,pipeline=witness.get('depth',2),witness.get('pipeline',0)
                    search_compiled=compiled if (depth,pipeline)==(2,0) else runtime.build(candidate,folder/'search_compiled',depth,pipeline)
                    current_after=pair(search_compiled,folder/'search_replay',witness['rows'],witness['mode'],witness['scenario_id'])
                after=merge_ledgers([common_after,current_after] if config['search'] else [common_after])
                old_inspect=inspect(before['ledger'])
                targets=sorted(old_inspect['false_positives']|old_inspect['misses'])
                gate=decide(before['ledger'],after['ledger'],targets)
                dump(folder/'historical_gate_audit.json',gate)
                now=inspect(current_after['ledger'])
                current_keys=set(now['rows'])
                current_targets=[k for k,row in now['rows'].items() if row['oracle']['verdict']=='violated']
                plain_ok=not now['unknown'] and not now['false_positives'] and all(k in now['detections'] for k in current_targets)
                decision=dict(accepted=gate['accepted'] if config['gate'] else plain_ok,
                    gate_enforced=config['gate'],plain_current_evidence_acceptance=plain_ok,
                    reasons=gate['reasons'] if config['gate'] else ([] if plain_ok else [{'kind':'current_evidence_not_repaired_or_unknown'}]))
                if decision['accepted']:accepted=candidate
                dump(folder/'after_ledger.json',after)
            else:decision={'accepted':False,'reasons':[{'kind':'native_compile_failed'}]}
        dump(folder/'decision.json',decision)
        dump(folder/'frozen_candidate.json',accepted)
        (folder/'frozen_candidate.sva').write_text(interface.candidate_sva(accepted))
        dump(folder/'freeze.json',dict(candidate_sha256=sha(accepted),sva_sha256=hashlib.sha256((folder/'frozen_candidate.sva').read_bytes()).hexdigest(),
            selected_version='proposal' if decision['accepted'] else 'retained_initial',final_for_holdout=True))
        dump(folder/'summary.json',dict(config=config,call=call,decision=decision,before=counts(before),after=counts(after) if after else None))
        print('ARM',arm,decision,flush=True)
    dump(OUT/'all_arms_freeze.json',{arm:read(OUT/'arms'/arm/'freeze.json') for arm in ARMS})


def holdout():
    from research15_search_experiment import stimulus
    freezes=read(OUT/'all_arms_freeze.json');protocol=read(OUT/'protocol.json')
    # New inputs are first materialized only after the all-arm freeze exists.
    cases=[(entry,stimulus(entry['seed'],entry['family'])) for entry in protocol['holdout']]
    summaries={}
    for arm in ARMS:
        candidate=read(OUT/'arms'/arm/'frozen_candidate.json')
        assert sha(candidate)==freezes[arm]['candidate_sha256']
        folder=OUT/'holdout'/arm
        compiled=runtime.build(candidate,folder/'compiled',4,2)
        groups=[]
        for case,rows in cases:
            scenario=f'holdout:d4:p2:s{case["seed"]}:{case["family"]}'
            target=folder/case['family']
            fixed=runtime.execute(compiled,target/'correct',rows,'correct')
            for mode in runtime.MODES[1:]:
                mutant=runtime.execute(compiled,target/mode,rows,mode)
                groups.append(paired_ledger(fixed,mutant,scenario))
        result=merge_ledgers(groups)
        for row in result['ledger']:row['split']='independent_test'
        dump(folder/'ledger.json',result);summaries[arm]=counts(result)
    dump(OUT/'holdout/summary.json',summaries)
    print(json.dumps(summaries,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['baseline','arms','holdout'])
    parser.add_argument('--witness',default=str(ROOT/'deliverables/research15_search_20261015_r01/model_search/treatment_witness.json'))
    args=parser.parse_args()
    if args.action=='baseline':baseline()
    elif args.action=='arms':arms(args.witness)
    else:holdout()
