"""Local attribution audit and a fixed-version supplemental-test checklist.

No model, compiler, simulator or candidate editing. Old independent results
remain immutable; their reuse for this design is explicitly development use.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
from pathlib import Path
import time

import research17_loop as loop
import research32_runtime as extension
from research15_evidence import epoch_map, marker_map, paired_ledger, merge_ledgers
from research68_result_audit import raw_replay

ROOT, read, dump = loop.ROOT, loop.read, loop.dump
MATRIX = ROOT / 'deliverables/research127_fifo_matrix_20261025_r01'
FIXED = ROOT / 'deliverables/research69_pilot_20261024_r01'


def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p): return p.relative_to(ROOT).as_posix()


def classify_zero(checks, violations, later):
    if later: return 'violation_observed_but_after_first_epoch_violation'
    if violations: return 'unresolved_violation_not_confirmed_in_ledger'
    if checks: return 'obligation_exercised_without_target_violation'
    return 'applicability_condition_not_activated_in_observed_samples'


def audit(out):
    start = time.perf_counter(); out.mkdir(parents=True, exist_ok=False)
    bindings = {}; checks = []; raw_count = 0
    def bind(p): bindings[rel(p)] = digest(p)
    # Fix using development acceptance, BEFORE examining any matrix cell.
    candidate = read(FIXED / 'core/frozen_candidate.json')
    decision = read(FIXED / 'core/v0/decision.json')
    assert decision['accepted'] and decision['ordinary_accepted'] and decision['history']['accepted']
    assert decision['history']['counts']['after']['detections'] == 214
    assert loop.sha(candidate) == read(FIXED / 'core/freeze.json')['candidate_sha256']
    for p in (FIXED / 'core/frozen_candidate.json', FIXED / 'core/freeze.json', FIXED / 'core/v0/decision.json'):
        bind(p)
    dump(out / 'fixed_version.json', dict(candidate_path=rel(FIXED / 'core/frozen_candidate.json'),
        candidate_sha256=loop.sha(candidate), file_sha256=digest(FIXED / 'core/frozen_candidate.json'),
        selection='Existing research69 pilot development acceptance and105-history gate, not best holdout score.',
        development_decision=rel(FIXED / 'core/v0/decision.json'), historical_detections=214,
        selected_before_cell_audit=True, no_assertion_change=True))
    # Source files and schema are locked; do not retroactively alter the matrix.
    for name,h in read(MATRIX / 'bindings.json').items(): assert digest(ROOT / name) == h, name
    for name in ('matrix.json','versions.json','bindings.json'): bind(MATRIX / name)
    for i,(args, expected) in enumerate([((1,0,0),'obligation_exercised_without_target_violation'),
        ((0,0,0),'applicability_condition_not_activated_in_observed_samples'),
        ((1,2,2),'violation_observed_but_after_first_epoch_violation'),
        ((1,2,0),'unresolved_violation_not_confirmed_in_ledger')]):
        assert classify_zero(*args) == expected; checks.append('classifier_fixture_' + str(i))
    cells = read(MATRIX / 'matrix.json'); versions = read(MATRIX / 'versions.json')
    zero_cells, failures, later_groups, fixed_cells, batch_reports = [], [], [], [], []
    with extension.installed():
        for version in versions:
            tag = version['version']; folder = ROOT / 'deliverables' / tag / 'independent'
            split = read(folder / 'split.json'); combined = read(folder / 'combined.json')
            cand = read(ROOT / version['candidate_file']); assert loop.sha(cand) == version['candidate_hash']
            index = {}; counters = defaultdict(Counter); valid_controls = {}; records = {}; reconstructed = []
            for cohort, key in (('boundary','boundary_cases'), ('drain','drain_cases')):
                selected = split[key]
                raw_count += raw_replay(folder / cohort, selected, cand, checks)
                for i, case in enumerate(selected):
                    loc = folder / cohort / f'case_{i}'
                    a, b = (read(loc / mode / 'replay.json') for mode in ('correct',case['mode']))
                    index[case['id']] = case
                    records[case['id']] = dict(correct=a, faulty=b, directory=loc)
                    reconstructed.append(paired_ledger(a,b,case['id']))
                    for mode in ('correct',case['mode']):
                        for name in ('replay.json','execute.log'): bind(loc / mode / name)
                    epochs = epoch_map(b['trace']); first = {}
                    for v in b['oracle']['violations']:
                        ep = epochs[v['cycle']]; first[ep] = min(first.get(ep,v['cycle']),v['cycle'])
                    for ob in loop.model.SPECS:
                        key_cell = (case['depth'],case['pipeline'],ob); co = counters[key_cell]
                        co['correct_applicable_checks'] += sum(c['obligation']==ob for c in a['oracle']['checks'])
                        co['faulty_applicable_checks'] += sum(c['obligation']==ob for c in b['oracle']['checks'])
                        co['raw_violations'] += sum(c['obligation']==ob for c in b['oracle']['violations'])
                        co['scenario_count'] += 1
                        co['cancelled_transactions'] += len(a['oracle']['cancelled'])
                    valid_controls[case['id']] = (a['oracle']['legality']=='legal' and not a['oracle']['violations']
                        and not a['oracle']['unknown'] and not a['native']['failures'])
            rebuilt = merge_ledgers(reconstructed)
            for row in rebuilt['ledger']: row['split']='independent_test'
            assert rebuilt == combined['group'], tag
            checks.append(tag + '/raw_ledger_and_exclusions_exact')
            info = loop.inspect(rebuilt['ledger'])
            # Bind every later unknown to its actual independent oracle event
            # and earlier event in the SAME reset epoch. Do not upgrade detection.
            lg = defaultdict(lambda:dict(count=0, examples=[]))
            for ex in rebuilt['exclusions']:
                rr = records[ex['scenario_id']]; b = rr['faulty']; epochs = epoch_map(b['trace'])
                epoch = epochs[ex['cycle']]
                earlier = [v for v in b['oracle']['violations'] if epochs[v['cycle']]==epoch and v['cycle'] < ex['cycle']]
                assert earlier and ex['oracle_violation'] in b['oracle']['violations']
                boundary = min(v['cycle'] for v in earlier)
                first_ob = sorted({v['obligation'] for v in earlier if v['cycle']==boundary})
                case = index[ex['scenario_id']]
                key = (case['depth'],case['pipeline'],ex['obligation'],case['mode'],tuple(first_ob))
                group = lg[key]; group['count'] += 1
                if len(group['examples']) < 2:
                    group['examples'].append(dict(scenario=ex['scenario_id'],first_cycle=boundary,
                        later_cycle=ex['cycle'],epoch=epoch,oracle_violation=ex['oracle_violation'],
                        source=rel(rr['directory'] / case['mode'] / 'replay.json')))
            for (d,p,ob,mode,first),value in lg.items():
                later_groups.append(dict(version=tag,depth=d,pipeline=p,obligation=ob,mode=mode,
                    first_obligations=list(first),classification='same_obligation_after_first' if ob in first else 'different_obligation_after_first',
                    causal_conclusion='unknown_not_new_confirmed_gap', **value))
            for cell in [c for c in cells if c['version']==tag]:
                key=(cell['depth'],cell['pipeline'],cell['obligation']); co=counters[key]
                detail=dict(version=tag,candidate_hash=cell['candidate_hash'],depth=cell['depth'],pipeline=cell['pipeline'],
                    obligation=cell['obligation'],matrix_status=cell['status'],observed=dict(co),
                    target_exposure=cell['actual_target_exposure'],later_unknown=cell['later_attribution_unknown'],
                    modes=sorted({c['mode'] for c in index.values() if (c['depth'],c['pipeline'])==key[:2]}),
                    design_applicability='supported_obligation_for_this_FIFO_configuration; sample conditions are conditional',
                    source=rel(folder / 'combined.json'))
                if cell['status']=='not_exposed':
                    detail['classification']=classify_zero(co['correct_applicable_checks']+co['faulty_applicable_checks'],co['raw_violations'],cell['later_attribution_unknown'])
                    detail['not_a_confirmed_assertion_miss']=True
                    zero_cells.append(detail)
                if tag == FIXED.name: fixed_cells.append(detail)
                if cell['status']=='failed':
                    events=[]
                    for kind in ('misses','false_positives','unknown'):
                        for eid in cell['evidence'][kind]:
                            row=info['rows'][eid]; rr=records[row['scenario_id']]; b=rr['faulty']; a=rr['correct']
                            c=row['cycle']; samples={t['cycle']:t for t in b['reference_trace']}
                            prev,now=samples.get(c-1),samples[c]
                            target=[v for v in b['oracle']['violations'] if v['cycle']==c and v['obligation']==row['obligation']]
                            assert kind!='misses' or (target and valid_controls[row['scenario_id']])
                            nas=row['native']['assertions']; triggered=[n['id'] for n in nas if n['trigger']]
                            reason='triggered_but_insufficient' if triggered else 'required_check_untriggered'
                            if kind=='misses' and row['obligation']=='stall_stability':
                                assert prev and prev['mvalid'] and not prev['mready'] and not prev['rst'] and not now['rst']
                                assert not now['mvalid'] or now['mdata']!=prev['mdata']
                            events.append(dict(evidence_id=eid,kind=kind,classification=reason,
                                scenario=row['scenario_id'],mode=index[row['scenario_id']]['mode'],
                                obligation=row['obligation'],anchor_cycle=c-1,check_cycle=c,anchor=prev,check=now,
                                native=nas,correct_control_legal_and_clean=valid_controls[row['scenario_id']],
                                independent_violation=target,
                                sample_binding=rel(rr['directory'] / index[row['scenario_id']]['mode'] / 'replay.json'),
                                source_properties=[dict(id=a['id'],property=a['property']) for a in cand['assertions'] if row['obligation'] in a['obligations']]))
                    failures.append(dict(**detail,events=events,reason_counts=dict(Counter(e['classification'] for e in events))))
            batch_reports.append(dict(version=tag,scenarios=len(index),ledger_rows=len(rebuilt['ledger']),later_unknown=len(rebuilt['exclusions'])))
            print('AUDIT129_BATCH',tag,'raw_records',raw_count,flush=True)
    assert len(zero_cells)==162 and len(failures)==10
    assert len(fixed_cells)==20
    dump(out / 'unexposed_cells.json',zero_cells); dump(out / 'failed_cells.json',failures)
    dump(out / 'later_unknown_groups.json',later_groups); dump(out / 'fixed_version_cells.json',fixed_cells)
    dump(out / 'batch_audit.json',batch_reports)
    # The audit is now used to design future supplemental tests. Protect old
    # results, but explicitly mark these inputs as seen development from here on.
    used={}; input_hashes=set()
    for version in versions:
        path=ROOT / 'deliverables' / version['version'] / 'independent/split.json'; sp=read(path)
        used[rel(path)]=digest(path)
        input_hashes.update(loop.sha(c['rows']) for c in sp['boundary_cases']+sp['drain_cases'])
    dump(out / 'development_promotion.json',dict(reason='Used to classify gaps and design supplemental tests; future independence excluded.',
        archived_results_preserved=True,inputs=used,input_hashes=sorted(input_hashes),
        effective_scope='All18 audited batches for future audit-driven campaigns; historical independent-at-the-time claims unchanged.'))
    make_checklist(out,fixed_cells)
    for name,h in bindings.items(): assert digest(ROOT / name)==h,name
    for name,h in read(MATRIX / 'bindings.json').items(): assert digest(ROOT / name)==h,name
    dump(out / 'source_bindings.json',bindings)
    totals=dict(passed=True,checks=len(checks),raw_native_records_reaudited=raw_count,
        matrix_cells=360,unexposed_cells=len(zero_cells),unexposed_classifications=dict(Counter(c['classification'] for c in zero_cells)),
        failed_cells=len(failures),confirmed_missed_points=sum(len(f['events']) for f in failures),
        distinct_failed_candidate_hashes=len({f['candidate_hash'] for f in failures}),
        miss_mechanisms=sorted({e['mode'] for f in failures for e in f['events']}),
        miss_reason_counts=dict(sum((Counter(f['reason_counts']) for f in failures),Counter())),
        later_unknown_observations=sum(g['count'] for g in later_groups),
        later_unknown_classes=dict(sum((Counter({g['classification']:g['count']}) for g in later_groups),Counter())),
        fixed_version=loop.sha(candidate),fixed_unexposed_cells=sum(c['matrix_status']=='not_exposed' for c in fixed_cells),
        fixed_failed_cells=sum(c['matrix_status']=='failed' for c in fixed_cells),
        raw_files_hash_checked=len(bindings),wall_seconds=time.perf_counter()-start,
        model_calls=0,native_executions=0,assertion_edits=0,new_independent_tests=0,unknowns_promoted_to_pass=0)
    dump(out / 'audit.json',totals); dump(out / 'checks.json',checks)
    lines=['# FIFO 未曝光与失败归因审计', '',
        '仅本地只读审计及补测设计：模型0、仿真0、断言修改0、新独立验收0。旧结果与冻结版本保持不变。', '',
        f'复核18批、360个参数—义务单元、{raw_count}份原生执行记录；重新解析日志、事务参考判定、采样、原生触发/失败和全部账本/排除记录。', '',
        '## 未曝光不是已经确认的漏报', '',
        '|分类|单元数|', '|---|---:|']
    lines += [f'|{k}|{v}|' for k,v in totals['unexposed_classifications'].items()]
    lines += ['', 'Depth2/Pipeline0和Depth4/Pipeline1批次只配置drop尾部丢失测试；四项其他义务没有对应首违例。Depth4/Pipeline2排空违例发生在更早错误之后，保留归因unknown。不能将这些参数上的义务判为设计不适用，也不能用SVA触发数代替独立义务适用检查。', '',
        '## 失败与后续归因', '',
        f'10个失败单元来自{totals["distinct_failed_candidate_hashes"]}个冻结哈希，合计{totals["confirmed_missed_points"]}个有限漏报点；重复批次不是独立Bug。故障机制：'+', '.join(totals['miss_mechanisms'])+'。',
        '原生原因分布：'+str(totals['miss_reason_counts'])+'。逐点起始/检查采样、真实属性及正确侧对照见failed_cells.json。',
        f'全部{totals["later_unknown_observations"]}条后续归因记录均绑定到同复位区间更早的真实义务违例；分类{totals["later_unknown_classes"]}。这是位置归因，不建立新的因果检出，全部仍为unknown。', '',
        '## 固定补测对象', '',
        f'research69冻结哈希 `{loop.sha(candidate)}`；依据开发目标+105历史门控（214个检出保留）固定，不按本轮独立成绩重新选优。',
        '该版本当前矩阵20单元：9未曝光、0失败。补测清单见SUPPLEMENTAL_TESTS.md；不会拿失败的另一哈希替换这个版本，也不会覆盖旧失败。',
        '本轮把参与归因和补测设计的18批输入登记为未来开发数据；旧独立结果保持历史事实，今后不能再次用作未见验收。新的独立测试须在补测/修改结束、最终版本冻结后另行生成。', '',
        '复核：', '```powershell', 'wsl -- python3 scripts/research129_fifo_gap_audit.py --out deliverables/research129_fifo_gap_audit_NEW', '```']
    (out / 'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('AUDIT129',totals,flush=True)


def make_checklist(out,cells):
    tasks=[]
    base=dict(fixed_candidate_sha256=read(out/'fixed_version.json')['candidate_sha256'],
        seed_set=[12907,12919],stage='planned_development_supplement_not_executed',
        no_model_calls=True,no_assertion_edit=True,
        acceptance='Same legal accepted-input streams; fixed control satisfies obligation; fault violates confirmed obligation at first event in epoch; actual native trigger and failure at required edge. Missing exposure or unknown never passes.')
    for depth,pipeline in ((2,0),(4,1)):
        defs=[('order_payload','corrupt','至少一个输入实际握手接受后输出；错误数据为该复位区间首违例'),
              ('order_payload','duplicate_payload','四个唯一数据已实际接受；第4个错误重复第3个，确认队列对应'),
              ('no_unsolicited_output+reset_cancellation','reset_residue','接受并暂存唯一数据，背压时复位取消；复位释放后不再输入，旧数据被接受时同时曝光两项'),
              ('stall_stability','stall_glitch','前周期valid=1且ready=0；当前数据改变，分别保留合法跨周期对照'),
              ('stall_stability','valid_withdraw_stalled','短背压持续阶段撤销valid，数据保持；请求呈现不代替接受'),
              ('stall_stability','valid_withdraw_release','短背压后ready恢复边界撤销valid；检查前周期触发与本周期要求'),
              ('stall_stability','long_valid_withdraw_stalled','至少8个已呈现输出的连续背压周期后撤销valid'),
              ('stall_stability','long_valid_withdraw_release','至少8个背压周期后的ready恢复边界撤销valid')]
        for ob,mode,recipe in defs:
            tasks.append(dict(id=f'd{depth}p{pipeline}_{mode}',depth=depth,pipeline=pipeline,
                obligations=ob.split('+'),mode=mode,recipe=recipe,role='paired_target',**base))
        tasks.append(dict(id=f'd{depth}p{pipeline}_legal_reset_cancel',depth=depth,pipeline=pipeline,
            obligations=['reset_cancellation','stall_stability','no_unsolicited_output'],mode='correct',role='legal_control',
            recipe='输出背压中复位，取消旧事务后不输出；跨复位的保持要求被取消，新epoch握手另行对应',**base))
    for family in ('isolated_tail','continuous_tail','parked_tail','reset_then_tail','legal_three','reset_cancels_tail'):
        tasks.append(dict(id='d4p2_'+family,depth=4,pipeline=2,obligations=['drain_no_loss'],mode='drop',
            role='legal_control' if family in ('legal_three','reset_cancels_tail') else 'paired_target',
            recipe='复用research29家族逻辑但显式支持Depth4/Pipeline2；目标为最后第4个已接受输出被隐藏，不能提前出现顺序错误；最终至少18个真实ready=1且input-valid=0周期；合法对照应排空或复位取消。',
            implementation_status='existing_generator_needs_explicit_parameter_option_without_changing_old_defaults',**base))
    dump(out / 'supplemental_tests.json',dict(protocol_status='checklist_only_not_executed_not_an_independent_result',
        tasks=tasks,minimum_confirmed_exposure='Each target task/seed at least one first-attributable violation per named obligation; each legal control zero oracle/native failure.',
        stop='Any invalid stimulus, fixed-side violation, sampling failure or attribution unknown stops that cell; record failure and do not change candidate or oracle.',
        budget=dict(seeds=2,designs=len(tasks),scenario_definitions=2*len(tasks),max_native_replays=4*len(tasks),
                    parameter_builds=3,smoke_runs_separate=3,model_calls=0),
        isolation='All tasks are development after current audit. Future independent inputs exclude all promoted hashes and all supplemental rows; no claim old tests remain unseen.'))
    lines=['# 固定research69版本的补测清单（本轮不执行）', '',
        '冻结哈希：`'+base['fixed_candidate_sha256']+'`。所有项目为开发补测，不能直接称新独立验收。',
        '对应当前9个未曝光单元：Depth2/Pipeline0、Depth4/Pipeline1各4义务，以及Depth4/Pipeline2排空。另检查背压持续/解除、短/长时段及复位合法取消。', '',
        '|参数|项目|义务|构造与曝光要求|','|---|---|---|---|']
    for t in tasks: lines.append(f'|{t["depth"]}/{t["pipeline"]}|{t["id"]}|{", ".join(t["obligations"])}|{t["recipe"]}|')
    lines += ['', f'预定种子12907、12919；{len(tasks)}种设计，共{len(tasks)*2}个场景定义。若每项均保留正确/故障侧，至多{len(tasks)*4}次回放，3个参数构建，编译冒烟另计。没有运行这些场景，不承诺必然曝光或通过。',
        '现有research29生成器的默认参数含4/1、不含4/2；后续应新增显式参数入口，保持历史默认不变。本轮仅列出该实现前置条件。',
        '每项目记录实际接受/响应/取消周期、正确/故障侧参考队列、原生前件起始和后件检查周期、首违例与归因状态。只呈现请求不计为事务，波形不同不直接计为Bug。',
        '后续unknown的处理：分别构造单故障、首违例或复位隔离场景重新验证，不能删除旧unknown或放宽归因规则；额外重复/丢失事件需要单独归因，不能直接宣称原级联已解决。',
        '失败时保留冻结版本并停止对应单元；本清单不授权模型修改。若将失败用于细化，完成历史回放后重新冻结，再用完全新批次独立验收。',
        '不覆盖全参数空间或内部RAM满状态：当前参数为2/0、4/1、4/2（另有归档8/2）；外部背压不等于已证明内部full，FIFO流水响应不是无条件固定延迟。']
    (out/'SUPPLEMENTAL_TESTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True)
    audit(ap.parse_args().out.resolve())
