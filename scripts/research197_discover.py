"""Read-only upstream provenance discovery; no credentials or model transport."""
import concurrent.futures
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/research197_source_discovery_20261104_r01'
PATHS=('src/spill_register_flushable.sv','src/id_queue.sv','src/stream_delay.sv','src/edge_propagator_ack.sv')

def fetch(path):
    url='https://api.github.com/repos/pulp-platform/common_cells/commits?path='+path+'&per_page=100'
    request=urllib.request.Request(url,headers={'User-Agent':'REGuard-research-provenance','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request,timeout=45) as response:raw=response.read()
    out=OUT/(Path(path).stem+'.json');out.write_bytes(raw)
    records=json.loads(raw)
    return {'path':path,'url':url,'commits':[{'sha':r['sha'],'message':r['commit']['message'].splitlines()[0]} for r in records]}

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    if any(OUT.iterdir()):raise ValueError('existing_source_discovery')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(fetch,PATHS))
    (OUT/'index.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    print(json.dumps(rows,indent=2))
