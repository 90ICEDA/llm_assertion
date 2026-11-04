"""Optional active temporal acquisition; no executor, oracle or hidden-test imports.

Structural differences are query hypotheses, never semantic equivalence proofs.
The caller adjudicates executed queries independently and supplies confirmed
observations only. Estimated costs select actions; actual costs report results.
"""
import hashlib
import itertools
import json
import re
from collections import Counter

DIMENSIONS = ('trigger', 'response', 'window', 'transaction', 'exception', 'vacuity')


def _text(candidate):
    if isinstance(candidate, str):
        return candidate
    for key in ('original_sva', 'sva', 'property', 'text'):
        if isinstance(candidate.get(key), str):
            return candidate[key]
    return json.dumps(candidate, sort_keys=True)


def describe(candidate):
    text = _text(candidate)
    flat = re.sub(r'\s+', '', text)
    parts = re.split(r'\|->|\|=>', text, maxsplit=1)
    known = len(parts) == 2 or (isinstance(candidate, dict) and 'antecedent' in candidate)
    ant = candidate.get('antecedent') if isinstance(candidate, dict) else None
    con = candidate.get('consequent') if isinstance(candidate, dict) else None
    ant = str(ant) if ant is not None else parts[0] if known else ''
    con = str(con) if con is not None else parts[-1] if known else ''
    delay = candidate.get('delay') if isinstance(candidate, dict) else None
    timing = candidate.get('timing') if isinstance(candidate, dict) else None
    windows = re.findall(r'##\s*(?:\[[^\]]+\]|\d+)|\|=>|\$past\([^)]*\)', text)
    transaction = re.findall(r'\$past\([^)]*\)|\b\w*(?:data|payload|tag|id|addr)\w*\b', con)
    exceptions = re.findall(r'disable\s+iff\s*\([^)]*\)|\b\w*(?:rst|reset|flush|ready|stall)\w*\b', text)
    return dict(trigger=re.sub(r'\s+', '', ant), response=re.sub(r'\s+', '', con),
                window=json.dumps([delay, timing, windows]), transaction=sorted(set(transaction)),
                exception=sorted(set(exceptions)), vacuity=ant.strip() in ('0', "1'b0", 'false'),
                parse_status='structural_only' if known else 'unknown_structure',
                content_sha256=hashlib.sha256(flat.encode()).hexdigest())


def analyze_candidates(candidates):
    descriptions = [describe(c) for c in candidates]
    pairs = []
    for i, j in itertools.combinations(range(len(descriptions)), 2):
        a, b = descriptions[i], descriptions[j]
        different = [d for d in DIMENSIONS if a[d] != b[d]]
        pairs.append(dict(a=i, b=j, dimensions=different,
                          identical_text=a['content_sha256'] == b['content_sha256'],
                          uncertain=a['parse_status'] == 'unknown_structure' or b['parse_status'] == 'unknown_structure'))
    return dict(candidates=descriptions, pairs=pairs,
                interpretation='Structural acquisition hints only; native replay determines behavioral disagreement.')


def rank_queries(queries, candidates, obligations, history):
    """Pure deterministic ranking, exposing every term and using no future outcome.

    No credit for unknowns. A known defect remains unprotected, but repeating its
    acquisition has lower novelty. A zero-failure query is not protection proof.
    """
    analysis = analyze_candidates(candidates)
    attempts = Counter(h.get('action_id') for h in history)
    # Exposure is not protection: a confirmed miss must never retire its obligation.
    protected = Counter(o for h in history if h.get('status') == 'confirmed' for o in h.get('protected_obligations', []))
    gaps = Counter(o for h in history if h.get('status') == 'confirmed' and h.get('gap_keys') for o in h.get('obligations', []))
    costs = {}
    for h in history:
        if h.get('actual_cost', 0) > 0:
            costs.setdefault(h.get('action_id'), []).append(h['actual_cost'])
    ranked = []
    for query in queries:
        q = dict(query)
        dims = set(q.get('dimensions', []))
        eligible = [p for p in analysis['pairs'] if not p['uncertain'] and not p['identical_text']]
        hits = [p for p in eligible if dims.intersection(p['dimensions'])]
        discrimination = len(hits) / max(1, len(eligible))
        targets = q.get('obligations') or list(obligations)
        deficit = sum(1 / (1 + protected[o]) for o in targets) / max(1, len(targets))
        novelty = 1 / (1 + attempts[q['id']] + sum(gaps[o] for o in targets) / max(1, len(targets)))
        prior_cost = q.get('estimated_cost', 1)
        if prior_cost <= 0:
            raise ValueError('estimated_cost must be positive')
        samples = costs.get(q['id'], [])
        estimate = sum(samples) / len(samples) if samples else prior_cost
        components = dict(candidate_discrimination=discrimination, obligation_deficit=deficit,
                          evidence_novelty=novelty, cost_estimate=estimate)
        q.update(score=(2 * discrimination + 2 * deficit + novelty) / estimate,
                 components=components, discriminated_pair_indices=[[p['a'], p['b']] for p in hits],
                 reason='(2*structural_pair_separation + 2*unprotected_obligation + novelty) / measured_or_estimated_cost',
                 evidence_is_prediction=True)
        ranked.append(q)
    return sorted(ranked, key=lambda q: (-q['score'], q['id']))


class ActiveSelector:
    def __init__(self, candidates, obligations):
        self.candidates, self.obligations, self.history = candidates, obligations, []

    def select(self, queries):
        ranking = rank_queries(queries, self.candidates, self.obligations, self.history)
        if not ranking:
            return dict(stop=True, reason='empty_query_pool')
        return dict(chosen=ranking[0], ranking=ranking, history=list(self.history))

    def observe(self, action_id, status, obligations=(), gap_keys=(), actual_cost=1, protected_obligations=()):
        self.history.append(dict(action_id=action_id, status=status,
                                 obligations=list(obligations), gap_keys=list(gap_keys), actual_cost=actual_cost,
                                 protected_obligations=list(protected_obligations)))
