"""Prospective one-call-per-arm 2x2 trial, with isolated initial feedback.

prepare: local native qualification and exact request previews, zero remote calls.
run: requires four newly authorized calls. No independent tests before all arms
freeze, no proposal sharing, no manual property edits, no retry or cherry-picking.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import secrets
import shutil

import research17_loop as loop
import research28_valid_runtime as extension
from research26_model import RemoteModel as ParentModel,replace_one
from research28_campaign import config

ROOT=loop.ROOT
read,dump=loop.read,loop.dump
SEARCH=ROOT/'deliverables/research30_search_compare_20261020_r01'
ORIGIN=ROOT/'deliverables/research27_closed_loop_20261020_r06'
ARMS=dict(A=dict(search=False,gate=False),B=dict(search=True,gate=False),
          C=dict(search=False,gate=True),D=dict(search=True,gate=True))


def snapshot(out):
    for name in ('research30_ablation.py','research28_campaign.py','research28_valid_runtime.py',
                 'research20_stall_runtime.py','research26_model.py','research22_model.py',
                 'research20_model.py','research20_remote.py','research21_model.py',
                 'research23_model.py','research24_model.py','research28_cases.py',
                 'research21_cases.py','research20_cases.py'):
        shutil.copy2(ROOT/'scripts'/name,out/'source_snapshot'/name)
    dump(out/'source_snapshot/hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (out/'source_snapshot').iterdir() if p.is_file() and p.name!='hashes.json'})


class Model(ParentModel):
    def __init__(self,out,settings):
        super().__init__(out,settings)
        self.assemble=self.edit

    @staticmethod
    def edit(value,current):
        if value.get('operation')=='keep':
            assert set(value)=={'operation','assertion_id','assertions','reason'}
            assert value['assertion_id']=='' and value['assertions']==[]
            return copy.deepcopy(current)
        eligible={a['id'] for a in current['assertions'] if a['obligations']==['stall_stability']}
        assert value['assertion_id'] in eligible
        assert value['assertions'][0]['obligation']==['stall_stability']
        return replace_one(value,current)

    def transform_request(self,request,current,target,feedback,phase):
        request=super().transform_request(request,current,target,feedback,phase)
        body=json.loads(request['messages'][1]['content'])
        task=body['boundary_repair']
        schema=task['response_schema']
        schema['properties']['operation']['enum']=['keep','replace_one']
        schema['properties']['assertion_id']['enum']=['']+[a['id'] for a in current['assertions'] if a['obligations']==['stall_stability']]
        schema['properties']['assertions']['minItems']=0
        schema['properties']['assertions']['maxItems']=1
        task['operation']='Review the current stall-stability protection using the shared specification and supplied actual observations. If no change is needed, return keep with empty assertion_id and empty assertions. Otherwise replace exactly one existing stall-stability property; other properties remain unchanged.'
        task['validation']='Compile and execute the returned set on supplied current evidence. No unevaluated scenario is a known pass.'
        body['final_instruction']=task['operation']+' '+task['boundary_semantics']
        body['output_schema']=schema
        body.pop('final_temporal_review',None)
        request['messages'][0]['content']='Review a native SVA set against its stated obligation and actual observations. Return only the JSON schema. Decide whether to keep or replace one property and explain why. Derive your own complete expression and timing; no answer is supplied. Only declared signals; the harness supplies clock/reset.'
        request['messages'][1]['content']=json.dumps(body)
        return request


def select_cases(seed=3113):
    """Fixed requested seed, first occurrence of each stall FN mechanism."""
    assert read(SEARCH/'outcome.json')['status']=='four_search_methods_completed'
    selected=[];seen=set()
    for record in read(SEARCH/'results.json'):
        if record['seed']!=seed or record['method']!='contract_coverage':
            continue
        for gap in record['gaps']:
            key=(gap['kind'],gap['mechanism'],gap['obligation'])
            if key in seen or gap['kind']!='FN' or gap['obligation']!='stall_stability':
                continue
            seen.add(key)
            folder=SEARCH/'queries'/f"s{record['seed']}"/record['method']/f"q{record['query']}"
            stimulus_path=folder/'initial'/(gap['mechanism']+'_stimulus')/'stimulus.json'
            rows=read(stimulus_path)
            selected.append(dict(id=f'acquired30:s{seed}:q{record["query"]}:{gap["mechanism"]}',
                depth=4,pipeline=1,rows=rows,mode=gap['mechanism'],split='development',
                source='contract_search_first_seed_first_mechanism',target_obligation='stall_stability',
                provenance=dict(search_query=str(folder),gap_key=gap['gap_key'],evidence_id=gap['evidence']['evidence_id'],
                    stimulus_sha256=hashlib.sha256(stimulus_path.read_bytes()).hexdigest())))
    assert selected,'no_valid_search_treatment'
    return selected


def feedback(prep,use_search):
    base=read(prep/'core/history/result.json')
    current=[base['feedback'][0]]
    groups=[read(prep/'core/history/case_0/ledger.json')]
    if use_search:
        acquired=read(prep/'core/acquired/result.json')
        current+=acquired['feedback'];groups.append(acquired['group'])
    from research15_evidence import merge_ledgers
    merged=merge_ledgers(groups)
    return dict(requested_obligations=['stall_stability'],counts=loop.counts(merged),
        actual_native_evidence=current)


def prepare(out):
    loop.prepare(out)
    snapshot(out)
    initial=read(ORIGIN/'core/frozen_candidate.json')
    assert loop.sha(initial)==read(ORIGIN/'core/freeze.json')['candidate_sha256']
    dump(out/'shared_initial.json',initial)
    history=read(ORIGIN/'development_plan.json')
    acquired=select_cases()
    dump(out/'history_cases.json',history);dump(out/'acquired_cases.json',acquired)
    settings=config(1)
    settings['options']['seed']=3113
    dump(out/'model_config.json',settings)
    dump(out/'protocol.json',dict(arms=ARMS,model_calls_per_arm=1,max_total_model_calls=4,model_config=settings,
        initial_source=str(ORIGIN/'core'),initial_hash=loop.sha(initial),
        common_information='Same full RTL/harness, specification, five initial properties and common case_0 evidence. No successful research28 predicate is supplied.',
        treatments='B/D receive only the first seed contract search witnesses; A/C do not. C/D enforce historical gate after proposal; A/B use visible current evidence only.',
        gate_feedback='One-call trial: gate is a decision treatment, not extra initial prompt evidence. Initial prompts A=C and B=D.',
        source_search_cost='Seed3113 contract arm: four queries,64 native executions,shared source setup. B/D share this acquisition physically; charge64 logical executions to each search arm and report shared physical cost separately.',
        fairness='Same model configuration and one-call cap; actual tokens and simulation cost may differ and are reported. No unspent-token padding.',
        history_audit='After all arms freeze, evaluate all on same historical+acquired evidence. Audit outcomes cannot affect acceptance or model inputs.',
        independent='Generate one shared fresh26-case batch only after all arms freeze. No adaptation or selection.',
        scope='Single model seed, one known FIFO repair task and artificial faults; retrospective case selection. Not multiseed model stability or original historical parent proof.'))
    with extension.installed():
        baseline=loop.replay(initial,out/'core/history',history)
        evidence=loop.replay(initial,out/'core/acquired',acquired)
        assert baseline['healthy'] and evidence['healthy']
        assert not baseline['counts']['misses'] and not baseline['counts']['unknown'] and not baseline['counts']['false_positives']
        assert evidence['counts']['misses']>0 and not evidence['counts']['unknown'] and not evidence['counts']['false_positives']
        for name,arm in ARMS.items():
            model=Model(out/'preview'/name,settings)
            request=model._payload(initial,'stall_stability',feedback(out,arm['search']),'controlled_stall_review')
            dump(out/'preview'/name/'request.preview.json',request)
    previews={name:read(out/'preview'/name/'request.preview.json') for name in ARMS}
    assert previews['A']==previews['C'] and previews['B']==previews['D']
    dump(out/'qualification.json',dict(passed=True,history_cases=len(history),search_cases=len(acquired),
        before_history=baseline['counts'],search_misses=evidence['counts']['misses'],
        paired_initial_requests_equal=True,model_calls=0,credentials_read=False,external_transmission=False))
    dump(out/'outcome.json',dict(status='prepared_without_remote_calls'))


def run(prep,out,authorization):
    auth=read(authorization)
    assert auth['authorized_calls']>=4 and auth['run_output']==out.relative_to(ROOT).as_posix()
    assert auth['endpoint']==config(1)['remote_url']
    assert read(prep/'qualification.json')['passed']
    loop.prepare(out);shutil.copy2(authorization,out/'authorization.json')
    snapshot(out)
    dump(out/'prepared_source.json',dict(path=str(prep),protocol=read(prep/'protocol.json')))
    initial=read(prep/'shared_initial.json')
    history=read(prep/'history_cases.json');acquired=read(prep/'acquired_cases.json')
    dump(out/'shared_initial.json',initial);dump(out/'arms.json',ARMS)
    settings=read(prep/'model_config.json');models=[];frozen={};decisions={}
    dump(out/'outcome.json',dict(status='running'))
    try:
        with extension.installed():
            for name,arm in ARMS.items():
                folder=out/'arms'/name
                llm=Model(folder,settings);models.append(llm)
                call,proposal=llm.call(folder/'model_call',initial,'stall_stability',feedback(prep,arm['search']),'controlled_stall_review')
                visible=[history[0]]+(acquired if arm['search'] else [])
                selected=(history if arm['gate'] else [history[0]])+(acquired if arm['search'] else [])
                baseline=loop.replay(initial,folder/'before',selected)
                after=loop.replay(proposal,folder/'proposed',selected) if proposal else None
                decision=dict(accepted=False,reasons=['model_or_interface_failure'],gate=arm['gate'])
                if after and after.get('group'):
                    old=loop.inspect(baseline['group']['ledger'])
                    visible_ids={c['id'] for c in visible}
                    targets=[k for k in old['misses']|old['false_positives'] if old['rows'][k]['scenario_id'] in visible_ids]
                    if arm['gate']:
                        gate=loop.decide(baseline['group']['ledger'],after['group']['ledger'],targets)
                        dump(folder/'historical_gate.json',gate)
                        okay=after['healthy'] and gate['accepted']
                        reasons=gate['reasons']
                    else:
                        now=loop.inspect(after['group']['ledger'])
                        okay=after['healthy'] and not(now['misses'] or now['false_positives'] or now['unknown'])
                        reasons=[] if okay else ['visible_current_evidence_failed']
                    decision=dict(accepted=bool(okay),reasons=reasons,gate=arm['gate'],call=call,
                        before=baseline['counts'],after=after['counts'],target_keys=targets)
                final=proposal if decision['accepted'] else initial
                dump(folder/'decision.json',decision);decisions[name]=decision
                loop.freeze(folder,final,'one_call_arm_terminal_before_common_audit_and_fresh_holdout')
                frozen[name]=final
            dump(out/'all_arms_freeze.json',{n:loop.sha(c) for n,c in frozen.items()})
            # Audit-only across equal evidence, after every decision is final.
            for name,candidate in frozen.items():
                loop.replay(candidate,out/'historical_audit'/name,history+acquired)
            from research28_cases import cases as valid_cases
            from research21_cases import independent_cases
            seed=secrets.randbelow(2**31)
            fresh=valid_cases(seed,independent=True)+independent_cases(seed)
            dump(out/'independent/split.json',dict(seed=seed,created_after_all_freeze=True,cases=fresh,
                hashes={n:loop.sha(c) for n,c in frozen.items()},usage='no_feedback_no_selection'))
            for name,candidate in frozen.items():
                result=loop.replay(candidate,out/'independent'/name,fresh)
                for row in result['group']['ledger']:row['split']='independent_test'
                dump(out/'independent'/name/'result.json',result)
        dump(out/'outcome.json',dict(status='four_real_model_arms_completed',decisions=decisions))
    except BaseException as exc:
        dump(out/'outcome.json',dict(status='execution_blocked',error=repr(exc)));raise
    finally:
        calls=[c for m in models for c in m.calls]
        dump(out/'model_cost.json',dict(calls=len(calls),prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),
            completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),
            usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls),formal_calls=0))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    args=p.parse_args();out=args.out.resolve();assert ROOT in out.parents
    try:
        if args.action=='prepare':prepare(out)
        else:run(args.prepared.resolve(),out,args.authorization.resolve())
    except BaseException as exc:
        if args.action=='prepare' and out.exists():
            dump(out/'outcome.json',dict(status='preparation_blocked',error=repr(exc),model_calls=0))
        raise


if __name__=='__main__':main()
