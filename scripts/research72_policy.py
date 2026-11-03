"""Execute the already specified independent, bounded 3x4 policy experiment.

Prepare is local only. Run requires a NEW explicit <=24 call authorization.
No research71 responses, decisions or test outcomes are used for adaptation.
"""
import argparse
import copy
import json
from pathlib import Path
import time

import research71_paired_run as paired

b, ROOT, read, dump = paired.b, paired.ROOT, paired.read, paired.dump
P = paired.P
ARMS = b.paired.ARMS
KEYS = paired.KEYS
MAX_CALLS = 24
ROUNDS = 2


class Model(paired.pilot.Model):
    def __init__(self, folder, config, request):
        super().__init__(folder, config, request)
        # Parent transport already executes with 300 seconds. Correct only its
        # inherited metadata; no payload, sampler or transmission changes.
        path = self.out/'remote_transport_config.json'
        metadata = read(path)
        metadata['timeout_seconds'] = min(300, config['call_timeout'])
        dump(path, metadata)


def decision_for(plain, full, historical, use_gate):
    assert use_gate or full is None, 'ordinary_arm_must_not_read_hidden_history'
    hg = None
    if use_gate:
        hg = (b.gate.decide(historical['group']['ledger'], full['group']['ledger'])
              if full and full.get('group') else
              dict(accepted=False, reasons=[dict(kind='history_unavailable')]))
    reasons = list(plain['reasons']) + (hg['reasons'] if use_gate else [])
    if use_gate and full and not full['healthy']:
        reasons.append(dict(kind='history_native_unhealthy'))
    accepted = bool(plain['accepted'] and
                    (not use_gate or (full and full['healthy'] and hg['accepted'])))
    return dict(accepted=accepted, reasons=reasons, ordinary_accepted=plain['accepted'],
                use_gate=use_gate, historical=hg,
                gate_incremental_rejection=bool(use_gate and plain['accepted'] and not accepted))


def feedback_for(small, full, decision, call, edit, previous_edit, use_gate):
    assert use_gate or full is None, 'hidden_history_feedback_forbidden'
    assert decision['use_gate'] == use_gate
    feedback = b.campaign.attempt_feedback(small, full, decision, call, edit, previous_edit)
    assert ('historical_replay' in feedback) == (full is not None)
    return feedback


def reserve(budget, arm, iteration):
    assert 0 <= iteration < ROUNDS
    assert budget['reserved'] < MAX_CALLS
    assert budget['per_arm'].get(arm, 0) == iteration, 'no_resend_or_transferred_slot'
    budget['reserved'] += 1
    budget['per_arm'][arm] = iteration + 1
    dump(budget['path'], {k:v for k,v in budget.items() if k != 'path'})


def run_arm(prep, out, seed, name, budget, models, model_type=Model):
    """Each arm starts at the same baseline, with its own real Model instance."""
    arm = ARMS[name]; use_gate = arm['gate']
    stream = 'search' if arm['search'] else 'ordinary'
    ready = P/'ready'/f's{seed}'
    initial = read(P/'shared_initial.json'); current = initial
    before = b.campaign.baseline(ready, stream)
    cases = read(ready/stream/'cases.json')
    history = historical = None
    if use_gate:
        history = read(P/'history_cases.json')
        binding = read(P/'history_binding.json'); path = b.gate.portable(binding['path'])
        assert b.search.digest(path) == binding['sha256']
        historical = read(path)
    source = read(prep/f's{seed}'/name/'request.preview.json')
    config = read(prep/f's{seed}'/name/'model_config.json')
    model = model_type(out/'model', config, source); models.append(model)
    dump(out/'initial_state.json', dict(candidate_hash=b.loop.sha(initial),
        source='shared qualified partial baseline', complete_protection=False,
        independent_physical_model=True, search=arm['search'], gate=use_gate))
    accepted = False; decisions = []; previous_edit = None
    seen = {b.interface.executable_hash(initial)}
    for iteration in range(ROUNDS):
        folder = out/'core'/f'v{iteration}'
        assert not folder.exists(), 'existing_attempt_requires_audit_not_resend'
        reserve(budget, f's{seed}/{name}', iteration)
        call, proposal = model.call(folder/'model_call', current, 'stall_stability', {},
                                    'independent_bounded_policy')
        if call['status'] != 'response_received':
            b.journal(folder, current, None, dict(accepted=False,
                      reasons=[dict(kind='transport_terminal', status=call['status'])]))
            dump(out/'interrupted.json', dict(status=call['status'], iteration=iteration,
                 candidate_hash=b.loop.sha(current), no_complete_arm_verdict=True))
            raise paired.TransportStop(call['status'])
        edit_path = folder/'model_call/model_edit.json'
        edit = read(edit_path) if edit_path.exists() else None
        repeated = bool(proposal and edit['operation'] != 'keep' and
                        b.interface.executable_hash(proposal) in seen)
        if proposal: seen.add(b.interface.executable_hash(proposal))
        small = b.loop.replay(proposal, folder/'visible_native', cases) if proposal and not repeated else None
        plain = (b.paired.current_decision(before, small, edit) if small else
                 dict(accepted=False, reasons=[dict(kind='repeated_executable' if repeated
                                                   else 'model_or_interface_failure')]))
        dump(folder/'ordinary_decision.json', plain)
        full = b.loop.replay(proposal, folder/'history_native', history) if proposal and not repeated and use_gate else None
        decision = decision_for(plain, full, historical, use_gate)
        decision.update(call=call, repeated_executable=repeated,
                        candidate_hash=b.loop.sha(proposal) if proposal else None,
                        visible_counts=small['counts'] if small else None,
                        history_counts=full['counts'] if full else None)
        dump(folder/'decision.json', decision)
        current = b.journal(folder, current, proposal, decision)
        decisions.append(decision); accepted = decision['accepted']
        print('POLICY', seed, name, iteration, 'accepted', accepted,
              'extra_history_rejection', decision['gate_incremental_rejection'], flush=True)
        if accepted: break
        diagnostic = feedback_for(small, full, decision, call, edit, previous_edit, use_gate)
        dump(folder/'next_feedback.json', diagnostic)
        if iteration + 1 < ROUNDS:
            model.request = b.campaign.request_from(source, current, seed, diagnostic)
            dump(folder/'next_request.preview.json', model.request)
        previous_edit = edit
    b.loop.freeze(out/'core', current, 'arm_terminal_before_all_arm_freeze_barrier')
    result = dict(accepted=accepted, frozen_hash=b.loop.sha(current), calls=len(model.calls),
        new_executable_version=b.interface.executable_hash(current) != b.interface.executable_hash(initial),
        search=arm['search'], gate=use_gate, rounds=decisions,
        history_rejection_followed_by_acceptance=bool(accepted and any(
            d['gate_incremental_rejection'] for d in decisions[:-1])))
    dump(out/'outcome.json', result)
    return current, result


def measure(prep, out, frozen, decisions):
    paired.barrier(decisions)
    dump(out/'all_arms_freeze.json', decisions)
    history = read(P/'history_cases.json')
    binding = read(P/'history_binding.json'); historic = read(b.gate.portable(binding['path']))
    acquired = [c for seed in b.SEEDS for c in read(P/'ready'/f's{seed}'/'search_cases.json')]
    development = history + [c for seed in b.SEEDS for n in ('common_cases.json','search_cases.json')
                             for c in read(P/'ready'/f's{seed}'/n)]
    excluded = set(read(prep/'excluded_inputs.json')['input_hashes'])
    common = None; evaluations = {}
    for key, candidate in frozen.items():
        h = b.loop.sha(candidate)
        if h not in evaluations:
            dest = out/'evaluation'/h
            b.loop.freeze(dest/'core', candidate, 'all12_frozen_measurement_only')
            # Measurement occurs only after ALL trajectories stop. Never feeds a model.
            full = b.loop.replay(candidate, dest/'history_native', history)
            targets = b.loop.replay(candidate, dest/'search_native', acquired)
            gate = (b.gate.decide(historic['group']['ledger'], full['group']['ledger'])
                    if full.get('group') else dict(accepted=False, reasons=[dict(kind='history_unavailable')]))
            dump(dest/'measurement.json', dict(history_counts=full['counts'], search_counts=targets['counts'],
                history_gate=gate, history_healthy=full['healthy'], search_healthy=targets['healthy'],
                no_feedback_no_selection=True))
            b.holdout(dest, candidate, development, excluded, common)
            if common is None:
                common = read(dest/'independent/split.json'); dump(out/'common_independent_split.json', common)
            evaluations[h] = dest.relative_to(out).as_posix()
            print('INDEPENDENT_POLICY', h, read(dest/'independent/summary.json')['all_five_pass_on_first_attributed_evidence'], flush=True)
        dump(out/'arms'/key/'evaluation_binding.json', dict(candidate_hash=h,
            physical_evaluation=evaluations[h], shared_exact_candidate=True, unique_statistical_sample=False))


def prepare(out):
    paired.prepared.verify(P)
    assert read(paired.A/'audit.json')['all_three_seeds_qualified']
    out.mkdir(parents=True, exist_ok=False)
    requests = {}; bindings = {}
    for seed in b.SEEDS:
        ready = P/'ready'/f's{seed}'
        for rel, h in read(ready/'sealed.json').items(): assert b.search.digest(ready/rel) == h, rel
        for name, arm in ARMS.items():
            stream = 'search' if arm['search'] else 'ordinary'
            source = ready/stream/'request.preview.json'
            request = read(source); requests[f's{seed}/{name}'] = request
            dump(out/f's{seed}'/name/'request.preview.json', request)
            config = read(ready/'model_config.json'); assert config['max_model_calls'] == ROUNDS
            dump(out/f's{seed}'/name/'model_config.json', config)
            bindings[str(source)] = b.search.digest(source)
        assert requests[f's{seed}/A'] == requests[f's{seed}/C']
        assert requests[f's{seed}/B'] == requests[f's{seed}/D']
    dump(out/'request_bindings.json', bindings)
    # Reuse the audited development exclusion inventory. Read research71 test
    # inputs only to exclude their hashes; no outcomes, proposals or labels.
    inventory = read(ROOT/'deliverables/research71_prepare_20261024_r01/excluded_inputs.json')
    split_path = ROOT/'deliverables/research71_real_20261024_r01/common_independent_split.json'
    split = read(split_path)
    inventory['input_hashes'] = sorted(set(inventory['input_hashes']) |
        {b.loop.sha(c['rows']) for c in split['boundary_cases'] + split['drain_cases']})
    inventory['sources'].append(dict(path=str(split_path), sha256=b.search.digest(split_path), usage='hash-only exclusion; no outcome'))
    dump(out/'excluded_inputs.json', inventory)
    # Preserve the already published results by byte hashes, without using them
    # to select an arm, change a rule, or construct a prompt.
    old = ROOT/'deliverables/research71_real_20261024_r01'
    protected = {str(p):b.search.digest(p) for p in [old/'outcome.json', split_path,
                 ROOT/'deliverables/research71_prepare_20261024_r01/excluded_inputs.json']}
    for p in old.glob('evaluation/*/independent/summary.json'): protected[str(p)] = b.search.digest(p)
    dump(out/'protected_research71.json', protected)
    source_protocol = read(P/'protocol.json'); config = read(P/'ready/s6711/model_config.json')
    dump(out/'protocol.json', dict(experiment='research72_independent_policy', sealed_at=time.time(),
        seeds=list(b.SEEDS), arms=ARMS, maximum_calls=MAX_CALLS, per_arm_calls=ROUNDS,
        order=[f's{s}/{a}' for s in b.SEEDS for a in ARMS],
        endpoint=config['remote_url'], model=config['remote_model'], temperature=0.2,
        output_tokens_per_call=2048, timeout_seconds=300, retries=0,
        per_arm_conservative_token_budget=config['max_tokens'],
        per_arm_wall_seconds=config['max_wall_seconds'],
        actual_costs='Stop at own acceptance; no unused-call redistribution. Tokens/native/reference unequal costs reported. Shared cached search acquisition charged to B/D logically.',
        protocol_source_sha256=b.search.digest(P/'protocol.json'),
        unchanged_policy_estimand=source_protocol['policy_estimand'],
        initial_requests='Exact research70 sealed requests; A=C, B=D but ALL responses independently generated.',
        shared_helpers=source_protocol['common_helpers'],
        feedback='Unchanged research45 attempt_feedback/request_from; own prior attempts only; history only C/D. No cross-arm response reuse.',
        acceptance=source_protocol['historical_rule'], ordinary_acceptance=source_protocol['ordinary_rule'],
        repeated='Same executable within own arm rejected before compile; no cross-arm cache of model responses.',
        failure='Any transport failure stops entire experiment, no retries or incomplete-arm holdout. Preserve executed prefix and denominators.',
        evaluation='All12 terminal freezes precede measurements:105 history,3 acquired cases and fresh common56 independent scenarios. Exact hashes share native measurement, not independent statistical samples.',
        independent_tests='research71 batch hash-excluded only, preserved and never used for rule/prompt/candidate tuning. New test failures are not fed back.',
        estimands=['End-of-budget accepted/final-history/new-test protection by arm and seed',
                   'History-only rejection when own ordinary gate passes',
                   'Within-arm later acceptance restoring target/history after such rejection'],
        attribution='Independent responses permit policy comparison, not shared-proposal causal attribution. One FIFO/artificial-fault task; three fixed seeds, service determinism unverified.',
        authorization_required=True, authorized_calls=0))
    from research72_policy_checks import checks
    report = checks(out/'local_checks', out)
    dump(out/'checks.json', report)
    dump(out/'code_versions.json', {p.relative_to(ROOT).as_posix():b.search.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json', {p.relative_to(out).as_posix():b.search.digest(p) for p in out.rglob('*.json')})
    print('PREPARED_POLICY', len(report['checks']), 'checks;12 sealed initial requests;0 real calls', flush=True)


def verify(prep):
    paired.prepared.verify(P)
    for rel,h in read(prep/'sealed.json').items(): assert b.search.digest(prep/rel) == h, rel
    for rel,h in read(prep/'code_versions.json').items(): assert b.search.digest(ROOT/rel) == h, rel
    for group in ('request_bindings.json','protected_research71.json'):
        for path,h in read(prep/group).items(): assert b.search.digest(Path(path)) == h, path


def run(prep, out, authorization):
    verify(prep); protocol = read(prep/'protocol.json'); auth = read(authorization)
    assert auth['authorized_calls'] == MAX_CALLS and auth['purpose'] == 'research72_independent_policy'
    assert auth['endpoint'] == protocol['endpoint'] and auth['model'] == protocol['model']
    assert auth['protocol_sha256'] == b.search.digest(prep/'protocol.json')
    assert auth['run_output'] == out.relative_to(ROOT).as_posix()
    out.mkdir(parents=True, exist_ok=False)
    dump(out/'authorization.json', auth); dump(out/'protocol.json', protocol)
    budget = dict(reserved=0, per_arm={}, path=out/'attempt_budget.json')
    models = []; decisions = {}; frozen = {}; status = 'running'
    try:
        with b.extension.installed():
            for seed in b.SEEDS:
                for name in ARMS:
                    key = f's{seed}/{name}'
                    frozen[key], decisions[key] = run_arm(prep, out/'arms'/key, seed, name, budget, models)
            measure(prep, out, frozen, decisions)
            status = 'twelve_independent_policy_arms_completed'
    except paired.TransportStop as exc:
        status = 'terminal_' + str(exc)
        dump(out/'transport_stop.json', dict(status=status, reserved=budget['reserved'], no_retry=True,
            remaining_arms_not_executed=sorted(KEYS-set(decisions))))
    except BaseException as exc:
        status = 'execution_exception'; dump(out/'exception.json', dict(type=type(exc).__name__)); raise
    finally:
        verify(prep)
        dump(out/'outcome.json', dict(status=status, calls=sum(len(m.calls) for m in models),
            reserved=budget['reserved'], max_calls=MAX_CALLS, completed_arms=len(decisions),
            planned_arms=12, decisions=decisions, policy_effect_evaluated=status=='twelve_independent_policy_arms_completed'))
        dump(out/'cost.json', b.search.native_cost(out)); print('TERMINAL', status, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare','verify','run'))
    p.add_argument('--out', type=Path); p.add_argument('--prepared', type=Path)
    p.add_argument('--authorization', type=Path); a = p.parse_args()
    if a.action == 'prepare': prepare(a.out.resolve())
    elif a.action == 'verify': verify(a.prepared.resolve()); print('SEALED_POLICY_VERIFIED; no calls')
    else: run(a.prepared.resolve(), a.out.resolve(), a.authorization.resolve())
