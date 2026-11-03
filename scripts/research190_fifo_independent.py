"""Separate frozen independent validation of research189's shared acceptance.

No model transport, no candidate editing, no resampling. The original pilot
continues to have zero recovery and no independent tests under its own protocol.
This new protocol authorizes local validation of its directly accepted version.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import copy
import json
from pathlib import Path
import sys
import time

sys.dont_write_bytecode=True
import research188_drop_binding_audit as b

p,s,ROOT=b.p,b.s,b.ROOT
PREP=ROOT/'deliverables/research189_transport_prepare_20261102_r01'
RUN=ROOT/'deliverables/research189_fifo_pilot_run_20261102_r01'
REPORT=ROOT/'deliverables/research189_result_report_20261102_r01'
SCOPE='Original axis_fifo atomic oversize frame drop; Width8 KEEP0 FRAME_FIFO1 DROP_WHEN_FULL1 ID_ENABLE1; unique TID, Depth16/32, initial reset only.'


def bind(paths):return {s.rel(path):s.sha(path) for path in paths}


def scope_grade(m,expected,executions,legal_count,release_ok):
    exposed=set(m['public_targets'])|set(m['historical_targets'])
    missing=expected-exposed;extra=exposed-expected
    fn=exposed-set(m['detected_ids']);untriggered=exposed-set(m['triggered_ids'])
    native_failed=[f"{j['scene_id']}/{j['revision']}" for j in executions if j['result']['compile_status']!='passed' or j['result']['execution_status']!='completed']
    incomplete=len(executions)!=2*len(expected)
    passed=not(missing or extra or fn or untriggered or m['false_positives'] or m['critical_unknown'] or native_failed or incomplete or not release_ok or legal_count!=4*len(expected))
    return dict(passed=passed,expected_targets=len(expected),exposed_targets=len(exposed),missing_exposure_ids=sorted(missing),unexpected_exposure_ids=sorted(extra),
        false_negative_ids=sorted(fn),untriggered_target_ids=sorted(untriggered),false_positive_records=m['false_positives'],critical_unknown=m['critical_unknown'],
        native_failed=native_failed,native_population_incomplete=incomplete,legal_frame_observations=legal_count,expected_legal_frame_observations=4*len(expected),
        required_readiness_and_handshake_exposed=release_ok)


def audit_guard(out):
    reads=set()
    def hook(event,args):
        if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('no_network_or_model_calls')
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        path=Path(args[0]).resolve();name=path.as_posix().lower();mode=args[1]
        if '/.secrets/' in name or '/.env' in name:raise RuntimeError('no_credentials')
        if not path.is_relative_to(out) and any(x in name for x in ('/independent','/holdout','/tested_versions/','/terminal_frozen/')):raise RuntimeError('no_old_independent_results')
        writing=isinstance(mode,str) and any(c in mode for c in 'wax+')
        if writing and path.is_relative_to(p.q.D) and not path.is_relative_to(out):raise RuntimeError('old_artifact_immutable')
        if not writing and path.is_relative_to(p.q.D) and not path.is_relative_to(out) and '/tools/' not in name and path.is_file():reads.add(path)
    sys.addaudithook(hook)
    return reads


def execute(out):
    out.mkdir(parents=True,exist_ok=False);reads=audit_guard(out);checks=[]
    def ck(name,condition):
        checks.append(dict(name=name,passed=bool(condition)));s.dump(out/'checks.json',checks);assert condition,name
    def event(name,**values):
        with (out/'events.jsonl').open('a') as f:f.write(json.dumps(dict(event=name,utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),monotonic=time.monotonic(),**values))+'\n')
    for folder in (PREP,REPORT):
        b.verify_manifest(folder/'seal.json');b.verify_manifest(folder/'source_bindings.json');ck('prior seal '+folder.name,True)
    status=s.read(RUN/'outcome.json')
    ck('direct shared acceptance, no recovery',status['status']=='stop_both_accept_no_discrimination' and status['first']['ordinary'] and status['first']['history'] and not status['full_recovery_accepted'])
    candidate=s.read(RUN/'shared/model_call/candidate.json');p.validate(candidate)
    ck('real model expressions',p.adapt(s.read(RUN/'shared/model_call/model_edit.json'))==candidate)
    ck('both terminal sets equal candidate',s.read(RUN/'terminal_versions.json')==dict(O=candidate,H=candidate))
    ck('no prior independent run in189',not (RUN/'independent').exists())
    for name in ('reserved_semantic_pool.json','development_exclusions.json','probe_descriptors.json'):
        (out/name).write_bytes((PREP/name).read_bytes())
    pool=s.read(out/'reserved_semantic_pool.json');excluded=s.read(out/'development_exclusions.json');probes=s.read(out/'probe_descriptors.json')
    # Add actual research189 development streams, not merely the earlier list.
    development=s.read(RUN/'shared/native/executions.json')
    for j in development:
        excluded.append(dict(path=s.rel(Path(j['folder'])/'tb.sv'),sha256=s.sha(Path(j['folder'])/'tb.sv'),semantic_key=list(p.semantic_key(j['rows'],j['depth'])),origin='research189 actual development execution'))
    for d in probes:excluded.append(dict(path='research187_development_probe',semantic_key=d['semantic_key'],origin='predeclared executed capacity probe'))
    s.dump(out/'complete_development_exclusions.json',excluded)
    blocked={tuple(d['semantic_key']) for d in excluded};poolkeys={tuple(d['semantic_key']) for d in pool}
    ck('60 distinct reserved semantic keys',len(pool)==len(poolkeys)==60)
    ck('reserved/development disjoint',not(poolkeys&blocked))
    for depth in (16,32):
        for policy in p.q.POLICIES:ck(f'15 remaining {depth}/{policy}',sum((d['depth'],d['policy'])==(depth,policy) for d in pool)==15)
    # Pure acceptance checks ensure absence of exposure cannot count as passing.
    good=dict(public_targets=['x'],historical_targets=[],detected_ids=['x'],triggered_ids=['x'],false_positives=[],critical_unknown=[])
    jobs=[dict(scene_id='s',revision=rev,result=dict(compile_status='passed',execution_status='completed')) for rev in ('before','after')]
    ck('fully exposed fixture passes',scope_grade(good,{'x'},jobs,4,True)['passed'])
    for field,value in [('public_targets',[]),('detected_ids',[]),('triggered_ids',[]),('false_positives',[{'fixture':True}]),('critical_unknown',['fixture'])]:
        bad=copy.deepcopy(good);bad[field]=value;ck('reject '+field,not scope_grade(bad,{'x'},jobs,4,True)['passed'])
    ck('reject incomplete pair',not scope_grade(good,{'x'},jobs[:1],4,True)['passed'])
    ck('reject missing legal observations',not scope_grade(good,{'x'},jobs,3,True)['passed'])
    ck('reject readiness/handshake mismatch',not scope_grade(good,{'x'},jobs,4,False)['passed'])
    protocol=dict(purpose='research190_separate_independent_validation_of_research189_direct_acceptance',
        scope=SCOPE,old_pilot='research189 remains stopped_both_accept_no_discrimination; its recovery numerator/denominator and independent fields are unchanged.',
        candidate_policy='Keep all3 actual model properties byte-for-byte, including redundant legal property. No manual or model changes.',
        population=dict(total_scenarios=32,per_depth_readiness_stratum=8,depths=[16,32],policies=list(p.q.POLICIES),reserved_pool=60,selection_seed=18732),
        sequence='Freeze hashes and this protocol first; then call unchanged research187 selector, generate all32 stimuli, seal selection before executing any native job.',
        acceptance='Every scene: same legal inputs both revisions; original buggy oversize frame first presentation and later handshake; fixed revision no violation; required first-readiness class; native target trigger and failure; legal prefix/suffix preserved in both revisions; no FP, FN, execution failure or critical unknown. No-exposure is not a pass or a SVA false negative.',
        independent_unit='Distinct accepted frame length, release-gap beat index and depth/readiness stratum; ignore payload/ID/seed/absolute cycle. One historical root defect, not32 independent bugs.',
        budget=dict(model_calls=0,formal_calls=0,max_compile_attempts=64,max_execution_attempts=64,workers=2,total_wall_seconds=3600,compile_or_run_timeout_seconds=240,tool_version_timeout_seconds=15,retries=0),
        stop='Fixed64 jobs, keep all outcomes. No early stop on failure/no-exposure, no replacement. On global deadline no further jobs; unfinished jobs/scenes unknown. No retries, no budget extension.',
        isolation='Do not send tests to models, use them to select a candidate, or change acceptance rules. If later used for improvement, promote the entire batch to development and obtain new tests.',
        limits='Initial reset only; no dynamic reset-cancellation, no sparseKEEP or ID reuse, no global/five-obligation FIFO claim, no formal proof or mechanism-increment claim.')
    s.dump(out/'protocol.json',protocol)
    frozen=out/'frozen';frozen.mkdir()
    (frozen/'assertions.json').write_bytes((RUN/'shared/model_call/candidate.json').read_bytes())
    (frozen/'candidate.sva').write_bytes((RUN/'shared/model_call/candidate.sva').read_bytes())
    paths=[Path(__file__),Path(p.__file__),Path(b.__file__),Path(p.q.__file__),Path(s.__file__),Path(s.n.__file__),
        ROOT/'scripts/research136_prospective_history.py',ROOT/'scripts/research167_adapter_controller.py',
        PREP/'seal.json',REPORT/'seal.json',RUN/'outcome.json',RUN/'terminal_versions.json',
        RUN/'shared/model_call/model_edit.json',RUN/'shared/model_call/result.json',RUN/'shared/model_call/response.stream.raw',
        RUN/'shared/native/measurement.json',RUN/'shared/native/executions.json',
        out/'protocol.json',out/'complete_development_exclusions.json',out/'reserved_semantic_pool.json']
    paths += [p.q.P/'frame_fifo_drop'/rev/'axis_fifo.v' for rev in ('before','after')]
    binary,env=s.n.native_environment()
    version,version_text=s.n.command([binary,'--version'],frozen,'tool_version',15,env)
    ck('native tool available',version['exit_code']==0)
    s.dump(frozen/'tool_config.json',dict(binary=binary,version=version_text.strip(),binary_sha256=s.sha(Path(binary)),
        flags=['--binary','--timing','--assert','--trace','-j','2','-Wno-fatal'],workers=2,formal_proof=False))
    paths += [frozen/'tool_version.json',frozen/'tool_version.log',frozen/'tool_config.json',Path(binary)]
    bindings=bind(paths)
    s.dump(frozen/'freeze.json',dict(assertions_sha256=s.sha(frozen/'assertions.json'),sva_sha256=s.sha(frozen/'candidate.sva'),
        bindings=bindings,origin='real_model_directly_accepted_separate_independent_protocol',model_calls=0,scope=SCOPE))
    event('frozen_before_selection',assertions_sha256=s.sha(frozen/'assertions.json'),protocol_sha256=s.sha(out/'protocol.json'))
    # Unmodified predeclared selector. No independently generated rows exist yet.
    selected=p.select_unseen(pool,frozen/'freeze.json',out/'selection')
    ck('selected32 unique unseen',len(selected)==len({tuple(d['semantic_key']) for d in selected})==32 and not({tuple(d['semantic_key']) for d in selected}&blocked))
    scene_specs=[];plans=[]
    for i,d in enumerate(selected):
        sid=f'test{i}/{d["depth"]}/{d["policy"]}';rows=p.scene(d)
        ck('generated semantic identity '+str(i),tuple(d['semantic_key'])==p.semantic_key(rows,d['depth']))
        folder=out/'selection'/f'scene{i}';s.dump(folder/'descriptor.json',d);s.dump(folder/'inputs.json',rows)
        source=p.bench(candidate,d['depth'],d['policy'],rows);(folder/'tb.sv').write_text(source)
        scene_specs.append(dict(scene_id=sid,descriptor=d,inputs=s.rel(folder/'inputs.json'),tb=s.rel(folder/'tb.sv')))
        for rev in ('before','after'):
            plans.append(dict(scene_id=sid,depth=d['depth'],policy=d['policy'],revision=rev,rows=rows,tb=str(folder/'tb.sv'),folder=str(out/'native'/sid/rev)))
    s.dump(out/'selection/scenes.json',scene_specs)
    s.dump(out/'selection/native_plan.json',plans)
    s.dump(out/'selection/seal.json',bind([f for f in (out/'selection').rglob('*') if f.is_file()]))
    event('selection_sealed_before_native',scenarios=32,jobs=64)
    print('FROZEN190 selected32, native64, workers2, model0; no replacements',flush=True)
    start=time.monotonic();deadline=start+3600;completed=[];original=s.n.command
    def bounded(argv,folder,name,timeout=240,env=None):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('independent_wall_budget_exhausted')
        return original(argv,folder,name,min(timeout,remaining),env)
    def worker(plan):
        job=copy.deepcopy(plan);folder=Path(job['folder'])
        try:
            if time.monotonic()>=deadline:raise TimeoutError('global_deadline')
            job['result']=s.n.run_native(Path(job.pop('tb')).read_text(),folder,
                extra_sources=[p.q.P/'frame_fifo_drop'/job['revision']/'axis_fifo.v'],timeout=240)
        except Exception as exc:
            job['result']=dict(compile_status='unknown',execution_status='not_completed',native_simulation_calls=0,failures=[],triggers=[],
                error_type=type(exc).__name__,tool_support_status='unknown',property_status='unknown',trigger_status='unknown')
            s.dump(folder/'incomplete.json',job['result'])
        return job
    b.verify_manifest(out/'selection/seal.json')
    try:
        s.n.command=bounded
        with ThreadPoolExecutor(max_workers=2) as executor:
            remaining=iter(plans);active={}
            for _ in range(2):
                plan=next(remaining);active[executor.submit(worker,plan)]=plan
            while active:
                done,_=wait(active,timeout=20,return_when=FIRST_COMPLETED)
                for future in done:
                    active.pop(future);job=future.result();completed.append(job)
                    s.dump(out/'executions.partial.json',completed)
                    print('NATIVE190',len(completed),job['scene_id'],job['revision'],job['result']['compile_status'],job['result']['execution_status'],flush=True)
                    if time.monotonic()<deadline:
                        nxt=next(remaining,None)
                        if nxt is not None:active[executor.submit(worker,nxt)]=nxt
    finally:s.n.command=original
    actual={(j['scene_id'],j['revision']):j for j in completed}
    jobs=[]
    for plan in plans:
        job=actual.get((plan['scene_id'],plan['revision']))
        if job is None:
            job=copy.deepcopy(plan);job['result']=dict(compile_status='not_run',execution_status='not_run',native_simulation_calls=0,failures=[],triggers=[],tool_support_status='unknown',property_status='unknown',trigger_status='unknown',reason='budget_stopped_no_replacement')
        jobs.append(job)
    s.dump(out/'executions.json',jobs)
    event('native_batch_terminal',scheduled=len(completed),planned=64,wall_seconds=time.monotonic()-start)
    # Keep unknown/incomplete jobs measurable without inventing a native result.
    measurement=p.measure(candidate,jobs)
    s.dump(out/'measurement.json',measurement)
    scene_results=[];traces=[]
    for spec in scene_specs:
        sid=spec['scene_id'];d=spec['descriptor'];pair=[j for j in jobs if j['scene_id']==sid];m=p.measure(candidate,pair)
        expected={sid+'/frame2'};legal=0;release_ok=True
        for rev in ('before','after'):
            ref=m['reference'].get(sid+'/'+rev)
            if not ref:release_ok=False;continue
            legal+=sum(not f['oversize'] and f['completed'] for f in ref['frames'].values())
            if rev=='before':
                if len(ref['events'])!=1:release_ok=False
                for ev in ref['events']:
                    ready=ev['first']['ready'];cycles=[r['cycle'] for r in ev['outputs']]
                    okay=bool(cycles) and ready==int(d['policy']=='ready_first') and ((cycles[0]==ev['first']['cycle']) if ready else (cycles[0]>ev['first']['cycle']))
                    release_ok=release_ok and okay
                    traces.append(dict(scene=sid,frame=ev['frame'],accepted_beats=len(ev['accepted']),first=ev['first'],first_handshake=cycles[0] if cycles else None,leaked_beats=len(ev['outputs']),
                        accepted_cycles=[r['cycle'] for r in ev['accepted']],handshake_cycles=cycles,assertion_evidence=m['obligation_assertion_evidence']))
        grade=scope_grade(m,expected,pair,legal,release_ok)
        grade.update(scene_id=sid,descriptor=d,detected_ids=m['detected_ids'],triggered_ids=m['triggered_ids'])
        scene_results.append(grade)
    s.dump(out/'scene_results.json',scene_results);s.dump(out/'transaction_traces.json',traces)
    # Recheck all bindings after execution; changing the version invalidates validation.
    for name,sha in bindings.items():ck('frozen binding unchanged '+name,s.sha(ROOT/name)==sha)
    ck('assertion collection unchanged',s.sha(frozen/'assertions.json')==s.sha(RUN/'shared/model_call/candidate.json'))
    b.verify_manifest(out/'selection/seal.json');ck('selection unchanged no resampling',True)
    b.verify_manifest(REPORT/'source_bindings.json');ck('research189 old run immutable',True)
    summary=dict(scope=SCOPE,total_scenarios=32,passed_scenarios=sum(v['passed'] for v in scene_results),
        target_exposure=sum(v['exposed_targets'] for v in scene_results),target_misses=sum(len(v['false_negative_ids']) for v in scene_results),
        missing_exposure=sum(len(v['missing_exposure_ids']) for v in scene_results),untriggered_exposed_targets=sum(len(v['untriggered_target_ids']) for v in scene_results),
        false_positive_records=sum(len(v['false_positive_records']) for v in scene_results),critical_unknown_records=sum(len(v['critical_unknown']) for v in scene_results),
        legal_frame_observations=sum(v['legal_frame_observations'] for v in scene_results),planned_legal_frame_observations=128,
        native_jobs_completed=sum(j['result']['execution_status']=='completed' for j in jobs),native_jobs_planned=64,
        whole_scope_pass=all(v['passed'] for v in scene_results),new_model_versions=0,model_calls=0,formal_calls=0,
        conditional_recovery=dict(numerator=0,denominator=0,estimate=None),mechanism_increment_claim=False,H_R_equivalent=True,
        research189_original_independent_field_unchanged=True,tasks2_3_expanded=False)
    s.dump(out/'summary.json',summary)
    compiles=list((out/'native').rglob('compile.json'));execs=list((out/'native').rglob('execute.json'))
    cost=dict(model_calls=0,tokens=0,formal_calls=0,native_compile_attempts=len(compiles),native_executions=len(execs),
        compile_seconds_sum=sum(s.read(f)['wall_seconds'] for f in compiles),execution_seconds_sum=sum(s.read(f)['wall_seconds'] for f in execs),
        batch_wall_seconds=time.monotonic()-start,workers=2,tool_version_queries=1+len(list((out/'native').rglob('tool_version.json'))))
    s.dump(out/'cost.json',cost)
    strata=[]
    for depth in (16,32):
        for policy in p.q.POLICIES:
            group=[v for v in scene_results if v['descriptor']['depth']==depth and v['descriptor']['policy']==policy]
            strata.append(dict(depth=depth,policy=policy,total=len(group),passed=sum(v['passed'] for v in group),exposed=sum(v['exposed_targets'] for v in group),
                misses=sum(len(v['false_negative_ids']) for v in group),missing_exposure=sum(len(v['missing_exposure_ids']) for v in group),unknown=sum(len(v['critical_unknown']) for v in group)))
    s.dump(out/'strata.json',strata)
    lines=['# research190：research189直接接受版本的独立验收','',
        '**预定独立范围全部通过。**' if summary['whole_scope_pass'] else '**预定独立范围未全部通过；失败/未曝光/unknown保留，不补抽。**','',
        f"冻结候选SHA256：`{s.sha(frozen/'assertions.json')}`。研究189旧协议、原始决定及独立字段均未修改。此处是用户另行授权的本地独立验收。",'',
        '|深度|首拍条件|场景通过|目标曝光|目标漏报|未曝光|关键unknown|','|---|---|---|---|---|---|---|']
    for v in strata:lines.append(f"|{v['depth']}|{v['policy']}|{v['passed']}/{v['total']}|{v['exposed']}/{v['total']}|{v['misses']}|{v['missing_exposure']}|{v['unknown']}|")
    lines+=['',f"总计场景{summary['passed_scenarios']}/32通过，实际目标曝光{summary['target_exposure']}/32；合法帧观察{summary['legal_frame_observations']}/128；误报{summary['false_positive_records']}、曝光目标漏报{summary['target_misses']}、曝光但未触发{summary['untriggered_exposed_targets']}、未曝光{summary['missing_exposure']}、关键unknown记录{summary['critical_unknown_records']}。原生执行完成{summary['native_jobs_completed']}/64。",'',
        '保持真实模型生成的3条性质原样，包含冗余ready_first_legal，不删除或修正。输入/输出事务判断来自独立原始端口参考，不以SVA通过充当RTL正确依据。每个buggy超长帧只计一个目标，多个泄漏拍不是多个缺陷。', '',
        '冻结后使用原先固定seed18732，从60个保留语义组合分层选32个，每Depth/首拍条件8个。排除了全部列明开发场景、4个容量探针及research189实际输入。数据、ID及绝对周期变体不增加语义新颖性。未用旧独立结果选择候选或规则。', '',
        '范围仅原始同步axis_fifo同一丢帧历史修复、Depth16/32、KEEP关闭、唯一TID、初始化复位、超长帧原子丢弃及合法前后帧保持。背压类要求首次呈现ready=0并后来实际握手；就绪类要求首呈现同周期握手。并不验证动态复位取消、全部FIFO义务、整系统正确性或形式化证明。', '',
        f"实际成本：模型0、形式化0；原生编译{cost['native_compile_attempts']}次、执行{cost['native_executions']}次；两路并发累计编译{cost['compile_seconds_sum']:.3f}秒，执行{cost['execution_seconds_sum']:.3f}秒，批次墙钟{cost['batch_wall_seconds']:.3f}秒。各命令/版本/日志/波形在native/。",'',
        '本批没有反馈给模型或修改断言。若以后据此优化候选或规则，整批转为开发数据并重新准备独立测试。手写对照未作为本批候选。', '',
        '任务1：该接受版本的独立验收单独记录，仍不是额外拒绝→恢复的机制证据；真实条件恢复0/0不可估计，H/R等价。任务2/3本轮未扩展，576次搜索负结果保持。', '',
        '完整复现（新目录；64个本地原生作业，模型0）：','```powershell','wsl -- python3 scripts/research190_fifo_independent.py --out deliverables/research190_reproduce','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    s.dump(out/'read_audit.json',dict(source_reads=sorted(s.rel(v) for v in reads),old_independent_results_read=False,network_calls=0))
    s.dump(out/'source_bindings.json',bindings)
    s.dump(out/'result_seal.json',bind([f for f in out.rglob('*') if f.is_file() and 'obj_dir' not in f.parts and f.name!='result_seal.json']))
    print('RESULT190',json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    execute(parser.parse_args().out.resolve())
