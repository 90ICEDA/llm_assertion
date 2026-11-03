"""Fresh real generation/search/refinement; common holdout after all freezes."""
import argparse
import hashlib
from pathlib import Path
import shutil
import research17_loop as loop
from research19_model import Model

ROOT=loop.ROOT
dump=loop.dump


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--model',default='qwen2.5-coder:7b-instruct')
    parser.add_argument('--contract-planning',action='store_true')
    parser.add_argument('--native-profile',action='store_true')
    parser.add_argument('--source',type=Path,help='Reuse a qualified actual initial and strictly validated search; no initial call is copied as new cost.')
    parser.add_argument('--retry-interface-edits',action='store_true',help='Chronologically replay actual interface-rejected source core responses under qualified frontend before requesting a new edit.')
    parser.add_argument('--max-refinement-calls',type=int,default=2)
    parser.add_argument('--max-model-calls',type=int,default=12)
    args=parser.parse_args()
    out=args.out.resolve()
    if ROOT not in out.parents:raise ValueError('Workspace output required')
    if not 1<=args.max_refinement_calls<=4 or not 1<=args.max_model_calls<=24:raise ValueError('bounded budgets required')
    if args.retry_interface_edits and not (args.source and args.native_profile):raise ValueError('Interface retry requires source and qualified native profile')
    loop.CONFIG.update(model=args.model,expression_format='text',preflight_tokens=True,
        max_refinement_calls=args.max_refinement_calls,max_model_calls=args.max_model_calls,
        max_tokens=480000,max_wall_seconds=14400,contract_planning=args.contract_planning,native_profile=args.native_profile)
    loop.CONFIG['options'].update(seed=20261019,temperature=0.2,num_predict=768)
    loop.prepare(out)
    for name in ('research19_loop.py','research19_model.py','research19_feedback.py','research18_context_budget.py'):
        shutil.copy2(ROOT/'scripts'/name,out/'source_snapshot'/name)
    dump(out/'source_snapshot/hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'source_snapshot').glob('*.py')})
    protocol=loop.read(out/'protocol.json')
    protocol.update(fresh_initial_call=True,interface='reason-first text expressions, model-owned predicates; target-first real paired samples',
        ablation=f'After core repair only; A/B/C/D start from the same initial candidate and model configuration, each at most {args.max_refinement_calls} refinement calls. A/C have common evidence only; B/D receive acquired search evidence. Core pilot charged separately.',
        old_tests='All research16/17/18 data are development. No old independent generalization claim. Fresh secrets-generated holdout only after all model operations and freezes.',
        independent='One fresh common batch after core and all executed arms freeze; no independent outcomes are read while model work continues.',
        change_scope='Model presentation and sampling changed from research18; no causal comparison across those runs. Same configuration and initial candidate within all four arms.',
        core='Fresh real order_payload candidate, new native search, bounded refinement; partial initial candidate explicitly prescribed, not spontaneous whole-spec generation.',
        schema='Generic reason-first text schema. Every expression is model-generated and strictly assembled without semantic rewrite.')
    protocol['contract_planning']=dict(enabled=args.contract_planning,
        scope='Separate actual model call on specification/signals/development samples, followed by full-RTL SVA generation. Draft never accepted or executed directly. Same option for all arms.',
        accounting='Planning and final generation both count against model-call/token budgets; all calls and raw responses saved.')
    protocol['native_profile']=dict(enabled=args.native_profile,name='qualified_sampled_v1' if args.native_profile else 'legacy',
        qualification='deliverables/research19_native_qualification_20261016_r01/qualification.json',
        scope='Qualified Boolean OR and $rose/$past antecedent native assert/cover; no property semantics rewritten.')
    protocol['retry_interface_edits']=dict(enabled=args.retry_interface_edits,
        policy='Source core interface-rejected real responses in chronological order, without viewing independent tests or altering expressions. Replay/acceptance happens again under upgraded syntax profile; original generation cost stays in source.',
        ablation='Pending responses are available only to the separate core pilot. Each arm starts initial and makes its own model calls, without pilot proposals.')
    if args.source:
        source=args.source.resolve()
        if ROOT not in source.parents or loop.read(source/'outcome.json')['status']=='running':raise ValueError('Terminal workspace source required')
        candidate=loop.read(source/'shared_initial.json')
        stamp=loop.read(source/'shared_initial_freeze.json')
        if loop.sha(candidate)!=stamp['hash']:raise ValueError('Initial hash mismatch')
        origin=Path(stamp['origin'])
        if source not in origin.resolve().parents or not loop.read(origin.parent/'decision.json')['qualified']:raise ValueError('Unqualified initial source')
        from research17_search_audit import validate_witness
        records=loop.read(source/'search/results.json')
        cases=loop.read(source/'search/admitted_cases.json')
        for case in cases:
            record=next(r for r in records if r['folder']==case['source_query'])
            evidence=next(e for e in record['evidence']['mapping'] if e['variant']==case['mode'] and e['obligation']=='drain_no_loss' and e['kind']=='false_negative')
            assert validate_witness(source/'search',dict(scenario_id=case['source_query'],mode=case['mode'],first_violation=evidence))['valid']
        for name in ('shared_initial.json','shared_initial_freeze.json'):
            shutil.copy2(source/name,out/name)
        for name in ('admitted_cases.json','strict_witnesses.json','corrected_comparison.json'):
            dump(out/'search'/name,loop.read(source/'search'/name))
        # Hash exact reused inputs, without consuming any source independent outcomes.
        inputs=[source/'shared_initial.json',source/'shared_initial_freeze.json',source/'axis_fifo.v',
            origin/'request.json',origin/'response.raw.json',origin/'candidate.json',origin.parent/'decision.json',
            *[source/'search'/n for n in ('admitted_cases.json','strict_witnesses.json','corrected_comparison.json','results.json')]]
        dump(out/'reused_source.json',dict(source=str(source),source_files={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
            accounting='Initial generation/search already occurred in source. New run charges only new calls/replays; source costs reported separately after all experiments end.',
            independent='Source independent outcomes not consumed; new holdout after all current freezes.'))
        protocol.update(fresh_initial_call=False,continuation_source=str(source),
            core='Reuse actual qualified initial and search with checked hashes; new real model planning/generation and native replay under declared qualified syntax profile.')
    dump(out/'protocol.json',protocol)
    outcome=dict(status='running');dump(out/'outcome.json',outcome)
    llm=None
    try:
        import research15_native_models as local_service
        local_service.OUT=out
        local_service.service()
        llm=Model(out,loop.CONFIG)
        if args.retry_interface_edits:
            llm.pending_edits=[p.parent for p in sorted((source/'core').glob('v*/model_call/result.json'))
                if loop.read(p).get('status')=='response_received' and loop.read(p).get('candidate_status')=='interface_rejected'
                and (p.parent/'model_edit.json').is_file() and not (p.parent.parent/'native').exists()]
            dump(out/'pending_interface_edits.json',dict(source=str(source),paths=[str(p) for p in llm.pending_edits],
                policy='All eligible responses, chronological; no manual assertion substitution'))
        candidate=candidate if args.source else loop.initial(out,llm)
        if candidate is None:
            outcome=dict(status='initial_unqualified');return
        cases=cases if args.source else loop.acquire(out)
        if not cases:
            outcome=dict(status='no_strict_search_witness');return
        core=loop.refine(out/'core',llm,candidate,[loop.common_case()]+cases,True,'core_both_mechanisms')
        outcome=dict(status='core_resolved' if core['resolved'] else 'core_unresolved',core=core)
        frozen={'core':loop.read(out/'core/frozen_candidate.json')}
        if core['resolved']:
            arms={}
            for name,cfg in loop.ARMS.items():
                arms[name]=loop.refine(out/'arms'/name,llm,candidate,
                    [loop.common_case()]+(cases if cfg['search'] else []),cfg['gate'],'ablation_'+name)
                frozen[name]=loop.read(out/'arms'/name/'frozen_candidate.json')
            dump(out/'all_arms_freeze.json',{name:loop.sha(c) for name,c in frozen.items() if name!='core'})
            outcome.update(status='core_and_four_arms_executed',arms=arms)
        loop.holdout(out/'core_independent',frozen)
    except KeyboardInterrupt:
        outcome.update(status='interrupted',reason='cancelled; unfinished generation usage unavailable');raise
    except Exception as exc:
        outcome.update(status='execution_blocked',error=repr(exc));raise
    finally:
        dump(out/'outcome.json',outcome)
        calls=llm.calls if llm else []
        dump(out/'model_cost.json',dict(calls=len(calls),prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),
            completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),
            usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls),formal_calls=0,
            accounting='Completed upper-layer calls; report audits physical attempts including interruptions separately.'))


if __name__=='__main__':main()
