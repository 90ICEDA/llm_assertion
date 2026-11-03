"""Native qualification and bounded real-model valid-retention refinement.

audit sends no requests. run requires a new explicit remote-call authorization.
Existing reports and test batches are never overwritten.
"""
import argparse
import copy
import hashlib
from pathlib import Path
import secrets
import shutil
import sys
import research17_loop as loop
import research28_valid_runtime as extension
from research28_cases import cases
from research28_model import RemoteModel
from research21_loop import refine
from research26_cases import promoted_cases

ROOT = loop.ROOT
SOURCE = ROOT/'deliverables/research27_closed_loop_20261020_r06'
dump, read = loop.dump, loop.read


def qualify(result, selected, folder):
    details = []
    for i, case in enumerate(selected):
        fixed = read(folder/f'case_{i}/correct/replay.json')
        faulty = read(folder/f'case_{i}'/case['mode']/'replay.json')
        ledger = read(folder/f'case_{i}/ledger.json')
        f = {r['cycle']: r for r in fixed['reference_trace']}
        b = {r['cycle']: r for r in faulty['reference_trace']}
        from research15_evidence import marker_map, INPUTS
        failure_cycles = set().union(*marker_map(faulty['native'], 'failures').values()) if faulty['native']['failures'] else set()
        for row in ledger['ledger']:
            if row['obligation'] != 'stall_stability' or row['oracle']['verdict'] != 'violated':
                continue
            cycle = row['cycle']
            prev, now = b.get(cycle-1), b[cycle]
            pending = [t for t in fixed['oracle']['transactions']
                       if t['accept_cycle'] < cycle and
                       (t['response_cycle'] is None or t['response_cycle'] >= cycle) and
                       (t['cancel_cycle'] is None or t['cancel_cycle'] > cycle)]
            control = [c for c in fixed['oracle']['checks'] if c['cycle'] == cycle and c['obligation'] == 'stall_stability']
            checks = dict(legal=fixed['oracle']['legality'] == faulty['oracle']['legality'] == 'legal',
                same_accepted_input_schedule=[{k:t[k] for k in INPUTS} for t in fixed['trace']] == [{k:t[k] for k in INPUTS} for t in faulty['trace']],
                real_pending_transaction=bool(pending),
                fixed_satisfies=bool(control) and all(c['passed'] for c in control),
                valid_withdrawal=bool(prev and prev['mvalid'] and not prev['mready'] and not now['mvalid']),
                data_unchanged=bool(prev and prev['mdata'] == now['mdata']),
                old_sva_no_failure=not any(c <= cycle for c in failure_cycles),
                attributable=row['native']['attribution_status'] == 'confirmed',
                sampling=fixed['sampling_qualification']['status'] == faulty['sampling_qualification']['status'] == 'passed')
            details.append(dict(case=case['id'], evidence_id=row['evidence_id'],
                dedup_class=case['dedup_class'], boundary='release' if now['mready'] else 'continued_stall',
                valid=all(checks.values()), checks=checks,
                transaction=min(pending, key=lambda t:t['accept_cycle']) if pending else None,
                buggy_samples=[prev, now], fixed_samples=[f.get(cycle-1), f.get(cycle)],
                native=row['native'], oracle_violation=row['oracle_violation']))
    return dict(passed=result['healthy'] and bool(details) and all(t['valid'] for t in details),
        targets=details, valid_witnesses=sum(t['valid'] for t in details),
        distinct_mechanisms=sorted({t['dedup_class'] for t in details if t['valid']}),
        counts=result['counts'], formal_queries=0, model_calls=0,
        limits='First attributed violations only. Later downstream errors remain unknown; deliberate injected faults, not historical fixes.')


def config(max_calls):
    return dict(loop.CONFIG, expression_format='text', direct_property=True, preflight_tokens=False,
        max_model_calls=max_calls, max_tokens=240000, max_wall_seconds=7200, call_timeout=180,
        model='qwen/qwen-2.5-72b-instruct', remote_model='qwen/qwen-2.5-72b-instruct',
        remote_url='https://api.highwayapi.ai/openai/chat/completions',
        key_file=str(ROOT/'.secrets/qwen_api_key.txt'), backend='configured-qwen-relay',
        options=dict(loop.CONFIG['options'], seed=2026102028, temperature=0, num_predict=1024))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('audit', 'run'))
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--max-model-calls', type=int, default=2)
    parser.add_argument('--authorization-record', type=Path)
    args = parser.parse_args()
    assert 1 <= args.max_model_calls <= 4
    if args.action == 'run':
        assert args.authorization_record, 'explicit_new_authorization_record_required'
        auth = read(args.authorization_record)
        assert auth['authorized_calls'] >= args.max_model_calls and auth['endpoint'] == config(2)['remote_url']
    out = args.out.resolve()
    assert ROOT in out.parents
    if args.action == 'run':
        assert auth['run_output'] == out.relative_to(ROOT).as_posix(), 'authorization_bound_to_one_new_run'
    loop.CONFIG.update(config(args.max_model_calls))
    loop.prepare(out)
    for name in ('research28_campaign.py', 'research28_cases.py', 'research28_valid_runtime.py',
                 'research28_model.py', 'research21_loop.py', 'research26_model.py',
                 'research26_cases.py', 'research20_stall_runtime.py', 'research22_model.py',
                 'research21_model.py', 'research20_model.py', 'research20_remote.py',
                 'research21_cases.py', 'research20_cases.py', 'research23_model.py',
                 'research24_model.py'):
        shutil.copy2(ROOT/'scripts'/name, out/'source_snapshot'/name)
    dump(out/'source_snapshot/hashes.json', {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                                            for p in (out/'source_snapshot').glob('*') if p.is_file() and p.name != 'hashes.json'})
    initial = read(SOURCE/'core/frozen_candidate.json')
    assert loop.sha(initial) == read(SOURCE/'core/freeze.json')['candidate_sha256']
    dump(out/'shared_initial.json', initial)
    dump(out/'shared_initial_freeze.json', dict(origin=str(SOURCE/'core'), hash=loop.sha(initial)))
    dump(out/'execution.command.json', dict(argv=[sys.executable, *sys.argv], cwd=str(Path.cwd())))
    dump(out/'protocol.json', dict(task='valid retention during stall and at release', action=args.action,
        config=loop.CONFIG, initial_hash=loop.sha(initial),
        fault_scope='Unchanged actual axis_fifo plus two explicit artificial valid-suppression faults.',
        history='Entire 105-case research27 development plan reused; its public 18-case r06 test promoted unchanged.',
        independent='Only after final candidate freezes. Never used in prompts, feedback or selection.',
        dedup='Two boundary mechanisms under stall_stability; seed/depth/reset variants are replications.',
        root_git_commit=None, model_properties='Only genuine model text; other assertions retained by existing assembler.'))
    llm = None
    outcome = dict(status='running')
    dump(out/'outcome.json', outcome)
    try:
        with extension.installed():
            selected = cases(2026102028)
            dump(out/'new_development_cases.json', selected)
            if args.action == 'audit':
                result = loop.replay(initial, out/'core/before', selected)
                qualification = qualify(result, selected, out/'core/before')
                dump(out/'qualification.json', qualification)
                assert qualification['passed'], 'valid_withdrawal_evidence_not_qualified'
                model = RemoteModel(out, loop.CONFIG)  # constructor sends no request and reads no key
                request = model._payload(initial, 'stall_stability',
                    dict(requested_obligations=['stall_stability'], counts=result['counts'],
                         actual_native_evidence=result['feedback']), 'valid_retention_repair')
                dump(out/'request.preview.json', request)
                dump(out/'review.json', dict(endpoint=model.url, model=model.remote_model,
                    proposed_max_calls=args.max_model_calls, model_calls=0, credentials_read=False,
                    external_transmission=False, request_sha256=hashlib.sha256((out/'request.preview.json').read_bytes()).hexdigest()))
                outcome = dict(status='development_witnesses_qualified_remote_not_called',
                               valid_witnesses=qualification['valid_witnesses'])
            else:
                shutil.copy2(args.authorization_record, out/'authorization.json')
                history = read(SOURCE/'development_plan.json') + promoted_cases(SOURCE)
                selected = history + selected
                assert len({c['id'] for c in selected}) == len(selected)
                dump(out/'development_plan.json', selected)
                llm = RemoteModel(out, loop.CONFIG)
                final, core = refine(out, llm, initial, selected, args.max_model_calls,
                                     stages_to_run=(('stall_stability',),))
                # No independent schedule or seed is materialized before freeze.
                seed = secrets.randbelow(2**31)
                from research21_cases import independent_cases
                fresh = cases(seed, independent=True) + independent_cases(seed)
                folder = out/'core_independent'
                dump(folder/'split.json', dict(created_after_freeze=True, seed=seed,
                    candidate_hash=loop.sha(final), usage='no_feedback_no_selection', cases=fresh))
                summary = {}
                for name, candidate in (('core', final), ('initial', initial)):
                    result = loop.replay(candidate, folder/name, fresh)
                    summary[name] = dict(healthy=result['healthy'], counts=result.get('counts'))
                dump(folder/'summary.json', summary)
                outcome = dict(status='development_resolved' if core['resolved'] else 'development_partial',
                    core=core, independent_executed=True, independent=summary)
    except BaseException as exc:
        outcome = dict(status='execution_blocked', error=repr(exc))
        raise
    finally:
        dump(out/'outcome.json', outcome)
        calls = llm.calls if llm else []
        dump(out/'model_cost.json', dict(calls=len(calls),
            prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),
            completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),
            usage_unavailable=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls),
            formal_calls=0))
        print(outcome['status'], flush=True)


if __name__ == '__main__':
    main()
