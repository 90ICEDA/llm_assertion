"""Frozen FIFO validation: seal protocol, generate unseen inputs, execute, audit.

No model, candidate selection, refinement or outcome-adaptive test generation.
Known artificial fault classes; independent inputs, not unseen defect classes.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random
import secrets
import time

import research130_fifo_supplement as base
from research15_evidence import paired_ledger, merge_ledgers

ROOT, read, dump, sha = base.ROOT, base.read, base.dump, base.loop.sha
digest, rel = base.digest, base.rel
PARAMS = ((2, 0), (4, 1), (4, 2), (8, 2))
FAMILIES = ('corrupt', 'duplicate_payload', 'reset_residue', 'stall_glitch',
    'valid_withdraw_stalled', 'valid_withdraw_release',
    'long_valid_withdraw_stalled', 'long_valid_withdraw_release',
    'isolated_tail', 'continuous_tail', 'parked_tail', 'reset_then_tail',
    'legal_three', 'reset_cancels_tail', 'legal_reset_cancel', 'legal_burst')
OBS = tuple(base.loop.model.SPECS)
FROZEN = ROOT/'deliverables/research69_pilot_20261024_r01/core/frozen_candidate.json'
EXPECTED = 'ef3974b9ac0dd7a79f008564d7af4a43b77e9befdc1da93bfb4ba79543bca3da'


def row_sets(obj):
    if isinstance(obj, list):
        if obj and all(isinstance(r, dict) and {'rst','intent','ready','data'} <= r.keys() for r in obj):
            yield obj
        else:
            for x in obj: yield from row_sets(x)
    elif isinstance(obj, dict):
        for x in obj.values(): yield from row_sets(x)


def timing_hash(rows):
    return sha([{k:r.get(k, 0) for k in ('cycle','rst','intent','ready','drain_due')} for r in rows])


def seal(out, inventory):
    assert sha(read(FROZEN)) == EXPECTED
    out.mkdir(parents=True, exist_ok=False)
    dump(out/'candidate.json', read(FROZEN))
    protocol = dict(candidate_sha256=EXPECTED, parameters=PARAMS, families=FAMILIES,
        seed_count=2, cases=128, maximum_compiles=4, maximum_experiment_replays=240,
        maximum_compile_smoke_runs=4, model_calls=0, formal_calls=0,
        randomization='Draw two 63-bit seeds ONCE after protocol seal. Within each parameter/family generate schedules and unique 32-bit values. Reject only exact-input or timing-only collisions with old/new inputs, at most 100 draws per cell; no execution outcomes available.',
        acceptance='All 128 prespecified cases healthy and legal, controls no failures, every target detected with native trigger and confirmed attribution; all 20 parameter/obligation cells exposed with zero missed target/false positive/critical unknown. Actual reset cancellation, stalls/release, paired transactions and >=18 fair drain cycles checked from native records.',
        unknown='Later events after first violation in same reset epoch remain attribution unknown, excluded from confirmed target denominator; any such event forbids full-trajectory completeness claim.',
        stop='No model, edits, retries, replacement cases or candidate selection. Complete all prespecified cases; infrastructure errors stop with incomplete status. Failed/no-exposure cases stay failed; no resampling. Later refinement requires promoting entire batch to development.',
        scope='Original axis_fifo module plus pre-existing artificial boundary faults; same known mechanisms, newly sampled inputs. Finite first-attributed targets only; no global/full-trace/formal/historical-bug claim.',
        split='independent_test', frozen_before_inputs=True, git_commit=None)
    dump(out/'protocol.json', protocol)
    paths=sorted({ROOT/p.replace('\\','/') for p in inventory.read_text(encoding='utf-8-sig').splitlines() if p})
    # Inventory includes all existing stimulus/cases/split/exclusion files, not outcomes.
    # Reading them only extracts input identities, never scores or candidate choices.
    sources=[]; hashes=set(); timings=set(); cache={}
    def ingest(path):
        data=path.read_bytes()
        import hashlib
        return path, hashlib.sha256(data).hexdigest(), data
    with ThreadPoolExecutor(max_workers=12) as pool:
        for i,(p,h,data) in enumerate(pool.map(ingest,paths)):
            if h not in cache:
                obj=json.loads(data.decode('utf-8-sig'))
                rows=list(row_sets(obj))
                extra=[]
                if isinstance(obj,dict):
                    for key in ('input_hashes','hashes'):
                        extra.extend(x for x in obj.get(key,[]) if isinstance(x,str) and len(x)==64)
                cache[h]=([sha(r) for r in rows],[timing_hash(r) for r in rows],extra)
            hs,ts,extra=cache[h]; hashes.update(hs); hashes.update(extra); timings.update(ts)
            sources.append(dict(path=rel(p),sha256=h,input_count=len(hs)))
            if (i+1)%5000==0: print('EXCLUSIONS132',i+1,len(hashes),flush=True)
    promotion=ROOT/'deliverables/research130_local_20261026_r01/future_development_exclusions.json'
    hashes.update(read(promotion)['input_hashes'])
    dump(out/'exclusions.json',dict(input_hashes=sorted(hashes),timing_hashes=sorted(timings),
        sources=sources,additional_promotion=rel(promotion),promotion_sha256=digest(promotion),
        scope='All inventoried existing FIFO stimulus/row-list inputs, old splits, prepared cases, plus promoted audit/supplement inputs. Same mechanisms are allowed; exact or timing-only duplicate inputs are not.'))
    bindings={rel(p):digest(p) for p in set(list((ROOT/'scripts').glob('*.py'))+[FROZEN,base.extension.runtime.RTL,inventory,promotion])}
    dump(out/'source_bindings.json',bindings)
    dump(out/'tools.json',dict(verilator=str(base.extension.runtime.__file__),
        note='Actual native compiler version, argv and flags recorded by unchanged runtime in each compiled directory.'))
    dump(out/'freeze.json',dict(created_unix=time.time(),candidate_sha256=EXPECTED,
        candidate_file_sha256=digest(FROZEN),protocol_sha256=digest(out/'protocol.json'),
        inputs_generated=False,model_calls=0))
    dump(out/'sealed.json',{p.name:digest(p) for p in out.iterdir() if p.is_file()})
    verify(out)
    print('SEALED132',len(paths),'source files',len(hashes),'excluded inputs',len(timings),'excluded timing schedules',flush=True)


def verify(prep):
    for name,h in read(prep/'sealed.json').items(): assert digest(prep/name)==h,name
    for name,h in read(prep/'source_bindings.json').items(): assert digest(ROOT/name)==h,name
    assert sha(read(prep/'candidate.json'))==EXPECTED and sha(read(FROZEN))==EXPECTED


def schedule(rng, family):
    start=rng.randint(5,12); gap=rng.randint(9,15); fair=rng.randint(24,40)
    resets=set(range(rng.randint(2,4))); low=set(); intents=[start+j*gap for j in range(4)]
    if family in ('reset_residue','legal_reset_cancel'):
        intents=[start]; reset_at=start+rng.randint(15,22)
        resets.update(range(reset_at,reset_at+rng.randint(2,4)))
        low=set(range(2,max(resets)+1))
    elif family in ('stall_glitch','valid_withdraw_stalled','valid_withdraw_release',
                     'long_valid_withdraw_stalled','long_valid_withdraw_release'):
        intents=[start]; release=start+(rng.randint(23,33) if family.startswith('long_') else rng.randint(10,15))
        low=set(range(2,release))
    elif family=='continuous_tail': intents=list(range(start,start+4))
    elif family=='parked_tail':
        release=start+3*gap;low=set(range(2,release));intents[-1]=release+rng.randint(9,14)
    elif family=='reset_then_tail':
        reset_at=start+rng.randint(14,19);resets.update(range(reset_at,reset_at+3))
        low=set(range(2,reset_at+3));intents=[start,start+5]+[reset_at+7+j*gap for j in range(4)]
    elif family=='legal_three': intents=intents[:3]
    elif family=='reset_cancels_tail':
        reset_at=intents[-1]+rng.randint(13,18);resets.update(range(reset_at,reset_at+3))
    elif family=='legal_burst':
        # Source driver holds presented request until handshake. This forces
        # genuine input backpressure, then concurrent accepted input/output.
        intents=list(range(start,start+65)); low=set(range(2,start+rng.randint(30,36)))
    length=max(max(intents),max(resets),max(low,default=0))+fair+2
    values=rng.sample(range(1,2**32),length)
    return [dict(cycle=c,rst=int(c in resets),intent=int(c in intents),ready=int(c not in low),
                 data=values[c],drain_due=int(c==length-1)) for c in range(length)]


def generate(prep,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False)
    excluded=read(prep/'exclusions.json');hs=set(excluded['input_hashes']);ts=set(excluded['timing_hashes'])
    seeds=[secrets.randbits(63) for _ in range(2)]; assert len(set(seeds))==2
    dump(out/'draw.json',dict(seeds=seeds,drawn_unix=time.time(),protocol_seal=digest(prep/'sealed.json')))
    cases=[]; collisions=[]
    for seed in seeds:
        rng=random.Random(seed)
        for depth,pipeline in PARAMS:
            for family in FAMILIES:
                for attempt in range(100):
                    rows=schedule(rng,family);h=sha(rows);t=timing_hash(rows)
                    if h not in hs and t not in ts: break
                    collisions.append(dict(seed=seed,depth=depth,pipeline=pipeline,family=family,attempt=attempt))
                else: raise RuntimeError('Input uniqueness budget exhausted; no native run allowed')
                hs.add(h);ts.add(t)
                mode=family if family in base.extension.runtime.MODES or family in (
                    'stall_glitch','valid_withdraw_stalled','valid_withdraw_release',
                    'long_valid_withdraw_stalled','long_valid_withdraw_release') else 'drop'
                if family in ('legal_burst','legal_reset_cancel'):mode='correct'
                role='legal_control' if family.startswith('legal_') or family=='reset_cancels_tail' else 'paired_target'
                if family in ('corrupt','duplicate_payload'):obs=['order_payload']
                elif family in ('reset_residue','legal_reset_cancel'):obs=['no_unsolicited_output','reset_cancellation']
                elif 'stall' in family or 'withdraw' in family:obs=['stall_stability']
                elif family=='legal_burst':obs=list(OBS)
                else:obs=['drain_no_loss']
                cases.append(dict(id=f'ind132:s{seed}:d{depth}p{pipeline}:{family}',task_id=family,
                    depth=depth,pipeline=pipeline,seed=seed,family=family,mode=mode,role=role,
                    obligations=obs,rows=rows,split='independent_test',input_sha256=h,timing_sha256=t))
    assert len(cases)==128 and all(len(c['rows'])>=18 for c in cases)
    dump(out/'cases.json',cases);dump(out/'collision_log.json',collisions)
    dump(out/'split.json',dict(created_unix=time.time(),protocol_seal=digest(prep/'sealed.json'),
        candidate_sha256=EXPECTED,cases_sha256=digest(out/'cases.json'),seeds=seeds,
        previous_input_overlap=0,previous_timing_overlap=0,split='independent_test',
        candidate_selected_before_test_generation=True,known_mechanisms=True))
    dump(out/'sealed.json',{p.name:digest(p) for p in out.iterdir() if p.is_file()})
    print('GENERATED132 128 cases; no executions; collision-only redraws',len(collisions),flush=True)


def check_inputs(prep,inputs):
    verify(prep)
    for n,h in read(inputs/'sealed.json').items():assert digest(inputs/n)==h,n
    assert read(inputs/'split.json')['protocol_seal']==digest(prep/'sealed.json')
    ex=read(prep/'exclusions.json');hs=set(ex['input_hashes']);ts=set(ex['timing_hashes'])
    cases=read(inputs/'cases.json')
    assert len(cases)==128 and len({sha(c['rows']) for c in cases})==128
    assert len({timing_hash(c['rows']) for c in cases})==128
    assert not hs&{sha(c['rows']) for c in cases} and not ts&{timing_hash(c['rows']) for c in cases}
    return cases


def assess(c,a,b,g):
    result=base.assessment(c,a,b,g);info=base.loop.inspect(g['ledger']);checks={}
    if c['role']=='legal_control':
        records=[a]+([b] if b else [])
        checks['native_and_sampling']=all(r['native']['compile_status']=='passed' and r['native']['execution_status']=='completed'
            and r['sampling_qualification']['status']=='passed' for r in records)
        checks['legal_no_violations']=all(r['oracle']['legality']=='legal' and not r['oracle']['unknown'] and not r['oracle']['violations'] and not r['native']['failures'] for r in records)
        checks['no_critical_unknown']=not info['unknown'] and not info['false_positives']
        checks['drained']=all(not r['oracle']['pending'] and r['oracle']['drain_scope']['actual_fair_samples']>=18 for r in records)
        if c['family'] in ('legal_reset_cancel','reset_cancels_tail'):
            checks['actual_reset_cancellation']=all(bool(r['oracle']['cancelled']) for r in records)
        if c['family']=='legal_burst':
            tr=a['trace']
            checks['actual_input_backpressure']=any(t['svalid'] and not t['sready'] for t in tr)
            checks['actual_simultaneous_acceptances']=any(t['svalid'] and t['sready'] and t['mvalid'] and t['mready'] for t in tr)
            checks['actual_multiple_transactions']=len(a['oracle']['transactions'])>=8
        result['passed']=bool(all(checks.values()));result['reasons']=[k for k,v in checks.items() if not v]
    else:
        targets=[t for t in g['ledger'] if t['oracle']['verdict']=='violated' and t['obligation'] in c['obligations']]
        checks['actual_confirmed_target']=bool(targets)
        if c['mode']=='drop':
            pending=b['oracle']['pending']
            checks['one_unresolved_transaction']=len(pending)==1
            checks['only_final_drain_violation']=bool(b['oracle']['violations']) and all(v['cycle']==len(c['rows'])-1 and v['obligation']=='drain_no_loss' for v in b['oracle']['violations'])
            checks['fair_drain']=all(r['oracle']['drain_scope']['actual_fair_samples']>=18 for r in (a,b))
            checks['same_transaction_responded_on_correct_side']=all(any(x['transaction_id']==p['transaction_id'] and x['response_cycle'] is not None for x in a['oracle']['transactions']) for p in pending)
        elif c['mode']=='reset_residue':
            checks['actual_accepted_cancellation']=bool(a['oracle']['cancelled'])
            checks['both_reset_and_unsolicited_exposed']={t['obligation'] for t in targets}=={'reset_cancellation','no_unsolicited_output'}
        elif c['mode']=='duplicate_payload':
            tx=b['oracle']['transactions']
            checks['fourth_repeats_third']=len(tx)==4 and tx[3]['observed_data']==tx[2]['data'] and tx[3]['data']!=tx[2]['data']
        elif c['mode']!='corrupt':
            samples={t['cycle']:t for t in b['reference_trace']}
            fixed={t['cycle']:t for t in a['trace']}
            for i,t in enumerate(targets):
                prev,now=samples[t['cycle']-1],samples[t['cycle']]
                checks[f'{i}:stall_anchor']=bool(prev['mvalid'] and not prev['mready'] and not prev['rst'] and not now['rst'])
                if 'release' in c['mode']:checks[f'{i}:release']=now['mready']==1
                if 'stalled' in c['mode']:checks[f'{i}:still_backpressured']=now['mready']==0
                if 'withdraw' in c['mode']:checks[f'{i}:withdrawn']=now['mvalid']==0 and now['mdata']==prev['mdata']
                if c['mode'].startswith('long_'):
                    n=0
                    for cyc in range(t['cycle']-1,-1,-1):
                        s=fixed[cyc]
                        if s['rst'] or not s['mvalid'] or s['mready']:break
                        n+=1
                    checks[f'{i}:eight_actual_stalled_cycles']=n>=8
        result['passed']=result['passed'] and all(checks.values())
        result['reasons'] += [k for k,v in checks.items() if not v]
    result['exposure_checks']=checks
    return result


def cost(out):
    comp=sorted(out.glob('compiled_*/compile.json'));smoke=sorted(out.glob('compiled_*/execute.json'))
    exp=sorted((out/'cases').glob('case_*/*/execute.json'))
    assert not set(exp)&set(smoke)
    return dict(model_calls=0,formal_calls=0,compile_calls=len(comp),experiment_replays=len(exp),
        compile_smoke_runs=len(smoke),total_simulator_executions=len(exp)+len(smoke),
        compile_wall_seconds=sum(read(p)['wall_seconds'] for p in comp),
        experiment_wall_seconds=sum(read(p)['wall_seconds'] for p in exp),
        smoke_wall_seconds=sum(read(p)['wall_seconds'] for p in smoke),
        commands=[dict(path=rel(p),sha256=digest(p)) for p in comp+smoke+exp])


def summarize(prep,inputs,out,results,groups,complete,error=None):
    merged=merge_ledgers(groups);dump(out/'combined.json',merged)
    matrices=[]
    for d,p in PARAMS:
        param=[r for r in results if (r['depth'],r['pipeline'])==(d,p)]
        for ob in OBS:
            relevant=[r for r in param if ob in r.get('obligations',{})]
            vals={k:sum(r['obligations'][ob][k] for r in relevant) for k in ('actual_target_exposure','detections','misses','false_positives','unknown','triggers')}
            matrices.append(dict(depth=d,pipeline=p,obligation=ob,**vals,
                passed=bool(vals['actual_target_exposure'] and all(r['passed'] for r in relevant)),
                evaluated_cases=len(relevant)))
    dump(out/'obligation_matrix.json',matrices); cc=cost(out);dump(out/'cost.json',cc)
    totals=base.loop.counts(merged)
    outcome=dict(completed=complete,error=error,scheduled=128,executed=len(results),passed=sum(r['passed'] for r in results),
        failed=sum(not r['passed'] for r in results),all_scoped_checks_passed=bool(complete and len(results)==128 and all(r['passed'] for r in results) and all(m['passed'] for m in matrices) and not any(totals[k] for k in ('misses','false_positives','unknown'))),
        candidate_sha256=EXPECTED,candidate_unchanged=read(out/'candidate.json')==read(prep/'candidate.json'),
        counts=totals,independent=True,model_calls=0,scope=read(prep/'protocol.json')['scope'])
    dump(out/'outcome.json',outcome)
    lines=['# research132 冻结FIFO的新独立验收','',
        f'固定集合 `{EXPECTED}`；候选及规则先封存，之后抽取新种子并生成输入。',
        f'执行 {len(results)}/128 个场景，通过 {outcome["passed"]}，失败 {outcome["failed"]}；指定范围验收：{outcome["all_scoped_checks_passed"]}。',
        '4种Depth/Pipeline配置；已知人工边界故障的新独立输入，非新故障类别或上游历史FIFO缺陷。',
        '|Depth/Pipeline|义务|检出/曝光|漏报|误报|关键unknown|验收|','|---|---|---:|---:|---:|---:|---|']
    for m in matrices:lines.append(f'|{m["depth"]}/{m["pipeline"]}|{m["obligation"]}|{m["detections"]}/{m["actual_target_exposure"]}|{m["misses"]}|{m["false_positives"]}|{m["unknown"]}|{m["passed"]}|')
    lines+=['',f'合并有限证据：{outcome["counts"]}',
        f'物理成本：编译{cc["compile_calls"]}次，实验回放{cc["experiment_replays"]}次，编译冒烟{cc["compile_smoke_runs"]}次，总仿真{cc["total_simulator_executions"]}次；模型/形式化0。',
        '后续归因unknown保留，不能把首违例检出推广到整个故障轨迹或全局完整保护。无曝光不能算通过；合法控制与目标违例、输入握手及取消均由独立事务模型与原生记录核验。',
        '本批未用于提示、搜索、修改、筛选候选或规则。若以后依据结果修改，整批转为开发数据并另建独立测试。',
        '不能由本次冻结版本验收推导模型恢复成功率、搜索增量或防退化增量。',
        f'失败项：{[dict(case=r["case"],reasons=r["reasons"]) for r in results if not r["passed"]]}',
        '原始SVA/模型来源：research69；本批不修改或重新生成。原生采样、事务、波形及逐项触发在cases/case_*/内。']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('RESULT132',outcome,flush=True)


def run(prep,inputs,out):
    cases=check_inputs(prep,inputs);out.mkdir(parents=True,exist_ok=False)
    cand=read(prep/'candidate.json');dump(out/'candidate.json',cand)
    dump(out/'execution.json',dict(started_unix=time.time(),prepared=rel(prep),inputs=rel(inputs),
        protocol_seal=digest(prep/'sealed.json'),input_seal=digest(inputs/'sealed.json'),model_calls=0))
    results=[];groups=[];builds={};complete=False;error=None
    try:
        with base.extension.installed():
            for i,c in enumerate(cases):
                folder=out/'cases'/f'case_{i:03d}';dump(folder/'case.json',c);key=(c['depth'],c['pipeline'])
                if key not in builds:builds[key]=base.loop.runtime.build(cand,out/f'compiled_d{key[0]}p{key[1]}',*key)
                build=builds[key]
                if build['native']['compile_status']!='passed':raise RuntimeError(f'Native compile failed: {key}')
                a=base.loop.runtime.execute(build,folder/'correct',c['rows'],'correct');base.raw_audit(a,c,folder/'correct',cand)
                b=None
                if c['mode']!='correct':
                    b=base.loop.runtime.execute(build,folder/c['mode'],c['rows'],c['mode']);base.raw_audit(b,c,folder/c['mode'],cand)
                g=paired_ledger(a,b,c['id'])
                for row in g['ledger']:row['split']='independent_test'
                dump(folder/'ledger.json',g);groups.append(g)
                result=assess(c,a,b,g);dump(folder/'assessment.json',result);results.append(result)
                dump(out/'progress.json',results)
                print('INDEPENDENT132',i+1,c['id'],result['passed'],result['reasons'],flush=True)
        complete=True
    except Exception as exc:
        error=repr(exc);raise
    finally:
        check_inputs(prep,inputs)
        summarize(prep,inputs,out,results,groups,complete,error)


def audit(prep,inputs,run_dir,out):
    cases=check_inputs(prep,inputs);out.mkdir(parents=True,exist_ok=False)
    cand=read(prep/'candidate.json');checks=[];groups=[];results=[];n=0
    def check(name,yes):
        assert yes,name
        checks.append(name)
    check('exact_frozen_candidate',read(run_dir/'candidate.json')==cand)
    for folder in sorted(run_dir.glob('compiled_*')):
        check(folder.name+'/candidate',read(folder/'compiled.json')['candidate']==cand)
        tb=(folder/'tb.sv').read_text();cmd=read(folder/'compile.json')
        check(folder.name+'/native_RTL_assertions',cmd['exit_code']==0 and '--assert' in cmd['argv'] and any(Path(x).name=='axis_fifo.v' for x in cmd['argv']))
        for prop in cand['assertions']:check(folder.name+'/'+prop['id'],prop['property'] in tb)
    with base.extension.installed():
        for i,c in enumerate(cases):
            folder=run_dir/'cases'/f'case_{i:03d}';check(c['id']+'/input',read(folder/'case.json')==c)
            a=read(folder/'correct/replay.json');base.raw_audit(a,c,folder/'correct',cand);n+=1;b=None
            if c['mode']!='correct':
                b=read(folder/c['mode']/'replay.json');base.raw_audit(b,c,folder/c['mode'],cand);n+=1
            g=paired_ledger(a,b,c['id'])
            for row in g['ledger']:row['split']='independent_test'
            groups.append(g);check(c['id']+'/ledger',g==read(folder/'ledger.json'))
            result=assess(c,a,b,g);results.append(result)
            check(c['id']+'/decision',result==read(folder/'assessment.json'))
    check('combined_ledger',merge_ledgers(groups)==read(run_dir/'combined.json'))
    check('cost_unique_physical_commands',cost(run_dir)==read(run_dir/'cost.json'))
    outcome=read(run_dir/'outcome.json')
    check('outcome_counts',outcome['counts']==base.loop.counts(merge_ledgers(groups)))
    check('scheduled_coverage',len(results)==128 and n==240)
    check('decisions_not_rewritten',sum(r['passed'] for r in results)==outcome['passed'])
    dump(out/'audit.json',dict(passed=True,checks=len(checks),raw_records_reaudited=n,
        new_native_executions=0,model_calls=0,candidate_sha256=EXPECTED,
        outcome=outcome,scope='Audit correctness is separate from candidate acceptance.'))
    dump(out/'checks.json',checks)
    dump(out/'source_bindings.json',{rel(p):digest(p) for p in [Path(__file__),prep/'sealed.json',inputs/'sealed.json',run_dir/'outcome.json',run_dir/'combined.json',run_dir/'cost.json']})
    print('AUDIT132',len(checks),'checks',n,'raw records',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=('seal','generate','run','audit','verify'))
    for field in ('out','inventory','prepared','inputs','run'):ap.add_argument('--'+field,type=Path)
    a=ap.parse_args()
    for field in ('out','inventory','prepared','inputs','run'):
        if getattr(a,field):setattr(a,field,getattr(a,field).resolve())
    if a.action=='seal':seal(a.out,a.inventory)
    elif a.action=='generate':generate(a.prepared,a.out)
    elif a.action=='run':run(a.prepared,a.inputs,a.out)
    elif a.action=='audit':audit(a.prepared,a.inputs,a.run,a.out)
    else:verify(a.prepared);print('SEALED132 VERIFIED')
