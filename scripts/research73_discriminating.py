"""Local retrospective qualification of archived real FIFO proposals.

Never reads independent outcomes or calls a model. Existing ordinary/history
rules are reused unchanged. Screening is not a prospective treatment estimate.
"""
import argparse
import os
import time
from pathlib import Path
import research72_policy as policy

b, ROOT, read, dump = policy.b, policy.ROOT, policy.read, policy.dump


def candidates():
    roots = [p for p in sorted((ROOT/'deliverables').iterdir())
             if p.is_dir() and any(p.name.startswith(f'research{n}_') for n in range(32,49))
             and any(x in p.name for x in ('real', 'continuation'))]
    skip = {'independent', 'source_snapshot', 'obj_dir', 'history', 'history_native',
            'visible_native', 'alignment', 'search', 'target_native', 'native'}
    unique = {}
    for root in roots:
        for folder, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x not in skip and not x.startswith(('compiled_', 'case_'))]
            if 'candidate.json' not in files or Path(folder).name != 'model_call':
                continue
            p = Path(folder)/'candidate.json'
            value = read(p)
            key = b.interface.executable_hash(value)
            row = unique.setdefault(key, dict(executable_hash=key, path=p.relative_to(ROOT).as_posix(),
                candidate_sha256=b.search.digest(p), sources=[],
                properties=[dict(id=a['id'], property=a['property']) for a in value['assertions']]))
            row['sources'].append(p.relative_to(ROOT).as_posix())
    return list(unique.values())


def protected():
    # Hash-only protection, no JSON parsing and no use for selection.
    roots = ['research72_real_20261024_r01', 'research72_audit_20261024_r01',
             'research63_independent_20261023_r02']
    result = {}
    for name in roots:
        for folder, dirs, files in os.walk(ROOT/'deliverables'/name):
            dirs[:] = [d for d in dirs if not d.startswith(('obj_dir', 'compiled_', 'case_'))]
            for name2 in files:
                p = Path(folder)/name2
                if p.suffix == '.json': result[p.relative_to(ROOT).as_posix()] = b.search.digest(p)
    return result


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    ready = policy.P/'ready/s6711/ordinary'
    dump(out/'cases.json', read(ready/'cases.json'))
    dump(out/'initial.json', read(policy.P/'shared_initial.json'))
    dump(out/'history_cases.json', read(policy.P/'history_cases.json'))
    dump(out/'baseline_binding.json', read(ready/'baseline_binding.json'))
    dump(out/'history_binding.json', read(policy.P/'history_binding.json'))
    dump(out/'inventory.json', candidates())
    dump(out/'protected.json', protected())
    dump(out/'protocol.json', dict(created=time.time(), study='retrospective candidate qualification',
        selection='All unique executable model_call candidates in research32..48 real/continuation folders; no outcome-based inventory filter.',
        public_rule='Unchanged research43.current_decision on all 14 research70 s6711 ordinary cases; no hidden-history outcomes used to relax this rule.',
        history_rule='Unchanged research72.decision_for with research31 applicability gate on all 105 historical cases.',
        schema='Archived executable proposals replayed verbatim. Different original interfaces remain a confound; not new controlled model arms.',
        progression='Replay baseline and every unique candidate on public cases. Only ordinary-pass candidates undergo fresh 105-history replay. All outcomes retained.',
        recovery='Archived successes may be replayed only as labeled retrospective availability controls, never as a new model response or same-budget continuation.',
        dedup='Executable property set hash for candidate denominator; obligation/reason/fault mechanism for gap denominator; waveform points not independent bugs.',
        independent='No independent outcome parsed; research72 and research63 byte hashes protected. No new independent test in this screening.',
        calls=0, native_backend='Verilator native SVA on existing axis_fifo RTL plus explicitly artificial fault modes',
        limits='Finite development evidence; no formal proof. No prospective gain or stable recovery conclusion.'))
    dump(out/'source_hashes.json', {p.relative_to(ROOT).as_posix():b.search.digest(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'sealed.json', {p.name:b.search.digest(p) for p in out.glob('*.json')})
    print('SEALED', len(read(out/'inventory.json')), 'unique candidates', flush=True)


def run(out):
    for name, h in read(out/'sealed.json').items(): assert b.search.digest(out/name)==h, name
    for name, h in read(out/'source_hashes.json').items(): assert b.search.digest(ROOT/name)==h, name
    initial=read(out/'initial.json'); cases=read(out/'cases.json'); history=read(out/'history_cases.json')
    assert len(cases)==14 and len(history)==105
    assert not (out/'run_started.json').exists(), 'never overwrite a run'
    dump(out/'run_started.json', dict(time=time.time(), model_calls=0))
    rows=[]
    with b.extension.installed():
        before=b.loop.replay(initial, out/'baseline_public', cases)
        historical=b.loop.replay(initial, out/'baseline_history', history)
        assert before['healthy'] and historical['healthy']
        for index, item in enumerate(read(out/'inventory.json')):
            p=ROOT/item['path']; assert b.search.digest(p)==item['candidate_sha256']
            candidate=read(p); folder=out/f'c{index:02d}'
            dump(folder/'candidate.json', candidate); dump(folder/'source.json', item)
            changed=[a['id'] for a in candidate['assertions'] if a not in initial['assertions']]
            # Public baseline has no misses, so the unchanged ordinary rule
            # does not inspect this edit identifier. Preserve provenance anyway.
            edit=dict(operation='keep' if b.interface.executable_hash(candidate)==b.interface.executable_hash(initial) else 'replace_one',
                      assertion_id=changed[0] if changed else '')
            small=b.loop.replay(candidate, folder/'public', cases)
            plain=b.paired.current_decision(before, small, edit)
            full=b.loop.replay(candidate, folder/'history', history) if plain['accepted'] else None
            decision=policy.decision_for(plain, full, historical, bool(full))
            row=dict(index=index, source=item['path'], executable_hash=item['executable_hash'], ordinary=plain,
                     full=decision, public_counts=small.get('counts'), history_counts=full.get('counts') if full else None,
                     ordinary_pass=plain['accepted'], additional_history_rejection=bool(full and not decision['accepted']))
            dump(folder/'decision.json',row)
            if full:
                current=b.journal(folder/'transition', initial, candidate, decision)
                assert current==(candidate if decision['accepted'] else initial)
            rows.append(row); dump(out/'screening.json',rows)
            print('SCREEN',index,'ordinary',plain['accepted'],'extra_history_rejection',row['additional_history_rejection'],flush=True)
    assert protected()==read(out/'protected.json')
    dump(out/'outcome.json',dict(candidates=len(rows),ordinary_pass=sum(r['ordinary_pass'] for r in rows),
        discriminating=sum(r['additional_history_rejection'] for r in rows),model_calls=0,protected_unchanged=True,
        scope='Retrospective local qualification; no new model recovery or independent-test claim.'))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run']);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();globals()[args.action](args.out.resolve())
