"""Recompute scoped FIFO/stat exposure from fresh raw native logs; no reruns."""
import argparse
import collections
from pathlib import Path
import re
import research152_source_scope_recheck as s


def audit(prep,run,out):
    s.verify(prep);out.mkdir(parents=True,exist_ok=False);checks=[];matrix=[];witnesses=[];rows_audited=0
    def check(name,ok):
        assert ok,name
        checks.append(name)
    originals={s.rel(f):s.sha(f) for f in run.rglob('*') if f.is_file() and 'obj_dir' not in f.parts}
    results=s.read(run/'results.json')
    for entry in results['results']:
        case=entry['case'];native=entry['native']
        if case=='fifo':
            depth=entry['depth'];rev=entry['revision'];off=entry['upstream_assertions_disabled']
            name=f'fifo_d{depth}_asserts_{"off" if off else "on"}/{rev}';folder=run/name
            stimuli=s.read(prep/f'fifo_d{depth}.json')
            expected_tb=s.fifo_tb(prep,stimuli,depth)
        elif case=='stat_local_synthetic':
            name='stat_local/'+entry['revision'];folder=run/name;stimuli=s.read(prep/'stat_local.json');expected_tb=s.local_tb(stimuli)
        else:
            width=entry['width'];name=f'stat_original_w{width}';folder=run/name
            stimuli=s.read(prep/f'stat_axis_w{width}.json');expected_tb=s.axis_tb(stimuli,width)
        check(name+'_native_record',s.read(folder/'result.json')==native)
        check(name+'_exact_tb',(folder/'tb.sv').read_text()==expected_tb)
        check(name+'_original_source_command',all('/sources/' in p for p in native['compile']['argv'] if p.endswith(('.sv','.v')) and not p.endswith('/tb.sv')))
        if case=='fifo':check(name+'_explicit_assert_mode',('+define+COMMON_CELLS_ASSERTS_OFF' in native['compile']['argv'])==off)
        if native['execution_status']!='completed':
            log=(folder/'execute.log').read_text()
            check(name+'_actual_parameter_rejection',case=='fifo' and depth==0 and not off and native['compile_status']=='passed' and 'Depth must be greater than 0' in log)
            matrix.append(dict(scope=name,status='upstream_configuration_rejected',functional_exposure=0,historical_success=False))
            continue
        check(name+'_normal_completion','NATIVE_RUN_COMPLETE' in (folder/'execute.log').read_text() and native['execute']['exit_code']==0)
        check(name+'_wave',(folder/'wave.vcd').stat().st_size>0)
        values=s.trace(folder,stimuli);rows_audited+=len(values)
        check(name+'_saved_trace',s.read(folder/'trace.json')==values)
        if case=='fifo':
            oracle=s.fifo_oracle(values,stimuli,depth)
            exposures=collections.Counter(v['obligation'] for v in oracle['checks'])
            failures=collections.Counter(v['obligation'] for v in oracle['failed'])
            check(name+'_no_presented_failure',not failures['nonempty_when_present'])
            if depth==0:
                marks={kind:[int(v) for v in re.findall(r'^ASSERT_FAIL '+kind+r' cycle=(\d+)$',(folder/'execute.log').read_text(),re.M)] for kind in ('idle','presented')}
                for mark,ob in [('idle','empty_when_idle'),('presented','nonempty_when_present')]:
                    check(name+'_native_assert_'+mark,marks[mark]==[v['cycle'] for v in oracle['failed'] if v['obligation']==ob])
                check(name+'_accepted_not_presented',sum(e['kind']=='accepted_and_responded' for e in oracle['events'])==36)
                check(name+'_reset_cancel',sum(e['kind']=='reset_cancel' for e in oracle['events'])==1)
            matrix.append(dict(scope=name,status='scoped_observation',exposure=dict(exposures),failures=dict(failures),
                transactions=oracle['events'],historical_success=False,configuration='conditional_assertions_off' if off else 'upstream_assertions_on'))
            if oracle['failed']:witnesses.append(dict(scope=name,classification='existing_artificial_mutant_idle_only',first_failure=oracle['failed'][0],sample=values[oracle['failed'][0]['cycle']]))
        elif case=='stat_local_synthetic':
            oracle=s.local_oracle(values,stimuli)
            matrix.append(dict(scope=name,status='synthetic_only',isolated_failures=len(oracle['confirmed_isolated_failures']),
                overlap_unknown_diagnostics=len(oracle['ambiguous_overlap_diagnostics']),historical_success=False))
            for key in ('confirmed_isolated_failures','ambiguous_overlap_diagnostics'):
                if oracle[key]:witnesses.append(dict(scope=name,classification=key,first_failure=oracle[key][0],sample=values[oracle[key][0]['cycle']]))
        else:
            oracle=s.axis_oracle(values,stimuli,width)
            check(name+'_three_exposed_snapshots',oracle['responses']==3)
            check(name+'_no_stall_assertion_failure',not native['failures'])
            counts={}
            for epoch in range(3):
                response=next(e for e in oracle['events'] if e['kind']=='snapshot_response' and e['epoch']==epoch)
                relevant=[v for v in oracle['checks'] if v.get('epoch')==epoch]
                counts[str(epoch)]=dict(expected=response['expected'],observed=response['actual'],passed=all(v['passed'] for v in relevant),
                    monitor_accepts=sum(e['kind']=='monitor_beat_accepted' and e['epoch']==epoch for e in oracle['events']))
                if not counts[str(epoch)]['passed']:
                    witnesses.append(dict(scope=name,classification='original_source_observation_no_repaired_revision',snapshot=response,
                        accepted_monitor_beats=[e for e in oracle['events'] if e['kind']=='monitor_beat_accepted' and e['epoch']==epoch]))
            matrix.append(dict(scope=name,status='original_source_scope_executed',snapshots=counts,
                failures=oracle['failed'],historical_success=False,missing='original fixed revision and historical repair lineage'))
        check(name+'_independent_oracle_recomputed',oracle==s.read(folder/'oracle.json'))
    original_fifo=(prep/'sources/common_cells/src/cc_fifo.sv').read_text()
    mutant=(prep/'sources/common_cells/src/cc_fifo_mutant.sv').read_text()
    check('exact_two_state_target_equations','assign empty_o     = ~push_i;' in original_fifo and "assign empty_o = '0;" in mutant)
    truth=[]
    for push,pop in ((p,r) for p in (0,1) for r in (0,1)):
        original_empty=(~push)&1;mutant_empty=0
        truth.append(dict(push=push,pop=pop,original_empty=original_empty,mutant_empty=mutant_empty,
            presented_target_applicable=bool(push),
            presented_repair_witness=bool(push and mutant_empty!=0 and original_empty==0)))
    check('no_presented_witness_for_existing_mutation',not any(r['presented_repair_witness'] for r in truth))
    check('runtime_no_history_success',results['historical_repair_successes']==0)
    check('raw_run_unchanged',originals=={s.rel(f):s.sha(f) for f in run.rglob('*') if f.is_file() and 'obj_dir' not in f.parts})
    s.verify(prep)
    compiles=list(run.rglob('compile.json'));execs=list(run.rglob('execute.json'))
    previous=s.ROOT/'deliverables/research152_source_scope_native_20261027_r01'
    cost=dict(model_calls=0,formal_calls=0,compiles=len(compiles),physical_executions=len(execs),
        compile_seconds=sum(s.read(f)['wall_seconds'] for f in compiles),execute_seconds=sum(s.read(f)['wall_seconds'] for f in execs),
        prior_failed_builds=len(list(previous.rglob('compile.json'))),prior_failed_build_executions=len(list(previous.rglob('execute.json'))))
    report=dict(passed=True,checks=len(checks),raw_trace_rows_audited=rows_audited,scope_matrix=matrix,witnesses=witnesses,cost=cost,
        historical_repair_successes=0,remaining_unknowns=['case505 original-to-surrogate derivation and overlap permission',
            'Original repaired stat revision/history for new AXI observation','Historical FIFO repair lineage; Depth0 default support conflict'],
        fifo_presented='No failure exposure in this specific force-zero mutation under its two-state Depth0 presented branch; do not confuse idle mismatch with presented witness.',
        stat='Local synthetic timing is separate from new original AXI behavior. No old result or independent batch reclassified.',
        no_learned_sva_claim=True,new_model_calls=0,formal_proof=False)
    s.dump(out/'audit.json',report);s.dump(out/'checks.json',checks);s.dump(out/'fifo_truth_table.json',truth)
    s.dump(out/'scope_matrix.json',matrix);s.dump(out/'witnesses.json',witnesses)
    lines=['# stat 规格与原始 FIFO presented 核查','',
        '本轮只做本地来源、配置、实际曝光与原生回放核验，没有模型调用、断言自动细化或形式化证明。新增历史修复成功数为0。','',
        '## FIFO：空闲违例不能替代 presented 见证','',
        f'固定来源 common_cells `{s.CC}`，完整原始 `cc_fifo.sv` 及头文件取自Git对象。原文件保持不变；另一版仅应用已有case438的empty_o恒0人工突变，未伪造上游修复提交。',
        '默认上游断言在Depth=0直接要求Depth>0而失败，两版均为配置拒绝。额外的Depth=0仿真显式关闭上游断言，只属条件性旁路语义验证。背压presented场景还与上游full_write前置条件冲突，因此不能称原配置合法事务。',
        'push=1时，原版~push与突变版0相同；push=0时才有空闲empty错误。本次目标必须按义务拆开统计。Depth2/4时该突变分支不启用，有限队列回放不能用来证明其Depth0历史缺陷。','',
        '|范围|曝光|失败|分类|','|---|---|---|---|']
    for row in matrix:
        if row['scope'].startswith('fifo'):lines.append(f"|{row['scope']}|{row.get('exposure',row.get('functional_exposure'))}|{row.get('failures','配置拒绝')}|{row['status']}|")
    lines+=['','## stat：旧代理模型与新原始AXI模块分开','',
        '旧case505两周期valid诊断仍只属于8行人工代理模型；来源映射未恢复。相邻不同长度事件可暴露其所谓correct版本的数据关联问题，但重叠是否获规格允许仍unknown，不能倒推出上游时序规格。',
        f'新增范围仅为verilog-axis `{s.AXIS}` 原始axis_stat_counter：8/64位监测输入、单拍/多拍完整帧、输入及输出背压、空闲且非busy时触发、连续低位tkeep。参考计数仅使用实际valid&&ready接受与tlast结束事件。',
        '规格依据：[固定提交README](https://raw.githubusercontent.com/alexforencich/verilog-axis/'+s.AXIS+'/README.md)的axis_stat_counter、tlast及接口示例；同提交tb/test_axis_stat_counter.py的>HLLL解码与计数断言。原始源码用于追因，不是待评估SVA充当唯一oracle。','',
        '|范围|快照|期望[tag,ticks,bytes,frames]|实际|通过|','|---|---:|---|---|---|']
    for row in matrix:
        if row['scope'].startswith('stat_original'):
            for ep,v in row['snapshots'].items():lines.append(f"|{row['scope']}|{ep}|{v['expected']}|{v['observed']}|{v['passed']}|")
    lines+=['', '即使新原始模块出现可复现计数违例，也没有对应修复后提交，不能计为case505来源补齐、历史修复成功或LLM闭环成功。全部判据只适用于已封存范围。',
        '',f"本轮成本：{cost['compiles']}次编译、{cost['physical_executions']}次执行，另保留首次缺头文件造成的{cost['prior_failed_builds']}次失败构建（未执行）。模型0、形式化0。",'',
        f'只读审计{len(checks)}项，重算{rows_audited}条原始采样；运行文件和旧记录保持不变。','',
        '复现到全新输出目录：','```powershell',
        'wsl -- python3 scripts/research153_source_scope_dependencies.py run --prepared deliverables/research152_source_scope_prepare_20261027_r02 --out deliverables/research152_new_replay',
        '```','', '只读复核到全新输出目录：','```powershell',
        f'wsl -- python3 scripts/research154_scope_result_audit.py --prepared {s.rel(prep)} --run {s.rel(run)} --out deliverables/research154_recheck', '```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    s.dump(out/'source_bindings.json',{**originals,s.rel(Path(__file__)):s.sha(Path(__file__)),s.rel(prep/'sealed.json'):s.sha(prep/'sealed.json')})
    s.dump(out/'sealed.json',{f.relative_to(out).as_posix():s.sha(f) for f in out.rglob('*') if f.is_file()})
    print('AUDIT154',len(checks),'checks',rows_audited,'samples; historical successes0',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','run','out'):ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
