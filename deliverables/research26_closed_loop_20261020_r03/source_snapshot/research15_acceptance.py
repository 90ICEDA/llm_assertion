"""Strict, evidence-scoped native assertion-set admission (2026-10-15).

The oracle is supplied by an independent transaction monitor. This module never
infers an obligation violation from an assertion failure. Native antecedent cover
is observation, not an entailment proof. All guarantees are replay-scoped.
"""
import hashlib
import json


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def inspect(ledger):
    """Normalize event rows and retain unknowns, missing native data and duplicates.

    Row identity: evidence_id, obligation, stimulus_sha256, oracle. oracle has
    legality=legal/illegal/unknown, verdict=satisfied/violated/unknown, and an
    independent validator name. native has compile=ok, support=supported,
    execution=ok, trigger_source=property_antecedent_cover and assertions[];
    each assertion has id, trigger(bool), failed(bool), causal_detection(bool).
    The adapter, not this gate, must establish causal_detection independently.
    """
    rows = {}
    errors = []
    fields = {name: set() for name in ('false_positives', 'detections', 'triggers', 'misses', 'unknown')}
    mapping = {}
    for row in ledger:
        key = row.get('evidence_id')
        if not key or key in rows:
            errors.append(dict(kind='missing_or_duplicate_evidence_id', evidence_id=key))
            continue
        rows[key] = row
        obligation = row.get('obligation')
        oracle, native = row.get('oracle', {}), row.get('native', {})
        invalid = (not obligation or not row.get('stimulus_sha256') or
                   oracle.get('legality') != 'legal' or
                   oracle.get('verdict') not in ('satisfied', 'violated') or
                   not oracle.get('validator') or
                   native.get('compile') != 'ok' or native.get('support') != 'supported' or
                   native.get('execution') != 'ok' or
                   native.get('trigger_source') != 'property_antecedent_cover' or
                   native.get('attribution_status') == 'unknown')
        assertions = native.get('assertions', [])
        ids = [a.get('id') for a in assertions]
        # An explicit empty obligation projection is known absence of protection,
        # whereas a missing measurement is unknown. No fake assertion is needed.
        invalid |= 'assertions' not in native or len(ids) != len(set(ids)) or not all(ids)
        invalid |= any(type(a.get(field)) is not bool for a in assertions
                       for field in ('trigger', 'failed', 'causal_detection'))
        invalid |= any(a.get('causal_detection') and (not a.get('failed') or not a.get('trigger'))
                       for a in assertions)
        if invalid:
            fields['unknown'].add(key)
            continue
        entry = mapping.setdefault(obligation, dict(assertions=set(), trigger_evidence=set(),
                                                    violation_evidence=set(), legal_evidence=set(), gaps=set()))
        if any(a['trigger'] for a in assertions):
            fields['triggers'].add(key)
            entry['trigger_evidence'].add(key)
        for a in assertions:
            if a['trigger']:
                entry['assertions'].add(a['id'])
        if oracle['verdict'] == 'satisfied':
            entry['legal_evidence'].add(key)
            if any(a['failed'] for a in assertions):
                fields['false_positives'].add(key)
                entry['gaps'].add(key)
        elif any(a['causal_detection'] for a in assertions):
            fields['detections'].add(key)
            entry['violation_evidence'].add(key)
        else:
            fields['misses'].add(key)
            entry['gaps'].add(key)
    return dict(rows=rows, errors=errors, **fields,
                mapping={ob: {k: sorted(v) for k, v in values.items()} for ob, values in mapping.items()})


def decide(before, after, target_keys=()):
    old, new = inspect(before), inspect(after)
    reasons = []
    for side, info in [('before', old), ('after', new)]:
        if not info['rows']:
            reasons.append(dict(kind='empty_replay', side=side))
        if info['errors']:
            reasons.append(dict(kind='malformed_ledger', side=side, errors=info['errors']))
        if side=='after' and info['unknown']:
            reasons.append(dict(kind='unconfirmed_replay', side=side, evidence_keys=sorted(info['unknown'])))
    removed = old['rows'].keys() - new['rows'].keys()
    if removed:
        reasons.append(dict(kind='missing_historical_replay', evidence_keys=sorted(removed)))
    changed = []
    for key in old['rows'].keys() & new['rows'].keys():
        identity = lambda row: {k: row.get(k) for k in ('obligation', 'stimulus_sha256', 'oracle')}
        if identity(old['rows'][key]) != identity(new['rows'][key]):
            changed.append(key)
    if changed:
        reasons.append(dict(kind='changed_evidence_identity', evidence_keys=sorted(changed)))
    for kind, keys in [
        ('new_legal_false_positive', new['false_positives'] - old['false_positives']),
        ('lost_target_detection', old['detections'] - new['detections']),
        ('lost_obligation_trigger', old['triggers'] - new['triggers']),
    ]:
        if keys:
            reasons.append(dict(kind=kind, evidence_keys=sorted(keys)))
    unresolved = []
    for key in target_keys:
        row = new['rows'].get(key, {})
        repaired = key not in new['unknown'] and (
            (row.get('oracle', {}).get('verdict') == 'violated' and key in new['detections']) or
            (row.get('oracle', {}).get('verdict') == 'satisfied' and key not in new['false_positives']
             and key in new['triggers']))
        if not repaired:
            unresolved.append(key)
    if unresolved:
        reasons.append(dict(kind='current_gap_not_confirmed_repaired', evidence_keys=sorted(unresolved)))
    return dict(accepted=not reasons, reasons=reasons,
                prior_unknown_evidence=sorted(old['unknown']),
                before_sha256=sha(before), after_sha256=sha(after),
                counts={side: {k: len(value[k]) for k in ('rows', 'unknown', 'triggers', 'false_positives', 'detections', 'misses')}
                        for side, value in [('before', old), ('after', new)]},
                obligation_assertion_evidence_mapping=new['mapping'],
                scope='Only identical replayed evidence; antecedent cover does not prove logical relevance or global non-regression.')
