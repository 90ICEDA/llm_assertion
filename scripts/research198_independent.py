"""Fresh fault instances and inputs, constructed only after population freeze."""
import argparse
import copy
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump
from research195_refinement_adapter import clone
import research197_cases as cases

FAULTS={
    cases.IDS[0]:dict(id='expiry_early',site='valid_state_zero_test',operator='early_expiry',obligation='exact_latency',
        search='if (count_out == 0) begin',replace='if (count_out == 1) begin',count=1),
    cases.IDS[1]:dict(id='destructive_peek',site='fullbw0_output_pop',operator='ignore_pop_enable',obligation='transaction_match',
        search='if (oup_pop_i) begin',replace="if (1'b1) begin",count=2),
    cases.IDS[2]:dict(id='load_does_not_clear_sticky',site='sticky_clear_condition',operator='remove_load_exception',obligation='clear_load_reset',
        search='if (clear_i || load_i) begin',replace='if (clear_i) begin',count=1)}

def register(out,p):
    entries=[dict(id=e['id'],case_id=e['case_id'],seed=e['seed'],search_strategy=e['search'],strategy=e['strategy'],policy=e['policy']) for e in p['entries']]
    dump(Path(out)/'acceptance_registration.json',dict(entries=entries,source_bindings=p['source_bindings'],faults=FAULTS,
        independent_seeds=[19881,19893],inputs_constructed=False,
        qualification='Every reserved instance must compile, execute and have independently confirmed reachable violation. Non-exposure/unknown are reported, not replaced by another favorable mutant.'))

def runtime(registration):
    m=cases.runtime();original=m._sources
    def sources(cid,folder,fault):
        if fault!=FAULTS[cid]['id']:return original(cid,folder,fault)
        paths=original(cid,folder,'correct');p=paths[0];text=p.read_text();f=FAULTS[cid]
        if text.count(f['search'])!=f['count']:raise ValueError('reserved_site_changed')
        p.write_text(text.replace(f['search'],f['replace'],1));return paths
    def queries(cid,split='development',seed=19407):
        mapping={19407:19881,19419:19893} if split=='independent' else {19407:19711,19419:19723}
        pool=cases.query_pool(cid,split,mapping.get(seed,seed))
        if split=='independent':
            pool=copy.deepcopy(pool)  # all four query families, preregistered
            for q in pool:
                q['rows']=[copy.deepcopy(q['rows'][0]) for _ in range(11)]+q['rows']
                q['semantic_key']=cases.digest(q['rows']);q['id']=cid+'/r198_reserved/'+q['semantic_key'][:16]
        return pool
    m._sources=sources;m.query_pool=queries
    m.FAULTS={cid:[dict(id='primary',split='development',site='original',operator='historical_or_injected'),dict(FAULTS[cid],split='independent')] for cid in cases.IDS}
    independent=clone('research194_independent');independent.cases=m;independent.REGISTRATION=Path(registration)
    independent.SOURCE_NAMES=(*independent.SOURCE_NAMES,'research197_cases.py','research198_independent.py')
    return independent

def run(prepared,execution,out):
    from research198_prepare import verify
    p=verify(prepared);out=Path(out)
    if read(Path(execution)/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('all_versions_must_freeze')
    if out.exists():raise ValueError('immutable_acceptance')
    entries=[dict(id=e['id'],case_id=e['case_id'],seed=e['seed'],search_strategy=e['search'],strategy=e['strategy'],policy=e['policy'],
        folder=str((Path(execution)/e['id']/'refinement').resolve().relative_to(ROOT))) for e in p['entries']]
    module=runtime(Path(prepared)/'acceptance_registration.json')
    module.freeze(entries,len(entries),out/'freeze.json');module.execute(out/'freeze.json',out/'native')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('prepared','execution','out'):p.add_argument('--'+k,type=Path,required=True)
    a=p.parse_args();run(a.prepared,a.execution,a.out)
