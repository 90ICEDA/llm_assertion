"""Real local generation, compact contract-first instructions, no templates."""
import argparse
import json
import subprocess
import time
import urllib.request
from pathlib import Path
import research_native_closed_loop as prior
import research15_native_interface as interface
from research_native_model import invoke

OUT=interface.OUT;dump=interface.dump
MODEL='qwen2.5-coder:7b-instruct'
OPTIONS=dict(seed=20261015,temperature=0,num_predict=640,num_ctx=16384,num_gpu=0,num_thread=8)


def service(env=None):
    try:
        tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3))
    except Exception:
        folder=OUT/'service';folder.mkdir(parents=True,exist_ok=True)
        with (folder/'server.log').open('a') as log:
            p=subprocess.Popen(['ollama','serve'],stdout=log,stderr=log,start_new_session=True,env=env)
        dump(folder/'process.json',{'pid':p.pid})
        for i in range(20):
            time.sleep(.5)
            try:tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3));break
            except Exception:pass
        else:raise RuntimeError('local_model_service_unavailable')
    else:
        if env is not None:
            raise RuntimeError('custom_environment_requires_new_owned_service')
    dump(OUT/'model_tags.json',tags)
    return next(m['digest'] for m in tags['models'] if m['name']==MODEL)


def context():
    ctx=prior.context()
    ctx.update(bug_description='An artificial boundary defect of the actual buffered FIFO can return payloads that differ from their corresponding accepted input transactions. Correct FIFO preserves the accepted transaction sequence. Other faults may require complementary properties.',
        allowed_signals='svalid sready sdata mvalid mready mdata ref_count ref_expected drain_due',
        auxiliary_reference_state=interface.REFERENCE,
        helper_semantics={
            'ref_count':'Independent queue count of accepted inputs still awaiting accepted output. Updated after the current sampling edge; reset clears it.',
            'ref_expected':'Full 32-bit payload of oldest outstanding accepted input. Defined only when ref_count > 0. It is NOT the current sdata and NOT the previous output.',
            'drain_due':'Test-environment marker at end of independently confirmed fair drain suffix. Only a finite no-loss checkpoint; not an unbounded liveness guarantee.'},
        output_schema={'assertions':[{'property':'one native SVA expression with exactly one explicit |-> or |=>, no clock/reset/wrapper','obligations':['one named obligation'],'reason':'why this obligation follows from this property'}]},
        instructions='Return only JSON. No trigger field: the harness parses the actual antecedent and compiles native cover property. Generate distinct complementary properties, never duplicates. No procedural checker. Only permitted signals, no internal DUT signals. Clock/reset are automatically wrapped. Do not impose constant output data between different accepted transactions: distinct transactions can carry different payloads. No ## delays. Ref state is trusted observation state, not candidate logic.')
    return ctx


def call(folder,ctx,digest):
    request=dict(model=MODEL,stream=True,format='json',options=OPTIONS,
        messages=[{'role':'system','content':'Synthesize native SVA from the provided transaction contract. Follow the final obligation-specific task exactly; use reference-state semantics. Return JSON only.'},
                  {'role':'user','content':json.dumps(ctx)}])
    estimate=int(sum(len(m['content'].encode()) for m in request['messages'])*.45)+256
    assert estimate+OPTIONS['num_predict']+1024<OPTIONS['num_ctx'],'context_budget_estimate_exceeded'
    result,content=invoke(request,folder,dump,digest,timeout=900)
    candidate=None
    if result['status']=='response_received':
        try:candidate=interface.normalize_candidate(json.loads(content));result['candidate_status']='parsed'
        except Exception as exc:result.update(candidate_status='rejected',candidate_error=repr(exc))
    if candidate:
        dump(folder/'candidate.json',candidate);(folder/'candidate.sva').write_text(interface.candidate_sva(candidate))
    result['context_budget']={'estimated_prompt_tokens':estimate,'context_tokens':OPTIONS['num_ctx'],'estimate_not_exact_tokenization':True}
    dump(folder/'result.json',result)
    return result,candidate


def initial():
    digest=service();ctx=context()
    ctx['task']='Generate exactly ONE assertion for order_payload only. At every accepted OUTPUT with an outstanding reference item, its full output payload must equal the oldest accepted input payload. Use the input/output handshake meanings and ref_expected defined above. The property checks equality on that output acceptance sample, not stability between consecutive output samples. Do not attempt other obligations yet.'
    result,candidate=call(OUT/'model_calls/initial',ctx,digest)
    dump(OUT/'initial_generation.json',dict(result=result,candidate=candidate))
    print(json.dumps({'status':result,'candidate':candidate},indent=2))


def qualify_initial():
    import research15_search_runtime as runtime
    import research_fifo_experiment as fifo
    from research15_evidence import paired_ledger
    from research15_acceptance import inspect,sha
    original=json.loads((OUT/'initial_generation.json').read_text())['candidate']
    assert original is not None,'no_parsed_initial_candidate'
    rows=fifo.stimulus(2026101501)
    for row in rows:row['drain_due']=0
    def check(candidate,name):
        folder=OUT/'initial_qualification'/name
        compiled=runtime.build(candidate,folder/'compiled',2,0)
        fixed=runtime.execute(compiled,folder/'correct',rows,'correct')
        mutant=runtime.execute(compiled,folder/'corrupt',rows,'corrupt')
        ledger=paired_ledger(fixed,mutant,'initial_qualification:d2:p0:s2026101501')
        dump(folder/'ledger.json',ledger)
        info=inspect(ledger['ledger'])
        qualified=not info['unknown'] and not info['false_positives'] and bool(info['detections'])
        record=dict(qualified=qualified,counts={k:len(info[k]) for k in ('rows','false_positives','detections','misses','triggers','unknown')},
            scope='order_payload only, common legal/corrupt finite replay; not all FIFO obligations')
        dump(folder/'qualification.json',record)
        return record,fixed,mutant
    before,fixed,mutant=check(original,'original')
    candidate=original;source='initial'
    if not before['qualified']:
        ctx=context()
        hit_cycles=[]
        for h in fixed['native']['failures']:
            import re
            hit_cycles.append(int(re.search(r'cycle=(\d+)',h['detail'])[1]))
        examples=[{'cycle':c,'port_sample':next(t for t in fixed['trace'] if t['cycle']==c),
            'independent_obligation_checks':[v for v in fixed['oracle']['checks'] if v['cycle']==c]}
            for c in sorted(set(hit_cycles))[:2]]
        ctx.update(current_assertions=original,actual_native_feedback=dict(qualification=before,
            correct_rtl_oracle=fixed['oracle']['verdict'],legal_false_positive_examples=examples),
            task='Perform ONE semantic correction of the current order_payload assertion using the actual legal false-positive examples. The earlier property compares sdata, but sdata is the currently presented INPUT transaction, which can differ from the queued transaction completing now. The OUTPUT payload is mdata. Generate one corrected native assertion for accepted OUTPUT versus oldest reference item. Do not weaken the accepted-output trigger, do not compare consecutive outputs, do not add other obligations. Return full JSON.')
        result,candidate=call(OUT/'model_calls/initial_semantic_repair',ctx,service())
        source='initial_semantic_repair'
        if candidate is None:
            dump(OUT/'initial_qualification/summary.json',dict(status='semantic_repair_generation_failed',before=before,call=result));return
        after,_,_=check(candidate,'semantic_repair')
    else:after=before
    if after['qualified']:
        dump(OUT/'shared_initial.json',candidate)
        dump(OUT/'shared_initial_freeze.json',dict(candidate_sha256=sha(candidate),source_model_call=source,
            common_initialization_calls=2 if source!='initial' else 1,
            scope='Selected after explicit shared semantic qualification; this selection and its cost are common to all four arms.'))
    dump(OUT/'initial_qualification/summary.json',dict(status='shared_initial_qualified' if after['qualified'] else 'shared_initial_unqualified',before=before,after=after,source=source))
    print(json.dumps({'before':before,'after':after,'source':source},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['initial','qualify'],nargs='?',default='initial')
    args=p.parse_args()
    if args.action=='initial':initial()
    else:qualify_initial()
