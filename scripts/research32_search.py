"""Predeclared equal-budget long-stall exploration, native whole-candidate pair.

Development experiment on explicit artificial counter faults. No model calls.
Policy never reads the hidden judge's gaps for ordinary/disagreement/raw arms.
"""
import argparse
import hashlib
import random
import shutil
from pathlib import Path
import research17_loop as loop
import research32_runtime as extension
from research30_search import SOURCES, failures
from research15_evidence import paired_ledger

SEEDS = (3203, 3209, 3217)
DURATIONS = (0, 1, 2, 4, 8, 16)
METHODS = ('ordinary', 'candidate_disagreement', 'raw_difference', 'contract_coverage')
read, dump = loop.read, loop.dump


def stimulus(seed, duration, depth=4, pipeline=1, independent=False):
    rng = random.Random(seed)
    start = rng.randrange(15, 23)
    rows = []
    for c in range(112):
        rows.append(dict(cycle=c, rst=int(c < 2), intent=int(3 <= c < 65),
            ready=int(not start <= c < start+duration), data=rng.getrandbits(32),
            drain_due=int(c == 111)))
    return rows


def stall_length(trace):
    longest = run = 0
    for s in trace:
        run = run+1 if not s['rst'] and s['mvalid'] and not s['mready'] else 0
        longest = max(longest, run)
    return longest


def run(out):
    loop.prepare(out)
    for name in ('research32_runtime.py', 'research32_search.py', 'research28_valid_runtime.py', 'research20_stall_runtime.py'):
        shutil.copy2(loop.ROOT/'scripts'/name, out/'source_snapshot'/name)
    candidates = {n: read(p/'frozen_candidate.json') for n,p in SOURCES.items()}
    for n,c in candidates.items():
        assert loop.sha(c) == read(SOURCES[n]/'freeze.json')['candidate_sha256']
        dump(out/'candidates'/f'{n}.json', c)
    dump(out/'protocol.json', dict(seeds=SEEDS, methods=METHODS, durations=DURATIONS,
        queries_per_method_seed=4, cycles=112, depth=4, pipeline=1,
        common='Same initial/repaired complete model-generated sets, RTL, artificial modes, duration grammar and common no-stall query.',
        contract='After own measured max stall: cover short(1), medium(4), long(16) in ascending uncovered order. These are public duration buckets, not hidden fault threshold lookup.',
        ordinary='Uniform choice of all six durations, with replacement, own seed.',
        score_baselines='With probability .65 exploit own positive historical XOR or raw mismatch score, otherwise uniform exploration.',
        accounting='One query is two candidates x correct/two long faults = six native executions; all failures/duplicates/no-witness charged. Two shared compiles and smoke counted separately.',
        dedup='Initial candidate content hash / obligation / fault mechanism; waves and seeds do not add independent bugs.',
        scope='Exploratory development counter mutation. Not historical repair, independent result, or general search advantage. Original FIFO semantics and port-history oracle unchanged.',
        root_git_commit=None, model_calls=0, formal_calls=0))
    records=[]; acquired=[]; seen=set()
    with extension.installed():
        builds={n:loop.runtime.build(c,out/'compiled'/n,4,1) for n,c in candidates.items()}
        assert all(b['native']['compile_status']=='passed' for b in builds.values())
        for seed in SEEDS:
            for method in METHODS:
                rng=random.Random(seed); history=[]; maximum=0
                for q in range(4):
                    if q==0: duration=0
                    elif method=='contract_coverage':
                        duration=next((n for n in (1,4,16) if n>maximum),16)
                    elif method in ('candidate_disagreement','raw_difference') and rng.random()<.65 and max(h['score'] for h in history)>0:
                        best=max(h['score'] for h in history)
                        duration=rng.choice([h['duration'] for h in history if h['score']==best])
                    else: duration=rng.choice(DURATIONS)
                    rows=stimulus(seed*100+q,duration)
                    folder=out/'core/search'/f's{seed}'/method/f'q{q}'
                    dump(folder/'selection.json',dict(duration=duration,permitted_history=history))
                    modes=('correct',)+extension.MODES
                    runs={n:{m:loop.runtime.execute(builds[n],folder/n/m,rows,m) for m in modes} for n in candidates}
                    healthy=all(r['native']['execution_status']=='completed' and
                        r['native']['tool_support_status']=='supported_for_compiled_constructs' and
                        r['sampling_qualification']['status']=='passed' and r['oracle']['legality']=='legal' and not r['oracle']['unknown']
                        for rr in runs.values() for r in rr.values())
                    healthy=healthy and all(not runs[n]['correct']['native']['failures'] and not runs[n]['correct']['oracle']['violations'] for n in candidates)
                    gaps=[]; later=unknown=0
                    for mode in extension.MODES:
                        case=dict(id=f'long32:s{seed}:{method}:q{q}:{mode}', depth=4,pipeline=1,
                            rows=rows,mode=mode,split='development',source='research32_native_search',
                            dedup_class='stall_stability:'+mode,target_obligation='stall_stability')
                        group=paired_ledger(runs['initial']['correct'],runs['initial'][mode],case['id'])
                        dump(folder/'ledgers'/f'{mode}.json',group)
                        info=loop.inspect(group['ledger']);unknown+=len(info['unknown']);later+=len(group['exclusions'])
                        for k in sorted(info['misses']):
                            row=info['rows'][k]
                            key=f"{loop.sha(candidates['initial'])}/{row['obligation']}/{mode}"
                            gaps.append(dict(key=key,evidence=row,case=case,source=str(folder/'initial'/mode)))
                            select=(seed,mode)
                            if healthy and method=='contract_coverage' and row['obligation']=='stall_stability' and select not in seen:
                                seen.add(select);acquired.append(case)
                    xor=sum(len(failures(runs['initial'][m]) ^ failures(runs['repaired'][m])) for m in modes)
                    diff=sum(any(a[k]!=b[k] for k in ('mvalid','mdata')) for m in extension.MODES
                        for a,b in zip(runs['initial']['correct']['trace'],runs['initial'][m]['trace']))
                    measured=stall_length(runs['initial']['correct']['trace'])
                    maximum=max(maximum,measured)
                    view=dict(duration=duration)
                    if method=='contract_coverage':view.update(maximum_stall=maximum)
                    elif method!='ordinary':view.update(score=xor if method=='candidate_disagreement' else diff)
                    history.append(view)
                    record=dict(seed=seed,method=method,query=q,duration=duration,healthy=healthy,
                        gaps=gaps if healthy else [],unqualified_gap_rows=[] if healthy else gaps,
                        independent_gap_keys=sorted({g['key'] for g in gaps}) if healthy else [],
                        permitted_view=view,judge_only=dict(xor=xor,raw_difference=diff,max_stall=measured),
                        unknown=unknown,later_attribution_unknown=later,native_executions=6)
                    records.append(record);dump(folder/'result.json',record);dump(out/'results.json',records)
                    print(seed,method,q,duration,len(record['independent_gap_keys']),flush=True)
    dump(out/'acquired_cases.json',acquired)
    summary=[]
    for seed in SEEDS:
        keys={m:{k for r in records if r['seed']==seed and r['method']==m for k in r['independent_gap_keys']} for m in METHODS}
        summary.append(dict(seed=seed,methods={m:dict(gaps=sorted(keys[m]),extra_vs_ordinary=sorted(keys[m]-keys['ordinary'])) for m in METHODS}))
    dump(out/'summary.json',summary)
    dump(out/'outcome.json',dict(status='native_search_completed',queries=len(records),
        all_healthy=all(r['healthy'] for r in records),acquired=len(acquired),model_calls=0))
    dump(out/'source_snapshot/hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'source_snapshot').glob('*.py')})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();assert loop.ROOT in out.parents
    run(out)
