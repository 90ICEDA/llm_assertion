"""Recompute native FIFO references and exact active rankings from saved logs."""
import argparse
from pathlib import Path
import re
import sys
import time

import research193_active_native as run

b=run.b


def audit(out):
    for name,digest in b.read(out/'sealed.json').items():
        assert b.digest(out/name)==digest,name
    # The inherited snapshot inventories all research scripts, including other
    # agents' unrelated work. Require exact hashes for every imported execution
    # dependency, while reporting unrelated changes rather than hiding them.
    imported={Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None)}
    unrelated_changes=[]
    for name,digest in b.read(out/'code_versions.json').items():
        source=(b.ROOT/name).resolve()
        if b.digest(source)!=digest:
            assert source not in imported, 'actual imported dependency changed: '+name
            unrelated_changes.append(name)
    assert b.read(out/'outcome.json')['status']=='completed'
    public=b.read(out/'public_feedback.json');records=b.read(out/'records.json')
    candidates={n:b.read(out/'candidates'/(n+'.json')) for n in run.NAMES}
    entries=[(out/'public'/f'q{i}',r) for i,r in enumerate(public)]
    entries.extend((out/'queries'/f"s{r['seed']}"/r['method']/f"q{r['query']}",r) for r in records)
    begin=time.perf_counter();count=0;ledgers=0
    with b.extension.installed():
        for folder,result in entries:
            rr={}
            for n in run.NAMES:
                rr[n]={}
                for mode in b.MODES:
                    path=folder/n/mode;r=b.read(path/'replay.json');rr[n][mode]=r
                    trace=b.extension.runtime.parse_trace(path/'execute.log')
                    refs=b.loop.runtime.parse_reference(path/'execute.log')
                    assert trace==r['trace'] and refs==r['reference_trace']
                    rows=b.read(folder/n/(mode+'_stimulus')/'stimulus.json')
                    if isinstance(rows,dict):rows=rows['rows']
                    assert b.extension.runtime.oracle(trace,rows)==r['oracle']
                    assert b.loop.runtime.qualify_sampling(trace,refs)==r['sampling_qualification']
                    log=(path/'execute.log').read_text()
                    for field,marker in (('failures','ASSERT_FAIL'),('triggers','TRIGGER')):
                        parsed={(m[0],int(m[1])) for m in re.findall(r'^'+marker+r' (\S+) cycle=(-?\d+)',log,re.M)}
                        stored={(m['id'],int(re.search(r'cycle=(-?\d+)',m['detail'])[1])) for m in r['native'][field]}
                        assert parsed==stored
                    assert 'NATIVE_RUN_COMPLETE' in log and (path/'wave.vcd').stat().st_size>0
                    count+=1
            confirmed=[]
            for mode in b.MODES[1:]:
                group=b.evidence.paired_ledger(rr['bounded']['correct'],rr['bounded'][mode],str(folder.relative_to(b.ROOT))+':'+mode)
                saved=b.read(folder/'judgements'/(mode+'.json'))
                assert group['stats']==saved['stats'] and group['exclusions']==saved['exclusions']
                info=b.loop.inspect(group['ledger'])
                for key in sorted(info['misses']):
                    row=info['rows'][key];v=b.prior.validate_gap(row,rr['bounded']['correct'],rr['bounded'][mode])
                    if result['healthy'] and result['correct_accepts']['bounded'] and v['valid']:
                        confirmed.append((b.key(candidates['bounded'],'FN',row['obligation'],mode),key))
                ledgers+=1
            assert sorted(confirmed)==sorted((g['key'],g['evidence']['evidence_id']) for g in result['gaps'] if g['kind']=='FN')
            fps=set()
            if result['healthy']:
                fault_class='legal_reset' if result['family']=='reset_pending' else 'legal_stall' if result['family']=='backpressure' else 'legal_transaction'
                markers=b.evidence.marker_map(rr['bounded']['correct']['native'],'failures')
                for assertion in rr['bounded']['correct']['candidate']['assertions']:
                    if markers.get(assertion['id']):
                        for obligation in assertion['obligations']:
                            fps.add(b.key(candidates['bounded'],'FP',obligation,fault_class))
            assert set(result['gap_keys'])=={key for key,_ in confirmed}|fps
            xor=sum(len(b.prior.failures(rr['bounded'][m])^b.prior.failures(rr['valid'][m])) for m in b.MODES)
            assert xor==result['candidate_disagreement_count']
    selection_count=0
    for seed in run.SEEDS:
        selector=run.active.ActiveSelector(run.descriptions(candidates),list(b.grammar.OBLIGATIONS))
        def observe(r):
            selector.observe(f"{r['family']}:{r['duration']}",'confirmed' if r['healthy'] else 'unknown',
                list(r['fixed_obligation_checks']),r['gap_keys'],r['native_executions'],[o for o,n in r['causal_protected'].items() if n>0])
        for r in public:observe(r)
        for r in sorted((r for r in records if r['seed']==seed and r['method']=='S3'),key=lambda r:r['query']):
            chosen=selector.select(run.options())
            saved=b.read(out/'queries'/f's{seed}'/'S3'/f"q{r['query']}"/'selection.json')
            assert chosen==saved['decision'];observe(r);selection_count+=1
    result=dict(passed=True,native_logs_verified=count,paired_ledgers_recomputed=ledgers,
                active_selections_replayed=selection_count,wall_seconds=time.perf_counter()-begin,
                new_native_executions=0,model_calls=0,unrelated_parallel_source_changes=unrelated_changes,
                execution_dependency_hashes_match=True,scope='Read-only audit; costs separate from selection experiments')
    b.dump(out/'audit.json',result);print(result,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();audit(a.out.resolve())
