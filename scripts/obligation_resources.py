"""Bounded local model probe and public historical dataset screening."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')

def model_probe(out):
    folder=out/'model_probe';folder.mkdir(exist_ok=False)
    try:
        tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=3))
    except Exception:
        with (folder/'server.log').open('w') as log:
            p=subprocess.Popen(['ollama','serve'],stdout=log,stderr=log,start_new_session=True)
        dump(folder/'server.json',dict(pid=p.pid,started_by_this_run=True))
        tags=None
        for _ in range(10):
            time.sleep(.5)
            try:tags=json.load(urllib.request.urlopen('http://127.0.0.1:11434/api/tags',timeout=2));break
            except Exception:pass
    dump(folder/'tags.json',tags)
    model='qwen2.5-coder:7b-instruct'
    entry=next((r for r in (tags or {}).get('models',[]) if r['name']==model),None)
    if not entry:
        dump(folder/'result.json',dict(status='required_model_not_installed',model=model,model_calls=0,prompt_tokens=None,completion_tokens=None));return
    # A single capability call; contains no candidate, monitor, test or hidden answer.
    request=dict(model=model,stream=False,format='json',messages=[dict(role='user',content='Return exactly this JSON object: {"ready":true}')],
                 options=dict(seed=20261013,temperature=0,num_predict=32,num_ctx=4096,num_gpu=0,num_thread=8))
    dump(folder/'request.json',request);t=time.perf_counter()
    try:
        req=urllib.request.Request('http://127.0.0.1:11434/api/chat',data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
        body=urllib.request.urlopen(req,timeout=180).read();(folder/'response.raw.json').write_bytes(body);r=json.loads(body)
        result=dict(status='available',model=model,digest=entry['digest'],model_calls=1,prompt_tokens=r.get('prompt_eval_count'),completion_tokens=r.get('eval_count'),response=r.get('message'))
    except Exception as exc:result=dict(status='generation_failed',model=model,digest=entry['digest'],model_calls=1,error=repr(exc),prompt_tokens=None,completion_tokens=None)
    result['wall_seconds']=time.perf_counter()-t;dump(folder/'result.json',result);print(json.dumps(result))

def history(out):
    folder=out/'historical_screening';folder.mkdir(exist_ok=False)
    url='https://huggingface.co/datasets/henryen/hwe-bench/resolve/main/lowRISC__ibex.jsonl'
    record=dict(url=url,source_repository='https://github.com/pku-liang/hwe-bench',accessed_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        environment={n:shutil.which(n) for n in ['docker','verilator','iverilog','git','make','g++']},
        generator_visibility='none: history patches and test answers are quarantined from generation',real_cases_admitted=0)
    try:
        response=urllib.request.urlopen(url,timeout=40);body=response.read(20_000_001)
        assert len(body)<=20_000_000,'dataset exceeds bounded 20MB retrieval'
        (folder/'lowRISC__ibex.jsonl').write_bytes(body)
        rows=[json.loads(s) for s in body.decode().splitlines() if s.strip()]
        record.update(status='metadata_downloaded',bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),rows=len(rows),fields=sorted(rows[0]))
        # Preserve all metadata; shortlist by small patch footprint, never success.
        shortlist=sorted(rows,key=lambda r:len(str(r.get('patch',''))))[:3]
        dump(folder/'shortlist_raw.json',shortlist)
        dump(folder/'screening.json',[dict(index=i,metadata=r,status='deferred_environment_not_reproduced',
             reason='Published fail-to-pass result not independently reproduced here; Docker/Verilator availability recorded. No real-bug admission without both revisions passing the requested gate.',
             before_execution='not_executed',after_execution='not_executed') for i,r in enumerate(shortlist)])
    except Exception as exc:record.update(status='retrieval_failed',error=repr(exc))
    dump(folder/'result.json',record);print(json.dumps(record))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('action',choices=['model_probe','history']);a=p.parse_args()
    globals()[a.action](ROOT/'deliverables'/a.run)
