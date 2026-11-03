"""Recompute actual requests, gates, state retention and fresh-test results."""
import argparse
from pathlib import Path

import research81_recovery_comparison as c
from research28_report import raw_response

g, b, read, dump = c.g, c.b, c.read, c.dump


def audit(prep, root, out):
    c.verify(prep)
    out.mkdir(parents=True, exist_ok=False)
    checks, traces, raw = [], [], 0
    def check(name, okay):
        assert okay, name
        checks.append(name)
    auth, budget, outcome = read(root / 'authorization.json'), read(root / 'budget.json'), read(root / 'outcome.json')
    check('bound authorization', auth['authorized_calls'] == 4 and auth['seed'] == c.SEED
          and auth['prepared_sha256'] == b.search.digest(prep / 'sealed.json'))
    initial = read(prep / 'initial.json')
    rows, frozen, accepted = read(prep / 'windows.private.json'), {}, {}
    reservations = [x for x in budget['events'] if x['kind'] == 'model_reserved']
    check('total budget', len(reservations) <= 4)
    check('unique slots', len({(x['arm'], x['stage']) for x in reservations}) == len(reservations))
    stops = [x['at'] for x in budget['events'] if x['kind'] == 'global_stop']
    check('no calls after stop', not stops or all(x['at'] < min(stops) for x in reservations))
    for arm in c.ARMS:
        loc = root / 'arms' / arm
        current, plan_pass, plan = initial, False, None
        was_accepted, expected, previous = False, read(prep / arm / 'request.preview.json'), None
        seen = {b.interface.executable_hash(initial)}
        calls = []
        if (loc / 'plan/v0/model_call/attempt.json').exists():
            calls.append(('plan', loc / 'plan/v0'))
        for i, stage in enumerate(('generate', 'refine')):
            if (loc / f'core/v{i}/model_call/attempt.json').exists():
                calls.append((stage, loc / f'core/v{i}'))
        check(arm + ': per-arm cap', len(calls) <= 2)
        for stage, folder in calls:
            call_dir = folder / 'model_call'
            req, call = read(call_dir / 'request.json'), read(call_dir / 'result.json')
            if stage == 'generate' and arm == 'P':
                check('P actual complete plan before SVA', plan_pass)
                expected = g.unlock(read(prep / 'sva_template.json'), plan, g.validate(plan, rows), rows)
            elif stage == 'refine':
                check('refine only D rejected own proposal', arm == 'D' and previous is not None and not previous[3]['accepted'])
                version, old_call, edit, decision, wr, small, full = previous
                expected = c.refinement_request(read(prep / 'sva_template.json'), initial, version,
                    old_call, edit, decision, wr, small, full, persist=False)
            check(arm + stage + ': exact request', req == expected)
            check(arm + stage + ': reserved hash', any(x['arm'] == arm and x['stage'] == stage and x['request_sha256'] == b.loop.sha(req) for x in reservations))
            check(arm + stage + ': sampler', req['seed'] == c.SEED and req['max_tokens'] == 2048 and req['temperature'] == 0.2)
            if call['status'] != 'response_received':
                check('transport terminal', budget['stopped'])
                continue
            if stage == 'plan':
                plan = read(call_dir / 'hold_plan.json')
                check('original actual plan', raw_response(call_dir, plan))
                verdict = g.validate(plan, rows)
                check('whole plan recomputed unchanged', verdict == read(folder / 'decision.json'))
                plan_pass = verdict['accepted']
                traces.append(dict(arm=arm, stage=stage, accepted=plan_pass, reasons=verdict['reasons']))
                continue
            edit = read(call_dir / 'model_edit.json') if (call_dir / 'model_edit.json').exists() else None
            candidate = read(call_dir / 'candidate.json') if (call_dir / 'candidate.json').exists() else None
            if edit:
                check(arm + stage + ': actual edit', raw_response(call_dir, edit))
            if candidate:
                check(arm + stage + ': unmodified rendered property', b.interface.assemble(edit, initial) == candidate)
            repeated = bool(candidate and b.interface.executable_hash(candidate) in seen)
            if candidate:
                seen.add(b.interface.executable_hash(candidate))
            check('repeat decision', repeated == read(folder / 'repeat_check.json')['repeated'])
            results = {}
            for phase, filename in [('windows', 'window_cases.json'), ('public', 'cases.json'), ('history', 'history_cases.json')]:
                path = folder / phase
                results[phase] = read(path / 'result.json') if (path / 'result.json').exists() else None
                if results[phase]:
                    check('no native repeated executable', not repeated)
                    raw += g.old.raw_replay(path, read(prep / filename), candidate, checks)
            wr, small, full = (results[x] for x in ('windows', 'public', 'history'))
            wg = (dict(accepted=False, reasons=[dict(kind='repeated_executable')]) if repeated else
                  g.old.sem.native_windows(wr, rows, read(prep / 'window_cases.json'), folder / 'windows'))
            check('identical native window gate', wg == read(folder / 'window_gate.json'))
            check('public conditional', small is None or wg['accepted'])
            before = read(g.old.sem.SOURCE / 'baseline_public/result.json')
            plain = b.paired.current_decision(before, small, edit) if small else dict(accepted=False, reasons=wg['reasons'])
            check('ordinary gate', plain == read(folder / 'ordinary_decision.json'))
            check('history conditional', full is None or plain['accepted'])
            decision = g.old.policy.decision_for(plain, full, read(g.old.sem.SOURCE / 'baseline_history/result.json'), True)
            check('same complete acceptance', decision == read(folder / 'decision.json'))
            was_accepted = decision['accepted']
            current = candidate if was_accepted else current
            check('retained active candidate', read(folder / 'active_candidate.json') == current)
            traces.append(dict(arm=arm, stage=stage, accepted=was_accepted, decision=decision,
                counts={k: v['counts'] if v else None for k, v in results.items()}))
            previous = (folder, call, edit, decision, wr, small, full)
        frozen[arm] = read(loc / 'core/frozen_candidate.json')
        accepted[arm] = was_accepted
        check('exact frozen active candidate', frozen[arm] == current)
        check('arm acceptance truth', read(loc / 'outcome.json')['accepted'] == was_accepted)
    check('accepted count', sum(accepted.values()) == outcome['new_accepted_versions'])
    if (root / 'independent_mapping.json').exists():
        from research35_campaign import join_results, metrics
        from research29_drain import assess
        mapping, split = read(root / 'independent_mapping.json'), read(root / 'common_independent_split.json')
        starts = [e['at'] for e in budget['events'] if e['kind'] == 'independent_started']
        freezes = [e['at'] for e in budget['events'] if e['kind'] == 'freeze']
        check('one batch after both freezes', len(starts) == 1 and len(freezes) == 2 and min(starts) > max(freezes))
        check('no generation after independent', all(e['at'] < starts[0] for e in reservations))
        check('fresh inputs excluded', not set(read(prep / 'excluded_inputs.json')['input_hashes']) &
              {b.loop.sha(x['rows']) for x in split['boundary_cases'] + split['drain_cases']})
        seen = set()
        for arm, m in mapping.items():
            check('frozen test hash', b.loop.sha(frozen[arm]) == m['candidate_hash'])
            path = root / m['path'] / 'independent'
            local_split = read(path / 'split.json')
            check('same common fresh tests', all(local_split[k] == split[k] for k in ('seed', 'boundary_cases', 'drain_cases')))
            if m['candidate_hash'] not in seen:
                for phase, name in [('boundary', 'boundary_cases'), ('drain', 'drain_cases')]:
                    raw += g.old.raw_replay(path / phase, local_split[name], frozen[arm], checks)
                seen.add(m['candidate_hash'])
            boundary, drain = read(path / 'boundary/result.json'), read(path / 'drain/result.json')
            combined = join_results([boundary, drain])
            passed = (combined['healthy'] and assess(path / 'drain', local_split['drain_cases'], drain)['passed']
                      and all(x['detections'] > 0 and x['triggers'] > 0 and not any(x[k] for k in ('misses', 'false_positives', 'unknown'))
                              for x in metrics(combined)['obligations'].values()))
            check('five exposures and independent result', m['passed'] == passed and m['qualified'] == (passed and accepted[arm]))
        check('independent milestones', sum(m['qualified'] for m in mapping.values()) == outcome['new_independent_passes'])
    else:
        check('no independent invented', outcome['new_independent_passes'] == 0)
    cost = g.old.cost_audit(root, b.paired.files(root))
    check('actual call accounting', cost['total']['model_calls'] == outcome['actual_model_calls'] <= len(reservations))
    check('completed history accounting', outcome['completed_history_replays'] == len(list((root / 'arms').glob('*/core/v*/history/result.json'))))
    check('old independent results untouched', g.old.old.screen.protected() == read(prep / 'protected.json'))
    dump(out / 'cost.json', cost)
    dump(out / 'trace.json', traces)
    dump(out / 'audit.json', dict(passed=True, checks=checks, raw_native_records=raw, outcome=outcome))
    print('RESULT_AUDIT', len(checks), raw, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    with b.extension.installed():
        audit(a.prepared.resolve(), a.run.resolve(), a.out.resolve())
