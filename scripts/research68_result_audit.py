"""Read-only raw-native / real-model / acceptance audit for research68."""
import argparse
import json
from pathlib import Path
import re
import time
import research68_service_pilot as run


def audit(prep,root,out):
    out.mkdir(parents=True,exist_ok=False);run.verify(prep)
    outcome=run.read(root/'outcome.json');checks=[];raw_count=0;reference_calls=0
    def check(name,value):assert value,name;checks.append(name)
    calls=sorted(root.glob('core/v*/model_call/attempt.json'))
    check('actual call cap',len(calls)==outcome['actual_new_calls'] and len(calls)<=2)
    initial=run.read(run.PREP/'shared_initial.json');current=initial
    baseline=run.base.campaign.baseline(run.PREP,'search')
    history_binding=run.read(run.PREP/'history_binding.json')
    history=run.read(run.base.gate.portable(history_binding['path']))
    details=[];start=time.perf_counter()
    with run.base.extension.installed():
        for attempt in calls:
            model=attempt.parent;folder=model.parent;call=run.read(model/'result.json')
            check(folder.name+' HTTP status terminal honest',call['status']=='response_received' or not (model/'candidate.json').exists())
            if not (model/'candidate.json').exists():
                details.append(dict(version=folder.name,status=call['status'],candidate=False,
                    error=run.read(model/'service_error_response.json') if (model/'service_error_response.json').exists() else None));continue
            edit=run.read(model/'model_edit.json');candidate=run.read(model/'candidate.json')
            check(folder.name+' exact model assembly',run.base.interface.assemble(edit,current)==candidate)
            for group in ('target_native','history_native'):
                loc=folder/group
                if not (loc/'result.json').exists():continue
                cases=run.read(run.PREP/('search/cases.json' if group=='target_native' else 'history_cases.json'))
                n=raw_replay(loc,cases,candidate,checks);raw_count+=n;reference_calls+=n
            target=run.read(folder/'target_native/result.json') if (folder/'target_native/result.json').exists() else None
            if target:
                plain=run.base.paired.current_decision(baseline,target,edit)
                check(folder.name+' target gate recomputed',plain==run.read(folder/'target_gate.json'))
            if (folder/'history_native/result.json').exists():
                full=run.read(folder/'history_native/result.json')
                hg=run.base.gate.decide(history['group']['ledger'],full['group']['ledger'])
                check(folder.name+' history gate recomputed',hg==run.read(folder/'decision.json')['history'])
            else:full=None
            decision=run.read(folder/'decision.json')
            expected=bool(target and plain['accepted'] and full and full['healthy'] and hg['accepted'])
            check(folder.name+' complete acceptance',decision['accepted']==expected)
            current=candidate if expected else current
            check(folder.name+' durable retained state',run.read(folder/'active_candidate.json')==current)
            details.append(dict(version=folder.name,status=call['status'],candidate_hash=run.base.loop.sha(candidate),
                properties=[dict(id=a['id'],property=a['property']) for a in candidate['assertions']],
                accepted=expected,target=target['counts'] if target else None,history=full['counts'] if full else None,
                reason_kinds=[r['kind'] for r in decision['reasons']]))
        if outcome['accepted']:
            check('freeze equals actually accepted candidate',run.read(root/'core/frozen_candidate.json')==current)
        if (root/'independent/summary.json').exists():
            split=run.read(root/'independent/split.json')
            check('holdout bound to accepted freeze',split['frozen_hash']==run.base.loop.sha(current) and outcome['accepted'])
            excluded=set(run.read(root/'exclusion_manifest.json')['input_hashes'])
            cases=split['boundary_cases']+split['drain_cases']
            check('new test inputs disjoint',not excluded&{run.base.loop.sha(c['rows']) for c in cases})
            for group,key in (('boundary','boundary_cases'),('drain','drain_cases')):
                n=raw_replay(root/'independent'/group,split[key],current,checks);raw_count+=n;reference_calls+=n
            independent=run.read(root/'independent/summary.json')
            check('pilot pass equals independent verdict',outcome['pilot_passed']==independent['all_five_pass_on_first_attributed_evidence'])
        else:
            independent=None;check('no absent independent success',not outcome['pilot_passed'])
    run.verify(prep)
    run.dump(out/'audit.json',dict(passed=True,checks=checks,native_records_recomputed=raw_count,
        reference_calls=reference_calls,audit_wall_seconds=time.perf_counter()-start,model_calls=0,new_native_calls=0,
        source_sha256=run.base.search.digest(Path(__file__))))
    run.dump(out/'version_trace.json',details)
    cost=run.read(root/'cost.json')['total']
    lines=['# research68：服务诊断与先导续接','',f"实际终态：**{outcome['status']}**。新增真实请求{len(calls)}次，原先导累计{len(calls)+1}/3；本轮接受={outcome['accepted']}，新独立验收通过={outcome['pilot_passed']}。",'',
        '本轮是HTTP失败后的续接，压缩公共重复诊断并修复实际opener错误采集路径；未改变RTL、规格、AST接口、模型、种子或两个实际目标采样。辅助修正须同样用于未来所有组，不能当作两个核心机制的收益。旧HTTP400原因不能从本轮成功或请求大小倒推。','',
        '|版本|传输|目标|105历史|完整接受|','|---|---|---|---|---|']
    for d in details:lines.append(f"|{d['version']}|{d['status']}|{d.get('target','无候选')}|{d.get('history','未执行')}|{d.get('accepted',False)}|")
    if independent:
        lines+=['',f"新独立场景{independent['scenarios']}个，具体各义务曝光/检出/触发/误报/漏报/unknown见原始independent/summary.json。结论仅限有限第一违例归因范围，后续unknown保留，不是形式化证明。"]
    for d in details:
        if d.get('error'):lines+=['','服务实际错误正文（脱敏）：','```',d['error']['body'][:3000],'```']
    lines+=['',f"实际成本：{cost['native_compile_calls']}编译/{cost['native_execute_calls']}执行，tokens输入/输出={cost['prompt_tokens_total']}/{cost['completion_tokens_total']}，用量缺失调用={cost['usage_unavailable_calls']}，形式化0。本地HTTP夹具未计入真实请求或模型成功。",'',
        f"审计重算{raw_count}份原始仿真记录，{len(checks)}项检查通过；采样、事务参考、原生trigger/failure标记和接受决定均复核。research63字节哈希保持不变，未读取其测试用于改进。",'',
        '多种子两类消融尚未执行。仅在先导完整通过后才可开始；共享提案的单轮门控与独立多轮轨迹分开报告，各组最终冻结后生成新独立测试。不能把单个先导成功解释为受控机制收益。', '',
        '只读复核（新目录）：','```powershell',
        'wsl -- python3 scripts/research68_result_audit.py --prepared '+prep.relative_to(run.ROOT).as_posix()+' --run '+root.relative_to(run.ROOT).as_posix()+' --out deliverables/research68_audit_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('AUDIT',len(checks),'raw records',raw_count,flush=True)


def raw_replay(folder,cases,candidate,checks):
    saved=run.read(folder/'result.json');groups=[];count=0
    if not saved.get('group'):
        assert not saved['healthy'];checks.append(str(folder.name)+':failed_native_not_success');return 0
    for i,case in enumerate(cases):
        source=folder/f'case_{i}';records=[]
        for mode in ('correct',case['mode']):
            path=source/mode;record=run.read(path/'replay.json')
            trace=run.base.extension.runtime.parse_trace(path/'execute.log')
            reference=run.base.loop.runtime.parse_reference(path/'execute.log')
            assert trace==record['trace'] and reference==record['reference_trace']
            assert run.base.extension.runtime.oracle(trace,case['rows'])==record['oracle']
            assert run.base.loop.runtime.qualify_sampling(trace,reference)==record['sampling_qualification']
            assert record['candidate']==candidate
            log=(path/'execute.log').read_text()
            for key,marker in (('failures','ASSERT_FAIL'),('triggers','TRIGGER')):
                actual={(m[0],int(m[1])) for m in re.findall(r'^'+marker+r' (\S+) cycle=(-?\d+)',log,re.M)}
                stored={(m['id'],int(re.search(r'cycle=(-?\d+)',m['detail'])[1])) for m in record['native'][key]}
                assert actual==stored
            assert 'NATIVE_RUN_COMPLETE' in log and (path/'wave.vcd').stat().st_size>0
            records.append(record);count+=1
        groups.append(run.base.search.evidence.paired_ledger(*records,case['id']))
    merged=run.base.search.evidence.merge_ledgers(groups)
    assert run.base.loop.counts(merged)==saved['counts']
    checks.append(str(folder)+':raw records and independent counts recomputed')
    return count


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
