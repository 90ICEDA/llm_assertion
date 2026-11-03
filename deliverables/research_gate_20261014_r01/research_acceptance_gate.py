"""Evidence-scoped assertion-set acceptance. No simulator or model dependency.

Keys identify replay inputs + reset epoch/transaction + obligation, never assertion
IDs. Changing assertion count/order therefore cannot erase historical failures.
The caller must independently establish causality and stimulus legality.
"""
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def decide(before, after, target_keys=()):
    """Reject unknown replay, new FP, lost detection, trigger loss or open target.

    A trigger key denotes an obligation evaluation on a specific legal witness,
    not just any antecedent becoming true. This remains bounded replay evidence.
    """
    reasons = []
    if before.get('status') != 'ok' or after.get('status') != 'ok':
        reasons.append({'kind': 'replay_unknown', 'before': before.get('status'), 'after': after.get('status')})
    for field, kind, reverse in [('false_positives', 'new_legal_false_positive', False),
                                  ('detections', 'lost_target_detection', True),
                                  ('effective_triggers', 'lost_effective_trigger', True)]:
        old, new = set(before.get(field, [])), set(after.get(field, []))
        lost = old-new if reverse else new-old
        if lost:
            reasons.append({'kind': kind, 'evidence_keys': sorted(lost)})
    unresolved = set(target_keys) & (set(after.get('false_positives', [])) | set(after.get('misses', [])))
    # A target disappearing through unknown/attribution loss is not a repair.
    unconfirmed = set(target_keys) - set(after.get('resolved_keys', []))
    if unresolved or unconfirmed:
        reasons.append({'kind': 'current_gap_not_confirmed_repaired', 'evidence_keys': sorted(unresolved | unconfirmed)})
    return {'accepted': not reasons, 'reasons': reasons,
            'scope': 'Only the replayed evidence; no global non-regression or formal proof.',
            'before_sha256': digest(before), 'after_sha256': digest(after)}


def merge(records):
    fields = ('false_positives', 'detections', 'effective_triggers', 'misses', 'resolved_keys')
    return dict(status='ok' if records and all(r['status']=='ok' for r in records) else 'unknown',
                **{key: sorted({v for r in records for v in r.get(key, [])}) for key in fields})
