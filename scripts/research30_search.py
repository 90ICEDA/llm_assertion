"""Equal-budget four-policy native search over two whole frozen candidates.

Retrospective mechanism pilot: known research27/28 versions and known artificial
faults. Never equate properties within one set with different candidates.
No LLM requests and no independent-test inputs or results are consumed.
"""
import argparse
from collections import Counter
from pathlib import Path
import shutil
import time
import research17_loop as loop
import research28_valid_runtime as extension
import research15_search_experiment as previous
from research15_evidence import paired_ledger,marker_map

ROOT=loop.ROOT
read,dump=loop.read,loop.dump
METHODS=previous.METHODS
SEEDS=(3113,3119,3121)
SOURCES=dict(initial=ROOT/'deliverables/research27_closed_loop_20261020_r06/core',
             repaired=ROOT/'deliverables/research28_valid_closed_loop_20261020_r01/core')


def failures(record):
    found=marker_map(record['native'],'failures')
    return set().union(*found.values()) if found else set()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--budget',type=int,default=4)
    args=parser.parse_args()
    assert 2<=args.budget<=12
    out=args.out.resolve();assert ROOT in out.parents
    loop.prepare(out)
    for name in ('research30_search.py','research28_valid_runtime.py','research20_stall_runtime.py'):
        shutil.copy2(ROOT/'scripts'/name,out/'source_snapshot'/name)
    import hashlib
    dump(out/'source_snapshot/hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (out/'source_snapshot').iterdir() if p.is_file() and p.name!='hashes.json'})
    candidates={name:read(path/'frozen_candidate.json') for name,path in SOURCES.items()}
    for name,candidate in candidates.items():
        assert loop.sha(candidate)==read(SOURCES[name]/'freeze.json')['candidate_sha256']
        dump(out/'candidates'/f'{name}.json',candidate)
    dump(out/'protocol.json',dict(methods=METHODS,seeds=SEEDS,queries_per_method_seed=args.budget,
        depth=4,pipeline=1,cycles_per_query=112,
        frozen_candidates={name:dict(source=str(SOURCES[name]),hash=loop.sha(c)) for name,c in candidates.items()},
        candidate_disagreement='XOR of whole-set native failure-cycle sets on identical runs of TWO frozen complete candidates, never between assertions inside one set.',
        common_information='Same two frozen candidates, RTL, specification, stimulus grammar, known fault modes and initial overlap query.',
        observations=dict(ordinary='family only',candidate_disagreement='family and whole-candidate native fail XOR count',
            raw_difference='family and correct/faulty output mismatch count',
            contract_coverage='family and own observed independent obligation checks, effective triggers, detected violations and confirmed gap keys'),
        schedule='q0 identical overlap schedule charged to each method. Later families chosen only from own permitted observations by existing Policy.',
        accounting='One query=one 112-cycle schedule, both candidates, correct+7 existing artificial faults: 16 native executions, even when no witness. No caching/retries. Shared 2 compiles charged once as common setup.',
        dedup='Primary candidate hash, FP/FN, obligation, fault mechanism; parameter/seed/cycle/data variants are duplicates. Gap examples retain full transaction traces.',
        exposure='All outputs development. Known historical repair pair deliberately chosen; no blind evaluation, no independent/general superiority claim.',
        legacy_11_pairs='Not reclassified as native: legacy six-parent/11-pair procedural studies remain separate. This pilot uses one true FIFO candidate pair.',
        model_calls=0,formal_calls=0))
    records=[];dump(out/'outcome.json',dict(status='running'))
    try:
        with extension.installed():
            modes=extension.runtime.MODES
            compiled={n:loop.runtime.build(c,out/'compiled'/n,4,1) for n,c in candidates.items()}
            if any(b['native']['compile_status']!='passed' for b in compiled.values()):
                raise RuntimeError('candidate_pair_native_compile_failed')
            for seed in SEEDS:
                for method in METHODS:
                    policy=previous.Policy(method,seed)
                    for q in range(args.budget):
                        choice=policy.choose() if q else dict(family='overlap',target_obligation=None,
                            reason='mandatory common initial feedback',deficit_scores={},history_queries=0)
                        stimulus_seed=seed*1000+q
                        rows=previous.stimulus(stimulus_seed,choice['family'])
                        folder=out/'queries'/f's{seed}'/method/f'q{q}'
                        dump(folder/'selection.json',dict(**choice,stimulus_seed=stimulus_seed,
                            permitted_prior_history=policy.history))
                        runs={}
                        for name in candidates:
                            runs[name]={mode:loop.runtime.execute(compiled[name],folder/name/mode,rows,mode)
                                        for mode in modes}
                        ordinary_fixed=runs['initial']['correct']
                        groups={};gaps=[];target_count=0
                        effective=Counter();protected=Counter()
                        for mode in modes[1:]:
                            scenario=f'compare30:s{seed}:q{q}:{choice["family"]}:{mode}'
                            g=paired_ledger(ordinary_fixed,runs['initial'][mode],scenario)
                            groups[mode]=g
                            dump(folder/'ledgers'/f'{mode}.json',g)
                            info=loop.inspect(g['ledger'])
                            for k in info['triggers']:effective[info['rows'][k]['obligation']]+=1
                            for k in info['detections']:protected[info['rows'][k]['obligation']]+=1
                            target_count+=len(info['detections']|info['misses']|info['unknown'])
                            for kind,keys in (('FN',info['misses']),('FP',info['false_positives'])):
                                for key in sorted(keys):
                                    row=info['rows'][key]
                                    mechanism=mode if row['variant']!='correct' else 'legal_control'
                                    gap_key=f'{loop.sha(candidates["initial"])}/{kind}/{mechanism}/{row["obligation"]}'
                                    gaps.append(dict(gap_key=gap_key,kind=kind,mechanism=mechanism,
                                        obligation=row['obligation'],evidence=row,
                                        replay_directory=str(folder/'initial'/row['variant']),
                                        candidate_hash=loop.sha(candidates['initial'])))
                        disagreement=sum(len(failures(runs['initial'][m]) ^ failures(runs['repaired'][m])) for m in modes)
                        difference=sum(any(a[k]!=b[k] for k in ('mvalid','mdata'))
                            for mode in modes[1:] for a,b in zip(ordinary_fixed['trace'],runs['initial'][mode]['trace']))
                        healthy=all(r['native']['compile_status']=='passed'
                            and r['native']['execution_status']=='completed'
                            and r['native']['tool_support_status']=='supported_for_compiled_constructs'
                            and r['sampling_qualification']['status']=='passed'
                            and r['oracle']['legality']=='legal' and not r['oracle']['unknown']
                            for candidates_runs in runs.values() for r in candidates_runs.values())
                        control_ok=all(not r['oracle']['violations'] and not r['native']['failures']
                                       for r in (runs[n]['correct'] for n in candidates))
                        counts=Counter(c['obligation'] for c in ordinary_fixed['oracle']['checks'])
                        observation=dict(status='ok' if healthy and control_ok else 'unknown',
                            candidate_disagreement_count=disagreement,raw_difference_count=difference,
                            fixed_obligation_checks=dict(counts),effective_native_triggers=dict(effective),
                            causal_protected=dict(protected),
                            obligation_gap_keys=sorted({f"{g['mechanism']}/{g['obligation']}" for g in gaps}))
                        view=policy.update(choice['family'],observation)
                        record=dict(seed=seed,method=method,query=q,family=choice['family'],
                            folder=str(folder),status=observation['status'],
                            gaps=gaps,unique_gap_keys=sorted({g['gap_key'] for g in gaps}),
                            permitted_feedback_view=view,observer_only=observation,
                            unknown_rows=sum(len(loop.inspect(g['ledger'])['unknown']) for g in groups.values()),
                            later_attribution_unknown=sum(len(g['exclusions']) for g in groups.values()),
                            physical_native_executions=2*len(modes),query_cycles=len(rows)*2*len(modes))
                        dump(folder/'result.json',record);records.append(record)
                        dump(out/'results.json',records)
                        print(dict(seed=seed,method=method,q=q,family=choice['family'],
                                   gaps=len(record['unique_gap_keys']),pair_disagreement=disagreement),flush=True)
        dump(out/'outcome.json',dict(status='four_search_methods_completed',queries=len(records),model_calls=0,
            all_queries_ok=all(r['status']=='ok' for r in records)))
    except BaseException as exc:
        dump(out/'outcome.json',dict(status='execution_blocked',error=repr(exc),completed_queries=len(records)))
        raise


if __name__=='__main__':
    main()
