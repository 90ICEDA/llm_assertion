"""Post-run audit of four-policy search; never changes frozen raw query records."""
import argparse
import collections
import csv
import json
from pathlib import Path

import research_search_compare as e


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--run',default='research_search_20261014_r01');a=ap.parse_args()
    if Path(a.run).name!=a.run or a.run in ('.','..'):ap.error('run must be a directory name')
    e.OUT=e.x.ROOT/'deliverables'/a.run;e.setup();e.guard()
    out=e.OUT/'audit';out.mkdir(exist_ok=False)
    qs=[json.loads(s) for k in e.CASES for s in (e.OUT/'search'/k/'queries.jsonl').read_text().splitlines()]
    assert len(qs)==864
    cells=collections.Counter((q['case'],q['seed'],q['method']) for q in qs)
    assert len(cells)==72 and set(cells.values())=={12}
    physical=[];transactions=[];pair_gaps={};per_case=[];candidate_executions=[]
    pools={k:e.x.read(e.OUT/'frozen'/k/'candidates.json')['candidates'] for k in e.CASES}
    for k in e.CASES:
        attempts=[json.loads(s)['query_id'] for s in (e.OUT/'search'/k/'attempts.jsonl').read_text().splitlines()]
        assert attempts==[q['query_id'] for q in qs if q['case']==k]
    for q in qs:
        assert len(q['runs'])==2
        assert q['attempted_queries']==1 and q['model_calls']==q['solver_calls']==q['cache_hits']==0
        assert q['spec_status']=='scoped' or not q['evidence']
        d=e.x.read(e.OUT/'frozen'/q['case']/'definition.json')
        for r in q['runs']:
            p=e.x.ROOT/r['run'];raw=e.x.read(p/'result.json')
            assert e.x.sha(p/'rtl.v')==raw['rtl_sha256']
            assert e.x.sha(p/'input.json')==raw['input_sha256']
            physical.append(dict(query_id=q['query_id'],variant=r['variant'],run=r['run'],compile_status=raw['compile']['status'],execution_status=raw['simulate']['status'] if raw['simulate'] else 'not_run',compile_wall_seconds=raw['compile']['wall_seconds'],simulation_wall_seconds=raw['simulate']['wall_seconds'] if raw['simulate'] else None,native_sva_status='not_executed',tool_support='procedural_subset_only',formal_cost=None))
            cc={c['id']:c for c in raw['candidates']}
            for c in pools[q['case']]:
                z=cc.get(c['id'])
                candidate_executions.append(dict(case=q['case'],method=q['method'],seed=q['seed'],query_id=q['query_id'],variant=r['variant'],candidate_id=c['id'],status='procedural_execution_measured' if z else 'unsupported_unknown',trigger_count=z['trigger_count'] if z else None,alarm_count=z['fail_hit'] if z else None,native_sva_status='not_executed'))
        if q['case']=='fifo':
            rows=e.x.read(e.x.ROOT/q['runs'][0]['run']/'input.json')
            epoch=0;pending=None;serial=0
            for r in rows:
                t=r['cycle']
                if not r[d['rst']]:
                    if pending:transactions.append(dict(query_id=q['query_id'],transaction_id=pending['id'],kind='reset_cancelled',cycle=t,accepted=False,**pending['detail']))
                    pending=None;epoch+=1;continue
                if r['push_i']:
                    if pending is None:
                        serial+=1;pending=dict(id=f'fifo:e{epoch}:n{serial}',detail=dict(presented_cycle=t,payload=r['data_i']))
                    assert pending['detail']['payload']==r['data_i']
                    if r['pop_i']:
                        transactions.append(dict(query_id=q['query_id'],transaction_id=pending['id'],kind='accepted',cycle=t,accepted=True,response_cycle=t,**pending['detail']));pending=None
            if pending:transactions.append(dict(query_id=q['query_id'],transaction_id=pending['id'],kind='pending_at_bound',cycle=rows[-1]['cycle'],accepted=False,**pending['detail']))
        for w in q['pair_witnesses']:
            for ob in w['obligations']:
                key=(w['pair_id'],q['method'],w['candidate_id'],w['kind'],ob)
                pair_gaps.setdefault(key,dict(query_id=q['query_id'],**w))
    e.x.dump(out/'physical_runs.json',physical)
    with (out/'candidate_execution.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(candidate_executions[0]));w.writeheader();w.writerows(candidate_executions)
    e.x.dump(out/'candidate_execution_summary.json',dict(total_candidate_variant_queries=len(candidate_executions),unsupported_unknown=sum(z['status']=='unsupported_unknown' for z in candidate_executions),executed_with_trigger=sum(z['trigger_count'] is not None and z['trigger_count']>0 for z in candidate_executions),executed_without_trigger=sum(z['trigger_count']==0 for z in candidate_executions),meaning='trigger and alarm counts from executed procedural checker only; no native SVA trigger or verdict claim'))
    e.x.dump(out/'fifo_transactions.json',transactions)
    e.x.dump(out/'pair_gap_representatives.json',[dict(key=k,witness=v) for k,v in pair_gaps.items()])
    for k in e.CASES:
        summary=[r for r in e.x.read(e.OUT/'parent_method_results.json') if r['case']==k]
        notes=dict(onehot='regression only; all current results finite procedural scope',filter='two unsupported natural candidates retained as unknown; third executable subset',fifo='Depth=0 only; no original presented-defect repair witness may be inferred from idle violation',spill='collision_empty obligation only; invalid data semantics unknown',stat='isolated local-spec events only; overlapping event queries unknown; no original upstream fix',intr='mask timing unknown; no definitive evidence')[k]
        per_case.append(dict(case=k,parent_bug=e.x.IDS[k],original_historical_case=False,whole_parent_pass=False,scope=notes,method_results=summary))
    e.x.dump(out/'six_parent_status.json',per_case)
    hist=e.OLD/'historical_screening/ibex_54';rep=e.x.read(hist/'reproduction.json')
    hashes=rep['hashes'];valid=all(e.x.sha(e.x.ROOT/p)==h for p,h in hashes.items())
    assert valid
    e.x.dump(out/'ibex_prior_evidence_audit.json',dict(source=rep['source']['source'],base_commit=rep['source']['base_commit'],merge_commit=rep['source']['merge_commit'],fix_commits=rep['source']['fix_commits'],prior_source_manifest_verified=valid,prior_admitted=rep['admitted'],new_execution=False,prior_environment=rep['actual_environment'],prior_results=[dict(revision=r['revision'],cohort=r['cohort'],failed_checks=r['failed_checks'],run=r['run']) for r in rep['results']],scope=rep['limitation'],stale_source_json_note='source.json is historical screening state; later reproduction.json supersedes deferred status; raw files are unchanged'))
    errata=dict(raw_handshake_field='queries[].handshake_records[].accepted is a raw push&&pop bit and lacks reset gating; do not use it as accepted-event evidence',authoritative_replacement='audit/fifo_transactions.json gates acceptance on active reset state and tracks stable presented payload through stalls and cancellation',evidence_impact='none: original independent oracle, pair/gap adjudication and search rewards do not consume handshake_records',search_limitation='contract obligation-gap template prioritization counts previous template exposure, not semantic uncovered obligation branches; complete generic gap-targeted solver remains unfinished',cost_limitation='CPU covers evaluation and children; postprocessing CPU unavailable. audit_wall_seconds is separate; aggregate query wall times sum concurrent processes and are not elapsed turnaround time')
    e.x.dump(out/'limitations_and_errata.json',errata)
    e.x.dump(out/'audit_result.json',dict(passed=True,queries=len(qs),cells=len(cells),physical_runs=len(physical),compile_statuses=dict(collections.Counter(r['compile_status'] for r in physical)),execution_statuses=dict(collections.Counter(r['execution_status'] for r in physical)),pair_gap_representatives=len(pair_gaps),fifo_transactions=len(transactions),source_freeze_verified=True,model_calls=0,formal_cost=None,global_nonregression=None,original_rtl_sources='frozen synthetic parent sources, not historical real-RTL cases'))
    report=e.OUT/'REPORT.md'
    text=report.read_text()
    text+='\n## Audit and configurable reproduction\n\nThe complete audit verified 864 queries / 72 cells / 1728 physical RTL runs, frozen source hashes and original raw input hashes. See audit/audit_result.json and physical_runs.json. Existing Ibex original-source/test hashes also match; this is a read-only prior-result audit, not a fresh reproduction.\n\nUse `python3 scripts/research_search_cli.py --run NEW_NAME prepare`, then `run`, then `report`; `python3 scripts/research_search_audit.py --run NEW_NAME` audits the complete result. The CLI wrapper supports new directories without editing frozen code. `--case` permits independent case execution.\n\nRaw handshake annotations omitted reset gating; their name was too strong. The authoritative FIFO transaction ledger is audit/fifo_transactions.json, which records presentation, accepted transfers, reset cancellation and bounded pending status. Gap/pair results do not depend on the erroneous annotation. Full limitations are in audit/limitations_and_errata.json.\n'
    report.write_text(text,encoding='utf-8')
    print(json.dumps(e.x.read(out/'audit_result.json')),flush=True)


if __name__=='__main__':main()
