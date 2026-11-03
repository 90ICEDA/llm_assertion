"""Selected Ibex historical proposal: paired rejection, bounded NEW local recovery.

Selection is retrospective. The continuation protocol/budget is sealed before
new calls. No archived successful OP predicate, test outcome or private answer
table is supplied. Ordinary stopping and full-history stopping are distinct.
"""
import argparse
import copy
import json
import os
import secrets
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

import research61_ast_local as ast
import research66_paired_audit as paired
import research63_phase_qualified as holdout
import research64_search_value as costs
from research_native_model import invoke
from research18_context_budget import count

g=ast.g; old=g.old; ROOT=g.ROOT; P=ast.base.P
read,dump,sha=old.read,old.dump,old.digest
SOURCE=ROOT/'deliverables/research61_ast_20261023_r01/v0/model_call/candidate.json'
SEED=8707


def signature(candidate):
    return old.acceptance.sha(sorted(a['property'].strip() for a in candidate['assertions']))


def all_guard(folder,result,candidate):
    return g.prior.prior.native_flow.prior.all_property_guard(result,
        {v:read(folder/v/'result.json') for v in ('before','after')},candidate)


def evaluate(candidate,folder,baseline):
    small,sg=g.alignment(candidate,P,folder/'alignment')
    search=old.replay(candidate,read(P/'search_cases.json'),'search',folder/'search',P)
    search_guard=all_guard(folder/'search',search,candidate)
    r0=paired.ordinary(small,sg,search,search_guard)
    # Measurement also runs on rejected candidates; only B receives historical feedback.
    history=old.replay(candidate,read(P/'history_cases.json'),'history',folder/'history',P)
    history_guard=all_guard(folder/'history',history,candidate)
    full=paired.aggregate(history,search)
    r1=g.prior.preserve(baseline,full,read(P/'target_preservation.private.json'),old.decide)
    r1['accepted']=bool(r0['accepted'] and r1['accepted'] and history_guard['accepted'] and search_guard['accepted'])
    absolute=bool(r0['accepted'] and old.admissible(full) and history_guard['accepted'] and search_guard['accepted'])
    before,after=old.acceptance.inspect(baseline['ledger']),old.acceptance.inspect(full['ledger'])
    result=dict(ordinary=r0,history=r1,full_absolute=absolute,
        incremental_rejection=bool(r0['accepted'] and not r1['accepted']),
        counts=dict(alignment=small['counts'],search=search['counts'],history=history['counts']),
        new_false_alarm_ids=sorted(after['false_positives']-before['false_positives']),
        lost_detection_ids=sorted(before['detections']-after['detections']),
        retained_detection_ids=sorted(before['detections']&after['detections']),
        current_gate=sg,all_property_guards=dict(search=search_guard,history=history_guard),
        required_untriggered=len(full['required_untriggered']),mapping=dict(history=history['mapping'],search=search['mapping']))
    dump(folder/'decision.json',result)
    return result,dict(alignment=small,search=search,history=history)


def diagnostics(evaluation,records):
    # Compact actual counterexamples only. No desired predicate or classification answer table.
    examples=[];seen=set()
    for cohort in ('alignment','search','history'):
        result=records[cohort];info=old.acceptance.inspect(result['ledger'])
        for kind in ('false_positives','misses','unknown'):
            for key in sorted(info[kind]):
                row=info['rows'][key];s=row['sample'];w=s['instruction']
                group=(cohort,kind,w&127,(w>>28)&1,s['instr_new'],row['obligation'])
                if group in seen:continue
                seen.add(group)
                examples.append(dict(cohort=cohort,kind=kind,sample=s,configuration=row['configuration'],
                    revision=row['revision'],obligation=row['obligation'],
                    decoded_fields=dict(opcode=w&127,bit28=(w>>28)&1,bit31=(w>>31)&1,funct3=(w>>12)&7),
                    expected=row['expected'],observed=row['observed'],native_assertions=row['native']['assertions']))
                if len(examples)>=8:break
            if len(examples)>=8:break
        if len(examples)>=8:break
    return dict(counts=evaluation['counts'],ordinary_accepted=evaluation['ordinary']['accepted'],
        historical_accepted=evaluation['history']['accepted'],new_false_alarms=len(evaluation['new_false_alarm_ids']),
        lost_detections=len(evaluation['lost_detection_ids']),required_untriggered=evaluation['required_untriggered'],
        actual_development_counterexamples=examples)


def request(candidate,feedback,iteration):
    template=ast.request(P,None,SEED+iteration)
    source=json.loads(template['messages'][1]['content'])
    body={k:source[k] for k in ('case','source','rtl','confirmed_obligations','interface','timing',
        'sampling_semantics','actual_model_op_rule','op_development_pairs','output_contract') if k in source}
    body.update(current_assertions=candidate,actual_feedback=feedback,
        task='Refine the supplied real model OP assertion(s) using the provided actual failures. Return a complete OP AST edit. Preserve the existing BRANCH component unchanged. Correct instruction applicability without losing any required first or held-phase detection. Eliminate legal false alarms. Choose every operator, operand, value and timing; the renderer does not repair semantics.',
        acceptance='Unchanged native current9 and search36 gates, then history115 with zero false alarms, misses, critical unknown or necessary untriggered samples, retaining historical protection. Two calls maximum, no retries or protocol change. No independent data is included.')
    template.update(messages=[dict(role='system',content='Return only the declared OP AST JSON edit. Use the actual RTL, confirmed obligations and measured development feedback. No predicate is preselected by the renderer.'),
        dict(role='user',content=json.dumps(body,separators=(',',':')))],format=ast.schema())
    template['options'].update(seed=SEED+iteration,temperature=0.2,num_predict=1536,num_ctx=12288,num_gpu=0,num_thread=8)
    return template


def journal(folder,current,proposal,accepted,reason):
    folder.mkdir(parents=True,exist_ok=False)
    dump(folder/'before.json',current)
    if proposal is not None:dump(folder/'proposal.json',proposal)
    next_version=proposal if accepted else current
    dump(folder/'active.json',next_version)
    dump(folder/'transition.json',dict(accepted=accepted,reason=reason,
        previous_sha256=old.acceptance.sha(current),proposal_sha256=old.acceptance.sha(proposal) if proposal else None,
        active_sha256=old.acceptance.sha(next_version),rollback_verified=accepted or next_version==current))
    return next_version


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    initial=read(P/'shared_initial.json');proposal=read(SOURCE)
    dump(out/'initial.json',initial);dump(out/'proposal.json',proposal)
    for rev in ('before','after'):shutil.copytree(P/rev,out/rev)
    for name in ('source_binding.json','history_cases.json','search_cases.json'):shutil.copy2(P/name,out/name)
    dump(out/'protocol.json',dict(case='original Ibex #166, distinct parent from selected axis_fifo case',
        selection='Known research61 AST proposal, already observed in retrospective research66. NOT a new unobserved proposal or prevalence estimate. Fresh native requalification and prospective bounded continuation only.',
        ordinary='Fixed research66 R0: same current9 first/held/trigger/sampling and all-property checks plus search36; no history115. Accept and stop when R0 passes.',
        history='Same R0 plus unchanged full151, 420 OP and270 BRANCH preservation and all-property history guard. Key unknown rejects. No stricter replacement of ordinary rule after seeing new proposals.',
        shadow_control='Same-history absolute no-false-alarm/miss/unknown/required-trigger check on each identical proposal. Decision-only shadow, not an independent model trajectory.',
        arms=dict(A=dict(history=False,maximum_new_calls=2,stop='initial R0 acceptance'),B=dict(history=True,maximum_new_calls=2,stop='R1 acceptance or budget')),
        shared_initial_proposal=str(SOURCE.relative_to(ROOT)),baseline_status='Partial usable BRANCH baseline, NOT a whole-set accepted version; existing OP gap remains until a new complete acceptance.',
        budget=dict(new_local_calls=2,remote_calls=0,retries=0,per_call_timeout=900,total_call_tokens=30000,
            per_call_output_tokens=1536,context=12288,maximum_native_compiles=26,maximum_native_executes=26),
        model='qwen2.5-coder:7b-instruct',seeds=[SEED,SEED+1],temperature=0.2,
        interface='Same full OP AST representation for both allowed continuation rounds. BRANCH copied unchanged from actual baseline. No category-only adapter switch, plan retries or archived successful predicate.',
        information='Common RTL/spec/current9/search36 and initial proposal; only history arm receives actual history diagnostics. All old successful predicates and test outcomes excluded from requests. Historical costs of common archived proposal remain separate.',
        terminal='Freeze both final versions after B stops. Then generate96 new words for same four configs, excluding all earlier development, research63 and research85 words. Never feed terminal tests back.',
        interpretation='Conditional selected-case continuation. Equal maximum budget, not equal actual spending because ordinary stops immediately. No cross-seed generation rate, no global guarantee.',
        created=time.time()))
    baseline_h=old.replay(initial,read(P/'history_cases.json'),'history',out/'baseline/history',P)
    baseline_s=old.replay(initial,read(P/'search_cases.json'),'search',out/'baseline/search',P)
    baseline=paired.aggregate(baseline_h,baseline_s);dump(out/'baseline_full.json',baseline)
    ev,records=evaluate(proposal,out/'qualification',baseline)
    qualified=ev['incremental_rejection'] and bool(ev['new_false_alarm_ids'] or ev['lost_detection_ids'])
    dump(out/'qualification.json',dict(qualified=qualified,ordinary_accept=ev['ordinary']['accepted'],
        historical_accept=ev['history']['accepted'],absolute_accept=ev['full_absolute'],
        new_false_alarms=len(ev['new_false_alarm_ids']),lost_detections=len(ev['lost_detection_ids']),
        initial_protection=paired.protection(baseline)))
    # Decision fixtures exercise only the fixed rule; never sent as model examples.
    checks=paired.checks_local(records['alignment'],ev['current_gate'],records['search'],ev['all_property_guards']['search'])
    dump(out/'local_checks.json',dict(passed=True,checks=checks))
    feedback=diagnostics(ev,records);dump(out/'initial_feedback.json',feedback)
    dump(out/'request.preview.json',request(proposal,feedback,0))
    excluded=set(read(ROOT/'deliverables/research85_historical_transfer_20261025_r01/ibex166/excluded_words.json'))
    for seed in (8501,8513,8521):
        excluded.update(t['instruction'] for t in read(ROOT/f'deliverables/research85_historical_transfer_20261025_r01/ibex166/s{seed}/independent_cases.json'))
    for cohort in records.values():excluded.update(r['sample']['instruction'] for r in cohort['ledger'])
    dump(out/'excluded_words.json',sorted(excluded))
    dump(out/'code_versions.json',{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'scripts').glob('*.py')})
    # Snapshot only immutable inputs/results, excluding large build trees.
    files=[p for p in out.glob('*.json')]+list(out.glob('before/*.sv'))+list(out.glob('after/*.sv'))
    dump(out/'sealed.json',{p.relative_to(out).as_posix():sha(p) for p in files})
    dump(out/'preparation_cost.json',costs.native_cost(out))
    print('PREPARED87',read(out/'qualification.json'),flush=True)


def verify(prep):
    for n,h in read(prep/'sealed.json').items():assert sha(prep/n)==h,n
    for n,h in read(prep/'code_versions.json').items():assert sha(ROOT/n)==h,n


def service(out,req):
    owned=None
    try:urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2).close()
    except Exception:
        env=os.environ.copy();env.update(OLLAMA_HOST='127.0.0.1:11434',OLLAMA_FLASH_ATTENTION='true',OLLAMA_KV_CACHE_TYPE='q8_0',OLLAMA_NUM_PARALLEL='1')
        with (out/'server.log').open('w') as log:owned=subprocess.Popen(['ollama','serve'],stdout=log,stderr=log,env=env,start_new_session=True)
        dump(out/'owned_service.json',dict(pid=owned.pid))
        for _ in range(30):
            try:urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2).close();break
            except Exception:time.sleep(.5)
        else:raise RuntimeError('local_service_unavailable')
    tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=5));dump(out/'model_tags.json',tags)
    digest=next(m['digest'] for m in tags['models'] if m['name']==req['model'])
    payload=dict(model=req['model'],prompt='',stream=False,keep_alive='30m',options=req['options'])
    dump(out/'model_load/request.json',payload)
    response=json.load(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:11434/api/generate',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}),timeout=120))
    dump(out/'model_load/response.json',response)
    assert response.get('response','')=='' and response.get('done')
    return owned,digest


def independent(prep,out,versions):
    freeze=dict(time=time.time(),versions={a:old.acceptance.sha(c) for a,c in versions.items()},
        source_sha256=read(prep/'source_binding.json')['source_sha256'],development_exclusion_sha256=sha(prep/'excluded_words.json'))
    for arm,c in versions.items():dump(out/'frozen'/arm/'candidate.json',c)
    dump(out/'freeze.json',freeze)
    seed=secrets.randbits(63);txns=holdout.base.generate(seed,read(prep/'excluded_words.json'))
    dump(out/'independent_cases.json',txns);dump(out/'generation.json',dict(seed=seed,at=time.time(),freeze_sha256=sha(out/'freeze.json')))
    results={}
    for arm,c in versions.items():
        folder=out/'frozen'/arm
        for rev in ('before','after'):shutil.copytree(prep/rev,folder/rev)
        result=old.replay(c,txns,'independent',folder/'independent',folder,configs=holdout.base.CONFIGS)
        # Native auditor binds exactly the newly saved executable, source paths and raw samples.
        r=read(folder/'independent/before/result.json')
        dump(folder/'tool_config.json',dict(version=r['tool_version']))
        if result['healthy']:
            audit=holdout.base.native_audit(folder,result);dump(folder/'audit.json',audit)
            with patch.object(old,'CONFIGS',holdout.base.CONFIGS):guard=all_guard(folder/'independent',result,c)
            summary=holdout.summarize(result,guard)
        else:summary=dict(passed=False,counts=result['counts'],status='native_failure')
        dump(folder/'summary.json',summary);results[arm]=summary
        assert old.acceptance.sha(read(folder/'candidate.json'))==freeze['versions'][arm]
        print('INDEPENDENT87',arm,summary['passed'],summary['counts'],flush=True)
    dump(out/'independent_summary.json',results)


def run(prep,out):
    verify(prep);assert read(prep/'qualification.json')['qualified']
    out.mkdir(parents=True,exist_ok=False);owned=None;calls=[];decisions=[];budget=[]
    initial=read(prep/'initial.json');proposal=read(prep/'proposal.json');active=initial;accepted=False
    dump(out/'protocol.json',read(prep/'protocol.json'))
    ordinary=journal(out/'A/initial',initial,proposal,True,'Fixed R0 accepts common archived proposal and stops; no history feedback.')
    active=journal(out/'B/initial',initial,proposal,False,'Fixed R1 adds historical rejection; partial baseline retained.')
    feedback=read(prep/'initial_feedback.json');req=read(prep/'request.preview.json');seen={signature(initial),signature(proposal)}
    try:
        owned,digest=service(out,req)
        for iteration in range(2):
            folder=out/'B'/f'v{iteration}'
            req=read(prep/'request.preview.json') if iteration==0 else request(proposal,feedback,iteration)
            preflight,_=count(req);rendered=preflight.pop('prompt');dump(folder/'context_preflight.json',preflight)
            (folder/'rendered_prompt.txt').write_text(rendered)
            assert preflight['fits_with_output_reserve'],'context_overflow'
            token_used=sum((c.get('prompt_tokens') or 0)+(c.get('completion_tokens') or 0) for c in calls)
            if token_used+preflight['conservative_input_estimate']+1536>30000:
                dump(out/'budget_stop.json',dict(reason='reserved_total_tokens',used=token_used));break
            budget.append(dict(iteration=iteration,reserved_at=time.time(),request_sha256=old.acceptance.sha(req),maximum_output=1536))
            dump(out/'budget_ledger.json',budget)
            print('REAL_LOCAL87',iteration,'prompt',preflight['rendered_prompt_tokens'],flush=True)
            call,text=invoke(req,folder/'model_call',dump,digest,timeout=900);calls.append(call)
            cand=None;ev=None
            decision=dict(accepted=False,reason='transport_or_interface_failure',status=call['status'])
            if call['status']=='response_received':
                try:
                    if abs(call['prompt_tokens']-preflight['rendered_prompt_tokens'])>preflight['wrapper_margin_tokens']:raise ValueError('context_rendering_mismatch')
                    value=json.loads(text);dump(folder/'model_call/model_edit.json',value)
                    cand,labels=ast.adapt(value,initial)
                    dump(folder/'model_call/candidate.json',cand);dump(folder/'model_call/label_mapping.json',labels)
                    (folder/'model_call/candidate.sva').write_text('\n'.join(a['property'] for a in cand['assertions'])+'\n')
                    if signature(cand) in seen:raise ValueError('repeated_executable_proposal')
                    seen.add(signature(cand))
                except (ValueError,TypeError,KeyError,AssertionError) as exc:
                    decision=dict(accepted=False,reason='interface_or_repeat',detail=str(exc));cand=None
            if cand:
                ev,records=evaluate(cand,folder/'native',read(prep/'baseline_full.json'))
                accepted=ev['history']['accepted'];decision=dict(accepted=accepted,ordinary=ev['ordinary'],history=ev['history'],full_absolute=ev['full_absolute'])
                proposal=cand;feedback=diagnostics(ev,records)
            else:feedback=dict(actual_model_text=text,actual_rejection=decision,previous_verified_diagnostics=feedback)
            active=journal(folder/'transition',active,cand,accepted,decision)
            decisions.append(dict(iteration=iteration,**decision));dump(out/'decisions.json',decisions)
            print('DECISION87',iteration,accepted,decision.get('reason'),flush=True)
            if accepted or call['status']!='response_received':break
        independent(prep,out,dict(A=ordinary,B=active))
    except Exception as exc:
        dump(out/'exception.json',dict(type=type(exc).__name__,detail=str(exc)))
        raise
    finally:
        if owned:
            owned.terminate()
            try:owned.wait(timeout=15)
            except subprocess.TimeoutExpired:pass
            dump(out/'service_shutdown.json',dict(pid=owned.pid,owned=True,returncode=owned.poll()))
        dump(out/'outcome.json',dict(new_calls=len(calls),accepted_B=accepted,decisions=decisions,
            active_B_sha256=old.acceptance.sha(active),ordinary_calls=0,ordinary_accepted=True,
            same_budget_recovery_success=accepted,selection='Known selected cross-parent proposal, not a random/new-proposal trial',
            independent_executed=(out/'independent_summary.json').exists(),remote_calls=0))
        dump(out/'cost.json',costs.native_cost(out))
        verify(prep)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=('prepare','run'))
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--prepared',type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve())
