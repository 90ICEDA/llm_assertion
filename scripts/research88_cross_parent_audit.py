"""Audit selected cross-parent paired decisions and bounded local continuation."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import research87_cross_parent_recovery as x

ROOT,read,dump,sha=x.ROOT,x.read,x.dump,x.sha


def inspect_version(folder,candidate,baseline):
    rows=0
    for cohort in ('alignment','history','search'):
        rows+=x.g.prior.diagnostic.audit_native(folder/cohort,candidate,x.P,cohort)
    small=read(folder/'alignment/result.json');smallgate=read(folder/'alignment/alignment_gate.json')
    assert smallgate['focus12']==x.g.focus_gate(small,read(x.P/'focus.private.json'))
    h=read(folder/'history/result.json');s=read(folder/'search/result.json')
    hg=x.all_guard(folder/'history',h,candidate);sg=x.all_guard(folder/'search',s,candidate)
    r0=x.paired.ordinary(small,smallgate,s,sg)
    full=x.paired.aggregate(h,s)
    r1=x.g.prior.preserve(baseline,full,read(x.P/'target_preservation.private.json'),x.old.decide)
    r1['accepted']=bool(r0['accepted'] and r1['accepted'] and hg['accepted'] and sg['accepted'])
    saved=read(folder/'decision.json')
    assert saved['ordinary']==r0 and saved['history']==r1
    assert saved['full_absolute']==bool(r0['accepted'] and x.old.admissible(full) and hg['accepted'] and sg['accepted'])
    before,after=x.old.acceptance.inspect(baseline['ledger']),x.old.acceptance.inspect(full['ledger'])
    for field,keys in [('new_false_alarm_ids',after['false_positives']-before['false_positives']),
        ('lost_detection_ids',before['detections']-after['detections']),
        ('retained_detection_ids',before['detections']&after['detections'])]:assert saved[field]==sorted(keys)
    return rows,saved,dict(alignment=small,history=h,search=s)


def run(prep,trial,out):
    x.verify(prep);out.mkdir(parents=True,exist_ok=False)
    initial=read(prep/'initial.json');proposal=read(prep/'proposal.json');baseline=read(prep/'baseline_full.json')
    assert sha(x.SOURCE)==sha(prep/'proposal.json')
    origin=x.SOURCE.parent
    original_edit=read(origin/'model_edit.json')
    compiled,_=x.ast.adapt(original_edit,initial);assert compiled==proposal
    original_chunks=[json.loads(line) for line in (origin/'response.stream.jsonl').read_text().splitlines()]
    original_text=''.join(c.get('message',{}).get('content','') for c in original_chunks)
    assert json.loads(original_text)==original_edit
    dump(out/'common_proposal_origin.json',dict(real_stream_and_ast_verified=True,
        files={p.relative_to(ROOT).as_posix():sha(p) for p in (origin/'request.json',origin/'response.stream.jsonl',origin/'model_edit.json',x.SOURCE)},
        historical_acquisition_cost=read(origin.parents[1]/'cost.json')['total'],
        allocation='Shared archived proposal acquisition, reported separately from the new two-call continuation budget.'))
    rows=0
    for cohort in ('history','search'):rows+=x.g.prior.diagnostic.audit_native(prep/'baseline'/cohort,initial,x.P,cohort)
    assert x.paired.aggregate(read(prep/'baseline/history/result.json'),read(prep/'baseline/search/result.json'))==baseline
    n,qualification,rs=inspect_version(prep/'qualification',proposal,baseline);rows+=n
    assert qualification['ordinary']['accepted'] and not qualification['history']['accepted']
    assert read(trial/'A/initial/active.json')==proposal
    assert read(trial/'B/initial/active.json')==initial
    active=initial;feedback=x.diagnostics(qualification,rs);versions=[];calls=[];seen={x.signature(initial),x.signature(proposal)}
    for folder in sorted((trial/'B').glob('v[0-9]*')):
        request=read(folder/'model_call/request.json');call=read(folder/'model_call/transport_result.json');calls.append(call)
        i=int(folder.name[1:]);assert request==(read(prep/'request.preview.json') if i==0 else x.request(proposal,feedback,i))
        if call['status']!='response_received':
            versions.append(dict(version=i,accepted=False,transport=call['status']));continue
        chunks=[json.loads(line) for line in (folder/'model_call/response.stream.jsonl').read_text().splitlines()]
        text=''.join(z.get('message',{}).get('content','') for z in chunks)
        assert text==read(folder/'model_call/response.raw.json')['message']['content']
        transition=read(folder/'transition/transition.json');final=read(folder/'transition/active.json')
        model=folder/'model_call/candidate.json';detail=None
        if model.exists():
            edit=read(folder/'model_call/model_edit.json');assert json.loads(text)==edit
            candidate,_=x.ast.adapt(edit,initial);assert candidate==read(model)
            if (folder/'native/decision.json').exists():
                assert x.signature(candidate) not in seen
                n,ev,rs=inspect_version(folder/'native',candidate,baseline);rows+=n
                assert transition['accepted']==ev['history']['accepted']
                detail=ev;proposal=candidate;feedback=x.diagnostics(ev,rs)
            else:
                assert not transition['accepted']
                assert x.signature(candidate) in seen or transition['reason']['reason']=='interface_or_repeat'
                feedback=dict(actual_model_text=text,actual_rejection=transition['reason'],previous_verified_diagnostics=feedback)
            seen.add(x.signature(candidate))
        else:feedback=dict(actual_model_text=text,actual_rejection=transition['reason'],previous_verified_diagnostics=feedback)
        assert final==(read(model) if transition['accepted'] else active)
        assert transition['previous_sha256']==x.old.acceptance.sha(active)
        active=final
        versions.append(dict(version=i,accepted=transition['accepted'],ordinary=detail['ordinary']['accepted'] if detail else None,
            full_absolute=detail['full_absolute'] if detail else None,counts=detail['counts'] if detail else None,
            new_false_alarms=len(detail['new_false_alarm_ids']) if detail else None,
            lost_detections=len(detail['lost_detection_ids']) if detail else None,reason=transition['reason']))
    assert len(calls)<=2
    if (trial/'budget_ledger.json').exists():assert len(read(trial/'budget_ledger.json'))<=2
    tests=None
    if (trial/'independent_summary.json').exists():
        freeze=read(trial/'freeze.json');generation=read(trial/'generation.json');txns=read(trial/'independent_cases.json')
        assert generation['at']>freeze['time'] and generation['freeze_sha256']==sha(trial/'freeze.json')
        excluded=read(prep/'excluded_words.json');assert txns==x.holdout.base.generate(generation['seed'],excluded)
        assert len({t['instruction'] for t in txns})==96 and not set(excluded)&{t['instruction'] for t in txns}
        assert read(trial/'frozen/A/candidate.json')==read(prep/'proposal.json')
        assert read(trial/'frozen/B/candidate.json')==active
        tests=read(trial/'independent_summary.json')
        for arm in ('A','B'):
            f=trial/'frozen'/arm;c=read(f/'candidate.json');r=read(f/'independent/result.json')
            assert x.old.acceptance.sha(c)==freeze['versions'][arm]
            a=x.holdout.base.native_audit(f,r);rows+=a['rows_audited']
            with patch.object(x.old,'CONFIGS',x.holdout.base.CONFIGS):guard=x.all_guard(f/'independent',r,c)
            assert tests[arm]==x.holdout.summarize(r,guard)
    costpath=trial/'resumed_cost.json' if (trial/'resume.json').exists() else trial/'cost.json'
    if (trial/'resume.json').exists():
        resume=read(trial/'resume.json')
        for n,h in resume['preserved'].items():assert sha(trial/n)==h,n
        assert resume['new_model_calls']==0 and resume['new_test_generation'] is False
        assert resume['reused_native']==dict(A=True,B=False)
        assert resume['new_native_revisions']==2
        assert read(trial/'terminal_outcome.json')['independent_executed'] is True
        for arm in ('A','B'):
            assert read(trial/'frozen'/arm/'independent_cases.json')==read(trial/'independent_cases.json')
    cost={name:read(p)['total'] for name,p in [('qualification',prep/'preparation_cost.json'),('continuation',costpath)]}
    assert sum(c['native_compile_calls'] for c in cost.values())<=26
    assert sum(c['native_execute_calls'] for c in cost.values())<=26
    assert cost['continuation']['model_calls']==len(calls)
    assert read(trial/'outcome.json')['new_calls']==len(calls)
    assert read(trial/'outcome.json')['active_B_sha256']==x.old.acceptance.sha(active)
    audit=dict(passed=True,native_rows_recomputed=rows,real_calls=len(calls),budget_passed=True,
        request_feedback_isolation_verified=True,original_preparation_unchanged=True,
        actual_rollback_verified=True,independent_generated_after_both_frozen=tests is not None,
        scripts={p.name:sha(p) for p in (Path(__file__),Path(x.__file__))})
    dump(out/'audit.json',audit);dump(out/'versions.json',versions);dump(out/'cost.json',cost)
    outcome=read(trial/'outcome.json')
    result=dict(paired_extra_rejection=True,avoided_new_legal_false_alarms=len(qualification['new_false_alarm_ids']),
        avoided_lost_target_detections=len(qualification['lost_detection_ids']),
        fallback=read(prep/'qualification.json')['initial_protection'],
        complete_fallback_before_recovery=False,new_recovery_accepted=outcome['accepted_B'],
        independent_passed_B=tests['B']['passed'] if tests else None,
        ordinary_acceptance=qualification['ordinary']['accepted'],same_history_absolute_also_rejects=not qualification['full_absolute'],
        new_calls=len(calls),ordinary_new_calls=0,equal_maximum_additional_calls=2,
        selection='Selected and previously observed historical proposal; conditional continuation, not new proposal discovery or random success rate.',
        same_budget_full_recovery=bool(outcome['accepted_B'] and tests and tests['B']['passed']))
    dump(out/'result.json',result)
    lines=['# research87–88：跨父案例的配对拒绝与固定预算恢复','',
        '父案例为原始 Ibex #166 decoder，区别于 axis_fifo 人工故障案例。起始提案来自 research61 真实本地模型；它曾被 research66 回顾性分析，本轮没有冒充新发现。新的部分是重新原生复核、持久化接受/回退，以及预封存预算后的真实恢复调用。','',
        f"同一提案：普通R0接受；历史R1额外拒绝。历史新增合法误报 **{len(qualification['new_false_alarm_ids'])}** 条，丢失旧违例检出 **{len(qualification['lost_detection_ids'])}** 条。避免误报属于保留合法事务保护，不能写成恢复了丢失的目标检出。计数为采样/配置/版本记录，不是独立Bug数。",'',
        '同历史信息的绝对检查也拒绝该提案，因此证据支持“额外历史回放有用”，不支持“相对比较器独有必要性”。绝对检查是共享提案决策对照，没有冒充独立模型运行。','',
        '拒绝后实际活动版本保留旧基线：BRANCH 270个检出、零合法误报；仍遗漏420个OP点，且必要触发不足。因此是可用的部分保护基线，不是已经完整接受的断言集合。新旧版本哈希和回退记录在B/initial与每轮transition中。','',
        '|恢复轮次|普通接受|历史接受|同信息绝对接受|完整目标检出|新增合法误报|丢失基线检出|','|---|---|---|---|---:|---:|---:|']
    for v in versions:
        detections=sum(v['counts'][c]['detections'] for c in ('history','search')) if v.get('counts') else None
        measured=f'{detections}/690' if detections is not None else '重复提案，未重编译'
        lines.append(f"|{v['version']}|{v.get('ordinary')}|{v['accepted']}|{v.get('full_absolute')}|{measured}|{v.get('new_false_alarms')}|{v.get('lost_detections')}|")
    lines+=['',f"本轮新模型调用 **{len(calls)}/2**，新完整接受版本 **{int(outcome['accepted_B'])}**。普通组初始接受即停止，实际新调用0；两组追加预算上限相同，实际成本不相同。未进行协议/模型/表示切换、传输重试或额度追加。",'',
        '|冻结终态|独立通过|检出证据点|漏报|误报|关键unknown|必要未触发|','|---|---|---:|---:|---:|---:|---:|']
    if tests:
        for arm,t in tests.items():
            c=t['counts'];lines.append(f"|{arm}|{t['passed']}|{c['detections']}|{c['misses']}|{c['false_positives']}|{c['unknown']}|{t.get('required_untriggered')}|")
    else:lines+=['|未执行|无法判定||||||']
    lines+=['','独立96个新指令字在两组终态冻结后生成，排除既有开发与research63/85全部已用编码，两组使用同一批新测试和四配置。两项义务实际曝光按原始RTL阶段规则验收。没有据独立失败修改断言；若以后用于调整，整批转开发。','',
        f"完整预算内恢复（新原生接受且新独立通过）：**{result['same_budget_full_recovery']}**。仅一个已观察、选定历史案例；不是新模型多种子成功率，也不是证明防退化全局有效。",'',
        '|成本|模型调用|输入tokens|输出tokens|原生编译|原生执行|','|---|---:|---:|---:|---:|---:|']
    for label,c in cost.items():lines.append(f"|{label}|{c['model_calls']}|{c['prompt_tokens_total']}|{c['completion_tokens_total']}|{c['native_compile_calls']}|{c['native_execute_calls']}|")
    lines+=['','上述为本轮新增成本；共同起始归档提案的原始生成成本保留在research61账本，不假称免费生成。原始模块、RTL哈希、模型请求响应、原生波形及每轮诊断均保存。远程调用0，形式化调用0。', '',
        f"审计重算{rows}条原生证据记录，验证固定规则、模型输出到可执行性质、反馈来源、预算、回退和独立划分。该结论不扩展到整核、所有指令或形式化证明。",'',
        '复核：','```powershell',f'wsl -- python3 scripts/research88_cross_parent_audit.py --prepared {prep.relative_to(ROOT).as_posix()} --run {trial.relative_to(ROOT).as_posix()} --out deliverables/research88_audit_NEW','```','',
        '上方复核命令只读取已有证据，不调用模型。重新运行research87的run命令才会产生新的本地模型调用，必须使用新目录并重新封存。不能把旧接受SVA复制成新模型恢复；也不自动追加调用。']
    if (trial/'resume.json').exists():
        lines+=['','执行记录：原运行在A组原生回放完成后因审计器所需的组内测试清单缺失而中断。research89仅补齐同一批测试的路径绑定，复用A日志、执行尚未运行的B；冻结哈希、测试种子、测试内容和模型结果均未更改。原exception/outcome/cost保留，terminal_outcome与resumed_cost单独记录补完状态；没有追加模型调用。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    paths=[prep/'sealed.json',trial/'outcome.json',trial/'cost.json']
    if (trial/'resume.json').exists():paths.extend(trial/n for n in ('resume.json','resumed_cost.json','terminal_outcome.json'))
    dump(out/'bindings.json',{p.relative_to(ROOT).as_posix():sha(p) for p in paths})
    print('AUDIT88',result,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('prepared','run','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
