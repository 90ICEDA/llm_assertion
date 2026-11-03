"""Read-only raw-response, gate, isolation, budget and freeze audit of research94."""
import argparse
import copy
import json
from pathlib import Path
from unittest.mock import patch
import research94_prospective_gate_pilot as p
from research93_remote_recovery_audit import response
from research88_cross_parent_audit import inspect_version

x=p.x
ROOT,read,dump,sha=p.ROOT,p.read,p.dump,p.sha


def run(prep,trial,out):
    x.verify(prep)
    p.grant_check(read(trial/'authorization.json'),prep,trial)
    assert p.protected_snapshot()==read(prep/'protected93.json')
    initial=read(prep/'initial.json');base=read(prep/'baseline_full.json')
    ledger=read(trial/'budget_ledger.json');assert 1<=len(ledger)<=4
    rows=0;versions=[];calls=[];measured={}
    first_candidate=None;first_records=None;first_ev=None;first_reason=None
    for index,item in enumerate(ledger):
        folder=trial/item['path'];mf=folder/'model_call'
        call=read(mf/'result.json');calls.append(call)
        if index==0:
            assert item['path']=='shared/v0'
            current=initial;visible=read(prep/'initial_public_feedback.json');iteration=0
        else:
            arm=folder.parent.name;assert arm in p.ARMS and folder.name=='v1'
            assert not measured['shared/v0']['decisions'][arm]
            current=first_candidate or initial;iteration=1
            if first_records:visible=p.feedback(first_ev,first_records,arm!='O')
            else:visible=dict(prior_public_feedback=read(prep/'initial_public_feedback.json'),
                actual_rejection=first_reason,actual_model_text=read(trial/'shared/v0/model_call/response.assembled.json')['message']['content'])
        req=read(mf/'request.json')
        assert req==p.payload(current,visible,iteration)
        assert item['request_sha256']==x.old.acceptance.sha(req)
        if index==0:assert req==read(prep/'request.preview.json')
        text,raw=response(mf);candidate=None;ev=None;records=None
        measurement=read(folder/'measurement.json')
        if (mf/'candidate.json').exists():
            edit=read(mf/'model_edit.json');assert json.loads(text)==edit
            candidate,_=p.prior.p.TEXT_ADAPT(edit,initial)
            assert candidate==read(mf/'candidate.json')
            assert candidate['assertions'][0]==initial['assertions'][0]
            for supplied,rendered in zip(edit['assertions'],candidate['assertions'][1:]):
                assert supplied['antecedent']==rendered['antecedent']
                assert supplied['consequent']==rendered['consequent']
            if measurement['reason']['kind']=='repeated_executable_proposal':
                assert x.signature(candidate) in {x.signature(initial),x.signature(current)}
                assert not (folder/'native').exists();candidate=None
            else:
                assert x.signature(candidate) not in {x.signature(initial),x.signature(current)}
                n,ev,records=inspect_version(folder/'native',candidate,base);rows+=n
                assert measurement['reason']['kind']=='native_measured'
        assert measurement['decisions']==(p.decisions(ev) if ev else {a:False for a in p.ARMS})
        measured[item['path']]=dict(decisions=measurement['decisions'],candidate=candidate,ev=ev)
        if index==0:
            first_candidate=candidate;first_records=records;first_ev=ev;first_reason=copy.deepcopy(measurement['reason'])
        edit=read(mf/'model_edit.json') if (mf/'model_edit.json').exists() else None
        raw_predicates=[{k:a.get(k) for k in ('antecedent','consequent','timing','obligations')} for a in edit.get('assertions',[])] if edit else None
        versions.append(dict(path=item['path'],raw_response=raw,decisions=measurement['decisions'],
            candidate_status=call.get('candidate_status'),candidate_error=call.get('candidate_error'),
            raw_model_predicates=raw_predicates,
            same_predicate_fields_as_shared=(raw_predicates==versions[0]['raw_model_predicates']) if versions else None,
            reason=measurement['reason']['kind'],counts=ev['counts'] if ev else None,
            new_false_alarms=len(ev['new_false_alarm_ids']) if ev else None,
            lost_detections=len(ev['lost_detection_ids']) if ev else None,
            retained_detections=len(ev['retained_detection_ids']) if ev else None))
        if call['status']!='response_received':assert index==len(ledger)-1
    first=measured['shared/v0']['decisions'];active={};states=read(trial/'states.json')
    for arm in p.ARMS:
        previous=initial
        paths=[(trial/'arms'/arm/'v0',measured['shared/v0'])]
        key=f'arms/{arm}/v1'
        if key in measured:paths.append((trial/key/'transition',measured[key]))
        for folder,m in paths:
            t=read(folder/'transition.json');accepted=m['decisions'][arm]
            assert t['accepted']==accepted
            assert read(folder/'before.json')==previous
            assert t['previous_sha256']==x.old.acceptance.sha(previous)
            assert t['proposal_sha256']==(x.old.acceptance.sha(m['candidate']) if m['candidate'] else None)
            expected=m['candidate'] if accepted else previous
            assert read(folder/'active.json')==expected
            assert t['active_sha256']==x.old.acceptance.sha(expected) and t['rollback_verified']
            previous=expected
        active[arm]=previous
        assert states[arm]==dict(accepted=paths[-1][1]['decisions'][arm],logical_calls=len(paths),
            initial_extra_rejection=bool(first['O'] and not first[arm]))
        assert read(trial/'terminal'/arm/'candidate.json')==previous
    assert read(trial/'terminal_versions.json')=={a:x.old.acceptance.sha(c) for a,c in active.items()}
    outcome=read(trial/'outcome.json');cost=read(trial/'cost.json')['total']
    assert cost['model_calls']==len(calls)==outcome['actual_model_calls']
    assert cost['native_compile_calls']<=30 and cost['native_execute_calls']<=30
    charged=sum(c['prompt_tokens']+c['completion_tokens'] if c.get('prompt_tokens') is not None and c.get('completion_tokens') is not None else c['token_budget_reservation'] for c in calls)
    assert charged<=120000
    assert outcome['accepted_arms']==sum(s['accepted'] for s in states.values())
    assert outcome['unique_accepted_versions']==len({x.old.acceptance.sha(active[a]) for a in p.ARMS if states[a]['accepted']})
    stopped=any(c['status']!='response_received' for c in calls)
    assert outcome['transport_stopped']==stopped
    tests=None
    if (trial/'independent_summary.json').exists():
        assert not stopped and outcome['accepted_arms']>0
        tests=read(trial/'independent_summary.json');freeze=read(trial/'freeze.json')
        generation=read(trial/'generation.json');cases=read(trial/'independent_cases.json')
        assert generation['at']>freeze['time'] and generation['freeze_sha256']==sha(trial/'freeze.json')
        assert freeze['development_exclusion_sha256']==sha(prep/'excluded_words.json')
        assert cases==x.holdout.base.generate(generation['seed'],read(prep/'excluded_words.json'))
        assert len({t['instruction'] for t in cases})==96
        assert not {t['instruction'] for t in cases}&set(read(prep/'excluded_words.json'))
        for arm,candidate in active.items():
            f=trial/'frozen'/arm;result=read(f/'independent/result.json')
            assert read(f/'candidate.json')==candidate and x.old.acceptance.sha(candidate)==freeze['versions'][arm]
            assert read(f/'independent_cases.json')==cases
            for rev in ('before','after'):
                for src in (prep/rev).glob('*.sv'):assert sha(src)==sha(f/rev/src.name)
            if result['healthy']:
                rows+=x.holdout.base.native_audit(f,result)['rows_audited']
                with patch.object(x.old,'CONFIGS',x.holdout.base.CONFIGS):guard=x.all_guard(f/'independent',result,candidate)
                assert tests[arm]==x.holdout.summarize(result,guard)
            else:assert not tests[arm]['passed']
    assert outcome['independent_executed']==(tests is not None)
    eligible=bool(not stopped and tests and any(states[a]['initial_extra_rejection'] and states[a]['accepted'] and tests[a]['passed'] for a in ('H','R')))
    decision=read(trial/'pilot_decision.json')
    assert decision['eligible_to_request_multiseed']==eligible and not decision['automatic_expansion']
    assert decision['first_shared_decisions']==first and decision['states']==states
    x.verify(prep);assert p.protected_snapshot()==read(prep/'protected93.json')
    audit=dict(passed=True,native_rows_recomputed=rows,actual_calls=len(calls),
        unique_new_accepted_versions=outcome['unique_accepted_versions'],
        first_paired_decisions=first,prospective_extra_rejection=bool(first['O'] and (not first['H'] or not first['R'])),
        qualified_rejection_recovery_independent_chain=eligible,
        request_feedback_isolation_verified=True,raw_model_predicates_unchanged=True,
        rollback_verified=True,freeze_before_new_test_verified=tests is not None,
        prior_research93_unchanged=True,no_expansion=True,script_sha256=sha(Path(__file__)))
    out.mkdir(parents=True,exist_ok=False)
    for name,obj in [('audit',audit),('versions',versions),('cost',cost),('independent_summary',tests)]:dump(out/f'{name}.json',obj)
    lines=['# research94 / 97 前瞻性三规则先导验收','',
        f"实际调用 {len(calls)}/4；新接受的不同版本 {outcome['unique_accepted_versions']}；接受组 {outcome['accepted_arms']}/3。",
        f"首个同一真实提案的接受决定：普通 O={first['O']}，同历史绝对 H={first['H']}，防退化 R={first['R']}。",
        f"符合预设的额外拒绝→预算内恢复→新独立通过链：{eligible}。不自动扩种子。",'',
        '|实际提案|O接受|H接受|R接受|新增合法误报|丢失旧检出|',
        '|---|---|---|---|---:|---:|']
    for v in versions:lines.append(f"|{v['path']}|{v['decisions']['O']}|{v['decisions']['H']}|{v['decisions']['R']}|{v['new_false_alarms']}|{v['lost_detections']}|")
    lines+=['','各提案的完整目标、历史、必要触发和unknown统计见versions.json及原始native/decision.json。没有把模型文本变化或编译成功当作完整接受。', '',
        '## 实际修改轨迹','']
    for v in versions:
        lines.append(f"- {v['path']}：{v['candidate_status']}；与首版前件/后件/时序/义务字段完全相同：{v['same_predicate_fields_as_shared']}。")
        if v['candidate_error']:lines.append('  原始拒绝诊断：`'+json.dumps(v['candidate_error'],ensure_ascii=False)+'`')
        for prop in v['raw_model_predicates'] or []:
            lines+=['```json',json.dumps(prop,ensure_ascii=False),'```']
    lines+=['','接口拒绝版本仅逐字审计其原始响应字段，没有删除多余字段后重新当作模型合格输出，也没有为这些版本补写原生检出结果。', '',
        '|冻结组|独立通过|检出|漏报|合法误报|unknown|必要未触发|','|---|---|---:|---:|---:|---:|---:|']
    if tests:
        for arm,t in tests.items():
            c=t['counts'];lines.append(f"|{arm}|{t['passed']}|{c['detections']}|{c['misses']}|{c['false_positives']}|{c['unknown']}|{t.get('required_untriggered')}|")
    else:lines.append('|未启动|||||||')
    lines+=['','新测试为全部终态冻结之后生成的96个新指令字、四种配置，排除已用开发/测试指令。三组使用同一批测试，不能算作三个独立样本总体；相同提案被三组接受也只算一个新版本。', '',
        f"成本：模型 {cost['model_calls']}次，输入/输出 tokens {cost['prompt_tokens_total']}/{cost['completion_tokens_total']}，原生编译/执行 {cost['native_compile_calls']}/{cost['native_execute_calls']}，编译冒烟 {cost['compile_smoke_execute_calls']}；形式化0。准备阶段另有18次原生编译/执行，不混入本轮生成成本。",'',
        f"只读审计重算 {rows} 条原生记录；逐字核对服务响应到模型性质、反馈隔离、三规则、回退及冻结哈希。",'',
        '该先导是已知原始Ibex #166 decoder任务上的前瞻性新提案，不是新父案例抽样。H与R共享完整历史信息并可能等价；不能把共同拒绝归因于相对比较器的独有优势。若没有额外拒绝，完整生成与独立通过也不能替代机制增量证据。有限仿真不构成形式化证明。','',
        '复核（无模型调用）：','```powershell',
        f'wsl -- python3 scripts/research97_pilot_result_audit.py --prepared {prep.relative_to(ROOT).as_posix()} --run {trial.relative_to(ROOT).as_posix()} --out deliverables/research97_audit_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    dump(out/'bindings.json',{f.relative_to(ROOT).as_posix():sha(f) for f in [prep/'sealed.json',trial/'authorization.json',trial/'outcome.json',trial/'pilot_decision.json',trial/'cost.json']})
    print('AUDIT97',audit,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('prepared','run','out'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
