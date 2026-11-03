"""Audit pilot requests, reservations, native records, freezes and fresh tests."""
import argparse
import json
from pathlib import Path
import research80_presentation_pilot as c
from research28_report import raw_response

b,read,dump=c.b,c.read,c.dump


def prepare(prep,out):
    c.verify(prep);out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):assert ok,name;checks.append(name)
    protocol=read(prep/'protocol.json');parent=read(c.P/'protocol/protocol.json')
    check('pilot seed only',protocol['seed']==parent['seeds'][0]==7907 and not protocol['automatic_expansion'])
    check('8 slots not16',protocol['maximum_calls']==8 and protocol['retries']==0 and not protocol['slot_transfer'])
    check('budget unit controls passed',read(prep/'budget_checks.json')['passed'])
    check('request local qualification passed',read(prep/'preflight.json')['passed'])
    for arm in c.ARMS:
        folder=prep/'arms'/arm;req=read(folder/'request.preview.json');body=json.loads(req['messages'][1]['content'])
        check(arm+': exact preregistered preview',req==read(c.P/f'protocol/previews/s7907/{arm}/request.preview.json'))
        check(arm+': scalar full schema',body['response_schema']==c.g.schema(read(folder/'windows.private.json')))
        check(arm+': unchanged initial',read(prep/'initial.json')==read(c.BASE/'initial.json'))
        check(arm+': no executable model response',not (folder/'accepted_plan.json').exists())
        cfg=read(folder/'model_config.json')
        check(arm+': single-call object configuration',cfg['max_model_calls']==1 and cfg['remote_url']==protocol['endpoint'] and cfg['remote_model']==protocol['model'])
    for name in ('cases.json','history_cases.json','window_cases.json','excluded_inputs.json','protected.json'):
        check('unchanged '+name,read(prep/name)==read(c.BASE/name))
    dump(out/'audit.json',dict(passed=True,checks=checks,model_calls=0,new_native_calls=0,
        sealed_sha256=b.search.digest(prep/'sealed.json'),code_sha256=b.search.digest(Path(__file__))))
    print('PREFLIGHT',len(checks),flush=True)


def result(prep,root,out):
    c.verify(prep);out.mkdir(parents=True,exist_ok=False);checks=[];raw=0;details=[]
    def check(name,ok):assert ok,name;checks.append(name)
    outcome=read(root/'outcome.json');budget=read(root/'budget.json');initial=read(prep/'initial.json')
    auth=read(root/'authorization.json');protocol=read(prep/'protocol.json')
    check('explicit bounded pilot authorization',auth['authorized_calls']==8 and auth['seed']==7907 and auth['prepared_sha256']==b.search.digest(prep/'sealed.json'))
    check('no second seed or automatic expansion',outcome['seed']==7907 and not outcome['automatic_expansion'])
    reserves=[e for e in budget['events'] if e['kind']=='model_reserved'];attempts=list(root.glob('arms/*/plan/v0/model_call/attempt.json'))+list(root.glob('arms/*/core/v0/model_call/attempt.json'))
    check('bounded calls and reservations',len(attempts)==outcome['actual_model_calls']<=len(reserves)==outcome['reserved_slots']<=8)
    check('one slot per stage and arm',len({(e['arm'],e['stage']) for e in reserves})==len(reserves))
    check('character and output slots',all(e['characters']<=64000 for e in reserves))
    stops=[e for e in budget['events'] if e['kind']=='global_stop']
    check('no calls after global stop',not stops or all(e['at']<=stops[0]['at'] for e in reserves))
    before=read(c.g.old.sem.SOURCE/'baseline_public/result.json');historical=read(c.g.old.sem.SOURCE/'baseline_history/result.json')
    frozen={};accepted={}
    with b.extension.installed():
        for arm in c.ARMS:
            af=prep/'arms'/arm;loc=root/'arms'/arm;rows=read(af/'windows.private.json');current=initial
            plan_pass=False;accept=False;plan=None
            pm=loc/'plan/v0/model_call';sm=loc/'core/v0/model_call'
            for stage,mp in [('plan',pm),('sva',sm)]:
                if not (mp/'attempt.json').exists():continue
                request=read(mp/'request.json');reservation=next(e for e in reserves if e['arm']==arm and e['stage']==stage)
                check(arm+stage+': reserved request exact',b.loop.sha(request)==reservation['request_sha256'])
                check(arm+stage+': sampler bounds',request['seed']==7907 and request['model']==protocol['model'] and request['temperature']==0.2 and request['max_tokens']==2048)
                if stage=='plan':expected=read(af/'request.preview.json')
                else:
                    check(arm+': full plan before SVA',plan_pass)
                    expected=c.g.unlock(read(af/'sva_template.json'),plan,c.g.validate(plan,rows),rows)
                check(arm+stage+': own exact request only',request==expected)
                call=read(mp/'result.json')
                if call['status']!='response_received':check(arm+': transport stopped globally',budget['stopped']);continue
                if stage=='plan':
                    plan=read(mp/'hold_plan.json');check(arm+': original plan response',raw_response(mp,plan))
                    verdict=c.g.validate(plan,rows);check(arm+': complete plan recomputed',verdict==read(loc/'plan/v0/decision.json'))
                    plan_pass=verdict['accepted']
                    details.append(dict(arm=arm,stage='plan',accepted=plan_pass,reasons=verdict['reasons']))
                    check(arm+': rejection did not unlock generation',plan_pass or not (sm/'attempt.json').exists())
                else:
                    edit=read(mp/'model_edit.json') if (mp/'model_edit.json').exists() else None
                    candidate=read(mp/'candidate.json') if (mp/'candidate.json').exists() else None
                    if edit:check(arm+': original edit response',raw_response(mp,edit))
                    if candidate:check(arm+': exact unmodified SVA assembly',b.interface.assemble(edit,initial)==candidate)
                    version=mp.parent;results={}
                    for phase,filename in [('windows','window_cases.json'),('public','cases.json'),('history','history_cases.json')]:
                        folder=version/phase;results[phase]=read(folder/'result.json') if (folder/'result.json').exists() else None
                        if results[phase]:raw+=c.g.old.raw_replay(folder,read(prep/filename),candidate,checks)
                    wr,small,full=results['windows'],results['public'],results['history']
                    wg=c.g.old.sem.native_windows(wr,rows,read(prep/'window_cases.json'),version/'windows')
                    check(arm+': native window gate unchanged',wg==read(version/'window_gate.json'))
                    check(arm+': public only after native windows',small is None or wg['accepted'])
                    plain=b.paired.current_decision(before,small,edit) if small else dict(accepted=False,reasons=wg['reasons'])
                    check(arm+': history only after public pass',full is None or plain['accepted'])
                    decision=c.g.old.policy.decision_for(plain,full,historical,True)
                    check(arm+': full history decision recomputed',decision==read(version/'decision.json'))
                    accept=decision['accepted'];current=candidate if accept else initial
                    check(arm+': persistent active version correct',read(version/'active_candidate.json')==current)
                    details.append(dict(arm=arm,stage='sva',accepted=accept,reasons=decision['reasons'],
                        windows_passed=wg['accepted'],public=small.get('counts') if small else None,history=full.get('counts') if full else None))
            if (loc/'core/frozen_candidate.json').exists():
                frozen[arm]=read(loc/'core/frozen_candidate.json')
                check(arm+': exact frozen version',frozen[arm]==current)
            accepted[arm]=accept
            if (loc/'outcome.json').exists():check(arm+': truthful native outcome',read(loc/'outcome.json')['accepted']==accept)
        check('new accepted count',sum(accepted.values())==outcome['new_accepted_versions'])
        if (root/'independent_mapping.json').exists():
            mapping=read(root/'independent_mapping.json');split=read(root/'common_independent_split.json')
            freeze=read(root/'all_frozen.json')
            check('all versions frozen before test',set(frozen)==set(c.ARMS) and freeze['hashes']=={a:b.loop.sha(v) for a,v in frozen.items()})
            events=budget['events'];freeze_times=[e['at'] for e in events if e['kind']=='freeze'];test_times=[e['at'] for e in events if e['kind']=='native_reserved' and e['phase']=='independent']
            check('time ordering freeze before independent',len(freeze_times)==4 and min(test_times)>max(freeze_times))
            check('no model calls after independent begins',max(e['at'] for e in reserves)<min(test_times))
            check('new inputs excluded from development',not set(read(prep/'excluded_inputs.json')['input_hashes']) & {b.loop.sha(x['rows']) for x in split['boundary_cases']+split['drain_cases']})
            seen=set()
            from research35_campaign import join_results,metrics
            from research29_drain import assess
            for arm,m in mapping.items():
                check(arm+': test hash exact',m['candidate_hash']==b.loop.sha(frozen[arm]))
                folder=root/m['path']/'independent';actual_split=read(folder/'split.json')
                check(arm+': same fresh inputs',all(actual_split[k]==split[k] for k in ('seed','boundary_cases','drain_cases')))
                check(arm+': test bound to freeze',actual_split['frozen_hash']==m['candidate_hash'])
                if m['candidate_hash'] not in seen:
                    for phase,cf in [('boundary','boundary_cases'),('drain','drain_cases')]:raw+=c.g.old.raw_replay(folder/phase,actual_split[cf],frozen[arm],checks)
                    seen.add(m['candidate_hash'])
                boundary=read(folder/'boundary/result.json');drain=read(folder/'drain/result.json')
                dr=assess(folder/'drain',split['drain_cases'],drain);combined=join_results([boundary,drain]);metrics_=metrics(combined)
                passed=combined['healthy'] and dr['passed'] and all(x['detections']>0 and x['triggers']>0 and not any(x[k] for k in ('misses','false_positives','unknown')) for x in metrics_['obligations'].values())
                check(arm+': independent exposure and status recomputed',passed==m['passed'] and m['qualified']==(accepted[arm] and passed))
            check('independent pass count',sum(m['qualified'] for m in mapping.values())==outcome['new_independent_passes'])
        else:check('no independent success invented',outcome['new_independent_passes']==0)
    check('old independent protected files unchanged',c.g.old.old.screen.protected()==read(prep/'protected.json'))
    cost=c.g.old.cost_audit(root,b.paired.files(root));dump(out/'cost.json',cost);dump(out/'trace.json',details)
    dump(out/'audit.json',dict(passed=True,checks=checks,raw_native_records=raw,outcome=outcome,code_sha256=b.search.digest(Path(__file__))))
    lines=['# research80 四组呈现先导','',f"终态：{outcome['status']}。真实调用{outcome['actual_model_calls']}/8；未自动扩大。",'',
        '|里程碑|新增|','|---|---:|',f"|接受版本（组数）|{outcome['new_accepted_versions']}|",f"|完整105历史回放|{outcome['full_history_replays']}|",
        f"|新独立验收通过（组数）|{outcome['new_independent_passes']}|",'|两个核心机制增量证据|0|','',
        '这四组比较输入呈现，不是核心机制消融。同哈希的独立回放共享物理测量，不重复计为独立样本。', '']
    for d in details:lines.append(json.dumps(d,ensure_ascii=False))
    lines+=['',f"成本：{cost['total']}。原生日志复核{raw}份，检查{len(checks)}项。",'',
        '原始模型回答没有拼接或人工改写。有限仿真保护不等于全局或形式化证明。若先导未产生合格版本则停止，不追加单字段修正。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('RESULT_AUDIT',len(checks),raw,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','result']);p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--run',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.action=='prepare':prepare(a.prepared.resolve(),a.out.resolve())
    else:result(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
