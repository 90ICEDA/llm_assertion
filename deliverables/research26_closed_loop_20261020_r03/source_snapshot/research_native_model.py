"""Configurable real-model transport; no synthetic fallback responses.

Ollama local-default reuses the existing audited stream logger. Alternative
endpoints and OpenAI-compatible transport are implemented but not validated by
the local Ollama experiment. Credentials are read from an environment variable
and never written into artifacts.
"""
import json
import os
import time
import urllib.request
from obligation_continuation_interface import stream_call


def invoke(request, folder, dump, digest=None, endpoint='http://127.0.0.1:11434',
           provider='ollama', key_env='OPENAI_API_KEY', timeout=900):
    if provider == 'ollama' and endpoint.rstrip('/') == 'http://127.0.0.1:11434':
        return stream_call(request, folder, dump, digest, timeout)
    folder.mkdir(parents=True, exist_ok=False)
    headers={'Content-Type':'application/json'}
    if provider == 'openai_compatible':
        key=os.environ.get(key_env)
        if key: headers['Authorization']='Bearer '+key
        payload=dict(model=request['model'],messages=request['messages'],stream=False,
                     temperature=request['options']['temperature'],
                     max_tokens=request['options']['num_predict'],seed=request['options']['seed'])
        route='/chat/completions'
    else:
        payload={**request,'stream':False};route='/api/chat'
    dump(folder/'request.json',payload)
    dump(folder/'transport_config.json',dict(endpoint=endpoint,provider=provider,key_env=key_env,
          credential_available=bool(os.environ.get(key_env)),secret_value_logged=False))
    started=time.monotonic();content=''
    result=dict(status='pending',model=request['model'],digest=digest,model_calls=1,retries=0,
                prompt_tokens=None,completion_tokens=None)
    try:
        req=urllib.request.Request(endpoint.rstrip('/')+route,data=json.dumps(payload).encode(),headers=headers)
        body=urllib.request.urlopen(req,timeout=timeout).read()
        (folder/'response.raw.json').write_bytes(body)
        response=json.loads(body)
        if provider=='openai_compatible':
            content=response['choices'][0]['message']['content']
            result.update(prompt_tokens=response.get('usage',{}).get('prompt_tokens'),
                          completion_tokens=response.get('usage',{}).get('completion_tokens'))
        else:
            content=response['message']['content']
            result.update(prompt_tokens=response.get('prompt_eval_count'),completion_tokens=response.get('eval_count'))
        result['status']='response_received'
    except Exception as exc:
        result.update(status='service_or_transport_error',error=repr(exc))
    result.update(wall_seconds=time.monotonic()-started,partial_response_characters=len(content))
    dump(folder/'transport_result.json',result)
    return result,content
