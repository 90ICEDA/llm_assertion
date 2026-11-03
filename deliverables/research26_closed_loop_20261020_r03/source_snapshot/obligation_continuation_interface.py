"""Shared v5 frontend. Public reset is a scalar; expressions are never repaired.

Temporal semantics remain exact sampled delay, with asynchronous observer reset.
Transport errors, JSON/shape errors, grammar errors and compilation are separate.
"""
import copy
import json
import re
import time
import urllib.error
import urllib.request
import contract_v3_checker as checker

BASE_NORMALIZE = checker.normalize
BASE_TB = checker.tb_text
VERSION = 'continuation-interface-v5'


def normalize(c, d, depth=0, param=None):
    assert isinstance(c, dict), 'parse:not_object'
    for key in ('antecedent', 'consequent'):
        assert isinstance(c.get(key), str), 'parse:expression_type'
        assert not re.search(r'\bp[123]_'+re.escape(d['rst'])+r'\b',c[key]), 'unsupported:reset_history'
    metadata=copy.deepcopy(d)
    metadata['observation_base']=list(dict.fromkeys([*d['observation_base'],d['rst']]))
    metadata['inputs']={**d['inputs'],d['rst']:1}
    return BASE_NORMALIZE(c,metadata,depth,param)


def tb_text(d, rows, candidates, param=None):
    text=BASE_TB(d,rows,candidates,param)
    before=f'always @(posedge {d["clk"]}) begin\np1_'
    after=f'always @(posedge {d["clk"]} or negedge {d["rst"]}) begin\np1_'
    assert text.count(before)==1
    return text.replace(before,after,1)


def extract(content, d, prefix):
    obj=json.loads(content)
    assert isinstance(obj,dict) and isinstance(obj.get('assertions'),list), 'parse:assertions_list'
    assert 1 <= len(obj['assertions']) <= 4, 'parse:assertion_count'
    result=[]
    for i,c in enumerate(obj['assertions']):
        normalize(c,d,3)
        result.append(dict(antecedent=c['antecedent'],consequent=c['consequent'],delay=c['delay'],
            id=f'{prefix}_{i}',provenance='actual_local_model',authorized_history_depth=3))
    return result


def stream_call(request, folder, dump, model_digest, timeout=420):
    folder.mkdir(parents=True,exist_ok=False)
    dump(folder/'request.json',request)
    tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=10))
    model=next(m for m in tags['models'] if m['name']==request['model'])
    assert model['digest']==model_digest, 'model_changed'
    dump(folder/'attempt.json',dict(status='submitted',model_digest=model_digest,timeout_seconds=timeout,
        started_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),retries=0))
    started=time.perf_counter(); content='';done=None
    result=dict(status='pending',model=request['model'],digest=model_digest,prompt_tokens=None,
                completion_tokens=None,model_calls=1,retries=0)
    try:
        req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=timeout) as response, (folder/'response.stream.jsonl').open('w') as log:
            for line in response:
                log.write(line.decode());log.flush()
                z=json.loads(line);content+=z.get('message',{}).get('content','')
                if z.get('error'):raise RuntimeError(z['error'])
                if z.get('done'):done=z
                if time.perf_counter()-started>timeout:raise TimeoutError('total_call_deadline')
        assert done is not None, 'transport:missing_done'
        result.update(status='response_received',prompt_tokens=done.get('prompt_eval_count'),completion_tokens=done.get('eval_count'),
            service_total_ns=done.get('total_duration'),done_reason=done.get('done_reason'))
    except KeyboardInterrupt:
        result.update(status='cancelled_by_operator',error='KeyboardInterrupt',
            wall_seconds=time.perf_counter()-started,partial_response_characters=len(content))
        dump(folder/'response.raw.json',dict(message=dict(role='assistant',content=content),service_done=done))
        dump(folder/'transport_result.json',result)
        # A cancelled connection cannot supply final service usage. Preserve
        # null counts and let the orchestrator record an interrupted outcome.
        raise
    except urllib.error.HTTPError as exc:
        (folder/'http_error.txt').write_bytes(exc.read());result.update(status='service_http_error',error=repr(exc))
    except TimeoutError as exc:result.update(status='transport_timeout',error=repr(exc))
    except Exception as exc:result.update(status='service_or_transport_error',error=repr(exc))
    result.update(wall_seconds=time.perf_counter()-started,partial_response_characters=len(content))
    dump(folder/'response.raw.json',dict(message=dict(role='assistant',content=content),service_done=done))
    dump(folder/'transport_result.json',result)
    return result,content
