"""Real local grammar enforcement probe; never a repair candidate or feedback."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

import research17_loop as loop
import research39_ast_refinement as adapter
from research_native_model import invoke


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    owned=None
    status='not_started'
    try:
        try: urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2).close()
        except Exception:
            env=os.environ.copy()
            env.update(OLLAMA_HOST='127.0.0.1:11434',OLLAMA_FLASH_ATTENTION='true',
                       OLLAMA_KV_CACHE_TYPE='q8_0',OLLAMA_NUM_PARALLEL='1')
            with (out/'server.log').open('w') as log:
                owned=subprocess.Popen(['ollama','serve'],stdout=log,stderr=log,env=env,start_new_session=True)
            loop.dump(out/'owned_service.json',dict(pid=owned.pid))
            for _ in range(30):
                try:
                    urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2).close()
                    break
                except Exception: time.sleep(.5)
            else: raise RuntimeError('local_service_unavailable')
        tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=5))
        name='qwen2.5-coder:7b-instruct'
        digest=next(m['digest'] for m in tags['models'] if m['name']==name)
        current=loop.read(adapter.previous.PREP/'shared_initial.json')
        request=dict(model=name,stream=True,format=adapter.schema(current),
            options=dict(temperature=0,seed=3903,num_predict=512,num_ctx=4096,num_gpu=0,num_thread=8),
            messages=[dict(role='user',content='Return exactly NOT_JSON. This is a conflicting-text structured-output enforcement probe, not a hardware repair. No generated expression will be used as a candidate.')])
        result,content=invoke(request,out/'model_call',loop.dump,digest,timeout=180)
        valid=False
        validation=None
        try:
            value=json.loads(content)
            # Strict AST validation only; no corrected expressions or replay.
            adapter.assemble(value,current)
            valid=True
        except Exception as exc: validation=repr(exc)
        errors=[]
        if owned is not None:
            errors=[line for line in (out/'server.log').read_text(errors='replace').splitlines()
                    if 'error parsing grammar' in line or 'failed to parse grammar' in line]
        else: errors=None
        passed=result['status']=='response_received' and valid and errors==[]
        status='probe_passed' if passed else 'probe_failed_or_unknown'
        loop.dump(out/'qualification.json',dict(status=status,passed=passed,strict_ast_valid=valid,
            validation_error=validation,backend_grammar_errors=errors,model_calls=result['model_calls'],
            prompt_tokens=result['prompt_tokens'],completion_tokens=result['completion_tokens'],
            model_wall_seconds=result.get('wall_seconds'),native_calls=0,formal_calls=0,
            scope='One real local conflicting-text grammar probe. Not a repair, not in model feedback, not independent validation. Remote schema enforcement remains unavailable.'))
        print(status,dict(valid_ast=valid,grammar_errors=errors),flush=True)
    finally:
        if owned is not None:
            owned.terminate()
            try: owned.wait(timeout=15)
            except subprocess.TimeoutExpired: pass
            loop.dump(out/'service_shutdown.json',dict(pid=owned.pid,returncode=owned.poll(),owned=True))
        shutil.copy2(__file__,out/'probe_source.py')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();assert loop.ROOT in a.out.resolve().parents
    run(a.out.resolve())
