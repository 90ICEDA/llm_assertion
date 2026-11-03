"""Recompute the bounded recovery result from real transport and native logs."""
import argparse
from pathlib import Path
import research74_recovery as run
import research68_result_audit as native
from research28_report import raw_response
from research17_report import cost_audit

b,read,dump,ROOT=run.b,run.read,run.dump,run.ROOT


def audit(prep,root,out):
    out.mkdir(parents=True,exist_ok=False);checks=[];raw=0
    def check(name,okay):
        assert okay,name
        checks.append(name)
    for name,h in read(prep/'sealed.json').items():check('sealed '+name,b.search.digest(prep/name)==h)
    for name,h in read(prep/'code_versions.json').items():check('code '+name,b.search.digest(Path(name))==h)
    bindings=read(prep/'bindings.json');source=Path(bindings['source']);old_audit=Path(bindings['audit'])
    for name,h in bindings['files'].items():check('source '+name,b.search.digest(Path(name))==h)
    initial=read(prep/'initial.json');current=initial;cases=read(prep/'cases.json');history=read(prep/'history_cases.json')
    before=read(source/'baseline_public/result.json');historical=read(source/'baseline_history/result.json')
    outcome=read(root/'outcome.json');attempts=sorted(root.glob('core/v*/model_call/attempt.json'))
    check('new bounded calls',len(attempts)==outcome['calls'] and 0<len(attempts)<=2)
    authorization=read(root/'authorization.json')
    check('bound authorization',authorization['authorized_calls']==2 and authorization['prepared_sha256']==b.search.digest(prep/'sealed.json'))
    seen={b.interface.executable_hash(initial),b.interface.executable_hash(read(source/bindings['candidate_slot']/'candidate.json'))}
    details=[];paired=[];previous_request=read(prep/'request.preview.json');last_edit=None
    with b.extension.installed():
        for attempt in attempts:
            m=attempt.parent;folder=m.parent;call=read(m/'result.json')
            check(folder.name+' request exact',read(m/'request.json')==previous_request)
            if call['status']!='response_received':
                check('transport terminal',outcome['status']=='transport_stopped' and attempt==attempts[-1])
                details.append(dict(version=folder.name,status=call['status'],candidate=False));break
            edit=read(m/'model_edit.json') if (m/'model_edit.json').exists() else None
            candidate=read(m/'candidate.json') if (m/'candidate.json').exists() else None
            if edit:check(folder.name+' real response preserved',raw_response(m,edit))
            if candidate:check(folder.name+' model-owned executable',b.interface.assemble(edit,current)==candidate)
            repeated=bool(candidate and b.interface.executable_hash(candidate) in seen)
            if candidate:seen.add(b.interface.executable_hash(candidate))
            small=read(folder/'public/result.json') if (folder/'public/result.json').exists() else None
            full=read(folder/'history/result.json') if (folder/'history/result.json').exists() else None
            if repeated:check(folder.name+' repeated skipped',small is None and full is None)
            if small:raw+=native.raw_replay(folder/'public',cases,candidate,checks)
            if full:raw+=native.raw_replay(folder/'history',history,candidate,checks)
            plain=b.paired.current_decision(before,small,edit) if small else dict(accepted=False,reasons=[dict(kind='repeated_executable' if repeated else 'interface_failure')])
            decision=run.policy.decision_for(plain,full,historical,True)
            check(folder.name+' decision recomputed',decision==read(folder/'decision.json'))
            ordinary_only=run.policy.decision_for(plain,None,None,False)
            paired.append(dict(version=folder.name,ordinary_rule_accepts=ordinary_only['accepted'],
                historical_rule_accepts=decision['accepted'],extra_rejection=decision['gate_incremental_rejection'],
                caveat='Same new actual proposal, decision counterfactual only; no independently running ordinary refinement trajectory. A rule already reading full105 history would also reject.'))
            current=candidate if decision['accepted'] else current
            check(folder.name+' retained state',current==read(folder/'active_candidate.json'))
            check(folder.name+' transition hash',b.loop.sha(current)==read(folder/'active_transition.json')['active_hash'])
            if decision['accepted']:check('accepted stops calls',attempt==attempts[-1])
            else:
                expected=run.policy.feedback_for(small,full,decision,call,edit,last_edit,True)
                check(folder.name+' genuine own feedback',expected==read(folder/'next_feedback.json'))
                if (folder/'next_request.preview.json').exists():
                    previous_request=b.campaign.request_from(read(prep/'request.preview.json'),current,run.SEED,expected)
                    check(folder.name+' next payload exact',previous_request==read(folder/'next_request.preview.json'))
            details.append(dict(version=folder.name,status=call['status'],edit=edit,repeated=repeated,
                ordinary_pass=plain['accepted'],accepted=decision['accepted'],reason_kinds=sorted({r['kind'] for r in decision['reasons']}),
                public=small.get('counts') if small else None,history=full.get('counts') if full else None,
                candidate_hash=b.loop.sha(candidate) if candidate else None))
            last_edit=edit
    check('frozen exact accepted or retained version',read(root/'core/frozen_candidate.json')==current and b.loop.sha(current)==outcome['frozen_hash'])
    check('no independent result fabricated',outcome['independent_performed'] is False and not (root/'independent').exists())
    check('old independent results unchanged',run.screen.protected()==read(source/'protected.json'))
    qualification=read(old_audit/f"{bindings['candidate_slot']}_evidence.json")
    recovery=None
    if outcome['accepted']:
        last=attempts[-1].parent.parent;full=read(last/'history/result.json')
        info=b.loop.inspect(full['group']['ledger']);reg=qualification['regressions']
        lost=reg['confirmed_lost_detection'];false=reg['new_legal_false_positive']
        restored=[k for k in lost if k in info['detections']]
        cleared=[k for k in false if k not in info['false_positives'] and k not in info['unknown']]
        check('all confirmed lost points restored',len(restored)==len(lost))
        check('all historical obligation false alarms resolved',len(cleared)==len(false))
        check('no historical critical unknown',not info['unknown'])
        recovery=dict(confirmed_lost=len(lost),restored=len(restored),false_alarms=len(false),cleared=len(cleared),
                      history=full['counts'],mapping=info['mapping'])
        dump(out/'recovery_evidence.json',dict(**recovery,restored_ids=restored,cleared_ids=cleared))
    cost=cost_audit(root,b.paired.files(root));check('physical call accounting',cost['total']['model_calls']==len(attempts))
    dump(out/'cost.json',cost);dump(out/'rounds.json',details);dump(out/'paired_decisions.json',paired)
    dump(out/'audit.json',dict(passed=True,checks=checks,raw_native_records=raw,reference_recomputations=raw,
        source_hash=b.search.digest(Path(__file__)),accepted=outcome['accepted'],independent_performed=False,recovery=recovery))
    lines=['# research74：真实历史拒绝反馈后的有界恢复','',
        f"实际调用 {len(attempts)}/2；终态 {outcome['status']}；接受 {outcome['accepted']}。无传输重试。",
        '', '入口提案由research73回顾性筛选：固定14公共场景普通通过；105历史新增31个确认漏报、46条义务级误报、22条关键unknown，门控额外拒绝并保留原基线。',
        '', '46条是合法激励下、对应义务被独立判为满足时的断言误报，部分发生于其他故障模式；不是46个完全无故障事务或独立Bug。31个确认漏报按失效机制归为背压稳定性这一类。',
        '', '|轮|普通通过|完整接受|重复|公共计数|历史计数|拒绝原因|','|---|---|---|---|---|---|---|']
    for d in details:
        lines.append(f"|{d['version']}|{d.get('ordinary_pass')}|{d.get('accepted')}|{d.get('repeated')}|{d.get('public')}|{d.get('history')}|{d.get('reason_kinds')}|")
    lines+=['',f"冻结哈希：`{outcome['frozen_hash']}`。",'',
        f"恢复核验：{ {k:v for k,v in (recovery or {}).items() if k!='mapping'} }。" if recovery else '没有接受的新恢复版本；保持之前部分有效的基线，不宣称修复成功。',
        '', '模型只收到失败提案、基线与开发诊断，没有归档成功性质或任何独立测试。所有编辑来自真实响应，未经语义改写。',
        '', '这是选定的已观察案例上的前瞻性两次有界恢复，不能计为新的随机消融或跨种子稳定收益；回顾性入口和新恢复调用成本分开。',
        '', f"同一新真实提案配对决定：{paired}。增量来自额外历史证据；若普通规则本来就读取105历史并要求无误报/漏报，它也会拒绝，不能单独归功于相对比较算子。",
        '', '本次未执行新的独立验收。旧research72独立结果未用于改规则或选候选，保持原状。若产生新接受版本，仍需另封存新的冻结后测试。',
        '', f"成本：{cost['total']}。形式化调用0；仿真不等于证明。原生记录复核{raw}份，审计{len(checks)}项。参考判定单独计时与货币金额不可用。",'',
        '只读复核（新目录）：','```powershell',
        f'wsl -- python3 scripts/research74_result_audit.py --prepared {prep.relative_to(ROOT).as_posix()} --run {root.relative_to(ROOT).as_posix()} --out deliverables/research74_audit_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    trace=['# 真实恢复轨迹','', '原始退化提案：','```systemverilog']
    failed=read(source/bindings['candidate_slot']/'candidate.json')
    trace += [a['id']+': '+a['property'] for a in failed['assertions']]
    trace+=['```','', '公共检查3/3；历史161/214检出，31确认漏报与22关键unknown分列。31漏报中5条无断言触发，26条有触发但未检出，不能只改前件解释。']
    for d in details:
        trace+=['',d['version'],'```json',__import__('json').dumps(d.get('edit'),ensure_ascii=False,indent=2),'```',
                f"接受 {d.get('accepted')}；原因 {d.get('reason_kinds')}。"]
    trace+=['','最终冻结集合：','```systemverilog']+[a['id']+': '+a['property'] for a in current['assertions']]+['```',
        '', '独立测试：未执行；不得把开发119场景通过写成独立验收。']
    (out/'CASE_TRACE.md').write_text('\n'.join(trace)+'\n',encoding='utf-8')
    print('RECOVERY_AUDIT',len(checks),'checks',raw,'native records',outcome['status'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
