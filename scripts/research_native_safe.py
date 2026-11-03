"""Future compact-feedback entry; prior native execution sources stay immutable.

Only preparation/static qualification has been run for this wrapper. Context
estimates are conservative for the observed English/SV corpus, not exact token
counts. Oversized requests fail before inference; measured usage is audited too.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import research_native_closed_loop as loop

ORIGINAL_ASK = loop.ask
SYSTEM = 'You generate native SystemVerilog assertion sets. Return exactly the requested JSON.'
REQUIRED = ('shared_unchanged_fifo_rtl', 'rtl_before', 'rtl_after', 'bug_description',
            'specification', 'confirmed_repair_obligations')


def compact_context(context):
    result=copy.deepcopy(context)
    source=context.get('feedback')
    if not source:return result
    feedback={}
    for kind in ('misses','false_positives'):
        values=source.get(kind,[])
        # Preserve at most two representatives per feedback category. Full
        # evidence is separately persisted, never silently discarded.
        feedback[kind]={'total_count':len(values),'representatives':values[:2]}
    feedback['current_assertions']=source.get('current_assertions')
    feedback['native_execution']={}
    for mode,record in source.get('native_execution',{}).items():
        feedback['native_execution'][mode]={k:v for k,v in record.items() if k!='failures'}
        failures=record.get('failures',[])
        feedback['native_execution'][mode].update(failure_count=len(failures),failure_representatives=failures[:2])
    feedback['independent_violations']={mode:{'provided_count':len(values),'representatives':values[:2]}
        for mode,values in source.get('independent_violations',{}).items()}
    diagnostics=source.get('compile_diagnostics','')
    errors=[line for line in diagnostics.splitlines() if '%Error' in line or 'syntax error' in line]
    feedback['compile_diagnostics']={'error_line_count':len(errors),'representatives':errors[:2],
        'complete_log_saved_externally':True}
    feedback['selection']='deterministic first two per category/mode; no independent-test evidence consulted'
    result['feedback']=feedback
    return result


def request_for(context):
    return dict(model=loop.MODEL,stream=True,format='json',options=copy.deepcopy(loop.OPTIONS),
        messages=[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(context)}])


def budget(request):
    serialized=json.dumps(request).encode()
    content_bytes=sum(len(m['content'].encode()) for m in request['messages'])
    # Completed archived calls measured 0.268 and 0.272 tokens/request byte.
    # 0.45 plus 256 message/template tokens is a conservative corpus estimate,
    # not a tokenizer guarantee. Keep a further 1024-token context reserve.
    estimate=math.ceil(content_bytes*.45)+256
    context=request['options']['num_ctx'];completion=request['options']['num_predict']
    reserved=1024
    allowed=context-completion-reserved
    return dict(request_bytes=len(serialized),message_content_bytes=content_bytes,
        estimated_prompt_tokens=estimate,token_count_method='0.45 * UTF8 message bytes + 256, calibrated conservatively to prior actual English/SystemVerilog calls; approximate',
        exact_tokenizer_available=False,context_tokens=context,max_completion_tokens=completion,
        reserve_tokens=reserved,max_prompt_tokens=allowed,
        status='estimated_within_budget' if estimate<=allowed else 'blocked_before_model_call',
        limitation='Estimated precheck is not proof against provider tokenization or truncation. Actual usage is checked when returned; context telemetry must remain auditable.')


def prepare(folder,context):
    folder=Path(folder)
    folder.mkdir(parents=True,exist_ok=False)
    compact=compact_context(context)
    for name in REQUIRED:
        assert compact[name]==context[name],f'core_context_changed:{name}'
    full=request_for(context);sent=request_for(compact)
    loop.dump(folder/'full_input_context.json',context)
    loop.dump(folder/'prepared_context.json',compact)
    loop.dump(folder/'original_uncompacted_request.json',full)
    loop.dump(folder/'actual_request_prepared.json',sent)
    record=budget(sent)
    record.update(core_fields_preserved=list(REQUIRED),
        rtl_sha256=hashlib.sha256(compact['shared_unchanged_fifo_rtl'].encode()).hexdigest(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    loop.dump(folder/'context_budget.json',record)
    return compact,record


def safe_ask(folder,context,digest):
    prepared_dir=Path(folder).parent/(Path(folder).name+'_preparation')
    compact,preflight=prepare(prepared_dir,context)
    if preflight['status']=='blocked_before_model_call':
        result=dict(status='context_budget_blocked',model_calls=0,retries=0,prompt_tokens=None,
            completion_tokens=None,wall_seconds=0,preparation=str(prepared_dir))
        loop.dump(Path(folder)/'result.json',result)
        return result,None
    result,candidate=ORIGINAL_ASK(folder,compact,digest)
    actual=json.loads((Path(folder)/'request.json').read_text())
    assert actual==request_for(compact),'prepared_request_differs_from_actual_request'
    observed=result.get('prompt_tokens')
    audit=dict(observed_prompt_tokens=observed,
        status='usage_unavailable' if observed is None else 'within_budget' if observed<=preflight['max_prompt_tokens'] else 'budget_exceeded_reject_candidate',
        provider_truncation_telemetry='not inferred from usage alone; inspect service log')
    loop.dump(prepared_dir/'actual_usage_audit.json',audit)
    if audit['status']=='budget_exceeded_reject_candidate':
        result={**result,'status':'context_budget_exceeded_after_response'}
        loop.dump(Path(folder)/'result.json',result)
        return result,None
    return result,candidate


def qualify(out):
    # Read only the original development request; no holdout evidence or calls.
    original=loop.OUT/'closed_loop/model_calls/revision/request.json'
    request=json.loads(original.read_text())
    ctx=json.loads(request['messages'][-1]['content'])
    compact,new=prepare(out,ctx)
    old=budget(request)
    checks=dict(original_request_estimated_blocked=old['status']=='blocked_before_model_call',
        compact_estimated_within_budget=new['status']=='estimated_within_budget',
        all_core_fields_unchanged=all(compact[k]==ctx[k] for k in REQUIRED),
        fifo_rtl_preserved_byte_for_byte=compact['shared_unchanged_fifo_rtl']==loop.RTL.read_text(),
        at_most_two_miss_examples=len(compact['feedback']['misses']['representatives'])<=2,
        at_most_two_fp_examples=len(compact['feedback']['false_positives']['representatives'])<=2)
    record=dict(status='implemented_static_qualified' if all(checks.values()) else 'static_qualification_failed',
        checks=checks,old_budget=old,new_budget=new,model_calls=0,native_simulation_calls=0,
        source_request=str(original),scope='Preparation/static validation only. No new successful model or native experiment is claimed.')
    loop.dump(Path(out)/'qualification.json',record)
    print(json.dumps(record,indent=2))
    assert all(checks.values()),'static_qualification_failed'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True);p.add_argument('--qualify',action='store_true')
    p.add_argument('--model',default=loop.MODEL);p.add_argument('--endpoint',default=loop.ENDPOINT)
    p.add_argument('--provider',choices=['ollama','openai_compatible'],default=loop.PROVIDER)
    p.add_argument('--key-env',default=loop.KEY_ENV);p.add_argument('--seed',type=int,default=loop.OPTIONS['seed'])
    p.add_argument('--temperature',type=float,default=loop.OPTIONS['temperature']);p.add_argument('--max-tokens',type=int,default=loop.OPTIONS['num_predict'])
    a=p.parse_args();loop.MODEL,loop.ENDPOINT,loop.PROVIDER,loop.KEY_ENV=a.model,a.endpoint,a.provider,a.key_env
    loop.OPTIONS.update(seed=a.seed,temperature=a.temperature,num_predict=a.max_tokens)
    if a.qualify:qualify(Path(a.out))
    else:
        loop.ask=safe_ask
        loop.main(Path(a.out))
