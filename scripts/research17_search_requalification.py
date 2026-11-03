"""Read-only requalification of archived development search; no model/test access.

validate_witness(candidate_path, witness_path) returns an explicit qualified flag.
It recomputes the independent transaction oracle from archived native trace logs;
it does not execute RTL and must not be described as a new native experiment.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SEARCH = ROOT/'deliverables/research16_ablation_20261016_r02/search'
OUT = ROOT/'deliverables/research17_search_audit_20261016_r02'

def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def resolve(path):
    text=str(path).replace('\\','/')
    marker='/AssertionForge-main1/'
    if marker in text:
        return ROOT/text.split(marker,1)[1]
    return Path(path)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def signature(candidate):
    return [(a['id'],a['property'],sorted(a.get('obligations',[]))) for a in candidate['assertions']]

def cycle(event):
    match=re.search(r'cycle=(-?\d+)',event.get('detail',''))
    return int(event['cycle']) if 'cycle' in event else int(match[1]) if match else None

def validate_witness(candidate_path, witness_path):
    """Fail closed for missing artifacts, mismatched candidates, or unknown checks.

    The input candidate must be the candidate actually compiled for this archived
    witness. Revisions need new native replays and cannot reuse old observations.
    """
    from research15_search_runtime import oracle, parse_trace
    from research15_native_interface import normalize_candidate
    result=dict(qualified=False,status='unknown',checks={},errors=[],scope='archived development evidence only; finite simulation; artificial FIFO boundary fault')
    try:
        candidate_path=resolve(candidate_path);witness_path=resolve(witness_path)
        witness=read(witness_path)
        if not witness:
            result['errors'].append('No witness exported');return result
        candidate=normalize_candidate(read(candidate_path))
        runs={}; artifacts={str(candidate_path):digest(candidate_path),str(witness_path):digest(witness_path)}
        for key,field in [('fixed','fixed_replay'),('buggy','mutant_replay')]:
            folder=resolve(witness[field]);record=read(folder/'replay.json')
            log=folder/'execute.log'
            if not log.exists():log=folder/'run.log'
            trace=parse_trace(log);ref=oracle(trace,witness['rows'])
            native=read(folder/'result.json')
            runs[key]=dict(trace=trace,oracle=ref,native=native,candidate=record['candidate'],folder=str(folder))
            for p in (log,folder/'replay.json',folder/'result.json',folder/'wave.vcd'):
                artifacts[str(p)]=digest(p)
            result['checks'][key+'_candidate_identity']=signature(candidate)==signature(record['candidate'])
            result['checks'][key+'_native_completed']=(native.get('compile_status')=='passed' and native.get('execution_status')=='completed' and native.get('tool_support_status')=='supported_for_compiled_constructs' and 'native cover property' in native.get('trigger_measurement',''))
            result['checks'][key+'_trace_and_oracle_reproduced']=trace==record['trace'] and ref==record['oracle']
            result['checks'][key+'_legal_and_known']=ref['legality']=='legal' and not ref['unknown']
        fixed,buggy=runs['fixed'],runs['buggy'];target=witness['first_violation'];c=target['cycle'];ob=target['obligation']
        inputs=('cycle','rst','svalid','sready','sdata','mready')
        result['checks']['identical_actual_input_schedule']=[{k:t[k] for k in inputs} for t in fixed['trace']]==[{k:t[k] for k in inputs} for t in buggy['trace']]
        result['checks']['fixed_contract_passes']=not fixed['oracle']['violations']
        result['checks']['fixed_same_obligation_checked']=any(v['obligation']==ob and v['cycle']==c and v['passed'] for v in fixed['oracle']['checks'])
        violations=[v for v in buggy['oracle']['violations'] if v['cycle']==c and v['obligation']==ob]
        result['checks']['buggy_target_violation']=bool(violations)
        result['checks']['first_violation']=bool(buggy['oracle']['violations']) and min(v['cycle'] for v in buggy['oracle']['violations'])==c
        result['checks']['fixed_candidate_no_alarm']=not fixed['native']['failures']
        result['checks']['buggy_candidate_no_alarm_through_target']=not any(cycle(e) is None or cycle(e)<=c for e in buggy['native']['failures'])
        result['checks']['bounded_parameter_scope']=2<=witness['depth']<=8 and 0<=witness['pipeline']<=2
        triggers=[]
        for a in candidate['assertions']:
            times=[cycle(e) for e in buggy['native']['triggers'] if e['id']==a['id']]
            triggers.append(dict(assertion_id=a['id'],obligations=a['obligations'],native_trigger_cycles=times,trigger_at_target_antecedent=c-a.get('derived_delay',0) in times,total_triggers=len(times)))
        tids=set(t for v in violations for t in v.get('outstanding',[]))|{v['transaction_id'] for v in violations if v.get('transaction_id')}
        mapping=[dict(transaction_id=tid,fixed=next((t for t in fixed['oracle']['transactions'] if t['transaction_id']==tid),None),buggy=next((t for t in buggy['oracle']['transactions'] if t['transaction_id']==tid),None)) for tid in sorted(tids)]
        result['checks']['target_transactions_identified']=bool(mapping) and all(t['fixed'] is not None and t['buggy'] is not None and t['fixed']['accept_cycle']==t['buggy']['accept_cycle'] and t['fixed']['data']==t['buggy']['data'] for t in mapping)
        result.update(target_obligation=ob,target_cycle=c,source_method=witness['source_method'],source_query_directory=str(resolve(witness['source_query_directory'])),parameters=dict(depth=witness['depth'],pipeline=witness['pipeline']),transaction_mapping=mapping,assertion_triggers=triggers,independent_target_violations=violations,drain_scope=buggy['oracle']['drain_scope'],cost=witness['actual_query_cost'],artifact_sha256=artifacts)
        result['miss_classification']='unprotected_obligation' if not any(ob in a['obligations'] for a in candidate['assertions']) else 'no_trigger_at_violation' if not any(t['trigger_at_target_antecedent'] for t in triggers if ob in t['obligations']) else 'triggered_but_insufficient'
        result['candidate_set_observation']='earlier triggers exist, no trigger at target' if any(t['total_triggers'] for t in triggers) and not any(t['trigger_at_target_antecedent'] for t in triggers) else 'see assertion_triggers'
        result['qualified']=all(result['checks'].values())
        result['status']='qualified_finite_missed_violation' if result['qualified'] else 'rejected_or_unknown'
        result['errors']=[name for name,passed in result['checks'].items() if not passed]
    except (OSError,ValueError,KeyError,TypeError) as exc:
        result['errors'].append(type(exc).__name__+': '+str(exc))
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--search',type=Path,default=SEARCH);ap.add_argument('--out',type=Path,default=OUT);args=ap.parse_args()
    search=args.search;args.out.mkdir(parents=True,exist_ok=False)
    records=read(search/'results.json');protocol=read(search/'protocol.json');summaries=[]
    for method in protocol['methods']:
        subset=[r for r in records if r['method']==method];seen=set();discovery=[];duplicates=0
        for r in subset:
            keys=set(r['evidence']['obligation_gap_keys']);duplicates+=len(keys&seen)
            for key in sorted(keys-seen):
                discovery.append(dict(gap_key=key,source_query=r['folder'],seed=r['seed'],query=r['query'],family=r['selection']['family'],sample=next(e for e in r['evidence']['mapping'] if e['kind']=='false_negative' and f"{e['variant']}/{e['obligation']}"==key)))
            seen|=keys
        summaries.append(dict(method=method,queries=len(subset),native_replays=sum(r['cost']['native_replays'] for r in subset),independent_gap_keys=sorted(seen),first_discoveries=discovery,duplicate_gap_observations_global_method=duplicates,unknown_queries=sum(r['evidence']['status']!='ok' for r in subset),false_positive_classes=sorted({f['semantic_key'] for r in subset for f in r['evidence']['findings'] if f['kind']=='false_positive'}),simulation_wall_seconds=sum(r['cost']['native_simulation_wall_seconds'] for r in subset)))
    contract=set(next(s for s in summaries if s['method']=='contract_coverage')['independent_gap_keys'])
    for s in summaries:s['contract_additional_gap_keys']=sorted(contract-set(s['independent_gap_keys']))
    witness=validate_witness(search/'initial_candidate.json',search/'treatment_witness.json')
    parents=dict(onehot='regression only',fifo_presented='original historical target witness unknown; this audit concerns artificial faults',filter='full native obligation protection not established',stat='synthetic source mapping and timing specification unconfirmed; unknown',spill='local collision-empty evidence only; remaining semantics unknown',intr='mask and timing semantics unknown',ibex54='original RTL module finite reproduction exists; not yet an LLM refinement result',ibex166='original RTL module finite reproduction exists; not yet an LLM refinement result')
    result=dict(source_search=str(search),split='reused development data',new_model_calls=0,new_native_executions=0,formal_calls=0,witness=witness,methods=summaries,cost=read(search/'cost.json'),protocol=protocol,parent_bug_status=parents,parent_status_source=str(ROOT/'deliverables/completion_audit_20261016_r01/REPORT.md'),limit='Single-property candidate-disagreement arm is uniform fallback. Results are small fixed-budget observations, not a demonstrated general search advantage. Reset-cancellation and no-unsolicited-output are distinct obligations for one reset-residue failure mechanism, not two independent parent bugs.')
    (args.out/'audit.json').write_text(json.dumps(result,indent=2)+'\n')
    (args.out/'witness_qualification.json').write_text(json.dumps(witness,indent=2)+'\n')
    lines=['# Archived development search requalification','','No new RTL simulation or model call. No independent holdout read.','',f'Witness qualified: {witness["qualified"]}. Target: {witness.get("target_obligation")}, cycle {witness.get("target_cycle")}.','', '| Method | Queries | Replays | Gap classes | Additional contract classes |','|---|---:|---:|---|---|']
    for s in summaries:lines.append(f'| {s["method"]} | {s["queries"]} | {s["native_replays"]} | {", ".join(s["independent_gap_keys"])} | {", ".join(s["contract_additional_gap_keys"])} |')
    lines+=['','Contract adds drop/drain_no_loss relative to ordinary and raw-difference, but adds none relative to the degenerate disagreement/exploration arm. No general superiority claim.','', 'Target transaction alignment and native trigger details are in witness_qualification.json. The original a0 property checks payload on an output handshake: it triggers on the first three responses but cannot trigger when the fourth response disappears. This is an unprotected drain obligation, not an entirely vacuous candidate.','',result['limit'],'','Costs are historical actual costs, reused once; audit adds zero model/native/formal calls. All evidence remains development data. Artificial output-boundary faults are not the original historical FIFO presented bug.','', 'API: `validate_witness(candidate_path, witness_path)` refuses mismatched candidate replay and unknown checks. A revised candidate requires a new native replay; this API cannot evaluate new SVA from old logs.']
    (args.out/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(dict(witness_qualified=witness['qualified'],errors=witness['errors'],queries=len(records),out=str(args.out))))

if __name__=='__main__':main()
