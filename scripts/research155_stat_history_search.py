"""Archive public upstream history and bounded issue/PR search. No model calls."""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import subprocess
import time
import urllib.parse
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
FILE = 'rtl/axis_stat_counter.v'


def dump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+'\n')


def git(repo, *args):
    return subprocess.check_output(['git', '--git-dir='+str(repo), *args])


def collect(out, archive_name):
    repo = out/'upstream.git'
    archive = out/archive_name
    archive.mkdir(exist_ok=False)
    refs = git(repo, 'show-ref').decode()
    (archive/'refs.txt').write_text(refs)
    assert git(repo, 'rev-parse', '--is-shallow-repository').strip() == b'false'
    commits = git(repo, 'log', '--all', '--format=%H', '--', FILE).decode().splitlines()
    records = []
    for c in commits:
        folder = archive/'commits'/c
        folder.mkdir(parents=True)
        rtl = git(repo, 'show', c+':'+FILE)
        (folder/'axis_stat_counter.v').write_bytes(rtl)
        (folder/'commit.txt').write_bytes(git(repo, 'show', '-s', '--format=fuller', c))
        (folder/'change.patch').write_bytes(git(repo, 'show', '--format=fuller', c, '--', FILE))
        text = rtl.decode()
        block = text.split('// count frames')[1].split('always @(posedge')[0]
        (folder/'frame_count_block.txt').write_text(block)
        records.append(dict(commit=c,parents=git(repo,'show','-s','--format=%P',c).decode().strip().split(),
            sha256=hashlib.sha256(rtl).hexdigest(),
            frame_block=block,commit_url='https://github.com/alexforencich/verilog-axis/commit/'+c))
    dump(archive/'history.json', dict(head=git(repo,'rev-parse','HEAD').decode().strip(),
        shallow=False,commits=records,scope='All file changes reachable from fetched public branch/tag refs; pull heads queried separately.'))
    queries = [
        'repo:alexforencich/verilog-axis stat',
        'repo:alexforencich/verilog-axis "single" "frame"',
        '"axis_stat_counter"',
        'repo:fpganinja/taxi stat counter',
    ]
    requests = [('issues_'+str(i), 'https://api.github.com/search/issues?'+urllib.parse.urlencode(dict(q=q,per_page=100))) for i,q in enumerate(queries)]
    requests += [('taxi_axis_rtl','https://api.github.com/repos/fpganinja/taxi/contents/src/axis/rtl')]
    summary=[]
    for name,url in requests:
        start=time.time()
        req=urllib.request.Request(url,headers={'User-Agent':'AssertionForge-public-history-audit','Accept':'application/vnd.github+json'})
        record=dict(url=url,started_at=start,no_retry=True)
        try:
            with urllib.request.urlopen(req,timeout=60) as response:
                data=response.read();record.update(status=response.status,headers=dict(response.headers))
            (archive/(name+'.json')).write_bytes(data)
            obj=json.loads(data)
            if isinstance(obj,list):
                record['paths']=[x.get('path') for x in obj]
                obj={}
            record['total_count']=obj.get('total_count')
            record['incomplete_results']=obj.get('incomplete_results')
            record['items']=[dict(number=x['number'],title=x['title'],url=x['html_url'],pull_request=x.get('pull_request')) for x in obj.get('items',[])]
            if 'tree' in obj:
                record['tree_truncated']=obj.get('truncated')
                record['stat_paths']=[x['path'] for x in obj['tree'] if 'stat' in x['path'].lower()]
        except (urllib.error.URLError,TimeoutError,http.client.IncompleteRead) as e:
            record.update(status='unavailable',error=str(e))
        record['wall_seconds']=time.time()-start
        dump(archive/(name+'.request.json'),record);summary.append(record)
        print(name,record.get('status'),record.get('total_count'),record.get('items',record.get('stat_paths')),flush=True)
    dump(archive/'public_search.json',summary)
    dump(archive/'seal.json',{str(p.relative_to(archive)):hashlib.sha256(p.read_bytes()).hexdigest() for p in archive.rglob('*') if p.is_file()})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);ap.add_argument('--archive-name',default='archive')
    args=ap.parse_args();collect(args.out.resolve(),args.archive_name)
