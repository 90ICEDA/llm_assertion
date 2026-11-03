"""Preserve research165 syntax failures; correct only reserved assertion label.

Four native reruns max, reuse four successful native executions unchanged.
"""
import argparse
import itertools
from pathlib import Path
import shutil
import research165_adapter_qualification as q

P=q.ROOT/'deliverables/research165_adapter_prepare_20261028_r01'
R=q.ROOT/'deliverables/research165_adapter_native_20261028_r01'


def prepare(out):
    q.verify(P);shutil.copytree(P,out,ignore=shutil.ignore_patterns('seal.json'))
    changes=[]
    for name in ('replacement','complementary'):
        path=out/'controls'/f'{name}.json';value=q.read(path)
        for a in value['assertions']:
            if a['label']=='final':a['label']='final_keep'
        q.dump(path,value)
        text=q.bench(value['assertions'],q.read(out/'scenarios.json'))
        original=(P/'controls'/f'{name}.sv').read_text()
        assert text.replace('final_keep','final')==original
        (out/'controls'/f'{name}.sv').write_text(text)
        changes.append(dict(control=name,change='label final -> final_keep',same_predicates_stimuli_rtl=True))
    q.dump(out/'label_correction.json',dict(changes=changes,reason='final is a SystemVerilog keyword; native compilation rejected identifier.',
        old_run=q.old.rel(R),old_results_preserved=True,max_new_compiles=4,max_new_executions=4,model_calls=0))
    binding=q.read(out/'code_bindings.json');binding[q.old.rel(Path(__file__))]=q.sha(Path(__file__));q.dump(out/'code_bindings.json',binding)
    q.dump(out/'seal.json',{p.relative_to(out).as_posix():q.sha(p) for p in out.rglob('*') if p.is_file()})
    q.verify(out);print('PREPARED166 label-only correction;4 native retries;no model',flush=True)


def run(prep,out):
    q.verify(prep);out.mkdir(parents=True,exist_ok=False);results=[]
    prior=q.read(R/'results.json')
    for name in q.controls():
        for rev in ('before','after'):
            folder=out/name/rev
            if name in ('baseline','overbroad'):
                original=next(r for r in prior if r['control']==name and r['revision']==rev)
                assert original['result']['compile_status']=='passed'
                shutil.copytree(R/name/rev,folder,ignore=shutil.ignore_patterns('obj_dir'))
                entry=dict(original,reused_from=q.old.rel(R/name/rev))
            else:
                n=q.old.native.run_native((prep/'controls'/f'{name}.sv').read_text(),folder,extra_sources=[prep/'rtl'/rev/'axis_adapter.v'])
                entry=dict(control=name,revision=rev,result=n)
                if n['execution_status']=='completed':
                    vals=q.old.trace(folder);q.dump(folder/'trace.json',vals);q.dump(folder/'oracle.json',q.adjudicate(vals))
                print('NATIVE166',name,rev,n['compile_status'],n['execution_status'],len(n.get('failures',[])),flush=True)
            results.append(entry);q.dump(out/'progress.json',results)
    q.dump(out/'results.json',results);q.verify(prep)


def report(prep,executed,out):
    out.mkdir(parents=True,exist_ok=False)
    q.report(prep,executed,out/'qualification')
    checks=[]
    def check(name,value):checks.append(dict(name=name,passed=bool(value)));assert value,name
    # Full original source identity, not just filenames.
    provenance=q.read(q.PRIOR/'source_manifest.json')['sources']
    for rev in ('before','after'):
        s=next(s for s in provenance if s['case']=='axis_adapter_keep' and s['revision']==rev and s['source_path']=='rtl/axis_adapter.v')
        check('original blob '+rev,q.old.git('show',s['commit']+':rtl/axis_adapter.v')==(prep/'rtl'/rev/'axis_adapter.v').read_bytes())
    prior=q.read(R/'results.json');now=q.read(executed/'results.json')
    physical=prior+[x for x in now if 'reused_from' not in x]
    costs=dict(model_calls=0,formal_calls=0,native_compiles=len(physical),native_executions=sum(x['result']['native_simulation_calls'] for x in physical),
        compile_seconds=sum(x['result']['compile']['wall_seconds'] for x in physical),
        execution_seconds=sum(x['result'].get('execute',{}).get('wall_seconds',0) for x in physical),
        failed_compiles=sum(x['result']['compile_status']!='passed' for x in physical),
        original_native_runs=q.old.rel(R),corrected_native_runs=q.old.rel(executed),reused_successful_executions=4)
    check('bounded label correction actual cost',costs['native_compiles']==12 and costs['native_executions']==8 and costs['failed_compiles']==4)
    # Count distinct external timing patterns; descriptor values yielding the
    # same ready waveform are NOT counted twice. No candidate is run on this pool.
    cap=q.read(prep/'future_shape_capacity.json');canonical={}
    for name,c in cap.items():
        keys=set()
        for length,gap,delay,period in itertools.product(c['lengths'],c['gap'],range(c['ready_delay'][0],c['ready_delay'][1]+1),c['stall_period']):
            ready=tuple(int(t>=2 and t>=delay and t%period!=0) for t in range(96))
            keys.add((length,gap,ready,c['keep']))
        canonical[name]=dict(raw_descriptors=c['available_shapes'],distinct_external_timing_shapes=len(keys),required=c['required'],
            actual_accepted_trace_novelty='Must still be checked only after future model version is frozen; no data-only novelty, duplicates/no exposure stop without redraw.')
        check('distinct remaining external schedules '+name,len(keys)>=c['required'])
    request=q.read(out/'qualification/pilot/request.preview.json');body=__import__('json').loads(request['messages'][1]['content'])
    scenarios=q.read(prep/'scenarios.json')
    check('all actual failure feedback public',all(scenarios[e['before']['sid']]['scope']=='public' for e in body['public_development_evidence']))
    check('no final-only/correct union fixture in request',body['current_assertions']==q.read(prep/'controls/baseline.json')['assertions'])
    matrix=q.read(out/'qualification/acceptance_matrix.json');by={x['control']:x for x in matrix}
    check('genuine semantic O/H difference on native records',by['replacement']['ordinary'] and not by['replacement']['history'] and len(by['replacement']['lost_prior_detections'])>0)
    # Private reference checks are independent, saved native failure records
    # are checked against raw logs as well as source predicates.
    import re
    for name in q.controls():
        for rev in ('before','after'):
            path=executed/name/rev;r=q.read(path/'result.json');log=(path/'execute.log').read_text()
            for key,tag in [('failures','ASSERT_FAIL'),('triggers','TRIGGER')]:
                actual=[dict(id=i,detail=d.strip()) for i,d in re.findall(r'^'+tag+r'\s+(\S+)(.*)$',log,re.M)]
                check('native raw markers '+name+rev+key,actual==r[key])
    q.dump(out/'physical_costs_including_failures.json',costs)
    q.dump(out/'independent_capacity_audit.json',canonical)
    q.dump(out/'checks.json',checks)
    q.dump(out/'decision.json',dict(local_three_gate_qualification=True,model_calls=0,
        pilot_protocol_and_request_sealed=True,executable_budget_controller_integrated=False,
        next='Integrate new adapter interface into bounded model controller and run local branch tests; only then request explicit max2 model authorization.',
        conditional_model_recovery='0/0 not estimable',new_independent_tests_executed=False,
        important='New semantic timing pools are not validated independent outcomes. Future actual exposure/novelty/trigger checks may fail and must be reported.'))
    lines=['# 新历史案例资格与封存结果', '',
        '**三项本地资格均成立：部分保护、非白名单区分、未用时序场景容量。已封存axis_adapter先导协议和请求；模型调用0。**', '',
        '范围是原始axis_adapter c1c3dc0修复前后，8→32位，输入KEEP禁用。没有改RTL、注入故障或调用旧独立测试挑选规则。原始Git blob复核通过。', '',
        '|手写本地对照|当前末拍检出|历史全部目标检出|旧保护丢失|合法误报周期|普通／历史|','|---|---:|---:|---:|---:|---|']
    for r in matrix:lines.append(f"|{r['control']}|{r['public_detected']}/{r['public_exposed']}|{r['historical_detected']}/{r['historical_exposed']}|{len(r['lost_prior_detections'])}|{r['false_positive_cycles']}|{r['ordinary']}/{r['history']}|")
    lines += ['', '基线已有非末拍实际检出，同时遗漏公共短帧末拍。替换对照依据TLAST语义，普通规则接受而历史规则额外拒绝，拒绝后保留原部分基线。互补正对照能同时满足两组检查。它们都是明确手写的资格夹具，不能计真实模型提案、自然退化概率或自动恢复成功。', '',
        '33个开发场景、每场景96周期；原生SVA作用于原始RTL，独立握手队列检查字节、掩码、帧边界、排空、复位和背压。前后实际输入一致。修复版参考检查无失败，旧版失败来自原始KEEP缺陷。计数是违例采样，不是独立Bug。', '',
        '## 独立余量已在调用前核查', '',
        '|分层|去除重复ready波形后的结构余量|需要|','|---|---:|---:|']
    for k,v in canonical.items():lines.append(f"|{k}|{v['distinct_external_timing_shapes']}|{v['required']}|")
    lines += ['', '按单帧长度、输入间隔、实际ready控制序列与KEEP去重，不按payload/种子。排除了当前1/3/5/9长度、间隔0/1、背压周期4的开发形状，以及旧research159/160的两帧[2,2]。未来仍须冻结后才抽取32个场景，并检查实际接受轨迹不重复、两类原始目标实际曝光；不能把池容量当作独立通过。重复/无曝光/失败不补抽。', '',
        '## 保留的错误与成本', '',
        '首轮replacement/complementary误用了SystemVerilog保留字final作标签，4次编译失败、未执行。已保留原封存与错误日志；仅改名final_keep，逐字核对性质/激励/RTL完全不变，重新运行这4次，其余4次成功回放直接复用。',
        f"本轮合计编译{costs['native_compiles']}次（含失败{costs['failed_compiles']}）、执行{costs['native_executions']}次；编译{costs['compile_seconds']:.3f}s、执行{costs['execution_seconds']:.3f}s。模型/形式化0。", '',
        '## 下一步边界', '',
        '先导协议和请求在qualification/pilot/：最多2次真实调用，第一份共享提案仅在普通接受/历史拒绝且确认退化、无unknown时允许一次恢复；完整接受后冻结并独立验收，不重试不扩种子。',
        '**实际预算控制器尚未接入这个新接口。下一步先完成本地控制器集成及分支预检，再申请明确模型授权。** 这与资格/协议封存分开报告。真实额外拒绝、恢复、独立通过均尚未发生，条件恢复仍0/0；H/R等价限制不变。', '',
        '既有FIFO独立结果、stat来源unknown和576查询负结果保持不变，已知TKEEP问题不重新算作搜索收益。', '',
        '```powershell',
        'wsl -- python3 scripts/research166_adapter_label_correction.py report --prepared deliverables/research166_adapter_prepare_20261028_r01 --executed deliverables/research166_adapter_native_20261028_r01 --out deliverables/research166_report_recheck',
        '```', '',
        '资格详情和完整复跑命令见qualification/SUMMARY.md，最终先导协议见qualification/pilot/protocol.json。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n')
    q.dump(out/'bindings.json',dict(correction_code=q.sha(Path(__file__)),original_prepare_seal=q.sha(P/'seal.json'),
        corrected_prepare_seal=q.sha(prep/'seal.json'),qualification_seal=q.sha(out/'qualification/seal.json')))
    q.dump(out/'seal.json',{p.relative_to(out).as_posix():q.sha(p) for p in out.rglob('*') if p.is_file()})
    print('REPORT166',matrix,'capacity',canonical,'cost',costs,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run','report'])
    for n in ('prepared','executed','out'):ap.add_argument('--'+n,type=Path,required=n=='out')
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='run':run(a.prepared.resolve(),a.out.resolve())
    else:report(a.prepared.resolve(),a.executed.resolve(),a.out.resolve())
