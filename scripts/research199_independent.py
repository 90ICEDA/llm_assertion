"""Register unseen instances; construct/grade only after both cohorts freeze."""
from pathlib import Path
import copy
from research195_refinement_adapter import clone
from research194_refinement_runner import ROOT,read,dump
import research197_cases as cases

FAULTS={
 cases.IDS[0]:dict(id='reserved_payload_corruption',site='delayed_branch_payload_assignment',operator='payload_bit_flip',obligation='handshake_payload',
    search='assign payload_o = payload_i;',replace="assign payload_o = payload_i ^ payload_t'(1);",count=2,occurrence=1),
 cases.IDS[1]:dict(id='reserved_empty_state',site='empty_output',operator='complement_empty_flag',obligation='queue_state',
    search='assign empty_o = empty;',replace='assign empty_o = !empty;',count=1,occurrence=0),
 cases.IDS[2]:dict(id='reserved_sticky_next_state',site='sticky_default_next_state',operator='clear_instead_of_hold',obligation='sticky_hold',
    search='overflow_d = overflow_q;',replace="overflow_d = 1'b0;",count=1,occurrence=0)}

def mutate(text,f):
    if text.count(f['search'])!=f['count']:raise ValueError('reserved_site_changed')
    pieces=text.split(f['search']);i=f['occurrence']
    return f['search'].join(pieces[:i+1])+f['replace']+f['search'].join(pieces[i+1:])

def register(out,p):
    dump(Path(out)/'acceptance_registration.json',dict(entries=[dict(id=e['id'],case_id=e['case_id'],seed=e['seed'],search_strategy=e['search'],strategy=e['strategy'],arm=e['arm'],cohort=e['cohort']) for e in p['entries']],
        source_bindings=dict(p['source_bindings']),faults=FAULTS,independent_seeds=[19981,19993],inputs_constructed=False,
        contamination='R197/R198 reserved instances are diagnostic, excluded from unseen claims. New sites/instances, not necessarily unseen behavioral fault families.',
        qualification='Retain all registered instances. Compile/reachability/unknown/unexposed reported independently of assertion verdict; never swap a poorly performing mutant.'))

def runtime(registration):
    m=cases.runtime();original=m._sources
    def sources(cid,folder,fault):
        if fault!=FAULTS[cid]['id']:return original(cid,folder,fault)
        paths=original(cid,folder,'correct');p=paths[0];p.write_text(mutate(p.read_text(),FAULTS[cid]));return paths
    def queries(cid,split='development',seed=19407):
        mapping={19407:19981,19419:19993} if split=='independent' else {19407:19711,19419:19723}
        pool=cases.query_pool(cid,split,mapping.get(seed,seed))
        if split=='independent':
            pool=copy.deepcopy(pool)
            for q in pool:
                q['rows']=[copy.deepcopy(q['rows'][0]) for _ in range(13)]+q['rows']
                q['semantic_key']=cases.digest(q['rows']);q['id']=cid+'/r199_reserved/'+q['semantic_key'][:16]
        return pool
    m._sources=sources;m.query_pool=queries
    m.FAULTS={cid:[dict(id='primary',split='development',site='original',operator='historical_or_injected'),dict(FAULTS[cid],split='independent')] for cid in cases.IDS}
    mod=clone('research194_independent');mod.cases=m;mod.REGISTRATION=Path(registration)
    mod.SOURCE_NAMES=(*mod.SOURCE_NAMES,'research197_cases.py','research199_independent.py');return mod

def run(prepared,execution,out):
    from research199_prepare import verify
    p=verify(prepared);out=Path(out)
    if read(Path(execution)/'outcome.json')['status']!='completed_all_versions_frozen':raise ValueError('all_cohorts_must_freeze')
    entries=[dict(id=e['id'],case_id=e['case_id'],seed=e['seed'],search_strategy=e['search'],strategy=e['strategy'],arm=e['arm'],cohort=e['cohort'],
        folder=str((Path(execution)/e['id']/'refinement').resolve().relative_to(ROOT))) for e in p['entries']]
    if out.exists():raise ValueError('immutable_acceptance')
    module=runtime(Path(prepared)/'acceptance_registration.json');module.freeze(entries,len(entries),out/'freeze.json');module.execute(out/'freeze.json',out/'native')
