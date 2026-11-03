"""Bounded real-model/native-SVA FIFO loop; prospective immutable run folders."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

import research17_model as model
import research17_fifo_feedback as runtime
import research15_search_experiment as search
import research15_native_experiment as previous
import research_fifo_experiment as fifo
from research15_acceptance import inspect,decide,sha
from research15_evidence import paired_ledger,merge_ledgers
from research17_search_audit import validate_witness,audit_search

ROOT=model.ROOT
dump=model.dump;read=model.read
ARMS=previous.ARMS
CONFIG=dict(model='qwen2.5-coder:7b-instruct',options=dict(seed=20261017,temperature=0,num_predict=1024,num_ctx=16384,num_gpu=0,num_thread=8),
    max_model_calls=17,max_tokens=190000,max_wall_seconds=7200,call_timeout=900,
    max_initial_calls=2,max_refinement_calls=3,search_budget=6)


def counts(group):return previous.counts(group)


def common_case():
    rows=fifo.stimulus(2026101501)
    for row in rows:row['drain_due']=0
    return dict(id='common:d2:p0:s2026101501',depth=2,pipeline=0,rows=rows,mode='corrupt',source='ordinary_feedback')


def replay(candidate,folder,cases):
    """Same stable identities for every version; all controls checked natively."""
    compiled={};groups=[];feedback=[];health=[]
    for index,case in enumerate(cases):
        key=(case['depth'],case['pipeline'])
        if key not in compiled:
            compiled[key]=runtime.build(candidate,folder/f'compiled_d{key[0]}_p{key[1]}',*key)
        build=compiled[key]
        if build['native']['compile_status']!='passed':
            result=dict(healthy=False,compile_failure=build['native'],group=None,feedback=[])
            dump(folder/'result.json',result);return result
        path=folder/f'case_{index}'
        fixed=runtime.execute(build,path/'correct',case['rows'],'correct')
        mutant=runtime.execute(build,path/case['mode'],case['rows'],case['mode'])
        group=paired_ledger(fixed,mutant,case['id']);groups.append(group)
        dump(path/'ledger.json',group);dump(path/'case.json',case)
        detail=runtime.feedback(fixed,mutant,group);feedback.append(dict(scenario=case['id'],diagnostic=detail))
        for record in (fixed,mutant):
            n=record['native'];o=record['oracle']
            health.append(dict(scenario=case['id'],mode=record['mode'],
                okay=n.get('compile_status')=='passed' and n.get('tool_support_status')=='supported_for_compiled_constructs'
                    and n.get('execution_status')=='completed' and record['sampling_qualification']['status']=='passed'
                    and o['legality']=='legal' and not o['unknown']
                    and (record['mode']!='correct' or (not o['violations'] and not n['failures'])),
                native_status={k:n.get(k) for k in ('compile_status','tool_support_status','execution_status')},
                sampling=record['sampling_qualification']['status'],oracle_unknown=o['unknown'],
                legal_control_native_failures=n['failures'] if record['mode']=='correct' else None))
    group=merge_ledgers(groups)
    result=dict(healthy=all(x['okay'] for x in health),health=health,group=group,counts=counts(group),feedback=feedback)
    dump(folder/'result.json',result);return result


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    previous.snapshot(out/'source_snapshot')
    for p in (Path(__file__),ROOT/'scripts/research17_model.py',ROOT/'scripts/research17_fifo_feedback.py',ROOT/'scripts/research17_search_audit.py'):
        shutil.copy2(p,out/'source_snapshot'/p.name)
    shutil.copy2(runtime.runtime.RTL,out/'axis_fifo.v')
    dump(out/'source_snapshot/hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'source_snapshot').glob('*.py')})
    dump(out/'protocol.json',dict(config=CONFIG,created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        core='Fresh true model initial order assertion; first qualified only; four-policy native search; strict witnesses; up to 3 actual edits with sampled feedback and full historical gate.',
        schema='Same constrained syntax subset for all calls; all Boolean predicates and timing chosen by model, no semantic repair.',
        arms=ARMS,ablation='Run only if core repairs acquired target. All start same initial and use same model/options/schema. B/D share acquired development evidence; A/C cannot receive it. Up to3 calls per arm; stop on valid current resolution. Core D is a pilot, separate from four-arm evidence.',
        budget='All physical model/native calls charged, including pilot, failed edits, compile smoke, search and evaluation. Equal arm maxima, report actual unequal costs.',
        witness_selection='First strictly valid contract tail_loss/drain_no_loss witness per searched parameter configuration; two configurations are replication, one unique fault/obligation class.',
        independent='After core freeze, materialize new secret random seeds, depth4/pipeline2. Never feed core test outcomes to later arm prompts. After all arms freeze, materialize a different fresh shared test batch. No adaptation from either test batch.',
        old_tests='All prior research16 holdouts are development for this study; old artifacts immutable. No independence claim for their reuse.',
        limitations='Actual upstream axis_fifo RTL plus artificial output-boundary faults; original FIFO presented unknown. Finite bounded fair drain <=RAM8/pipeline2; no formal proof. Single parent and model seed. Exact internal full state unknown.',
        root_git_commit=None,source_versions='Content hashes in source_snapshot and axis_fifo file; missing root historical Git not invented.'))


def initial(out,llm):
    feedback={}
    for iteration in range(CONFIG['max_initial_calls']):
        folder=out/'initial'/f'v{iteration}'
        call,candidate=llm.call(folder/'model_call',None,'order_payload',feedback,'initial_generation')
        result=replay(candidate,folder/'native',[common_case()]) if candidate else None
        c=result['counts'] if result and result['group'] else {}
        okay=bool(result and result['healthy'] and c and not c['unknown'] and not c['false_positives'] and not c['misses'] and c['detections'])
        dump(folder/'decision.json',dict(qualified=okay,call=call,counts=c))
        print('INITIAL',iteration,okay,c,flush=True)
        if okay:
            dump(out/'shared_initial.json',candidate)
            dump(out/'shared_initial_freeze.json',dict(hash=sha(candidate),origin=str(folder/'model_call'),model_selected=True))
            return candidate
        feedback=dict(call=call,native=result)
    return None


def acquire(out):
    subprocess.run([sys.executable,str(ROOT/'scripts/research15_search_experiment.py'),'--candidate',str(out/'shared_initial.json'),
        '--out',str(out/'search'),'--budget',str(CONFIG['search_budget'])],check=True)
    base=out/'search';records=read(base/'results.json');cases=[];validations=[];seen=set()
    for r in records:
        key=(r['depth'],r['pipeline'])
        if key in seen or r['method']!='contract_coverage' or r['selection']['family']!='tail_loss' or r['evidence']['status']!='ok':continue
        items=[e for e in r['evidence']['mapping'] if e['variant']=='drop' and e['obligation']=='drain_no_loss' and e['kind']=='false_negative']
        if not items:continue
        witness=dict(scenario_id=r['folder'],mode='drop',first_violation=items[0])
        verified=validate_witness(base,witness);validations.append(verified)
        if not verified['valid']:continue
        seen.add(key)
        cases.append(dict(id=f'search:d{key[0]}:p{key[1]}:'+r['folder'],depth=key[0],pipeline=key[1],mode='drop',
            rows=read(base/r['folder']/'stimulus.json'),source='contract_coverage',source_query=r['folder'],validation=verified))
    dump(out/'search/strict_witnesses.json',validations);dump(out/'search/admitted_cases.json',cases)
    dump(out/'search/corrected_comparison.json',audit_search(base))
    return cases


def freeze(folder,candidate,reason):
    dump(folder/'frozen_candidate.json',candidate)
    (folder/'frozen_candidate.sva').write_text(model.native.candidate_sva(candidate))
    dump(folder/'freeze.json',dict(candidate_sha256=sha(candidate),reason=reason,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))


def refine(out,llm,initial_candidate,cases,gate_enabled,phase,prior_rejection=None):
    accepted=copy.deepcopy(initial_candidate)
    before=replay(accepted,out/'before',cases)
    if not before['group'] or not before['healthy']:raise RuntimeError('unhealthy_development_replay')
    old=inspect(before['group']['ledger']);targets=sorted(old['misses']|old['false_positives'])
    target=old['rows'][targets[0]]['obligation'] if targets else None
    feedback=dict(counts=before['counts'],current_gap_ids=targets,actual_native_evidence=before['feedback'])
    if prior_rejection is not None:feedback['prior_rejected_development_proposal']=prior_rejection
    history=[];resolved=False
    for iteration in range(CONFIG['max_refinement_calls']):
        folder=out/f'v{iteration}'
        call,candidate=llm.call(folder/'model_call',accepted,target,feedback,phase)
        after=replay(candidate,folder/'native',cases) if candidate else None
        decision=dict(accepted=False,reasons=[dict(kind='model_or_interface_failure')],gate_enforced=gate_enabled)
        if after and after['group']:
            gate=decide(before['group']['ledger'],after['group']['ledger'],targets)
            dump(folder/'historical_gate_audit.json',gate)
            # Plain feedback validates the current acquisition only. Full replay
            # is audit-only for the unguarded arm and never leaks into its prompt.
            current_case_index=len(cases)-1
            current_group=read(folder/'native'/f'case_{current_case_index}'/'ledger.json')
            now=inspect(current_group['ledger'])
            current_targets=[k for k,r in now['rows'].items() if r['oracle']['verdict']=='violated']
            current_health=all(h['okay'] for h in after['health'] if h['scenario']==cases[-1]['id'])
            plain=current_health and not now['unknown'] and not now['false_positives'] and all(k in now['detections'] for k in current_targets)
            okay=gate['accepted'] and after['healthy'] if gate_enabled else plain
            decision=dict(accepted=bool(okay),gate_enforced=gate_enabled,plain_current_pass=bool(plain),
                reasons=gate['reasons'] if gate_enabled else ([] if plain else [dict(kind='current_evidence_unrepaired_or_unknown')]))
            if gate_enabled and not after['healthy']:decision['reasons'].append(dict(kind='native_or_sampling_or_legal_control_health_failed'))
            if okay:accepted=candidate;resolved=True
        elif after:decision['reasons']=[dict(kind='native_compile_failed')]
        dump(folder/'decision.json',decision)
        history.append(dict(iteration=iteration,call=call,decision=decision,before=before['counts'],after=after.get('counts') if after else None))
        dump(out/'history.json',history)
        print('REFINE',phase,iteration,decision,flush=True)
        if resolved:break
        if after and after.get('feedback'):
            diagnostics=after['feedback'] if gate_enabled else after['feedback'][-1:]
        else:
            # A transport/schema/compile failure supplies no replacement
            # observations. Keep the last actual development observations so
            # the next model request does not silently lose the target witness.
            diagnostics=feedback.get('actual_native_evidence') or before['feedback']
            if not gate_enabled:diagnostics=diagnostics[-1:]
        feedback=dict(current_gap_ids=targets,initial_feedback=feedback if iteration==0 else None,
            previous_rejected_proposal=model.structured(candidate),actual_rejection=decision,
            transport_or_interface_diagnostic=call,actual_native_evidence=diagnostics,
            accepted_version_retained=model.structured(accepted))
    freeze(out,accepted,'accepted_revision' if resolved else 'retained_initial_after_bounded_rejections')
    result=dict(resolved=resolved,has_acquired_gap=bool(targets),target_keys=targets,history=history,
        frozen_hash=sha(accepted),scope='Identical finite historical replay only; all-obligation completeness not implied')
    dump(out/'summary.json',result);return result


def holdout(folder,candidates):
    """Create inputs only after every supplied candidate has been frozen."""
    folder.mkdir(parents=True,exist_ok=False)
    entries=[dict(seed=secrets.randbelow(2**31),family=f) for f in ('random','tail_loss','reset_pending','backpressure','overlap')]
    dump(folder/'split.json',dict(created_after_freeze=True,seeds=entries,parameters=dict(depth=4,pipeline=2),
        hashes={name:sha(c) for name,c in candidates.items()},usage='independent_test_no_feedback_no_selection'))
    cases=[]
    for e in entries:
        rows=search.stimulus(e['seed'],e['family'])
        for mode in runtime.runtime.MODES[1:]:
            cases.append(dict(id=f'test:d4:p2:s{e["seed"]}:{e["family"]}:{mode}',depth=4,pipeline=2,rows=rows,mode=mode,source='independent'))
    summaries={}
    for name,candidate in candidates.items():
        result=replay(candidate,folder/name,cases)
        if result['group']:
            for row in result['group']['ledger']:row['split']='independent_test'
            dump(folder/name/'independent_ledger.json',result['group'])
            info=inspect(result['group']['ledger'])
            by_obligation={o:{k:sum(info['rows'][key]['obligation']==o for key in info[k]) for k in ('detections','misses','unknown','false_positives','triggers')} for o in model.SPECS}
        else:by_obligation={}
        summaries[name]=dict(counts=result.get('counts'),by_obligation=by_obligation,healthy=result['healthy'])
    dump(folder/'summary.json',summaries);return summaries


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'deliverables/research17_closed_loop_20261016_r01');args=p.parse_args()
    out=args.out.resolve();prepare(out)
    llm=model.Model(out,CONFIG)
    outcome=dict(status='running')
    try:
        candidate=initial(out,llm)
        if not candidate:outcome=dict(status='initial_not_qualified');return
        cases=acquire(out)
        if not cases:outcome=dict(status='no_strict_valid_search_witness');return
        core=refine(out/'core',llm,candidate,[common_case()]+cases,True,'core_both_mechanisms')
        outcome=dict(status='core_resolved' if core['resolved'] else 'core_unresolved',core=core)
        # Test once and retain every outcome; test content never enters calls.
        holdout(out/'core_independent',{'core':read(out/'core/frozen_candidate.json')})
        if not core['resolved']:return
        arm_results={};frozen={}
        for name,config in ARMS.items():
            arm_results[name]=refine(out/'arms'/name,llm,candidate,[common_case()]+(cases if config['search'] else []),config['gate'],'ablation_'+name)
            frozen[name]=read(out/'arms'/name/'frozen_candidate.json')
        dump(out/'all_arms_freeze.json',{name:sha(c) for name,c in frozen.items()})
        outcome['arms']=arm_results
        holdout(out/'ablation_independent',frozen)
        outcome['status']='core_and_four_arms_executed'
    except Exception as exc:
        outcome.update(status='execution_blocked',error=repr(exc))
        raise
    finally:
        dump(out/'outcome.json',outcome)
        dump(out/'model_cost.json',dict(calls=len(llm.calls),prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in llm.calls),
            completion_tokens=sum(c.get('completion_tokens') or 0 for c in llm.calls),
            usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in llm.calls),formal_calls=0))


if __name__=='__main__':main()
