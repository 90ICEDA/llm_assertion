"""Local rule discrimination and archived search eligibility; no model/holdout reads.

Ledger mutations below are explicitly synthetic software checks, not RTL witnesses.
Native qualifications are recomputed from the existing development logs unchanged.
"""
import argparse
import copy
import hashlib
import itertools
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import research116_prospective_deepseek as s
import research117_search_preparation as search
from research88_cross_parent_audit import inspect_version

ROOT, read, dump, sha, x = s.ROOT, s.read, s.dump, s.sha, s.x
PREP = ROOT / 'deliverables/research116_prepare_20261025_r01'
SEARCH = ROOT / 'deliverables/research117_search_prepare_20261025_r01'
AUDIT = ROOT / 'deliverables/research117_native_audit_20261025_r01/audit.json'


def guard_reads():
    """Fail closed on test/outcome input access; hash only permitted development files."""
    opened = set()
    def hook(event, args):
        if event != 'open' or not isinstance(args[0], (str, bytes)):
            return
        name = str(args[0]).replace('\\', '/')
        mode = args[1]
        if isinstance(mode, str) and any(c in mode for c in 'wax+'):
            return
        if any(z in name for z in ('research113_real_', 'research116_real_', '/independent', '/frozen/')):
            raise RuntimeError('forbidden_test_or_success_input:' + name)
        if '/deliverables/' in name or name.startswith('deliverables/'):
            opened.add(name)
    sys.addaudithook(hook)
    return opened


def refresh(result):
    info = x.old.acceptance.inspect(result['ledger'])
    result['counts'] = {k: len(info[k]) for k in ('rows', 'triggers', 'detections', 'misses', 'false_positives', 'unknown')}
    result['required_untriggered'] = [k for k, r in info['rows'].items() if r['required'] and k not in info['triggers']]
    return result


def gate_pair(base, full, protected):
    # Common ordinary/native-all-property factors held true to isolate H versus R.
    return dict(H=bool(x.old.admissible(full)),
                R=bool(x.g.prior.preserve(base, full, protected, x.old.decide)['accepted']))


def rule_audit(check):
    base = read(PREP / 'baseline_full.json')
    initial = read(PREP / 'initial.json')
    protected = read(x.P / 'target_preservation.private.json')
    cases = [('baseline', PREP / 'baseline_native', initial),
             ('positive_fixture', PREP / 'controls/positive/native', read(PREP / 'controls/positive/candidate.json')),
             ('overbroad_fixture', PREP / 'controls/known_overbroad/native', read(PREP / 'controls/known_overbroad/candidate.json'))]
    actual = []; full_good = None; base_records = None; raw_rows = 0
    oldinfo = x.old.acceptance.inspect(base['ledger'])
    for name, folder, candidate in cases:
        n, ev, records = inspect_version(folder, candidate, base)
        raw_rows += n
        full = x.paired.aggregate(records['history'], records['search'])
        info = x.old.acceptance.inspect(full['ledger'])
        check(name + '/complete_identity', oldinfo['rows'].keys() == info['rows'].keys() and all(
            all(oldinfo['rows'][k][f] == info['rows'][k][f] for f in ('obligation', 'stimulus_sha256', 'oracle', 'required'))
            for k in oldinfo['rows']))
        check(name + '/no_ledger_errors', not info['errors'])
        check(name + '/H_equals_R', ev['full_absolute'] == ev['history']['accepted'])
        expected = {'baseline': dict(O=False, H=False, R=False),
                    'positive_fixture': dict(O=True, H=True, R=True),
                    'overbroad_fixture': dict(O=True, H=False, R=False)}[name]
        check(name + '/original_rules', s.old.decisions(ev) == expected)
        actual.append(dict(name=name, source=folder.relative_to(ROOT).as_posix(), decisions=expected,
            native_rows=n, fixture=name != 'baseline', new_false_alarms=len(ev['new_false_alarm_ids']),
            lost_detections=len(ev['lost_detection_ids']), retained_detections=len(ev['retained_detection_ids']), counts=ev['counts']))
        if name == 'positive_fixture': full_good = full
        if name == 'baseline': base_records = records
    goodinfo = x.old.acceptance.inspect(full_good['ledger'])
    violation_ids = {k for k, r in goodinfo['rows'].items() if r['oracle']['verdict'] == 'violated'}
    check('protected_exact_all_690_targets', set().union(*(set(v) for v in protected.values())) == violation_ids)
    check('baseline_270_detection_subset', len(oldinfo['detections']) == 270 and oldinfo['detections'] <= violation_ids)
    check('baseline_420_misses_subset', len(oldinfo['misses']) == 420 and oldinfo['misses'] <= violation_ids)
    check('baseline_no_malformed_or_unknown', not oldinfo['errors'] and not oldinfo['unknown'])
    # All distinct independent oracle/required/obligation/revision classes.
    representatives = {}
    for index, row in enumerate(full_good['ledger']):
        representatives.setdefault((row['oracle']['verdict'], row['required'], row['obligation'], row['revision']), index)
    synthetic = []
    for label, index in representatives.items():
        for trigger, failed, causal in itertools.product((False, True), repeat=3):
            edited = copy.deepcopy(full_good)
            edited['ledger'][index]['native']['assertions'] = [dict(id='software_fixture', trigger=trigger, failed=failed, causal_detection=causal)]
            refresh(edited)
            pair = gate_pair(base, edited, protected)
            check('fixed_identity_state/' + str(label) + str((trigger, failed, causal)), pair['H'] == pair['R'])
            synthetic.append(dict(kind='synthetic_not_native', row_class=label, state=[trigger, failed, causal], **pair))
    integrity = []
    # These exercise record-integrity differences, not a model-expressible RTL change.
    for kind in ('remove_target_row', 'change_stimulus_identity', 'duplicate_row'):
        edited = copy.deepcopy(full_good)
        index = next(i for i, r in enumerate(edited['ledger']) if r['evidence_id'] in violation_ids)
        if kind == 'remove_target_row': edited['ledger'].pop(index)
        elif kind == 'change_stimulus_identity': edited['ledger'][index]['stimulus_sha256'] = 'synthetic_identity_change'
        else: edited['ledger'].append(copy.deepcopy(edited['ledger'][index]))
        refresh(edited); pair = gate_pair(base, edited, protected)
        check('integrity_difference/' + kind, pair == dict(H=True, R=False))
        integrity.append(dict(kind=kind, synthetic_not_native=True, **pair,
                              interpretation='Replay-integrity protection, not extra assertion protection on a complete fixed corpus.'))
    # Adapter-only checks: no fixture is written to any model request.
    edit = dict(operation='replace_op', reason='local interface audit', assertions=[{k: initial['assertions'][1][k]
                for k in ('antecedent', 'consequent', 'timing', 'obligations')}])
    candidate, _ = s.old.prior.p.TEXT_ADAPT(edit, initial)
    check('adapter_fixed_branch', candidate['assertions'][0] == initial['assertions'][0])
    for kind in ('branch_obligation_edit', 'remove_all_op', 'reserved_branch_id'):
        invalid = copy.deepcopy(edit)
        if kind == 'branch_obligation_edit': invalid['assertions'][0]['obligations'] = ['illegal_branch_persists']
        elif kind == 'remove_all_op': invalid['assertions'] = []
        else: invalid['assertions'][0]['id'] = 'a0'
        rejected = False
        try: s.old.prior.p.TEXT_ADAPT(invalid, initial)
        except (ValueError, AssertionError, KeyError, TypeError): rejected = True
        check('adapter_rejects/' + kind, rejected)
    result = dict(native_development_rows_reaudited=raw_rows, actual_cases=actual,
        synthetic_state_checks=synthetic, synthetic_integrity_checks=integrity,
        H_R_equivalence_scope='Complete identity-preserving, well-formed fixed151 corpus; required flags and oracle verdicts fixed; protected IDs exactly all690 violations. Both use the same O and all-property guards.',
        implication='R implies H by explicit admissible(full). Under these invariants H implies every R relative constraint: no new FP, all old detections and targets detected, all required triggers present, no missing/changed identities or malformed rows.',
        unrestricted_equivalence=False, independent_test_inputs_read=False,
        contrasts=dict(O_vs_history_qualified=True, H_vs_R_semantic_increment_qualified=False,
                       H_vs_R_integrity_only_qualified=True),
        excluded_by_interface=['delete or alter fixed BRANCH component', 'relabel OP as BRANCH', 'empty OP set'],
        still_model_expressible=['OP too broad creates legal historical false alarms', 'OP too narrow or wrong phase loses OP detections/triggers', 'OP next-sample check alarms after transaction switch'],
        opportunity_limit='Initial OP detects0/420; fixed BRANCH retains270. Initial shared step cannot demonstrate loss of previously detected OP. Model text cannot remove fixed BRANCH. Public OP failures are rejected by O already.',
        reporting='O/H can test added history. H/R independent random continuation differences cannot establish unique relative-rule effect. Synthetic corruption is not a successful model proposal or native witness.')
    return result, base_records


def search_matrix(check):
    search.b.verify(SEARCH)
    native = read(AUDIT)
    check('search_native_audit_passed', native['passed'] and native['native_replays_verified'] == 2520)
    inventory = read(SEARCH / 'inventory.json'); qualification = read(SEARCH / 'qualification.json')
    public = read(SEARCH / 'public_feedback.json'); records = read(SEARCH / 'records.json')
    history = set(read(SEARCH / 'historical_registry.json')['keys'])
    earlier = search.b.historical_registry()
    history.update(earlier['keys'])
    historical_mechanisms = {'/'.join(k.split('/')[1:]) for k in history} | set(earlier['mechanisms'])
    modes = read(SEARCH / 'protocol.json')['modes'][1:]
    mechanisms = sorted({search.b.mechanism(m) for m in modes})
    grouped = defaultdict(list)
    for r in records: grouped[r['pair']].append(r)
    detailed = []; candidates = []; obligations = []; known_rows = []
    for item, qual in zip(inventory, qualification):
        name = item['name']; pair = name + '__reference'
        check(name + '/qualification_identity', qual['pair'] == pair)
        candidate = read(SEARCH / 'candidates' / (name + '.json')); content_hash = search.b.loop.sha(candidate)
        observations = [(r, SEARCH / 'public' / pair / ('q' + str(q)), 'public') for q, r in enumerate(public[pair]['results'])]
        observations += [(r, SEARCH / 'queries' / pair / ('s' + str(r['seed'])) / r['method'] / ('q' + str(r['query'])), 'search') for r in grouped[pair]]
        pubkeys = set(public[pair]['gap_keys']); allkeys = set(); sources = defaultdict(list); expose = defaultdict(Counter)
        ob_checks = Counter(); ob_triggers = Counter(); critical = later = 0
        for r, folder, stage in observations:
            critical += r['unknown']; later += r['later_attribution_unknown']
            ob_checks.update(r['fixed_obligation_checks']); ob_triggers.update(r['effective_native_triggers'])
            for gap in r['gaps']:
                check(name + '/gap_hash/' + gap['key'], gap['key'].split('/')[0] == content_hash)
                if gap['kind'] == 'FN': check(name + '/confirmed_gap/' + gap['key'], gap['validation']['valid'] and all(gap['validation']['conditions'].values()))
                allkeys.add(gap['key'])
                sources[gap['key']].append(dict(stage=stage, result=(folder / 'result.json').relative_to(ROOT).as_posix(),
                    trigger_class=gap.get('trigger_class'), mode=gap['mode'], evidence_id=gap.get('evidence', {}).get('evidence_id')))
            for mode in modes:
                j = read(folder / 'judgements' / (mode + '.json'))
                mech = search.b.mechanism(mode)
                info = search.b.loop.inspect(j['target_rows'])
                expose[mech]['query_mode_observations'] += 1
                for kind in ('detections', 'misses', 'unknown'):
                    expose[mech][kind] += len(info[kind])
                expose[mech]['critical_unknown_rows'] += len(j['unknown_rows'])
                expose[mech]['later_attribution_unknown_rows'] += len(j['exclusions'])
                for row in j['target_rows']: expose[mech]['obligation:' + row['obligation']] += 1
        for key in sorted(allkeys):
            _, kind, ob, mech = key.split('/')
            row = dict(candidate=name, key=key, kind=kind, obligation=ob, mechanism=mech,
                public_feedback_known=key in pubkeys, historically_known_same_candidate_before117=key in history,
                historically_known_mechanism_before117='/'.join((kind, ob, mech)) in historical_mechanisms,
                historical_registry_absence='unknown_not_globally_new', known_development_now=True,
                current_confirmed_miss=kind == 'FN', candidate_qualified=qual['qualified'], sources=sources[key])
            known_rows.append(row)
        for mech in mechanisms:
            keys = sorted(k for k in allkeys if k.split('/')[1] == 'FN' and k.split('/')[-1] == mech)
            counts = dict(expose[mech])
            target_count = sum(counts.get(k, 0) for k in ('detections', 'misses', 'unknown'))
            status = ('confirmed_current_miss' if keys else 'critical_unknown' if counts.get('critical_unknown_rows', 0)
                      else 'no_confirmed_target_exposure' if not target_count else 'no_validated_miss_in_observed_scope')
            detailed.append(dict(candidate=name, candidate_qualified=qual['qualified'], mechanism=mech, status=status,
                observed_obligations=sorted(k.removeprefix('obligation:') for k in counts if k.startswith('obligation:')),
                public_known_keys=sorted(set(keys) & pubkeys), confirmed_FN_keys=keys,
                same_candidate_historically_known_keys=sorted(set(keys) & history), exposure=counts,
                historical_mechanism_known=any(k.endswith('/' + mech) for k in historical_mechanisms),
                beyond_public_queries=len(grouped[pair]), scope='Counts include repeated methods/seeds/modes; no exposure is not protection. No unselected search outcome is inferred.'))
        for ob in sorted(set(ob_checks) | set(ob_triggers)):
            obligations.append(dict(candidate=name, obligation=ob, independent_fixed_checks=ob_checks[ob],
                effective_trigger_observations=ob_triggers[ob], scope='Aggregated fixed/reference observations, not full obligation protection.'))
        candidates.append(dict(name=name, source=item['path'], candidate_content_hash=content_hash,
            executable_hash=item['executable_hash'], qualified=qual['qualified'], failure=qual['failure'],
            selected117=qual['selected'], public_queries=len(public[pair]['results']), search_queries=len(grouped[pair]),
            public_known_gap_count=len(pubkeys), confirmed_current_FN_keys=sorted(k for k in allkeys if k.split('/')[1] == 'FN'),
            observed_public_unexposed_keys=sorted(allkeys - pubkeys), historical_same_candidate_keys=sorted(allkeys & history),
            critical_unknown=critical, later_attribution_unknown=later,
            future_eligibility='eligible_for_new_scope_qualification' if qual['qualified'] else 'rejected_public_qualification',
            selection_warning='Observed development candidate; not a new independent or historical parent case.'))
    check('all_nine_candidates_retained', len(candidates) == 9)
    check('seven_unsearched_not_claimed_tested', sum(c['search_queries'] == 0 for c in candidates) == 7)
    check('all_search_queries_accounted', sum(c['search_queries'] for c in candidates) == 108)
    return dict(candidates=candidates, matrix=detailed, obligation_coverage=obligations, gap_registry=known_rows,
        source_native_audit=AUDIT.relative_to(ROOT).as_posix(), source_native_audit_sha256=sha(AUDIT),
        historical_registry_scope='Partial research30/42/82/84 registry; absence means unknown. All observed117 gaps must be known development at the next protocol lock.',
        next_population_rule='All8 publicly eligible archived candidates, including6 not previously searched; no selection by gap count or favorable method result. c07 retained as excluded. New public qualification and parameter-specific exposure still required.',
        new_native_queries=0, new_model_calls=0, new_independent_tests=0)


def run(out):
    opened = guard_reads(); checks = []
    def check(name, value):
        if not value: raise AssertionError(name)
        checks.append(name)
    start = time.time()
    # Check old seals without invoking helpers that inspect protected holdout paths.
    for rel, digest in read(PREP / 'sealed.json').items(): check('old_seal/' + rel, sha(PREP / rel) == digest)
    rules, _ = rule_audit(check)
    matrix = search_matrix(check)
    out.mkdir(parents=True, exist_ok=False)
    dump(out / 'rule_audit.json', rules)
    for name, value in matrix.items():
        if name in ('candidates', 'matrix', 'obligation_coverage', 'gap_registry'): dump(out / ('search_' + name + '.json'), value)
    consumed = {str(Path(p).resolve().relative_to(ROOT)): sha(Path(p)) for p in sorted(opened) if Path(p).is_file()}
    dump(out / 'input_bindings.json', consumed)
    audit = dict(passed=True, checks=len(checks), check_names=checks, elapsed_seconds=time.time() - start,
        native_development_rows_reaudited=rules['native_development_rows_reaudited'],
        search_candidates=len(matrix['candidates']), search_candidate_mechanism_cells=len(matrix['matrix']),
        search_public_qualified=sum(c['qualified'] for c in matrix['candidates']),
        rule_contrasts=rules['contrasts'], new_model_calls=0, new_native_executions=0,
        new_accepted_versions=0, new_independent_tests=0, holdout_read_guard_enforced=True,
        protocol_eligibility='O_vs_history_only; R is paired shadow, not distinct recovery arm',
        script_sha256=sha(Path(__file__)))
    dump(out / 'audit.json', audit)
    lines = ['# research122 本地区分能力与搜索资格审计', '',
        f'本轮模型调用0、新原生执行0、新接受版本0、新独立验收0。复核{rules["native_development_rows_reaudited"]}条已有原生开发记录；{len(checks)}项检查通过。', '',
        '## O / H / R', '',
        '|开发资格对象|O|H|R|新增合法误报|旧检出丢失|', '|---|---|---|---|---:|---:|']
    for r in rules['actual_cases']: lines.append(f'|{r["name"]}|{r["decisions"]["O"]}|{r["decisions"]["H"]}|{r["decisions"]["R"]}|{r["new_false_alarms"]}|{r["lost_detections"]}|')
    lines += ['', '正负对照仅作本地资格，不是新模型提案。O与历史检查可区分；固定151事务、完整且身份一致的证据上，H与R的语义接受条件等价。R已包含H的绝对要求；H通过则690个目标及所有必要触发均满足，因而相对保护条件也满足。',
        '', 'R对缺失目标行、改变输入身份、重复行的额外拒绝已用软件故障注入验证。这是记录完整性检查，不能冒充模型性质退化上的独有收益；原始生成器固定证据，正常候选不会造成这些改变。',
        '', '固定BRANCH组件使模型无法删除/修改原有270个BRANCH检出。基线OP为0/420，首提案没有既有OP检出可丢失。仍可发生新增OP引起的历史合法误报；公共目标内的OP漏报O本身就会拒绝。',
        '', '## 搜索候选资格', '', '|候选|公共合格|公共已知缺口|117搜索查询|当前确认FN类|公共之外已见类|关键unknown|后续unknown|', '|---|---|---:|---:|---:|---:|---:|---:|']
    for c in matrix['candidates']: lines.append(f'|{c["name"]}|{c["qualified"]}|{c["public_known_gap_count"]}|{c["search_queries"]}|{len(c["confirmed_current_FN_keys"])}|{len(c["observed_public_unexposed_keys"])}|{c["critical_unknown"]}|{c["later_attribution_unknown"]}|')
    lines += ['', '逐候选×失效机制见search_matrix.json；逐义务触发与参考检查见search_obligation_coverage.json；实际漏报、公开/历史已知状态及原始查询来源见search_gap_registry.json。没有曝光、没有执行后续搜索、存在unknown均不计完整保护。',
        '', matrix['historical_registry_scope'], '',
        '## 下一步资格结论', '',
        '可以封存O对历史检查的单次小预算先导，R只作同提案影子判定，不能再把H/R的独立随机续轮差异解释为相对规则收益。该先导只估计新增历史检查的额外拒绝与恢复；不能证明检出丢失的恢复或跨案例稳定性。',
        '', '搜索扩展应保留全部8个公共合格候选及c07排除记录，重新按参数确认资格；不能按本矩阵的有利结果挑选。旧公共之外的发现现在都是已知开发资料，未来不得再次计作历史新发现。',
        '', 'research113/116独立输入和结果未读取；旧失败和冻结结果未修改。有限日志审计不是新的RTL实验或形式化证明。']
    (out / 'SUMMARY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    dump(out / 'sealed.json', {f.name: sha(f) for f in out.iterdir() if f.is_file()})
    print('AUDIT122', {k: v for k, v in audit.items() if k != 'check_names'}, flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    run(ap.parse_args().out.resolve())
