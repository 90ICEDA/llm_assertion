"""Prospective independent fair-drain exposure for the frozen research28 set.

No model calls, candidate selection, assertion edits, RTL edits or oracle edits.
Uses the existing artificial mode 3 (drop every fourth raw output). A hidden
final response exposes loss without a later output causing earlier order errors.
"""
import argparse
import hashlib
from pathlib import Path
import random
import secrets
import shutil
import sys
import time

import research17_loop as loop
from research15_evidence import INPUTS, marker_map

ROOT = loop.ROOT
SOURCE = ROOT/'deliverables/research28_valid_closed_loop_20261020_r01/core'
dump, read = loop.dump, loop.read
FAMILIES = ('isolated_tail', 'continuous_tail', 'parked_tail',
            'reset_then_tail', 'legal_three', 'reset_cancels_tail')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cases(seed):
    """All families/parameters fixed before execution; no adaptive selection."""
    rng = random.Random(seed)
    result = []
    for depth, pipeline in ((2, 0), (4, 1), (8, 2)):
        for family in FAMILIES:
            start = 4+rng.randrange(4)
            gap = 8+rng.randrange(4)
            fair = rng.choice((18, 24, 31))
            reset_cycles = set(range(2))
            intent_cycles = [start+j*gap for j in range(4)]
            low_ready = set()
            if family == 'continuous_tail':
                intent_cycles = list(range(start, start+4))
            elif family == 'parked_tail':
                # Space the first three requests so source intent is not
                # mistaken for acceptance. Release before the fourth request.
                release = start+3*gap
                low_ready = set(range(2, release))
                intent_cycles[-1] = release+8
            elif family == 'reset_then_tail':
                reset_at = start+12
                reset_cycles.update((reset_at, reset_at+1))
                low_ready = set(range(2, reset_at+2))
                intent_cycles = [start, start+5] + [reset_at+5+j*gap for j in range(4)]
            elif family == 'legal_three':
                intent_cycles = intent_cycles[:3]
            elif family == 'reset_cancels_tail':
                reset_at = intent_cycles[-1]+12
                reset_cycles.update((reset_at, reset_at+1))
            last_activity = max(max(intent_cycles), max(reset_cycles))
            length = last_activity+1+fair
            payloads = rng.sample(range(1, 2**32), length)
            rows = [dict(cycle=c, rst=int(c in reset_cycles), intent=int(c in intent_cycles),
                ready=int(c not in low_ready), data=payloads[c], drain_due=int(c==length-1))
                for c in range(length)]
            target = family not in ('legal_three', 'reset_cancels_tail')
            result.append(dict(id=f'independent29:s{seed}:d{depth}:p{pipeline}:{family}',
                depth=depth, pipeline=pipeline, mode='drop', family=family, seed=seed,
                rows=rows, split='independent_test', target_obligation='drain_no_loss',
                expected_role='target_loss' if target else 'legal_control',
                requested_fair_suffix=fair,
                source='prospective_post_research28_freeze_contract_targeted_generator',
                dedup_class='drain_no_loss:hidden_final_fourth_output' if target else 'legal_drain',
                scope='New schedules of a known artificial fault, not a new upstream defect or unseen fault-class test.'))
    return result


def assess(folder, selected, result):
    records = []
    for i, case in enumerate(selected):
        path = folder/f'case_{i}'
        fixed = read(path/'correct/replay.json')
        mutant = read(path/'drop/replay.json')
        ledger = read(path/'ledger.json')
        deadline = len(case['rows'])-1
        target = case['expected_role']=='target_loss'
        fc = [c for c in fixed['oracle']['checks'] if c['obligation']=='drain_no_loss']
        mc = [c for c in mutant['oracle']['checks'] if c['obligation']=='drain_no_loss']
        target_rows = [r for r in ledger['ledger'] if r['obligation']=='drain_no_loss'
                       and r['oracle']['verdict']=='violated']
        fm, mm = marker_map(fixed['native'], 'failures'), marker_map(mutant['native'], 'failures')
        fail_cycles = set().union(*mm.values()) if mm else set()
        pending = mutant['oracle']['pending']
        resolved_pending = []
        for txn in pending:
            counterpart = next((t for t in fixed['oracle']['transactions']
                                if t['transaction_id']==txn['transaction_id']), None)
            resolved_pending.append(dict(faulty=txn, fixed=counterpart))
        native_ok = all(r['native'].get('compile_status')=='passed'
                        and r['native'].get('tool_support_status')=='supported_for_compiled_constructs'
                        and r['native'].get('execution_status')=='completed'
                        and r['sampling_qualification']['status']=='passed' for r in (fixed, mutant))
        checks = dict(native_complete=native_ok,
            legal_inputs=all(r['oracle']['legality']=='legal' and not r['oracle']['unknown'] for r in (fixed,mutant)),
            identical_accepted_inputs=[{k:t[k] for k in INPUTS} for t in fixed['trace']]==[{k:t[k] for k in INPUTS} for t in mutant['trace']],
            actual_fair_suffix=all(r['oracle']['drain_scope']['actual_fair_samples']>=18 for r in (fixed,mutant)),
            correct_control_drained=len(fc)==1 and fc[0]['passed'] and not fixed['oracle']['pending'] and not fixed['oracle']['violations'],
            correct_control_no_false_alarm=not fixed['native']['failures'],
            checkpoint_observed=len(mc)==1 and mc[0]['cycle']==deadline)
        if target:
            checks.update(one_unresolved_accepted_transaction=len(pending)==1 and all(
                p['faulty']['accept_cycle']<deadline and p['faulty']['cancel_cycle'] is None
                and p['faulty']['response_cycle'] is None and p['fixed']
                and p['fixed']['response_cycle'] is not None
                and p['fixed']['response_cycle']<deadline for p in resolved_pending),
                only_independent_violation_is_drain=bool(mutant['oracle']['violations']) and all(
                    v['obligation']=='drain_no_loss' and v['cycle']==deadline for v in mutant['oracle']['violations']),
                no_earlier_native_alarm=not any(c<deadline for c in fail_cycles),
                first_attributed_drain_target=len(target_rows)==1 and target_rows[0]['native']['attribution_status']=='confirmed',
                triggered_and_detected=len(target_rows)==1 and any(
                    a['trigger'] and a['failed'] and a['causal_detection'] for a in target_rows[0]['native']['assertions']))
        else:
            checks.update(no_uncancelled_pending=not pending,
                no_oracle_violation=not mutant['oracle']['violations'],
                no_native_false_alarm=not mutant['native']['failures'])
        snapshots = {}
        for name, replay in (('correct',fixed),('drop',mutant)):
            snapshots[name] = [s for s in replay['reference_trace'] if deadline-1<=s['cycle']<=deadline]
        records.append(dict(case=case['id'], family=case['family'], depth=case['depth'], pipeline=case['pipeline'],
            role=case['expected_role'], passed=all(checks.values()), checks=checks, deadline=deadline,
            actual_fair_samples={n:r['oracle']['drain_scope']['actual_fair_samples'] for n,r in (('correct',fixed),('drop',mutant))},
            accepted_transactions=len(mutant['oracle']['transactions']),
            responded_transactions=sum(t['response_cycle'] is not None for t in mutant['oracle']['transactions']),
            cancelled_transactions=len(mutant['oracle']['cancelled']),
            loss_transaction_correspondence=resolved_pending, deadline_samples=snapshots,
            drain_checks=dict(correct=fc,drop=mc), target_rows=target_rows,
            native_failures=mutant['native']['failures'],
            prior_native_failures=[c for c in fail_cycles if c<deadline],
            raw_files=dict(correct=str(path/'correct/replay.json'),drop=str(path/'drop/replay.json')),
            later_attribution_unknown=len(ledger['exclusions'])))
    return dict(passed=result['healthy'] and len(records)==18 and all(r['passed'] for r in records),
        scenarios=records, target_scenarios=sum(r['role']=='target_loss' for r in records),
        valid_target_detections=sum(r['role']=='target_loss' and r['passed'] for r in records),
        legal_scenarios=sum(r['role']=='legal_control' for r in records),
        legal_scenarios_passed=sum(r['role']=='legal_control' and r['passed'] for r in records),
        distinct_loss_mechanisms=1, counts=result['counts'],
        limits='Finite fair-drain check only. Known synthetic drop fault, independently generated schedules. No proof of global completeness, no model refinement or historical-defect claim.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    assert ROOT in out.parents
    candidate = read(SOURCE/'frozen_candidate.json')
    stamp = read(SOURCE/'freeze.json')
    assert loop.sha(candidate)==stamp['candidate_sha256']
    source_hashes = {name:digest(SOURCE/name) for name in ('frozen_candidate.json','frozen_candidate.sva','freeze.json')}
    loop.prepare(out)
    shutil.copy2(__file__,out/'source_snapshot'/Path(__file__).name)
    dump(out/'source_snapshot/hashes.json',{p.name:digest(p) for p in (out/'source_snapshot').iterdir() if p.is_file() and p.name!='hashes.json'})
    dump(out/'frozen_candidate.json',candidate)
    shutil.copy2(SOURCE/'frozen_candidate.sva',out/'frozen_candidate.sva')
    dump(out/'freeze_binding.json',dict(source=str(SOURCE),source_freeze=stamp,
        source_file_hashes=source_hashes,candidate_sha256=loop.sha(candidate),
        bound_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        rule='Existing research28 frozen set; no edits, selection, model calls or feedback.'))
    dump(out/'protocol.json',dict(target='drain_no_loss',cases=18,parameters=[[2,0],[4,1],[8,2]],
        families=FAMILIES, candidate_source=str(SOURCE),candidate_sha256=loop.sha(candidate),
        independent='Inputs generated after binding existing freeze; all results reported, no tuning, subset selection or model feedback.',
        fair_condition='Actual output-ready, input-idle, no-reset suffix of at least 18 samples in depth<=8, pipeline<=2, output FIFO disabled.',
        oracle='Unmodified independent accepted-input/output queue, reset cancellation and paired-control check.',
        mutation='Existing mode3 suppresses every fourth raw output. All RTL, harness and oracle code unchanged.',
        accounting='Four target families and two legal controls per parameter; parameter/waveform variants not independent mechanisms.',
        failure_rule='If outcomes inform any later repair or candidate selection, promote entire batch to development; require fresh post-freeze tests.',
        model_calls=0,formal_queries=0,root_git_commit=None))
    seed = secrets.randbelow(2**31)
    selected = cases(seed)
    dump(out/'split.json',dict(seed=seed,split='independent_test',candidate_sha256=loop.sha(candidate),
        created_after_freeze_binding=True,cases=selected))
    dump(out/'execution.command.json',dict(argv=[sys.executable,*sys.argv],cwd=str(Path.cwd())))
    dump(out/'outcome.json',dict(status='running'))
    try:
        result = loop.replay(candidate,out/'native',selected)
        if not result.get('group'):
            raise RuntimeError('native_compile_or_execution_unavailable')
        # The general replay helper defaults to development. Relabel the
        # standalone evaluation records explicitly; no feedback enters a model.
        for i in range(len(selected)):
            path=out/'native'/f'case_{i}/ledger.json'
            ledger=read(path)
            for row in ledger['ledger']: row['split']='independent_test'
            dump(path,ledger)
        for row in result['group']['ledger']: row['split']='independent_test'
        dump(out/'native/result.json',result)
        summary=assess(out/'native',selected,result)
        summary['candidate_unchanged']=all(digest(SOURCE/name)==value for name,value in source_hashes.items()) and read(out/'frozen_candidate.json')==candidate
        summary['passed'] &= summary['candidate_unchanged']
        dump(out/'summary.json',summary)
        dump(out/'outcome.json',dict(status='independent_drain_passed' if summary['passed'] else 'independent_drain_failed_or_unknown',
            candidate_modified=False,model_calls=0,formal_queries=0,independent_executed=True,
            batch_status='independent_public_after_report',
            future_rule='Promote full batch before any outcome-driven repair; do not reuse as independent after modification.'))
        print(dict(passed=summary['passed'],targets=summary['valid_target_detections'],
                   target_denominator=summary['target_scenarios'],legal=summary['legal_scenarios_passed'],
                   counts=summary['counts']),flush=True)
    except BaseException as exc:
        dump(out/'outcome.json',dict(status='execution_blocked',error=repr(exc),candidate_modified=False,model_calls=0))
        raise


if __name__=='__main__':
    main()
