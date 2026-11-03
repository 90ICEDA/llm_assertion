"""Read-only audit of sealed original-RTL runs; no model or simulator calls."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import research159_history_screen as base

ROOT = base.ROOT
P159 = ROOT / 'deliverables/research159_history_prepare_20261028_r01'
P160 = ROOT / 'deliverables/research160_history_prepare_20261028_r01'
R159 = ROOT / 'deliverables/research159_history_native_20261028_r01'
R160 = ROOT / 'deliverables/research160_history_native_20261028_r01'
PUBLIC = {'ibex54': {'li_hint', 'lui_hint'},
          'axis_adapter_keep': {'ignored_keep_zero', 'ignored_keep_alternating'},
          'axis_fifo_pause': {'pause_first_stall'}}


def run(out):
    out.mkdir(parents=True, exist_ok=False)
    checks = []
    consumed = {}

    def check(label, value):
        checks.append({'check': label, 'passed': bool(value)})
        if not value:
            raise AssertionError(label)

    def read(p):
        consumed[base.rel(p)] = base.sha(p)
        return base.read(p)

    for p in (P159, P160):
        base.verify(p)
        for name in base.read(p / 'seal.json'):
            consumed[base.rel(p / name)] = base.sha(p / name)
        check('prepared seal and code bindings ' + p.name, True)
    source = read(P159 / 'source_manifest.json')
    cached = read(base.ibex.OLD / 'downloads_retry.json')
    for s in source['sources']:
        p = ROOT / s['path']
        check('source hash ' + s['path'], base.sha(p) == s['sha256'])
        if s['case'] == 'ibex54':
            matches = [x for x in cached if x['revision'] == s['commit'] and
                       x['url'].endswith('/' + p.name)]
            check('archived immutable download ' + s['path'],
                  len(matches) == 1 and matches[0]['sha256'] == s['sha256'])
        else:
            check('original Git blob ' + s['path'],
                  base.git('show', s['commit'] + ':' + s['source_path']) == p.read_bytes())
    for case, fix in base.FIXES.items():
        parents = {s['commit'] for s in source['sources'] if s['case'] == case and s['revision'] == 'before'}
        check('actual parent ' + case, parents == {base.git('rev-parse', fix + '^').decode().strip()})
    check('Ibex original patch exactly reproduces fixed file', source['ibex_patch_exact'])

    all_runs = []
    costs = {'model_calls': 0, 'model_tokens': 0, 'formal_calls': 0,
             'native_compiles': 0, 'native_executions': 0,
             'compile_wall_seconds': 0.0, 'execute_wall_seconds': 0.0,
             'cost_in_currency': None, 'cost_in_currency_reason': 'No monetary meter for local compute'}
    for runroot in (R159, R160):
        for r in read(runroot / 'results.json')['results']:
            n = r['native']
            costs['native_compiles'] += 1
            costs['native_executions'] += n['native_simulation_calls']
            costs['compile_wall_seconds'] += n['compile']['wall_seconds']
            costs['execute_wall_seconds'] += n['execute']['wall_seconds']
            folder = runroot / r['case'] / ('p' + str(r['parameter'])) / r['revision']
            values = base.trace(folder)
            check('saved TRACE matches raw log ' + base.rel(folder), values == read(folder / 'trace.json'))
            consumed[base.rel(folder / 'execute.log')] = base.sha(folder / 'execute.log')
            consumed[base.rel(folder / 'compile.log')] = base.sha(folder / 'compile.log')
            consumed[base.rel(folder / 'wave.vcd')] = base.sha(folder / 'wave.vcd')
            oracle = read(folder / 'oracle.json')
            if r['case'] == 'ibex54':
                vectors = read(P159 / 'ibex54/vectors.json')
                reconstructed = []
                for v, s in zip(values, vectors):
                    check('Ibex sampled instruction ' + str(v['sample']) + r['revision'], v['instr'] == s['instruction'])
                    expected = base.ibex.oracle(v['instr'])
                    for k in ('illegal', 'compressed', 'decoded'):
                        if k == 'decoded' and expected['illegal']:
                            continue
                        reconstructed.append(dict(sample=v['sample'], family=s['family'], obligation=k,
                                                  expected=expected[k], observed=v[k], passed=expected[k] == v[k]))
                check('independent ISA rejudgment ' + r['revision'], reconstructed == oracle['checks'])
            else:
                stimulus = read(folder / 'actual_stimuli.json') if runroot == R160 else read(P159 / r['case'] / 'stimuli.json')
                fresh = base.oracle_axis(values, stimulus, r['parameter'] if r['case'] == 'axis_adapter_keep' else 8)
                check('independent port queue rejudgment ' + base.rel(folder), fresh == oracle)
            # Correlate every native assertion failure with independently adjudicated scope.
            aliases = {'legality': 'illegal', 'expansion': 'decoded', 'compressed': 'compressed',
                       'hold_valid': 'hold_valid', 'hold_payload': 'hold_payload'}
            for f in n['failures']:
                pos = re.search(r'(sample|cycle)=(\d+)', f['detail'])
                check('native/oracle failure agreement ' + base.rel(folder) + str(f), bool(pos) and
                      any(x.get(pos[1]) == int(pos[2]) and x['obligation'] == aliases[f['id']] for x in oracle['failures']))
            check('native compile completed ' + base.rel(folder), n['compile_status'] == 'passed')
            check('native execution completed ' + base.rel(folder), n['execution_status'] == 'completed')
            all_runs.append(dict(root=base.rel(runroot), case=r['case'], parameter=r['parameter'],
                                 revision=r['revision'], oracle_failures=len(oracle['failures']),
                                 input_legal=oracle['legality_confirmed'], native_failures=len(n['failures']),
                                 native_trigger_status=n['trigger_status'],
                                 native_property_status=n['property_status']))
    check('precommitted local execution budget', costs['native_compiles'] == costs['native_executions'] == 18)

    pairs = []
    coverage = []
    witnesses = []
    for case, params, rr in [('ibex54', [0], R159), ('axis_adapter_keep', [8, 32], R160), ('axis_fifo_pause', [0, 1], R160)]:
        for parameter in params:
            dirs = {rev: rr / case / ('p' + str(parameter)) / rev for rev in ('before', 'after')}
            traces = {rev: read(dirs[rev] / 'trace.json') for rev in dirs}
            oracles = {rev: read(dirs[rev] / 'oracle.json') for rev in dirs}
            input_keys = ('sample', 'instr') if case == 'ibex54' else ('cycle', 'rst', 'sv', 'sd', 'sk', 'sl', 'mr', 'pause')
            differences = [(a.get('cycle', a.get('sample')), k) for a, b in zip(traces['before'], traces['after']) for k in input_keys if a[k] != b[k]]
            check('identical actual inputs ' + case + str(parameter), not differences and len(traces['before']) == len(traces['after']))
            check('both input protocols legal ' + case + str(parameter), all(x['legality_confirmed'] for x in oracles.values()))
            check('repair fail/pass ' + case + str(parameter), oracles['before']['failures'] and not oracles['after']['failures'])
            pairs.append(dict(case=case, parameter=parameter, same_actual_input=True, legal=True,
                              before_failures=len(oracles['before']['failures']), after_failures=0,
                              before_native=next(x for x in all_runs if x['root'] == base.rel(rr) and x['case'] == case and x['parameter'] == parameter and x['revision'] == 'before'),
                              paths={rev: base.rel(p) for rev,p in dirs.items()}))
            for rev, oracle in oracles.items():
                buckets = {}
                for c in oracle['checks']:
                    key = (c['family'], c['obligation'])
                    bucket = buckets.setdefault(key, dict(exposed_checks=0, failures=0))
                    bucket['exposed_checks'] += 1
                    bucket['failures'] += not c['passed']
                for (family, obligation), counts in sorted(buckets.items()):
                    coverage.append(dict(case=case, parameter=parameter, revision=rev, family=family,
                                         scope='public' if family in PUBLIC[case] else 'history',
                                         obligation=obligation, **counts))
                if case != 'ibex54':
                    ev = oracle['events']
                    coverage.append(dict(case=case, parameter=parameter, revision=rev,
                                         event_counts=dict(Counter(e['kind'] for e in ev)),
                                         reset_cancelled_accepted_bytes=oracle['reset_cancelled_bytes']))
            seen = set()
            for f in oracles['before']['failures']:
                key = (f['family'], f['obligation'])
                if key in seen:
                    continue
                seen.add(key)
                pos = f.get('sample', f.get('cycle'))
                window = slice(max(0, pos-1), pos+2)
                witnesses.append(dict(case=case, parameter=parameter, violation=f,
                                      dedup_note='One example per family/obligation/config; not independent Bug counts. Adapter drain/order errors can follow the same TKEEP loss.',
                                      before=traces['before'][window], after=traces['after'][window],
                                      transaction_events=[e for e in oracles['before'].get('events', []) if
                                                          e.get('cycle', e.get('accepted_cycle', -1)) <= pos],
                                      corresponding_fixed_checks=[c for c in oracles['after']['checks'] if
                                                                  c.get('sample', c.get('cycle')) == pos and c['obligation'] == f['obligation']],
                                      fixed_entire_trace_failures=0))

    matrix = []
    diagnostic_sets = {
        'ibex54': dict(existing='Handwritten legality/expansion/compressed diagnostic assertions, full oracle checks',
                       retained='Native legality detects 20 old-version samples (8 public, 12 history); expansion/compressed have no original target violation in this batch.',
                       gap='No public target miss in this full diagnostic set. A partial genuine candidate with retained protection and a current gap has not been established.'),
        'axis_adapter_keep': dict(existing='Handwritten hold_valid + hold_payload; no generated partial baseline on this module',
                       retained='Stall triggers observed, but these two properties detect no old-version TKEEP target violation in either width configuration.',
                       gap='TKEEP/byte-preservation misses exist; no measured prior target detection by the current diagnostic set. Legal transactions alone do not establish retained violation detection.'),
        'axis_fifo_pause': dict(existing='Handwritten hold_valid + hold_payload; no generated partial baseline on these exact RTL hashes',
                       retained='hold_valid detects the original pause-first-stall violation in each pipeline configuration.',
                       gap='This exposed target is already detected; other sampled families show no original target violation. No simultaneous current miss and retained target protection is established.')}
    for case in PUBLIC:
        matrix.append(dict(case=case, source_and_original_witness='qualified_in_bounded_scope',
                           editable_diagnostic_sva=True, existing_model_candidate='not_established_for_this_case',
                           common_generation_frontend='not_integrated_for_this_original_interface',
                           meaningful_non_whitelist_acceptance_discriminator='not_established',
                           history_contains_additional_legal_behaviors=True,
                           combined_partial_protection_and_current_gap=False,
                           pilot_qualified=False, decision='STOP_NO_MODEL_PILOT', **diagnostic_sets[case]))
    decision = dict(decision='STOP_NO_MODEL_PILOT', repair_cases_confirmed=3, paired_configurations_confirmed=5,
                    qualifying_partial_candidates=0, new_model_calls=0, new_accepted_model_versions=0,
                    new_independent_acceptances=0, extra_history_rejections=0,
                    conditional_recovery=dict(numerator=0, denominator=0, interpretation='not estimable'),
                    hr_limitation='Existing H/R equivalence is unchanged. New scopes are not an H-versus-R uniqueness result.',
                    search_limitation='No new fair search benchmark executed. Previous 576-query no-unique-gain result remains valid.',
                    preserved_unknown=['old stat provenance', 'new stat actual repair revision', 'original FIFO presented historical witness'],
                    next_local_gate='On an original interface, establish a genuine editable partial candidate with native historical target detections AND current misses, then validate behavioral public/history distinction without explicit instruction whitelist. Do not derive gains by disabling a complete oracle or by fixed components hiding regression.',
                    independent_data='Only development qualification inputs used; no previous independent outcome was consumed for selection. No claim of new independent validation.')
    base.dump(out / 'qualification_matrix.json', matrix)
    base.dump(out / 'paired_results.json', pairs)
    base.dump(out / 'witnesses.json', witnesses)
    base.dump(out / 'public_history_coverage.json', coverage)
    base.dump(out / 'all_runs_including_invalid_stimulus.json', all_runs)
    base.dump(out / 'costs.json', costs)
    base.dump(out / 'decision.json', decision)
    base.dump(out / 'audit_checks.json', checks)
    base.dump(out / 'consumed_development_artifacts.json', consumed)
    base.dump(out / 'source_provenance.json', source)

    lines = ['# 新历史案例本地资格筛选', '',
             '**结论：3 个原始修复案例、5 对配置的前后见证成立；本轮没有合格的防退化先导候选，停止，不申请模型调用。**', '',
             '候选在详细补丁分析与运行前固定：既有 Ibex #54，加已有 verilog-axis 完整历史中最近两项功能修复；工具兼容提交按预定规则排除。不是仓库历史的穷举筛选，也没有按机制收益挑选。全部输入是开发资格材料。', '',
             '|案例／配置|独立规格检查旧版失败点|新版失败点|诊断 SVA 的实际作用|', '|---|---:|---:|---|']
    for p in pairs:
        lines.append(f"|{p['case']} / {p['parameter']}|{p['before_failures']}|0|原生失败 {p['before_native']['native_failures']}；{p['before_native']['native_property_status']}|")
    lines += ['', '失败点不是独立 Bug 数。adapter 的 TKEEP 为空、后续顺序与排空失败可能来自同一根因；本表只确认三项修复，不将波形变体或流水参数计作多个发现。', '',
              '## 来源与范围', '',
              '- Ibex #54：原始 compressed decoder；历史下载 SHA256 与原始补丁精确复核通过。本轮四次不可变 raw URL 获取均连接失败，未宣称重新下载成功。29 个采样含重复指令，独立指令数 ' + str(len({v['instruction'] for v in base.read(P159 / 'ibex54/vectors.json')})) + '；只验证该模块和所列编码。',
              '- axis_adapter：修复 c1c3dc0b66e98a186878b32a4d65cdcd00eaa358 与直接父提交的原始 Git blobs，8→8、8→32，输入 KEEP 禁用、输出 KEEP 启用；未测试降宽。输出的字节／帧边界独立由握手队列判断，SVA 的通过不能替代该判断。',
              '- axis_fifo：修复 e493c6cdb4fd20939b7b9a613e9ab6fd7395ada2 与直接父提交，Depth=4、RAM_PIPELINE=0/1、FRAME_FIFO=0、FRAME_PAUSE=1；验证暂停不能撤销已呈现但未接受的 valid。未验证同提交的 async FIFO，也没有假定 pause_ack 必须在某固定周期响应。', '',
              '全部 5 对的实际输入逐周期一致，源端协议合法；有请求接受、输出接受、队列顺序与复位取消记录。波形、命令、日志与原生工具版本在 paired_results.json 所指目录。有限仿真不是形式化证明。', '',
              '## 公共／历史覆盖差异与先导排除', '',
              '|案例|预定公共范围|预定历史范围|为何尚不进入先导|', '|---|---|---|---|',
              '|Ibex #54|LI/LUI HINT|移位 HINT、合法／保留移位、直通|现有完整诊断集检出全部曝光目标，没有当前漏报；不能通过白名单削弱它制造机会。|',
              '|adapter|禁用 KEEP 后的零／交替 KEEP|KEEP=1 控制、复位取消|当前保持性质确有 TKEEP 漏报，但没有已检出的历史目标违例；尚不具备可丢失的目标检出保护。|',
              '|FIFO pause|首拍背压期间暂停|帧内暂停、普通传输、复位取消|现有 valid 保持性质已检出曝光缺陷；没有同时存在的未修目标。|', '',
              '上述差异按功能类别与时序定义，不按指令字白名单定义。历史有额外合法行为覆盖，可能发现未来误报，但本轮没有实际提案或非白名单对照证明它能额外拒绝。所有诊断性质可编辑，未固定组件规避退化；仍缺真实部分候选及对应模块公共生成接口。手写诊断／独立参考模型不冒充模型生成候选。', '',
              'public_history_coverage.json 逐项给出实际检查、失败和事务事件数；未出现的事件不可算曝光。尤其 adapter 8→8 为旁路，复位前未接受的数据不能计为取消已接受事务；按实际事件记录报告。', '',
              '## 保留的失败与成本', '',
              '首轮 adapter 固定周期源在背压时改变未接受数据，合法性检查拒绝；首轮原始结果完整保留，未追改。只修正测试平台为握手后推进，使用预定 18 次本地总额度中的剩余 8 次重验两项 AXI。原始 RTL、义务和 SVA 均未改。初轮 FIFO 是否合法逐条记录，不一概归为非法。',
              f"本轮模型 0、token 0、形式化 0；原生编译 {costs['native_compiles']}、执行 {costs['native_executions']}（包含首轮）；编译墙钟合计 {costs['compile_wall_seconds']:.3f}s，执行 {costs['execute_wall_seconds']:.3f}s。审计检查 {len(checks)} 项通过。未计费货币成本不可用。", '',
              '## 停止结论与下一步', '',
              '本轮新模型接受版本 0、新独立验收 0、前瞻额外拒绝 0，条件恢复仍为 **0/0，不可估计**。H/R 等价限制不变；576 次搜索无独有收益结果不变。stat 的真实修复版本、旧 stat 来源与原始 FIFO presented 见证仍 unknown。既有 FIFO 指定范围独立验收未重跑。', '',
              '下一项本地前置任务是为实际模块接口建立并原生验证“已保护历史目标＋仍漏报另一行为”的可编辑部分候选，核验非白名单公共／历史差异。只有这项成立才封存生成接口、普通／历史规则和有界预算；本轮不封存空有来源资格的模型先导。', '',
              '## 复核与运行', '',
              '以下命令从仓库根目录执行，输出目录必须尚不存在。前两条是新的原生复跑（共18次），最后一条只审计本轮已保存记录：', '',
              '```powershell',
              'wsl -- python3 scripts/research159_history_screen.py run --prepared deliverables/research159_history_prepare_20261028_r01 --out deliverables/research159_native_recheck',
              'wsl -- python3 scripts/research160_legal_source_replay.py run --prepared deliverables/research160_history_prepare_20261028_r01 --out deliverables/research160_native_recheck',
              'wsl -- python3 scripts/research161_history_qualification_audit.py --out deliverables/research161_audit_recheck',
              '```', '',
              '上游：[Ibex #54](https://github.com/lowRISC/ibex/pull/54)、[adapter 修复](https://github.com/alexforencich/verilog-axis/commit/c1c3dc0b66e98a186878b32a4d65cdcd00eaa358)、[FIFO 修复](https://github.com/alexforencich/verilog-axis/commit/e493c6cdb4fd20939b7b9a613e9ab6fd7395ada2)。']
    (out / 'SUMMARY.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    base.dump(out / 'report_seal.json', {p.relative_to(out).as_posix():base.sha(p) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(dict(checks=len(checks), pair_count=len(pairs), decision=decision['decision'], costs=costs), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    run(parser.parse_args().out.resolve())
