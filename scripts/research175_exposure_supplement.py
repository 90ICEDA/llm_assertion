"""Bounded, separately sealed supplement for research174's exposure gaps.

No model or candidate edits. Reuse the original RTL, bench and research172 gate.
prepare does not select tests. run selects once after freeze, never replaces a
failed/duplicate/unexposed test. audit only rereads saved native records.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import random
import time
import research174_independent_acceptance as r

q=r.q;g=r.g
OLD_PREP=q.ROOT/'deliverables/research174_independent_prepare_20261028_r01'
OLD_RUN=q.ROOT/'deliverables/research174_independent_run_20261028_r01'
OLD_REPORT=q.ROOT/'deliverables/research174_independent_report_20261028_r01'


def seal_check(folder):
    for p,h in q.read(folder/'seal.json').items():assert q.sha(folder/p)==h,p


def chains(trace,reference):
    """Actual held output -> same transaction's accepted release, not ready alone."""
    by_cycle={v['cycle']:v for v in trace};found=[]
    for e in reference['episodes']:
        end=e['transfer_cycle']
        if e['status']!='accepted' or end is None or not e['alignment_known'] or not e['stable']:continue
        values=[by_cycle[c] for c in e['cycles']]
        if len(values)<2:continue
        held=values[:-1];last=values[-1]
        if not all(not v['rst'] and v['mv'] and not v['mr'] for v in held):continue
        if not (last['cycle']==end and not last['rst'] and last['mv'] and last['mr']):continue
        if [v['cycle'] for v in values]!=list(range(e['start_cycle'],end+1)):continue
        if not e['request_ids'] or not all(x['cycle']<e['start_cycle'] for x in e['requests']):continue
        if not all(reference['samples'][v['cycle']]['episode']==e['id'] for v in values):continue
        found.append(dict(sid=e['sid'],episode=e['id'],request_ids=e['request_ids'],
            input_acceptance_cycles=[x['cycle'] for x in e['requests']],presentation_cycle=e['start_cycle'],
            held_cycles=[v['cycle'] for v in held],release_cycle=end,
            expected_keep=e['expected_keep'],expected_last=e['expected_last'],
            samples=[{k:v[k] for k in ('cycle','phase','rst','mv','mr','md','mk','ml')} for v in values]))
    return found


def prepare(out):
    r.verify(OLD_PREP);seal_check(OLD_RUN);seal_check(OLD_REPORT)
    assert q.read(OLD_RUN/'result.json')['scenario_passed']==37
    # Read-only archived exposure checks: no prospective test generated here.
    old_ev=q.read(OLD_RUN/'evaluation.json');checks=[]
    for rev in ('before','after'):
        tr=old_ev['evidence'][rev]['trace'];ref=g.audit.replay(tr);ch=chains(tr,ref)
        ids={x['sid'] for x in ch}
        for sid in (1,7,22):
            ok=sid not in ids;checks.append(dict(check=f'{rev} old unexposed{sid} rejected',passed=ok));assert ok
        for s in q.read(OLD_RUN/'scenario_results.json'):
            if s['stratum']=='reset_cancel':
                ok=s['id'] not in ids;checks.append(dict(check=f'{rev} reset cancellation not release{s["id"]}',passed=ok));assert ok
        ok=len(ids)==29;checks.append(dict(check=rev+' actual released scenes29',passed=ok));assert ok
    out.mkdir(parents=True,exist_ok=False)
    for name in ('candidate.json',): (out/name).write_bytes((OLD_PREP/name).read_bytes())
    for rev in ('before','after'):
        p=out/'rtl'/rev/'axis_adapter.v';p.parent.mkdir(parents=True);p.write_bytes((OLD_PREP/'rtl'/rev/'axis_adapter.v').read_bytes())
    exclusions=q.read(OLD_PREP/'development_exclusions.json')
    old_novel=q.read(OLD_RUN/'actual_novelty.json')
    exclusions['actual_trace_signatures']=sorted(set(exclusions['actual_trace_signatures']) | set(old_novel['independent_signatures']['before']) | set(old_novel['independent_signatures']['after']))
    exclusions['additional_prior_batch']=dict(path=q.old.rel(OLD_RUN),seal_sha256=q.sha(OLD_RUN/'seal.json'),
        role='Observed coverage gaps inform supplementary test scheduling only; not candidate or acceptance-rule changes. Never reuse these scenes as new independent data.')
    q.dump(out/'development_exclusions.json',exclusions)
    protocol=dict(purpose='targeted_exposure_supplement_not_mechanism_or_recovery_experiment',seed=17507,
        config=g.s.PARAMETERS,cycles_per_scenario=96,scenario_count=12,
        generation=dict(lengths=[6,7,13],gaps=[3],ready_delays=[32,40],keeps=[0,1],stall_periods=[2,3,5],
            semantics='Same existing bench; ready remains low before fixed delay, then follows periodic ready rule. No adaptive reroll.'),
        known_gap_links={'6':22,'7':7,'13':1},
        checks=['same unchanged model SVA and original RTL','legal identical inputs before/after','complete trace and fixed-reference pass',
            'each scene has actual valid&&!ready followed without reset by the SAME aligned output valid&&ready',
            'hold_valid and both hold_payload properties trigger at every held-check and release cycle',
            'each scene transfers entire frame and exposes legal partial tail on fixed RTL',
            'KEEP0 scenes expose and directly detect both original KEEP target classes',
            'KEEP1 scenes have no independent reference violations on either RTL',
            'no false positives, key unknown, or duplicate actual transaction signature'],
        budget=dict(model_calls=0,formal_calls=0,max_native_compiles=2,max_native_executions=2,retries=0,replacements=0),
        stop='One fixed batch; any execution failure, no exposure, duplicate, miss, false alarm or unknown remains failure. No rerun to seek pass.',
        prior='research174 remains37/40; never merge as40/40. research172 remains both_accept_no_discrimination.',
        scope='8to32 original adapter KEEP repair. Holding is legal-behavior exposure, not injected hold-fault detection. No new reset test.',
        data_role='Targeted supplementary verification designed after observing old coverage gaps; not an unbiased repeat or new discovery. Candidate and rules unchanged. If used for candidate/rule changes, entire batch becomes development and fresh holdout is required.')
    q.dump(out/'protocol.json',protocol);q.dump(out/'local_checks.json',checks)
    bindings=q.read(OLD_PREP/'code_bindings.json')
    for p in [Path(__file__),OLD_PREP/'seal.json',OLD_RUN/'seal.json',OLD_REPORT/'seal.json',OLD_RUN/'result.json']:
        bindings[q.old.rel(p)]=q.sha(p)
    q.dump(out/'code_bindings.json',bindings)
    q.dump(out/'freeze.json',dict(created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        candidate_hash=r.digest(q.read(out/'candidate.json')),candidate_file_sha256=q.sha(out/'candidate.json'),
        rtl={rev:q.sha(out/'rtl'/rev/'axis_adapter.v') for rev in ('before','after')},protocol_hash=q.sha(out/'protocol.json'),
        exclusions_hash=q.sha(out/'development_exclusions.json'),test_selection_not_yet_done=True,
        old_result_sha256=q.sha(OLD_RUN/'result.json'),pilot_sha256=q.sha(r.PILOT/'outcome.json')))
    g.s.seal_files(out);verify(out)
    print('SEALED175',len(checks),'archived exposure checks; tests not selected; model0',flush=True)


def verify(prep):
    g.s.verify_files(prep);r.verify(OLD_PREP);seal_check(OLD_RUN);seal_check(OLD_REPORT)
    freeze=q.read(prep/'freeze.json')
    assert q.sha(prep/'candidate.json')==q.sha(OLD_PREP/'candidate.json')==freeze['candidate_file_sha256']
    assert q.sha(OLD_RUN/'result.json')==freeze['old_result_sha256']
    assert q.sha(r.PILOT/'outcome.json')==freeze['pilot_sha256']


def generate(protocol):
    rng=random.Random(protocol['seed']);cfg=protocol['generation'];rows=[]
    for length in cfg['lengths']:
        for delay in cfg['ready_delays']:
            for keep in cfg['keeps']:
                rows.append(dict(frames=[length],gap=3,ready_delay=delay,keep=keep,reset_at=-1,
                    stall_period=rng.choice(cfg['stall_periods']),scope='public' if length==6 else 'history',
                    stratum='legal' if keep else 'original_KEEP_target',old_gap_id=protocol['known_gap_links'][str(length)]))
    rng.shuffle(rows)
    return [dict(v,id=i) for i,v in enumerate(rows)]


def evaluate(prep,run):
    candidate=q.read(prep/'candidate.json');rows=q.read(run/'scenarios.json');ev=g.measure(candidate,run/'native',rows)
    references={};all_chains={};stats=[];novel={};tables={}
    excluded=set(q.read(prep/'development_exclusions.json')['actual_trace_signatures'])
    complete=all(rev in ev['evidence'] and len(ev['evidence'][rev]['trace'])==len(rows)*96 for rev in ('before','after'))
    if complete and 'obligation_evaluation' in ev:
        for rev in ('before','after'):
            tr=ev['evidence'][rev]['trace'];references[rev],tables[rev]=g.reference_table(tr)
            all_chains[rev]=chains(tr,references[rev]);novel[rev]=g.c.actual_signatures(tr)
        for row in rows:
            sid=row['id'];rr={};issues=[]
            for rev in ('before','after'):
                d=ev['obligation_evaluation'][rev];tr=ev['evidence'][rev]['trace'];oracle=ev['evidence'][rev]['oracle']
                own={a:set(v) for a,v in d['own_effective_triggers'].items()}
                required=[(a,v['cycle']) for a in candidate for v in tr if v['sid']==sid and any(tables[rev][v['cycle']][ob]['applicable'] for ob in a['obligations'])]
                missing=[dict(label=a['label'],cycle=c) for a,c in required if c not in own[a['label']]]
                ch=[x for x in all_chains[rev] if x['sid']==sid]
                cov=[x for x in d['target_coverage'] if x['cycle']//96==sid]
                events=[x for x in oracle['events'] if x['kind']=='output' and x['sid']==sid]
                failures=[x for x in oracle['failures'] if x['sid']==sid]
                samples=[v for v in tr if v['sid']==sid]
                inputs=[v['cycle'] for v in samples if not v['rst'] and v['sv'] and v['sr']]
                record=dict(chains=ch,target_exposure=dict(Counter(ob for x in cov for ob in x['obligations'])),
                    target_misses=sum(not x['detected'] for x in cov),target_untriggered=sum(not x['triggered'] for x in cov),
                    missing_obligation_triggers=missing,native_false_positive_cycles=[c for c in ev['false_'+rev] if c//96==sid],
                    reference_failures=failures,accepted_input_cycles=inputs,
                    output_acceptance_cycles=[x['cycle'] for x in events],partial_tail_outputs=sum(x['last'] and 0<x['expected_keep']<15 for x in events),
                    actual_trigger_counts={a:len([c for c in cs if c//96==sid]) for a,cs in own.items()},
                    novel=novel[rev][sid] not in excluded and novel[rev].count(novel[rev][sid])==1,
                    applicable_counts={ob:sum(tables[rev][v['cycle']][ob]['applicable'] for v in samples) for ob in g.OBLIGATIONS})
                rr[rev]=record
                if not ch:issues.append(rev+':unexposed_same_transaction_stall_release')
                if missing:issues.append(rev+':missing_required_trigger')
                if not record['novel']:issues.append(rev+':duplicate_trace')
                if record['native_false_positive_cycles']:issues.append(rev+':false_positive')
                if len(inputs)!=row['frames'][0] or not record['partial_tail_outputs']:issues.append(rev+':incomplete_frame_or_partial_tail')
                if failures and (rev=='after' or row['keep']==1):issues.append(rev+':legal_reference_failure')
            if row['keep']==0:
                if not all(rr['before']['target_exposure'].get(ob) for ob in g.KEEP):issues.append('unexposed_original_KEEP_class')
                if rr['before']['target_misses'] or rr['before']['target_untriggered']:issues.append('target_miss_or_untriggered')
            if ev['unknown']:issues.append('critical_unknown')
            stats.append(dict(id=sid,configuration=row,passed=not issues,issues=issues,revision=rr))
    else:
        stats=[dict(id=row['id'],configuration=row,passed=False,issues=['incomplete_native_or_unknown_reference']) for row in rows]
    exposure=Counter(ob for x in ev.get('obligation_evaluation',{}).get('before',{}).get('target_coverage',[]) for ob in x['obligations'])
    result=dict(status='passed' if all(s['passed'] for s in stats) and ev['history'] else 'failed_or_unresolved',
        passed=sum(s['passed'] for s in stats),total=len(rows),original_KEEP_exposure=dict(exposure),
        misses=len(ev.get('public_missed',[]))+len(ev.get('history_missed',[])),
        false_positives={rev:len(ev['false_'+rev]) for rev in ('before','after')},unknown=ev['unknown'],
        same_transaction_release_scenes={rev:len({c['sid'] for c in all_chains.get(rev,[])}) for rev in ('before','after')},
        same_transaction_release_events={rev:len(all_chains.get(rev,[])) for rev in ('before','after')},
        candidate_unchanged=q.sha(prep/'candidate.json')==q.sha(OLD_PREP/'candidate.json'),old_result='37/40 unchanged',
        data_role='targeted_supplement_no_candidate_or_rule_changes',conditioned_recovery='0/0 not estimable',
        hold_fault_exposure=0,hold_fault_detection_rate=None,reset_scope='not tested in this supplement')
    return ev,stats,references,all_chains,result


def run(prep,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False)
    candidate=q.read(prep/'candidate.json');protocol=q.read(prep/'protocol.json');rows=generate(protocol)
    assert len(rows)==protocol['scenario_count']
    q.dump(out/'scenarios.json',rows)
    q.dump(out/'input_freeze.json',dict(created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        prepared_seal=q.sha(prep/'seal.json'),candidate_hash=r.digest(candidate),scenarios_hash=r.digest(rows),rerolls=0))
    native={}
    for rev in ('before','after'):
        native[rev]=q.old.native.run_native(q.bench(candidate,rows),out/'native'/rev,extra_sources=[prep/'rtl'/rev/'axis_adapter.v'])
        q.dump(out/'native_results.json',native)
        print('NATIVE175',rev,native[rev]['compile_status'],native[rev]['execution_status'],flush=True)
    ev,stats,refs,ch,result=evaluate(prep,out)
    for name,obj in [('evaluation',ev),('scenario_results',stats),('transaction_reference',refs),('held_release_chains',ch)]:q.dump(out/(name+'.json'),obj)
    result['cost']=dict(model_calls=0,formal_calls=0,native_compiles=len(native),native_executions=sum(v['native_simulation_calls'] for v in native.values()),
        compile_seconds=sum(v['compile']['wall_seconds'] for v in native.values()),execute_seconds=sum(v.get('execute',{}).get('wall_seconds',0) for v in native.values()))
    q.dump(out/'result.json',result);verify(prep)
    lines=['# research175 背压曝光补充验收','',f"结果：**{result['status']}，{result['passed']}/{len(rows)}场景**。研究174保持37/40，不合并、不追改。",'',
        f"两类原始KEEP违例曝光：{result['original_KEEP_exposure']}；漏报{result['misses']}；误报{result['false_positives']}；关键unknown={len(result['unknown'])}。",
        f"同一事务实际保持→解除握手场景：{result['same_transaction_release_scenes']}；对应事件：{result['same_transaction_release_events']}。",'',
        '|场景|旧曝光缺口ID|长度|KEEP输入|通过|问题|','|---|---|---|---|---|---|']
    lines += [f"|{s['id']}|{s['configuration']['old_gap_id']}|{s['configuration']['frames'][0]}|{s['configuration']['keep']}|{s['passed']}|{s['issues']}|" for s in stats]
    lines += ['', '12个场景由封存协议在冻结后生成；6个合法输入与6个原始KEEP缺陷配对输入；均使用相同8→32原始RTL、原测试平台及未改动的5条模型SVA。此前40场景及开发轨迹全部排除；失败或重复不替换。',
        '对每个保持区间保存输入接受、输出呈现、逐周期稳定性及同事务解除握手，逐性质检查适用周期的触发。SVA失败来自原生执行；触发来自执行中的前件诊断及周期对齐，不是形式化cover。',
        '本批由已知曝光缺口指导测试调度，属于定向补充验收，不是无偏独立复现、搜索新发现或防退化恢复实验。未注入保持故障，其故障漏报率不可估计；本批不新增复位验证。',
        '候选和接受规则未改；不把旧37/40改为40/40。若后续据本批修改候选或规则，整批转为开发数据，另做新的独立验收。H/R等价与条件恢复0/0不变。',
        '',f"实际成本：{result['cost']}",'', '执行命令（运行目录必须不存在）：','```powershell',
        f'wsl -- python3 scripts/research175_exposure_supplement.py run --prepared {q.old.rel(prep)} --out {q.old.rel(out)}','```',
        '只读复核（不调用模型或仿真）：','```powershell',f'wsl -- python3 scripts/research175_exposure_supplement.py audit --prepared {q.old.rel(prep)} --out {q.old.rel(out)}','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');g.s.seal_files(out)
    print(json.dumps(result,ensure_ascii=False),flush=True)


def audit(prep,run):
    verify(prep);seal_check(run)
    inputs=q.read(run/'input_freeze.json');rows=q.read(run/'scenarios.json')
    assert inputs['prepared_seal']==q.sha(prep/'seal.json')
    assert inputs['created_utc']>=q.read(prep/'freeze.json')['created_utc']
    assert rows==generate(q.read(prep/'protocol.json'))
    ev,stats,refs,ch,result=evaluate(prep,run)
    for name,value in [('evaluation',ev),('scenario_results',stats),('transaction_reference',refs),('held_release_chains',ch)]:
        assert json.loads(json.dumps(value))==q.read(run/(name+'.json')),name
    saved=q.read(run/'result.json');saved.pop('cost');assert saved==result
    for rev in ('before','after'):
        assert q.bench(q.read(prep/'candidate.json'),rows).strip()==(run/'native'/rev/'tb.sv').read_text().strip()
    print('AUDITED175 all saved reference, chain, gate and frozen-source records match; no new simulation/model',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','verify','run','audit']);p.add_argument('--prepared',type=Path);p.add_argument('--out',type=Path);a=p.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='verify':verify(a.prepared.resolve());print('VERIFIED175')
    elif a.action=='run':run(a.prepared.resolve(),a.out.resolve())
    else:audit(a.prepared.resolve(),a.out.resolve())
