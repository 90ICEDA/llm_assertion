"""Reserved new mutation sites; all inputs constructed only after model freeze."""
import argparse
import copy
from pathlib import Path
from research195_refinement_adapter import clone
import research194_refinement_runner as common
import research194_ibex as ibex
import research196_cases as development

NEW_FAULTS={
 'arbiter':dict(id='r196_grant_rotate',site='grant_output_assignment',operator='rotate_output',obligation='arbiter_priority',search='assign grant = grant_reg;',replace='assign grant = {grant_reg[2:0],grant_reg[3]};'),
 'counter':dict(id='r196_overflow_slice',site='overflow_output_slice',operator='wrong_bit_slice',obligation='counter_boundary',file=1,search='assign overflow_o = counter_q[Width];',replace='assign overflow_o = counter_q[Width-1];'),
 'uart':dict(id='r196_idle_early',site='idle_output_comparison',operator='premature_idle',obligation='uart_busy',search="assign idle = (tx_enable) ? (bit_cnt_q == 4'h0) : 1'b1;",replace="assign idle = (tx_enable) ? (bit_cnt_q <= 4'h1) : 1'b1;"),
 'ibex_flush':dict(id='r196_stack_destination',site='stack_adjust_destination',operator='wrong_destination_register',obligation='expansion_match',search="instr[11: 7] /* dest reg  */ = 5'd2; // x2 (sp / stack pointer)",replace="instr[11: 7] /* dest reg  */ = 5'd3; // injected destination defect")}


def runtime(registration):
    ibex.register();adapter=clone('research194_cases');module=clone('research194_independent')
    adapter.CONFIG=copy.deepcopy(adapter.CONFIG);adapter.FAULTS=copy.deepcopy(adapter.FAULTS)
    for cid,f in NEW_FAULTS.items():
        adapter.FAULTS[cid]=[x for x in adapter.FAULTS[cid] if x['split']=='development']+[dict(f,split='independent')]
    original_sources=adapter._sources
    def sources(cid,folder,fault):
        if cid!='ibex_flush' or fault!=NEW_FAULTS[cid]['id']:return original_sources(cid,folder,fault)
        paths=ibex.sources(folder,'correct');p=paths[0];text=p.read_text();f=NEW_FAULTS[cid]
        if text.count(f['search'])!=1:raise ValueError('reserved_mutation_site_changed')
        p.write_text(text.replace(f['search'],f['replace']));return paths
    adapter._sources=sources
    def queries(cid,split='development',seed=19407):
        # Reused verifier's two seed slots map to fresh preregistered seeds.
        mapped=({19407:19683,19419:19697} if split=='independent' else {19407:19607,19419:19619}).get(seed,seed)
        pool=development.query_pool(cid,split,mapped)
        selected=copy.deepcopy(pool[:2] if split=='independent' else pool)
        for q in selected:
            if cid=='ibex_flush' and split=='independent':
                # The old Ibex generator depends only on seed parity. Changing
                # an odd seed alone would silently reuse the old exact input.
                # A preregistered extra reset prefix makes both new seed slots
                # distinct; it does not claim a new protocol scenario family.
                q['rows']=[copy.deepcopy(q['rows'][0]) for _ in range(1+mapped%3)]+q['rows']
                q['semantic_key']=adapter.digest(q['rows'])
                q['id']='r196/'+q['family']+'/'+q['semantic_key'][:12]
            q.setdefault('semantic_key',adapter.digest(q['rows']))
        return selected
    adapter.query_pool=queries
    module.cases=adapter;module.REGISTRATION=Path(registration)
    module.SOURCE_NAMES=(*module.SOURCE_NAMES,'research196_independent.py','research196_cases.py','research195_active_queries.py')
    return module


def register(prepared):
    prepared=Path(prepared);protocol=common.read(prepared/'protocol.json')
    entries=[dict(id=e['id'],case_id=e['case_id'],seed=e['seed'],search_strategy=e['search'],strategy=e['strategy']) for e in protocol['entries']]
    common.dump(prepared/'acceptance_registration.json',dict(entries=entries,source_bindings=protocol['source_bindings'],
        faults=NEW_FAULTS,independent_seeds=[19683,19697],queries_per_case_seed=2,
        ibex_freshness='Original generator uses seed parity only. Add 1+seed%3 initial reset samples before hashing. Fresh exact input, not a new protocol family.',
        scope='64 frozen trajectories plus four initial controls. New exact mutation sites; artificial mutants, not new historical bug fixes. No inputs constructed at registration.'))


def run(prepared,execution,out):
    from research196_campaign import verify
    protocol,_=verify(prepared);out=Path(out)
    if out.exists():raise ValueError('immutable_acceptance_destination')
    completion=common.read(Path(execution)/'outcome.json')
    if completion.get('status')!='completed_all_versions_frozen':raise ValueError('population_not_frozen')
    module=runtime(Path(prepared)/'acceptance_registration.json')
    entries=[dict(id=e['id'],case_id=e['case_id'],seed=e['seed'],search_strategy=e['search'],strategy=e['strategy'],
        folder=str((Path(execution)/e['id']/'refinement').resolve().relative_to(common.ROOT))) for e in protocol['entries']]
    module.freeze(entries,64,out/'freeze.json');module.execute(out/'freeze.json',out/'native')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',type=Path,required=True);p.add_argument('--execution',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.prepared,a.execution,a.out)
