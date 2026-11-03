"""One alternative model, unchanged research104 requests and native acceptance.

Preparation is offline. Run requires a purpose/model/seal/output-bound grant.
The archived Qwen trial is a historical comparator, not a randomized new arm.
"""
import argparse
import copy
import time
import shutil
from pathlib import Path
import research104_temporal_recovery as r
import research108_generation_representation as rep

p, x = r.p, r.x
ROOT, read, dump, sha = r.ROOT, r.read, r.dump, r.sha
SOURCE = ROOT / 'deliverables/research104_prepare_20261025_r01'
INVENTORY = ROOT / 'deliverables/research112_inventory_20261025_r01/inventory.json'
MODEL = 'deepseek/deepseek-v3-0324'
PURPOSE = 'research113_single_alternative_model_pilot'


def protected():
    result = rep.protected_failures()
    root = ROOT / 'deliverables/research108_real_20261025_r01'
    paths = [root / n for n in ('authorization.json', 'outcome.json', 'cost.json', 'budget_ledger.json', 'pilot_decision.json')]
    for folder in root.glob('*/v*/model_call'):
        paths.extend(f for f in folder.iterdir() if f.is_file())
    result.update({f.relative_to(ROOT).as_posix(): sha(f) for f in paths})
    return result


def request(current, records, native_folder, iteration, diagnostic=None):
    assert iteration in (0, 1)
    req = r.temporal.request(current, records, native_folder, iteration, diagnostic)
    req['model'] = MODEL  # The only changed request field. No provider fallback.
    return req


class Budget:
    """Charge an attempted dispatch before sending; invalid/error responses count."""
    def __init__(self):
        self.entries = []

    def reserve(self, req):
        if len(self.entries) >= 2:
            raise ValueError('two_call_ceiling')
        if req['model'] != MODEL:
            raise ValueError('model_change_forbidden')
        amount = sum(len(m['content'].encode()) for m in req['messages']) + 2048 + req['max_tokens']
        if amount > 40000 or sum(e['reservation'] for e in self.entries) + amount > 80000:
            raise ValueError('conservative_reservation_ceiling')
        self.entries.append(dict(iteration=len(self.entries), reservation=amount, reserved_at=time.time(),
                                 request_sha256=x.old.acceptance.sha(req)))


def must_stop(accepted, status, attempts):
    return bool(accepted or status != 'response_received' or attempts >= 2)


def prepare(out):
    r.verify(SOURCE)
    inventory = read(INVENTORY)
    remote = next(q for q in inventory['queries'] if q['kind'] == 'remote')
    assert remote['status'] == 'completed' and any(e.get('id') == MODEL for e in remote['models'])
    out.mkdir(parents=True, exist_ok=False)
    for name in ('initial.json', 'proposal.json', 'baseline_full.json', 'source_binding.json', 'history_cases.json',
                 'search_cases.json', 'excluded_words.json', 'protected93.json'):
        shutil.copy2(SOURCE / name, out / name)
    for revision in ('before', 'after'):
        shutil.copytree(SOURCE / revision, out / revision)
    shutil.copy2(INVENTORY, out / 'inventory.json')
    original = read(SOURCE / 'request.preview.json')
    req = request(read(out / 'proposal.json'), r.records(r.VERSION / 'native'), r.VERSION / 'native', 0)
    expected = copy.deepcopy(original); expected['model'] = MODEL
    assert req == expected
    dump(out / 'request.preview.json', req)
    dump(out / 'comparison.json', dict(historical_request_sha256=sha(SOURCE / 'request.preview.json'),
         changed_fields=['model'], common_messages_sha256=x.old.acceptance.sha(req['messages']),
         historical_run='deliverables/research104_real_20261025_r01',
         interpretation='Historical reference only, no contemporaneous randomized Qwen arm. Provider/time effects and effective sampling comparability remain unknown. No mechanism effect estimate.'))
    protocol = read(SOURCE / 'protocol.json')
    protocol.update(name=PURPOSE, model=MODEL, created=time.time(),
        selection='One catalog-listed different-family, date-tagged model selected before any generation. Catalog lacks capability, pricing and weight attestations; no claim of superiority or confirmed generation compatibility.',
        change='ONLY model field vs research104 full-set textual representation. Same messages, failed candidate, native-bound development diagnostics, seed10407/10408 and all sampling parameters. No new plan gate or atomic-edit representation.',
        stopping='At most2 calls INCLUDING HTTP errors, truncation and invalid/repeated responses. No retry/model fallback/parameter fallback/extra seed. Accept or transport failure stops immediately. Budget exhaustion stops route.',
        adoption_gate='Full native acceptance then fresh independent pass required. Otherwise stop this model route. A pass only qualifies this selected-case public generation capability; no mechanism benefit or automatic expansion.',
        cost='Two new calls require explicit authorization; old Qwen routes remain stopped. Same40000 reservation per call and80000 total as historical trial, not actual tokens. Price and billable monetary usage unavailable unless supplied by service.',
        native_max_compile_execute_each=14,
        comparison='Historical Qwen reference, not concurrent randomized comparison. Same seeds do not guarantee equal sampling across models.')
    dump(out / 'protocol.json', protocol)
    config = read(SOURCE / 'model_config.json'); config['remote_model'] = MODEL
    dump(out / 'model_config.json', config)
    dump(out / 'route_stops.json', dict(stopped=['research104_Qwen_temporal_recovery', 'research108_C_Qwen_full_set', 'research108_E_Qwen_atomic_edit'],
         no_further_calls=True, old_results_not_reclassified=True, automatic_expansion=False))
    dump(out / 'protected_failures.json', protected())
    files = [SOURCE / 'sealed.json', INVENTORY]
    dump(out / 'reused_bindings.json', {f.relative_to(ROOT).as_posix(): sha(f) for f in files})
    dump(out / 'code_versions.json', {f.relative_to(ROOT).as_posix(): sha(f) for f in (ROOT / 'scripts').glob('*.py')})
    paths = list(out.glob('*.json')) + list(out.glob('before/*.sv')) + list(out.glob('after/*.sv'))
    dump(out / 'sealed.json', {f.relative_to(out).as_posix(): sha(f) for f in paths})
    print('PREPARED113', MODEL, 'max2; generation0', flush=True)


def verify(prep):
    x.verify(prep); r.verify(SOURCE)
    for name, digest in read(prep / 'reused_bindings.json').items():
        assert sha(ROOT / name) == digest, name
    assert protected() == read(prep / 'protected_failures.json')
    assert read(prep / 'protocol.json')['model'] == MODEL
    assert read(prep / 'model_config.json')['remote_model'] == MODEL


def grant_check(g, prep, out):
    assert g['purpose'] == PURPOSE and type(g['authorized_calls']) is int and g['authorized_calls'] == 2
    assert g['endpoint'] == p.prior.transport.DEFAULT_URL and g['model'] == MODEL
    assert g['prepared_sha256'] == sha(prep / 'sealed.json')
    assert g['run_output'] == out.relative_to(ROOT).as_posix()


def run(prep, out, authorization):
    verify(prep); grant = read(authorization); grant_check(grant, prep, out)
    out.mkdir(parents=True, exist_ok=False)
    dump(out / 'authorization.json', grant); dump(out / 'protocol.json', read(prep / 'protocol.json'))
    active = initial = read(prep / 'initial.json'); current = read(prep / 'proposal.json')
    base = read(prep / 'baseline_full.json'); records = r.records(r.VERSION / 'native')
    native_folder = r.VERSION / 'native'; diagnostic = None
    model = p.Model(out / 'service', read(prep / 'model_config.json')); model.fixed = initial
    seen = {x.signature(initial), x.signature(current)}
    budget = Budget(); accepted = stopped = False; tests = None; completed = False
    try:
        for iteration in range(2):
            req = request(current, records, native_folder, iteration, diagnostic)
            if iteration == 0:
                assert req == read(prep / 'request.preview.json')
            budget.reserve(req); dump(out / 'budget_ledger.json', budget.entries)
            model.pending_request = req; folder = out / f'v{iteration}'
            call, candidate = model.call(folder / 'model_call', current, 'op_bit28_illegal', {}, 'alternative_model_recovery')
            reason = dict(kind='transport_or_interface', actual=call); ev = None
            if candidate is not None:
                if x.signature(candidate) in seen:
                    reason = dict(kind='repeated_executable_proposal'); candidate = None
                else:
                    seen.add(x.signature(candidate))
                    ev, newrecords = x.evaluate(candidate, folder / 'native', base)
                    accepted = bool(ev['history']['accepted'])
                    reason = dict(kind='native_measured', decision=ev)
                    current, records, native_folder = candidate, newrecords, folder / 'native'
            if ev is None:
                assembled = folder / 'model_call/response.assembled.json'
                diagnostic = dict(reason=reason, actual_model_text=read(assembled)['message']['content'] if assembled.exists() else None)
            else:
                diagnostic = None
            active = x.journal(folder / 'transition', active, candidate, accepted, reason)
            stopped = call['status'] != 'response_received'
            print('ALTERNATIVE113', iteration, reason['kind'], accepted, flush=True)
            if must_stop(accepted, call['status'], len(budget.entries)):
                break
        dump(out / 'terminal/candidate.json', active)
        if accepted and not stopped:
            # Existing holdout implementation freezes first and draws fresh words after.
            p.prior.p.independent(prep, out, dict(alternative=active))
            tests = read(out / 'independent_summary.json')
        completed = True
    finally:
        passed = bool(completed and accepted and tests and tests['alternative']['passed'])
        dump(out / 'cost.json', x.costs.native_cost(out))
        dump(out / 'outcome.json', dict(actual_calls=len(model.calls), reserved_attempts=len(budget.entries),
             new_accepted_versions=int(accepted), transport_stopped=stopped, completed=completed,
             active_sha256=x.old.acceptance.sha(active), independent=tests, automatic_expansion=False))
        dump(out / 'pilot_decision.json', dict(alternative_passed=passed,
             status='qualified_selected_case_only' if passed else 'stop_alternative_route',
             automatic_expansion=False, mechanism_benefit_claim=False))
        verify(prep)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['prepare', 'run'])
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--prepared', type=Path)
    ap.add_argument('--authorization', type=Path)
    a = ap.parse_args()
    if a.action == 'prepare':
        prepare(a.out.resolve())
    else:
        run(a.prepared.resolve(), a.out.resolve(), a.authorization.resolve())
