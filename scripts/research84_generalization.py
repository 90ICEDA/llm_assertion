"""Presealed local transfer study; archived model proposals, never fresh generation."""
import argparse
import copy
import shutil
import time
from pathlib import Path
from unittest.mock import patch

import research64_search_value as b
import research65_search_policy as policy
import research64_native_audit as raw
import research73_discriminating as archive

ROOT, read, dump = b.ROOT, b.read, b.dump
SEEDS = (8401, 8419, 8431)
METHODS = ('ordinary', 'candidate_disagreement', 'raw_difference', 'ordinary_no_repeat', 'contract_novelty')
MODES = b.MODES + ('corrupt', 'duplicate_payload')
BUDGET = 3


def seal(out):
    dump(out/'sealed.json', {p.relative_to(out).as_posix():b.digest(p)
        for p in out.rglob('*') if p.is_file() and p.name != 'sealed.json'})


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    old = {archive.b.interface.executable_hash(read(p)) for p in b.SOURCES.values()}
    inventory = archive.candidates()
    for i, row in enumerate(inventory):
        row['name'] = f'c{i:02d}'
        row['already_in_research82'] = row['executable_hash'] in old
        shutil.copy2(ROOT/row['path'], out/'candidate.tmp')
        (out/'candidates').mkdir(exist_ok=True)
        (out/'candidate.tmp').rename(out/'candidates'/f"{row['name']}.json")
    shutil.copy2(b.SOURCES['valid'], out/'candidates/reference.json')
    shutil.copy2(b.extension.runtime.RTL, out/'axis_fifo.v')
    dump(out/'inventory.json', inventory)
    dump(out/'protocol.json', dict(seeds=SEEDS, methods=METHODS, modes=MODES, budget=BUDGET,
        depth=2, pipeline=1, model_calls=0, formal_calls=0, maximum_search_tasks=2,
        selection='All unique real model proposals research32..48, source order, no outcome filter. Public qualification for every candidate. First two qualified candidates whose executable hash was absent from research82 enter search; all exclusions retained.',
        qualification='Both candidates compile and execute; legal original reference, zero native false alarms on overlap and duration1 backpressure. Qualification is not full protection.',
        new_dimensions='Archived candidates absent from research82; Depth2 instead of Depth4; corruption and duplicated payload modes added to identical mode access for all policies; three new fixed seeds. Mutations already existed in runtime and are not new historical bugs.',
        known_feedback='All public gap keys subtracted before discovery credit; same six remaining family/duration actions available. Policies reused unchanged. Extra discoveries are new to public feedback only.',
        independence='Development generalization comparison, not frozen independent assertion acceptance. No model or assertion edits. No prior independent outcomes used to select candidates or tune policy.',
        limits='Two qualified tasks is an explicit resource cap, not population sampling. Failed eligibility remains in denominator; unselected eligible candidates remain untested. Three seeds measure search scheduling/stimulus variation, NOT model-generation success.',
        accounting='20 fresh native executions/query, no cache; reference/sampling/paired judges timed; shared builds/public qualification separate. No cost assumed for unexecuted queries.',
        dedup='Exact candidate executable eligibility; discoveries by existing candidate hash/FN|FP/obligation/failure mechanism. Long/short variants collapsed; seeds not bugs.',
        stopping='No retries or outcome-driven extension. Compile/qualification failures retained; no model calls. Entire run stops on infrastructure exception and saves partial counts.',
        expected_maximum_search_queries=90, prepared_at=time.time()))
    dump(out/'local_checks.json', dict(policy_checks=policy.tests(), unique=len(inventory)))
    dump(out/'code_versions.json', {p.relative_to(ROOT).as_posix():b.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    seal(out)
    dump(out/'outcome.json', dict(status='prepared'))
    print('SEALED84', len(inventory), 'candidates', flush=True)


def run(out):
    b.verify(out)
    assert read(out/'outcome.json')['status']=='prepared'
    inv=read(out/'inventory.json')
    cs={p.stem:read(p) for p in (out/'candidates').glob('*.json')}
    calls=[]; records=[]; public={}; eligible=[]; start=time.perf_counter()
    dump(out/'outcome.json', dict(status='running'))
    try:
        with b.extension.installed(), patch.object(b, 'MODES', MODES):
            builds={n:b.loop.runtime.build(c,out/'compiled'/n,2,1) for n,c in cs.items()}
            for row in inv:
                n=row['name']; pair=n+'__reference'; pub=[]
                compile_ok=all(builds[x]['native']['compile_status']=='passed' for x in (n,'reference'))
                if compile_ok:
                    for q,(family,duration) in enumerate((('overlap',None),('backpressure',1))):
                        r=b.query(out/'public'/pair/f'q{q}',builds,cs,(n,'reference'),b.schedule(84000+q,family,duration),
                            dict(pair=pair,stage='public',method='common',seed=0,query=q,family=family,duration=duration),calls)
                        pub.append(r)
                good=compile_ok and len(pub)==2 and all(r['healthy'] and all(r['correct_accepts'].values()) for r in pub)
                public[pair]=dict(results=pub,gap_keys=sorted({k for r in pub for k in r['gap_keys']}))
                eligible.append(dict(pair=pair,qualified=good,already_in_research82=row['already_in_research82'],
                    compile_ok=compile_ok, selected=False, failure=None if good else 'compile/reference/false-positive public qualification'))
                print('QUALIFY84', pair, good, flush=True)
            selected=[e for e in eligible if e['qualified'] and not e['already_in_research82']][:2]
            for e in selected:e['selected']=True
            dump(out/'qualification.json', eligible);dump(out/'public_feedback.json', public)
            dump(out/'public_freeze.json', dict(sha256=b.digest(out/'public_feedback.json'),at=time.time()))
            dump(out/'reference_costs.json', calls);dump(out/'records.json', records)
            for e in selected:
                pair=e['pair']; names=tuple(pair.split('__'))
                for seed in SEEDS:
                    for method in METHODS:
                        p=policy.factory(method,seed); history=[]; seen=set(public[pair]['gap_keys'])
                        for r in public[pair]['results']:history.append(policy.update(p,method,r['family'],r))
                        for q in range(BUDGET):
                            path=out/'queries'/pair/f's{seed}'/method/f'q{q}'
                            t=time.perf_counter();chosen=policy.decision(p,method,seed,q,history);elapsed=time.perf_counter()-t
                            dump(path/'selection.json',dict(chosen=chosen,permitted_history=history))
                            r=b.query(path,builds,cs,names,b.schedule(seed*100+q,chosen['family'],chosen['duration']),
                                dict(pair=pair,stage='search',method=method,seed=seed,query=q,family=chosen['family'],duration=chosen['duration']),calls)
                            r.update(public_unexposed_keys=sorted(set(r['gap_keys'])-set(public[pair]['gap_keys'])),
                                first_new_keys=sorted(set(r['gap_keys'])-seen),selector_seconds=elapsed)
                            seen.update(r['gap_keys']);history.append(policy.update(p,method,r['family'],r))
                            dump(path/'result.json',r);records.append(r)
                            dump(out/'records.json',records);dump(out/'reference_costs.json',calls)
                            print('QUERY84',pair,seed,method,q,'new',len(r['first_new_keys']),flush=True)
        b.verify(out)
        dump(out/'outcome.json',dict(status='completed',queries=len(records),qualified=sum(e['qualified'] for e in eligible),
            selected=len(selected),inventory=len(inv),elapsed_seconds=time.perf_counter()-start,model_calls=0,formal_calls=0))
    except BaseException as exc:
        dump(out/'outcome.json',dict(status='interrupted',error=repr(exc),queries=len(records)))
        raise
    finally:
        dump(out/'reference_costs.json',calls)
    report(out)


def report(out):
    b.verify(out)
    rr=read(out/'records.json');public=read(out/'public_feedback.json');calls=read(out/'reference_costs.json')
    assert b.digest(out/'public_feedback.json')==read(out/'public_freeze.json')['sha256']
    units=[]
    for e in read(out/'qualification.json'):
        if not e['selected']:continue
        pair=e['pair']
        for seed in SEEDS:
            for method in METHODS:
                rows=[r for r in rr if (r['pair'],r['seed'],r['method'])==(pair,seed,method)]
                assert len(rows)==BUDGET
                p=policy.factory(method,seed);h=[];seen=set(public[pair]['gap_keys']);first={};actions=set();repeats=0
                for r in public[pair]['results']:
                    h.append(policy.update(p,method,r['family'],r));actions.add((r['family'],r['duration']))
                for q,r in enumerate(rows):
                    choice=policy.decision(p,method,seed,q,h)
                    saved=read(out/'queries'/pair/f's{seed}'/method/f'q{q}/selection.json')
                    assert choice==saved['chosen'] and h==saved['permitted_history']
                    assert r['first_new_keys']==sorted(set(r['gap_keys'])-seen)
                    for k in r['first_new_keys']:first[k]=q+1
                    action=(r['family'],r['duration']);repeats+=action in actions;actions.add(action)
                    seen.update(r['gap_keys']);h.append(policy.update(p,method,r['family'],r))
                units.append(dict(pair=pair,seed=seed,method=method,first_query=first,found=bool(first),keys=sorted(first),
                    queries=len(rows),repeats=repeats,unknown=sum(r['unknown'] for r in rows),
                    later_unknown=sum(r['later_attribution_unknown'] for r in rows),failed_queries=sum(not r['healthy'] for r in rows)))
    totals={m:dict(keys=sorted({k for u in units if u['method']==m for k in u['keys']}),
        successful_tasks=sum(u['found'] for u in units if u['method']==m),tasks=sum(u['method']==m for u in units),
        queries=sum(u['queries'] for u in units if u['method']==m),unknown=sum(u['unknown'] for u in units if u['method']==m),
        later_unknown=sum(u['later_unknown'] for u in units if u['method']==m),repeats=sum(u['repeats'] for u in units if u['method']==m)) for m in METHODS}
    paired=[]
    for c in [u for u in units if u['method']=='contract_novelty']:
        for other in [u for u in units if u['pair']==c['pair'] and u['seed']==c['seed'] and u['method']!='contract_novelty']:
            common=set(c['keys'])&set(other['keys'])
            paired.append(dict(pair=c['pair'],seed=c['seed'],comparator=other['method'],
                contract_only=sorted(set(c['keys'])-set(other['keys'])),other_only=sorted(set(other['keys'])-set(c['keys'])),
                earlier=sum(c['first_query'][k]<other['first_query'][k] for k in common),
                tied=sum(c['first_query'][k]==other['first_query'][k] for k in common),
                later=sum(c['first_query'][k]>other['first_query'][k] for k in common)))
    extra=sorted(set(totals['contract_novelty']['keys'])-set().union(*(set(totals[m]['keys']) for m in METHODS if m!='contract_novelty')))
    cost=b.native_cost(out)
    expected=sum(r['native_executions'] for r in rr)+sum(r['native_executions'] for p in public.values() for r in p['results'])
    dump(out/'cost.json',cost);dump(out/'units.json',units);dump(out/'paired.json',paired)
    dump(out/'summary.json',dict(methods=totals,extra_over_all=extra,reference_calls=len(calls),
        reference_seconds_by_kind={k:sum(c['wall_seconds'] for c in calls if c['kind']==k) for k in {c['kind'] for c in calls}},
        expected_query_native_executions=expected,physical_native=cost['total'],
        scope='Archived-candidate search transfer only. No new model acceptance, recovery, independent acceptance or cross-parent mechanism benefit inferred.'))
    print('SUMMARY84', {m:len(v['keys']) for m,v in totals.items()}, 'extra',len(extra),flush=True)


def audit(out,destination):
    # Existing auditor recomputes every saved trace/oracle/witness; policy replay above is separate.
    with b.extension.installed(), patch.object(b,'MODES',MODES):
        raw.audit(out,destination)
    report(out)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action',choices=('prepare','run','report','audit'))
    ap.add_argument('--out',type=Path,required=True);ap.add_argument('--audit-out',type=Path)
    a=ap.parse_args()
    if a.action=='audit':audit(a.out.resolve(),a.audit_out.resolve())
    else:globals()[a.action](a.out.resolve())
