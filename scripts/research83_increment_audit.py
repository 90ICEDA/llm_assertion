"""Separate paired rejection, bounded strategy recovery, and cross-protocol repair.

Read-only recomputation of real responses/native logs. No new model invocation,
proposal selection, candidate edit, or independent-test generation is permitted.
"""
import argparse
import time
from pathlib import Path

import research71_paired_audit as paired
import research72_policy_audit as strategy
import research73_result_audit as selected
import research74_result_audit as recovery
import research81_audit as helper

b, read, dump, ROOT = selected.b, selected.read, selected.dump, selected.ROOT
D = ROOT / 'deliverables'


def location(name):
    return D / name


SOURCES = {
    'paired': ('research71_prepare_20261024_r01', 'research71_real_20261024_r01'),
    'strategy': ('research72_prepare_20261024_r02', 'research72_real_20261024_r01'),
    'selected': (None, 'research73_discriminating_20261024_r01'),
    'recovery': ('research74_prepare_20261024_r01', 'research74_real_20261024_r01'),
    'helper': ('research81_prepare_20261025_r01', 'research81_real_20261025_r01'),
}


def protected():
    result = {}
    for prep, run in SOURCES.values():
        for name in (prep, run):
            if name is None:
                continue
            root = location(name)
            # Use bounded artifact paths; do not recursively traverse native
            # compiler object trees on the Windows/WSL filesystem boundary.
            files = set(root.glob('*.json'))
            for pattern in ('core/freeze.json', 'arms/*/freeze.json',
                            'arms/*/*/freeze.json', 'arms/*/core/freeze.json',
                            'arms/*/*/core/freeze.json',
                            'evaluation/*/independent/*.json',
                            'independent_by_hash/*/independent/*.json'):
                files.update(root.glob(pattern))
            for path in files:
                result[str(path.relative_to(ROOT))] = b.search.digest(path)
    return result


def compare_repair(out):
    """ID-level descriptive comparison, never causal attribution to feedback."""
    src = location(SOURCES['selected'][1])
    prep, run = map(location, SOURCES['helper'])
    assert read(src / 'history_cases.json') == read(prep / 'history_cases.json')
    qualified = read(out / 'selected/c04_evidence.json')
    regressions = qualified['regressions']
    result = read(run / 'arms/D/core/v0/history/result.json')
    info = b.loop.inspect(result['group']['ledger'])
    # Every reference ID must be present in the new ledger, not merely absent
    # from a set of alarms. Evidence row presence is checked independently.
    lost = regressions['confirmed_lost_detection']
    alarms = regressions['new_legal_false_positive']
    old_rows = b.loop.inspect(read(src / 'c04/history/result.json')['group']['ledger'])['rows']
    for key in set(lost) | set(alarms):
        assert key in info['rows'], 'missing historical row: ' + key
        for field in ('obligation', 'stimulus_sha256', 'oracle'):
            assert old_rows[key][field] == info['rows'][key][field], (key, field)
    restored = [key for key in lost if key in info['detections']]
    cleared = [key for key in alarms if key not in info['false_positives'] and key not in info['unknown']]
    candidate = read(run / 'arms/D/core/frozen_candidate.json')
    state = read(run / 'arms/D/outcome.json')
    assert state['accepted'] and state['calls'] == 1
    assert len(restored) == len(lost) and len(cleared) == len(alarms)
    assert result['healthy'] and not info['unknown'] and not info['false_positives'] and not info['misses']
    result_data = dict(confirmed_loss_ids=lost, restored_ids=restored,
        legal_alarm_ids=alarms, cleared_ids=cleared,
        candidate_hash=b.loop.sha(candidate), counts=result['counts'],
        new_independent=read(run / 'independent_mapping.json')['D'],
        source='Previously completed research81 D first-call direct generation; no new generation in this audit.',
        causal_recovery_credit=False,
        reason='Different helper protocol and extra cumulative budget; first-call acceptance has no within-arm historical rejection feedback. This is descriptive restoration only.')
    dump(out / 'cross_protocol_restoration.json', result_data)
    return result_data


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    before = protected()
    dump(out / 'protocol.json', dict(kind='Retrospective read-only audit, not new randomized trial',
        sources=SOURCES, new_model_calls=0, new_native_queries=0,
        paired_estimand='Same real proposal, unchanged ordinary rule versus ordinary plus historical replay.',
        strategy_estimand='Existing independently generated four-arm trajectories, equal maximum calls, actual unequal costs; no cherry-picking.',
        recovery_estimand='Extra historical rejection followed by acceptance within that SAME sealed protocol/budget. Different helper protocols receive zero causal recovery credit.',
        restoration_estimand='ID-level restoration by existing research81 accepted candidate; descriptive only, no new independent result.',
        stop='Any provenance, isolation, raw replay, or state mismatch stops the audit. No new model requests, altered rules, candidate changes, or tests.'))
    dump(out / 'input_hashes.json', before)
    dump(out / 'code_versions.json', {str(p): b.search.digest(p) for p in
        [Path(__file__), Path(paired.__file__), Path(strategy.__file__), Path(selected.__file__), Path(recovery.__file__), Path(helper.__file__)]})
    timings = {}
    for label, (prep, source) in SOURCES.items():
        started = time.perf_counter()
        target = out / label
        args = (location(prep), location(source), target) if prep else (location(source), target)
        fn = dict(paired=paired.audit, strategy=strategy.audit, selected=selected.audit,
                  recovery=recovery.audit, helper=helper.audit)[label]
        # The older auditors own their runtime context; only research81's
        # programmatic API expects the caller to install it. It is not reentrant.
        if label == 'helper':
            with b.extension.installed():
                fn(*args)
        else:
            fn(*args)
        timings[label] = time.perf_counter() - started
        dump(out / 'audit_progress.json', timings)
        print('RECHECK83', label, flush=True)
    with b.extension.installed():
        restoration = compare_repair(out)
    proposals = read(out / 'paired/proposals.json')
    screened = read(out / 'selected/results.json')
    strategies = read(out / 'strategy/results.json')
    recovery_result = read(out / 'recovery/audit.json')
    metrics = dict(
        paired=dict(proposals=len(proposals), ordinary_accepts=sum(p['plain_accepted'] for p in proposals),
                    extra_rejections=sum(p['incremental_rejection'] for p in proposals)),
        selected=dict(proposals=len(screened), ordinary_accepts=sum(p['ordinary_pass'] for p in screened),
                      extra_rejections=sum(p['extra_rejection'] for p in screened),
                      selection='All nine archived screened proposals retained; selected follow-up not an unbiased prevalence estimate.'),
        independent_multiround=strategies,
        bounded_selected_recovery=dict(accepted=recovery_result['accepted'], maximum_calls=2,
                                      actual_calls=read(out / 'recovery/cost.json')['total']['model_calls']),
        cross_protocol_restoration=dict(restored=len(restoration['restored_ids']),
            confirmed_losses=len(restoration['confirmed_loss_ids']), cleared=len(restoration['cleared_ids']),
            causal_recovery_credit=False),
        new_accepted_versions=0, new_independent_tests=0, new_model_calls=0,
        conclusion='Extra rejection demonstrated in one retrospectively selected real proposal; controlled multiround incremental recovery not demonstrated. Negative trials complete within their scope; gate-eligible denominator zero is not evidence of ineffectiveness.')
    assert protected() == before, 'old inputs or independent results changed'
    audits = {label: read(out / label / 'audit.json') for label in SOURCES}
    raw = sum(a.get('native_records_recomputed', a.get('raw_native_records', 0)) for a in audits.values())
    dump(out / 'increment_results.json', metrics)
    dump(out / 'audit.json', dict(passed=True, source_audits=len(audits),
        native_records_recomputed=raw, native_recomputations_are_not_new_queries=True,
        source_checks=sum(len(a['checks']) for a in audits.values()),
        reference_recheck_wall_seconds=timings, protected_inputs_unchanged=True))
    costs = {}
    for label in ('paired', 'strategy', 'recovery', 'helper'):
        name = dict(paired='cost_by_stream.json', strategy='cost_by_arm.json',
                    recovery='cost.json', helper='cost.json')[label]
        costs[label] = read(out / label / name)['total']
    costs['selected'] = read(out / 'selected/cost.json')['total']
    dump(out / 'historical_actual_costs.json', dict(experiments=costs,
        warning='Historical experiment costs, not new calls in this audit. Search acquisition and qualification are separate. Re-audit reference time above; missing original component time/monetary bills unavailable, not zero.'))
    lines = ['# research83：防退化增量分项复核', '',
        '本轮没有模型调用、新原生查询或新独立测试。复核真实响应、原生日志、接受决定、冻结和数据隔离；不改旧结果，不追加同模型修正。', '',
        '|问题|可核查结果|结论范围|', '|---|---|---|',
        f"|同提案额外拒绝（research71）|{metrics['paired']['extra_rejections']}/{metrics['paired']['ordinary_accepts']}个普通接受提案|三个固定种子的单轮配对，没有观察到额外拒绝|",
        f"|回顾筛选额外拒绝（research73）|{metrics['selected']['extra_rejections']}/{metrics['selected']['ordinary_accepts']}；全部筛选{len(screened)}个提案|c04普通14场景通过，105历史暴露31确认漏报、46义务级误报、22关键unknown|",
        '|拒绝后的保留状态|c04被拒绝，active哈希保持基线；保留214个历史检出点|基线部分有效，不等于新目标已修复|',
        '|独立多轮策略（research72）|A/B/C/D独立通过1/3、2/3、0/3、0/3；21/24次调用|历史额外拒绝后恢复0；C/D普通接受提案分母0，未曝光门控增量判别机会|',
        f"|选定案例有界恢复（research74）|{metrics['bounded_selected_recovery']['actual_calls']}/2次调用，新接受{int(recovery_result['accepted'])}|未恢复；不转用其他协议预算补成成功|",
        f"|后续直接生成（research81）|旧31漏报恢复{len(restoration['restored_ids'])}/31，46误报消除{len(restoration['cleared_ids'])}/46；105历史214/214，新独立68/68|已完成的跨协议恢复。不是历史反馈造成恢复的因果证据，也不是本轮新增独立结果|", '',
        '额外拒绝的决定因素是新增历史证据。如果普通检查也读取同样105场景，它同样会拒绝；不能把绝对合法性检查和相对保护保持的重叠理由重复计收益。31/46/214均为有限采样证据点，不是独立Bug数。', '',
        '三种子四组受控实验已经执行，负结果不是未执行。尚未得到的是：在固定预算与相同公共辅助条件下，历史额外拒绝后的反馈带来更好的最终保护。现有C/D样本没有普通规则会接受的提案，不能据此断言机制无效。', '',
        f'复核{raw}份已有原生记录；逐实验真实成本见historical_actual_costs.json，审计重算耗时单列audit.json。模型/仿真新增成本均0。', '',
        '旧独立结果仍是各自冻结版本的结果；本次只作描述性对照，没有用它调规则、选新候选或修改断言。原始后续归因unknown保留在子审计的arms.json和counts；有限通过不等于全局保护或形式化证明。', '',
        '复核：`wsl -- python3 scripts/research83_increment_audit.py --out deliverables/research83_increment_recheck_NEW`']
    (out / 'SUMMARY.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('AUDIT83', raw, 'existing native records; no new model calls', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    run(args.out.resolve())
