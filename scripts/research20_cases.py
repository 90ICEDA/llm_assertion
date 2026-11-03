"""Prospective development cases for obligation-by-obligation FIFO refinement.

Reuses the qualified upstream RTL, boundary faults, legal handshake driver and
port-history oracle. No model calls, no reading of new independent test data.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
from pathlib import Path
import shutil

import research17_loop as loop
import research15_search_experiment as search
from research17_model import ROOT, dump, read


PARAMETERS = ((2, 0), (5, 1))
# Each family has a distinct deterministic seed, fixed before execution.
FAMILIES = (
    ('tail_loss', 'drop', 2026101801, 'drain_no_loss'),
    ('reset_pending', 'reset_residue', 2026101802, 'reset_cancellation'),
    ('backpressure', 'duplicate_payload', 2026101803, 'stall_stability'),
    ('overlap', 'duplicate_payload', 2026101804, 'order_payload'),
)


def cases():
    """Fresh development cases in the existing loop.replay input format.

    ``target_obligation`` records the planned acquisition objective, never a
    claim that a violation or missed detection was actually found.
    """
    result = [loop.common_case()]
    for family, mode, seed, target in FAMILIES:
        for index, (depth, pipeline) in enumerate(PARAMETERS):
            actual_seed = seed + index * 100
            result.append(dict(
                id=f'dev20:d{depth}:p{pipeline}:s{actual_seed}:{family}:{mode}',
                depth=depth, pipeline=pipeline, mode=mode,
                rows=search.stimulus(actual_seed, family),
                source='prospective_contract_obligation_development',
                family=family, seed=actual_seed, target_obligation=target,
                split='development',
            ))
    return result


def audit(out, candidate_path):
    """Execute an actual existing model candidate and audit independent oracle.

    Candidate choice is explicit and saved. This is development acquisition,
    not a new generation or independent final-candidate validation.
    """
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    candidate_path = Path(candidate_path).resolve()
    candidate = read(candidate_path)
    selected = cases()
    dump(out/'plan.json', dict(
        candidate_source=str(candidate_path),
        candidate_sha256=hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        parameters=PARAMETERS, families=FAMILIES,
        scope='Fresh fixed-seed development evidence only; no model calls or independent results read.',
        failure_model='Actual vendored axis_fifo plus existing artificial output boundary mutations; not a historical upstream defect.',
        rules=dict(legality='Source driver holds valid/data until actual ready handshake; reset cancels presentation.',
                   responses='Output transaction acceptance requires mvalid && mready.',
                   reset='Synchronous reset cancels outstanding accepted inputs; unique accepted payload identity used for residue attribution.',
                   stall='Previous mvalid && !mready requires current valid and same payload, unless reset.',
                   loss='Finite fair drain >=18 ready/input-idle samples, RAM depth <=8 and pipeline <=2.',
                   target_credit='First independent violation per reset epoch; later events remain attribution unknown.'),
    ))
    dump(out/'cases.json', selected)
    snapshot=out/'source_snapshot'
    snapshot.mkdir()
    sources=[Path(__file__),Path(loop.__file__),Path(search.__file__),
             ROOT/'scripts/research17_fifo_feedback.py',ROOT/'scripts/research15_search_runtime.py',
             ROOT/'scripts/research15_native_interface.py',ROOT/'scripts/research15_evidence.py',
             ROOT/'external/verilog-axis/rtl/axis_fifo.v']
    for source in sources:shutil.copy2(source,snapshot/source.name)
    dump(snapshot/'hashes.json',{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in snapshot.iterdir() if p.is_file()})
    result = loop.replay(candidate, out/'native', selected)
    summaries=[]
    oracle_totals=collections.Counter()
    first_totals=collections.Counter()
    fixed_checks=collections.Counter()
    for index, case in enumerate(selected):
        base=out/'native'/f'case_{index}'
        detail=dict(id=case['id'], depth=case['depth'], pipeline=case['pipeline'],
                    family=case.get('family','common'), mode=case['mode'], runs={})
        for mode in ('correct', case['mode']):
            path=base/mode/'result.json'
            if not path.exists():
                detail['runs'][mode]=dict(status='unavailable', reason='native result not produced')
                continue
            # Runtime saves its rich record as replay.json, while the native
            # interface saves result.json. Read actual recorded oracle below.
            oracle_path=base/mode/'independent_oracle.json'
            if not oracle_path.exists():
                oracle_path=base/mode/'oracle.json'
            if not oracle_path.exists():
                detail['runs'][mode]=dict(status='unavailable', reason='oracle artifact absent')
                continue
            oracle=read(oracle_path)
            violations=collections.Counter(v['obligation'] for v in oracle['violations'])
            checks=collections.Counter(v['obligation'] for v in oracle['checks'])
            if mode=='correct':fixed_checks.update(checks)
            else:oracle_totals.update(violations)
            detail['runs'][mode]=dict(legality=oracle['legality'], unknown=oracle['unknown'],
                violations=dict(violations), checks=dict(checks), coverage=oracle['coverage'],
                transactions=oracle['transactions'],cancelled=oracle['cancelled'],pending=oracle['pending'])
        ledger_path=base/'ledger.json'
        if ledger_path.exists():
            group=read(ledger_path)
            targets=[r for r in group['ledger'] if r['oracle']['verdict']=='violated']
            first_totals.update(r['obligation'] for r in targets)
            detail['first_violation_targets']=[dict(obligation=r['obligation'],cycle=r['cycle'],
                variant=r['variant'],oracle=r['oracle'],native=r['native'],details=r['oracle_violation']) for r in targets]
            detail['later_attribution_unknown']=len(group['exclusions'])
        summaries.append(detail)
    summary=dict(healthy=result['healthy'],native_counts=result.get('counts'),
        oracle_violations=dict(oracle_totals),first_violation_targets=dict(first_totals),
        correct_control_checks=dict(fixed_checks),cases=summaries,
        missing_target_obligations=[o for o in search.OBLIGATIONS if not first_totals[o]],
        stall_target_scope='Existing corrupt/duplicate/drop/residue boundary faults do not intentionally change payload or valid while stalled. Legal backpressure coverage does not establish detection of a stall violation.',
        model_calls=0,formal_calls=0,
        simulation_scope='Finite native simulation; passing control is not a formal proof.')
    commands=[read(p) for p in (out/'native').rglob('compile.json')]
    executions=[read(p) for p in (out/'native').rglob('execute.json')]
    summary['cost']=dict(native_compiles=len(commands),native_executions=len(executions),
        compilation_smoke_executions=sum('compiled_' in p.parent.name for p in (out/'native').rglob('execute.json')),
        compile_wall_seconds=sum(x.get('wall_seconds',0) for x in commands),
        execute_wall_seconds=sum(x.get('wall_seconds',0) for x in executions),
        model_calls=0,model_tokens=0,formal_queries=0)
    dump(out/'summary.json',summary)
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--candidate',type=Path,default=ROOT/'deliverables/research19_closed_loop_20261016_r03/shared_initial.json')
    args=parser.parse_args()
    summary=audit(args.out,args.candidate)
    print({k:summary[k] for k in ('healthy','native_counts','first_violation_targets','missing_target_obligations')},flush=True)


if __name__=='__main__':
    main()
