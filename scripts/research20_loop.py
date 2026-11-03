"""Fresh-model progressive FIFO refinement, strict historical gate, fresh holdout."""
import argparse
import copy
import hashlib
from pathlib import Path
import shutil
import time

import research17_loop as loop
import research17_model as base
from research20_model import Model
from research20_cases import cases

ROOT=loop.ROOT
dump,read=loop.dump,loop.read
STAGES=(('drain_no_loss',),('no_unsolicited_output','reset_cancellation'),('stall_stability',))


def coverage_samples(replay_folder, selected, obligations):
    result=[]
    for i,case in enumerate(selected):
        folder=replay_folder/f'case_{i}'/'correct'
        oracle=read(folder/'oracle.json')
        samples=read(folder/'reference_trace.json')
        checks=[c for c in oracle['checks'] if c['obligation'] in obligations][:2]
        for check in checks:
            cycle=check['cycle']
            result.append(dict(scenario=case['id'], source=str(folder), independent_check=check,
                samples=[s for s in samples if cycle-1<=s['cycle']<=cycle+1]))
    return result[:8]


def refine(out,llm,initial,selected,max_iterations,stages_to_run=STAGES):
    folder=out/'core'
    current=copy.deepcopy(initial)
    before=loop.replay(current,folder/'before',selected)
    if not before['healthy'] or not before.get('group'):
        raise RuntimeError('initial_development_replay_unhealthy')
    origin=before
    dump(out/'search/admitted_cases.json',selected)
    info=loop.inspect(before['group']['ledger'])
    witnesses=[info['rows'][k] for k in sorted(info['misses'])]
    dump(out/'search/validated_missing_evidence.json',dict(witnesses=witnesses,
        scope='Independent queue oracle, identical legal input handshakes, healthy native controls. Candidate verdict is not the RTL oracle. First-violation attribution only.',
        dedup='fault mode plus obligation, not waveform/seed/parameter variants'))
    history=[];stages=[];ordinal=0
    for obligations in stages_to_run:
        old=loop.inspect(before['group']['ledger'])
        targets=sorted(k for k in old['misses']|old['false_positives'] if old['rows'][k]['obligation'] in obligations)
        coverage_only=not targets
        # Coverage acquisition uses actual obligation checks, not arbitrary
        # satisfied ledger rows whose applicability may be empty.
        samples=coverage_samples(folder/'before',selected,obligations)
        if coverage_only:
            for sample in samples:
                cycle=sample['independent_check']['cycle']
                targets.extend(k for k,r in old['rows'].items() if r['obligation'] in obligations
                    and r['scenario_id']==sample['scenario'] and r['variant']=='correct'
                    and r['cycle']==cycle and k not in old['triggers'])
            targets=sorted(set(targets))
        if not targets:
            stages.append(dict(obligations=obligations,status='no_unresolved_observed_gap',target_keys=[]))
            continue
        feedback=dict(requested_obligations=obligations,current_gap_ids=targets,
            counts=before['counts'],actual_native_evidence=before['feedback'],coverage_samples=samples)
        source_record=out/'reused_core_source.json'
        if source_record.exists():
            source=Path(read(source_record)['source'])
            old_history=read(source/'core/history.json')
            rejected=[h for h in old_history if not h['decision']['accepted'] and set(h['requested_obligations']) & set(obligations)]
            if rejected:
                last=rejected[-1];call_folder=source/'core'/f"v{last['iteration']}"/'model_call'
                if (call_folder/'model_edit.json').exists():feedback['previous_rejected_proposal']=read(call_folder/'model_edit.json')
                feedback.update(actual_rejection=last['decision'],transport_or_interface_diagnostic=read(call_folder/'result.json'))
        success=False
        for attempt in range(max_iterations):
            version=folder/f'v{ordinal}';ordinal+=1
            call,candidate=llm.call(version/'model_call',current,obligations[0],feedback,'core_fresh_progressive')
            after=loop.replay(candidate,version/'native',selected) if candidate else None
            decision=dict(accepted=False,gate_enforced=True,reasons=[dict(kind='model_or_interface_failure')])
            if after and after.get('group'):
                gate=loop.decide(before['group']['ledger'],after['group']['ledger'],targets)
                dump(version/'historical_gate_audit.json',gate)
                decision.update(accepted=bool(gate['accepted'] and after['healthy']),reasons=gate['reasons'])
                if not after['healthy']:decision['reasons'].append(dict(kind='native_or_control_or_sampling_unknown'))
            elif after:decision['reasons']=[dict(kind='native_compile_failed')]
            dump(version/'decision.json',decision)
            record=dict(iteration=ordinal-1,requested_obligations=obligations,coverage_only=coverage_only,
                call=call,decision=decision,before=before['counts'],after=after.get('counts') if after else None,
                target_keys=targets)
            history.append(record);dump(folder/'history.json',history)
            print('REFINE20',obligations,ordinal-1,decision,flush=True)
            if decision['accepted']:
                current=candidate;before=after;success=True;break
            feedback.update(previous_rejected_proposal=base.structured(candidate),actual_rejection=decision,
                transport_or_interface_diagnostic=call,accepted_version_retained=base.structured(current))
            if after and after.get('feedback'):feedback['actual_native_evidence']=after['feedback']
        stages.append(dict(obligations=obligations,status='accepted_observed_repair' if success else 'unresolved',
            coverage_only=coverage_only,target_keys=targets))
    loop.freeze(folder,current,'final_accepted_progressive_set')
    result=dict(resolved=all(s['status']!='unresolved' for s in stages),has_acquired_gap=bool(witnesses),
        history=history,stages=stages,before=origin['counts'],after=before['counts'],
        frozen_hash=loop.sha(current),scope='Finite development evidence only. Coverage-only acceptance is not demonstrated target detection.')
    dump(folder/'summary.json',result)
    return current,result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--seed',type=int,default=20261018)
    parser.add_argument('--iterations',type=int,default=2)
    parser.add_argument('--stall-fault',action='store_true',help='Include explicitly artificial stalled-output data mutation and its independently checked cases.')
    parser.add_argument('--direct-property',action='store_true',help='Model emits a whole native property instead of split expression fields.')
    parser.add_argument('--backend',choices=('ollama','configured-qwen-relay'),default='ollama',help='Reuse the existing local model or Qwen relay configuration from run_final46_model.ps1.')
    parser.add_argument('--max-model-calls',type=int,default=8,help='Bound physical generation requests in this run (1..8).')
    parser.add_argument('--source-core',type=Path,help='Reuse an immutable accepted core set from a terminal run; this is not fresh initial generation.')
    parser.add_argument('--only-stage',choices=('drain','reset','stall'),help='Optional targeted continuation on a remaining obligation group.')
    args=parser.parse_args()
    assert 1<=args.iterations<=3
    assert 1<=args.max_model_calls<=8
    assert not args.only_stage or args.source_core,'targeted_stage_requires_auditable_source'
    stages_to_run=({'drain':(STAGES[0],),'reset':(STAGES[1],),'stall':(STAGES[2],)}[args.only_stage]
        if args.only_stage else STAGES)
    out=args.out.resolve();assert ROOT in out.parents
    stall_extension=None
    if args.stall_fault:
        import research20_stall_runtime as stall_extension
        stall_extension.install()
    loop.CONFIG.update(expression_format='text',preflight_tokens=True,max_model_calls=args.max_model_calls,
        max_tokens=240000,max_wall_seconds=7200,call_timeout=900,max_refinement_calls=args.iterations)
    loop.CONFIG['direct_property']=args.direct_property
    loop.CONFIG['options'].update(seed=args.seed,temperature=0,num_predict=1024)
    loop.CONFIG['backend']=args.backend
    if args.backend=='configured-qwen-relay':
        loop.CONFIG.update(model='qwen/qwen-2.5-72b-instruct',remote_model='qwen/qwen-2.5-72b-instruct',
            remote_url='https://api.highwayapi.ai/openai/chat/completions',
            key_file=str(ROOT/'.secrets/qwen_api_key.txt'),preflight_tokens=False,call_timeout=180,
            remote_configuration_source='scripts/run_final46_model.ps1')
    loop.prepare(out)
    for name in ('research20_model.py','research20_loop.py','research20_cases.py','research19_feedback.py','research18_context_budget.py'):
        shutil.copy2(ROOT/'scripts'/name,out/'source_snapshot'/name)
    if stall_extension:
        shutil.copy2(ROOT/'scripts/research20_stall_runtime.py',out/'source_snapshot/research20_stall_runtime.py')
    if args.backend=='configured-qwen-relay':
        shutil.copy2(ROOT/'scripts/research20_remote.py',out/'source_snapshot/research20_remote.py')
    dump(out/'source_snapshot/hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'source_snapshot').glob('*.py')})
    selected=cases()+(stall_extension.extra_cases() if stall_extension else [])
    dump(out/'development_plan.json',selected)
    protocol=read(out/'protocol.json')
    protocol.update(core='Fresh real initial generation and fresh progressive edits on independently checked development evidence. No archived response replay.',
        schema='JSON mode, model-selected whole property or split expressions (config.direct_property) and optional multiple obligation labels. No expression substitution; labels alone never establish detection.',
        stages=stages_to_run,arms=None,ablation='Not conducted in this priority run.',
        independent='One fresh common batch only after final freeze; no modification after outcomes. Old research19 tests are development.',
        old_tests='All previous tests, including research19, are development. New seeds materialize only after model work stops.',
        witness_selection='Prospective contract-guided families across two parameter sets; independent ledger validates actual misses. No baseline comparison claim.',
        native_profile='qualified_sampled_multi_v2; same property execution, opt-in multiple model-declared obligation labels.')
    protocol['stall_fault']=dict(enabled=args.stall_fault,scope='Explicit artificial output boundary mutation. Same original FIFO protocol, no historical defect claim; never substitutes for native RTL execution.')
    if args.source_core:
        protocol['core']='Continuation of the named frozen accepted set with fresh real edits. Source initial generation/earlier edits are reused, never counted as new calls. Prior independent outcomes were not read.'
    dump(out/'protocol.json',protocol)
    dump(out/'execution.command.json',dict(cwd=str(ROOT),command=f'wsl -- python3 scripts/research20_loop.py --out {out.relative_to(ROOT).as_posix()} --seed {args.seed} --iterations {args.iterations} --max-model-calls {args.max_model_calls}'+(' --stall-fault' if args.stall_fault else '')+(' --direct-property' if args.direct_property else '')+(' --backend '+args.backend if args.backend!='ollama' else '')+(' --source-core '+args.source_core.as_posix() if args.source_core else '')+(' --only-stage '+args.only_stage if args.only_stage else ''),reproduction='Use a fresh output directory. No guarantee identical model output.'))
    llm=None;outcome=dict(status='running');dump(out/'outcome.json',outcome)
    try:
        if args.backend=='configured-qwen-relay':
            from research20_remote import RemoteModel
            llm=RemoteModel(out,loop.CONFIG)
        else:
            import research15_native_models as service
            service.OUT=out;service.service()
            llm=Model(out,loop.CONFIG)
        if args.source_core:
            source=args.source_core.resolve()
            assert ROOT in source.parents and read(source/'outcome.json')['status']!='running'
            candidate=read(source/'core/frozen_candidate.json')
            stamp=read(source/'core/freeze.json')
            assert loop.sha(candidate)==stamp['candidate_sha256'],'source_freeze_mismatch'
            dump(out/'shared_initial.json',candidate)
            dump(out/'shared_initial_freeze.json',dict(hash=loop.sha(candidate),origin=str(source/'core'),
                model_selected=True,reused_accepted_set=True))
            dump(out/'reused_core_source.json',dict(source=str(source),source_freeze=stamp,
                source_initial_freeze=read(source/'shared_initial_freeze.json'),
                files={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in source.rglob('*') if p.is_file() and (p.name in ('model_edit.json','candidate.json','result.json','response.assembled.json','response.events.jsonl','response.stream.raw','request.json','decision.json','freeze.json','frozen_candidate.json','history.json','summary.json')) and 'core_independent' not in p.parts and 'report' not in p.parts},
                usage='All source calls charged in source run only. No source independent data used.'))
        else:
            candidate=loop.initial(out,llm)
        if candidate is None:outcome=dict(status='initial_unqualified');return
        candidate,core=refine(out,llm,candidate,selected,args.iterations,stages_to_run)
        outcome=dict(status='development_resolved' if core['resolved'] else 'development_partial',core=core)
        loop.holdout(out/'core_independent',{'core':candidate,'initial':read(out/'shared_initial.json')})
        outcome['independent_executed']=True
    except Exception as exc:
        outcome.update(status='execution_blocked',error=repr(exc));raise
    finally:
        dump(out/'outcome.json',outcome)
        calls=llm.calls if llm else []
        dump(out/'model_cost.json',dict(calls=len(calls),prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),
            completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls),formal_calls=0))
        if stall_extension:stall_extension.uninstall()


if __name__=='__main__':main()
