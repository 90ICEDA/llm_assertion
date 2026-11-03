"""Predeclared four-policy, true two-candidate native search; development only.

No model calls. Policies consume explicit narrow views; the independent judge
is invoked only after the query and cannot affect baseline selection.
"""
import argparse
import hashlib
import random
import shutil
import time
from pathlib import Path

import research17_loop as loop
import research32_runtime as extension
from research32_search import stimulus, stall_length
from research30_search import failures
from research15_evidence import paired_ledger

ROOT = loop.ROOT
read, dump = loop.read, loop.dump
SEEDS = (4201, 4211, 4217)
METHODS = ('ordinary', 'candidate_disagreement', 'raw_difference', 'contract_coverage')
DURATIONS = (0, 1, 2, 4, 8, 16)
SOURCES = dict(initial=ROOT/'deliverables/research41_prepare_20261022_r01/s4103/shared_initial.json',
               repaired=ROOT/'deliverables/research28_valid_closed_loop_20261020_r01/core/frozen_candidate.json')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def choose(method, query, rng, history):
    if query == 0:
        return 0
    if method == 'contract_coverage':
        maximum = max(h['maximum_stall'] for h in history)
        return next((n for n in (1, 4, 16) if n > maximum), 16)
    if method in ('candidate_disagreement', 'raw_difference'):
        if rng.random() < .65 and max(h['score'] for h in history) > 0:
            best = max(h['score'] for h in history)
            return rng.choice([h['duration'] for h in history if h['score'] == best])
    return rng.choice(DURATIONS)


def prepare(out):
    loop.prepare(out)
    # Snapshot all local research modules so imported helpers have content versions.
    for p in (ROOT/'scripts').glob('research*.py'):
        shutil.copy2(p, out/'source_snapshot'/p.name)
    candidates = {n: read(p) for n, p in SOURCES.items()}
    repaired_freeze = read(SOURCES['repaired'].parent/'freeze.json')
    assert loop.sha(candidates['repaired']) == repaired_freeze['candidate_sha256']
    assert loop.sha(candidates['initial']) != loop.sha(candidates['repaired'])
    for n, c in candidates.items():
        dump(out/'candidates'/f'{n}.json', c)
    dump(out/'protocol.json', dict(
        seeds=SEEDS, methods=METHODS, duration_grammar=DURATIONS,
        queries_per_method_seed=4, cycles_per_query=112, depth=4, pipeline=1,
        candidates={n: dict(source=str(SOURCES[n]), hash=loop.sha(c)) for n,c in candidates.items()},
        common_information='Same two complete historically model-generated candidates, RTL, specifications, duration grammar, artificial fault names and q0 no-stall stimulus. No successful research40/41 candidate or independent test is read.',
        information_views=dict(ordinary='Own selected durations only.',
            candidate_disagreement='Own durations and XOR count of whole-set native failure-cycle sets between TWO complete candidates.',
            raw_difference='Own durations and count of mvalid/mdata differences between correct and faulty runs.',
            contract_coverage='Own durations and maximum actual stalled run on the correct trace, measured from mvalid && !mready. No hidden oracle verdict or mutation threshold enters selection.'),
        policies=dict(ordinary='Uniform from six durations with replacement.',
            candidate_disagreement='Probability .65 exploit own largest positive score by replaying that duration; otherwise uniform exploration.',
            raw_difference='Same score/exploration rule as candidate disagreement.',
            contract_coverage='Select first uncovered public short/medium/long bucket 1/4/16 based on own correct-side measured stall coverage.'),
        comparison_scope='Equal access to common inputs and six native runs per query; differing allowed observations are the intended mechanism treatment. No claim of equal policy feedback information.',
        accounting='Each query costs six native executions: two candidates times correct and two long-valid faults. All 48 queries, duplicates, no-witness and unknowns charged; 2 fresh compiles and 2 smoke executions separately. No cache.',
        dedup='candidate content hash / FN or FP / obligation / artificial fault mechanism. Across cycles, seeds and waveforms identical keys are one gap. Report repeated observations separately.',
        witness='Independent port-history queue confirms protocol legality, matched accepted handshakes, correct satisfaction and first faulty obligation violation. Native antecedent cover distinguishes empty trigger from triggered but insufficient.',
        attribution='Only first oracle violation per reset epoch is evaluated as confirmed target; later violations retained as attribution_unknown.',
        selection_bias='Known long-stall mutation family selected prospectively for this bounded comparison. Short/medium/long bucket policy was inherited from research32, which already studied this family. This is a transparent development replication, not blind benchmark discovery or a real historical bug.',
        model_calls=0, formal_calls=0, git_commit=None,
        independent_test_consumed=False, all_outputs_split='development',
        prepared_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())))
    hashes = {str(p.relative_to(out)): digest(p) for p in out.rglob('*') if p.is_file()}
    dump(out/'prepared_hashes.json', hashes)
    dump(out/'outcome.json', dict(status='prepared_no_native_execution'))


def validate_gap(row, fixed, mutant):
    o = row['oracle']; native = row['native']; a = native['assertions']
    tx = mutant['oracle']['transactions']
    accepted = [t for t in tx if t.get('accept_cycle', 10**9) <= row['cycle']]
    tests = dict(input_legal=o['legality']=='legal',
        accepted_transactions_identifiable=bool(accepted),
        identical_accepted_inputs=o['identical_input_handshakes'],
        faulty_violates_confirmed_obligation=o['verdict']=='violated' and bool(row['oracle_violation']),
        fixed_satisfies=o['paired_control_pass'],
        native_current_assertions_miss=not any(x['failed'] for x in a),
        confirmed_first_attribution=native['attribution_status']=='confirmed' and o['first_violation_in_epoch'])
    return dict(valid=all(tests.values()), conditions=tests,
        trigger_class='triggered_but_insufficient' if any(x['trigger'] for x in a) else 'not_triggered',
        matching_assertions=a,
        accepted_transaction_count=len(accepted),
        transactions=tx,
        paired_fixed_transactions=fixed['oracle']['transactions'],
        samples=[t for t in mutant['reference_trace'] if row['cycle']-2 <= t['cycle'] <= row['cycle']+1])


def run(out):
    assert read(out/'outcome.json')['status'] == 'prepared_no_native_execution'
    frozen = read(out/'prepared_hashes.json')
    assert all(digest(out/p)==h for p,h in frozen.items())
    # Lock the runtime dependency versions, including the policy itself.
    deps = ('research42_search.py','research32_search.py','research32_runtime.py',
        'research28_valid_runtime.py','research20_stall_runtime.py','research17_loop.py',
        'research17_fifo_feedback.py','research15_search_runtime.py',
        'research15_native_interface.py','research15_evidence.py','research15_acceptance.py')
    assert all(digest(ROOT/'scripts'/n)==digest(out/'source_snapshot'/n) for n in deps)
    candidates={n:read(out/'candidates'/f'{n}.json') for n in SOURCES}
    records=[]; acquired=[]; seen=set(); start=time.monotonic()
    dump(out/'outcome.json',dict(status='running'))
    try:
        with extension.installed():
            builds={n:loop.runtime.build(c,out/'compiled'/n,4,1) for n,c in candidates.items()}
            assert all(b['native']['compile_status']=='passed' for b in builds.values())
            dump(out/'candidate_qualification.json',dict(
                candidates_distinct=loop.sha(candidates['initial'])!=loop.sha(candidates['repaired']),
                native_compile={n:b['native'] for n,b in builds.items()},
                correct_control_qualification='Every common and selected query is checked for both candidates below.',
                second_candidate_role='Whole historical comparator only; not a hand-written property or current successful research41 answer.'))
            for seed in SEEDS:
                for method in METHODS:
                    rng=random.Random(seed); history=[]; maximum=0
                    for q in range(4):
                        duration=choose(method,q,rng,history)
                        rows=stimulus(seed*100+q,duration)
                        folder=out/'queries'/f's{seed}'/method/f'q{q}'
                        dump(folder/'selection.json',dict(duration=duration,stimulus_seed=seed*100+q,permitted_history=history))
                        modes=('correct',)+extension.MODES
                        runs={n:{m:loop.runtime.execute(builds[n],folder/n/m,rows,m) for m in modes} for n in candidates}
                        healthy=all(r['native']['compile_status']=='passed' and
                            r['native']['execution_status']=='completed' and
                            r['native']['tool_support_status']=='supported_for_compiled_constructs' and
                            r['sampling_qualification']['status']=='passed' and
                            r['oracle']['legality']=='legal' and not r['oracle']['unknown']
                            for rr in runs.values() for r in rr.values())
                        healthy=healthy and all(not runs[n]['correct']['native']['failures'] and not runs[n]['correct']['oracle']['violations'] for n in candidates)
                        gaps=[]; later=unknown=0; false_positives=[]; all_obligations=set()
                        for mode in extension.MODES:
                            case=dict(id=f'search42:s{seed}:{method}:q{q}:{mode}',depth=4,pipeline=1,
                                rows=rows,mode=mode,split='development',source='research42_native_search',
                                source_seed=seed,source_query=str(folder),
                                dedup_class='stall_stability:'+mode,target_obligation='stall_stability')
                            group=paired_ledger(runs['initial']['correct'],runs['initial'][mode],case['id'])
                            dump(folder/'ledgers'/f'{mode}.json',group)
                            info=loop.inspect(group['ledger']);unknown+=len(info['unknown']);later+=len(group['exclusions'])
                            all_obligations.update(info['mapping'])
                            false_positives.extend(info['rows'][k] for k in sorted(info['false_positives']))
                            for k in sorted(info['misses']):
                                row=info['rows'][k]
                                validation=validate_gap(row,runs['initial']['correct'],runs['initial'][mode])
                                key=f"{loop.sha(candidates['initial'])}/FN/{row['obligation']}/{mode}"
                                gaps.append(dict(key=key,evidence=row,validation=validation,case=case,source=str(folder/'initial'/mode)))
                                select=(seed,mode)
                                if healthy and validation['valid'] and method=='contract_coverage' and row['obligation']=='stall_stability' and select not in seen:
                                    seen.add(select)
                                    acquired.append(dict(**case,validation=validation,evidence_id=row['evidence_id'],gap_key=key))
                        xor=sum(len(failures(runs['initial'][m]) ^ failures(runs['repaired'][m])) for m in modes)
                        diff=sum(any(a[k]!=b[k] for k in ('mvalid','mdata')) for m in extension.MODES
                            for a,b in zip(runs['initial']['correct']['trace'],runs['initial'][m]['trace']))
                        measured=stall_length(runs['initial']['correct']['trace']);maximum=max(maximum,measured)
                        view=dict(duration=duration)
                        if method=='contract_coverage':view.update(maximum_stall=maximum)
                        elif method!='ordinary':view.update(score=xor if method=='candidate_disagreement' else diff)
                        history.append(view)
                        qualified=[g for g in gaps if healthy and g['validation']['valid']]
                        record=dict(seed=seed,method=method,query=q,duration=duration,healthy=healthy,
                            gaps=qualified,unqualified_gap_rows=[g for g in gaps if g not in qualified],
                            independent_gap_keys=sorted({g['key'] for g in qualified}),
                            false_positive_rows=false_positives,covered_obligations=sorted(all_obligations),
                            permitted_view=view,judge_only=dict(xor=xor,raw_difference=diff,max_stall=measured),
                            unknown=unknown,later_attribution_unknown=later,native_executions=6)
                        records.append(record);dump(folder/'result.json',record);dump(out/'results.json',records)
                        print(seed,method,q,duration,len(record['independent_gap_keys']),flush=True)
        dump(out/'acquired_cases.json',acquired)
        dump(out/'acquired_manifest.json',dict(path=str(out/'acquired_cases.json'),file_sha256=digest(out/'acquired_cases.json'),
            content_sha256=loop.sha(acquired),count=len(acquired),split='development',
            per_seed={str(s):[c['mode'] for c in acquired if c['source_seed']==s] for s in SEEDS},
            initial_candidate_sha256=loop.sha(candidates['initial'])))
        dump(out/'outcome.json',dict(status='native_search_completed',queries=len(records),
            all_healthy=all(r['healthy'] for r in records),acquired=len(acquired),model_calls=0,
            wall_seconds=time.monotonic()-start,prepared_files_unchanged=all(digest(out/p)==h for p,h in frozen.items())))
    except BaseException as exc:
        dump(out/'outcome.json',dict(status='execution_failed',error=repr(exc),completed_queries=len(records)))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve();assert ROOT in out.parents
    (prepare if a.action=='prepare' else run)(out)
