"""Execute the sealed research123 two-call pilot without changing its protocol.

No transport during preflight. A purpose/output/seal-bound grant is required.
H is the sole possible continuation; R is a decision-only shadow, not an arm
with a separately sampled response or a third independent-test population.
"""
import argparse
import copy
import shutil
import time
from pathlib import Path
from unittest.mock import patch

import research123_history_contrast_prepare as p

s, x = p.s, p.x
ROOT, read, dump, sha = p.ROOT, p.read, p.dump, p.sha


def grant_check(grant, prep, out):
    assert grant['purpose'] == p.PURPOSE
    assert type(grant['authorized_calls']) is int and grant['authorized_calls'] == 2
    assert grant['endpoint'] == s.old.prior.transport.DEFAULT_URL
    assert grant['model'] == s.MODEL
    assert grant['prepared_sha256'] == sha(prep / 'sealed.json')
    assert grant['run_output'] == out.relative_to(ROOT).as_posix()


def healthy(records):
    return records is not None and all(r['healthy'] for r in records.values())


def next_action(decisions, status, records):
    return p.continuation(decisions, status, measured=healthy(records))


def preflight(prep, out):
    count = p.verify(prep)
    s.verify(p.PREP)
    request = read(prep / 'request.preview.json')
    initial = read(prep / 'initial.json')
    records = s.qualified.r.records(p.PREP / 'baseline_native')
    with patch.object(s, 'SEED', p.SEED):
        rebuilt = s.payload(initial, records, p.PREP / 'baseline_native', False, 0)
    assert request == rebuilt
    checks = ['sealed_frontend_exact', 'source116_seal_valid']
    for status, recs, expected in [
        ('response_received', {'test': {'healthy': True}}, 'history_once'),
        ('response_received', {'test': {'healthy': False}}, 'stop_interface_or_repeat'),
        ('response_received', None, 'stop_interface_or_repeat'),
        ('timeout', {'test': {'healthy': True}}, 'stop_transport')]:
        assert next_action(dict(O=True, H=False, R=False), status, recs) == expected
        checks.append('native_health/' + expected)
    assert next_action(dict(O=True,H=True,R=True), 'response_received', records) == 'stop_no_discriminating_proposal'
    checks.append('all_accept_stops')
    # Check the exact future grant schema without granting or calling anything.
    dummy_out = ROOT / 'deliverables/NOT_AUTHORIZED'
    fixture = dict(purpose=p.PURPOSE, authorized_calls=2, endpoint=s.old.prior.transport.DEFAULT_URL,
                   model=s.MODEL, prepared_sha256=sha(prep / 'sealed.json'),
                   run_output=dummy_out.relative_to(ROOT).as_posix())
    grant_check(fixture, prep, dummy_out)
    for field in fixture:
        bad = dict(fixture); bad[field] = 3 if field == 'authorized_calls' else 'wrong'
        try: grant_check(bad, prep, dummy_out)
        except AssertionError: checks.append('grant_reject/' + field)
        else: raise AssertionError(field)
    out.mkdir(parents=True, exist_ok=False)
    dump(out / 'checks.json', dict(passed=True, sealed_controller_checks=count, execution_checks=checks,
        model_calls=0, native_executions=0, credential_read=False))
    dump(out / 'execution_binding.json', dict(protocol_seal=sha(prep / 'sealed.json'),
        runner_sha256=sha(Path(__file__)), source_binding_sha256=sha(prep / 'input_bindings.json'),
        R_shadow_of='H', physical_terminal_arms=['O','H']))
    print('PREFLIGHT126', count + len(checks), 'checks; calls0', flush=True)


def independent_inputs(out):
    """After protocol and terminals lock, read prior INPUTS only for exclusion."""
    dest = out / 'independent_inputs'
    dest.mkdir()
    for name in ('source_binding.json',):
        shutil.copy2(p.PREP / name, dest / name)
    for rev in ('before', 'after'):
        shutil.copytree(p.PREP / rev, dest / rev)
    excluded = set(read(p.PREP / 'excluded_words.json'))
    bindings = {}
    # Existing top-level historical-decoder batches. Do not parse their outcomes
    # or candidates. Earlier nested batches are already in the sealed exclusion.
    for f in sorted((ROOT / 'deliverables').glob('research*/independent_cases.json')):
        rows = read(f)
        if isinstance(rows, list) and rows and all(isinstance(r, dict) and 'instruction' in r for r in rows):
            excluded.update(r['instruction'] for r in rows)
            bindings[f.relative_to(ROOT).as_posix()] = sha(f)
    dump(dest / 'excluded_words.json', sorted(excluded))
    dump(dest / 'input_only_exclusion_bindings.json', dict(paths=bindings,
        use='Collision suppression only after all terminal candidates frozen; no outcomes read.',
        terminals_sha256=sha(out / 'terminal_freeze.json')))
    return dest


def run(prep, out, grant_path, preflight_path):
    p.verify(prep); s.verify(p.PREP)
    binding = read(preflight_path / 'execution_binding.json')
    assert binding['runner_sha256'] == sha(Path(__file__))
    assert binding['protocol_seal'] == sha(prep / 'sealed.json')
    assert read(preflight_path / 'checks.json')['passed']
    grant = read(grant_path); grant_check(grant, prep, out)
    out.mkdir(parents=True, exist_ok=False)
    dump(out / 'authorization.json', grant)
    dump(out / 'execution_binding.json', binding)
    dump(out / 'protocol.json', read(prep / 'protocol.json'))
    config = dict(remote_url=s.old.prior.transport.DEFAULT_URL, remote_model=s.MODEL,
        max_model_calls=2, max_tokens=80000, max_wall_seconds=1200, call_timeout=300,
        options=dict(seed=p.SEED, temperature=0.2, num_predict=1024))
    dump(out / 'model_config.json', config)
    initial = read(prep / 'initial.json'); baseline = read(p.PREP / 'baseline_full.json')
    records = s.qualified.r.records(p.PREP / 'baseline_native')
    model = s.old.Model(out / 'service', config); model.fixed = initial
    budget = p.Budget(); active = dict(O=initial, H=initial)
    states = {a: dict(accepted=False, logical_calls=0) for a in active}
    decisions = None; tests = None; complete = False; stage = 'starting'
    first_status = None; first_decisions = None; started = time.monotonic()

    def dispatch(path, current, recs, native, iteration, seen):
        if time.monotonic() - started >= 1200: raise RuntimeError('wall_budget_exhausted')
        with patch.object(s, 'SEED', p.SEED):
            req = s.payload(current, recs, native, iteration == 1, iteration)
        if iteration == 0: assert req == read(prep / 'request.preview.json')
        budget.reserve(path, req, first_decisions, first_status)
        dump(out / 'budget_ledger.json', budget.entries)
        folder = out / path; dump(folder / 'request.preview.json', req)
        model.pending_request = req
        call, candidate = model.call(folder / 'model_call', current, 'op_bit28_illegal', {}, 'research123_scoped_history')
        ev = new_records = None
        reason = 'transport_or_interface_failure'
        if candidate is not None and x.signature(candidate) in seen:
            reason = 'repeated_executable_proposal'; candidate = None
        if candidate is not None:
            ev, new_records = x.evaluate(candidate, folder / 'native', baseline)
            reason = 'native_measured' if healthy(new_records) else 'native_infrastructure_failure'
        d = s.old.decisions(ev) if ev else dict(O=False,H=False,R=False)
        dump(folder / 'measurement.json', dict(decisions=d, reason=reason, transport_status=call['status'],
            healthy=healthy(new_records), proposal_sha256=x.old.acceptance.sha(candidate) if candidate else None))
        print('SCOPED123', path, call['status'], d, reason, flush=True)
        return call, candidate, ev, new_records, d, reason

    try:
        call, candidate, ev, new_records, decisions, reason = dispatch('shared/v0', initial, records,
            p.PREP / 'baseline_native', 0, {x.signature(initial)})
        first_status = call['status']; first_decisions = decisions
        stage = next_action(decisions, call['status'], new_records)
        for arm in active:
            active[arm] = x.journal(out / 'arms' / arm / 'v0', initial, candidate, decisions[arm],
                dict(rule=arm, shadow_R=decisions['R'], reason=reason, paired=True))
            states[arm] = dict(accepted=decisions[arm], logical_calls=1)
        dump(out / 'first_decision.json', dict(decisions=decisions, next_action=stage,
            historical_extra_rejection=stage == 'history_once', R_has_independent_continuation=False))
        if stage == 'history_once':
            call2, c2, ev2, rec2, d2, reason2 = dispatch('history/v1', candidate, new_records,
                out / 'shared/v0/native', 1, {x.signature(initial), x.signature(candidate)})
            ok = d2['H'] and d2['R'] and healthy(rec2)
            active['H'] = x.journal(out / 'arms/H/v1', active['H'], c2, ok,
                dict(rule='H', shadow_R=d2['R'], reason=reason2))
            states['H'] = dict(accepted=ok, logical_calls=2)
            stage = ('stop_transport' if call2['status'] != 'response_received' else
                     'stop_rule_integrity_disagreement' if d2['H'] != d2['R'] else
                     'bounded_recovery_accepted' if ok else 'stop_recovery_failed')
        # No loop or alternative dispatch path: all-accept and O-reject stop.
        for arm, cand in active.items(): dump(out / 'terminal' / arm / 'candidate.json', cand)
        dump(out / 'states.json', states)
        dump(out / 'terminal_freeze.json', dict(time=time.time(), states=states,
            versions={a:x.old.acceptance.sha(c) for a,c in active.items()},
            candidate_files={a:sha(out / 'terminal' / a / 'candidate.json') for a in active},
            protocol_seal=sha(prep / 'sealed.json'), development_binding=sha(prep / 'input_bindings.json'),
            source_sha256=read(p.PREP / 'source_binding.json')['source_sha256'],
            shadow=dict(R='H', no_separate_sample_or_population=True)))
        if stage not in ('stop_transport','stop_rule_integrity_disagreement') and any(v['accepted'] for v in states.values()):
            test_prep = independent_inputs(out)
            s.old.prior.p.independent(test_prep, out, active)
            tests = read(out / 'independent_summary.json')
            assert read(out / 'generation.json')['at'] >= read(out / 'terminal_freeze.json')['time']
            words = {r['instruction'] for r in read(out / 'independent_cases.json')}
            assert len(words) == 96 and not words.intersection(read(test_prep / 'excluded_words.json'))
        ready = bool(first_decisions['O'] and not first_decisions['H'] and states['H']['accepted']
                     and tests and tests['H']['passed'] and stage == 'bounded_recovery_accepted')
        dump(out / 'pilot_decision.json', dict(status=stage, first_shared_decisions=first_decisions,
            states=states, independent={a:t['passed'] for a,t in tests.items()} if tests else None,
            qualified_incremental_recovery_chain=ready, eligible_for_separate_replication_protocol=ready,
            R_unique_effect='not_identifiable_H_R_equivalent', automatic_expansion=False))
        complete = True
    finally:
        cost = x.costs.native_cost(out); dump(out / 'cost.json', cost)
        dump(out / 'outcome.json', dict(completed=complete, status=stage, actual_model_calls=len(model.calls),
            reserved_attempts=len(budget.entries), new_unique_accepted_versions=len({x.old.acceptance.sha(active[a])
                for a in active if states[a]['accepted']}), states=states, independent_executed=tests is not None,
            independent_passes=sum(t['passed'] for t in tests.values()) if tests else 0,
            shadow_R_not_a_third_population=True, automatic_expansion=False))
        p.verify(prep)
        for key in ('native_compile_calls','native_execute_calls','compile_smoke_execute_calls'):
            assert cost['total'][key] <= 16, key


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['preflight','run'])
    ap.add_argument('--prepared', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--authorization', type=Path)
    ap.add_argument('--preflight', type=Path)
    args = ap.parse_args()
    if args.action == 'preflight': preflight(args.prepared.resolve(), args.out.resolve())
    else: run(args.prepared.resolve(), args.out.resolve(), args.authorization.resolve(), args.preflight.resolve())
