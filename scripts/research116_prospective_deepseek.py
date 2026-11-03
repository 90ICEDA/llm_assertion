"""Prospective three-rule pilot using the qualified common generation frontend.

No research113 holdout outcome or accepted predicate enters preparation/requests.
Only held-out INPUT WORDS may be read for collision exclusion, after task locking.
"""
import argparse
import copy
import json
import shutil
import time
from pathlib import Path
import research94_prospective_gate_pilot as old
import research103_temporal_feedback as temporal
import research113_alternative_model_pilot as qualified

ROOT, read, dump, sha = old.ROOT, old.read, old.dump, old.sha
x = old.x
SOURCE = ROOT / 'deliverables/research94_prepare_20261025_r01'
MODEL = qualified.MODEL
ARMS = old.ARMS
SEED = 11607
PURPOSE = 'research116_prospective_three_rule_deepseek'


def protected():
    values = qualified.protected()
    root = ROOT / 'deliverables/research113_real_20261025_r01'
    # Hash only. No outcome or successful candidate is parsed or sent.
    paths = [root / n for n in ('outcome.json', 'pilot_decision.json', 'cost.json', 'freeze.json',
                               'generation.json', 'independent_cases.json', 'independent_summary.json')]
    paths += [root / 'frozen/alternative/candidate.json']
    values.update({f.relative_to(ROOT).as_posix(): sha(f) for f in paths})
    return values


def payload(current, records, folder, history, iteration, diagnostic=None):
    assert iteration in (0, 1)
    cohorts = ('alignment', 'search', 'history') if history else ('alignment', 'search')
    allowed = {c: records[c] for c in cohorts}
    visible = old.feedback(None, allowed, history)
    req = temporal.fmt.request(current, visible, allowed, 'T', iteration, diagnostic)
    body = json.loads(req['messages'][1]['content'])
    body['actual_feedback']['temporal_binding'] = temporal.selected_events(current, allowed, folder, visible)
    req['messages'][1]['content'] = json.dumps(body, separators=(',', ':'))
    req['model'] = MODEL
    req['seed'] = SEED + iteration
    return req


def reserve(entries, path, req):
    if len(entries) >= 4 or req['model'] != MODEL:
        raise ValueError('call_or_model_budget')
    if path not in ('shared/v0', 'arms/O/v1', 'arms/H/v1', 'arms/R/v1') or any(e['path'] == path for e in entries):
        raise ValueError('duplicate_or_unapproved_trajectory')
    amount = sum(len(m['content'].encode()) for m in req['messages']) + 2048 + req['max_tokens']
    if amount > 40000 or sum(e['reservation'] for e in entries) + amount > 160000:
        raise ValueError('token_reservation_budget')
    entries.append(dict(path=path, reservation=amount, reserved_at=time.time(), request_sha256=x.old.acceptance.sha(req)))


def prepare(out):
    x.verify(SOURCE)
    out.mkdir(parents=True, exist_ok=False)
    # Commit the case/baseline choice before looking at any prior holdout inputs.
    dump(out / 'task_lock.json', dict(source=SOURCE.relative_to(ROOT).as_posix(), source_seal=sha(SOURCE / 'sealed.json'),
        initial_sha256=sha(SOURCE / 'initial.json'), parent='original Ibex #166 decoder', seed=SEED,
        selection='Reuse pre-research113 public task and partial BRANCH baseline; no outcome-based task or proposal selection.', time=time.time()))
    for name in ('initial.json', 'baseline_full.json', 'source_binding.json', 'history_cases.json', 'search_cases.json', 'protected93.json'):
        shutil.copy2(SOURCE / name, out / name)
    for rev in ('before', 'after'):
        shutil.copytree(SOURCE / rev, out / rev)
    initial, baseline = read(out / 'initial.json'), read(out / 'baseline_full.json')
    ev, records = x.evaluate(initial, out / 'baseline_native', baseline)
    assert x.paired.aggregate(records['history'], records['search']) == baseline
    eligibility = old.public_eligibility(ev, records)
    assert eligibility['runtime_healthy'] and eligibility['actual_public_op_misses'] > 0 and eligibility['baseline_branch_detections'] == 270
    dump(out / 'task_eligibility.json', eligibility)
    checks = []
    for name, expected in [('positive', dict(O=True, H=True, R=True)), ('known_overbroad', dict(O=True, H=False, R=False))]:
        candidate = read(SOURCE / 'controls' / name / 'candidate.json')
        dump(out / 'controls' / name / 'candidate.json', candidate)
        ce, cr = x.evaluate(candidate, out / 'controls' / name / 'native', baseline)
        assert old.decisions(ce) == expected
        checks.append(dict(name=name, decisions=expected, local_fixture_not_model_output=True))
    req = payload(initial, records, out / 'baseline_native', False, 0)
    dump(out / 'request.preview.json', req)
    for arm in ARMS:
        dump(out / 'arms' / arm / 'request.preview.json', req)
    exclusions = set(read(SOURCE / 'excluded_words.json'))
    # Only duplicate suppression: inputs do not enter candidate selection, policy,
    # feedback, or acceptance. No labels/results/successful predicates are read.
    inputs = ROOT / 'deliverables/research113_real_20261025_r01/independent_cases.json'
    exclusions.update(t['instruction'] for t in read(inputs))
    dump(out / 'excluded_words.json', sorted(exclusions))
    dump(out / 'holdout_input_use.json', dict(path=inputs.relative_to(ROOT).as_posix(), sha256=sha(inputs),
        use='Input words only, collision exclusion after task_lock. Never feedback, task selection or rule tuning.'))
    dump(out / 'protected_records.json', protected())
    protocol = read(SOURCE / 'protocol.json')
    protocol.update(name=PURPOSE, created=time.time(), model=MODEL, seeds=[SEED, SEED + 1], token_cap=160000,
        common_generation='Qualified research103/113 text-expression+sample-bound pair/temporal presentation. All arms identical frontend, fixed BRANCH, model, temperature0.2/max_tokens1024; no extra plan gate. Only allowed evidence differs by rule after shared proposal.',
        first_proposal='One fresh shared response from original partial BRANCH baseline. No research113 successful property or any holdout outcome in requests.',
        information='First all public current9/search36; O continuation sees only those. H/R receive identical current9/search36/history115 facts via same builder, independently called. Full native history measured for all but never fed to O.',
        score='Shared-proposal paired acceptance contrast; then separate independent continuation outcomes. Same seeds do not couple independent service samples. One selected known task, no population recovery rate.',
        privacy='research113 input words used only for collision exclusion after task selection; outcomes and accepted assertions hash-protected but not parsed. No new test generated before all terminal versions.',
        maximum_reserved_tokens_per_call=40000,
        preparation_native_compiles=18, maximum_native_compile_run=30, maximum_native_execute_run=30,
        rule_status='R includes strict absolute acceptance on this fixed identity-preserving corpus. H/R may be equivalent. Do not weaken H or interpret stochastic continuation differences as unique relative-gate benefit.',
        stopping='Maximum4 physical calls:1 shared and at most1 separate continuation for each rejected O/H/R. Accepting arm stops; transport failure stops all. No retry, fallback, quota transfer or extra seed. A non-discriminating/negative pilot is a completed result and stops expansion.',
        future='No automatic multiseed calls. Only a shared O-accepted/H-or-R-extra-rejected proposal followed by same-arm bounded recovery and fresh independent pass qualifies for a separately sealed replication request.')
    dump(out / 'protocol.json', protocol)
    dump(out / 'model_config.json', dict(remote_url=old.prior.transport.DEFAULT_URL, remote_model=MODEL,
        max_model_calls=4, max_tokens=160000, max_wall_seconds=2400, call_timeout=300,
        options=dict(seed=SEED, temperature=0.2, num_predict=1024)))
    dump(out / 'checks.json', dict(native_controls=checks, initial_decisions=old.decisions(ev), model_calls=0))
    dump(out / 'preparation_cost.json', x.costs.native_cost(out))
    paths = [SOURCE / 'sealed.json', SOURCE / 'initial.json']
    dump(out / 'source_bindings.json', {f.relative_to(ROOT).as_posix(): sha(f) for f in paths})
    dump(out / 'code_versions.json', {f.relative_to(ROOT).as_posix(): sha(f) for f in (ROOT / 'scripts').glob('*.py')})
    paths = list(out.glob('*.json')) + list(out.glob('before/*.sv')) + list(out.glob('after/*.sv')) + list(out.glob('arms/*/*.json'))
    paths += list(out.glob('baseline_native/*/result.json')) + [out / 'baseline_native/decision.json']
    paths += list(out.glob('controls/*/candidate.json')) + list(out.glob('controls/*/native/decision.json')) + list(out.glob('controls/*/native/*/result.json'))
    dump(out / 'sealed.json', {f.relative_to(out).as_posix(): sha(f) for f in paths})
    print('PREPARED116', eligibility, 'generation0; native18', flush=True)


def verify(prep):
    x.verify(prep); x.verify(SOURCE)
    assert protected() == read(prep / 'protected_records.json')
    for name, h in read(prep / 'source_bindings.json').items():
        assert sha(ROOT / name) == h


def grant_check(g, prep, out):
    assert g['purpose'] == PURPOSE and type(g['authorized_calls']) is int and g['authorized_calls'] == 4
    assert g['endpoint'] == old.prior.transport.DEFAULT_URL and g['model'] == MODEL
    assert g['prepared_sha256'] == sha(prep / 'sealed.json') and g['run_output'] == out.relative_to(ROOT).as_posix()


def run(prep, out, authorization):
    verify(prep); grant = read(authorization); grant_check(grant, prep, out)
    out.mkdir(parents=True, exist_ok=False)
    dump(out / 'authorization.json', grant); dump(out / 'protocol.json', read(prep / 'protocol.json'))
    initial = read(prep / 'initial.json'); baseline = read(prep / 'baseline_full.json')
    base_records = qualified.r.records(prep / 'baseline_native')
    active = {a: initial for a in ARMS}; states = {a: dict(accepted=False, logical_calls=0, initial_extra_rejection=False) for a in ARMS}
    model = old.Model(out / 'service', read(prep / 'model_config.json')); model.fixed = initial
    budget = []; stopped = False; tests = None; complete = False

    def dispatch(path, current, records, native_folder, history, iteration, seen, diagnostic=None):
        req = payload(current, records, native_folder, history, iteration, diagnostic)
        if iteration == 0:
            assert req == read(prep / 'request.preview.json')
        reserve(budget, path, req); dump(out / 'budget_ledger.json', budget)
        folder = out / path; model.pending_request = req
        call, candidate = model.call(folder / 'model_call', current, 'op_bit28_illegal', {}, 'prospective_three_rule')
        ev = rec = None; reason = dict(kind='transport_or_interface', actual=call)
        if candidate is not None:
            if x.signature(candidate) in seen:
                reason = dict(kind='repeated_executable_proposal'); candidate = None
            else:
                ev, rec = x.evaluate(candidate, folder / 'native', baseline)
                reason = dict(kind='native_measured')
        dump(folder / 'measurement.json', dict(decisions=old.decisions(ev) if ev else {a: False for a in ARMS}, reason=reason))
        return call, candidate, ev, rec, reason

    try:
        call, first_candidate, first, first_records, first_reason = dispatch('shared/v0', initial, base_records,
             prep / 'baseline_native', False, 0, {x.signature(initial)})
        decisions = old.decisions(first) if first else {a: False for a in ARMS}
        for arm in ARMS:
            active[arm] = x.journal(out / 'arms' / arm / 'v0', initial, first_candidate, decisions[arm],
                dict(shared_proposal='shared/v0', rule=arm, accepted=decisions[arm], reason=first_reason))
            states[arm] = dict(accepted=decisions[arm], logical_calls=1,
                initial_extra_rejection=bool(first and decisions['O'] and not decisions[arm]))
        stopped = call['status'] != 'response_received'
        dump(out / 'states.json', states)
        for arm in ARMS:
            if stopped or states[arm]['accepted']:
                continue
            current = first_candidate or initial
            records = first_records or base_records
            folder = out / 'shared/v0/native' if first_records else prep / 'baseline_native'
            # Failed/absent interfaces do not leak measured hidden histories to O.
            diagnostic = None
            if first is None:
                assembled = out / 'shared/v0/model_call/response.assembled.json'
                diagnostic = dict(reason=first_reason, actual_model_text=read(assembled)['message']['content'] if assembled.exists() else None)
            call, candidate, ev, rec, reason = dispatch(f'arms/{arm}/v1', current, records, folder, arm != 'O', 1,
                {x.signature(initial), x.signature(current)}, diagnostic)
            accepted = old.decisions(ev)[arm] if ev else False
            active[arm] = x.journal(out / 'arms' / arm / 'v1/transition', active[arm], candidate, accepted,
                dict(rule=arm, accepted=accepted, reason=reason))
            states[arm].update(accepted=accepted, logical_calls=2)
            stopped = call['status'] != 'response_received'
            dump(out / 'states.json', states)
            print('PROSPECTIVE116', arm, accepted, flush=True)
        for arm in ARMS:
            dump(out / 'terminal' / arm / 'candidate.json', active[arm])
        dump(out / 'terminal_versions.json', {a: x.old.acceptance.sha(c) for a, c in active.items()})
        if not stopped and any(st['accepted'] for st in states.values()):
            old.prior.p.independent(prep, out, active)
            tests = read(out / 'independent_summary.json')
        ready = bool(not stopped and tests and any(states[a]['initial_extra_rejection'] and states[a]['accepted'] and tests[a]['passed'] for a in ('H', 'R')))
        dump(out / 'pilot_decision.json', dict(eligible_to_request_multiseed=ready, automatic_expansion=False,
            first_shared_decisions=decisions, states=states,
            independent={a: t['passed'] for a, t in tests.items()} if tests else None,
            status='qualified_for_separately_authorized_replication' if ready else 'stop_no_qualified_chain'))
        complete = True
    finally:
        dump(out / 'cost.json', x.costs.native_cost(out))
        dump(out / 'outcome.json', dict(actual_model_calls=len(model.calls), reserved_attempts=len(budget),
            accepted_arms=sum(st['accepted'] for st in states.values()),
            unique_accepted_versions=len({x.old.acceptance.sha(active[a]) for a in ARMS if states[a]['accepted']}),
            transport_stopped=stopped, independent_executed=tests is not None, completed=complete, automatic_expansion=False))
        verify(prep)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['prepare', 'run'])
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--prepared', type=Path)
    ap.add_argument('--authorization', type=Path)
    a = ap.parse_args()
    if a.action == 'prepare': prepare(a.out.resolve())
    else: run(a.prepared.resolve(), a.out.resolve(), a.authorization.resolve())
