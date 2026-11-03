"""Read-only audit of the research76 one-plan, one-SVA continuation."""
import argparse
import copy
import json
from pathlib import Path
import research75_campaign as run
import research76_schema_continuation as typed
from research28_report import raw_response
b,read,dump,ROOT=run.b,run.read,run.dump,run.ROOT

def result(prep,root,out):
    run.verify(prep);out.mkdir(parents=True,exist_ok=False);checks=[];raw=0
    def check(name,ok):assert ok,name;checks.append(name)
    outcome=read(root/'outcome.json');auth=read(root/'authorization.json')
    check('bounded explicit grant',auth['authorized_calls']==2 and auth['prepared_sha256']==b.search.digest(prep/'sealed.json'))
    plan_calls=sorted(root.glob('plan/v*/model_call/attempt.json'));sva_calls=sorted(root.glob('core/v*/model_call/attempt.json'))
    check('bounded stages',len(plan_calls)<=1 and len(sva_calls)<=1 and len(plan_calls)+len(sva_calls)==outcome['model_calls']<=2)
    rows=read(prep/'windows.private.json');initial=read(prep/'initial.json');current=initial
    plan_source=read(prep/'plan_request.preview.json');expected_request=plan_source;passed_plan=None;details=[]
    for attempt in plan_calls:
        m=attempt.parent;folder=m.parent;call=read(m/'result.json')
        check(str(folder)+' request',read(m/'request.json')==expected_request)
        if call['status']!='response_received':check('terminal plan transport',not sva_calls and attempt==plan_calls[-1]);break
        value=read(m/'hold_plan.json')
        check(str(folder)+' actual response',raw_response(m,value))
        verdict=typed.validate(value,rows);check(str(folder)+' independent interpretation',verdict==read(folder/'decision.json'))
        details.append(dict(stage='plan',version=folder.name,accepted=verdict['accepted'],reasons=verdict['reasons']))
        if verdict['accepted']:
            check('stop plan at pass',attempt==plan_calls[-1]);passed_plan=value;break
        if (folder/'next_request.preview.json').exists():
            expected_request=copy.deepcopy(plan_source);body=json.loads(expected_request['messages'][1]['content'])
            body['rejected_model_plan']=value;body['actual_rejection']=[{k:v for k,v in r.items() if k!='expected'} for r in verdict['reasons']]
            expected_request['messages'][1]['content']=json.dumps(body)
            check('no private answer in retry',expected_request==read(folder/'next_request.preview.json'))
    check('generation only after complete interpretation',not sva_calls or passed_plan is not None)
    seen={b.interface.executable_hash(initial)};last_edit=None;accepted=False
    before=read(run.sem.SOURCE/'baseline_public/result.json');historical=read(run.sem.SOURCE/'baseline_history/result.json')
    if passed_plan is not None:
        template=run.sem.unlock(read(prep/'sva_template.json'),passed_plan,run.sem.validate(passed_plan,rows),rows)
        check('unmodified verified plan in SVA request',template==read(root/'sva_request.preview.json'));expected_request=template
    with b.extension.installed():
        for attempt in sva_calls:
            m=attempt.parent;folder=m.parent;call=read(m/'result.json')
            check(str(folder)+' request',read(m/'request.json')==expected_request)
            if call['status']!='response_received':check('terminal SVA transport',attempt==sva_calls[-1]);break
            edit=read(m/'model_edit.json') if (m/'model_edit.json').exists() else None
            candidate=read(m/'candidate.json') if (m/'candidate.json').exists() else None
            if edit:check(str(folder)+' raw model edit',raw_response(m,edit))
            if candidate:check(str(folder)+' exact executable',b.interface.assemble(edit,current)==candidate)
            repeated=bool(candidate and b.interface.executable_hash(candidate) in seen)
            if candidate:seen.add(b.interface.executable_hash(candidate))
            results={}
            for name,casefile in [('windows','window_cases.json'),('public','cases.json'),('history','history_cases.json')]:
                loc=folder/name
                if (loc/'result.json').exists():
                    results[name]=read(loc/'result.json');raw+=run.raw_replay(loc,read(prep/casefile),candidate,checks)
                else:results[name]=None
            wr,small,full=results['windows'],results['public'],results['history']
            wg=run.sem.native_windows(wr,rows,read(prep/'window_cases.json'),folder/'windows')
            check('native window gate '+folder.name,wg==read(folder/'window_gate.json'))
            check('public stage guarded',small is None or wg['accepted'])
            plain=b.paired.current_decision(before,small,edit) if small else dict(accepted=False,reasons=wg['reasons'])
            check('history stage guarded',full is None or plain['accepted'])
            decision=run.policy.decision_for(plain,full,historical,True)
            check('unchanged full admission '+folder.name,decision==read(folder/'decision.json'))
            accepted=decision['accepted'];current=candidate if accepted else current
            check('durable state '+folder.name,current==read(folder/'active_candidate.json'))
            details.append(dict(stage='sva',version=folder.name,edit=edit,window_gate=wg['accepted'],accepted=accepted,
                public=small.get('counts') if small else None,history=full.get('counts') if full else None,reasons=decision['reasons']))
            if accepted:check('stop on acceptance',attempt==sva_calls[-1])
            last_edit=edit
        check('accepted outcome truthful',accepted==outcome['accepted'])
        check('frozen exact version',read(root/'core/frozen_candidate.json')==current and b.loop.sha(current)==outcome['frozen_hash'])
        if outcome['independent_performed']:
            check('holdout requires accepted',accepted)
            split=read(root/'independent/split.json');excluded=set(read(prep/'excluded_inputs.json')['input_hashes'])
            check('fresh input exclusion',not excluded & {b.loop.sha(c['rows']) for c in split['boundary_cases']+split['drain_cases']})
            check('frozen hash binding',split['frozen_hash']==b.loop.sha(current))
            for name,key in [('boundary','boundary_cases'),('drain','drain_cases')]:raw+=run.raw_replay(root/'independent'/name,split[key],current,checks)
            # Recompute all obligation exposure and finite pass, not just a saved boolean.
            from research35_campaign import join_results,metrics
            from research29_drain import assess
            boundary=read(root/'independent/boundary/result.json');drain=read(root/'independent/drain/result.json')
            ds=assess(root/'independent/drain',split['drain_cases'],drain)
            combined=join_results([boundary,drain]);m=metrics(combined)
            finite=combined['healthy'] and ds['passed'] and all(v['detections']>0 and v['triggers']>0 and not any(v[k] for k in ('misses','false_positives','unknown')) for v in m['obligations'].values())
            check('independent exposure and pass recomputed',finite==read(root/'independent/summary.json')['all_five_pass_on_first_attributed_evidence'])
        else:check('no unperformed holdout',not (root/'independent').exists())
    check('prior independent results retained',run.old.screen.protected()==read(prep/'protected.json'))
    cost=run.cost_audit(root,b.paired.files(root));dump(out/'cost.json',cost);dump(out/'trace.json',details)
    dump(out/'audit.json',dict(passed=True,checks=checks,raw_native_records=raw,outcome=outcome,code_sha256=b.search.digest(Path(__file__))))
    lines=['# research76：跨周期保持语义门控与真实细化','',f"终态：{outcome['status']}；实际模型调用{outcome['model_calls']}/2。",'',
        '语义判断逐项对照真实原生采样和独立事务参考；失败不能进入SVA生成。生成性质必须通过原生窗口、固定14公共场景及105历史检查。', '']
    for d in details:
        lines += [f"{d['stage']} {d['version']}：接受={d['accepted']}；原生窗口={d.get('window_gate','不适用')}。",f"公共：{d.get('public')}；历史：{d.get('history')}。"]
    lines += ['',f"冻结哈希 `{outcome['frozen_hash']}`。新的独立测试已执行：{outcome['independent_performed']}。"]
    if outcome['independent_performed']:lines+=['',json.dumps(read(root/'independent/summary.json'),ensure_ascii=False,indent=2)]
    else:lines+=['','尚无满足全部条件的新接受版本；未执行或声称新的独立验收。']
    lines+=['',f"成本：{cost['total']}。原生日志复核{raw}份，审计{len(checks)}项通过。",'',
        '有限开发/测试证据不是全局证明。本轮为已观察案例加公共语义辅助的继续实验，不能归入两个机制的受控收益。旧独立结果没有用于调规则，未发送归档成功性质或私有答案。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('RESULT_AUDIT',len(checks),raw,outcome['status'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();result(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
