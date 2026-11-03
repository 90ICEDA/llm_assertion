"""Closed, development-only qualification audit; no model or native dispatch.

Preserve the research181 C interface, not its successful generated assertions.
Do not reopen the stopped frame_len baseline or inspect independent results.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'deliverables'
P = D / 'research181_presentation_prepare_20261030_r01'
OLD = D / 'research176_discrimination_audit_20261029_r01'
Q = D / 'research178_partial_report_20261029_r01'
RUNS = {
    'real179': D / 'research179_frame_controller_run_20261029_r01/shared',
    'real181C': D / 'research181_presentation_run_20261030_r01/arms/C/r0',
    'real181T': D / 'research181_presentation_run_20261030_r01/arms/T/r0',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(out):
    out.mkdir(parents=True, exist_ok=False)
    reads, blocked, checks = set(), [], []
    # Closed input roots, with stricter run subdirectories excluding all holdouts.
    allowed = [OLD, Q, P, *RUNS.values(),
               D / 'research178_partial_prepare_20261029_r01/seal.json',
               D / 'research180_frame_failure_diagnosis_20261029_r01/seal.json',
               D / 'research179_frame_controller_run_20261029_r01/outcome.json',
               D / 'research179_frame_controller_run_20261029_r01/budget_ledger.json',
               D / 'research178_partial_run_20261029_r01',
               D / 'research177_history_prepare_20261029_r03',
               D / 'research177_history_report_20261029_r01',
               D / 'research179_frame_controller_prepare_20261029_r01']

    def guard(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system'):
            raise RuntimeError('no_network_or_child_process')
        if event != 'open' or not isinstance(args[0], (str, bytes)):
            return
        path = Path(args[0]).resolve()
        mode = args[1]
        writing = isinstance(mode, str) and any(k in mode for k in 'wax+')
        if writing:
            if not path.is_relative_to(out):
                raise RuntimeError('writes_only_to_new_audit')
            return
        name = path.as_posix().lower()
        if any(k in name for k in ('/.secrets/', '/.env', '/independent', '/holdout',
                                   '/tested_versions/', '/terminal_frozen/')):
            blocked.append(str(path))
            raise RuntimeError('excluded_material')
        if path.is_relative_to(D) and not path.is_relative_to(out):
            if not any(path.is_relative_to(p) for p in allowed):
                blocked.append(str(path))
                raise RuntimeError('excluded_material')
        if path.is_relative_to(ROOT) and not path.is_relative_to(out):
            reads.add(path)

    sys.addaudithook(guard)
    import research179_frame_controller as c

    def check(name, ok):
        checks.append(dict(name=name, passed=bool(ok)))
        assert ok, name

    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))

    def dump(name, value):
        (out / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

    def sealed(folder, name):
        check('seal ' + str(folder.relative_to(D)) + '/' + name,
              sha(folder / name) == read(folder / 'seal.json')[name])
        return read(folder / name)

    # These checks reject before opening files, including aggregate reports that
    # could leak independent outcomes. The successful C candidate is local only.
    for path in [D/'research181_presentation_run_20261030_r01/independent/C/result.json',
                 D/'research181_presentation_report_20261030_r01/SUMMARY.md',
                 D/'research174_independent_run_20261028_r01/result.json',
                 D/'research175_exposure_run_20261028_r01/result.json',
                 D/'research133_independent/result.json']:
        try:
            path.read_bytes()
        except RuntimeError as e:
            check('deny ' + str(path.relative_to(D)), str(e) == 'excluded_material')
        else:
            raise AssertionError('isolation failure')

    # Define the population before evaluating new proposal outcomes. Entries
    # include diagnostic/control versions, not independent bugs or new trials.
    inherited = sealed(OLD, 'candidate_matrix.json')
    ids = [v['id'] for v in inherited]
    original_cases = ['pipeline_offbyone', 'pipeline_assignment', 'switch_alignment', 'frame_len_consecutive']
    controls = c.controls()
    population = dict(scope='closed existing development inventory; not exhaustive repository/upstream screening',
                      inherited=ids, original_case_diagnostics=original_cases,
                      controls=list(controls)+['pipeline_hold'], proposals=list(RUNS),
                      ordering='all inherited entries, four research177 cases, all research178 controls, all subsequent real development proposals',
                      prohibited='No predicate removal, public-rule weakening, independent-data selection, new faults or repeated baseline pilot.')
    dump('population_lock', population)
    check('inherited43', len(ids) == 43)

    request = sealed(P, 'C/request.preview.json')
    body = json.loads(request['messages'][1]['content'])
    initial = sealed(P, 'initial.json')
    rows = sealed(P, 'development.json')
    protected = sealed(P, 'protected.json')
    check('request uses original partial baseline', body['current_assertions'] == initial == controls['baseline'])
    interface = dict(model_parameters={k: request[k] for k in ('model', 'temperature', 'max_tokens', 'seed')},
                     system_message=request['messages'][0],
                     interface=body['interface'], output_schema=body['output_schema'],
                     acceptance_description=body['acceptance'],
                     evidence_layout='original nested development records (C)',
                     source_request_sha256=sha(P/'C/request.preview.json'),
                     successful_model_predicates_included=False,
                     scope='frame_len interface frozen; other RTL requires separate local interface qualification',
                     pilot_authorized=False)
    dump('public_interface_lock', interface)
    code = sealed(P, 'code_bindings.json')
    for path, expected in code.items():
        check('code binding ' + path, sha(ROOT/path) == expected)
    dump('native_standard_lock', dict(
        code_bindings=code, rtl_versions=sealed(P, 'rtl_versions.json'),
        ordinary='Complete native execution and independent input-event oracle; separated targets detected and triggered; no applicable legal false alarms or critical unknown.',
        historical='Same ordinary gate plus adjacent targets and prior detection/trigger preservation.',
        no_applicability_change=True, H_R='equivalent in this evidence scope',
        frozen_functions=['research179_frame_controller.measure', 'research179_frame_controller.bench',
                          'research178_partial_qualification.independent_events', 'research_native_runner.run_native']))

    matrix = [dict(v, audit182_status='excluded_new_pilot', evidence_level='inherited sealed development audit; not reexecuted') for v in inherited]
    pairs = sealed(D/'research177_history_report_20261029_r01', 'pair_counts.json')
    dump('original_pair_evidence', pairs)
    reasons = {
        'pipeline_offbyone': 'Reliable pair; existing hold properties detect zero old violations. Boundary and drain symptoms of one loss cannot supply separate old/current protection.',
        'pipeline_assignment': 'No distinct functional repair witness; shared capacity defect remains. Unknown, not a new qualified case.',
        'switch_alignment': 'Whitespace-only change; no functional repair witness.',
        'frame_len_consecutive': 'Reliable pair and structural distinction already used in research179/181. Same stopped baseline, no newly exposed mechanism.',
    }
    for case in original_cases:
        matrix.append(dict(id='original_'+case, parent=case, origin='archived_original_RTL_diagnostic',
                           reason=[reasons[case]], audit182_status='excluded_new_pilot',
                           evidence_level='sealed research177 pair summary; not reexecuted'))
    qual = sealed(Q, 'candidate_qualification_matrix.json')
    pipeline = next(v for v in qual if v['case'] == 'pipeline_offbyone')
    check('pipeline no retained target protection', pipeline['old_target_detections'] == 0 and not pipeline['qualified'])
    matrix.append(dict(id='pipeline_hold', parent='pipeline_offbyone', origin='handwritten_development_control',
                       audit182_status='excluded_new_pilot', reason=[pipeline['reason']],
                       historical_detected=0, current_missed=pipeline['current_missed_loss_traces']))

    evs = {}
    for name, candidate in controls.items():
        evs[name] = c.measure(candidate, c.N178, rows, protected, fixture_subset=True)
    for name, run in RUNS.items():
        candidate = read(run/'model_call/candidate.json')
        ev = c.measure(candidate, run/'native', rows, protected)
        saved = read(run/'evaluation.json')
        for key in ('ordinary', 'history', 'unknown', 'lost', 'new_false', 'detected', 'public_missed', 'history_missed'):
            # Native markers are reconstructed from sets; ordering is not a verdict.
            actual, expected = ev[key], saved[key]
            if isinstance(actual, list):
                actual, expected = sorted(actual), sorted(expected)
            check(name+' recompute '+key, actual == expected)
        # Verify the executed bench corresponds exactly to the archived proposal.
        for cfg in (0, 1):
            for rev in ('before', 'after'):
                folder = run/'native'/str(cfg)/rev
                check(name+f' executed candidate {cfg}/{rev}',
                      (folder/'tb.sv').read_text() == c.bench(candidate, cfg, rows))
        evs[name] = ev
        # Do not export any successful C predicate to a request/template.
        dump(name+'_development_digest', dict(candidate_sha256=sha(run/'model_call/candidate.json'),
                                              detected=ev['detected'], public_missed=ev['public_missed'],
                                              history_missed=ev['history_missed'], false_alarms=ev['new_false'],
                                              unknown=ev['unknown'], mapping=ev['mapping']))

    for name, ev in evs.items():
        old = len(set(protected) & set(ev['detected']))
        partial = bool(old and ev['public_missed'] and not ev['new_false'] and not ev['unknown'])
        reasons_here = []
        if not old: reasons_here.append('no_old_target_detection')
        if not ev['public_missed']: reasons_here.append('no_current_development_miss')
        if ev['new_false']: reasons_here.append('legal_false_alarms')
        if ev['unknown']: reasons_here.append('critical_unknown')
        if partial: reasons_here.append('same_already_stopped_baseline_and_mechanism')
        matrix.append(dict(id=name, parent='frame_len_consecutive',
                           origin='real_model_development' if name.startswith('real') else 'handwritten_local_control',
                           historical_detected=old, historical_total=len(protected),
                           current_detected=len(ev['public_targets'])-len(ev['public_missed']), current_total=len(ev['public_targets']),
                           false_alarms=len(ev['new_false']), critical_unknown=len(ev['unknown']),
                           ordinary=ev['ordinary'], history=ev['history'], editable=True,
                           structural_partial=partial, new_failure_mechanism=False,
                           audit182_status='excluded_new_pilot', reason=reasons_here,
                           evidence_level='fresh reconstruction of archived native logs; no new simulation'))
    check('closed57 entries', len(matrix) == 57 and len({v['id'] for v in matrix}) == 57)
    check('baseline partial only', [k for k,v in evs.items() if set(protected)&set(v['detected']) and v['public_missed'] and not(v['new_false'] or v['unknown'])] == ['baseline'])
    check('local discriminator still holds', evs['replacement']['ordinary'] and not evs['replacement']['history'] and len(evs['replacement']['lost']) == 6)
    check('complete control', evs['union']['history'])
    check('C has no remaining development target gap', evs['real181C']['history'] and not evs['real181C']['public_missed'])
    check('T not qualified by incidental target alarms', len(evs['real181T']['new_false']) == 31 and len(evs['real181T']['unknown']) == 36)
    for i in range(len(initial)):
        edited = copy.deepcopy(initial); edited[i]['antecedent'] = '('+edited[i]['antecedent']+') && !rst'
        check('baseline component editable '+str(i), c.adapt(dict(assertions=edited, reason='local qualification only')) == edited)
    coverage = dict(public_targets=evs['baseline']['public_targets'], historical_targets=evs['baseline']['history_targets'],
                    preserved=protected, semantic_split='Previous clock accepted TLAST versus separated completion; same count-carryover root defect, not two independent bugs.',
                    shared_guards='All correct applicable samples of both RTL revisions, triggers, unknown rejection and independent transaction reference.',
                    extra_history_guard='Six previously detected adjacent-frame targets; local replacement loses all six while O passes.',
                    no_new_exposure=True, H_R_equivalent=True,
                    inference='Structural distinction exists but is already tested; not a reason to repeat the same stopped pilot.')
    dump('candidate_matrix', matrix); dump('coverage_difference', coverage)
    native_logs = sorted(p for p in reads if p.name == 'execute.log')
    unique_rows = sum(sum(line.startswith('TRACE ') for line in p.read_text().splitlines()) for p in native_logs)
    decision = dict(action='STOP_NO_NEW_QUALIFIED_PILOT', inventory_entries=len(matrix),
                    new_qualified_candidates=0, reason='No new candidate/mechanism simultaneously has retained prior detections, a current miss, editable properties, clean legality/unknown guards and new substantive public/history scope.',
                    no_model_request_sealed=True, new_accepted_versions=0, new_independent_tests=0,
                    conditional_recovery=dict(numerator=0, denominator=0, estimate=None),
                    H_R='equivalent; added history checking only', search_576_negative_unchanged=True,
                    reentry='A newly documented development candidate/mechanism satisfying all criteria, not a predicate deletion or reuse of a stopped baseline. Independently qualify any new RTL interface before sealing a bounded pilot.',
                    limits='Closed existing-development audit, not proof no qualifying candidate exists anywhere. No new upstream search or exhaustive semantic enumeration.')
    dump('decision', decision)
    dump('cost', dict(model_calls=0, tokens=0, native_compiles=0, native_executions=0, formal_queries=0,
                     unique_archived_native_logs=len(native_logs), unique_raw_trace_rows=unique_rows,
                     repeated_frame_evaluation_sample_visits=sum(len(x['trace']) for ev in evs.values() for x in ev['evidence'].values())))
    dump('checks', checks)
    report = '''# research182 本地资格审计

结论：**当前固定开发清单中没有新增合格候选；停止，不封存新模型先导、不申请调用。** 这不证明其他材料中永远不存在区分机会。

C组公共生成接口、嵌套采样格式、模型参数与原生接受实现已锁定哈希。没有将C成功SVA写入公共接口或模型请求。独立测试及混合结果报告被读取保护排除；仅复核开发原生日志。

固定清单57条：继承43条开发入口/提案，4个原始历史诊断，7个本地控制候选和3个后续真实开发提案。条目不是57个独立Bug，重复、旧失败和手写对照均保留。完整排除理由见candidate_matrix.json。

|frame_len候选|当前检出/2|历史检出/6|合法误报|关键unknown|结论|
|---|---:|---:|---:|---:|---|
'''
    for v in matrix:
        if v['id'] in ('baseline','replacement','real179','real181C','real181T'):
            report += f"|{v['id']}|{v['current_detected']}|{v['historical_detected']}|{v['false_alarms']}|{v['critical_unknown']}|{'; '.join(v['reason'])}|\n"
    report += '''
原部分基线仍有6个旧检出、2个当前漏报，性质可编辑，公共/历史按真实输入完成是否相邻区分。替换控制O接受、H拒绝，失去6个旧检出。这只是已经存在的本地结构资格，不能因C成功再重复同一基线寻找退化。

C在开发集没有待修目标；179及T有合法误报，T另有关键unknown，不是“同时保住旧保护并存在新漏报”的合格初始候选。不能删去C保护制造缺口。pipeline保持性质没有旧目标检出；不能把同一次丢失的帧边界和排空症状拆成新旧机制。其他继承条目仍有同基线、白名单区分、语义目标空间耗尽或来源/见证不足等原限制。

本轮未改变性质、接受规则或旧结果。research181独立批次仍保持独立。条件恢复0/0、不可估计；H/R等价，仅能研究增加历史检查的作用。576次搜索负结果保持有效。

后续只有出现新的开发候选/失效机制并通过上述资格，才重新封存有界先导；当前不追加调用。本审计未扩大上游案例范围，未声称穷举仓库全部候选。

复核（输出目录必须不存在）：
```powershell
wsl -- python3 scripts/research182_development_qualification.py --out deliverables/research182_recheck
```
'''
    report += f'\n本轮{len(checks)}项检查通过，复核{len(native_logs)}份不同原生日志、{unique_rows}条原始采样；新模型/编译/执行/形式化调用均0。\n'
    (out/'SUMMARY.md').write_text(report, encoding='utf-8')
    bindings = {str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in sorted(reads)}
    bindings[str(Path(__file__).resolve().relative_to(ROOT)).replace('\\','/')] = sha(Path(__file__))
    dump('source_bindings', bindings)
    dump('read_audit', dict(read_paths=sorted(str(p.relative_to(ROOT)) for p in reads), blocked_paths=blocked,
                           successful_C_candidate_read_locally=True, successful_C_candidate_exported_to_generation=False,
                           independent_contents_read=False, network_calls=0, child_processes=0))
    dump('seal', {p.name:sha(p) for p in out.iterdir() if p.is_file()})
    print(json.dumps(dict(decision=decision['action'],checks=len(checks),inventory=len(matrix),native_logs=len(native_logs),raw_rows=unique_rows)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    audit(parser.parse_args().out.resolve())
