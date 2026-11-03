"""Standalone frozen independent evaluation of research172's accepted proposal.

prepare seals the candidate, code, exclusions and test-generation protocol.
run selects tests only after verifying that seal. No model calls, no rerolls,
no candidate edits, no changes to the earlier pilot's terminal state.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import time
import research172_applicability_gate as g

q=g.q
PRIOR=q.ROOT/'deliverables/research173_pilot_report_20261028_r01'
PILOT=q.ROOT/'deliverables/research172_adapter_run_20261028_r01'
PILOT_PREP=q.ROOT/'deliverables/research172_applicability_prepare_20261028_r02'


def digest(value):return g.c.digest(value)


def development_files():
    definitions=[g.c.P/'scenarios.json',g.c.P/'prior_shape_inventory.json',
        q.ROOT/'deliverables/research159_history_prepare_20261028_r01/axis_adapter_keep/stimuli.json',
        q.ROOT/'deliverables/research160_history_prepare_20261028_r01/axis_adapter_keep/stimuli.json']
    traces=[]
    for number in (159,160):
        root=q.ROOT/f'deliverables/research{number}_history_native_20261028_r01'
        for width in (8,32):
            for rev in ('before','after'):traces.append(root/f'axis_adapter_keep/p{width}'/rev/'execute.log')
    for name in ('baseline','replacement','complementary','overbroad'):
        for rev in ('before','after'):traces.append(g.c.N/name/rev/'execute.log')
    root=q.ROOT/'deliverables/research169_scope_native_20261028_r01'
    for name in ('bound_archived','literal_control','replacement_control'):
        for rev in ('before','after'):traces.append(root/name/rev/'execute.log')
    # Deliberately bad binding aborts before real stimulus, excluded explicitly.
    extras=[root/'mismatch/after/result.json']
    for number in (169,172):
        root=q.ROOT/f'deliverables/research{number}_adapter_run_20261028_r01'
        for rev in ('before','after'):traces.append(root/'shared/native'/rev/'execute.log')
    for number in (167,169,172):
        root=q.ROOT/f'deliverables/research{number}_adapter_run_20261028_r01/shared/model_call'
        extras += [root/'request.json',root/'model_edit.json']
    extras += [q.ROOT/'deliverables/research171_nonhandshake_report_20261028_r01/synthetic_classifier_controls.json',
        PILOT_PREP/'synthetic_controls.json']
    return definitions,traces,extras


def normalized_trace(path):
    trace=q.old.trace(path.parent)
    if trace and 'sid' not in trace[0]:
        for v in trace:v['sid']=v['cycle']//40
    return trace


def prepare(out):
    g.c.verify(PILOT_PREP)
    for p,h in q.read(PRIOR/'seal.json').items():assert q.sha(PRIOR/p)==h,p
    for p,h in q.read(PRIOR/'source_bindings.json').items():assert q.sha(q.ROOT/p)==h,p
    ev=q.read(PILOT/'shared/evaluation.json');candidate=q.read(PILOT/'shared/model_call/candidate.json')
    assert ev['ordinary'] and ev['history'] and not ev['unknown']
    assert q.read(PILOT/'terminal_versions.json')==dict(O=candidate,H=candidate)
    out.mkdir(parents=True,exist_ok=False)
    definitions,traces,extras=development_files();inventory=[];signatures=set()
    for p in definitions+traces+extras:
        assert p.is_file(),str(p)
        item=dict(path=q.old.rel(p),sha256=q.sha(p),role='development_excluded')
        if p in traces:
            values=normalized_trace(p);sig=g.c.actual_signatures(values);signatures.update(sig)
            item.update(role='native_development_trace_excluded',scenarios=len(sig),configuration='8to8' if '/p8/' in p.as_posix() else '8to32')
        elif p.name in ('synthetic_classifier_controls.json','synthetic_controls.json'):
            item['role']='synthetic_development_classifier_controls_not_independent'
            item['exclusion']='Derived from old one/three/five/nine-byte traces or two repeated one-byte frames; new lengths/gaps and actual transaction signature checks exclude those shapes. No synthetic data treated as native.'
        inventory.append(item)
    q.dump(out/'candidate.json',candidate)
    for rev in ('before','after'):
        target=out/'rtl'/rev/'axis_adapter.v';target.parent.mkdir(parents=True)
        target.write_bytes((g.c.P/'rtl'/rev/'axis_adapter.v').read_bytes())
    q.dump(out/'development_exclusions.json',dict(files=inventory,actual_trace_signatures=sorted(signatures),
        rejected_or_reused_data_remain_development=True,
        prior_not_run_independent_pools='research166/167/169 pool definitions are not executions. No prior axis_adapter independent scenes selected.',
        other_parent_cases='FIFO and Ibex independent outcomes not read or used to select adapter candidate/rules. Scope unchanged8to32.'))
    q.dump(out/'protocol.json',dict(purpose='standalone_independent_acceptance_after_both_accept_not_recovery',seed=17407,
        original_pilot_unchanged=True,model_calls=0,formal_calls=0,max_compiles=2,max_executions=2,rerolls=0,retries=0,
        config=g.s.PARAMETERS,cycles_per_scenario=96,
        strata={'short_target':8,'long_target':8,'legal_transfer':16,'reset_cancel':8},
        generation=dict(short_lengths=[2],short_gaps=[2,3,4,5],short_delays=[14,19],
            long_lengths=[6,7,10,11,12,13,14,15],long_gaps=[2,3],long_delay=21,
            legal_lengths=[2,6,7,10,11,12,13,14],legal_gaps=[2,3],legal_delays=[14,19],
            reset_length=14,reset_gaps=[2,3],reset_cycles=[20,24],reset_keeps=[0,1],reset_ready_delay=40,
            stall_period_choices=[2,3,5],selection='Draw period/gap choices then shuffle all descriptors after freeze; no observed-outcome selection.'),
        checks=['native both revisions complete','same legal inputs','new actual semantic transaction signatures ignoring payload',
            'short targets final_nonempty exposure and direct detection','long targets nonfinal_keep AND final_nonempty exposure and direct detection',
            'legal partial tails explicitly exposed','actual backpressure and release observed','reset cancels actual pending input and stalled output; no unsolicited postreset output',
            'fixed independent reference clean','no false positives or key unknown','frozen SVA unchanged'],
        expected_scope='Two original KEEP fault obligations; stall and reset are legal-behavior tests only, no injected stall/reset faults.',
        novelty='Compare each before/after trace to development and other tests in same revision; ignore payload/seed/IDs. Preserve duplicates, failures, no-exposure, unknown; never redraw.',
        acceptance='All40 scenarios must meet own exposure, execution, novelty and finite-scope checks. Separately report per-obligation and scenario scope. No formal/global guarantee.',
        failure_policy='No feedback to model or candidate changes; if later used for improvement, entire batch must be reclassified as development and new holdout prepared.'))
    bindings=q.read(PILOT_PREP/'code_bindings.json')
    for p in definitions+traces+extras+[Path(__file__),PILOT_PREP/'seal.json',PRIOR/'seal.json',PILOT/'outcome.json',PILOT/'shared/model_call/candidate.json']:
        bindings[q.old.rel(p)]=q.sha(p)
    q.dump(out/'code_bindings.json',bindings)
    q.dump(out/'freeze.json',dict(created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),candidate_hash=digest(candidate),
        candidate_file_sha256=q.sha(out/'candidate.json'),rtl={rev:q.sha(out/'rtl'/rev/'axis_adapter.v') for rev in ('before','after')},
        protocol_hash=q.sha(out/'protocol.json'),exclusions_hash=q.sha(out/'development_exclusions.json'),
        development_acceptance=q.old.rel(PILOT/'shared/evaluation.json'),pilot_outcome_sha256=q.sha(PILOT/'outcome.json'),
        test_selection_not_yet_done=True,scope='new independent protocol; not retroactive research172 recovery branch'))
    g.s.seal_files(out);verify(out)
    print('FROZEN174; scenarios not generated; model0; exclusions',len(inventory),'distinct signatures',len(signatures),flush=True)


def verify(prep):
    g.s.verify_files(prep);g.c.verify(PILOT_PREP)
    freeze=q.read(prep/'freeze.json')
    assert digest(q.read(prep/'candidate.json'))==freeze['candidate_hash']
    assert q.sha(PILOT/'outcome.json')==freeze['pilot_outcome_sha256']


def generate(protocol):
    rng=random.Random(protocol['seed']);cfg=protocol['generation'];rows=[]
    def add(stratum,length,gap,delay,keep,reset=-1):
        rows.append(dict(frames=[length],gap=gap,ready_delay=delay,keep=keep,reset_at=reset,
            stall_period=rng.choice(cfg['stall_period_choices']),stratum=stratum,
            scope='history' if stratum=='long_target' else 'public'))
    for gap in cfg['short_gaps']:
        for delay in cfg['short_delays']:add('short_target',2,gap,delay,0)
    for length in cfg['long_lengths']:add('long_target',length,rng.choice(cfg['long_gaps']),cfg['long_delay'],0)
    for length in cfg['legal_lengths']:
        for gap in cfg['legal_gaps']:add('legal_transfer',length,gap,rng.choice(cfg['legal_delays']),1)
    for gap in cfg['reset_gaps']:
        for reset in cfg['reset_cycles']:
            for keep in cfg['reset_keeps']:add('reset_cancel',cfg['reset_length'],gap,cfg['reset_ready_delay'],keep,reset)
    rng.shuffle(rows)
    return [dict(v,id=i) for i,v in enumerate(rows)]


def run(prep,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False)
    candidate=q.read(prep/'candidate.json');freeze=q.read(prep/'freeze.json');protocol=q.read(prep/'protocol.json')
    rows=generate(protocol)
    assert Counter(r['stratum'] for r in rows)==Counter(protocol['strata'])
    q.dump(out/'scenarios.json',rows)
    q.dump(out/'input_freeze.json',dict(prior_freeze_hash=q.sha(prep/'freeze.json'),prior_seal_hash=q.sha(prep/'seal.json'),
        generated_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),candidate_hash=digest(candidate),scenarios_hash=digest(rows),rerolls=0))
    results={}
    for rev in ('before','after'):
        results[rev]=q.old.native.run_native(q.bench(candidate,rows),out/'native'/rev,extra_sources=[prep/'rtl'/rev/'axis_adapter.v'])
        q.dump(out/'native_results.json',results)
        print('NATIVE174',rev,results[rev]['compile_status'],results[rev]['execution_status'],flush=True)
    verify(prep)
    ev=g.measure(candidate,out/'native',rows);q.dump(out/'evaluation.json',ev)
    prior=set(q.read(prep/'development_exclusions.json')['actual_trace_signatures']);fresh={};refs={};stats=[]
    if all(rev in ev['evidence'] for rev in ('before','after')):
        for rev in ('before','after'):
            values=ev['evidence'][rev]['trace'];fresh[rev]=g.c.actual_signatures(values);refs[rev]=g.audit.replay(values)
        # Preserve every duplicate/failure rather than select replacement scenes.
        for row in rows:
            sid=row['id'];rev_records={}
            for rev in ('before','after'):
                values=[v for v in ev['evidence'][rev]['trace'] if v['sid']==sid]
                oracle=ev['evidence'][rev]['oracle']
                failures=[x for x in oracle['failures'] if x['sid']==sid]
                cancels=[x for x in refs[rev]['reset_cancellations'] if x['sid']==sid and x['cancelled_requests']]
                table=g.reference_table(ev['evidence'][rev]['trace'])[1]
                applicable={ob:sum(table[v['cycle']][ob]['applicable'] for v in values) for ob in g.OBLIGATIONS}
                detections=ev.get('obligation_evaluation',{}).get(rev,{}).get('target_coverage',[])
                exposed=Counter(ob for d in detections if d['cycle']//96==sid for ob in d['obligations'])
                held=[v for v in values if not v['rst'] and v['mv'] and not v['mr']]
                released=[v for i,v in enumerate(values) if i and values[i-1]['mv'] and not values[i-1]['mr'] and v['mv'] and v['mr'] and not v['rst']]
                transfers=[e for e in oracle['events'] if e['kind']=='output' and e['sid']==sid]
                inputs=[v['cycle'] for v in values if not v['rst'] and v['sv'] and v['sr']]
                fp=[x for x in ev.get('false_'+rev,[]) if x//96==sid]
                partial=sum(e['last'] and 0<e['expected_keep']<15 for e in transfers)
                after_reset=[v for v in values if row['reset_at']>=0 and v['phase']>row['reset_at']+1]
                rev_records[rev]=dict(novel=fresh[rev][sid] not in prior and fresh[rev].count(fresh[rev][sid])==1,
                    accepted_input_cycles=inputs,output_acceptance_cycles=[e['cycle'] for e in transfers],
                    applicable_cycles=applicable,target_exposure=dict(exposed),target_misses=sum(not d['detected'] for d in detections if d['cycle']//96==sid),
                    necessary_untriggered=sum(not d['triggered'] for d in detections if d['cycle']//96==sid),
                    false_positive_cycles=fp,reference_failures=failures,backpressure_cycles=len(held),release_edges=len(released),
                    partial_final_outputs=partial,reset_cancellations=cancels,
                    postreset_no_request_no_output=bool(after_reset) and all(not v['sv'] and not v['mv'] for v in after_reset))
            b,a=rev_records['before'],rev_records['after'];issues=[]
            if not b['novel'] or not a['novel']:issues.append('duplicate_actual_trace')
            if a['reference_failures']:issues.append('fixed_reference_failure')
            if b['false_positive_cycles'] or a['false_positive_cycles']:issues.append('assertion_false_positive')
            if b['target_misses'] or b['necessary_untriggered']:issues.append('target_miss_or_untriggered')
            if row['stratum']=='short_target':
                if not b['target_exposure'].get('final_nonempty'):issues.append('unexposed_short_target')
            elif row['stratum']=='long_target':
                if not all(b['target_exposure'].get(ob) for ob in g.KEEP):issues.append('unexposed_long_target')
            elif row['stratum']=='legal_transfer':
                if b['reference_failures']:issues.append('legal_reference_failure')
                if not a['output_acceptance_cycles']:issues.append('no_legal_transfer')
                if row['frames'][0]%4 and not a['partial_final_outputs']:issues.append('unexposed_legal_partial_tail')
            else:
                if not all(r['reset_cancellations'] and r['postreset_no_request_no_output'] for r in (b,a)):issues.append('unexposed_or_failed_reset_cancel')
            if not a['backpressure_cycles']:issues.append('unexposed_backpressure')
            if row['stratum']!='reset_cancel' and not a['release_edges']:issues.append('unexposed_release')
            if ev['unknown']:issues.append('critical_unknown_in_batch')
            stats.append(dict(id=sid,stratum=row['stratum'],configuration=row,passed=not issues,issues=issues,revision=rev_records))
    else:
        stats=[dict(id=r['id'],stratum=r['stratum'],passed=False,issues=['native_or_trace_incomplete']) for r in rows]
    q.dump(out/'scenario_results.json',stats);q.dump(out/'actual_novelty.json',dict(development_signatures=sorted(prior),independent_signatures=fresh))
    cost=dict(model_calls=0,formal_calls=0,native_compiles=len(results),native_executions=sum(n['native_simulation_calls'] for n in results.values()),
        compile_seconds=sum(n['compile']['wall_seconds'] for n in results.values()),execute_seconds=sum(n.get('execute',{}).get('wall_seconds',0) for n in results.values()))
    by={name:dict(total=sum(x['stratum']==name for x in stats),passed=sum(x['stratum']==name and x['passed'] for x in stats)) for name in protocol['strata']}
    answer=dict(status='passed' if all(x['passed'] for x in stats) and ev['history'] else 'failed_or_unresolved',
        scenario_passed=sum(x['passed'] for x in stats),scenario_total=len(stats),strata=by,unknown=ev['unknown'],
        target_exposure=len(ev.get('public_targets',[]))+len(ev.get('history_targets',[])),
        target_misses=len(ev.get('public_missed',[]))+len(ev.get('history_missed',[])),
        false_positive_before=len(ev.get('false_before',[])),false_positive_after=len(ev.get('false_after',[])),
        candidate_unchanged=digest(candidate)==freeze['candidate_hash'],pilot_unchanged=q.sha(PILOT/'outcome.json')==freeze['pilot_outcome_sha256'],
        batch_role='independent_not_used_for_refinement',rerolls=0,
        fault_scope='original KEEP repair only; stall/reset are legal-behavior exposure, not injected-fault coverage',cost=cost)
    q.dump(out/'result.json',answer);verify(prep)
    lines=['# research174 单独冻结后的独立验收','',f"结果：{answer['status']}；场景{answer['scenario_passed']}/{len(stats)}通过。",
        '', '|分层|通过/总数|','|---|---|']
    lines += [f"|{k}|{v['passed']}/{v['total']}|" for k,v in by.items()]
    lines += ['',f"原始KEEP目标曝光{answer['target_exposure']}点，漏报{answer['target_misses']}；误报before/after={answer['false_positive_before']}/{answer['false_positive_after']}；关键unknown={len(answer['unknown'])}。",'',
        '独立范围固定为原始axis_adapter 8→32、输入KEEP禁用。新断言先冻结，再生成新场景；开发排除清单及实际轨迹新颖性逐项保存。不通过/重复/无曝光均保留，不补抽替换。',
        '两类KEEP目标检出与背压/复位合法行为检查分开。没有注入背压或复位故障，因此其故障检出能力未曝光，不能算完整故障保护通过。也不代表其他参数、全模块证明或形式化证明。',
        'research172仍为“两规则同时接受后停止”，此次为单独独立验收，不追认恢复链。条件恢复仍0/0、不可估计。',
        '',f"本轮模型0次；原生编译{cost['native_compiles']}次、执行{cost['native_executions']}次；编译{cost['compile_seconds']:.3f}s、执行{cost['execute_seconds']:.3f}s。",
        '', '候选和规则未根据本批结果修改。若未来使用本批失败调规则/模型/候选，整批应转为开发数据并重新准备独立测试。',
        '', '本次执行命令：','```powershell',f'wsl -- python3 scripts/research174_independent_acceptance.py run --prepared {q.old.rel(prep)} --out {q.old.rel(out)}','```',
        '运行目录不可重复使用，防止隐式重试。只读核验命令：','```powershell',f'wsl -- python3 scripts/research174_independent_acceptance.py verify --prepared {q.old.rel(prep)}','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    g.s.seal_files(out);print(json.dumps(answer,ensure_ascii=False),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','verify','run'])
    ap.add_argument('--prepared',type=Path);ap.add_argument('--out',type=Path);a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='verify':verify(a.prepared.resolve());print('VERIFIED174 no model')
    else:run(a.prepared.resolve(),a.out.resolve())
