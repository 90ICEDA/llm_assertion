"""Predeclared held-out fault sites. Construct inputs only after all versions freeze."""
from pathlib import Path
import copy
from research195_refinement_adapter import clone
from research194_refinement_runner import ROOT,read,dump,file_hash
import research197_cases as cases

FAULTS={
 cases.IDS[0]:dict(id='test_extra_delay',site='fixed_counter_load',operator='increment_delay_constant',obligation='exact_latency',
   search='assign counter_load = FixedDelay;',replace='assign counter_load = FixedDelay + 1;'),
 cases.IDS[1]:dict(id='test_id_route',site='read_id_select',operator='flip_read_identifier',obligation='transaction_match',
   search='match_in_id = oup_id_i;',replace="match_in_id = oup_id_i ^ 2'b01;"),
 cases.IDS[2]:dict(id='test_sticky_output_gate',site='overflow_output',operator='gate_output_by_enable',obligation='sticky_hold',
   search='assign overflow_o = overflow_q;',replace='assign overflow_o = overflow_q && en_i;')}

def runtime(registration):
    m=cases.runtime();original_sources=m._sources
    def sources(cid,folder,fault):
        if fault!=FAULTS[cid]['id']:return original_sources(cid,folder,fault)
        paths=original_sources(cid,folder,'correct');p=paths[0];s=p.read_text();f=FAULTS[cid]
        if s.count(f['search'])!=1:raise ValueError('reserved_site_changed')
        p.write_text(s.replace(f['search'],f['replace']));return paths
    def queries(cid,split='development',seed=19407):
        mapped=({19407:19781,19419:19793} if split=='independent' else {19407:19711,19419:19723}).get(seed,seed)
        pool=cases.query_pool(cid,split,mapped)
        if split=='independent':
            pool=copy.deepcopy(pool[:2])
            for q in pool:
                q['rows']=[copy.deepcopy(q['rows'][0]) for _ in range(7)]+q['rows']
                q['semantic_key']=cases.digest(q['rows']);q['id']=cid+'/reserved/'+q['semantic_key'][:16]
        return pool
    m._sources=sources;m.query_pool=queries
    m.FAULTS={cid:[dict(id='primary',split='development',site='historical_original_or_data_xor',operator='original_or_xor'),dict(FAULTS[cid],split='independent')] for cid in cases.IDS}
    independent=clone('research194_independent');independent.cases=m;independent.REGISTRATION=Path(registration)
    independent.SOURCE_NAMES=(*independent.SOURCE_NAMES,'research197_independent.py','research197_cases.py');return independent

def register(prepared,protocol):
    entries=[dict(id=e['id'],case_id=e['case_id'],seed=e['seed'],search_strategy=e['search'],strategy=e['strategy']) for e in protocol['entries']]
    dump(Path(prepared)/'acceptance_registration.json',dict(entries=entries,source_bindings=protocol['source_bindings'],faults=FAULTS,
        independent_seeds=[19781,19793],inputs_constructed=False,scope='Reserved exact mutation sites and new inputs; same three parent cases, not new historical bugs.'))

def run(prepared,execution,out):
    from research197_prepare import verify
    p=verify(prepared);out=Path(out)
    if read(Path(execution)/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('all_models_must_freeze')
    if out.exists():raise ValueError('immutable_acceptance')
    module=runtime(Path(prepared)/'acceptance_registration.json')
    entries=[dict(id=e['id'],case_id=e['case_id'],seed=e['seed'],search_strategy=e['search'],strategy=e['strategy'],folder=str((Path(execution)/e['id']/'refinement').resolve().relative_to(ROOT))) for e in p['entries']]
    module.freeze(entries,len(entries),out/'freeze.json');module.execute(out/'freeze.json',out/'native')

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser()
    for k in ('prepared','execution','out'):ap.add_argument('--'+k,required=True,type=Path)
    a=ap.parse_args();run(a.prepared,a.execution,a.out)
