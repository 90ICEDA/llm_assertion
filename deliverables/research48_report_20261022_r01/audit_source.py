"""Read-only audit of the real SVA continuation; never calls a model or simulator."""
import argparse
import json
from pathlib import Path
import shutil
import research48_sva_campaign as campaign

read,dump=campaign.read,campaign.dump


def audit(run,out):
    out.mkdir(parents=True,exist_ok=False)
    prep=campaign.gate.portable(read(run/'prepared_source.json')['path'])
    checks=[];rows=[]
    def check(name,passed):checks.append(dict(name=name,passed=bool(passed)))
    for name,h in read(prep/'prepared_hashes.json').items():check('prepared:'+name,campaign.common.digest(prep/name)==h)
    for name,h in read(prep/'source_snapshot/hashes.json').items():check('executed_source:'+name,campaign.common.digest(run/'source_snapshot'/name)==h)
    check('actual_protocol',read(run/'protocol.json')==read(prep/'protocol.json'))
    plan,expected,verdict=campaign.accepted_plan(prep)
    initial=current=read(prep/'shared_initial.json')
    before=read(prep/'core/initial_native/result.json');historical=campaign.history_source(prep)
    template=request=read(prep/'request.preview.json')
    accepted=False;rejected=set();previous_edit=None
    for version in sorted((run/'core').glob('v*')):
        folder=version/'model_call';label=version.name
        check(label+':no_call_after_acceptance',not accepted)
        check(label+':exact_request',read(folder/'request.json')==request)
        candidate=read(folder/'candidate.json') if (folder/'candidate.json').exists() else None
        edit=read(folder/'model_edit.json') if (folder/'model_edit.json').exists() else None
        if edit is not None:check(label+':raw_response',campaign.raw_response(folder,edit))
        if candidate is not None:check(label+':no_manual_sva_rewrite',candidate==campaign.interface.assemble(edit,current))
        key=campaign.interface.executable_hash(candidate) if candidate else None
        repeated=bool(key and key in rejected)
        small=read(version/'visible_native/result.json') if candidate else None
        current_gate=(campaign.common.current_decision(before,small,edit) if candidate
            else dict(accepted=False,reasons=[dict(kind='unusable_model_output')]))
        window=(campaign.windows.native_window_gate(version/'visible_native',read(prep/'cases.json'),candidate,edit['assertion_id'],expected)
            if candidate and small.get('group') and edit['operation']=='replace_one'
            else dict(accepted=False,reasons=[dict(kind='native_window_check_unavailable')]))
        full=read(version/'history_native/result.json') if candidate and small.get('group') else None
        hgate=(campaign.gate.decide(historical['group']['ledger'],full['group']['ledger']) if full and full.get('group')
            else dict(accepted=False,reasons=[dict(kind='history_unavailable')]))
        reasons=current_gate['reasons']+window['reasons']+hgate['reasons']
        if not full or not full['healthy']:reasons.append(dict(kind='history_native_unhealthy'))
        if repeated:reasons.append(dict(kind='repeated_previously_rejected_executable'))
        okay=bool(current_gate['accepted'] and window['accepted'] and hgate['accepted'] and full and full['healthy'] and not reasons)
        saved=read(version/'decision.json')
        check(label+':current_gate',current_gate==read(version/'current_gate.json'))
        check(label+':window_gate',window==read(version/'native_window_gate.json'))
        check(label+':history_gate',hgate==read(version/'history_gate.json'))
        check(label+':final_acceptance',saved['accepted']==okay and saved['reasons']==reasons)
        check(label+':obligation_mapping',read(version/'obligation_mapping.json')==dict(current=campaign.mapping(small),history=campaign.mapping(full)))
        if full and full.get('group'):
            cases=read(prep/'history_cases.json')
            check(label+':exact105_history_cases',len(cases)==105 and all(read(version/f'history_native/case_{i}/case.json')==c for i,c in enumerate(cases)))
        rows.append(dict(version=label,accepted=okay,executable_hash=key,repeated=repeated,
            reason_kinds=sorted({r['kind'] for r in reasons}),current_counts=small.get('counts') if small else None,
            history_counts=full.get('counts') if full else None,edit=edit))
        if okay:current=candidate;accepted=True
        else:
            if key:rejected.add(key)
            diagnostic=campaign.prior.attempt_feedback(small,full,saved,read(folder/'result.json'),edit,previous_edit)
            diagnostic['validated_windows_native_rejection']=window
            diagnostic['repeated_previously_rejected_executable']=repeated
            check(label+':only_actual_failure_feedback',diagnostic==read(version/'next_feedback.json'))
            updated=campaign.prior.request_from(template,current,campaign.windows.SEED,diagnostic)
            request=campaign.plan_gate.verified_sva_request(updated,plan,verdict,expected)
            previous_edit=edit
    outcome=read(run/'outcome.json');auth=read(run/'authorization.json')
    check('call_bound',1<=len(rows)<=auth['authorized_sva_calls']<=3)
    check('accepted_outcome',outcome['accepted']==accepted)
    check('retained_or_accepted_frozen_candidate',read(run/'core/frozen_candidate.json')==current)
    check('frozen_hash',read(run/'core/freeze.json')['candidate_sha256']==campaign.loop.sha(current)==outcome['frozen_hash'])
    check('no_new_plan_calls',not (run/'plan').exists() and outcome['plan_calls']==0)
    check('no_independent_test_claim',not (run/'independent').exists() and outcome['independent_test_run'] is False)
    check('prior_versions_unchanged',campaign.common.protected()==read(prep/'protected.json'))
    cost=campaign.cost_audit(run,campaign.common.files(run))
    check('cost',cost==read(run/'cost.json'))
    dump(out/'audit.json',dict(passed=all(c['passed'] for c in checks),checks=checks))
    dump(out/'results.json',dict(outcome=outcome,attempts=rows,cost=cost['total']))
    text='# research48：真实SVA细化与原生接受检查\n\n'
    text+='终态：'+outcome['status']+'。新版本接受：'+str(accepted)+'。\n\n'
    text+='|轮次|接受|重复已拒性质|当前结果|历史结果|拒绝原因|\n|---|---|---|---|---|---|\n'
    for row in rows:
        def brief(counts):
            if not counts:return '不可用'
            return '/'.join(f'{k}={counts[k]}' for k in ('detections','misses','false_positives','unknown','later_attribution_unknown'))
        text+=f'|{row["version"]}|{row["accepted"]}|{row["repeated"]}|{brief(row["current_counts"])}|{brief(row["history_counts"])}|'+','.join(row['reason_kinds'])+'|\n'
    text+='\n计数为义务×采样周期证据行，不是独立Bug；后续归因unknown保留。历史防退化仅限实际回放证据。'
    text+='本阶段无新独立测试；接受新版本也不等于独立验收通过或形式化证明。\n\n'
    text+='实际成本：\n\n```json\n'+json.dumps(cost['total'],ensure_ascii=False,indent=2)+'\n```\n'
    text+=f'\n只读审计 {sum(c["passed"] for c in checks)}/{len(checks)} 通过。请求、响应、各版SVA、原生工具日志和波形见运行目录core/v*/；义务映射见各轮obligation_mapping.json。\n'
    (out/'SUMMARY.md').write_text(text,encoding='utf-8');shutil.copy2(Path(__file__),out/'audit_source.py')
    assert all(c['passed'] for c in checks),'audit_failed'
    print('AUDITED',len(checks),'accepted',accepted,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    a=p.parse_args();audit(a.run.resolve(),a.out.resolve())
