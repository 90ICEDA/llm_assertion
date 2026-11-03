"""Continue interrupted genuine-model FIFO study in a new immutable run.

Reuses the archived initial generation and search, explicitly charges their
historical costs separately. No response is synthesized or silently retried.
"""
import argparse
import copy
import hashlib
from pathlib import Path
import shutil

import research17_loop as loop
import research17_model as model
from research17_search_audit import validate_witness, audit_search
from research17_report import artifacts, cost_audit

ROOT=loop.ROOT
dump=model.dump;read=model.read


def compact_feedback(value):
    """Bound actual observations without substituting suggested predicates."""
    if isinstance(value,list):return [compact_feedback(v) for v in value]
    if not isinstance(value,dict):return value
    result={}
    for key,val in value.items():
        if key in ('artifacts','coverage','associated_transactions','initial_feedback','sampling_contract','sampling','scope','property','validator'):continue
        if key in ('evidence_id','before_sha256','after_sha256'):continue
        if key in ('evidence_keys','current_gap_ids','trigger_cycles','failure_cycles') and isinstance(val,list):
            result[key+'_count']=len(val)
        elif key=='samples' and isinstance(val,list) and 'center_cycle' in value:
            # Keep the actual antecedent/prior sample and the observation edge;
            # full traces remain archived. No signal values are synthesized.
            center=value['center_cycle']
            result[key]=[v for v in val if center-1<=v.get('cycle',-999)<=center]
            result['omitted_samples']=len(val)-len(result[key])
        elif key=='sample_windows' and isinstance(val,list):
            # First violations and drain checkpoint; each window retains both
            # fixed and mutant actual sampled values in its containing record.
            priority=[v for v in val if v.get('oracle_violations') or any(s.get('drain_due') for s in v.get('samples',[]))]
            chosen=priority[:2]
            for window in val:
                if len(chosen)>=2:break
                if window not in chosen:chosen.append(window)
            result[key]=[compact_feedback(v) for v in chosen]
            result['omitted_feedback_windows']=len(val)-len(chosen)
        else:result[key]=compact_feedback(val)
    return result


class CompactModel(model.Model):
    def call(self,folder,current,target,feedback,phase):
        return super().call(folder,current,target,compact_feedback(feedback),phase)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=ROOT/'deliverables/research17_closed_loop_20261016_r01')
    parser.add_argument('--out',type=Path,default=ROOT/'deliverables/research18_closed_loop_20261016_r01')
    parser.add_argument('--previous-attempt',type=Path,action='append',default=[])
    parser.add_argument('--backend-probe',type=Path,action='append',default=[])
    parser.add_argument('--max-refinement-calls',type=int,default=3)
    parser.add_argument('--max-model-calls',type=int,default=15)
    parser.add_argument('--resume-core-rejection',type=Path)
    args=parser.parse_args();source=args.source.resolve();out=args.out.resolve()
    if ROOT not in out.parents or ROOT not in source.parents:raise ValueError('Workspace paths required')
    candidate=read(source/'shared_initial.json')
    assert read(source/'initial/v0/decision.json')['qualified']
    assert loop.sha(candidate)==read(source/'shared_initial_freeze.json')['hash']
    cases=read(source/'search/admitted_cases.json')
    assert cases
    records=read(source/'search/results.json')
    for case in cases:
        record=next(r for r in records if r['folder']==case['source_query'])
        violation=next(e for e in record['evidence']['mapping'] if e['variant']==case['mode']
            and e['obligation']=='drain_no_loss' and e['kind']=='false_negative')
        assert validate_witness(source/'search',dict(scenario_id=case['source_query'],mode=case['mode'],
            first_violation=violation))['valid']
    if not 1<=args.max_refinement_calls<=10 or not 1<=args.max_model_calls<=40:
        raise ValueError('Explicit bounded iteration and call limits required')
    loop.CONFIG.update(expression_format='ast',max_model_calls=args.max_model_calls,
        max_refinement_calls=args.max_refinement_calls,max_tokens=230000,preflight_tokens=True)
    loop.prepare(out)
    for name in ('research18_continue.py','research17_model_schema.py','research17_search_requalification.py','research18_context_budget.py'):
        shutil.copy2(ROOT/'scripts'/name,out/'source_snapshot'/name)
    dump(out/'source_snapshot/hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'source_snapshot').glob('*.py')})
    for name in ('shared_initial.json','shared_initial_freeze.json'):
        shutil.copy2(source/name,out/name)
    for name in ('admitted_cases.json','strict_witnesses.json','corrected_comparison.json'):
        dump(out/'search'/name,read(source/'search'/name))
    costs=cost_audit(source,artifacts(source))
    dump(out/'reused_source.json',dict(source=str(source),initial_generation=str(source/'initial/v0/model_call'),
        search=str(source/'search'),cost=costs,
        incomplete_call='core/v0/model_call has no terminal response; final usage unavailable, not inferred from chunks.',
        accounting='This run adds new physical calls only. Reused source costs charged separately once, including incomplete attempt.',
        source_files={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts(source)}))
    protocol=read(out/'protocol.json')
    protocol.update(continuation_source=str(source),fresh_initial_call=False,
        preceding_attempts=[str(p.resolve()) for p in args.previous_attempt],
        backend_probes=[str(p.resolve()) for p in args.backend_probe],
        schema='Model-owned recursive expression AST; generic native SVA assembly, no semantic rewrite.',
        feedback='Actual diagnostics compacted uniformly; prioritize two independent target/drain windows, omit opaque hashes and cycle arrays with counts. Full evidence remains on disk.',
        max_refinement_calls=args.max_refinement_calls,
        independent='All core/arm versions frozen before a fresh common independent batch is generated. No test feedback to any model.',
        initial_origin='Prior real Qwen call, original raw response retained and source hashed; no template replacement.')
    dump(out/'protocol.json',protocol)
    llm=CompactModel(out,loop.CONFIG);outcome=dict(status='running')
    try:
        prior=None
        if args.resume_core_rejection:
            prior_path=args.resume_core_rejection.resolve()
            assert ROOT in prior_path.parents
            assert not read(prior_path/'decision.json')['accepted']
            prior=dict(proposal=model.structured(read(prior_path/'model_call/candidate.json')),
                decision=read(prior_path/'decision.json'),counts=read(prior_path/'native/result.json')['counts'])
            dump(out/'resumed_core_rejection.json',dict(source=str(prior_path),feedback=prior,
                scope='Prior real development rejection; no independent test consumed. Charged in linked failed attempt.'))
        core=loop.refine(out/'core',llm,candidate,[loop.common_case()]+cases,True,'core_both_mechanisms',prior)
        outcome=dict(status='core_resolved' if core['resolved'] else 'core_unresolved',core=core)
        frozen={'core':read(out/'core/frozen_candidate.json')}
        if core['resolved']:
            arm_results={}
            for name,cfg in loop.ARMS.items():
                arm_results[name]=loop.refine(out/'arms'/name,llm,candidate,
                    [loop.common_case()]+(cases if cfg['search'] else []),cfg['gate'],'ablation_'+name)
                frozen[name]=read(out/'arms'/name/'frozen_candidate.json')
            dump(out/'all_arms_freeze.json',{name:loop.sha(c) for name,c in frozen.items() if name!='core'})
            outcome.update(status='core_and_four_arms_executed',arms=arm_results)
        # One prospective batch, generated only after ALL model operations stop.
        loop.holdout(out/'core_independent',frozen)
    except KeyboardInterrupt:
        outcome.update(status='interrupted',reason='operator_cancelled; incomplete call usage unavailable')
        raise
    except Exception as exc:
        outcome.update(status='execution_blocked',error=repr(exc));raise
    finally:
        dump(out/'outcome.json',outcome)
        dump(out/'model_cost.json',dict(calls=len(llm.calls),prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in llm.calls),
            completion_tokens=sum(c.get('completion_tokens') or 0 for c in llm.calls),
            usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in llm.calls),formal_calls=0))


if __name__=='__main__':main()
