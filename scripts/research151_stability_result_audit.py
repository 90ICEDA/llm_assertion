"""Read-only audit of the sealed real candidate/seed replication batch.

Recompute actual proposals, native decisions, retention, conditional recovery,
freeze order, holdout exposure and physical cost; never call a model or replay.
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
from unittest.mock import patch
import research148_stability_execution as b

c=b.c
read,dump,digest,rel=b.read,b.dump,b.digest,b.rel


def audit(prep,run,out):
    b.prepmod.verify(prep);b.validate_grant(prep,run,read(run/'authorization.json'))
    out.mkdir(parents=True,exist_ok=False);checks=[];details=[];raw_count=0
    def check(name,ok):
        assert ok,name
        checks.append(name)
    original={rel(f):digest(f) for f in run.rglob('*') if f.is_file() and 'obj_dir' not in f.parts}
    result=read(run/'results.json');cells=read(prep/'cells.json');frozen=read(run/'global_freeze.json')
    check('schedule_complete',len(result['cells'])==len(cells)==12)
    fresh=[];stop_seen=False
    for cell in cells:
        folder=run/'cells'/cell['id'];prepared=prep/'cells'/cell['id'];initial=read(prepared/'initial.json')
        baseline=read(prepared/'baseline_full.json');native=b.ROOT/cell['native']
        records={k:read(native/k/'result.json') for k in ('alignment','search','history')}
        before=initial;versions={'O':initial,'H':initial};stages=[];first=None
        row=b.collect_cell(cell,folder)
        if stop_seen:check(cell['id']+'_not_run_after_global_stop',not row['first_dispatched'])
        for index,stage in enumerate(('shared/v0','history/v1')):
            callfolder=folder/stage/'model_call'
            if not (callfolder/'attempt.json').exists():continue
            attempt=read(callfolder/'attempt.json');call=read(callfolder/'result.json')
            req=read(callfolder/'request.json')
            with patch.object(c,'SEED',cell['seed']):expected=c.request(before,records,native,index==1,index)
            check(cell['id']+stage+'_request',req==expected)
            check(cell['id']+stage+'_no_retry',call['retries']==attempt['retries']==0)
            started=datetime.fromisoformat(attempt['started_utc'].replace('Z','+00:00')).timestamp()
            check(cell['id']+stage+'_before_global_freeze',started<=frozen['time'])
            check(cell['id']+stage+'_model_seed',req['seed']==cell['seed']+index and req['model']==read(prep/'protocol.json')['model'])
            if index==0:check(cell['id']+'_sealed_first',req==read(prepared/'request.preview.json'))
            else:check(cell['id']+'_qualified_recovery_only',first and first['branch']=='history_once')
            candidate=read(callfolder/'candidate.json') if (callfolder/'candidate.json').exists() else None
            if candidate:
                edit=read(callfolder/'model_edit.json')
                assembled=read(callfolder/'response.assembled.json')
                check(cell['id']+stage+'_raw_response_to_edit',json.loads(assembled['message']['content'])==edit)
                check(cell['id']+stage+'_model_verbatim',c.mapping.adapt(edit,before)==candidate)
                usage=assembled.get('service_done',{}).get('usage')
                if usage:
                    check(cell['id']+stage+'_usage',call['prompt_tokens']==usage['prompt_tokens'] and call['completion_tokens']==usage['completion_tokens'])
            measured=(folder/stage/'native/decision.json').exists()
            ev=None;summary=None
            if measured:
                n,ev,newrecords=c.mapping.inspect_version(folder/stage/'native',candidate,baseline);raw_count+=n
                full=c.x.paired.aggregate(newrecords['history'],newrecords['search'])
                info=c.x.old.acceptance.inspect(full['ledger']);summary={}
                for ob in (c.mapping.OP,c.mapping.BRANCH):
                    summary[ob]={}
                    for phase,predicate in [('first',lambda r:r['sample']['phase']==0),('first_held',lambda r:r['sample']['phase']==1),('later_held',lambda r:r['sample']['phase']>=2)]:
                        keys={k for k,r in info['rows'].items() if r['obligation']==ob and predicate(r) and r['revision']=='before' and r['oracle']['verdict']=='violated'}
                        summary[ob][phase]=dict(exposure=len(keys),detected=len(keys&info['detections']),missed=len(keys&info['misses']),unknown=len(keys&info['unknown']))
                summary['false_positives']=len(info['false_positives']);summary['critical_unknown']=c.critical_unknown(ev)
            if index==0:
                ordinary=bool(ev and ev['ordinary']['accepted']);historical=bool(ev and ev['full_absolute'])
                branch=c.p.branch(call['status'],measured,ordinary,historical,len(ev['lost_detection_ids']) if ev else 0,
                    len(ev['new_false_alarm_ids']) if ev else 0,c.critical_unknown(ev))
                first=dict(O=ordinary,H=historical,branch=branch,measured=measured)
                check(cell['id']+'_first_decision',first==read(folder/'first_decisions.json'))
                for arm,accepted in [('O',ordinary),('H',historical)]:
                    expected_active=candidate if accepted else initial
                    check(cell['id']+arm+'_active',read(folder/'arms'/arm/'v0/active.json')==expected_active)
                    versions[arm]=expected_active
            else:
                accepted=bool(ev and ev['full_absolute'] and not c.critical_unknown(ev))
                if accepted:versions['H']=candidate
                check(cell['id']+'_recovery_retention',read(folder/'arms/H/v1/active.json')==versions['H'])
                check(cell['id']+'_recovery_result',accepted==row['recovered'])
            stages.append(dict(stage=stage,status=call['status'],native_measured=measured,
                O=bool(ev and ev['ordinary']['accepted']),H=bool(ev and ev['full_absolute']),
                lost_old_detections=len(ev['lost_detection_ids']) if ev else None,
                new_false_alarms=len(ev['new_false_alarm_ids']) if ev else None,
                per_obligation_phase=summary,properties=[a['property'] for a in candidate['assertions']] if candidate else None,
                repeat_rejected=(folder/stage/'repeat_rejection.json').exists()))
            if measured:before,records,native=candidate,newrecords,folder/stage/'native'
        terminal=b.terminal_versions(prepared,folder)
        for arm,candidate in terminal.items():
            check(cell['id']+arm+'_freeze_hash',c.x.old.acceptance.sha(candidate)==frozen['versions'][cell['id']][arm])
            check(cell['id']+arm+'_frozen_content',candidate==read(run/'terminal_frozen'/cell['id']/arm/'candidate.json'))
            check(cell['id']+arm+'_decisions_retained',candidate==versions[arm])
        row['H_hash']=frozen['versions'][cell['id']]['H'];fresh.append(row)
        stop_seen=stop_seen or row['transport_failure'] or row['execution_exception']
        details.append(dict(id=cell['id'],candidate=cell['candidate'],seed=cell['seed'],stages=stages,
                            retained_hashes=frozen['versions'][cell['id']]))
    tests=read(run/'independent_summary.json') if (run/'independent_summary.json').exists() else {}
    if tests:
        generation=read(run/'test_generation.json');txns=read(run/'independent_cases.json')
        check('test_after_global_freeze',generation['time']>=frozen['time'] and generation['freeze_sha256']==digest(run/'global_freeze.json'))
        check('new96_unique_excluded',len(txns)==len({t['instruction'] for t in txns})==96 and not ({t['instruction'] for t in txns}&set(read(run/'excluded_words.json'))))
        for sha,summary in tests.items():
            folder=run/'tested_versions'/sha;candidate=read(folder/'candidate.json');ledger=read(folder/'independent/result.json')
            check(sha+'_bound_inputs',digest(folder/'independent_cases.json')==digest(run/'independent_cases.json'))
            check(sha+'_bound_candidate',c.x.old.acceptance.sha(candidate)==sha)
            native=c.x.holdout.base.native_audit(folder,ledger);raw_count+=native['rows_audited']
            c.mapping.validate_ledger(ledger,candidate)
            with patch.object(c.x.old,'CONFIGS',c.x.holdout.base.CONFIGS):guard=c.x.all_guard(folder/'independent',ledger,candidate)
            check(sha+'_independent_recomputed',c.x.holdout.summarize(ledger,guard)==summary)
    for row in fresh:
        if row['full_terminal']:
            row['independent_pass']=bool(tests[row['H_hash']]['passed']) if row['H_hash'] in tests else None
    check('overall_denominators',b.metrics(fresh)==result['overall'])
    check('cost_recomputed',c.physical_cost(run)==result['actual_cost'])
    check('actual_calls_match_attempts',len(list(run.rglob('attempt.json')))==result['actual_cost']['model']['model_calls'])
    check('physical_compiles',len(list(run.rglob('compile.json')))==result['actual_cost']['native_compiles'])
    check('physical_executions',len(list(run.rglob('execute.json')))==result['actual_cost']['native_executions'])
    check('run_immutable',original=={rel(f):digest(f) for f in run.rglob('*') if f.is_file() and 'obj_dir' not in f.parts})
    b.prepmod.verify(prep)
    dump(out/'audit.json',dict(passed=True,checks=len(checks),native_rows_recomputed=raw_count,
        actual_model_calls=result['actual_cost']['model']['model_calls'],new_model_calls_during_audit=0,
        new_native_calls_during_audit=0,original_files_unchanged=True,scope=result['scope'],
        independent_versions={k:dict(passed=v['passed'],counts=v['counts'],
            target_exposure_complete=v.get('target_exposure_complete'),
            legal_control_exposure_complete=v.get('legal_control_exposure_complete'),
            required_untriggered=v.get('required_untriggered')) for k,v in tests.items()}))
    dump(out/'checks.json',checks);dump(out/'case_details.json',details)
    trace=['# 全部真实提案轨迹','', '以下仅整理本批实际模型输出及原生决策，不选择或修改终态版本。独立测试未反馈给模型。']
    for detail in details:
        trace+=['', '## '+detail['id']]
        for stage in detail['stages']:
            trace+=['',stage['stage']+': O='+str(stage['O'])+', H='+str(stage['H']),
                    '旧检出丢失='+str(stage['lost_old_detections'])+'；新增误报='+str(stage['new_false_alarms']),
                    '```systemverilog',*(stage['properties'] or ['// No executable model candidate']), '```']
            if stage['per_obligation_phase']:
                trace+=['', '```json', json.dumps(stage['per_obligation_phase'],ensure_ascii=False,indent=2), '```']
    (out/'CASE_TRACE.md').write_text('\n'.join(trace)+'\n',encoding='utf-8')
    dump(out/'source_bindings.json',{**original,rel(Path(__file__)):digest(Path(__file__)),rel(prep/'sealed.json'):digest(prep/'sealed.json')})
    lines=['# 固定候选与种子真实复现','', '公共生成流程、原生标准及条件恢复预算保持封存版本；4个候选、3个种子、2类已观察保护行为，仅1个Ibex decoder父案例。','',
           '|指标|分子/分母|比例|','|---|---:|---:|']
    names={'planned_coverage':'执行覆盖','ordinary_acceptance':'普通接受','generation_full_acceptance':'首次生成完整接受','conditional_recovery':'条件恢复','independent_pass':'完整接受H轨迹的独立通过','unique_version_independent_pass':'不同H冻结版本独立通过','whole_schedule_success':'全部计划单元最终独立通过'}
    for key,label in names.items():
        r=result['overall'][key];v='不可估计' if r['value'] is None else f"{r['value']:.1%}"
        lines.append(f"|{label}|{r['numerator']}/{r['denominator']}|{v}|")
    for dimension,label in [('candidate','候选'),('seed','请求种子'),('behavior_profile','实际保护行为分组'),('mechanisms','义务/阶段漏报分层')]:
        lines+=['', '### '+label, '', '|分组|首次完整接受|条件恢复|独立通过|未运行|', '|---|---:|---:|---:|---:|']
        for group,stats in result['grouped'][dimension].items():
            rates=[]
            for key in ('generation_full_acceptance','conditional_recovery','independent_pass'):
                value=stats[key];rates.append(f"{value['numerator']}/{value['denominator']}" if value['denominator'] else '不可估计（0机会）')
            lines.append('|'+group+'|'+'|'.join(rates)+f"|{stats['not_run']}|")
    lines+=['', '同一候选可属于多个义务/阶段分层，分层分母不能相加。种子是请求参数，不把服务端确定性当作已验证事实。']
    lines+=['','|单元|首次O/H|旧检出丢失/新增误报|恢复|H独立|','|---|---|---|---|---|']
    for detail,row in zip(details,fresh):
        first=detail['stages'][0] if detail['stages'] else {}
        lines.append(f"|{row['id']}|{first.get('O')}/{first.get('H')}|{first.get('lost_old_detections')}/{first.get('new_false_alarms')}|{row['recovered'] if row['qualified_recovery'] else '无合格机会'}|{row['independent_pass']}|")
    cost=result['actual_cost'];overall=result['overall']
    lines+=['', '|独立版本哈希前缀|检出|漏报|误报|unknown|必要未触发|目标/合法曝光完整|',
            '|---|---:|---:|---:|---:|---:|---|']
    for sha,summary in tests.items():
        v=summary['counts']
        lines.append(f"|{sha[:12]}|{v['detections']}|{v['misses']}|{v['false_positives']}|{v['unknown']}|{summary.get('required_untriggered')}|{summary.get('target_exposure_complete')}/{summary.get('legal_control_exposure_complete')}|")
    lines+=['', '不同版本共享同一批新指令与原始RTL违例，不能把跨版本重复检出相加为独立新缺口。BRANCH首周期原RTL正确，验收要求正确输出及触发，不虚构首周期违例。']
    lines+=['',f"实际成本：模型{cost['model']['model_calls']}次，原生编译/执行{cost['native_compiles']}/{cost['native_executions']}次，形式化0。完整token与时间见原运行results.json。",'',
        f"关键unknown采样记录{overall['critical_unknown_points']}，传输失败单元{overall['transport_failure_cells']}，执行/完整性异常单元{overall['native_or_integrity_failure_cells']}，未运行{overall['not_run']}，合格但独立结果缺失{overall['independent_pending_or_unavailable']}。",'',
        '生成率分母包含实际首次调用的失败；条件恢复率只以普通接受、历史拒绝且确认退化的机会为分母，0机会不是0%恢复率。独立通过率仅描述通过开发接受的H终态，另列全部计划单元的最终通过率。',
        '文本不同但开发保护相同的候选相关；共同独立输入及重复版本也相关。不得按独立Bug相加、外推跨父案例成功率或形式化证明。',
        '本批所有初始漏报属于已知开发反馈，不能计作契约搜索额外发现。H/R在此语料上等价，只能讨论增加历史检查的作用。',
        f'只读审计：{len(checks)}项检查，重算{raw_count}条原生记录；未新增模型调用或仿真。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    dump(out/'sealed.json',{f.relative_to(out).as_posix():digest(f) for f in out.rglob('*') if f.is_file()})
    print('AUDIT151',len(checks),'checks',raw_count,'native rows',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','run','out'):ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
