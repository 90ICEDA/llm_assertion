"""Offline bottleneck audit and lossless, unexecuted presentation comparison.

No network/model/simulator calls; no old result mutation. Requests are proposals,
not authorization. Full plan, native and history admission remain unchanged.
"""
import argparse
import copy
import hashlib
import itertools
import json
import re
from pathlib import Path
import research77_rule_consistency as gate
from research28_report import raw_response

ROOT,read,dump=gate.ROOT,gate.read,gate.dump
BASE=ROOT/'deliverables/research78_prepare_20261024_r01'
LAST=ROOT/'deliverables/research78_real_20261024_r01'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def remap(value,mapping,key=None):
    if isinstance(value,dict):return {k:remap(v,mapping,k) for k,v in value.items()}
    if isinstance(value,list):return [remap(v,mapping,key) for v in value]
    if isinstance(value,str):
        if key in ('id','enum','samples_ref','returned_window_ref'):return mapping.get(value,value)
        if key=='diagnosis':
            return re.sub(r'\b(?:'+ '|'.join(re.escape(k) for k in mapping)+r')\b',lambda m:mapping[m[0]],value)
    return value


def render(request,bound=False,compact=False):
    q=copy.deepcopy(request);body=json.loads(q['messages'][1]['content']);aliases={}
    if bound:
        aliases={w['id']:'window_'+digest({k:v for k,v in w.items() if k!='id'})[:12] for w in body['windows']}
        assert len(set(aliases.values()))==len(aliases)
        body=remap(body,aliases)
        body['sample_bindings']=[dict(id=w['id'],
            anchor_key=w['id']+':anchor:'+str(w['anchor_sample']['cycle']),
            check_key=w['id']+':check:'+str(w['check_sample']['cycle'])) for w in body['windows']]
    if compact:
        for item in body['actual_failed_plan_feedback']['examples']:
            item['samples_ref']=item.pop('samples')['id']
            item['returned_window_ref']=item.pop('returned_window')['id']
    q['messages'][1]['content']=json.dumps(body)
    return q,aliases


def expand(request,aliases):
    body=json.loads(request['messages'][1]['content'])
    windows={w['id']:w for w in body['windows']}
    previous={w['id']:w for w in body['actual_failed_plan_feedback']['rejected_plan']['windows']}
    for item in body['actual_failed_plan_feedback']['examples']:
        if 'samples_ref' in item:item['samples']=copy.deepcopy(windows[item.pop('samples_ref')])
        if 'returned_window_ref' in item:item['returned_window']=copy.deepcopy(previous[item.pop('returned_window_ref')])
    body.pop('sample_bindings',None)
    return remap(body,{v:k for k,v in aliases.items()}) if aliases else body


def main(out):
    out.mkdir(parents=True,exist_ok=False);checks=[];bindings={}
    def source(path):
        bindings[str(path)]=gate.b.search.digest(path)
        return read(path)
    def check(name,condition):
        assert condition,name
        checks.append(name)
    records=[];costs=[]
    rows=source(BASE/'windows.private.json')
    for n in range(75,79):
        root=ROOT/f'deliverables/research{n}_real_20261024_r01'
        outcome=source(root/'outcome.json');cost=source(root/'cost.json')['total'];costs.append(cost)
        check(f'{n}: no accepted/generated/independent result',not outcome['accepted'] and not outcome['independent_performed'] and not (root/'sva_request.preview.json').exists())
        for folder in sorted(root.glob('plan/v*/model_call')):
            request=source(folder/'request.json');plan=source(folder/'hold_plan.json');saved=source(folder.parent/'decision.json')
            call=source(folder/'result.json');assembled=source(folder/'response.assembled.json')
            check(str(folder)+': raw model output',raw_response(folder,plan))
            if n==75:verdict=gate.old.sem.validate(plan,rows)
            elif n==76:verdict=gate.prior.validate(plan,rows)
            else:verdict=gate.validate(plan,rows)
            check(str(folder)+': rejection recomputed',verdict==saved and not verdict['accepted'])
            body=json.loads(request['messages'][1]['content'])
            by_id={w['id']:w for w in plan['windows']}
            fields=[]
            for row in rows:
                truth,cert=gate.old.sem.truth(Path(row['source']),row['check_cycle'])
                check(str(folder)+': bound source '+row['id'],gate.b.search.digest(Path(row['source']))==row['source_sha256'])
                want=dict(id=row['id'],**truth);actual=by_id[row['id']]
                fields.append(dict(id=row['id'],correct=want==actual,
                    mismatches={k:dict(actual=actual.get(k),independent=v) for k,v in want.items() if type(actual.get(k)) is not type(v) or actual.get(k)!=v}))
            common=body['rtl_and_common_contract'];parts={k:len(json.dumps(v)) for k,v in body.items()}
            records.append(dict(run=n,version=folder.parent.name,status=call['status'],
                request_characters=len(request['messages'][1]['content']),field_json_characters=parts,
                common_field_characters={k:len(json.dumps(v)) for k,v in common.items()},
                max_output_tokens=request.get('max_tokens'),service_done=assembled.get('service_done'),
                window_judgments_correct=sum(w['correct'] for w in fields),window_count=len(fields),
                actual_rule_outputs_correct=sum(d['rule_matches_certificate'] for d in verdict.get('details',[])) if n>=77 else None,
                rejection_reasons=verdict['reasons'],field_audit=fields))
    dump(out/'call_audit.json',records)
    public=source(BASE/'windows.public.json');pairs=[]
    for a,b in itertools.combinations(public,2):
        differences=[dict(sample=side,field=k,left=a[side][k],right=b[side][k])
            for side in ('anchor_sample','check_sample') for k in a[side] if a[side][k]!=b[side][k]]
        if len(differences)<=1:
            pairs.append(dict(left=a['id'],right=b['id'],differences=differences,
                cycles_equal=all(a[s]['cycle']==b[s]['cycle'] for s in ('anchor_sample','check_sample'))))
    check('paired legal control differs by one anchor value',any(p['left']=='w0' and p['right']=='w1' and len(p['differences'])==1 for p in pairs))
    dump(out/'sample_identity.json',dict(unique_ids=len({w['id'] for w in public}),windows=len(public),
        duplicate_ids=False,near_identical_pairs=pairs,
        finding='IDs are unique and evaluator source bindings correct; ordinal identifiers and nearly identical sampled pairs are a plausible human/model association risk, not demonstrated cause.'))
    original=source(LAST/'plan/v0/model_call/request.json');body=json.loads(original['messages'][1]['content'])
    old_plan=source(LAST/'plan/v0/model_call/hold_plan.json')
    prototype=[]
    for name,bound,compact in [('A',False,False),('B',True,False),('C',False,True),('D',True,True)]:
        q,aliases=render(original,bound,compact);restored=expand(q,aliases)
        check(name+': all input semantics recover exactly',restored==body)
        rb=json.loads(q['messages'][1]['content'])
        check(name+': RTL/contract unchanged',rb['rtl_and_common_contract']==body['rtl_and_common_contract'])
        adapted=copy.deepcopy(rows)
        for row in adapted:
            row['id']=aliases.get(row['id'],row['id']);row['public']['id']=row['id'];row['expected']['id']=row['id']
        good=dict(**gate.fixture_rules(),windows=[r['expected'] for r in adapted])
        check(name+': private positive fixture passes unchanged semantic gate',gate.validate(good,adapted)['accepted'])
        raw=remap(old_plan,aliases) if aliases else old_plan
        v=gate.validate(raw,adapted)
        check(name+': actual failed response remains rejected',not v['accepted'])
        check(name+': same w1 failure, no semantic correction',{r.get('id') for r in v['reasons']}=={aliases.get('w1','w1')})
        partial=copy.deepcopy(raw);partial['windows'].pop()
        check(name+': missing label still rejects',not gate.validate(partial,adapted)['accepted'])
        # No private positive fixture or adapted answers are written to requests.
        for seed in (7907,7919):
            preview=copy.deepcopy(q);preview['seed']=seed
            dump(out/f'protocol/previews/s{seed}/{name}/request.preview.json',preview)
        prototype.append(dict(arm=name,bound_ids=bound,compact_feedback=compact,
            request_characters=len(q['messages'][1]['content']),
            feedback_characters=len(json.dumps(rb['actual_failed_plan_feedback'])),
            model_token_cost='unavailable: not called',aliases=aliases))
    dump(out/'representation_checks.json',prototype)
    totals={k:sum(c[k] for c in costs) for k in ('model_calls','prompt_tokens_total','completion_tokens_total','native_compile_calls','native_execute_calls','formal_calls')}
    check('five real plan calls, zero SVA',totals['model_calls']==5 and totals['native_compile_calls']==0 and totals['native_execute_calls']==0)
    dump(out/'gate_assessment.json',dict(historical_cost=totals,plans_accepted=0,sva_generated=0,
        whole_plan_gate_effect='Five actual judgments rejected; no SVA generation reached. Bad SVA counterfactual is unobserved.',
        latest=dict(correct_rule_execution=11,correct_window_labels=10,total=11,blocking_window='w1'),
        conclusion='Gate detects inconsistency; increased generation success, avoided bad native outcomes and net efficiency are not identified.',
        limitation='Research75-78 changed interfaces and feedback and reuse one selected development task. No controlled gate/no-gate comparison. Cannot use local fixture success as model efficacy.'))
    protocol=dict(status='sealed_design_and_request_previews_only_NOT_EXECUTED',authorization=False,
        objective='Disentangle sample presentation and feedback repetition without changing acceptance; not a test of the two core innovations.',
        arms=prototype,seeds=[7907,7919],same_model=original['model'],temperature=original.get('temperature'),
        controls='Same RTL,11 full public samples, actual failed plan/diagnostics, whole-plan gate, native windows,14 public and105 history. Compact arm losslessly references duplicate samples/labels, does not remove evidence. Binding IDs encode input only, no legal/buggy label.',
        budget=dict(max_plan_calls=8,max_conditional_sva_calls=8,max_total_calls=16,
            per_seed_per_arm=dict(plan=1,sva_only_if_complete_plan_passes=1,max_output_tokens=original['max_tokens']),
            reserved_input_character_cap_per_call=64000,
            actual_input_tokens='Report service usage; no exact tokenizer available, do not pretend equal token costs.',
            retries=0,no_slot_transfer=True,native_case_limits=dict(window=5,public=14,history=105,independent=56)),
        pilot='Complete all four arms of seed7907; if no arm produces a new native accepted version with the prescribed new independent pass, stop. Only then run seed7919. Report pilot and conditional continuation separately, not unbiased pooled replication.',
        stops=['Any transport error: stop all subsequent calls, preserve usage uncertainty.',
               'Schema, rule/window or native failure: stop that arm; no extra repair call.',
               'All arms use own entire response; never merge successful fields, hand repair, or fill missing labels.',
               'No accepted pilot: stop, report failure and do not open another prompt-only continuation automatically.',
               'If expanding shared-reference feedback changes reconstructed information, do not call model.',
               'Independent failures never feed back. Any later use promotes the whole related test batch to development.'],
        final_acceptance='Unchanged complete-plan pass, native trigger/target checks,14 public and105 history; critical unknown rejects; durable previous version preserved; freeze then new unseen test with actual five-obligation exposure.',
        comparisons='B-A and D-C identify binding presentation; C-A and D-B identify lossless feedback compression. Seeds are not guaranteed deterministic; two seeds are exploratory. Primary endpoints complete-plan pass, actual native accepted version and independent pass, not field accuracy alone.',
        gate_benefit='Not causally identified by this design: every arm keeps the gate. Track rejected error types, downstream success and cost; do not claim necessity or superiority of the plan gate.',
        infrastructure='Execution/authorization controller for this factorial protocol NOT implemented here. Before any run, enforce budgets, isolation and final freeze with local tests. Request previews are not runnable approval or completion.',
        disclosure='All11 examples and previous failures are observed development data. Neither the render experiment nor its candidate selection is independent validation of a new bug.')
    dump(out/'protocol/protocol.json',protocol)
    dump(out/'milestones.json',dict(new_accepted_versions=0,new_complete_105_history_replays=0,
        new_independent_acceptances=0,new_core_mechanism_increment_evidence=0,
        stage='Offline bottleneck audit; last actual pipeline still stops at plan w1.',
        new_model_calls=0,new_simulations=0,proposed_experiment_executed=False))
    for path,h in bindings.items():check('source unchanged '+path,gate.b.search.digest(Path(path))==h)
    dump(out/'source_bindings.json',bindings)
    dump(out/'audit.json',dict(passed=True,checks=checks,new_model_calls=0,new_simulations=0,code_sha256=gate.b.search.digest(Path(__file__))))
    dump(out/'manifest.json',{p.relative_to(out).as_posix():gate.b.search.digest(p) for p in out.rglob('*.json')})
    print('AUDIT',len(checks),'checks;5 archived calls;0 new calls;0 new accepted versions',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();main(a.out.resolve())
