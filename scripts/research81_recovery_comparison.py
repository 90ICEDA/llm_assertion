"""Fixed-budget plan-first versus direct-generation recovery pilot.

Old failures are immutable. No remote call during prepare/qualify/audit.
Final native acceptance is identical; only the helper workflow differs.
"""
import argparse
import copy
import json
from pathlib import Path

import research80_presentation_pilot as prior
from research80_budget import Budget as DurableBudget, BudgetError

g, b, ROOT, read, dump = prior.g, prior.b, prior.ROOT, prior.read, prior.dump
BASE = ROOT / 'deliverables/research80_prepare_20261024_r02'
OLD = ROOT / 'deliverables/research80_real_20261025_r01'
SEED = 8107
ARMS = ('P', 'D')
CAPS = {'windows': 5, 'public': 14, 'history': 105}


class Budget(DurableBudget):
    def __init__(self, path, model):
        self.path = Path(path)
        if self.path.exists():
            raise BudgetError('resume_not_allowed')
        self.model, self.seed = model, SEED
        self.state = dict(maximum=4, seed=SEED, stopped=False, events=[], arms={
            a: dict(calls=[], completed=[], plan_passed=False, accepted=False,
                    terminal=False, frozen=False, phases=[], passed=[]) for a in ARMS})
        self.save()

    def reserve(self, arm, stage, request):
        self.require(arm in ARMS, 'unknown_arm')
        s = self.state['arms'][arm]
        self.require(not self.state['stopped'] and not s['terminal'] and not s['frozen'], 'closed')
        expected = ('plan', 'generate') if arm == 'P' else ('generate', 'refine')
        n = len(s['calls'])
        self.require(n < 2 and stage == expected[n], 'no_retry_or_slot_transfer')
        self.require(n == len(s['completed']), 'previous_call_not_completed')
        self.require(not (arm == 'P' and n == 1) or s['plan_passed'] is True, 'complete_plan_required')
        self.require(request.get('seed') == SEED and request.get('model') == self.model, 'sampler_changed')
        self.require(request.get('max_tokens') == 2048 and request.get('temperature') == 0.2, 'sampling_cap_changed')
        size = sum(len(m['content']) for m in request['messages'])
        self.require(size <= 64000, 'request_size_cap')
        self.require(sum(len(x['calls']) for x in self.state['arms'].values()) < 4, 'total_cap')
        s['calls'].append(stage)
        self.event('model_reserved', arm, stage=stage, request_sha256=b.loop.sha(request), characters=size)

    def complete(self, arm, stage, accepted):
        s = self.state['arms'][arm]
        self.require(len(s['calls']) == len(s['completed']) + 1 and s['calls'][-1] == stage, 'bad_completion')
        if stage == 'plan':
            self.require(arm == 'P', 'plan_arm')
            s['plan_passed'] = accepted is True
            if accepted is not True:
                s['terminal'] = True
        else:
            if accepted is True:
                self.require(stage + ':history' in s['passed'], 'complete_history_required')
            s['accepted'] = accepted is True
            if accepted is True or len(s['calls']) == 2:
                s['terminal'] = True
        s['completed'].append(stage)
        self.event('call_completed', arm, stage=stage, accepted=accepted is True)

    def native(self, arm, stage, phase, count):
        s = self.state['arms'][arm]
        self.require(not self.state['stopped'] and not s['terminal'], 'closed')
        self.require(s['calls'] and s['calls'][-1] == stage and stage != 'plan'
                     and len(s['calls']) == len(s['completed']) + 1, 'pending_generation_required')
        self.require(phase in CAPS and count == CAPS[phase], 'native_case_cap')
        key = stage + ':' + phase
        self.require(key not in s['phases'], 'native_repeat')
        previous = {'public': 'windows', 'history': 'public'}.get(phase)
        self.require(previous is None or stage + ':' + previous in s['passed'], 'native_order')
        s['phases'].append(key)
        self.event('native_reserved', arm, stage=stage, phase=phase, cases=count)

    def phase_pass(self, arm, stage, phase):
        s = self.state['arms'][arm]
        key = stage + ':' + phase
        self.require(key in s['phases'] and key not in s['passed'], 'unexecuted_or_repeated_phase')
        s['passed'].append(key)
        self.event('native_passed', arm, stage=stage, phase=phase)

    def freeze(self, arm, candidate_hash):
        s = self.state['arms'][arm]
        self.require(not s['frozen'], 'already_frozen')
        s.update(terminal=True, frozen=True)
        self.event('freeze', arm, candidate_hash=candidate_hash)

    def independent(self):
        self.require(not self.state['stopped'], 'global_stop')
        self.require(all(s['frozen'] for s in self.state['arms'].values()), 'all_freezes_required')
        self.require(any(s['accepted'] for s in self.state['arms'].values()), 'new_acceptance_required')
        self.require(not any(e['kind'] == 'independent_started' for e in self.state['events']), 'no_second_batch')
        self.event('independent_started', None, scenarios=56)


def requests():
    template = copy.deepcopy(read(BASE / 'arms/A/sva_template.json'))
    old_plan = read(BASE / 'arms/A/request.preview.json')
    plan_body = json.loads(old_plan['messages'][1]['content'])
    common = json.loads(template['messages'][1]['content'])
    for key in ('actual_previous_attempt', 'verified_model_hold_plan', 'execution_contract'):
        common.pop(key, None)
    rows = read(BASE / 'arms/A/windows.private.json')
    common['hold_development_samples'] = [r['public'] for r in rows]
    common['hold_specification'] = plan_body['specification']
    # Exactly the same RTL, initial candidate, AST interface and development
    # observations are available in both arms, including the planning stage.
    template.update(seed=SEED, max_tokens=2048, temperature=0.2)
    template['messages'][1]['content'] = json.dumps(common)
    plan = copy.deepcopy(template)
    plan['messages'] = [dict(role='system', content=old_plan['messages'][0]['content']),
                       dict(role='user', content=json.dumps(dict(
                           task=plan_body['task'], instruction=plan_body['instruction'],
                           response_schema=g.schema(rows), common_development=common)))]
    return common, plan, template


def check_requests(common, plan, direct):
    assert json.loads(plan['messages'][1]['content'])['common_development'] == common
    assert json.loads(direct['messages'][1]['content']) == common
    for req in (plan, direct):
        assert req['seed'] == SEED and req['max_tokens'] == 2048 and req['temperature'] == 0.2
        assert sum(len(m['content']) for m in req['messages']) <= 64000
        text = json.dumps(req)
        assert not any(k in text for k in ('windows.private', 'source_sha256', 'research80_real',
                                           'verified_model_hold_plan', 'api_key', 'Authorization:'))


def prepare(out):
    prior.verify(BASE)
    out.mkdir(parents=True, exist_ok=False)
    common, plan, direct = requests()
    check_requests(common, plan, direct)
    dump(out / 'common_development.json', common)
    dump(out / 'P/request.preview.json', plan)
    dump(out / 'D/request.preview.json', direct)
    dump(out / 'sva_template.json', direct)
    for name in ('initial.json', 'cases.json', 'history_cases.json', 'window_cases.json',
                 'excluded_inputs.json', 'protected.json'):
        dump(out / name, read(BASE / name))
    dump(out / 'windows.private.json', read(BASE / 'arms/A/windows.private.json'))
    config = read(BASE / 'arms/A/model_config.json')
    config['max_model_calls'] = 1
    config['call_timeout'] = 300
    config['options']['seed'] = SEED
    dump(out / 'model_config.json', config)
    dump(out / 'protocol.json', dict(
        seed=SEED, maximum_calls=4, per_arm_maximum=2, arms=list(ARMS), order=list(ARMS),
        endpoint=config['remote_url'], model=config['remote_model'], temperature=0.2,
        max_output_tokens=2048, input_character_cap=64000, timeout_seconds=300,
        retries=0, slot_transfer=False, automatic_expansion=False,
        P='One complete plan; only actual full pass permits one SVA call. Failed plan stops P.',
        D='One direct SVA; only native/interface rejection permits one evidence-based refinement. No plan prerequisite.',
        common_information_sha256=b.loop.sha(common),
        acceptance='Identical 5 native window cases,14 public cases,105 history,required triggers,causal targets,no legal FP or critical unknown. No acceptance based on model prose.',
        estimand='Bounded two-call helper WORKFLOW comparison, not pure gate causality, not core mechanism ablation. D has up to two SVA opportunities; P spends one slot planning. Report calls/tokens/native costs and opportunity differences.',
        scope='One fixed seed and selected observed FIFO recovery task. No stable/general effect estimate.',
        repeat='Within-arm executable hash repetition including baseline rejects before compilation.',
        feedback='Only own actual call and native development diagnostics; no cross-arm response,corrected plan,archived success or independent tests.',
        holdout='After BOTH arms freeze and any new acceptance,generate one fresh56-case batch,depths2/4/8,five actual exposures;replay each distinct frozen hash once. Never refine using holdout.',
        stop='Transport/execution/size exception stops all calls. Failed gate stops P. Accepted candidate stops its arm. No new accepted independent-pass means stop; no automatic seed or prompt changes.',
        authorization='Requires new explicit <=4 calls for this protocol. Research80 unused slots remain restricted.'))
    bindings = read(BASE / 'source_bindings.json')
    bindings[str(BASE / 'sealed.json')] = b.search.digest(BASE / 'sealed.json')
    dump(out / 'source_bindings.json', bindings)
    # Seal only after checks and native controls; no model call is possible yet.
    print('PREPARED_NOT_SEALED', out, flush=True)


def native_admission(prep, version, candidate, edit, *, budget=None, arm=None, stage=None, repeated=False):
    rows, cases = read(prep / 'windows.private.json'), read(prep / 'window_cases.json')
    wr = small = full = None
    def replay(phase, filename):
        data = read(prep / filename)
        if budget:
            budget.native(arm, stage, phase, len(data))
        return b.loop.replay(candidate, version / phase, data)
    def passed(phase):
        if budget:
            budget.phase_pass(arm, stage, phase)
    if candidate and not repeated:
        wr = replay('windows', 'window_cases.json')
    wg = g.old.sem.native_windows(wr, rows, cases, version / 'windows')
    if repeated:
        wg = dict(accepted=False, reasons=[dict(kind='repeated_executable')])
    dump(version / 'window_gate.json', wg)
    if wg['accepted']:
        passed('windows')
        small = replay('public', 'cases.json')
    before = read(g.old.sem.SOURCE / 'baseline_public/result.json')
    historical = read(g.old.sem.SOURCE / 'baseline_history/result.json')
    plain = b.paired.current_decision(before, small, edit) if small else dict(accepted=False, reasons=wg['reasons'])
    dump(version / 'ordinary_decision.json', plain)
    if plain['accepted']:
        passed('public')
        full = replay('history', 'history_cases.json')
    decision = g.old.policy.decision_for(plain, full, historical, True)
    if decision['accepted']:
        passed('history')
    dump(version / 'decision.json', decision)
    return decision, wr, small, full


def refinement_request(template, initial, version, call, edit, decision, wr, small, full, *, persist=True):
    # Scope window feedback separately; each fact is from a real completed replay.
    diagnostic = g.old.policy.feedback_for(small, full, decision, call, edit, None, True)
    if wr is not None:
        diagnostic['window_native_replay'] = b.campaign.feedback(wr, read(version / 'window_gate.json'), call, edit)
    if persist:
        dump(version / 'next_feedback.json', diagnostic)
    return b.campaign.request_from(template, initial, SEED, diagnostic)


def run_arm(prep, out, arm, budget, models):
    loc = out / 'arms' / arm
    initial = read(prep / 'initial.json')
    current, accepted, status = initial, False, 'not_started'
    template = read(prep / 'sva_template.json')
    request = read(prep / arm / 'request.preview.json')
    seen = {b.interface.executable_hash(initial)}
    try:
        if arm == 'P':
            budget.reserve(arm, 'plan', request)
            model = g.old.PlanModel(loc / 'plan_model', read(prep / 'model_config.json'), request)
            models.append(model)
            call, plan = model.call(loc / 'plan/v0/model_call', initial, 'stall_stability', {}, 'research81_plan')
            if call['status'] != 'response_received':
                status = 'transport_stopped'
                budget.stop(status)
                return
            verdict = g.validate(plan, read(prep / 'windows.private.json'))
            dump(loc / 'plan/v0/decision.json', verdict)
            budget.complete(arm, 'plan', verdict['accepted'])
            status = 'plan_rejected'
            print(arm, 'PLAN', verdict['accepted'], flush=True)
            if not verdict['accepted']:
                return
            request = g.unlock(template, plan, verdict, read(prep / 'windows.private.json'))
        for i in range(1 if arm == 'P' else 2):
            stage = 'generate' if i == 0 else 'refine'
            version = loc / 'core' / f'v{i}'
            dump(version / 'request.preview.json', request)
            budget.reserve(arm, stage, request)
            model = g.old.policy.Model(loc / f'model_{i}', read(prep / 'model_config.json'), request)
            models.append(model)
            call, candidate = model.call(version / 'model_call', initial, 'stall_stability', {}, 'research81_' + stage)
            if call['status'] != 'response_received':
                status = 'transport_stopped'
                budget.stop(status)
                return
            edit_path = version / 'model_call/model_edit.json'
            edit = read(edit_path) if edit_path.exists() else None
            repeated = bool(candidate and b.interface.executable_hash(candidate) in seen)
            if candidate:
                seen.add(b.interface.executable_hash(candidate))
            decision, wr, small, full = native_admission(prep, version, candidate, edit,
                budget=budget, arm=arm, stage=stage, repeated=repeated)
            dump(version / 'repeat_check.json', dict(repeated=repeated))
            current = b.journal(version, current, candidate, decision)
            accepted = decision['accepted']
            budget.complete(arm, stage, accepted)
            status = 'native_accepted' if accepted else 'native_rejected'
            print(arm, stage, accepted, flush=True)
            if accepted:
                break
            if arm == 'D' and i == 0:
                request = refinement_request(template, initial, version, call, edit, decision, wr, small, full)
    except BaseException as exc:
        status = 'execution_exception'
        budget.stop(status)
        dump(loc / 'exception.json', dict(type=type(exc).__name__, detail=str(exc)))
        raise
    finally:
        b.loop.freeze(loc / 'core', current, 'arm_terminal_before_common_independent')
        budget.freeze(arm, b.loop.sha(current))
        dump(loc / 'outcome.json', dict(status=status, accepted=accepted,
            frozen_hash=b.loop.sha(current), calls=len(budget.state['arms'][arm]['calls'])))


def verify(prep):
    g.old.verify(prep)
    protocol = read(prep / 'protocol.json')
    assert protocol['maximum_calls'] == 4 and protocol['seed'] == SEED
    assert read(prep / 'qualification.json')['passed']
    assert read(prep / 'local_checks.json')['passed']
    assert read(prep / 'preflight.json')['passed']


def run(prep, out, authpath):
    verify(prep)
    auth, protocol = read(authpath), read(prep / 'protocol.json')
    assert type(auth['authorized_calls']) is int and auth['authorized_calls'] == 4
    assert auth['prepared_sha256'] == b.search.digest(prep / 'sealed.json')
    assert auth['model'] == protocol['model'] and auth['endpoint'] == protocol['endpoint']
    assert auth['seed'] == SEED and auth['run_output'] == out.relative_to(ROOT).as_posix()
    out.mkdir(parents=True, exist_ok=False)
    dump(out / 'authorization.json', auth)
    dump(out / 'protocol.json', protocol)
    budget, models, independent = Budget(out / 'budget.json', protocol['model']), [], {}
    status = 'running'
    try:
        with b.extension.installed():
            for arm in ARMS:
                run_arm(prep, out, arm, budget, models)
                if budget.state['stopped']:
                    status = 'stopped_no_expansion'
                    return
            frozen = {a: read(out / 'arms' / a / 'core/frozen_candidate.json') for a in ARMS}
            dump(out / 'all_frozen.json', {a: b.loop.sha(v) for a, v in frozen.items()})
            if not any(s['accepted'] for s in budget.state['arms'].values()):
                status = 'no_accepted_version_stop'
                return
            budget.independent()
            development = sum((read(prep / n) for n in ('window_cases.json', 'cases.json', 'history_cases.json')), [])
            split, measured = None, {}
            for arm in ARMS:
                candidate, h = frozen[arm], b.loop.sha(frozen[arm])
                if h not in measured:
                    loc = out / 'independent_by_hash' / h
                    with prior.independent_case_cap():
                        b.holdout(loc, candidate, development, set(read(prep / 'excluded_inputs.json')['input_hashes']), fixed_split=split)
                    if split is None:
                        split = read(loc / 'independent/split.json')
                        dump(out / 'common_independent_split.json', split)
                    measured[h] = loc.relative_to(out).as_posix()
                summary = read(out / measured[h] / 'independent/summary.json')
                independent[arm] = dict(path=measured[h], candidate_hash=h,
                    passed=summary['all_five_pass_on_first_attributed_evidence'],
                    qualified=budget.state['arms'][arm]['accepted'] and summary['all_five_pass_on_first_attributed_evidence'])
                dump(out / 'independent_mapping.json', independent)
            status = 'qualified_no_expansion' if any(v['qualified'] for v in independent.values()) else 'independent_failed_stop'
    except BaseException as exc:
        status = 'execution_exception_stop'
        budget.stop(status)
        dump(out / 'exception.json', dict(type=type(exc).__name__, detail=str(exc)))
        raise
    finally:
        for arm in ARMS:
            loc = out / 'arms' / arm
            if not (loc / 'outcome.json').exists():
                initial = read(prep / 'initial.json')
                b.loop.freeze(loc / 'core', initial, 'not_run_after_global_stop')
                budget.freeze(arm, b.loop.sha(initial))
                dump(loc / 'outcome.json', dict(status='not_run_global_stop', accepted=False, frozen_hash=b.loop.sha(initial), calls=0))
        cost = g.old.cost_audit(out, b.paired.files(out))
        dump(out / 'cost.json', cost)
        dump(out / 'outcome.json', dict(status=status, actual_model_calls=cost['total']['model_calls'],
            reserved_calls=sum(len(s['calls']) for s in budget.state['arms'].values()),
            new_accepted_versions=sum(s['accepted'] for s in budget.state['arms'].values()),
            completed_history_replays=len(list((out / 'arms').glob('*/core/v*/history/result.json'))),
            new_independent_passes=sum(x['qualified'] for x in independent.values()), independent=independent,
            core_mechanism_increment_evidence=0, automatic_expansion=False,
            protected_unchanged=g.old.old.screen.protected() == read(prep / 'protected.json')))
        print('TERMINAL', status, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['prepare', 'verify', 'run'])
    p.add_argument('--prepared', type=Path)
    p.add_argument('--out', type=Path)
    p.add_argument('--authorization', type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        prepare(a.out.resolve())
    elif a.action == 'verify':
        verify(a.prepared.resolve())
        print('VERIFIED')
    else:
        run(a.prepared.resolve(), a.out.resolve(), a.authorization.resolve())
