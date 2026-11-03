"""Development-only local discrimination audit; no dispatch or native reruns.

Closed inventory: research158's 17 entries and 12 real development proposals,
research161's three original-interface diagnostics, research162's four HINT
controls, research166's four adapter controls, and all three adapter proposals.
Old compiler-invalid duplicates are retained as provenance, not new candidates.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import sys
import research172_applicability_gate as g

q=g.q;ROOT=q.ROOT
D=ROOT/'deliverables'
A=D/'research158_development_decision_audit_20261027_r01'
B=D/'research161_history_qualification_20261028_r01'
C=D/'research162_partial_report_20261028_r01'
F=D/'research164_feasibility_20261028_r02'
P=D/'research172_applicability_prepare_20261028_r02'


def guard_reads(out):
    reads=set();blocked=[]
    def guard(event,args):
        if event in ('socket.connect','socket.getaddrinfo','subprocess.Popen'):
            raise RuntimeError('local_readonly_audit_no_network_or_process')
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        name=str(args[0]).replace('\\','/');mode=args[1]
        if '.secrets/' in name:raise RuntimeError('no_credentials')
        if '/deliverables/' not in name:return
        if isinstance(mode,str) and any(k in mode for k in 'wax+'):
            if not name.startswith(out.as_posix()+'/'):raise RuntimeError('no_old_artifact_writes')
            return
        if any(x in name for x in ('research174_','research175_','/independent','/tested_versions/',
                                   'research133_','research134_','/terminal_frozen/','/frozen/')):
            blocked.append(name);raise RuntimeError('holdout_material_denied')
        reads.add(name)
    sys.addaudithook(guard)
    return reads,blocked


def audit(out):
    out.mkdir(parents=True,exist_ok=False);reads,blocked=guard_reads(out);checks=[]
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)));assert ok,name
    def sealed(folder,name,seal='seal.json'):
        expected=q.read(folder/seal)[name];check('sealed '+q.old.rel(folder/name),q.sha(folder/name)==expected)
        return q.read(folder/name)
    # Denial tests do not open/read the independent files.
    for name in ('research174_independent_run_20261028_r01/result.json','research175_exposure_run_20261028_r01/result.json'):
        try:q.read(D/name)
        except RuntimeError as e:check('blocked '+name,str(e)=='holdout_material_denied')
        else:raise AssertionError('holdout read was permitted')
    inherited=sealed(A,'candidate_scope_matrix.json','sealed.json')
    cells=sealed(A,'cell_diagnostics.json','sealed.json')
    originals=sealed(B,'qualification_matrix.json','report_seal.json')
    hints=sealed(C,'acceptance_matrix.json','report_seal.json')
    exhaustion=sealed(F,'decision.json')
    check('fixed inherited inventory17',len(inherited)==17)
    check('all12 Ibex proposals',len(cells)==12)
    population=dict(scope='closed development inventory, not repository-wide historical enumeration',
        inherited=[v['id'] for v in inherited],ibex_proposals=[v['id'] for v in cells],
        original_diagnostics=[v['case'] for v in originals],hint_controls=[v['control'] for v in hints],
        adapter_controls=['baseline','replacement','complementary','overbroad'],adapter_real=[167,169,172],
        immutable_exclusions='No independent data; artificial-FIFO candidates retained but outside original-history interface scope; no added candidates after verdicts.')
    q.dump(out/'population_lock.json',population)
    matrix=[]
    for v in inherited:
        matrix.append(dict(id='prior_'+v['id'],parent=v['parent'],origin='prior_development_audit',source=v['source'],
            structural_partial=v['eligible_initial'],editable=v.get('all_predicates_editable'),
            current_misses=v.get('unresolved_public_misses'),existing_detections=v.get('existing_detections'),
            decision='not_new_pilot',reason=v['exclusion_reasons'] or ['same_previously_tested_behavior; only_whitelist_discriminator_in_prior_Ibex_audit'],
            evidence_level='inherited sealed development audit; not freshly rerun'))
    for v in cells:
        reason='no_current_gap_full_development_accept' if v['O'] and v['H'] else 'ordinary_already_rejects; no_extra_history_decision'
        matrix.append(dict(id='ibex_proposal_'+v['id'],parent='ibex166',origin='real_model_prior_development',
            ordinary=v['O'],historical=v['H'],reason=[reason],decision='not_new_pilot',
            public_misses=v['public_misses'],public_false_alarms=v['public_false_alarm_property_points'],
            evidence_level='inherited sealed development audit; independent outcomes not read'))
    for v in originals:
        matrix.append(dict(id='original_diagnostic_'+v['case'],parent=v['case'],origin='handwritten_diagnostic',
            structural_partial=v['combined_partial_protection_and_current_gap'],editable=True,
            reason=[v['gap']],decision='excluded_as_this_candidate',
            supersession='adapter partial controls examined separately; original diagnostic not silently upgraded'))
    for v in hints:
        matrix.append(dict(id='hint_'+v['control'],parent='ibex54',origin=v['origin'],editable=True,
            existing_detections=v['history_detected'],current_misses=v['public_total']-v['public_detected'],
            ordinary=v['ordinary_accept'],historical=v['historical_accept'],
            decision='excluded_new_full_chain',reason=['mandatory_unseen_low16_target_pools_exhausted'],
            local_discrimination=v['ordinary_accept'] and not v['historical_accept']))
    check('HINT holdout space failure preserved',not exhaustion['frozen_pilot_end_to_end_feasible'])
    scenarios=sealed(g.c.P,'scenarios.json');protected=sealed(P,'protected.json');initial=sealed(P,'initial.json')
    request=sealed(P,'request.preview.json');body=json.loads(request['messages'][1]['content'])
    protocol=sealed(P,'protocol.json')
    check('unchanged common starting candidate',body['current_assertions']==initial)
    # All components can be edited verbatim; no compiled fixture/model response created.
    for i in range(len(initial)):
        edit=copy.deepcopy(initial);edit[i]['antecedent']='('+edit[i]['antecedent']+') && !rst'
        check('component editable '+str(i),g.c.adapt(dict(assertions=edit,reason='local interface audit only'))==edit)
    evals={};raw_records=0;real=[]
    entries=[]
    for name in ('baseline','replacement','complementary','overbroad'):
        obj=sealed(g.c.P,'controls/'+name+'.json')
        entries.append((name,obj['assertions'],g.c.N/name,'handwritten_local_fixture'))
    for number in (169,172):
        run=D/f'research{number}_adapter_run_20261028_r01'
        entries.append(('real'+str(number),q.read(run/'shared/model_call/candidate.json'),run/'shared/native','real_model'))
    for name,candidate,folder,origin in entries:
        ev=g.measure(candidate,folder,scenarios,protected);evals[name]=ev
        q.dump(out/'recomputed'/f'{name}.json',ev)
        for rev in ('before','after'):
            raw_records+=len(ev['evidence'][rev]['trace'])
            n=q.read(folder/rev/'result.json')
            check(name+' '+rev+' native completed',n['compile_status']=='passed' and n['execution_status']=='completed')
        partial=bool(set(protected)-set(ev['lost'])) and bool(ev['public_missed']) and not(ev['unknown'] or ev['new_false'])
        reasons=[]
        if ev['unknown']:reasons.append('critical_unknown')
        if ev['new_false']:reasons.append('legal_false_positives')
        if not ev['public_missed']:reasons.append('no_current_public_gap')
        if len(ev['lost'])==len(protected):reasons.append('no_retained_nonfinal_baseline_protection')
        if partial:reasons.append('existing_same_partial_baseline_already_piloted; no_new_mechanism_or_candidate')
        row=dict(id='adapter_'+name,parent='axis_adapter_keep',origin=origin,structural_partial=partial,editable=True,
            ordinary=ev['ordinary'],historical=ev['history'],public_detected=len(ev['public_targets'])-len(ev['public_missed']),public_total=len(ev['public_targets']),
            history_detected=len(ev['history_targets'])-len(ev['history_missed']),history_total=len(ev['history_targets']),
            prior_retained=len(protected)-len(ev['lost']),lost=len(ev['lost']),false_positives=len(ev['new_false']),unknown=len(ev['unknown']),
            predicate_hash=g.c.signature(candidate),decision='structural_only_no_new_pilot' if partial else 'excluded_as_initial',reason=reasons,
            evidence_level='fresh local rejudgment of archived native logs; no new RTL execution')
        matrix.append(row)
        if origin=='real_model':
            archived=q.read(folder.parent.parent/'shared_decision.json');outcome=q.read(folder.parent.parent/'outcome.json')
            real.append(dict(id=name,archived_decision=archived,rejudged_O=ev['ordinary'],rejudged_H=ev['history'],
                current_rule_extra_rejection=ev['ordinary'] and not ev['history'],
                interpretation='169 retrospective new-gate diagnostic; original rejection immutable' if name=='real169' else '172 actual new-gate proposal both accepted; no recovery opportunity',
                original_outcome=outcome['status']))
    old167=q.read(D/'research167_adapter_run_20261028_r01/outcome.json')
    matrix.append(dict(id='adapter_real167',parent='axis_adapter_keep',origin='real_model',decision='excluded',
        reason=['original_interface_rejected_no_native_measurement; later parameter fix cannot retroactively accept'],
        archived_status=old167['status']))
    check('full locked inventory43',len(matrix)==43)
    baseline=evals['baseline'];replacement=evals['replacement'];complete=evals['complementary']
    check('baseline meaningful partial',len(baseline['public_missed'])==8 and not baseline['lost'] and not baseline['new_false'])
    check('nonwhitelist discriminator remains',replacement['ordinary'] and not replacement['history'] and len(replacement['lost'])==12 and not replacement['unknown'])
    check('local complementary positive control',complete['ordinary'] and complete['history'])
    check('overbroad remains rejected in ordinary',not evals['overbroad']['ordinary'] and len(evals['overbroad']['false_after'])==32)
    check('real proposals have no current-rule extra rejection',all(not x['current_rule_extra_rejection'] for x in real))
    table=baseline['obligation_evaluation']['before']['obligation_samples']
    def projection(cycles):
        return dict(Counter(ob for c in cycles for ob,s in table[c].items() if s['verdict']=='violation'))
    coverage=dict(public_targets=projection(baseline['public_targets']),historical_targets=projection(baseline['history_targets']),
        protected_ids=protected,protected_projection=projection(protected),
        semantic_discriminator='TLAST / final versus nonfinal output group; no instruction/scenario ID whitelist in predicates',
        shared_checks=['same native compilation/execution','same independent transaction reference','same unknown rejection','false alarms on ALL correct samples of BOTH RTL versions','public target detection and trigger'],
        H_addition='all historical target detection AND trigger; loss of baseline detections separately decides whether recovery is eligible',
        excluded_effect='new historical legal false positive cannot be H-only rejection under current common all-correct-sample false-positive guard',
        H_R='equivalent in fixed evidence scope; no R-over-H unique benefit',
        cycle_counts_are_not_bug_counts=True)
    check('public final8 history nonfinal12 final8',coverage['public_targets']=={'final_nonempty':8} and coverage['historical_targets']=={'nonfinal_keep':12,'final_nonempty':8})
    branch=g.c.branch('response_received',True,replacement['ordinary'],replacement['history'],len(replacement['lost']),len(replacement['new_false']),len(replacement['unknown']))
    check('fixture would qualify one recovery',branch=='history_once')
    check('actual172 stops',g.c.branch('response_received',True,True,True,0,0,0)=='stop_both_accept_no_discrimination')
    # Demonstrate retention using immutable initial state; not a model recovery.
    retention=dict(origin='local decision replay only',branch=branch,kept_candidate_hash=g.c.digest(initial),
        retained_detection_ids=protected,retained_count=len(protected),real_recovery_numerator=0,real_recovery_denominator=0)
    decision=dict(action='STOP_NO_NEW_MODEL_PILOT_SEALED',structural_discrimination=True,
        adapter_partial_baselines=1,new_qualified_behavior_or_candidate=0,
        rationale='The meaningful TLAST discriminator already qualified research172. Its new real proposal passed both rules; 169 rejudgment also passes both. Complete model candidates have no current development gap. Reopening the same baseline/seed search supplies no new scientific scope. This does not prove future model regressions impossible.',
        reentry='New development-motivated candidate/failure mechanism with editable retained protection plus a public miss, meaningful non-whitelist discriminator and feasible fresh target scope. List complete candidate pool before selection; no weakening O or using holdout outcomes.',
        seal_if_reentry='Freeze common generator, O/H rules, first-proposal/conditional-one-recovery budget and stop conditions; only then request explicit model authorization.',
        models=0,native_compiles=0,native_executions=0,formal_calls=0,raw_adapter_trace_rows_rejudged=raw_records,
        new_accepted_versions=0,new_independent_tests=0,conditional_recovery=dict(numerator=0,denominator=0,estimate=None),
        search='576-query negative result unchanged; no search expansion performed',H_R='equivalent; added history only')
    for name,obj in [('candidate_matrix',matrix),('coverage_difference',coverage),('real_proposal_decisions',real),('retention_control',retention),('decision',decision),('checks',checks)]:q.dump(out/(name+'.json'),obj)
    bound={q.old.rel(Path(p)):q.sha(Path(p)) for p in sorted(reads) if not p.startswith(out.as_posix()+'/')}
    bound[q.old.rel(Path(__file__))]=q.sha(Path(__file__))
    q.dump(out/'source_bindings.json',bound)
    q.dump(out/'read_audit.json',dict(read_paths=sorted(reads),blocked_independent_paths=blocked,
        selection_from_development_only=True,credentials_read=False,network_calls=0,processes_launched=0))
    lines=['# research176 本地区分能力审计','',
        '**结论：结构区分资格仍成立，但没有新增可用候选／行为范围支持再次开启相同先导。本轮停止，不封存新模型先导，不申请调用。** 不把“本轮不再重复”解释为证明模型不可能退化。','',
        f'固定清单共{len(matrix)}个条目：17个既有Ibex/FIFO入口、12个Ibex真实开发提案、3个原始接口诊断集、4个Ibex #54手写对照、4个adapter手写对照及3个adapter真实提案。保留重复/失效版本及排除原因；这是明确边界内的全清单，不是仓库所有历史候选的穷举。','',
        '|adapter开发候选|公共检出|历史检出|旧保护丢失|误报周期|普通/历史|','|---|---|---|---|---|---|']
    for x in matrix:
        if 'public_total' in x:
            lines.append(f"|{x['id']}|{x['public_detected']}/{x['public_total']}|{x['history_detected']}/{x['history_total']}|{x['lost']}|{x['false_positives']}|{x['ordinary']}/{x['historical']}|")
    lines += ['', '## 区分能力与局限','',
        'adapter部分基线保留12个非尾拍目标检出，并遗漏8个公共短帧尾拍目标。全部三条性质可编辑。只保留尾拍的手写对照普通接受/历史拒绝，历史额外检查确实阻止12个非尾拍检出的丢失；区分依据TLAST事务语义，不依赖样本白名单。局部拒绝分支保留原基线及12个旧检出。手写对照不算真实模型退化或恢复。',
        '公共目标8个均为尾拍；历史目标20个=12个非尾拍+8个尾拍。普通规则已经检查所有正确样本上的误报，H在此只有历史目标检出/触发的额外要求。因此不能把新增合法误报包装成H独有的拒绝作用，H/R仍等价。',
        'research169在新门控下的回顾性诊断与research172实际提案均两规则通过；前者原拒绝不追改。research167原接口失败保留。当前完整模型版本没有开发期待修目标；删除其保护或缩小公共范围来制造缺口不在本轮允许范围内。',
        'Ibex #166四个原部分入口基础资格仍成立，但既有12个提案为7个两规则通过、5个普通已拒绝；旧区分夹具依赖指令白名单，不能算新语义机会。Ibex #54非白名单部分资格成立，但原协议强制的新低16位目标空间已耗尽。原始FIFO pause缺少同时存在的当前漏报；9个人工FIFO入口不计入本轮真实历史接口范围，不据此否认其以往有限验收。','',
        '## 决定与交付','',
        '不修改候选、普通规则、提示或历史结果；不准备重复调用请求。若要重入，先在新增开发案例/失效机制中建立可编辑旧保护＋当前漏报＋实质区分对照和可执行的新测试范围，再封存小预算先导。无合格新范围就停止；不追求必得正收益。',
        f'本轮重判{raw_records}条adapter原生开发采样，{len(checks)}项检查通过。其他候选明确继承封存开发审计，未冒充重新仿真。模型/原生编译/原生执行/形式化均0，新增接受版本与独立测试均0。',
        'research174/175及其他独立材料被读保护拒绝；未用于挑选候选或改变规则。完整输入路径及哈希见read_audit.json、source_bindings.json。条件恢复仍0/0不可估计；576次查询负结果不变。','',
        '全部候选逐项见candidate_matrix.json；公共/历史目标与保护ID见coverage_difference.json；真实提案的新旧决定分开见real_proposal_decisions.json。','',
        '本地复核（新的报告目录必须不存在；不启动仿真或模型）：','```powershell',
        'wsl -- python3 scripts/research176_discrimination_audit.py --out deliverables/research176_discrimination_recheck','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');g.s.seal_files(out)
    print(json.dumps(dict(candidates=len(matrix),checks=len(checks),trace_rows=raw_records,action=decision['action'],models=0),ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.out.resolve())
