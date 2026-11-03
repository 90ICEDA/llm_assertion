"""Read-only provenance, scope and cost report for research132 -> research133."""
import argparse
from pathlib import Path
import research132_fifo_independent as r

ROOT,read,dump,rel,digest=r.ROOT,r.read,r.dump,r.rel,r.digest


def report(out):
    prep=ROOT/'deliverables/research133_prepare_20261026_r01'
    inputs=ROOT/'deliverables/research133_inputs_20261026_r01'
    run=ROOT/'deliverables/research133_independent_20261026_r01'
    audit=ROOT/'deliverables/research133_audit_20261026_r01'
    old=ROOT/'deliverables/research132_independent_20261026_r01'
    old_prep=ROOT/'deliverables/research132_prepare_20261026_r01'
    old_inputs=ROOT/'deliverables/research132_inputs_20261026_r01'
    cases=r.check_inputs(prep,inputs);r.check_inputs(old_prep,old_inputs)
    checks=[]
    def check(name,condition):
        assert condition,name
        checks.append(name)
    check('raw_audit_complete',read(audit/'audit.json')['passed'] and read(audit/'audit.json')['raw_records_reaudited']==240)
    check('old_failure_retained',read(old/'outcome.json')['failed']==8 and not read(old/'outcome.json')['all_scoped_checks_passed'])
    check('candidate_bytes_unchanged',digest(prep/'candidate.json')==digest(old_prep/'candidate.json'))
    check('acceptance_text_unchanged',read(prep/'protocol.json')['acceptance']==read(old_prep/'protocol.json')['acceptance'])
    check('old_gate_source_unchanged',read(prep/'source_bindings.json')['scripts/research132_fifo_independent.py']==read(old_prep/'source_bindings.json')['scripts/research132_fifo_independent.py'])
    check('whole_old_batch_excluded',set(read(prep/'development_promotion.json')['input_hashes']) <= set(read(prep/'exclusions.json')['input_hashes']))
    check('freeze_then_draw_then_execute',read(prep/'freeze.json')['created_unix']<read(inputs/'draw.json')['drawn_unix']<read(run/'execution.json')['started_unix'])
    examples=[]
    for i,c in enumerate(cases):
        if c['family']!='reset_cancels_tail':continue
        folder=run/'cases'/f'case_{i:03d}'
        a=read(folder/'correct/replay.json');b=read(folder/'drop/replay.json')
        check(c['id']+'/real_cancellation_both_sides',len(a['oracle']['cancelled'])>=1 and len(b['oracle']['cancelled'])>=2)
        check(c['id']+'/no_legal_false_alarm',not a['native']['failures'] and not b['native']['failures'])
        examples.append(dict(id=c['id'],rows=rel(folder/'case.json'),
            correct_cancelled=a['oracle']['cancelled'],faulty_cancelled=b['oracle']['cancelled'],
            correct_log=rel(folder/'correct/execute.log'),faulty_log=rel(folder/'drop/execute.log')))
    results=read(run/'progress.json');matrix=read(run/'obligation_matrix.json')
    for m in matrix:
        relevant=[x for x in results if (x['depth'],x['pipeline'])==(m['depth'],m['pipeline']) and m['obligation'] in x['obligations']]
        for key in ('actual_target_exposure','detections','misses','false_positives','unknown','triggers'):
            check(f'{m["depth"]}/{m["pipeline"]}/{m["obligation"]}/{key}',m[key]==sum(x['obligations'][m['obligation']][key] for x in relevant))
    check('20_prespecified_cells',len(matrix)==20)
    version_logs=[p.read_text() for p in sorted(run.glob('compiled_*/tool_version.log'))]
    check('native_version_recorded',len(version_logs)==4 and all('Verilator' in s for s in version_logs))
    costs={tag:r.cost(folder) for tag,folder in [('qualification_failed_batch',old),('new_independent_batch',run)]}
    total={k:sum(v[k] for v in costs.values()) for k in ('model_calls','formal_calls','compile_calls','experiment_replays','compile_smoke_runs','total_simulator_executions')}
    outcome=read(run/'outcome.json')
    out.mkdir(parents=True,exist_ok=False)
    dump(out/'audit.json',dict(passed=True,checks=len(checks),scope='Provenance and report audit; not new native execution.',outcome=outcome))
    dump(out/'checks.json',checks);dump(out/'costs.json',dict(batches=costs,total=total))
    dump(out/'reset_control_examples.json',examples)
    dump(out/'commands.json',dict(executed=[
        'wsl -- python3 scripts/research133_fifo_independent.py seal --out deliverables/research133_prepare_20261026_r01',
        'wsl -- python3 scripts/research133_fifo_independent.py generate --prepared deliverables/research133_prepare_20261026_r01 --out deliverables/research133_inputs_20261026_r01',
        'wsl -- python3 scripts/research133_fifo_independent.py run --prepared deliverables/research133_prepare_20261026_r01 --inputs deliverables/research133_inputs_20261026_r01 --out deliverables/research133_independent_20261026_r01',
        'wsl -- python3 scripts/research133_fifo_independent.py audit --prepared deliverables/research133_prepare_20261026_r01 --inputs deliverables/research133_inputs_20261026_r01 --run deliverables/research133_independent_20261026_r01 --out deliverables/research133_audit_20261026_r01'],
        note='Output directories are immutable. Read-only verification command below; rerun audit with a NEW output directory. Do not reuse completed independent batches to tune candidates or criteria.'))
    lines=['# 固定FIFO集合：新的独立验收', '',
        f'最终批次research133：{outcome["passed"]}/128场景通过，指定范围通过={outcome["all_scoped_checks_passed"]}。',
        f'研究69冻结集合 `{r.EXPECTED}` 保持不变。参数为Depth/Pipeline 2/0、4/1、4/2、8/2，2个冻结后随机种子。',
        f'共{outcome["counts"]["detections"]}个首归因违例义务采样点检出，漏报{outcome["counts"]["misses"]}、合法误报{outcome["counts"]["false_positives"]}、关键unknown {outcome["counts"]["unknown"]}；另保留{outcome["counts"]["later_attribution_unknown"]}条后续归因unknown。',
        '96个目标场景、32个合法控制；每个目标均配同输入正确侧。20个参数—义务单元均须实际曝光，无曝光不能通过。', '',
        '|配置|顺序检出/曝光|无请求输出|背压/解除|复位取消|排空|', '|---|---:|---:|---:|---:|---:|']
    for d,p in r.PARAMS:
        cells={x['obligation']:x for x in matrix if (x['depth'],x['pipeline'])==(d,p)}
        labels=('order_payload','no_unsolicited_output','stall_stability','reset_cancellation','drain_no_loss')
        lines.append(f'|{d}/{p}|'+ '|'.join(f'{cells[x]["detections"]}/{cells[x]["actual_target_exposure"]}' for x in labels)+'|')
    lines+=['',
        '首批research132保留120/128：8个“复位取消尾部”控制因正确侧已提前排空而缺少实际取消曝光，未算通过；未发现断言漏报/误报。整批128个输入已转开发。随后仅修改该家族激励：增加一个在背压下接受、随后由复位取消的事务。断言、RTL、参考模型及全部接受条件未改。research133重新封存，重新抽取种子，全部128个输入重生且排除旧输入/旧时序。原失败不追改。',
        f'原生日志重新解析{read(audit/"audit.json")["raw_records_reaudited"]}份、{read(audit/"audit.json")["checks"]}项回放审计；另{len(checks)}项来源、冻结顺序及报表检查。',
        f'最终批次成本：{costs["new_independent_batch"]["compile_calls"]}次编译、240次实验回放、4次编译冒烟，共244次仿真执行。包含失败首批的本轮总成本：{total}。',
        '限定结论：指定参数、已知人工故障家族的新输入及首违例归因范围验收完成（须以上passed为true）。不等于整段故障轨迹无unknown、所有参数完整保护、形式化证明或原始历史FIFO缺陷复现；也不是新模型生成/恢复成功率或两个机制增量证据。',
        '没有修改候选或使用本批结果挑选版本。若未来据此修改，整批研究133须转为开发数据，再冻结并生成新独立测试。', '',
        '只读核验封存：','```powershell',
        'wsl -- python3 scripts/research133_fifo_independent.py verify --prepared deliverables/research133_prepare_20261026_r01',
        '```','完整已执行命令见commands.json；波形和原生日志见research133_independent_20261026_r01/cases/case_*/。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    dump(out/'source_bindings.json',{rel(p):digest(p) for p in [Path(__file__),prep/'sealed.json',inputs/'sealed.json',run/'outcome.json',run/'obligation_matrix.json',audit/'audit.json',old/'outcome.json']})
    print('REPORT134',len(checks),'checks',outcome,'total_cost',total,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True)
    report(ap.parse_args().out.resolve())
