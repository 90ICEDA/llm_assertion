"""Bounded action acquisition; confirmed gaps are refinement work, not coverage credit."""
from collections import Counter
import random
import research64_search_value as base

OriginalPolicy = base.grammar.Policy
OriginalDecision = base.decision
OriginalUpdate = base.update
ACTIONS = (('overlap', None), ('reset_pending', None), ('tail_loss', None),
           ('backpressure', 1), ('backpressure', 4), ('backpressure', 16),
           ('drain', None), ('random', None))
TARGETS = {'overlap': ('order_payload',),
           'reset_pending': ('reset_cancellation', 'no_unsolicited_output'),
           'tail_loss': ('drain_no_loss',), 'drain': ('drain_no_loss',),
           'backpressure': ('stall_stability',), 'random': base.grammar.OBLIGATIONS}
NEW = ('contract_novelty', 'ordinary_no_repeat')


class Acquisition:
    def __init__(self, method, seed):
        self.method = method
        self.rng = random.Random(seed)
        self.attempted = set()
        self.checks = Counter()
        self.triggers = Counter()
        self.protected = Counter()
        self.ob_attempts = Counter()
        self.refinement = set()
        self.exposed = set()
        self.unknown_attempts = 0
        self.history = []

    def observe(self, family, result):
        action = (family, result.get('duration'))
        self.attempted.add(action)  # Unknown also consumes real query budget.
        view = dict(family=family, duration=action[1])
        if self.method == 'contract_novelty':
            self.ob_attempts.update(TARGETS[family])
            if result['status'] == 'ok':
                self.checks.update(result['fixed_obligation_checks'])
                self.triggers.update(result['effective_native_triggers'])
                self.protected.update(result['causal_protected'])
                self.refinement.update(result['gap_keys'])
                self.exposed.update(k.rsplit('/', 1)[-1] for k in result['obligation_gap_keys'])
            else:
                self.unknown_attempts += 1
            view.update(checks=dict(self.checks), triggers=dict(self.triggers),
                        protected=dict(self.protected), refinement_queue=sorted(self.refinement),
                        exposed_obligations=sorted(self.exposed), unknown_attempts=self.unknown_attempts)
        self.history.append(view)
        return view

    def choose(self):
        eligible = [a for a in ACTIONS if a not in self.attempted]
        if not eligible:
            return dict(stop=True, reason='finite action pool exhausted; unspent budget retained')
        scores = {}
        if self.method == 'contract_novelty':
            for ob in base.grammar.OBLIGATIONS:
                # A known gap is NOT a proof of protection. Only its acquisition urgency is removed.
                deficit = 1 if ob in self.exposed else (3 * (self.checks[ob] == 0)
                    + 2 * (self.triggers[ob] == 0) + 2 * (self.protected[ob] == 0) + 1)
                scores[ob] = deficit / (1 + self.ob_attempts[ob])
            ranking = {a: sum(scores[o] for o in TARGETS[a[0]]) / len(TARGETS[a[0]]) for a in eligible}
            best = max(ranking.values())
            eligible = [a for a in eligible if ranking[a] == best]
        family, duration = self.rng.choice(eligible)
        return dict(family=family, duration=duration, target_obligations=list(TARGETS[family]),
                    deficit_scores=scores, attempted_actions=sorted(map(str, self.attempted)),
                    refinement_queue=sorted(self.refinement),
                    reason='untried action; known gaps queued for refinement' if scores else 'uniform untried action; no outcome feedback')


def factory(method, seed):
    return Acquisition(method, seed) if method in NEW else OriginalPolicy(method, seed)


def decision(policy, method, seed, q, history):
    return policy.choose() if method in NEW else OriginalDecision(policy, method, seed, q, history)


def update(policy, method, family, result):
    return policy.observe(family, result) if method in NEW else OriginalUpdate(policy, method, family, result)


def tests():
    checks = []
    def check(name, value):
        assert value, name
        checks.append(name)
    empty = dict(duration=None, status='ok', fixed_obligation_checks={}, effective_native_triggers={},
                 causal_protected={}, gap_keys=[], obligation_gap_keys=[])
    for seed in (0, 1, 6503, 6521):
        p = Acquisition('contract_novelty', seed)
        gap = dict(empty, gap_keys=['hash/FN/reset_cancellation/reset_residue'],
                   obligation_gap_keys=['reset_residue/reset_cancellation'])
        p.observe('reset_pending', gap)
        check(f'{seed}:confirmed queued', len(p.refinement) == 1)
        p.observe('reset_pending', gap)
        check(f'{seed}:duplicate not new', len(p.refinement) == 1)
        actions = []
        for _ in range(7):
            d = p.choose(); a = (d['family'], d['duration']); actions.append(a)
            p.observe(d['family'], dict(empty, duration=d['duration']))
        check(f'{seed}:shared reset action excluded', all(a[0] != 'reset_pending' for a in actions))
        check(f'{seed}:no repeated action', len(set(actions)) == 7)
        check(f'{seed}:all stall boundaries retained', all(('backpressure', d) in actions for d in (1, 4, 16)))
        check(f'{seed}:explicit exhaustion', p.choose().get('stop'))
        q = Acquisition('contract_novelty', seed)
        q.observe('reset_pending', dict(gap, status='unknown'))
        check(f'{seed}:unknown cannot retire deficit', not q.exposed and not q.refinement and q.unknown_attempts == 1)
        a, b = Acquisition('ordinary_no_repeat', seed), Acquisition('ordinary_no_repeat', seed)
        a.observe('reset_pending', empty); b.observe('reset_pending', gap)
        check(f'{seed}:generic control blind to oracle', a.choose() == b.choose() and a.history == b.history)
    a, b = Acquisition('contract_novelty', 6503), Acquisition('contract_novelty', 6503)
    a.observe('reset_pending', empty)
    b.observe('reset_pending', dict(empty, gap_keys=['hash/FN/drain_no_loss/drop'], obligation_gap_keys=['drop/drain_no_loss']))
    check('observed gap changes acquisition priority', a.choose() != b.choose())
    return checks
