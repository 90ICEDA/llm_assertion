"""Read-only recipe, raw-log, frozen-SVA and physical-cost audit of research130."""
import argparse
from collections import Counter
from pathlib import Path
import research130_fifo_supplement as r
from research15_evidence import paired_ledger, merge_ledgers, marker_map

ROOT,read,dump,digest=r.ROOT,r.read,r.dump,r.digest


def audit(prep,run,out):
    r.verify(prep); out.mkdir(parents=True,exist_ok=False)
    cand=read(prep/'candidate.json'); cases=read(prep/'cases.json'); checks=[]; groups=[]; examples=[]; count=0
    def check(name,value):
        assert value,name
        checks.append(name)
    check('candidate_unchanged',read(run/'candidate.json')==cand)
    for folder in sorted(run.glob('compiled_*')):
        compiled=read(folder/'compiled.json'); tb=(folder/'tb.sv').read_text()
        check(folder.name+'/candidate',compiled['candidate']==cand)
        for a in cand['assertions']:check(folder.name+'/'+a['id'],a['property'] in tb)
        cmd=read(folder/'compile.json')
        check(folder.name+'/native_original_RTL',cmd['exit_code']==0 and '--assert' in cmd['argv'] and
            any(Path(arg).name=='axis_fifo.v' for arg in cmd['argv']))
    with r.extension.installed():
        for i,c in enumerate(cases):
            folder=run/'cases'/f'case_{i:02d}'; check(c['id']+'/sealed_case',read(folder/'case.json')==c)
            a=read(folder/'correct/replay.json'); b=None
            r.raw_audit(a,c,folder/'correct',cand);count+=1
            if c['mode']!='correct':
                b=read(folder/c['mode']/'replay.json');r.raw_audit(b,c,folder/c['mode'],cand);count+=1
            g=paired_ledger(a,b,c['id']);groups.append(g)
            check(c['id']+'/ledger',g==read(folder/'ledger.json'))
            expected=r.assessment(c,a,b,g)
            check(c['id']+'/acceptance',expected==read(folder/'assessment.json'))
            # The actual recipe, rather than a no-failure run, must be exposed.
            targets=[row for row in g['ledger'] if row['oracle']['verdict']=='violated' and row['obligation'] in c['obligations']]
            recipe=True; detail={}
            if c['mode'] in ('corrupt','duplicate_payload'):
                recipe=len(a['oracle']['transactions'])==4 and len(b['oracle']['transactions'])==4 and bool(targets)
                if c['mode']=='duplicate_payload':
                    tx=b['oracle']['transactions'];recipe &= tx[3]['observed_data']==tx[2]['data'] and tx[3]['data']!=tx[2]['data']
            elif c['mode']=='reset_residue':
                recipe=bool(a['oracle']['cancelled']) and all(t['cancel_cycle'] is not None for t in a['oracle']['transactions'])
                recipe &= all(t['accept_cycle']<14 for t in a['oracle']['transactions'])
                recipe &= {t['obligation'] for t in targets}=={'no_unsolicited_output','reset_cancellation'}
            elif c['mode']=='correct':
                recipe=bool(a['oracle']['cancelled']) and not a['oracle']['pending'] and not a['oracle']['violations']
            elif c['mode']=='drop':
                recipe=all(v['oracle']['drain_scope']['actual_fair_samples']>=18 for v in (a,b))
                recipe &= not a['oracle']['pending']
                if c['role']=='paired_target':
                    pending=b['oracle']['pending'];recipe &= len(pending)==1 and len(targets)==1
                    if pending:
                        counterpart=next((t for t in a['oracle']['transactions'] if t['transaction_id']==pending[0]['transaction_id']),None)
                        recipe &= counterpart is not None and counterpart['response_cycle'] is not None
                        detail['pending_and_fixed_counterpart']=dict(faulty=pending[0],correct=counterpart)
                    recipe &= all(v['cycle']==len(c['rows'])-1 and v['obligation']=='drain_no_loss' for v in b['oracle']['violations'])
                else: recipe &= not b['oracle']['pending'] and not b['oracle']['violations']
            else:
                samples={t['cycle']:t for t in b['reference_trace']}
                recipe=bool(targets)
                for t in targets:
                    before,now=samples[t['cycle']-1],samples[t['cycle']]
                    recipe &= bool(before['mvalid'] and not before['mready'] and not before['rst'] and not now['rst'])
                    if 'release' in c['mode']: recipe &= now['mready']==1
                    if 'withdraw' in c['mode']: recipe &= now['mvalid']==0 and now['mdata']==before['mdata']
                    if 'stalled' in c['mode']: recipe &= now['mready']==0
                    if c['mode'].startswith('long_'):
                        fixed_samples={v['cycle']:v for v in a['trace']};n=0
                        for cyc in range(t['cycle']-1,-1,-1):
                            v=fixed_samples[cyc]
                            if v['rst'] or not v['mvalid'] or v['mready']:break
                            n+=1
                        recipe &= n>=8;detail['actual_previous_stalled_samples']=n
            check(c['id']+'/actual_recipe_exposure',recipe)
            detail.update(case=c['id'],recipe_passed=bool(recipe),transactions=dict(correct=a['oracle']['transactions'],
                faulty=b['oracle']['transactions'] if b else None),target_count=len(targets))
            if targets:
                first=targets[0]; rec=b or a; samples={s['cycle']:s for s in rec['reference_trace']};cyc=first['cycle']
                detail['example']=dict(ledger=first,anchor=samples.get(cyc-1),check=samples[cyc],
                    raw_log=r.rel(folder/c['mode']/'execute.log'))
            examples.append(detail)
    check('combined_exact',merge_ledgers(groups)==read(run/'combined.json'))
    check('48_cases_92_raw_records',len(cases)==48 and count==92)
    # The generic legacy cost extractor counts compile smoke execute.json files
    # inside native_execute_calls as well as its smoke field. Count paths once.
    experimental=sorted((run/'cases').glob('case_*/*/execute.json'))
    smoke=sorted(run.glob('compiled_*/execute.json'));compile_files=sorted(run.glob('compiled_*/compile.json'))
    check('disjoint_physical_cost',len(experimental)==92 and len(smoke)==3 and len(compile_files)==3 and not set(experimental)&set(smoke))
    for f in experimental+smoke+compile_files:check(r.rel(f)+'/successful_command',read(f)['exit_code']==0)
    old_cost=read(run/'cost.json')['total']
    check('legacy_execute_field_includes_smoke',old_cost['native_execute_calls']==len(experimental)+len(smoke))
    cost=dict(model_calls=0,compile_calls=len(compile_files),experiment_replays=len(experimental),
        compile_smoke_runs=len(smoke),total_simulator_executions=len(experimental)+len(smoke),formal_calls=0,
        compile_wall_seconds=sum(read(f)['wall_seconds'] for f in compile_files),
        experiment_wall_seconds=sum(read(f)['wall_seconds'] for f in experimental),
        smoke_wall_seconds=sum(read(f)['wall_seconds'] for f in smoke),
        correction='research130 generic native_execute_calls=95 already includes3 smoke; do not add them again. Original extractor output preserved.')
    matrices=read(run/'obligation_matrix.json')
    zero=read(r.SOURCE/'fixed_version_cells.json')
    required={(c['depth'],c['pipeline'],c['obligation']) for c in zero if c['matrix_status']=='not_exposed'}
    observed={(m['depth'],m['pipeline'],m['obligation']) for m in matrices if m['passed'] and m['actual_target_exposure']>0}
    check('all_nine_requested_cells_exposed',len(required)==9 and required<=observed)
    r.verify(prep)
    outcome=read(run/'outcome.json')
    dump(out/'audit.json',dict(passed=True,checks=len(checks),raw_records_reaudited=count,
        fixed_candidate= r.loop.sha(cand),previously_unexposed_cells_covered=len(required),new_model_calls=0,
        new_native_executions=0,new_independent_tests=0,scope='Development supplements of fixed version; finite first-attribution only.'))
    dump(out/'checks.json',checks);dump(out/'cost_corrected.json',cost);dump(out/'cases.json',examples)
    dump(out/'source_bindings.json',{r.rel(f):digest(f) for f in [Path(__file__),prep/'sealed.json',run/'outcome.json',
        run/'combined.json',run/'obligation_matrix.json',run/'candidate.json',run/'cost.json']})
    lines=['# 固定FIFO版本补测验收（research130/131）', '',
        f'完成48/48个开发补测场景，48通过；9个原未曝光参数—义务单元全部取得实际首违例曝光。原始采样与事务资格复核{len(checks)}项通过。',
        f'冻结哈希 `{r.loop.sha(cand)}` 完全不变，未调用模型，未修改性质、RTL或参考判据。', '',
        '|参数|义务|检出/实际曝光|漏报|误报|关键unknown|', '|---|---|---:|---:|---:|---:|']
    for m in matrices:lines.append(f'|{m["depth"]}/{m["pipeline"]}|{m["obligation"]}|{m["detections"]}/{m["actual_target_exposure"]}|{m["misses"]}|{m["false_positives"]}|{m["unknown"]}|')
    lines+=['',f'共{outcome["counts"]["detections"]}个确认检出采样点，无漏报、误报或关键unknown；另有{outcome["counts"]["later_attribution_unknown"]}条后续归因unknown继续保留。采样点不是独立Bug，旧批次unknown不被本轮覆盖或删除。',
        '排空目标已确认仅一个已接受事务未完成，正确侧同事务已响应，且最终公平排空检查是首违例；长背压目标已检查前8个及以上实际valid停顿采样；复位目标由真正被取消的已接受数据归因。',
        '成本按物理命令去重：3次编译、92次实验回放、3次编译冒烟，共95次仿真执行；模型与形式化0。通用旧统计器把冒烟含在native_execute_calls=95中，不能再相加成98；原始cost.json保留，正确口径见cost_corrected.json。',
        '这些是针对已见缺口的开发补测，不是新独立验收或两个机制的增量证明。只覆盖清单和指定参数，不能宣称全局完整保护。', '',
        '已执行：','```powershell',
        f'wsl -- python3 scripts/research130_fifo_supplement.py run --prepared {r.rel(prep)} --out {r.rel(run)}',
        '```','该运行目录已存在，命令不覆盖；再次实验须先用prepare生成新目录。只读复核：','```powershell',
        f'wsl -- python3 scripts/research131_supplement_audit.py --prepared {r.rel(prep)} --run {r.rel(run)} --out deliverables/research131_audit_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('AUDIT131',len(checks),'checks;',cost,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','run','out'):ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
