"""Model-free search comparison preparation, reusing fixed selectors and FIFO RTL."""
import argparse
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
import research84_generalization as previous

b = previous.b
ROOT, read, dump = b.ROOT, b.read, b.dump
SEEDS = (11707, 11719, 11731)
METHODS = ('ordinary', 'candidate_disagreement', 'raw_difference', 'coverage_sweep', 'ordinary_no_repeat', 'contract_novelty')


@contextmanager
def installed():
    with patch.object(previous, 'SEEDS', SEEDS), patch.object(previous, 'METHODS', METHODS):
        yield


def prepare(out):
    with installed():
        previous.prepare(out)
    protocol = read(out / 'protocol.json')
    protocol.update(name='research117_fixed_search_comparison', methods=METHODS, seeds=SEEDS,
        expected_maximum_search_queries=108,
        selection='Unchanged research84 source-ordered archive inventory and public eligibility. First2 eligible candidates absent from research82. No research113 response, independent result or candidate is read. Not a new parent case or new fault population.',
        fixed_extra_control='coverage_sweep is the existing fixed-coverage policy, added alongside ordinary_no_repeat to separate contract information from generic schedule/avoidance.',
        prior_results='research82/84/110 remain valid negative/mixed results. New seeds are development search replication, not new assertion independent tests.',
        cost_comparison='Fixed maximum3 queries per task/seed/method. Actual per-gap first-discovery native executions and nested reference/selection/query timing reported separately; no double counting reference inside query wall time. Budget censoring not replaced by invented discovery cost.',
        timing_limit='Execution order remains fixed, so wall seconds are descriptive, not a rigorous speed advantage claim.',
        success='Fair accounting may finish with zero extra gaps and no cost advantage. No outcome-dependent budget extension, candidate reselection or selector tuning.',
        model_calls=0, formal_calls=0)
    dump(out / 'protocol.json', protocol)
    keys = set(); sources = []
    for name in ('research82_search_20261025_r01', 'research84_generalization_20261025_r01'):
        path = ROOT / 'deliverables' / name / 'records.json'
        rows = read(path); found = {k for row in rows for k in row['gap_keys']}
        keys.update(found); sources.append(dict(path=path.relative_to(ROOT).as_posix(), sha256=b.digest(path)))
    dump(out / 'historical_registry.json', dict(keys=sorted(keys), sources=sources,
        use='Reporting historical novelty only. Never visible to selectors; public feedback separately subtracted from per-run discovery credit.'))
    checks = list(previous.policy.tests())
    assert len(read(out / 'inventory.json')) > 2
    assert not any('research113' in row['path'] for row in read(out / 'inventory.json'))
    for seed in SEEDS:
        for method in METHODS:
            policy = previous.policy.factory(method, seed)
            decision = previous.policy.decision(policy, method, seed, 0, [])
            assert decision['family'] in previous.policy.TARGETS
            checks.append(f'{seed}/{method}/existing_selector_available')
    dump(out / 'preflight.json', dict(passed=True, checks=checks, count=len(checks), model_calls=0,
        new_native_calls=0, search_queries=0, raw_discovery_results_created=False))
    # research84 created a temporary seal; this is the final seal before any run.
    dump(out / 'sealed.json', {f.relative_to(out).as_posix(): b.digest(f) for f in out.rglob('*')
        if f.is_file() and f.name not in ('sealed.json', 'outcome.json')})
    b.verify(out)
    print('PREPARED117', len(checks), 'checks;108 query ceiling;new queries0;model0', flush=True)


def report(out):
    b.verify(out)
    with installed(): previous.report(out)
    records = read(out / 'records.json'); calls = read(out / 'reference_costs.json')
    known = set(read(out / 'historical_registry.json')['keys']); gaps = []
    for row in records:
        for key in row['first_new_keys']:
            earlier = [r for r in records if all(r[k] == row[k] for k in ('pair', 'seed', 'method')) and r['query'] <= row['query']]
            refs = [r for r in calls if r.get('stage') == 'search' and all(r.get(k) == row[k] for k in ('pair', 'seed', 'method')) and r['query'] <= row['query']]
            gaps.append(dict(pair=row['pair'], seed=row['seed'], method=row['method'], key=key,
                first_query=row['query'] + 1, historical_candidate_gap_known=key in known,
                native_executions=sum(r['native_executions'] for r in earlier),
                query_wall_seconds=sum(r['query_wall_seconds'] for r in earlier),
                selector_seconds=sum(r['selector_seconds'] for r in earlier),
                reference_by_kind={k: dict(calls=sum(r['kind'] == k for r in refs), seconds=sum(r['wall_seconds'] for r in refs if r['kind'] == k)) for k in {r['kind'] for r in refs}}))
    dump(out / 'first_discovery_actual_cost.json', gaps)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=['prepare', 'run', 'report', 'audit'])
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--audit-out', type=Path)
    a = ap.parse_args(); out = a.out.resolve()
    if a.action == 'prepare': prepare(out)
    elif a.action == 'report': report(out)
    elif a.action == 'run':
        with installed(): previous.run(out)
        report(out)
    else:
        with installed(): previous.audit(out, a.audit_out.resolve())
        report(out)
