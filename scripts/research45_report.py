"""Read-only acceptance, isolation and cost audit for the bounded campaign."""
import argparse
import json
from pathlib import Path
import shutil
import research45_campaign as campaign
import research43_paired_ablation as old
import research44_interface as interface
import research17_loop as loop
import research31_gate as gate
from research28_report import raw_response
from research17_report import cost_audit
from research29_drain import assess

read,dump=loop.read,loop.dump


def report(run,out):
    out.mkdir(parents=True,exist_ok=False)
    prep=gate.portable(read(run/'prepared_source.json')['path'])
    outcome=read(run/'outcome.json');initial=read(prep/'shared_initial.json')
    checks=[];examples=[];tests={};arms={}
    def check(name,value):checks.append(dict(name=name,passed=bool(value)))
    check('prior_versions_unchanged',old.protected()==read(prep/'protected.json'))
    amendment=run/'amendments/feedback_scope_v1/amendment.json'
    if amendment.exists():
        saved=read(amendment.parent/'preserved_round0_hashes.json')
        check('completed_first_round_preserved',all(old.digest(run/p)==h for p,h in saved.items()))
        check('amended_code_bound',old.digest(run/'amendments/feedback_scope_v1/research45_campaign.py')==read(amendment)['new_campaign_sha256'])
    check('within_authorized_budget',outcome['actual_calls']<=11 and outcome['reserved_calls']<=11)
    paths=list(run.glob('pilot/core/v*/model_call'))+list(run.glob('arms/*/core/v*/model_call'))
    check('physical_call_count',len(paths)==outcome['actual_calls'])
    historic=read(gate.portable(read(prep/'history_binding.json')['path']))
    for folder in sorted(paths):
        version=folder.parent;root=version.parent.parent
        name=root.relative_to(run).as_posix()
        use_gate=name=='pilot' or name in ('arms/C','arms/D')
        label=version.relative_to(run).as_posix()
        request=read(folder/'request.json')
        body=json.loads(request['messages'][1]['content'])
        check(label+':metadata_schema','maxLength' not in body['output_schema']['properties']['reason'])
        check(label+':token_cap',request['max_tokens']==2048)
        if version.name=='v0':check(label+':sealed_first_request',request==read(prep/name/'request.preview.json'))
        check(label+':no_successful_prior_candidate',not any(x in json.dumps(request) for x in ('research40','research41','independent_test')))
        previous=body.get('actual_previous_attempt')
        if previous and not use_gate:
            check(label+':no_hidden_history_section','historical_replay' not in previous)
            allowed={c['id'] for c in read(prep/name/'cases.json')}
            cards=sum([previous.get(k,[]) for k in ('legal_false_alarms','missed_obligations','unknown')],[])
            check(label+':no_hidden_history_cards',all(c['scenario'] in allowed for c in cards))
        decision=read(version/'decision.json')
        if (folder/'candidate.json').exists():
            edit=read(folder/'model_edit.json');candidate=read(folder/'candidate.json')
            check(label+':raw_response',raw_response(folder,edit))
            check(label+':no_predicate_rewrite',interface.assemble(edit,initial)==candidate)
            small=read(version/'visible_native/result.json')
            plain=old.current_decision(campaign.baseline(prep,name),small,edit)
            check(label+':current_gate',plain==read(version/'plain_decision.json'))
            full=read(version/'history_native/result.json') if use_gate else None
            history=(gate.decide(historic['group']['ledger'],full['group']['ledger'])
                if full and full.get('group') else dict(accepted=False,reasons=[dict(kind='history_not_executed')]))
            if use_gate:check(label+':history_gate',history==read(version/'history_gate.json'))
            expected=bool(plain['accepted'] and (not use_gate or (full and full['healthy'] and history['accepted'])))
            check(label+':decision',decision['accepted']==expected)
            examples.append(dict(version=label,model_edit=edit,properties=candidate['assertions'],decision=decision))
        else:check(label+':no_candidate_not_accepted',not decision['accepted'])
        if not use_gate:check(label+':no_history_during_refinement',not (version/'history_native').exists())
    phase_names=['pilot']+([f'arms/{n}' for n in campaign.previous.ARMS] if (run/'all_arms_freeze.json').exists() else [])
    for name in phase_names:
        folder=run/name;terminal=read(folder/'outcome.json')
        accepted=[p for p in sorted((folder/'core').glob('v*/decision.json')) if read(p)['accepted']]
        candidate=read(accepted[0].parent/'model_call/candidate.json') if accepted else initial
        check(name+':terminal_version',candidate==read(folder/'core/frozen_candidate.json'))
        check(name+':freeze_hash',loop.sha(candidate)==read(folder/'core/freeze.json')['candidate_sha256'])
        arms[name]=dict(accepted=terminal['accepted'],new_executable_version=terminal['new_executable_version'],calls=terminal['calls'])
    excluded=set(read(prep/'excluded_tests.json')['input_hashes'])
    development=read(prep/'history_cases.json')+read(prep/'pilot/cases.json')+read(prep/'arms/D/cases.json')
    used=excluded|{loop.sha(c['rows']) for c in development}
    test_paths=list(run.glob('pilot/independent/split.json'))+list(run.glob('evaluation/*/independent/split.json'))
    for path in test_paths:
        split=read(path);folder=path.parent;label=folder.relative_to(run).as_posix()
        rows=split['boundary_cases']+split['drain_cases'];hashes={loop.sha(c['rows']) for c in rows}
        check(label+':fresh_56_48',len(rows)==56 and len(hashes)==48 and not used&hashes)
        if folder.parent.name=='pilot':
            check(label+':after_freeze',path.stat().st_mtime>=(folder.parent/'core/freeze.json').stat().st_mtime)
        else:
            check(label+':after_all_freezes',path.stat().st_mtime>=(run/'all_arms_freeze.json').stat().st_mtime)
            check(label+':same_shared_batch',all(split[k]==read(run/'common_independent_split.json')[k] for k in ('seed','boundary_cases','drain_cases')))
            pilot_split=read(run/'pilot/independent/split.json')
            check(label+':not_pilot_test',not hashes&{loop.sha(c['rows']) for c in pilot_split['boundary_cases']+pilot_split['drain_cases']})
        combined=read(folder/'combined.json');summary=read(folder/'summary.json')
        m=campaign.metrics(combined);check(label+':metrics',summary['metrics']==m)
        drain=assess(folder/'drain',split['drain_cases'],read(folder/'drain/result.json'))
        check(label+':drain',drain==read(folder/'drain_assessment.json'))
        okay=combined['healthy'] and drain['passed'] and all(v['detections']>0 and v['triggers']>0 and not any(v[k] for k in ('misses','false_positives','unknown')) for v in m['obligations'].values())
        check(label+':acceptance',bool(okay)==summary['all_five_pass_on_first_attributed_evidence'])
        tests[label]=summary
    if outcome['arms']:
        check('ablation_conditional_on_pilot_pass',read(run/'pilot/independent/summary.json')['all_five_pass_on_first_attributed_evidence'])
        for name in campaign.previous.ARMS:
            binding=read(run/'arms'/name/'evaluation_binding.json');folder=run/binding['path']
            check(name+':measurement_binding',binding['candidate_hash']==read(run/'arms'/name/'core/freeze.json')['candidate_sha256']==read(folder/'core/freeze.json')['candidate_sha256'])
            arms[f'arms/{name}']['independent']=read(folder/'independent/summary.json')
            arms[f'arms/{name}']['historical_and_search_measurement']=read(folder/'measurement.json')
    cost=cost_audit(run,old.files(run))
    pilot_edits=[e['model_edit'] for e in examples if e['version'].startswith('pilot/')]
    unique_asts={loop.sha({k:v for k,v in e.items() if k!='reason'}) for e in pilot_edits}
    result=dict(audit_passed=all(c['passed'] for c in checks),checks=checks,outcome=outcome,arms=arms,tests=tests,cost=cost['total'],
        pilot_unique_executable_asts=len(unique_asts),independent_executed=bool(tests),ablation_executed=bool(outcome['arms']),
        authorization_remaining=11-outcome['actual_calls'],
        remaining_scope='Up to8 calls conditional on pilot new independent pass; not transferable to extra pilot attempts.',
        scope='Finite artificial-fault FIFO evidence. One conditional four-arm seed, independent calls and bounded feedback; no general mechanism advantage implied.')
    dump(out/'results.json',result);dump(out/'case_examples.json',examples);dump(out/'cost.json',cost)
    lines=['# research45 实际验收','',f"终态：{outcome['status']}。记录审计 {sum(c['passed'] for c in checks)}/{len(checks)}。",'',
        '|阶段/组|接受|新可执行版本|实际调用|','|---|---|---|---:|']
    for name,a in arms.items():lines.append(f"|{name}|{a['accepted']}|{a['new_executable_version']}|{a['calls']}|")
    lines+=['',f"先导完整提案的可执行AST结构数：{len(unique_asts)}。新独立验收已执行：{bool(tests)}；四组消融已执行：{bool(outcome['arms'])}。",
        f"本次授权剩余 {11-outcome['actual_calls']} 次；剩余消融额度以先导独立通过为条件，不能转用于追加先导。",
        '原始提案、拒绝/接受、历史回放及独立验收见 results.json、case_examples.json 和运行目录。未启动阶段不计为通过。',
        '独立测试不用于修改或选择候选；有限回放不等于形式化证明，单个种子不代表稳定机制收益。','','实际物理成本：','```json',json.dumps(cost['total'],ensure_ascii=False,indent=2),'```']
    if amendment.exists():lines+=['','首轮拒绝后曾因公共场景重复证据ID的反馈合并错误停止。修改为当前/历史反馈分别保存后恢复；原请求、响应、执行和决定哈希已核验不变，旧调用及成本计入。该实现修正及原始异常终态见运行目录amendments/feedback_scope_v1，不能称为未发生协议实施变更的预注册实验。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');shutil.copy2(__file__,out/'audit_source.py')
    print('AUDIT',result['audit_passed'],len(checks),flush=True)
    assert result['audit_passed'],[c for c in checks if not c['passed']]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();report(a.run.resolve(),a.out.resolve())
