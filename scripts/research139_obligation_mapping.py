"""Label-bound full-set adapter and gates. No model access or predicate repair.

Versioned replacement for the research135 positional adapter and the two
legacy OP trigger filters. Original scripts and experiment decisions stay intact.
"""
import copy
from pathlib import Path
import research136_prospective_history as prior
import research55_native_plan_alignment as alignment_base

x, old = prior.x, prior.x.old
read, dump = prior.read, prior.dump
OP = 'op_bit28_illegal'
BRANCH = 'illegal_branch_persists'
CONTRACT = ('JSON object with exactly operation,reason,assertions. operation=replace; reason string. '
            'assertions array length2..6. Each item has exactly antecedent,consequent,timing,obligations; '
            'text expressions, timing same_sample or next_sample. Each obligations is a one-element list '
            'containing illegal_branch_persists or op_bit28_illegal. Both obligations must be represented. '
            'Multiple properties may declare the same obligation, in any order. All predicates are editable. '
            'IDs are generated from array order only for native marker binding, never to infer obligation. '
            'Signals instr,instr_new,illegal_insn,rv32e,rv32m and supported sampled functions. '
            'No declarations or preassembled property fields.')


def adapt(value, current=None):
    if not isinstance(value, dict) or value.get('operation') != 'replace':
        raise ValueError('full_set_replace_required')
    candidate = old.assemble(value, current)
    if not 2 <= len(candidate['assertions']) <= 6:
        raise ValueError('full_set_two_to_six')
    for a in candidate['assertions']:
        if a['obligations'] not in ([OP], [BRANCH]):
            raise ValueError('exact_single_known_obligation')
    if {a['obligations'][0] for a in candidate['assertions']} != {OP, BRANCH}:
        raise ValueError('both_obligations_required')
    for raw, executable in zip(value['assertions'], candidate['assertions']):
        assert all(raw[k] == executable[k] for k in prior.q.FIELDS)
    return candidate


def ids(candidate, obligation):
    items = candidate['assertions']
    if len({a['id'] for a in items}) != len(items):
        raise ValueError('duplicate_assertion_ids')
    return {a['id'] for a in items if obligation in a['obligations']}


def mapped_assertions(row, candidate, obligation):
    allowed = ids(candidate, obligation)
    return [a for a in row['native']['assertions'] if a['id'] in allowed]


def validate_ledger(result, candidate):
    """Missing, duplicate or foreign marker bindings cannot become vacuous success."""
    all_ids = {a['id'] for a in candidate['assertions']}
    ids(candidate, OP)  # checks uniqueness even for an empty/failed ledger
    for row in result['ledger']:
        want = all_ids if row['obligation'] == 'encoding_controls' else ids(candidate, row['obligation'])
        got = [a['id'] for a in row['native']['assertions']]
        if len(got) != len(set(got)) or set(got) != want:
            raise ValueError('ledger_obligation_binding_mismatch')


def focus_gate(result, manifest, candidate):
    validate_ledger(result, candidate)
    checks = []
    phases = {k: dict(exposed=0, detected=0, triggered_revision_points=0) for k in ('first', 'held')}
    for target in manifest['targets']:
        rows = [r for r in result['ledger'] if r['sample']['sample_id'] == target['sample_id']
                and r['configuration'] == target['configuration']]
        before = [r for r in rows if r['revision'] == 'before']
        after = [r for r in rows if r['revision'] == 'after']
        bound = len(before) == len(after) == 1 and all(
            r['sample'] == target['sample'] and r['obligation'] == OP and r['required'] and r['expected'] == 1 for r in rows)
        valid = bound and before[0]['observed'] == 0 and after[0]['observed'] == 1
        executed = bound and all(r['native']['compile'] == 'ok' and r['native']['execution'] == 'ok'
                                 and r['native']['support'] == 'supported'
                                 and r['native']['attribution_status'] == 'confirmed' for r in rows)
        triggers = sum(any(a['trigger'] for a in mapped_assertions(r, candidate, OP)) for r in rows) if bound else 0
        detected = bound and any(a['causal_detection'] for a in mapped_assertions(before[0], candidate, OP))
        phase = 'first' if target['sample']['phase'] == 0 else 'held'
        phases[phase]['exposed'] += int(valid)
        phases[phase]['detected'] += int(detected)
        phases[phase]['triggered_revision_points'] += triggers
        checks.append(dict(sample_id=target['sample_id'], configuration=target['configuration'], phase=phase,
                           bound=bool(bound), independent_violation=bool(valid), native_execution_confirmed=bool(executed),
                           triggered_revision_points=triggers, detected=bool(detected),
                           passed=bool(valid and executed and detected and triggers == 2)))
    return dict(accepted=len(checks) == 12 and phases['first']['exposed'] == 3
                and phases['held']['exposed'] == 9 and all(c['passed'] for c in checks),
                phases=phases, checks=checks,
                scope='Same twelve fixed development sample/configuration points; label-bound properties, not positional IDs.')


def alignment(candidate, prep, folder):
    result = old.replay(candidate, read(prep/'alignment_cases.json'), 'alignment', folder, prep)
    validate_ledger(result, candidate)
    guard = x.all_guard(folder, result, candidate)
    windows = read(prep/'windows.public.json')
    context = alignment_base.prior.previous.source_check(prep)
    expected = {w['id']: w for w in context['expected']['windows']}
    bindings = []
    for w in windows:
        refs = [r for r in result['reference'] if r['transaction_id'] == w['transaction_id']
                and r['phase'] == w['phase'] and r['configuration'] == w['configuration']]
        ref = refs[0] if len(refs) == 1 else None
        match = ref is not None and ref['instruction'] == int(w['instruction_hex'], 16) and ref['instr_new'] == w['instr_new']
        match = match and all(ref['actual'][rev] == w[rev+'_illegal'] for rev in ('before', 'after'))
        required = expected[w['id']]['op_applicable']
        rows = [r for r in result['ledger'] if ref and r['sample']['sample_id'] == ref['sample_id']
                and r['configuration'] == w['configuration']]
        triggered = len(rows) == 2 and all(any(a['trigger'] for a in mapped_assertions(r, candidate, OP)) for r in rows)
        bindings.append(dict(window=w['id'], source_sample_id=w['sample_id'], replay_sample_id=ref['sample_id'] if ref else None,
                             original_sampling_matches=bool(match), op_required=required,
                             op_triggered_on_both_revisions=triggered, accepted=bool(match and (not required or triggered))))
    focus = focus_gate(result, read(prep/'focus.private.json'), candidate)
    gate = dict(accepted=bool(old.admissible(result) and guard['accepted'] and all(b['accepted'] for b in bindings) and focus['accepted']),
                bindings=bindings, counts=result['counts'], required_untriggered=len(result['required_untriggered']),
                all_property_guard=guard, native_status=result['native_status'], focus12=focus)
    dump(folder/'focus_gate.json', focus)
    dump(folder/'alignment_gate.json', gate)
    return result, gate


def decide(candidate, baseline, records, smallgate, folder):
    for result in records.values():
        validate_ledger(result, candidate)
    h, s = records['history'], records['search']
    hg, sg = x.all_guard(folder/'history', h, candidate), x.all_guard(folder/'search', s, candidate)
    ordinary = x.paired.ordinary(records['alignment'], smallgate, s, sg)
    full = x.paired.aggregate(h, s)
    history = x.g.prior.preserve(baseline, full, read(x.P/'target_preservation.private.json'), old.decide)
    history['accepted'] = bool(ordinary['accepted'] and history['accepted'] and hg['accepted'] and sg['accepted'])
    before, after = old.acceptance.inspect(baseline['ledger']), old.acceptance.inspect(full['ledger'])
    return dict(ordinary=ordinary, history=history,
                full_absolute=bool(ordinary['accepted'] and old.admissible(full) and hg['accepted'] and sg['accepted']),
                incremental_rejection=bool(ordinary['accepted'] and not history['accepted']),
                counts={k: r['counts'] for k, r in records.items()},
                new_false_alarm_ids=sorted(after['false_positives']-before['false_positives']),
                lost_detection_ids=sorted(before['detections']-after['detections']),
                retained_detection_ids=sorted(before['detections'] & after['detections']),
                current_gate=smallgate, all_property_guards=dict(search=sg, history=hg),
                required_untriggered=len(full['required_untriggered']), mapping=dict(history=h['mapping'], search=s['mapping']))


def evaluate(candidate, folder, baseline):
    small, gate = alignment(candidate, x.P, folder/'alignment')
    records = dict(alignment=small)
    for cohort in ('search', 'history'):
        records[cohort] = old.replay(candidate, read(x.P/(cohort+'_cases.json')), cohort, folder/cohort, x.P)
    result = decide(candidate, baseline, records, gate, folder)
    dump(folder/'decision.json', result)
    detail = {}
    for obligation in (BRANCH, OP):
        detail[obligation] = {}
        for ident in sorted(ids(candidate, obligation)):
            rows = [(r, a) for rec in records.values() for r in rec['ledger']
                    if r['obligation'] == obligation for a in r['native']['assertions'] if a['id'] == ident]
            detail[obligation][ident] = dict(
                trigger_evidence=sorted({r['evidence_id'] for r, a in rows if a['trigger']}),
                violation_evidence=sorted({r['evidence_id'] for r, a in rows if a['causal_detection']}))
    dump(folder/'assertion_evidence_mapping.json', detail)
    return result, records


def inspect_version(folder, candidate, baseline):
    n = sum(x.g.prior.diagnostic.audit_native(folder/k, candidate, x.P, k) for k in ('alignment', 'search', 'history'))
    records = {k: read(folder/k/'result.json') for k in ('alignment', 'search', 'history')}
    gate = read(folder/'alignment/alignment_gate.json')
    assert gate['focus12'] == focus_gate(records['alignment'], read(x.P/'focus.private.json'), candidate)
    for b in gate['bindings']:
        rows = [r for r in records['alignment']['ledger'] if r['sample']['sample_id'] == b['replay_sample_id']
                and r['configuration'] == next(w['configuration'] for w in read(x.P/'windows.public.json') if w['id'] == b['window'])]
        triggered = len(rows) == 2 and all(any(a['trigger'] for a in mapped_assertions(r, candidate, OP)) for r in rows)
        assert b['op_triggered_on_both_revisions'] == triggered
    result = decide(candidate, baseline, records, gate, folder)
    assert result == read(folder/'decision.json')
    return n, result, records


def request(candidate, records, folder, history, iteration):
    req = prior.request(candidate, records, folder, history, iteration)
    body = prior.json.loads(req['messages'][1]['content'])
    body['output_contract'] = CONTRACT
    req['messages'][1]['content'] = prior.json.dumps(body, separators=(',', ':'))
    return req
