"""Freeze first, then execute the fixed variable-cost development experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import time

import research194_cases as cases
import research195_active_queries as queries
import research195_active_search as active

ROOT=Path(__file__).resolve().parents[1]
SEEDS=(19507,19519)


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(out):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    files=[p for p in (ROOT/'scripts').glob('research195_active*.py')]
    files += [ROOT/'scripts'/n for n in ('research194_cases.py','research194_active_search.py','research194_active_semantics.py','research194_active_analysis.py','research194_metrics.py','research_native_runner.py')]
    files += [ROOT/p for c in queries.CASES for p in cases.get_case(c)['sources']]
    files += [ROOT/'external/common_cells/include/common_cells'/p for p in ('registers.svh','deprecated/registers.svh')]
    bindings={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(files))}
    for p in sorted(set(files)):
        target=out/'source_snapshot'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
    pools={f'{case}/{seed}':queries.query_pool(case,seed) for case in queries.CASES for seed in SEEDS}
    order=[]
    for case in queries.CASES:
        for seed in SEEDS:
            arms=list(active.STRATEGIES);random.Random(seed).shuffle(arms)
            order.extend(dict(case_id=case,seed=seed,strategy=s) for s in arms)
    protocol=dict(version='r195_variable_cost_v1',cases=list(queries.CASES),seeds=list(SEEDS),strategies=list(active.STRATEGIES),
        max_queries_per_unit=4,reserved_cycle_budget_per_unit=4*2*max(queries.LENGTHS),
        expected_main_queries=48,expected_main_native_jobs=96,expected_calibration_native_jobs=12,expected_baseline_native_jobs=4,
        total_expected_native_jobs=112,run_order=order,query_pools=pools,query_pool_hashes={k:cases.digest(v) for k,v in pools.items()},
        schedule_coverage={k:[queries.coverage(q) for q in pool] for k,pool in pools.items()},
        initial_candidates={c:cases.get_case(c)['initial'] for c in queries.CASES},candidate_pools={c:cases.get_case(c)['candidate_pool'] for c in queries.CASES},
        calibration=dict(seed=19501,lengths=list(queries.LENGTHS),family='first declared family per design',feedback_visible_to_search=False,
            predictor='nonnegative affine native-wall fit for diagnostics; score denominator is exact submitted sampled cycles, not learned wall time'),
        public_baseline=dict(seed=19500,length=min(queries.LENGTHS),family='first declared family per design',
            shared_physical_queries=2,logical_native_jobs_per_trajectory=2,physical_cost_accounted_separately=True),
        selection=dict(active='unseen schedules; benefit=3*semantic_discrimination+2*unprotected_obligation_fraction+1/(1+previous_family_queries)',
            active_cost='maximize benefit/(2*input_rows)',active_no_cost='maximize identical benefit without the cost divisor',
            S2='minimize previous declared obligation exposures among unseen schedules',tie_break='seeded random choice',max_semantic_hypotheses=24),
        analysis=dict(primary_gap_unit='confirmed first-violation/false-alarm observed transaction context, stripping absolute cycle only; never parent-count inflation',
            late_detection='reported separately from transaction complete misses',
            cost_cuts='step function using only entire queries with cumulative observed sampled cycles <= cut; no interpolation, no use of a query crossing the cut',
            equal_query_cuts=[0,1,2,3,4],cycle_grid=[0,48,96,144,192,288,432,576,864,1296,1728],
            complete_common_cost_support='only grid points reached or exceeded by every strategy in the paired unit; incomplete-query benefit is never credited',
            wall_time='actual native compile+execute seconds, planning time, and lock wait all recorded separately; no cycle-to-speedup claim'),
        cohort='Two real-project RTL designs with explicit artificial primary obligation faults; no new historical-bug or full independent acceptance claim.',
        heldout_access=False,independent_generator_invoked=False,model_calls=0,native_cache_enabled=False,
        source_sha256=bindings,preparation_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
    cases.dump(out/'protocol.json',protocol);cases.dump(out/'seal.json',dict(protocol_sha256=sha(out/'protocol.json'),source_sha256=bindings,prepared_before_native_execution=True))
    print('SEALED',out,flush=True)


def verify(out):
    seal=read(out/'seal.json')
    if sha(out/'protocol.json')!=seal['protocol_sha256']:raise ValueError('protocol_changed_after_seal')
    for path,value in seal['source_sha256'].items():
        if sha(ROOT/path)!=value:raise ValueError('sealed_source_changed:'+path)


def check_stop(out):
    if (out/'STOP').exists():raise RuntimeError('operator_stop_before_next_native_query')


def qualified(record):
    return record['semantic_native_consistent'] and record['paired_correct_independently_legal']


def calibration(out,protocol):
    for case in protocol['cases']:
        pilot=[]
        for length in protocol['calibration']['lengths']:
            check_stop(out);verify(out);folder=out/'calibration'/case/f'n{length}'
            q=queries.generate_query(case,queries.FAMILIES[case][0],length,protocol['calibration']['seed'])
            record=read(folder/'acquisition.json') if (folder/'acquisition.json').exists() else active.execute_query(case,protocol['initial_candidates'][case],q,folder)
            pilot.append(record);print('CALIBRATION',case,length,'qualified',qualified(record),flush=True)
            if not qualified(record):raise ValueError('native_semantic_or_oracle_preflight_failed:'+case)
        cases.dump(out/'calibration'/case/'fit.json',active.fit_cost_calibration(pilot))
        folder=out/'baseline'/case
        if not (folder/'acquisition.json').exists():
            check_stop(out);verify(out);q=queries.generate_query(case,queries.FAMILIES[case][0],protocol['public_baseline']['length'],protocol['public_baseline']['seed'])
            record=active.execute_query(case,protocol['initial_candidates'][case],q,folder)
        else:record=read(folder/'acquisition.json')
        if not qualified(record):raise ValueError('public_baseline_preflight_failed:'+case)
    verify(out);cases.dump(out/'calibration_complete.json',dict(status='completed',model_calls=0,qualification_native_jobs=16))


def execute(out,stage):
    out=Path(out).resolve();verify(out);protocol=read(out/'protocol.json');started=time.monotonic()
    cases.dump(out/'run_started.json',dict(stage=stage,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
    try:
        if stage in ('all','calibration'):calibration(out,protocol)
        if stage=='calibration':return
        if not (out/'calibration_complete.json').exists():raise ValueError('calibration_not_completed')
        for unit in protocol['run_order']:
            check_stop(out);verify(out);case=unit['case_id'];seed=unit['seed'];strategy=unit['strategy']
            folder=out/'sessions'/case/str(seed)/strategy
            session=active.Session(case,strategy,seed,protocol['query_pools'][f'{case}/{seed}'],read(out/'baseline'/case/'acquisition.json'),
                read(out/'calibration'/case/'fit.json'),folder,protocol['max_queries_per_unit'],protocol['reserved_cycle_budget_per_unit'])
            for _ in range(protocol['max_queries_per_unit']):
                check_stop(out);verify(out);record=session.acquire()
                if record is None:break
                print('QUERY',case,seed,strategy,record['round'],len(record['query']['rows']),'cycles',record['cost']['observed_sampled_cycles'],
                    'new_contexts',len(record['cumulative_new_context_ids']),'unknown',len(record['measurement']['critical_unknown']),flush=True)
                if not qualified(record):raise ValueError('main_native_semantic_or_correct_oracle_failure')
            cases.dump(folder/'outcome.json',dict(status='completed',actual_queries=len(session.records),reserved_cycles=session.reserved_cycles,
                new_contexts=len(session.seen_contexts),model_calls=0))
        verify(out);cases.dump(out/'outcome.json',dict(status='completed',main_units=len(protocol['run_order']),model_calls=0,wall_seconds=time.monotonic()-started))
    except Exception as exc:
        cases.dump(out/'interruption.json',dict(status='interrupted',error_type=type(exc).__name__,error=str(exc),stage=stage,
            model_calls=0,all_partial_native_records_retained=True,wall_seconds=time.monotonic()-started))
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','execute']);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--stage',choices=['all','calibration','main'],default='all');args=parser.parse_args()
    if args.action=='prepare':prepare(args.out)
    else:execute(args.out,args.stage)
