"""Private, port-only acceptance oracle. Never consumes a candidate or RTL state.

The source contracts and limitations are pinned by run_obligation_evidence.py.
Events carry reset-epoch/trigger identities; latency is checked before any alignment.
This module is an adjudicator, not a generator API or a native SVA implementation.
"""

def check_inputs(d, rows):
    errors = []
    previous = None
    for i, row in enumerate(rows):
        for name, width in {**d['inputs'], d['rst']: 1}.items():
            value = row.get(name)
            if type(value) is not int or not 0 <= value < (1 << width):
                errors.append([i, name, 'outside_declared_unsigned_width'])
        if previous and row[d['rst']] and previous[d['rst']]:
            if d['key'] == 'filter' and previous['thresh_i'] != row['thresh_i']:
                errors.append([i, 'threshold_changed_without_reset'])
            if d['key'] == 'fifo' and previous['push_i'] and not previous['pop_i']:
                if not row['push_i'] or previous['data_i'] != row['data_i']:
                    errors.append([i, 'stalled_transaction_abandoned'])
        previous = row
    return errors


def monitor(d, trace):
    """Return conservative scoped obligations, not fixed/buggy labels.

    Filter threshold means equal-input intervals, per upstream implementation
    documentation; it is a conditional interpretation, recorded in the contract.
    Spill raw invalid data and intr mask timing remain unresolved.
    """
    key = d['key']
    epoch = 0
    pending = {}
    previous = None
    stored = 0
    last_input = 0
    equal_intervals = 0
    prefix_ok = True
    events = []
    cancelled = []
    for row in trace:
        cycle = row['cycle']
        if not row[d['rst']]:
            cancelled.extend(v for vv in pending.values() for v in vv)
            pending.clear()
            epoch += 1
            previous = None
            stored = last_input = equal_intervals = 0
            prefix_ok = True
            continue
        checks = []
        def put(obligation, expected, actual, trigger=cycle, branch=None, conditional=False):
            checks.append(dict(obligation=obligation, expected=expected, actual=actual,
                               trigger_cycle=trigger, due_cycle=cycle,
                               transaction_id=f'{key}:e{epoch}:t{trigger}', branch=branch,
                               conditional=conditional, passed=actual == expected))
        due = pending.pop(cycle, [])
        if key == 'onehot':
            if sum(int(bit) for bit in format(row['oh_i'], 'b')) > 1:
                put('multihot_detect', 1, row['err_o'], branch='multihot')
        elif key == 'fifo':
            put('nonempty_when_present' if row['push_i'] else 'empty_when_idle',
                int(not row['push_i']), row['empty_o'],
                branch='stalled' if row['push_i'] and not row['pop_i'] else 'accepted' if row['push_i'] else 'idle')
        elif key == 'filter':
            put('qualified_value', stored if row['enable_i'] else row['filter_i'], row['filter_o'],
                branch='bypass' if not row['enable_i'] else 'qualification')
            equal_intervals = equal_intervals + 1 if row['filter_i'] == last_input else 0
            if equal_intervals >= row['thresh_i']:
                stored = row['filter_i']
            last_input = row['filter_i']
        elif key == 'spill':
            for event in due:
                put('collision_empty', 0, row['valid_o'], event['trigger_cycle'], 'flush_push')
            if row['flush_i'] and row['push_i']:
                pending.setdefault(cycle + 1, []).append(dict(trigger_cycle=cycle, payload=row['data_i']))
        elif key == 'stat':
            put('valid_latency', int(bool(due)), row['stat_valid_o'],
                due[0]['trigger_cycle'] if due else cycle, 'event_due' if due else 'no_event_due')
            for event in due:
                put('captured_length', event['payload'], row['stat_len_o'], event['trigger_cycle'], 'event_due')
            if row['frame_done_i']:
                pending.setdefault(cycle + 2, []).append(dict(trigger_cycle=cycle, payload=row['frame_len_i']))
        elif key == 'intr':
            if previous and not previous['reg2hw_intr_enable_q_i']:
                put('registered_mask', 0, row['intr_o'], previous['cycle'], 'mask_disabled', True)
            if not row['reg2hw_intr_enable_q_i']:
                put('same_sample_mask', 0, row['intr_o'], cycle, 'mask_disabled', True)
        definitive = [c for c in checks if not c['conditional']]
        current_ok = all(c['passed'] for c in definitive)
        events.append(dict(cycle=cycle, checks=checks, legal_prefix=prefix_ok and current_ok,
                           first_violation=prefix_ok and not current_ok,
                           classification='unknown_spec' if key == 'intr' else 'target_violation' if not current_ok else 'scoped_legal_sample'))
        prefix_ok = prefix_ok and current_ok
        previous = row
    return dict(events=events, pending=[v for vv in pending.values() for v in vv],
                cancelled=cancelled, scope='repair obligations only; legal prefix since latest reset',
                full_spec_resolved=key not in ('spill', 'intr'))


def evidence(d, trace, checks, oracle):
    """FP needs a legal prefix. A missed witness requires no alarm in that epoch.

    Coincident alarms are retained but are NOT credited as transaction-matched
    detections. This prevents fail-hit counts from inventing independent hits.
    """
    bycycle = {r['cycle']: r for r in oracle['events']}
    bycheck = {r['cycle']: r for r in checks}
    emitted = []
    alarm = False
    epoch = 0
    for row in trace:
        t = row['cycle']
        if not row[d['rst']]:
            alarm = False
            epoch += 1
            continue
        cc = bycheck.get(t)
        if cc is None or cc['fail'] is None or cc['trigger'] is None:
            emitted.append(dict(kind='checker_unknown', cycle=t)); continue
        verdict = bycycle[t]
        if verdict['classification'] == 'unknown_spec':
            continue
        if cc['fail'] and verdict['legal_prefix']:
            emitted.append(dict(kind='false_positive', cycle=t, epoch=epoch,
                                basis='entire prefix satisfies scoped obligations', obligations=verdict['checks']))
        if verdict['first_violation']:
            violated = [c for c in verdict['checks'] if not c['conditional'] and not c['passed']]
            if not alarm and not cc['fail']:
                emitted.append(dict(kind='miss', cycle=t, epoch=epoch, obligations=violated,
                                    basis='candidate accepts full reset-to-first-violation prefix'))
            else:
                emitted.append(dict(kind='alarm_attribution_unknown', cycle=t, epoch=epoch,
                                    obligations=violated, basis='alarm is not a transaction-identity proof'))
        alarm |= bool(cc['fail'])
    return emitted
