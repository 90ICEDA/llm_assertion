"""Read-only audit: event pass must precede SVA and native sample coverage."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import research46_cycle_gate as campaign
import research43_paired_ablation as common
import research44_interface as interface
import research45_campaign as prior
import research17_loop as loop
import research31_gate as gate
from research36_applicability import validate_events
from research28_report import raw_response
from research17_report import cost_audit
from research29_drain import assess

read,dump=loop.read,loop.dump


def audit(run,out):
    out.mkdir(parents=True,exist_ok=False)
    prep=gate.portable(read(run/'prepared_source.json')['path'])
    outcome=read(run/'outcome.json');expected=read(prep/'expected.private.json')
    checks=[];plans=[];edits=[];accepted_plan=None;plan_gate=None
    def check(name,value):checks.append(dict(name=name,passed=bool(value)))
    for name,h in read(prep/'prepared_hashes.json').items():check('prepared:'+name,common.digest(prep/name)==h)
    for name,h in read(prep/'source_snapshot/hashes.json').items():check('source:'+name,common.digest(run/'source_snapshot'/name)==h)
    check('old_versions_unchanged',common.protected()==read(prep/'protected.json'))
    request=read(prep/'plan_request.preview.json')
    for version in sorted((run/'plan').glob('v*')):
        folder=version/'model_call';check(version.name+':before_plan_accept',accepted_plan is None)
        check(version.name+':plan_request',read(folder/'request.json')==request)
        value=read(folder/'applicability_plan.json') if (folder/'applicability_plan.json').exists() else None
        if value is not None:check(version.name+':raw_plan',raw_response(folder,value))
        verdict=validate_events(value,expected);check(version.name+':independent_event_gate',verdict==read(version/'decision.json'))
        plans.append(dict(version=version.name,plan=value,gate=verdict,call=read(folder/'result.json')))
        if verdict['accepted']:accepted_plan=value;plan_gate=verdict
        body=json.loads(request['messages'][1]['content']);body.update(prior_actual_model_plan=value,prior_actual_rejection=verdict['reasons'])
        request['messages'][1]['content']=json.dumps(body)
    check('bounded_plans',1<=len(plans)<=2)
    initial=current=read(prep/'shared_initial.json');cases=read(prep/'cases.json')
    baseline=campaign.bound_baseline(prep)
    binding=read(prep/'history_binding.json');historical=read(gate.portable(binding['path']))
    template=read(prep/'sva_request.template.json')
    request=campaign.verified_sva_request(template,accepted_plan,plan_gate,expected) if accepted_plan else None
    accepted=False;last_full=None
    versions=sorted((run/'core').glob('v*'))
    if accepted_plan is None:check('failed_plan_blocks_all_sva',not versions and not (run/'sva').exists())
    else:
        check('saved_plan_is_actual',read(run/'accepted_plan.json')==accepted_plan and read(run/'accepted_plan_gate.json')==plan_gate)
    for version in versions:
        folder=version/'model_call';label='sva/'+version.name
        check(label+':no_sva_before_plan',accepted_plan is not None and folder.stat().st_mtime>=(run/'accepted_plan_gate.json').stat().st_mtime)
        check(label+':no_call_after_accept',not accepted)
        check(label+':exact_passed_plan_request',read(folder/'request.json')==request)
        edit=read(folder/'model_edit.json') if (folder/'model_edit.json').exists() else None
        candidate=read(folder/'candidate.json') if (folder/'candidate.json').exists() else None
        if edit is not None:check(label+':raw_edit',raw_response(folder,edit))
        if candidate is not None:check(label+':no_predicate_rewrite',candidate==interface.assemble(edit,initial))
        small=read(version/'visible_native/result.json') if candidate else None
        verdict=common.current_decision(baseline,small,edit) if candidate else dict(accepted=False,reasons=[dict(kind='unusable_sva_output')])
        check(label+':current_gate',verdict==read(version/'current_gate.json'))
        window=(campaign.native_window_gate(version/'visible_native',cases,candidate,edit['assertion_id'],expected)
            if candidate and small.get('group') and edit['operation']=='replace_one'
            else dict(accepted=False,reasons=[dict(kind='window_check_unavailable')]))
        check(label+':native_cycle_window_gate',window==read(version/'native_window_gate.json'))
        reasons=list(verdict['reasons'])+window['reasons'];full=None
        if verdict['accepted'] and window['accepted']:
            full=read(version/'history_native/result.json')
            hgate=gate.decide(historical['group']['ledger'],full['group']['ledger']) if full.get('group') else dict(accepted=False,reasons=[dict(kind='history_unavailable')])
            check(label+':history_gate',hgate==read(version/'history_gate.json'))
            reasons+=hgate['reasons']
            if not full['healthy']:reasons.append(dict(kind='history_native_unhealthy'))
        else:check(label+':failed_windows_stop_history',not (version/'history_native').exists())
        accepted=bool(verdict['accepted'] and window['accepted'] and full and full['healthy'] and not reasons)
        final=dict(accepted=accepted,reasons=reasons)
        check(label+':acceptance',final==read(version/'decision.json'))
        edits.append(dict(version=version.name,edit=edit,decision=final,window_gate=window,
            current=small.get('counts') if small else None,history=full.get('counts') if full else None,call=read(folder/'result.json')))
        if accepted:current=candidate;last_full=full
        else:
            diagnostic=prior.attempt_feedback(small,full,final,read(folder/'result.json'),edit)
            diagnostic['validated_windows_native_rejection']=window
            check(label+':actual_feedback',diagnostic==read(version/'next_feedback.json'))
            updated=prior.request_from(template,initial,campaign.SEED,diagnostic)
            request=campaign.verified_sva_request(updated,accepted_plan,plan_gate,expected)
    check('bounded_sva',len(versions)<=2 and (accepted_plan is None or len(versions)>=1))
    check('final_candidate',read(run/'core/frozen_candidate.json')==current and read(run/'core/freeze.json')['candidate_sha256']==loop.sha(current))
    check('terminal_flags',outcome['plan_passed']==bool(accepted_plan) and outcome['sva_accepted']==accepted)
    independent=None
    if accepted:
        folder=run/'independent';split=read(folder/'split.json');independent=read(folder/'summary.json')
        rows=split['boundary_cases']+split['drain_cases'];hashes={loop.sha(c['rows']) for c in rows}
        excluded=set(read(prep/'excluded_tests.json')['input_hashes'])|{loop.sha(c['rows']) for c in read(prep/'history_cases.json')+cases}
        check('fresh_56_48',len(rows)==56 and len(hashes)==48 and not hashes&excluded)
        check('test_after_freeze',(folder/'split.json').stat().st_mtime>=(run/'core/freeze.json').stat().st_mtime)
        combined=read(folder/'combined.json');metrics=prior.metrics(combined)
        drain=assess(folder/'drain',split['drain_cases'],read(folder/'drain/result.json'))
        okay=combined['healthy'] and drain['passed'] and all(v['detections']>0 and v['triggers']>0 and not any(v[k] for k in ('misses','false_positives','unknown')) for v in metrics['obligations'].values())
        check('independent_metrics',metrics==independent['metrics'])
        check('independent_acceptance',bool(okay)==independent['all_five_pass_on_first_attributed_evidence'])
    else:check('no_test_after_rejected_candidate',not (run/'independent').exists())
    cost=cost_audit(run,common.files(run));check('actual_calls',cost['total']['model_calls']==len(plans)+len(edits)==outcome['model_calls']<=4)
    check('no_retries',all(v['call']['retries']==0 for v in plans+edits))
    result=dict(audit_passed=all(c['passed'] for c in checks),checks=checks,outcome=outcome,plans=plans,edits=edits,independent=independent,cost=cost['total'],
        scope='Eleven selected development windows, finite native history and post-freeze test if reached. Event success does not imply SVA correctness or general understanding.')
    dump(out/'results.json',result);dump(out/'cost.json',cost)
    lines=['# research46：先验收周期判断，再允许SVA','',f"终态：{outcome['status']}。记录审计 {sum(c['passed'] for c in checks)}/{len(checks)}。",'',
        f"真实周期判断调用 {len(plans)}，判断通过 {bool(accepted_plan)}；真实SVA调用 {len(edits)}，接受 {accepted}；独立验收已执行 {independent is not None}。",'',
        '逐窗口判断、原生触发对应、拒绝原因及模型用量见results.json。失败与unknown不计通过，未达到的阶段不计完成。','','```json',json.dumps(cost['total'],ensure_ascii=False,indent=2),'```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');shutil.copy2(__file__,out/'audit_source.py')
    print('AUDIT',result['audit_passed'],len(checks),flush=True);assert result['audit_passed'],[c for c in checks if not c['passed']]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.run.resolve(),a.out.resolve())
