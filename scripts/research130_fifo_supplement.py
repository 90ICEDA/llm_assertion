"""Execute the research129 local checklist with immutable research69 assertions.

Preparation seals all48 development cases before any native execution. No model
interface is instantiated. Existing RTL, oracle, assertions and archived runs
are never edited; failures terminate that case with no adaptive retry.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
from pathlib import Path
import random
import re
import time

import research17_loop as loop
import research32_runtime as extension
import research29_drain as drain
from research15_evidence import paired_ledger, merge_ledgers, INPUTS, marker_map
from research64_search_value import native_cost

ROOT, read, dump = loop.ROOT, loop.read, loop.dump
SOURCE = ROOT / 'deliverables/research129_fifo_gap_audit_20261026_r01'


def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p): return p.relative_to(ROOT).as_posix()


def schedule(task, seed):
    mode=task['mode']; rng=random.Random(seed); family=task['id'].removeprefix('d4p2_')
    if task['depth']==4 and task['pipeline']==2:
        # Reuse the already sealed research29 family and RNG schedules. Its
        # stimuli depend on family/seed, not pipeline. Parameter is explicit
        # here; neither the historical function nor its defaults are modified.
        source=next(c for c in drain.cases(seed) if c['depth']==4 and c['family']==family)
        rows=source['rows']
        return rows, dict(source='research29.cases depth4 family schedule',
            original_pipeline=1, applied_pipeline=2, family=family,
            generation_change='explicit parameter binding only; no observed output used')
    if mode in ('corrupt','duplicate_payload'):
        gap=8+rng.randrange(3); intents={3+i*gap for i in range(4)}
        reset={0,1}; low=set(); length=max(intents)+35
    elif mode=='reset_residue' or task['role']=='legal_control':
        intents={3}; reset={0,1,14,15}; low=set(range(2,16)); length=65
    else:
        release=26 if mode.startswith('long_') else 11
        intents={3}; reset={0,1}; low=set(range(2,release)); length=release+35
    values=rng.sample(range(1,2**32),length)
    rows=[dict(cycle=c,rst=int(c in reset),intent=int(c in intents),ready=int(c not in low),
        data=values[c],drain_due=int(c==length-1)) for c in range(length)]
    return rows,dict(source='fixed research129 recipe', reset_cycles=sorted(reset),
        presented_intent_cycles=sorted(intents), output_not_ready_cycles=sorted(low),
        acceptance='Actual handshake determined only by subsequent native trace.')


def prepare(out):
    plan=read(SOURCE/'supplemental_tests.json'); frozen=read(SOURCE/'fixed_version.json')
    candidate_path=ROOT/frozen['candidate_path']; candidate=read(candidate_path)
    assert loop.sha(candidate)==frozen['candidate_sha256']
    assert digest(candidate_path)==frozen['file_sha256']
    out.mkdir(parents=True,exist_ok=False)
    cases=[]
    for task in plan['tasks']:
        assert task['fixed_candidate_sha256']==loop.sha(candidate)
        for seed in task['seed_set']:
            rows, provenance=schedule(task,seed)
            assert len(rows)>=18 and all(r['ready'] and not r['intent'] and not r['rst'] for r in rows[-18:])
            cases.append(dict(id=f'supp130:s{seed}:{task["id"]}',task_id=task['id'],seed=seed,
                depth=task['depth'],pipeline=task['pipeline'],mode=task['mode'],role=task['role'],
                obligations=task['obligations'],rows=rows,split='development',provenance=provenance))
    assert len(cases)==48 and len({c['id'] for c in cases})==48
    assert {(c['depth'],c['pipeline']) for c in cases}=={(2,0),(4,1),(4,2)}
    assert {c['seed'] for c in cases}=={12907,12919}
    dump(out/'candidate.json',candidate); dump(out/'cases.json',cases)
    old=set(read(SOURCE/'development_promotion.json')['input_hashes'])
    dump(out/'development_inputs.json',dict(hashes=sorted({loop.sha(c['rows']) for c in cases}),
        overlaps_prior=sorted(old&{loop.sha(c['rows']) for c in cases}),
        status='Development supplements, never independent tests even when inputs are new.'))
    dump(out/'protocol.json',dict(scope='Exact research129 task/seed list; fixed research69 candidate.',
        candidate_sha256=loop.sha(candidate),model_calls=0,case_count=48,maximum_native_replays=96,
        maximum_compiles=3,maximum_smoke_runs=3,no_retries=True,no_candidate_changes=True,
        no_observed_result_changes_to_cases=True,
        acceptance='Each requested obligation needs legal paired inputs, correct-side satisfaction, first-attributed target, native trigger/detection, zero critical unknown/false positives. Legal controls must have actual reset cancellation or fair-drain exposure as applicable.',
        termination='A failing case records terminal result; no regeneration/retry/refinement. Continue other presealed cases; do not assert whole-cell pass when any requested case fails.',
        attribution='Later violations retained unknown; no global or whole-trajectory conclusion.',
        independent=False))
    inputs=[SOURCE/'supplemental_tests.json',SOURCE/'fixed_version.json',SOURCE/'development_promotion.json',candidate_path,
            extension.runtime.RTL,Path(__file__)] + list((ROOT/'scripts').glob('*.py'))
    dump(out/'source_bindings.json',{rel(p):digest(p) for p in set(inputs)})
    dump(out/'sealed.json',{p.name:digest(p) for p in out.iterdir() if p.is_file()})
    verify(out)
    print('PREPARED130',len(cases),'cases; native0 model0',flush=True)


def verify(prep):
    for name,h in read(prep/'sealed.json').items(): assert digest(prep/name)==h,name
    for name,h in read(prep/'source_bindings.json').items(): assert digest(ROOT/name)==h,name


def raw_audit(record,case,folder,candidate):
    trace=extension.runtime.parse_trace(folder/'execute.log')
    refs=loop.runtime.parse_reference(folder/'execute.log')
    assert trace==record['trace'] and refs==record['reference_trace']
    assert extension.runtime.oracle(trace,case['rows'])==record['oracle']
    assert loop.runtime.qualify_sampling(trace,refs)==record['sampling_qualification']
    assert record['candidate']==candidate
    log=(folder/'execute.log').read_text()
    for key,marker in (('triggers','TRIGGER'),('failures','ASSERT_FAIL')):
        actual={(a,int(b)) for a,b in re.findall(r'^'+marker+r' (\S+) cycle=(-?\d+)',log,re.M)}
        saved={(m['id'],int(re.search(r'cycle=(-?\d+)',m['detail'])[1])) for m in record['native'][key]}
        assert actual==saved
    assert 'NATIVE_RUN_COMPLETE' in log and (folder/'wave.vcd').stat().st_size>0


def assessment(case,fixed,mutant,group):
    info=loop.inspect(group['ledger']); records=[fixed]+([mutant] if mutant else [])
    native_ok=all(r['native'].get('compile_status')=='passed' and r['native'].get('execution_status')=='completed'
        and r['native'].get('tool_support_status')=='supported_for_compiled_constructs'
        and r['sampling_qualification']['status']=='passed' for r in records)
    legal=all(r['oracle']['legality']=='legal' and not r['oracle']['unknown'] for r in records)
    identical=mutant is None or [[{k:t.get(k) for k in INPUTS} for t in r['trace']] for r in (fixed,mutant)][0]==[
        {k:t.get(k) for k in INPUTS} for t in mutant['trace']]
    control_ok=not fixed['oracle']['violations'] and not fixed['native']['failures']
    obligations={}
    for ob in case['obligations']:
        selected={k for k,r in info['rows'].items() if r['obligation']==ob}
        counts={k:len(selected&info[k]) for k in ('detections','misses','false_positives','unknown','triggers')}
        target_points=[info['rows'][k] for k in sorted(selected & (info['detections']|info['misses']))]
        obligations[ob]=dict(**counts,actual_target_exposure=len(target_points),targets=target_points)
    target_ok=all(v['actual_target_exposure']>0 and v['detections']==v['actual_target_exposure'] and v['triggers']>0
        and not any(v[k] for k in ('misses','false_positives','unknown')) for v in obligations.values())
    legal_exposure=True
    if case['role']=='legal_control':
        target_ok=all(not r['oracle']['violations'] and not r['native']['failures'] for r in records)
        if case['mode']=='correct': legal_exposure=bool(fixed['oracle']['cancelled'])
        else: legal_exposure=all(any(c['obligation']=='drain_no_loss' and c['passed'] for c in r['oracle']['checks']) for r in records)
    passed=bool(native_ok and legal and identical and control_ok and target_ok and legal_exposure and not info['unknown'] and not info['false_positives'])
    reason=[]
    for name,ok in [('native_sampling',native_ok),('input_or_reference_legality',legal),('identical_accepted_inputs',identical),
        ('correct_control',control_ok),('target_or_legal_check',target_ok),('legal_applicability',legal_exposure),
        ('no_critical_unknown',not info['unknown']),('no_false_alarm',not info['false_positives'])]:
        if not ok: reason.append(name)
    return dict(case=case['id'],task_id=case['task_id'],depth=case['depth'],pipeline=case['pipeline'],seed=case['seed'],
        role=case['role'],mode=case['mode'],passed=passed,reasons=reason,obligations=obligations,
        counts=loop.counts(group),later_attribution_unknown=len(group['exclusions']),
        transaction_counts=[dict(mode=r['mode'],accepted=len(r['oracle']['transactions']),
            responded=sum(t['response_cycle'] is not None for t in r['oracle']['transactions']),
            cancelled=len(r['oracle']['cancelled']),pending=len(r['oracle']['pending']),
            actual_fair_samples=r['oracle']['drain_scope']['actual_fair_samples']) for r in records],
        full_trace_scope='first-attributed evidence only; later unknown retained')


def run(prep,out):
    verify(prep); out.mkdir(parents=True,exist_ok=False)
    candidate=read(prep/'candidate.json'); cases=read(prep/'cases.json')
    dump(out/'execution.json',dict(prepared=rel(prep),seal=digest(prep/'sealed.json'),candidate_sha256=loop.sha(candidate),
        script_sha256=digest(Path(__file__)),started=time.time(),model_calls=0,development_only=True))
    dump(out/'candidate.json',candidate)
    results=[]; builds={}; groups=[]; audited=0; complete=False
    try:
        with extension.installed():
            for i,case in enumerate(cases):
                key=(case['depth'],case['pipeline']); folder=out/'cases'/f'case_{i:02d}'
                dump(folder/'case.json',case)
                if key not in builds:
                    builds[key]=loop.runtime.build(candidate,out/f'compiled_d{key[0]}p{key[1]}',*key)
                build=builds[key]
                if build['native']['compile_status']!='passed':
                    result=dict(case=case['id'],task_id=case['task_id'],depth=key[0],pipeline=key[1],seed=case['seed'],
                        passed=False,reasons=['compile_or_support_failure'],obligations={},counts=None)
                else:
                    fixed=loop.runtime.execute(build,folder/'correct',case['rows'],'correct')
                    raw_audit(fixed,case,folder/'correct',candidate); audited+=1
                    mutant=None
                    if case['mode']!='correct':
                        mutant=loop.runtime.execute(build,folder/case['mode'],case['rows'],case['mode'])
                        raw_audit(mutant,case,folder/case['mode'],candidate); audited+=1
                    group=paired_ledger(fixed,mutant,case['id']);dump(folder/'ledger.json',group);groups.append(group)
                    result=assessment(case,fixed,mutant,group)
                dump(folder/'assessment.json',result);results.append(result);dump(out/'progress.json',results)
                print('SUPPLEMENT130',i+1,case['id'],result['passed'],result['reasons'],flush=True)
        complete=True
    finally:
        verify(prep);assert read(out/'candidate.json')==candidate
        cost=native_cost(out);dump(out/'cost.json',cost)
        combined=merge_ledgers(groups);dump(out/'combined.json',combined)
        dump(out/'outcome.json',dict(completed=complete,scheduled=48,executed=len(results),passed=sum(r['passed'] for r in results),
            failed=sum(not r['passed'] for r in results),raw_records_audited=audited,counts=loop.counts(combined),
            candidate_sha256=loop.sha(candidate),candidate_unchanged=True,model_calls=0,new_independent_tests=0))
        assert cost['total']['model_calls']==0 and cost['total']['native_compile_calls']<=3
        assert cost['total']['native_execute_calls']<=96 and cost['total']['compile_smoke_execute_calls']<=3
    report(prep,out,results)


def report(prep,out,results):
    matrix=[]
    for (d,p) in sorted({(r['depth'],r['pipeline']) for r in results}):
        for ob in loop.model.SPECS:
            relevant=[r for r in results if (r['depth'],r['pipeline'])==(d,p) and ob in r['obligations']]
            if not relevant:continue
            counts={k:sum(r['obligations'][ob][k] for r in relevant) for k in ('detections','misses','false_positives','unknown','triggers','actual_target_exposure')}
            passed=all(r['passed'] for r in relevant) and counts['actual_target_exposure']>0
            matrix.append(dict(depth=d,pipeline=p,obligation=ob,**counts,checklist_cases=len(relevant),passed=passed,
                cases=[r['case'] for r in relevant],scope='Only requested supplemental cells; not all parameters and all obligations.'))
    dump(out/'obligation_matrix.json',matrix)
    outcome=read(out/'outcome.json');cost=read(out/'cost.json')['total']
    promoted=read(SOURCE/'development_promotion.json')
    promoted['input_hashes']=sorted(set(promoted['input_hashes'])|set(read(prep/'development_inputs.json')['hashes']))
    promoted['additional_supplement']=dict(prepared=rel(prep),cases_sha256=digest(prep/'cases.json'),independent=False)
    dump(out/'future_development_exclusions.json',promoted)
    lines=['# research130 固定FIFO断言的本地补测', '',
        f'48个封存场景执行{len(results)}个，通过{outcome["passed"]}，失败{outcome["failed"]}。原生记录复核{outcome["raw_records_audited"]}份。',
        f'冻结research69集合 `{outcome["candidate_sha256"]}` 未改动；模型0、断言修改0、新独立测试0。',
        '本批使用已见问题设计，是开发补测。旧独立结果、失败及unknown不改写；不能当作全局保证或机制收益。', '',
        '|参数|义务|检出/实际曝光|漏报|误报|关键unknown|清单验收|', '|---|---|---:|---:|---:|---:|---|']
    for m in matrix:lines.append(f'|{m["depth"]}/{m["pipeline"]}|{m["obligation"]}|{m["detections"]}/{m["actual_target_exposure"]}|{m["misses"]}|{m["false_positives"]}|{m["unknown"]}|{m["passed"]}|')
    lines += ['', f'合并证据：{outcome["counts"]}。后续归因unknown仍为unknown，未加入确认检出分母。',
        f'成本：编译{cost["native_compile_calls"]}次、实验执行{cost["native_execute_calls"]}次、另编译冒烟{cost["compile_smoke_execute_calls"]}次、形式化0。',
        '复用research29原家族激励，显式将Depth4绑定Pipeline2；不改旧生成器默认、RTL或参考模型。实际接受/响应/取消关系在cases/case_*/correct|模式/replay.json；原生日志和wave.vcd在同目录。',
        '失败项：'+str([dict(case=r['case'],reasons=r['reasons']) for r in results if not r['passed']]), '',
        '只读封存复核：', '```powershell', f'wsl -- python3 scripts/research130_fifo_supplement.py verify --prepared {rel(prep)}', '```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('COMPLETE130',outcome,'cost',cost,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=['prepare','verify','run'])
    ap.add_argument('--out',type=Path);ap.add_argument('--prepared',type=Path);a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='verify':verify(a.prepared.resolve());print('SEALED130_VERIFIED; model0 native0')
    else:run(a.prepared.resolve(),a.out.resolve())
