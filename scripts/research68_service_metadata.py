"""Read-only same-origin model directory diagnostic; no generation requests."""
import argparse
import json
from pathlib import Path
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import research68_service_pilot as run
from research20_remote import _NoRedirect,safe_error


def diagnose(out):
    out.mkdir(parents=True,exist_ok=False)
    config=run.base.campaign.settings(run.base.PILOT,1)
    model=run.Model(out/'configuration',config,{})
    endpoint=model.url.rsplit('/',2)[0]+'/models'
    assert urllib.parse.urlsplit(endpoint).netloc==urllib.parse.urlsplit(model.url).netloc
    secret=model.key_file.read_text(encoding='utf-8-sig').strip()
    request=urllib.request.Request(endpoint,headers={'Authorization':'Bearer '+secret,'Accept':'application/json'})
    started=time.perf_counter();result=dict(endpoint=endpoint,generation_calls=0,metadata_http_requests=1,redirects=False)
    try:
        opener=urllib.request.build_opener(_NoRedirect())
        with run.capture(out):
            with opener.open(request,timeout=45) as response:
                value=json.load(response)
        entries=value.get('data',[]) if isinstance(value,dict) else []
        matching=[{k:v for k,v in e.items() if k in ('id','context_length','max_context_length','max_tokens','owned_by')}
                  for e in entries if isinstance(e,dict) and 'qwen' in e.get('id','').lower()]
        result.update(status='completed',catalog_entries=len(entries),qwen_entries=matching,
            requested_model=model.remote_model,requested_model_listed=any(e.get('id')==model.remote_model for e in entries))
    except Exception as exc:result.update(status='failed',error=safe_error(exc))
    result['wall_seconds']=time.perf_counter()-started
    run.dump(out/'result.json',result)
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args();diagnose(a.out.resolve())
