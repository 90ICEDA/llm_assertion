"""Bounded genuine boundary refinement; all holdout generation follows freeze."""
import argparse
import copy
import hashlib
import os
from pathlib import Path
import secrets
import shutil

import research17_loop as loop
import research17_model as base
import research20_stall_runtime as extension
from research21_model import Model
from research21_cases import cases, independent_cases

ROOT=loop.ROOT
dump,read=loop.dump,loop.read
STAGES=(('stall_stability',),('no_unsolicited_output','reset_cancellation'))


def refine(out,llm,initial,selected,iterations,feedback_run=None,stages_to_run=STAGES,qualified_before=None):
    folder=out/'core';current=copy.deepcopy(initial)
    if qualified_before is None:
        before=loop.replay(current,folder/'before',selected)
    else:
        # Reuse a physically executed preparation baseline, with exact input
        # and candidate binding; never count its commands as new executions.
        assert qualified_before['candidate_hash']==loop.sha(initial)
        assert qualified_before['cases_hash']==loop.sha(selected)
        source=Path(qualified_before['result_path'])
        assert hashlib.sha256(source.read_bytes()).hexdigest()==qualified_before['result_sha256']
        before=read(source)
        dump(folder/'baseline_reuse.json',qualified_before)
    if not before['healthy'] or not before.get('group'):
        raise RuntimeError('initial_development_replay_unhealthy')
    origin=before;info=loop.inspect(before['group']['ledger'])
    witnesses=[info['rows'][k] for k in sorted(info['misses'])]
    dump(out/'search/admitted_cases.json',selected)
    dump(out/'search/validated_missing_evidence.json',dict(witnesses=witnesses,
        scope='Independent transaction oracle and same legal inputs on native paired RTL. Only attributable first violations qualify.',
        dedup='Obligation and fault mechanism; parameter/seed/waveform variants are replications.'))
    history=[];stages=[];ordinal=0;exhausted=None
    for obligations in stages_to_run:
        info=loop.inspect(before['group']['ledger'])
        targets=sorted(k for k in info['misses']|info['false_positives'] if info['rows'][k]['obligation'] in obligations)
        if not targets:
            stages.append(dict(obligations=obligations,status='no_unresolved_observed_gap',target_keys=[]));continue
        feedback=dict(requested_obligations=obligations,current_gap_ids=targets,counts=before['counts'],actual_native_evidence=before['feedback'])
        if feedback_run:
            earlier=[h for h in read(feedback_run/'core/history.json') if not h['decision']['accepted'] and set(h['requested_obligations']) & set(obligations)]
            if earlier:
                old=feedback_run/'core'/f"v{earlier[-1]['iteration']}"
                proposal_path=old/'model_call/model_edit.json'
                feedback.update(previous_rejected_proposal=read(proposal_path) if proposal_path.exists() else None,
                    actual_rejection=earlier[-1]['decision'],transport_or_interface_diagnostic=read(old/'model_call/result.json'))
                dump(out/'feedback_inheritance'/f'{obligations[0]}.json',dict(source=str(old),
                    files={str(p.relative_to(old)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                        (old/'model_call/model_edit.json',old/'model_call/response.raw.json',old/'model_call/result.json',old/'decision.json') if p.is_file()},
                    parsed_proposal_available=proposal_path.is_file(),
                    scope='Actual rejected development edit only; its predicates remain rejected and current samples come from this run.'))
        success=False
        for attempt in range(iterations):
            if exhausted:break
            version=folder/f'v{ordinal}';ordinal+=1
            try:
                call,candidate=llm.call(version/'model_call',current,obligations[0],feedback,'core_fresh_boundary_repair')
            except RuntimeError as exc:
                if str(exc) not in ('configured_model_budget_exhausted','insufficient_remaining_conservative_remote_token_budget','configured_wall_budget_exhausted'):raise
                exhausted=str(exc);dump(folder/'budget_stop.json',dict(reason=exhausted,physical_calls=len(llm.calls)));break
            after=loop.replay(candidate,version/'native',selected) if candidate else None
            decision=dict(accepted=False,gate_enforced=True,reasons=[dict(kind='model_or_interface_failure')])
            if candidate is None and call.get('proposal_rejection'):
                # A parsed but unchanged/repeated edit is not a transport or
                # native-tool failure. Keep the concrete pre-execution reason.
                decision['reasons']=[call['proposal_rejection']]
            if after and after.get('group'):
                gate=loop.decide(before['group']['ledger'],after['group']['ledger'],targets)
                dump(version/'historical_gate_audit.json',gate)
                decision.update(accepted=bool(gate['accepted'] and after['healthy']),reasons=gate['reasons'])
                if not after['healthy']:decision['reasons'].append(dict(kind='native_or_control_or_sampling_unknown'))
            elif after:decision['reasons']=[dict(kind='native_compile_failed')]
            dump(version/'decision.json',decision)
            history.append(dict(iteration=ordinal-1,requested_obligations=obligations,coverage_only=False,call=call,decision=decision,
                before=before['counts'],after=after.get('counts') if after else None,target_keys=targets))
            dump(folder/'history.json',history)
            print('REFINE21',obligations,ordinal-1,dict(accepted=decision['accepted'],
                reason_counts=[dict(kind=r['kind'],evidence_count=len(r.get('evidence_keys',[]))) for r in decision['reasons']],
                full_decision=str(version/'decision.json')),flush=True)
            if decision['accepted']:
                current=candidate;before=after;success=True;break
            proposal=version/'model_call/model_edit.json'
            feedback.update(previous_rejected_proposal=read(proposal) if proposal.exists() else None,
                actual_rejection=decision,transport_or_interface_diagnostic=call,accepted_version_retained=base.structured(current))
            # Failed interface edits have no native evidence; preserve the
            # previous source rather than erasing it with an empty projection.
            if after and after.get('feedback'):feedback['actual_native_evidence']=after['feedback']
        stages.append(dict(obligations=obligations,status='accepted_observed_repair' if success else 'unresolved',coverage_only=False,target_keys=targets))
    loop.freeze(folder,current,'final_accepted_boundary_set_before_new_independent_generation')
    result=dict(resolved=all(s['status']!='unresolved' for s in stages),has_acquired_gap=bool(witnesses),history=history,stages=stages,
        before=origin['counts'],after=before['counts'],frozen_hash=loop.sha(current),budget_stop=exhausted,
        scope='Finite development evidence; historical gate is not a global non-regression proof.')
    dump(folder/'summary.json',result)
    return current,result


def holdout(folder,candidates):
    folder.mkdir(parents=True,exist_ok=False)
    seed=secrets.randbelow(2**31)
    selected=independent_cases(seed)
    dump(folder/'split.json',dict(created_after_freeze=True,seeds=[dict(seed=seed,family='boundary_and_random')],
        parameters=[dict(depth=4,pipeline=2),dict(depth=8,pipeline=2)],hashes={name:loop.sha(c) for name,c in candidates.items()},
        usage='independent_test_no_feedback_no_selection',cases=selected))
    summaries={}
    for name,candidate in candidates.items():
        result=loop.replay(candidate,folder/name,selected)
        if result['group']:
            for row in result['group']['ledger']:row['split']='independent_test'
            dump(folder/name/'independent_ledger.json',result['group'])
            info=loop.inspect(result['group']['ledger'])
            by_obligation={o:{k:sum(info['rows'][key]['obligation']==o for key in info[k]) for k in ('detections','misses','unknown','false_positives','triggers')} for o in base.SPECS}
        else:by_obligation={}
        summaries[name]=dict(counts=result.get('counts'),by_obligation=by_obligation,healthy=result['healthy'])
    dump(folder/'summary.json',summaries)
    return summaries


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--source-core',type=Path,default=ROOT/'deliverables/research20_closed_loop_20261018_r06')
    parser.add_argument('--seed',type=int,default=2026101821)
    parser.add_argument('--iterations',type=int,default=4)
    parser.add_argument('--max-model-calls',type=int,default=8)
    parser.add_argument('--feedback-run',type=Path,help='Terminal prior development run containing real rejected proposals; no independent files are read.')
    parser.add_argument('--first-stage',choices=('stall','reset'),default='stall')
    parser.add_argument('--compact-feedback',action='store_true',help='Exact RTL and two real adjacent observations without repeated diagnostic dumps.')
    parser.add_argument('--local-model',action='store_true',help='Use existing local Qwen service; no remote generation requests.')
    parser.add_argument('--local-model-name',default='qwen2.5-coder:7b-instruct',choices=('qwen2.5-coder:7b-instruct','deepseek-coder:6.7b-instruct'),help='Installed local model; changing it is not a controlled mechanism comparison.')
    parser.add_argument('--local-kv-cache-type',choices=('f16','q8_0','q4_0'),default='f16',help='Non-default KV cache requires a newly owned local server; actual support must be checked in its log.')
    parser.add_argument('--structured-local',action='store_true',help='Enforce edit JSON schema on the local model; predicates remain unconstrained strings.')
    parser.add_argument('--lexical-local',action='store_true',help='Constrain local property tokens to declared signals/functions; no property answer is supplied.')
    parser.add_argument('--local-service-log',type=Path,help='Owned Ollama log for per-call grammar-support auditing.')
    parser.add_argument('--boundary-replace',action='store_true',help='Let the model replace one property while retaining the other accepted properties.')
    parser.add_argument('--promote-run',type=Path,action='append',default=[],help='Completed public test batch explicitly promoted to development; repeat for multiple batches.')
    parser.add_argument('--fresh-obligation',action='store_true',help='Synthesize the selected obligation afresh without prior predicate text; strict native gate unchanged.')
    parser.add_argument('--free-local-property',action='store_true',help='Fresh synthesis with a free property string instead of lexical-token grammar; native validation unchanged.')
    args=parser.parse_args()
    assert not args.structured_local or (args.local_model and args.compact_feedback)
    assert not args.lexical_local or args.structured_local
    assert not args.lexical_local or args.local_service_log
    assert not args.boundary_replace or (args.compact_feedback and (not args.local_model or args.lexical_local))
    assert not args.fresh_obligation or args.boundary_replace
    assert not args.free_local_property or args.fresh_obligation
    assert args.local_kv_cache_type=='f16' or args.local_model
    if args.local_service_log:
        assert ROOT in args.local_service_log.resolve().parents and args.local_service_log.is_file()
    assert 1<=args.iterations<=4 and 1<=args.max_model_calls<=8
    stages_to_run=STAGES if args.first_stage=='stall' else tuple(reversed(STAGES))
    out=args.out.resolve();source=args.source_core.resolve()
    assert ROOT in out.parents and ROOT in source.parents
    feedback_run=args.feedback_run.resolve() if args.feedback_run else None
    if feedback_run:
        assert ROOT in feedback_run.parents and read(feedback_run/'outcome.json')['status']!='running'
    extension.install()
    loop.CONFIG.update(expression_format='text',direct_property=True,preflight_tokens=False,max_model_calls=args.max_model_calls,
        max_tokens=240000,max_wall_seconds=7200,call_timeout=180,max_refinement_calls=args.iterations,
        model='qwen/qwen-2.5-72b-instruct',remote_model='qwen/qwen-2.5-72b-instruct',
        remote_url='https://api.highwayapi.ai/openai/chat/completions',key_file=str(ROOT/'.secrets/qwen_api_key.txt'),
        backend='configured-qwen-relay',remote_configuration_source='scripts/run_final46_model.ps1')
    loop.CONFIG['options'].update(seed=args.seed,temperature=0,num_predict=1024)
    loop.CONFIG['fresh_unconstrained_property']=args.free_local_property
    if args.local_model:
        assert args.compact_feedback,'local experiment uses qualified compact presentation'
        loop.CONFIG.update(model=args.local_model_name,backend='ollama',preflight_tokens=True,call_timeout=900)
        for k in ('remote_model','remote_url','key_file','remote_configuration_source'):loop.CONFIG.pop(k,None)
        if args.local_service_log:loop.CONFIG['local_service_log']=str(args.local_service_log.resolve())
    loop.prepare(out)
    for name in ('research19_feedback.py','research20_model.py','research20_remote.py','research20_cases.py','research20_stall_runtime.py',
                 'research21_model.py','research21_loop.py','research21_cases.py'):
        shutil.copy2(ROOT/'scripts'/name,out/'source_snapshot'/name)
    if args.compact_feedback:
        shutil.copy2(ROOT/'scripts/research22_model.py',out/'source_snapshot/research22_model.py')
    if args.structured_local:
        shutil.copy2(ROOT/'scripts/research23_model.py',out/'source_snapshot/research23_model.py')
    if args.lexical_local:
        shutil.copy2(ROOT/'scripts/research24_model.py',out/'source_snapshot/research24_model.py')
    if args.boundary_replace:
        shutil.copy2(ROOT/'scripts/research26_model.py',out/'source_snapshot/research26_model.py')
        for name in ('research23_model.py','research24_model.py'):
            shutil.copy2(ROOT/'scripts'/name,out/'source_snapshot'/name)
    if args.promote_run:
        shutil.copy2(ROOT/'scripts/research26_cases.py',out/'source_snapshot/research26_cases.py')
    if args.fresh_obligation:
        shutil.copy2(ROOT/'scripts/research27_model.py',out/'source_snapshot/research27_model.py')
    dump(out/'source_snapshot/hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'source_snapshot').glob('*.py')})
    protocol=read(out/'protocol.json')
    protocol.update(core='Fresh real edits of a previously frozen model-generated set; no new initial-generation claim.',
        stages=stages_to_run,arms=None,ablation='Not conducted in this focused boundary repair.',
        old_tests='All public research20 tests are development; selected release cases explicitly promoted.',
        independent='New seed and inputs materialized only after all model work ends and final set freezes; no feedback or selection.',
        witness_selection='Contract-guided release boundaries and cancelled zero-payload transactions; no baseline superiority claim.',
        stall_fault=dict(enabled=True,scope='Artificial output boundary mutation on native axis_fifo, not a historical upstream fix.'),
        schema='Unchanged research20 assembler: exact model-owned predicates, at most five properties, native sampled execution.')
    protocol['compact_feedback']=args.compact_feedback
    protocol['structured_local']=args.structured_local
    protocol['lexical_local']=args.lexical_local
    protocol['boundary_replace']=args.boundary_replace
    protocol['promoted_test_runs']=[str(p.resolve()) for p in args.promote_run]
    protocol['fresh_obligation']=args.fresh_obligation
    protocol['free_local_property']=args.free_local_property
    protocol['requested_local_kv_cache_type']=args.local_kv_cache_type
    if args.boundary_replace:
        protocol['schema']='research26_model.replace_one: model selects one existing assertion ID and its full new predicate; all other predicates retained, maximum five properties, full native replay.'
    if args.promote_run:
        protocol['old_tests']+=' Entire named completed test batch explicitly promoted to development with source hashes and unchanged rows.'
    dump(out/'protocol.json',protocol)
    dump(out/'execution.command.json',dict(cwd=str(ROOT),command=f'wsl -- python3 scripts/research21_loop.py --out {out.relative_to(ROOT).as_posix()} --source-core {source.relative_to(ROOT).as_posix()} --seed {args.seed} --iterations {args.iterations} --max-model-calls {args.max_model_calls} --first-stage {args.first_stage}'+(' --feedback-run '+feedback_run.relative_to(ROOT).as_posix() if feedback_run else ''),reproduction='Fresh output directory required; model outputs may differ.'))
    if args.compact_feedback:
        command=read(out/'execution.command.json');command['command']+=' --compact-feedback';dump(out/'execution.command.json',command)
    if args.local_model:
        command=read(out/'execution.command.json');command['command']+=' --local-model';dump(out/'execution.command.json',command)
        if args.local_model_name!='qwen2.5-coder:7b-instruct':
            command=read(out/'execution.command.json');command['command']+=' --local-model-name '+args.local_model_name;dump(out/'execution.command.json',command)
        if args.local_kv_cache_type!='f16':
            command=read(out/'execution.command.json');command['command']+=' --local-kv-cache-type '+args.local_kv_cache_type;dump(out/'execution.command.json',command)
    if args.structured_local:
        command=read(out/'execution.command.json');command['command']+=' --structured-local';dump(out/'execution.command.json',command)
    if args.lexical_local:
        command=read(out/'execution.command.json');command['command']+=' --lexical-local';dump(out/'execution.command.json',command)
    if args.local_service_log:
        command=read(out/'execution.command.json');command['command']+=' --local-service-log '+args.local_service_log.as_posix();dump(out/'execution.command.json',command)
    if args.boundary_replace:
        command=read(out/'execution.command.json');command['command']+=' --boundary-replace';dump(out/'execution.command.json',command)
    for promoted in args.promote_run:
        command=read(out/'execution.command.json');command['command']+=' --promote-run '+promoted.as_posix();dump(out/'execution.command.json',command)
    if args.fresh_obligation:
        command=read(out/'execution.command.json');command['command']+=' --fresh-obligation';dump(out/'execution.command.json',command)
    if args.free_local_property:
        command=read(out/'execution.command.json');command['command']+=' --free-local-property';dump(out/'execution.command.json',command)
    llm=None;outcome=dict(status='running');dump(out/'outcome.json',outcome)
    try:
        assert read(source/'outcome.json')['status']!='running'
        candidate=read(source/'core/frozen_candidate.json');stamp=read(source/'core/freeze.json')
        assert loop.sha(candidate)==stamp['candidate_sha256']
        dump(out/'shared_initial.json',candidate)
        dump(out/'shared_initial_freeze.json',dict(hash=loop.sha(candidate),origin=str(source/'core'),model_selected=True,reused_accepted_set=True))
        dump(out/'reused_core_source.json',dict(source=str(source),source_freeze=stamp,source_initial_freeze=read(source/'shared_initial_freeze.json'),
            files={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()
                and p.name in ('model_edit.json','candidate.json','result.json','response.assembled.json','response.events.jsonl','response.stream.raw','request.json','decision.json','freeze.json','frozen_candidate.json','history.json','summary.json')
                and 'core_independent' not in p.parts and 'report' not in p.parts},
            usage='Source calls charged only to source. Public source independent release cases are now development, explicitly in development_plan provenance.'))
        selected=cases()
        for promoted in args.promote_run:
            from research26_cases import promoted_cases
            selected+=promoted_cases(promoted)
        assert len({c['id'] for c in selected})==len(selected),'duplicate_development_case'
        dump(out/'development_plan.json',selected)
        if args.local_model:
            import research15_native_models as service
            service.OUT=out
            service_env=None
            if args.local_kv_cache_type!='f16':
                overrides=dict(OLLAMA_FLASH_ATTENTION='true',OLLAMA_KV_CACHE_TYPE=args.local_kv_cache_type)
                service_env={**os.environ,**overrides}
                dump(out/'requested_service_overrides.json',overrides)
            service.service(env=service_env)
            if args.lexical_local and (out/'service/process.json').is_file():
                loop.CONFIG['local_service_log']=str(out/'service/server.log')
            if args.lexical_local:
                dump(out/'local_service_binding.json',dict(
                    requested_log=str(args.local_service_log.resolve()),
                    effective_log=loop.CONFIG['local_service_log'],
                    started_owned_service=(out/'service/process.json').is_file()))
                protocol['config']['local_service_log']=loop.CONFIG['local_service_log']
                dump(out/'protocol.json',protocol)
            from research22_model import LocalModel as SelectedModel
            if args.structured_local:
                from research23_model import Model as SelectedModel
            if args.lexical_local:
                from research24_model import Model as SelectedModel
            if args.boundary_replace:
                from research26_model import Model as SelectedModel
            if args.fresh_obligation:
                from research27_model import Model as SelectedModel
        elif args.boundary_replace:
            from research26_model import RemoteModel as SelectedModel
            if args.fresh_obligation:
                from research27_model import RemoteModel as SelectedModel
        elif args.compact_feedback:
            from research22_model import Model as SelectedModel
        else:SelectedModel=Model
        llm=SelectedModel(out,loop.CONFIG)
        candidate,core=refine(out,llm,candidate,selected,args.iterations,feedback_run,stages_to_run)
        outcome=dict(status='development_resolved' if core['resolved'] else 'development_partial',core=core)
        holdout(out/'core_independent',{'core':candidate,'initial':read(out/'shared_initial.json')})
        outcome['independent_executed']=True
    except KeyboardInterrupt:
        outcome.update(status='operator_stopped_before_completion',reason='KeyboardInterrupt; no uncompleted replay or freeze is claimed');raise
    except Exception as exc:
        outcome.update(status='execution_blocked',error=repr(exc));raise
    finally:
        dump(out/'outcome.json',outcome)
        calls=llm.calls if llm else []
        dump(out/'model_cost.json',dict(calls=len(calls),prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),
            completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),
            usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls),formal_calls=0))
        extension.uninstall()


if __name__=='__main__':main()
