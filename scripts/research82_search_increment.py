"""Fresh-seed replication of fixed search policies; no model or test-data use."""
import argparse
import copy
import json
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import research65_search_value as old
import research64_native_audit as raw

b = old.base
SEEDS = (8203, 8211, 8221)


def protected():
    # Hash bytes only, never parse independent outcomes or accepted properties.
    result = {}
    for name in ('research81_real_20261025_r01', 'research81_audit_20261025_r01'):
        root = b.ROOT / 'deliverables' / name
        paths = list(root.glob('*.json')) + list(root.glob('arms/*/core/freeze.json'))
        paths += list(root.glob('independent_by_hash/*/independent/*.json'))
        for path in paths:
            result[path.relative_to(b.ROOT).as_posix()] = b.digest(path)
    return result


@contextmanager
def installed():
    with patch.object(old, 'SEEDS', SEEDS), old.installed(), patch.object(b, 'report', report):
        yield


def prepare(out):
    with patch.object(old, 'SEEDS', SEEDS):
        old.prepare(out)
    protocol = b.read(out / 'protocol.json')
    protocol.update(experiment='research82', seeds=SEEDS,
        qualification='All three pre-existing directed candidate tasks retained, including failures. Two unordered pairs, one parent FIFO, depth4/pipeline1. Not 11 historical pairs.',
        retrospective_origin='Unchanged research65 policies/candidate inventory and action pool; three new seeds fixed before any query. No research81 accepted property or test outcome used.',
        replication='3 tasks x 3 seeds x 7 policies x 4 queries =252 maximum search queries; 6 shared public queries plus 3 builds. No algorithm tuning, early-success filtering or second batch.',
        scope='Development replication on known artificial faults. Extra public-unexposed candidate gaps and lower first-discovery cost are measured separately; no positive result required.')
    b.dump(out / 'protocol.json', protocol)
    registry = b.read(out / 'historical_registry.json')
    path = b.ROOT / 'deliverables/research65_search_value_20261024_r01/records.json'
    keys = {k for r in b.read(path) for k in r['gap_keys']}
    registry['keys'] = sorted(set(registry['keys']) | keys)
    registry['mechanisms'] = sorted(set(registry['mechanisms']) | {'/'.join(k.split('/')[1:]) for k in keys})
    registry['sources'].append(dict(path=str(path.relative_to(b.ROOT)), sha256=b.digest(path), keys=sorted(keys)))
    b.dump(out / 'historical_registry.json', registry)
    b.dump(out / 'protected81.json', protected())
    b.dump(out / 'sealed.json', {str(p.relative_to(out)): b.digest(p) for p in out.rglob('*')
        if p.is_file() and p.name not in ('sealed.json', 'outcome.json')})
    b.verify(out)
    print('SEALED82', len(SEEDS), 'seeds,252 query cap', flush=True)


def report(out):
    # Statistics reuse the exact selector replay and dedup implementation.
    with patch.object(old, 'SEEDS', SEEDS):
        old.report(out)
    assert protected() == b.read(out / 'protected81.json')
    summary = b.read(out / 'summary.json')
    totals = b.read(out / 'method_totals.json')
    records = b.read(out / 'records.json')
    refs = b.read(out / 'reference_costs.json')
    per_gap, paired = [], []
    for s in summary:
        rr = sorted((r for r in records if (r['pair'], r['seed'], r['method']) ==
                     (s['pair'], s['seed'], s['method'])), key=lambda r:r['query'])
        for key, first in s['first_query'].items():
            cc = [r for r in refs if r.get('stage') == 'search' and
                  (r.get('pair'), r.get('seed'), r.get('method')) == (s['pair'], s['seed'], s['method'])
                  and r['query'] < first]
            per_gap.append(dict(pair=s['pair'], seed=s['seed'], method=s['method'], key=key,
                first_query=first, native_executions=16*first, common_public_executions=32,
                cumulative_query_wall_seconds=sum(r['query_wall_seconds'] for r in rr[:first]),
                cumulative_selector_seconds=sum(r['selector_seconds'] for r in rr[:first]),
                reference={kind:dict(calls=sum(r['kind'] == kind for r in cc),
                    seconds=sum(r['wall_seconds'] for r in cc if r['kind'] == kind))
                    for kind in ('transaction_reference', 'sampling_reference', 'paired_obligation_judge')},
                historical_novelty=s['historical_novelty'][key]))
    for pair in b.read(out / 'public_feedback.json'):
        for seed in SEEDS:
            ss = {s['method']:s for s in summary if s['pair'] == pair and s['seed'] == seed}
            if not ss:
                continue
            contract = ss['contract_novelty']
            for method, other in ss.items():
                if method == 'contract_novelty':
                    continue
                common = set(contract['new_keys']) & set(other['new_keys'])
                paired.append(dict(pair=pair, seed=seed, comparator=method,
                    contract_only=sorted(set(contract['new_keys']) - set(other['new_keys'])),
                    comparator_only=sorted(set(other['new_keys']) - set(contract['new_keys'])),
                    common_keys=len(common),
                    earlier=sum(contract['first_query'][k] < other['first_query'][k] for k in common),
                    tied=sum(contract['first_query'][k] == other['first_query'][k] for k in common),
                    later=sum(contract['first_query'][k] > other['first_query'][k] for k in common)))
    unions = {m:set(t['keys']) for m,t in totals.items()}
    extra = sorted(unions['contract_novelty'] - set().union(*(s for m,s in unions.items() if m != 'contract_novelty')))
    b.dump(out / 'first_discovery_actual_cost.json', per_gap)
    b.dump(out / 'paired_increment.json', paired)
    b.dump(out / 'increment_conclusion.json', dict(contract_unique_over_all=extra,
        extra_over_all_count=len(extra), observed_candidate_tasks=len(b.PAIRS), fixed_seeds=list(SEEDS),
        mechanism_effect='Measured within this finite development scope; no general advantage or global novelty claim.',
        unobserved_cost='Missing discovery within four queries is censored, not assigned cost five.',
        timing='Reference/native components overlap query wall time; never sum them twice. Single sequential run, timing is descriptive.',
        protected81_unchanged=True))
    cost = b.read(out / 'cost.json')['total']
    lines = ['# research82：契约搜索增量与成本复现', '',
        '协议先封存后执行。固定3个有向候选任务、3个新种子、7种原策略、各4查询；同一公共反馈、候选、激励池和原生查询预算。未调用模型，未读取research81成功性质或独立结果用于选择。', '',
        '|策略|公共之外去重候选缺口|重复动作|查询|关键unknown|后续归因unknown|',
        '|---|---:|---:|---:|---:|---:|']
    for m,t in totals.items():
        lines.append(f"|{m}|{t['unique_candidate_gaps']}|{t['repeated_action_queries']}|{t['queries']}|{t['unknown']}|{t['later_attribution_unknown']}|")
    lines += ['', f'契约相对全部对照并集独有缺口：{len(extra)}。公共反馈已曝光的问题不计收益；按候选/误报或漏报/义务/机制去重，长短波形不另计。所有故障是已知人工变异，历史未命中为unknown。', '',
        '|对照|共同发现点上契约更早/相同/更晚|契约单独找到（任务×种子）|对照单独找到|',
        '|---|---|---:|---:|']
    for m in old.METHODS:
        if m == 'contract_novelty':
            continue
        rows = [r for r in paired if r['comparator'] == m]
        lines.append(f"|{m}|" + '/'.join(str(sum(r[k] for r in rows)) for k in ('earlier','tied','later')) +
                     f"|{sum(len(r['contract_only']) for r in rows)}|{sum(len(r['comparator_only']) for r in rows)}|")
    lines += ['', '表中的任务×种子发现次数不是独立Bug数量；对未发现项保留预算内未找到，不伪造发现成本。逐缺口轨迹与实际查询、参考判定计数和耗时见first_discovery_actual_cost.json；实际候选分歧使用两套性质的原生失败集合异或。', '',
        f"实际编译{cost['native_compile_calls']}次、执行{cost['native_execute_calls']}次；模型/形式化0。共同编译与公共查询成本单列于cost.json，所有参考判定逐次记录于reference_costs.json。审计重算单独收费，不混入发现成本。", '',
        '这里只验证固定开发范围的发现/成本差异；同一父FIFO、已知人工故障、3候选方向不能推广为跨历史Bug稳定优势。研究65/70无额外独有缺口的旧结果保持不变。未调整策略追求正收益。', '',
        '复核：`wsl -- python3 scripts/research82_search_increment.py audit --run '+str(out.relative_to(b.ROOT)).replace('\\','/')+' --out deliverables/research82_audit_NEW`']
    (out / 'SUMMARY.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('REPORT82 extra_over_all', len(extra), flush=True)


def audit(root, out):
    with installed():
        raw.audit(root, out)
        report(root)
    # Byte-identical stimulation when method, but not selection, changes.
    seen, count = {}, 0
    for r in b.read(root / 'records.json'):
        identity = (r['pair'], r['seed'], r['query'], r['family'], r['duration'])
        primary = r['pair'].split('__')[0]
        path = root/'queries'/r['pair']/f"s{r['seed']}"/r['method']/f"q{r['query']}"/primary/'correct_stimulus/stimulus.json'
        h = b.digest(path)
        if identity in seen:
            assert seen[identity] == h
            count += 1
        seen[identity] = h
    # Selector sensitivity is diagnostic only, never credited as a discovery.
    probes = []
    public = b.read(root / 'public_feedback.json')
    for s in b.read(root / 'summary.json'):
        if s['method'] != 'contract_novelty':
            continue
        p = old.policy.Acquisition('contract_novelty', s['seed'])
        for r in public[s['pair']]['results']:
            p.observe(r['family'], r)
        for q in range(b.BUDGET):
            baseline = copy.deepcopy(p)
            chosen = p.choose()
            altered = copy.deepcopy(baseline); altered.exposed.clear()
            changed = altered.choose()
            probes.append(dict(pair=s['pair'], seed=s['seed'], query=q,
                actual=[chosen['family'], chosen['duration']],
                without_exposure=[changed['family'], changed['duration']],
                different=(chosen['family'], chosen['duration']) != (changed['family'], changed['duration'])))
            r = b.read(root/'queries'/s['pair']/f"s{s['seed']}"/'contract_novelty'/f'q{q}/result.json')
            p.observe(r['family'], r)
    b.dump(out/'selection_audit.json', dict(shared_input_matches=count, probes=probes,
        selection_changes=sum(p['different'] for p in probes), sensitivity_is_not_gain=True))
    b.dump(out/'conclusion.json', b.read(root/'increment_conclusion.json'))
    print('AUDIT82 DONE', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['prepare','run','report','audit'])
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--run', type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        prepare(a.out.resolve())
    elif a.action == 'run':
        with installed():
            b.run(a.out.resolve())
    elif a.action == 'report':
        report(a.out.resolve())
    else:
        audit(a.run.resolve(), a.out.resolve())
