"""Accelerate only known exclusion globs using a native filesystem name index.

The unchanged exclusion function still reads/hashes every selected stimulus.
Validate against the original completed run before using the cache elsewhere.
No model, native simulation, candidate selection or test outcome access.
"""
import argparse
from pathlib import Path
from unittest.mock import patch
import time
import research69_deadline_pilot as pilot

ROOT,read,dump=pilot.ROOT,pilot.read,pilot.dump


def compute(folder):
    index=read(folder/'index.json')
    paths=[ROOT/str(p).replace('\\','/') for p in index['split_paths']+index['stimulus_paths']]
    original=Path.glob;queries=[]
    def indexed(where,pattern):
        recognized=('**/bounded/correct_stimulus/stimulus.json','**/correct_stimulus/stimulus.json',
                    'research*/**/independent/split.json')
        if pattern not in recognized:return original(where,pattern)
        selected=[]
        for path in paths:
            try:rel=path.relative_to(where)
            except ValueError:continue
            if pattern=='research*/**/independent/split.json':
                okay=len(rel.parts)>=3 and rel.parts[0].startswith('research') and rel.parts[-2:]==('independent','split.json')
            else:
                okay=rel.parts[-2:]==('correct_stimulus','stimulus.json')
                if pattern.startswith('**/bounded/'):okay=okay and len(rel.parts)>=3 and rel.parts[-3]=='bounded'
            if okay:selected.append(path)
        queries.append(dict(root=str(where),pattern=pattern,selected=len(selected)))
        return iter(sorted(set(selected)))
    t=time.perf_counter()
    with patch.object(Path,'glob',indexed):
        hashes,sources=pilot.prior.previous.exclusions(pilot.prior.ORIGIN)
    prep=pilot.prior.PREP
    development=read(prep/'history_cases.json')+read(prep/'common_cases.json')+read(prep/'search_cases.json')
    expected=hashes|{pilot.prior.base.loop.sha(c['rows']) for c in development}
    dump(folder/'computed.json',dict(input_hashes=sorted(expected),sources=sources,
        query_log=queries,compute_seconds=time.perf_counter()-t,
        index_sha256=pilot.prior.base.search.digest(folder/'index.json'),
        source_sha256=pilot.prior.base.search.digest(Path(__file__)),model_calls=0,native_calls=0))
    print('COMPUTED exclusion hash count',len(expected),'glob queries',len(queries),flush=True)


def compare(folder,original):
    new=read(folder/'computed.json');old=read(original/'exclusion_manifest.json')
    assert new['input_hashes']==old['input_hashes']
    # Only traversal order may differ. The same source bytes must be bound.
    assert {r['path']:r['sha256'] for r in new['sources']}=={r['path']:r['sha256'] for r in old['sources']}
    dump(folder/'comparison.json',dict(passed=True,exact_hash_set_equal=True,exact_source_bytes_equal=True,
        original_manifest=str(original/'exclusion_manifest.json'),
        original_manifest_sha256=pilot.prior.base.search.digest(original/'exclusion_manifest.json'),
        computed_sha256=pilot.prior.base.search.digest(folder/'computed.json'),
        scope='Equivalent exclusion enumeration only; no change to active sealed pilot.'))
    print('EXACT EXCLUSION COMPARISON PASSED',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('compute','compare'))
    p.add_argument('--out',type=Path,required=True);p.add_argument('--original',type=Path)
    a=p.parse_args()
    if a.action=='compute':compute(a.out.resolve())
    else:compare(a.out.resolve(),a.original.resolve())
