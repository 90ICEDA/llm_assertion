"""Local retrospective O/H discrimination audit. No generation or native replay.

Reads development cohorts only. Frozen/independent inputs and results are denied.
No rule changes; no selected successful predicates are assembled into a proposal.
"""
import argparse
from collections import Counter
import copy
import json
from pathlib import Path
import sys
from unittest.mock import patch
import research145_stability_prepare as prepmod

c=prepmod.c
ROOT,read,dump,digest,rel=c.ROOT,c.read,c.dump,c.digest,c.rel
PREP=ROOT/'deliverables/research145_stability_prepare_20261027_r02'
RUN=ROOT/'deliverables/research145_stability_real_20261027_r01'


def install_guard(out):
    opened=set()
    def guard(event,args):
        if event in ('socket.connect','socket.getaddrinfo','subprocess.Popen'):
            raise RuntimeError('audit_must_not_launch_network_or_process:'+event)
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        path=str(args[0]).replace('\\','/')
        mode=args[1]
        if '/deliverables/' not in path:return
        if isinstance(mode,str) and any(k in mode for k in 'wax+'):
            if not path.startswith(str(out).replace('\\','/')+'/'):raise RuntimeError('write_outside_new_report:'+path)
            return
        if any(k in path for k in ('/independent','/tested_versions/','/terminal_frozen/','/frozen/',
                                   'research133_','research134_','/excluded_words.json')):
            raise RuntimeError('independent_material_forbidden:'+path)
        # Aggregate results include independent outcomes; read only cell development records.
        if path in {str(RUN/'results.json'),str(RUN/'independent_summary.json')}:
            raise RuntimeError('aggregate_holdout_results_forbidden')
        opened.add(path)
    sys.addaudithook(guard)
    return opened


def sample(row):
    s=row['sample'];word=s['instruction']
    return dict(evidence_id=row['evidence_id'],sample=s,configuration=row['configuration'],revision=row['revision'],
        obligation=row['obligation'],expected=row['expected'],observed=row['observed'],oracle=row['oracle'],
        decoded=dict(instruction_hex=f'{word:08x}',opcode=word&127,funct3=(word>>12)&7,bit28=(word>>28)&1,bit31=(word>>31)&1),
        assertions=row['native']['assertions'])


def profile(info):
    return c.x.old.acceptance.sha({k:sorted(info[k]) for k in ('detections','misses','triggers','false_positives','unknown')})


def alarm_trace(records,candidate,cohort,alarm):
    rec=records[cohort];sid=alarm['sample_id'];config=alarm['configuration'];rev=alarm['revision']
    prop=next(a for a in candidate['assertions'] if a['id']==alarm['assertion'])
    end=next(r for r in rec['reference'] if r['sample_id']==sid and r['configuration']==config)
    startid=sid-prop['delay']
    starts=[r for r in rec['reference'] if r['sample_id']==startid and r['configuration']==config]
    start=starts[0] if len(starts)==1 else None
    return dict(cohort=cohort,assertion=prop,revision=rev,configuration=config,antecedent_start=start,
        consequent_check=end,transaction_switched=start is not None and start['transaction_id']!=end['transaction_id'],
        specification_at_check=end['expected'],rtl_at_check=end['actual'][rev],
        attribution='Existing native ASSERT/TRACE record, property delay and actual sample identity; not inferred from model explanation.')


def coverage(records,info):
    """Decoded-category projections expose residual scope; never imply equivalence."""
    def key(r):
        s=r['sample'];w=s['instruction'];cfg=r['configuration']
        return (r['revision'],r['obligation'],w&127,(w>>12)&7,(w>>28)&1,(w>>31)&1,s['instr_new'],
                cfg['RV32E'],cfg['RV32M'],r['expected'],r['observed'])
    public={key(r) for name in ('alignment','search') for r in records[name]['ledger']}
    hist=records['history']['ledger'];protected=[r for r in hist if r['evidence_id'] in info['detections']]
    missing=[r for r in hist if key(r) not in public]
    return dict(public_projection_classes=len(public),historical_projection_classes=len({key(r) for r in hist}),
        history_only_classes=len({key(r) for r in missing}),history_only_rows=len(missing),
        old_protected_history_rows=len(protected),old_protected_history_rows_outside_public_projection=sum(key(r) not in public for r in protected),
        history_only_examples=[sample(r) for r in missing[:3]],
        projection_fields='revision,obligation,opcode,funct3,bit28,bit31,instr_new,RV32E,RV32M,expected,observed',
        limit='Ignores other instruction bits, complete phase counts and temporal context. Shared projection is not semantic equivalence or a guarantee. History-only rows are not new search discoveries.')


def audit(out):
    out.mkdir(parents=True,exist_ok=False);opened=install_guard(out);checks=[];raw_rows=0
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        assert value,name
    cells=read(PREP/'cells.json');inventory=read(PREP/'candidate_matrix.json')
    check('locked_12_cells',len(cells)==12)
    # Snapshot only permitted development files; never traverse tested_versions.
    bound={rel(PREP/name):digest(PREP/name) for name in ('cells.json','candidate_matrix.json','protocol.json','population_lock.json')}
    details=[];baseline_profiles={};baseline_info={};base_records={};candidate_rows=[]
    for item in inventory:
        row=dict(id=item['id'],parent=item['parent'],source=item['path'],eligible_initial=item['eligible'],
                 exclusion_reasons=item['exclusion_reasons'],new_recovery_opportunity=False)
        if item['eligible']:
            initial=read(PREP/'candidates'/item['id']/'initial.json')
            baseline=read(PREP/'candidates'/item['id']/'baseline_full.json')
            fullinfo=c.x.old.acceptance.inspect(baseline['ledger']);baseline_info[item['id']]=fullinfo
            folder=ROOT/item['development']['measurement']
            records={k:read(folder/k/'result.json') for k in ('alignment','search','history')};base_records[item['id']]=records
            for rec in records.values():c.mapping.validate_ledger(rec,initial)
            baseline_profiles[item['id']]=profile(fullinfo)
            row.update(existing_detections=len(fullinfo['detections']),unresolved_public_misses=sum(records[k]['counts']['misses'] for k in ('alignment','search')),
                immutable_components=[],all_predicates_editable=True,scope_residual=coverage(records,fullinfo))
            # Interface accepts a changed BRANCH antecedent verbatim. Not a model proposal.
            edit=c.p.q.as_edit(initial)
            for a in edit['assertions']:
                if a['obligations']==[c.mapping.BRANCH]:a['antecedent']="1'b0"
            adapted=c.mapping.adapt(edit)
            check('editable_branch_'+item['id'],all(a['antecedent']=="1'b0" for a in adapted['assertions'] if a['obligations']==[c.mapping.BRANCH]))
        candidate_rows.append(row)
    for cell in cells:
        ident=cell['id'];folder=RUN/'cells'/ident;stage=folder/'shared/v0'
        candidate=read(stage/'model_call/candidate.json');baseline=read(PREP/'cells'/ident/'baseline_full.json')
        n,d,records=c.mapping.inspect_version(stage/'native',candidate,baseline);raw_rows+=n
        initial=read(PREP/'cells'/ident/'initial.json')
        req=read(stage/'model_call/request.json');body=json.loads(req['messages'][1]['content'])
        check(ident+'_request_frozen',req==read(PREP/'cells'/ident/'request.preview.json'))
        check(ident+'_only_public_feedback',set(body['actual_feedback']['visible_counts'])=={'alignment','search'})
        check(ident+'_editable_components','fixed_component' not in body and 'Every component is editable' in body['current_candidate_status'])
        oldinfo=baseline_info[cell['candidate']];full=c.x.paired.aggregate(records['history'],records['search']);info=c.x.old.acceptance.inspect(full['ledger'])
        o=d['ordinary']['accepted'];h=d['full_absolute'];first=read(folder/'first_decisions.json')
        check(ident+'_decision_recomputed',o==first['O'] and h==first['H'])
        check(ident+'_H_R_agree_on_actual',h==d['history']['accepted'])
        check(ident+'_no_hidden_recovery_call',not (folder/'history/v1/model_call/attempt.json').exists())
        active={a:read(folder/'arms'/a/'v0/active.json') for a in ('O','H')}
        check(ident+'_active_versions_preserved',all(v==(candidate if o else initial) for v in active.values()))
        errors=[];alarm_examples=[];miss_examples=[];cohort_counts={}
        for name,rec in records.items():
            i=c.x.old.acceptance.inspect(rec['ledger'])
            guard=d['current_gate']['all_property_guard'] if name=='alignment' else d['all_property_guards'][name]
            alarms=guard['false_alarms']
            reasons=Counter()
            for alarm in alarms:
                tr=alarm_trace(records,candidate,name,alarm)
                reasons['cross_transaction' if tr['transaction_switched'] else 'same_transaction']+=1
            cohort_counts[name]=dict(**rec['counts'],required_untriggered=len(rec['required_untriggered']),
                all_property_false_alarms=len(alarms),false_alarms_by_assertion=dict(Counter(a['assertion'] for a in alarms)),alarm_timing=dict(reasons))
            if alarms:alarm_examples.append(alarm_trace(records,candidate,name,alarms[0]))
            if i['misses']:miss_examples.append(dict(cohort=name,**sample(i['rows'][sorted(i['misses'])[0]])))
            check(ident+'_'+name+'_confirmed_no_unknown',not i['unknown'] and not i['errors'] and not guard['unknown'])
        for kind,keys in [('old_detection_lost',d['lost_detection_ids']),('new_legal_false_alarm',d['new_false_alarm_ids'])]:
            bycohort=Counter(info['rows'][k]['sample']['cohort'] for k in keys)
            errors.append(dict(kind=kind,total=len(keys),by_cohort=dict(bycohort),evidence_ids=keys,
                example=sample(info['rows'][keys[0]]) if keys else None))
        failed=[k for k,v in d['ordinary']['checks'].items() if not v]
        public_misses=sum(records[k]['counts']['misses'] for k in ('alignment','search'))
        public_fp=sum(cohort_counts[k]['all_property_false_alarms'] for k in ('alignment','search'))
        if o and h:reason='both_pass_no_observed_regression'
        elif public_fp:reason='ordinary_already_rejects_public_legal_false_alarms'
        elif public_misses:reason='ordinary_already_rejects_public_misses_or_required_triggers'
        else:reason='other_check_failure'
        eligibility=[]
        if info['false_positives'] or any(v['all_property_false_alarms'] for v in cohort_counts.values()):eligibility.append('baseline_legal_false_alarms')
        if not info['detections']:eligibility.append('no_existing_protection')
        if not public_misses:eligibility.append('no_public_repair_target')
        if info['unknown'] or info['errors']:eligibility.append('unknown_or_integrity_error')
        prof=profile(info)
        details.append(dict(id=ident,candidate=cell['candidate'],seed=cell['seed'],O=o,H=h,
            reason=reason,ordinary_failed_checks=failed,public_misses=public_misses,public_false_alarm_property_points=public_fp,
            cohort_counts=cohort_counts,regressions=errors,properties=candidate['assertions'],
            concrete_false_alarm_traces=alarm_examples,concrete_missed_samples=miss_examples,
            focus12=d['current_gate']['focus12']['phases'],critical_unknown=c.critical_unknown(d),
            incremental_rejection=bool(o and not h),retained_baseline_after_rejection=not o,
            retained_detection_points_after_rejection=len(oldinfo['detections']) if not o else None,
            proposed_as_next_initial=dict(eligible=not eligibility,exclusion_reasons=eligibility,
                existing_behavior_profiles=[k for k,v in baseline_profiles.items() if v==prof],
                new_qualified_profile=not eligibility and prof not in baseline_profiles.values()),
            no_recovery_reason='protocol_requires_O_accept_H_reject_confirmed_regression',native_rows_reaudited=n))
        for f in stage.rglob('*'):
            if f.is_file() and 'obj_dir' not in f.parts:bound[rel(f)]=digest(f)
        print('AUDIT158',ident,'O/H',o,h,'public FN/FP',public_misses,public_fp,'reason',reason,flush=True)
    # Recheck the pre-existing fabricated discriminator only to rule out O==H
    # by construction. Do not turn an exact instruction whitelist into a new trial.
    fixture=ROOT/'deliverables/research140_mapping_native_20261027_r01/historical_loss'
    fprep=ROOT/'deliverables/research140_mapping_prepare_20261027_r01/fixtures/historical_loss'
    fcan=read(fprep/'candidate.json')
    fbaseline=read(c.p.QUAL/'baseline_full.json')
    n,fd,_=c.mapping.inspect_version(fixture/'native',fcan,fbaseline);raw_rows+=n
    fixture_result=dict(source=rel(fixture),local_handbuilt_not_model=True,O=fd['ordinary']['accepted'],H=fd['full_absolute'],
        lost_old_detections=len(fd['lost_detection_ids']),new_false_alarms=len(fd['new_false_alarm_ids']),
        exact_instruction_whitelist=any('instr == 32\'h' in a['antecedent'] for a in fcan['assertions']),
        interpretation='Confirms interface/rule distinguishability only. Explicit public-word whitelist is not a fresh real model proposal, meaningful generation probability or recovery success.')
    check('O_H_not_identical_by_construction',fixture_result['O'] and not fixture_result['H'] and fixture_result['lost_old_detections']>0)
    eligible_new=[r for r in details if r['proposed_as_next_initial']['new_qualified_profile']]
    opportunities=[r for r in details if r['incremental_rejection']]
    decision=dict(base_initial_qualification_count=sum(r['eligible_initial'] for r in candidate_rows),
        real_proposal_count=len(details),ordinary_historical_both_pass=sum(r['O'] and r['H'] for r in details),
        ordinary_historical_both_reject=sum(not r['O'] and not r['H'] for r in details),
        actual_incremental_rejections=len(opportunities),actual_qualified_recovery_opportunities=len(opportunities),
        new_qualified_behavior_profiles=len(eligible_new),structural_discrimination_exists=True,
        meaningful_new_pilot_qualification='not_established',action='STOP_NO_NEW_PILOT_SEALED',
        rationale='Existing four initial candidates remain legal partial baselines, but this batch offers no O-pass/H-fail real proposal and no new qualified behavioral profile. A handbuilt word-whitelist discriminator only repeats old structural qualification. Do not rerun the same seed search or weaken O to create a result.',
        future_reentry='New independently motivated development case/failure mechanism with editable prior protection and a bounded meaningful discrimination control; list all candidates/exclusions before selecting. Fix public rules and budget before real calls. New local controls alone cannot be called prospective mechanism success.',
        H_R_scope='Same fixed evidence and full-scope acceptance remain equivalent; no R-over-H unique benefit claimed.',
        model_calls=0,new_native_compiles=0,new_native_executions=0,formal_calls=0,
        new_accepted_versions=0,new_independent_tests=0,retrospective=True)
    dump(out/'cell_diagnostics.json',details);dump(out/'candidate_scope_matrix.json',candidate_rows)
    dump(out/'structural_discriminator.json',fixture_result);dump(out/'decision.json',decision)
    dump(out/'audit.json',dict(checks=checks,raw_native_rows_reaudited=raw_rows,no_rule_changes=True,no_holdout_reads=True))
    lines=['# 12单元普通/历史同判诊断（仅开发数据、回顾性）','',
        '**结论：停止，不封存新的同类先导，不申请或执行模型调用。** 四个初始候选的基础资格仍成立，但没有新增可用的区分提案或保护行为；不能把人工白名单对照当成值得继续追加同类调用的证据。','',
        '|单元|O/H|公共漏报采样|公共误报性质点|历史旧检出丢失（history+search）|新增误报（history+search）|拒绝后保留检出|',
        '|---|---|---:|---:|---:|---:|---:|']
    for r in details:
        lines.append(f"|{r['id']}|{r['O']}/{r['H']}|{r['public_misses']}|{r['public_false_alarm_property_points']}|{r['regressions'][0]['total']}|{r['regressions'][1]['total']}|{r['retained_detection_points_after_rejection'] if not r['O'] else '新版本接受'}|")
    lines += ['', '公共漏报列为alignment与search两个队列的采样合计；误报列按性质/配置/版本计数。相同事务可跨队列出现，不能相加为独立Bug。原始普通规则同时检查current9与search36，H还要求history115；未删减公共检查。', '',
        '## 五个失败单元为何没有增量拒绝','',
        '- s14501_c01、s14509_c01：目标全部检出，但next_sample性质在保持末拍触发，检查落到后继合法事务，公共两队列已出现误报。历史另有误报，也不是额外拒绝的决定因素。',
        '- s14509_c05：BRANCH错误使用bit28代替funct3类别，公共已经漏报；历史另外有636个误报及旧保护损失。虽有历史独有错误，整个提案已被O拒绝，不能归功于H。',
        '- s14519_c00：OP仍加错误bit31约束，缺少必需触发；延后一周期的BRANCH还丢失历史检出。普通漏报足以拒绝。',
        '- s14519_c01：OP仍使用bit31，公共目标未补齐；BRANCH历史保护保留。两套规则都应拒绝。',
        '- 其余7个真实提案在开发完整范围内都通过，没有保护损失需要历史额外拦截。没有读其独立测试来挑选候选或规则。','',
        '## 可编辑性与剩余区分空间','',
        '- 请求中全部BRANCH/OP谓词可编辑，2至6条性质可多对一映射；没有固定组件提前阻止退化。对四个基线的BRANCH编辑均经适配器逐字保留检查。',
        f"- 旧手写白名单对照重审O=True/H=False，丢失{fixture_result['lost_old_detections']}个旧检出。说明O与H并非逻辑上完全相同；它按公共指令字显式限制前件，不能包装为真实模型机会或新贡献。",
        '- 候选矩阵保存历史独有类别和既有保护的覆盖投影。投影只作范围描述，不证明O蕴含H，也不把历史记录多于公共记录等同于可实现的模型增量收益。',
        '- 全部8个既有Ibex候选和9个FIFO入口均保留资格/排除原因；未按预期收益筛选。当前12个新提案中，完整版本没有待修复公共缺口；带误报版本不合格；唯一仍合格的部分行为复用了已有行为簇，没有新增合格行为簇。',
        '', '## 停止与重入条件','',
        '本次基础资格与“值得新开一次相同先导”分开：前者成立，后者未建立。因此没有新请求预览、模型预算或前瞻实验封存。条件恢复率仍是0/0不可估计，不是0%成功率。',
        '后续只有出现依据独立开发动机的新案例/失效机制、可编辑旧保护与实质性区分对照，才重新做候选全集资格和有界协议；不得削弱普通规则、人工拼接真实提案、读取独立结果选候选，或把白名单夹具作为模型成功。',
        '',f'本轮模型0、编译0、执行0；只读重算{raw_rows}条原生开发记录，{len(checks)}项检查。没有新接受版本、新独立验收或前瞻增量成功。旧结果不追改。',
        '', '复核到新目录：','```powershell','wsl -- python3 scripts/research158_development_decision_audit.py --out deliverables/research158_new_audit','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n')
    # Writes remain restricted to this new report and all read paths are disclosed.
    for name,h in bound.items():check('unchanged/'+name,digest(ROOT/name)==h)
    dump(out/'source_bindings.json',bound)
    dump(out/'read_audit.json',sorted(opened))
    dump(out/'audit.json',dict(checks=checks,raw_native_rows_reaudited=raw_rows,no_rule_changes=True,no_holdout_reads=True))
    dump(out/'sealed.json',{p.relative_to(out).as_posix():digest(p) for p in out.rglob('*') if p.is_file()})
    print('COMPLETE158',decision,'checks',len(checks),'rows',raw_rows,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True,type=Path)
    audit(ap.parse_args().out.resolve())
