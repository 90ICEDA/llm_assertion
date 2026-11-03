"""Independent FIFO/native replay adapter. No assertion text is an oracle.

First violation per reset epoch is the conservative attribution boundary. Later
violations are retained as attribution-unknown, outside confirmed target replay.
This scope is explicit; it is not whole-trajectory or whole-obligation protection.
"""
import collections
import hashlib
import json
import re
from research15_acceptance import sha

OBLIGATIONS=('order_payload','no_unsolicited_output','stall_stability','drain_no_loss','reset_cancellation')
INPUTS=('cycle','rst','svalid','sready','sdata','mready')


def marker_map(native, field):
    result=collections.defaultdict(set)
    for marker in native.get(field, []):
        match=re.search(r'\bcycle=(-?\d+)\b', marker.get('detail',''))
        if match:result[marker['id']].add(int(match[1]))
    return result


def epoch_map(trace):
    epoch=0
    result={}
    previous_reset=False
    for t in trace:
        if t['rst'] and not previous_reset:epoch+=1
        previous_reset=bool(t['rst'])
        if not previous_reset:result[t['cycle']]=epoch
    return result


def paired_ledger(fixed, mutant, scenario_id):
    """Return {ledger, exclusions, stats}; pass mutant=None for control only.

    Each replay is dict(native, trace, oracle, candidate, mode, directory).
    candidate has assertions[{id, obligations, derived_delay, ...}]. The native
    results must come from research15_native_interface (native cover property).
    ``scenario_id`` must remain identical before/after, encode parameter settings,
    and never contain an assertion-version identifier. Each call includes control
    rows; merge_ledgers removes identical duplicate control rows across modes.
    """
    mode=(mutant or fixed).get('mode','correct')
    traces=[fixed['trace']] + ([mutant['trace']] if mutant is not None else [])
    inputs=[[{k:t.get(k) for k in INPUTS} for t in trace] for trace in traces]
    input_sha=sha(dict(scenario=scenario_id, inputs=inputs[0]))
    paired_equal=len(inputs)==1 or inputs[0]==inputs[1]
    fixed_good=(fixed['oracle'].get('legality')=='legal' and
                not fixed['oracle'].get('violations') and not fixed['oracle'].get('unknown'))
    fixed_epochs=epoch_map(fixed['trace'])
    fixed_failures=marker_map(fixed['native'],'failures')
    fixed_failure_cycles=set().union(*fixed_failures.values()) if fixed_failures else set()
    ledger=[]; exclusions=[]

    def append_run(record, variant, control):
        native, trace, oracle=record['native'], record['trace'], record['oracle']
        epochs=epoch_map(trace)
        triggers, failures=marker_map(native,'triggers'), marker_map(native,'failures')
        all_failure_cycles=set().union(*failures.values()) if failures else set()
        first={}
        for violation in oracle.get('violations',[]):
            c=violation['cycle']
            if c in epochs:first[epochs[c]]=min(first.get(epochs[c],c),c)
        by_cycle=collections.defaultdict(list)
        for v in oracle.get('violations',[]):by_cycle[v['cycle']].append(v)
        candidates=record['candidate'].get('assertions',[])
        exact_cover='native cover property' in native.get('trigger_measurement','').lower()
        healthy=(native.get('compile_status')=='passed' and native.get('execution_status')=='completed' and exact_cover)
        legal=oracle.get('legality')=='legal' and paired_equal and fixed_good
        for t in trace:
            c=t['cycle']
            if c not in epochs:continue
            boundary=first.get(epochs[c])
            if not control and boundary is not None and c>boundary:
                for violation in by_cycle[c]:
                    exclusions.append(dict(scenario_id=scenario_id,mode=variant,cycle=c,
                        obligation=violation['obligation'],oracle_violation=violation,
                        status='attribution_unknown',reason='After first oracle violation in this reset epoch; causal assertion detection not established.'))
                continue
            selected=list(OBLIGATIONS) if control or boundary is None or c<boundary else sorted({v['obligation'] for v in by_cycle[c]})
            for obligation in selected:
                target=not control and boundary==c
                identity=dict(scenario=scenario_id,variant=variant,input_sha256=input_sha,
                              epoch=epochs[c],cycle=c,obligation=obligation)
                evidence_id='fifo:'+sha(identity)
                assertions=[]
                earlier_alarm=any(epochs.get(fc)==epochs[c] and fc<c for fc in all_failure_cycles)
                fixed_alarm=any(fixed_epochs.get(fc)==fixed_epochs.get(c) and fc<=c for fc in fixed_failure_cycles)
                matching_ids={a['id'] for a in candidates if obligation in a.get('obligations',[])}
                unmatched_alarm=target and c in all_failure_cycles and not any(c in failures[a] for a in matching_ids)
                attribution_unknown=target and (earlier_alarm or fixed_alarm or unmatched_alarm)
                for a in candidates:
                    if obligation not in a.get('obligations',[]):continue
                    delay=a.get('derived_delay')
                    cover_cycle=c-delay if type(delay) is int else None
                    trigger=(cover_cycle in triggers[a['id']] and epochs.get(cover_cycle)==epochs[c]) if cover_cycle is not None else None
                    failed=c in failures[a['id']]
                    causal=(failed and trigger and not attribution_unknown) if target else False
                    if attribution_unknown:causal=None
                    assertions.append(dict(id=a['id'],trigger=trigger,failed=failed,causal_detection=causal))
                # Prior false alarms confound the whole set, including empty
                # obligation projections. Preserve this explicitly as unknown.
                oracle_verdict='violated' if target else 'satisfied'
                oracle_record=dict(legality='legal' if legal else 'unknown', verdict=oracle_verdict,
                    validator='independent_fifo_port_history_queue', paired_control_pass=fixed_good,
                    identical_input_handshakes=paired_equal, first_violation_in_epoch=target)
                row=dict(evidence_id=evidence_id,obligation=obligation,stimulus_sha256=input_sha,
                    split='development',scenario_id=scenario_id,variant=variant,cycle=c,epoch=epochs[c],
                    oracle=oracle_record,native=dict(
                        compile='ok' if native.get('compile_status')=='passed' else 'unknown',
                        support='supported' if native.get('tool_support_status')=='supported_for_compiled_constructs' else 'unknown',
                        execution='ok' if native.get('execution_status')=='completed' else 'unknown',
                        attribution_status='unknown' if attribution_unknown else 'confirmed',
                        trigger_source='property_antecedent_cover' if exact_cover else 'unknown',assertions=assertions),
                    source_directory=record.get('directory'), oracle_violation=by_cycle[c] if target else [])
                ledger.append(row)
        # Do not let zero parsed TRACE rows, partial execution, or missing fair
        # drain suffix disappear into an empty/successful admission ledger.
        if not trace or not healthy or not legal or oracle.get('unknown'):
            ledger.append(dict(evidence_id='fifo:unknown:'+sha([scenario_id,variant,input_sha]),
                obligation='execution_completeness',stimulus_sha256=input_sha,split='development',
                oracle=dict(legality='unknown',verdict='unknown',validator='independent_fifo_port_history_queue',
                            issues=oracle.get('unknown',[])),native={},source_directory=record.get('directory')))

    append_run(fixed,'correct',True)
    if mutant is not None:append_run(mutant,mode,False)
    return dict(ledger=ledger, exclusions=exclusions,
                stats=dict(rows=len(ledger),later_violation_attribution_unknown=len(exclusions),
                           paired_inputs_identical=paired_equal,correct_control_pass=fixed_good),
                scope='All control samples and mutant legal prefixes; only first oracle violation per reset epoch is a target. causal_detection is a legacy field name for bounded paired-contrast detection with same accepted inputs and a candidate-accepted legal control prefix, not strict causation or logical entailment. Presented outputs may differ during contract-allowed delay; later violations retained as attribution unknown.')


def merge_ledgers(groups):
    rows={}
    exclusions=[]
    for group in groups:
        for row in group['ledger']:
            key=row['evidence_id']
            if key in rows and rows[key]!=row:
                raise ValueError('conflicting_replay_for_stable_evidence_id:'+key)
            rows[key]=row
        exclusions.extend(group.get('exclusions',[]))
    return dict(ledger=list(rows.values()),exclusions=exclusions)
