"""Archive public before/after RTL and upstream PR/commit provenance."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/research197_history_sources_20261104_r01'
REPO='pulp-platform/common_cells'

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'REGuard-research-provenance','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=45) as r:return r.read()

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=False)
    raw=get(f'https://api.github.com/repos/{REPO}/commits/66b3934d6478f255a668a8d6de026730c25f52c5')
    (OUT/'commit.json').write_bytes(raw);commit=json.loads(raw)
    raw=get(f'https://api.github.com/repos/{REPO}/pulls/190');(OUT/'pull_request.json').write_bytes(raw)
    pr=json.loads(raw)
    before=commit['parents'][0]['sha'];after=commit['sha']
    assert pr['merged_at'] and pr['merge_commit_sha']==after
    entries=[]
    for rev in (before,after):
        for path in ('src/stream_delay.sv','src/counter.sv','src/delta_counter.sv','src/lfsr_16bit.sv'):
            url=f'https://raw.githubusercontent.com/{REPO}/{rev}/{path}'
            raw=get(url);dest=OUT/rev/Path(path).name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
            entries.append(dict(path=str(dest.relative_to(ROOT)),url=url,sha256=hashlib.sha256(raw).hexdigest()))
    metadata=dict(parent_bug=REPO+'#190',before=before,after=after,title=pr['title'],intent=pr['body'],sources=entries,
                  patch=[dict(filename=f['filename'],patch=f.get('patch')) for f in commit['files']])
    (OUT/'provenance.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps(metadata,indent=2))
