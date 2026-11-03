"""Finalize local FIFO controller bindings after research187 qualification.

No model or independent tests. The transport remains deliberately absent.
This adds proposal-to-measurement binding and complete freeze prerequisites;
research187 artifacts are read-only and its local native probes are reused.
"""
import argparse
import copy
import json
from pathlib import Path

import research187_drop_controller as p

s=p.s
ROOT=p.ROOT
DEFAULT=ROOT/'deliverables/research187_drop_controller_prepare_20261102_r02'


def bound_measure(candidate,jobs,protected=()):
    result=p.measure(candidate,jobs,protected)
    result['candidate_sha256']=p.digest(candidate)
    result['native_bindings']={s.rel(Path(j['folder'])/'result.json'):s.sha(Path(j['folder'])/'result.json') for j in jobs}
    return result


class Controller(p.Controller):
    def response(self,status,value):
        candidate=super().response(status,value)
        self.pending_hash=p.digest(candidate) if candidate is not None else None
        return candidate
    def decision(self,candidate,measurement):
        if p.digest(candidate)!=self.pending_hash or measurement.get('candidate_sha256')!=self.pending_hash:
            self.state='stop_binding_mismatch';raise ValueError('proposal_measurement_mismatch')
        if not measurement.get('native_bindings'):
            self.state='stop_binding_mismatch';raise ValueError('missing_native_sources')
        return super().decision(candidate,measurement)
    def freeze(self,out,bindings,origin):
        # Every bound file must already exist; unknown/missing provenance stops.
        if self.state!='recovered':raise ValueError('no_complete_recovery')
        required={'protocol','RTL','development_exclusions','tool_versions','model_records','native_results','configuration'}
        if set(bindings)!=required or origin not in ('real_model','local_branch_fixture'):raise ValueError('freeze_provenance')
        for entries in bindings.values():
            if not entries:raise ValueError('empty_freeze_binding')
            for name,expected in entries.items():
                path=ROOT/name
                if not path.is_file() or s.sha(path)!=expected:raise ValueError('freeze_hash_mismatch')
        out.mkdir(parents=True,exist_ok=False)
        s.dump(out/'assertions.json',self.retained)
        s.dump(out/'freeze.json',dict(assertions_sha256=s.sha(out/'assertions.json'),bindings=bindings,origin=origin,
            scope='Original axis_fifo atomic oversize drop, first presentation, unique TID, KEEP0, initial reset only'))
        if origin=='real_model':self.budget.reserve_native('independent',recovered=True)
        self.state='frozen' if origin=='real_model' else 'local_fixture_frozen'
        return out/'freeze.json'
    def freeze_for_independent(self,out):
        raise ValueError('use_complete_provenance_freeze')


def select_unseen(pool,freeze,out):
    meta=s.read(freeze)
    if meta.get('origin')!='real_model':raise ValueError('handwritten_fixture_cannot_start_independent_test')
    for entries in meta['bindings'].values():
        for name,expected in entries.items():
            if s.sha(ROOT/name)!=expected:raise ValueError('frozen_binding_changed')
    return p.select_unseen(pool,freeze,out)


def evaluate(candidate,folder,protected,descriptors=None):
    """Same executable interface for shared proposal/recovery and future tests.

    Development is the frozen six scene pairs. Independent descriptors must be
    selected AFTER freeze by the caller; never generated inside this function.
    Every failure is retained, with no rerun/replacement.
    """
    p.validate(candidate);folder.mkdir(parents=True,exist_ok=False)
    scenes=[]
    if descriptors is None:
        for depth in p.q.DEPTHS:
            for policy in p.q.POLICIES:
                scenes.append((f'{depth}/{policy}',depth,policy,p.q.rows(depth,policy)))
    else:
        if len(descriptors)!=32 or len({tuple(d['semantic_key']) for d in descriptors})!=32:raise ValueError('independent_population')
        scenes=[(f'test{i}/{d["depth"]}/{d["policy"]}',d['depth'],d['policy'],p.scene(d)) for i,d in enumerate(descriptors)]
    jobs=[]
    for sid,depth,policy,rows in scenes:
        for rev in ('before','after'):
            run=folder/sid/rev
            result=s.n.run_native(p.bench(candidate,depth,policy,rows),run,extra_sources=[p.q.P/'frame_fifo_drop'/rev/'axis_fifo.v'])
            jobs.append(dict(scene_id=sid,depth=depth,policy=policy,rows=rows,revision=rev,folder=str(run),result=result))
            s.dump(folder/'executions.json',jobs)
    result=bound_measure(candidate,jobs,protected)
    s.dump(folder/'measurement.json',result)
    return result


def verify_manifest(manifest):
    for name,expected in s.read(manifest).items():
        if s.sha(ROOT/name)!=expected:raise ValueError('seal_mismatch:'+name)


def audit(prepared,out):
    out.mkdir(parents=True,exist_ok=False)
    # Enforce read-only development inputs, network prohibition and independent isolation.
    def guard(event,args):
        if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('no_network')
        if event!='open' or not isinstance(args[0],(str,bytes)):return
        path=Path(args[0]).resolve();name=path.as_posix().lower();mode=args[1]
        if any(x in name for x in ('/independent','/holdout','/.secrets/','/.env','/terminal_frozen/','/tested_versions/')):raise RuntimeError('excluded_material')
        write=isinstance(mode,str) and any(x in mode for x in 'wax+')
        if write and path.is_relative_to(p.q.D) and not path.is_relative_to(out):raise RuntimeError('immutable_archive')
    p.sys.addaudithook(guard)
    checks=[]
    def ck(name,ok):
        checks.append(dict(name=name,passed=bool(ok)));s.dump(out/'checks.json',checks);assert ok,name
    def rejects(name,fn):
        try:fn()
        except (ValueError,RuntimeError,AssertionError):ck(name,True);return
        ck(name,False)
    verify_manifest(prepared/'seal.json');ck('187 seal verified',True)
    ck('187 locally qualified',s.read(prepared/'decision.json')['pilot_sealed'])
    ck('all187 checks',all(c['passed'] for c in s.read(prepared/'checks.json')))
    ctl=p.controls();req=s.read(prepared/'request.preview.json');protected=s.read(prepared/'pilot_protocol.json')['protected_ids']
    jobs=[]
    for d,policy,rev in p.itertools.product(p.q.DEPTHS,p.q.POLICIES,('before','after')):
        f=p.ARCHIVE/'native'/str(d)/policy/rev
        jobs.append(dict(scene_id=f'{d}/{policy}',depth=d,policy=policy,revision=rev,folder=str(f),rows=p.q.rows(d,policy),result=s.read(f/'result.json')))
    measured={name:bound_measure(c,jobs,protected) for name,c in ctl.items()}
    for name in ctl:
        archived=s.read(prepared/'archived_control_results.json')[name]
        ck('same O/H '+name,(measured[name]['ordinary_accept'],measured[name]['historical_accept'])==(archived['ordinary_accept'],archived['historical_accept']))
    def at_first(name):
        c=Controller(ctl['partial_stalled'],protected);c.reserve(req)
        prop=c.response('response_received',dict(assertions=ctl[name],reason='HANDWRITTEN LOCAL BRANCH FIXTURE'))
        return c,prop
    c,prop=at_first('replacement_ready');rejects('measurement from different candidate',lambda:c.decision(prop,measured['union']))
    ck('mismatch terminal',c.state=='stop_binding_mismatch')
    c,prop=at_first('replacement_ready');rejects('different response predicate',lambda:c.decision(ctl['union'],measured['union']))
    c,prop=at_first('replacement_ready');m=copy.deepcopy(measured['replacement_ready']);m.pop('native_bindings');rejects('missing native provenance',lambda:c.decision(prop,m))
    for name in ('union','overbroad','vacuous'):
        c,prop=at_first(name);c.decision(prop,measured[name]);rejects('terminal no second '+name,lambda:c.reserve(req));rejects('no freeze '+name,lambda:c.freeze_for_independent(out/'not_created'))
    c,prop=at_first('replacement_ready');ck('fixture opportunity',c.decision(prop,measured['replacement_ready'])=='history_once' and c.retained==ctl['partial_stalled'])
    recovery=p.feedback(req,prop,measured['replacement_ready'])
    c.reserve(recovery);proposal=c.response('response_received',dict(assertions=ctl['union'],reason='HANDWRITTEN LOCAL BRANCH FIXTURE'))
    ck('fixture recovery control',c.decision(proposal,measured['union'])=='recovered')
    rejects('incomplete freeze metadata',lambda:c.freeze(out/'bad_freeze',{},'local_branch_fixture'))
    def binding(*paths):return {s.rel(path):s.sha(path) for path in paths}
    versions=Path(jobs[0]['folder'])/'tool_version.json'
    # A local fixture binds its control file in place of model records and is
    # explicitly barred from independent selection. This never asserts a model run.
    bindings=dict(protocol=binding(prepared/'pilot_protocol.json'),RTL=binding(*(p.q.P/'frame_fifo_drop'/rev/'axis_fifo.v' for rev in ('before','after'))),
        development_exclusions=binding(prepared/'development_exclusions.json',prepared/'probe_descriptors.json'),
        tool_versions=binding(versions),model_records=binding(prepared/'local_controls.json'),
        native_results=measured['union']['native_bindings'],configuration=binding(prepared/'request.preview.json',prepared/'reserved_semantic_pool.json'))
    bad=copy.deepcopy(bindings);bad['configuration'][next(iter(bad['configuration']))]='0'*64
    rejects('incorrect freeze hash',lambda:c.freeze(out/'bad_hash_freeze',bad,'local_branch_fixture'))
    frozen=c.freeze(out/'local_fixture_freeze',bindings,'local_branch_fixture')
    ck('fixture freeze recorded no independent stage',c.state=='local_fixture_frozen' and c.budget.native==['shared','recovery'])
    rejects('handwritten recovery cannot start independent tests',lambda:select_unseen([],frozen,out/'never_selected'))
    ck('still no independent selection',not(out/'never_selected').exists())
    # All expression-preserving wrappers have identical emitted SVA to the
    # successfully executed combined control bench (no post-hoc repair).
    native=s.read(prepared/'probe_executions.json')
    flat=[v[0] for name,v in ctl.items() if name!='union']
    for j in native:
        src=Path(j['folder'])/'tb.sv'
        ck('native exact renderer '+j['scene_id']+'/'+j['revision'],src.read_text()==p.bench(flat,j['depth'],j['policy'],j['rows']))
        ck('probe completed '+j['scene_id']+'/'+j['revision'],j['result']['compile_status']=='passed' and j['result']['execution_status']=='completed')
    # Byte-size upper bound for failure feedback: the request reservoir was
    # checked on an actual loss fixture. Future oversized feedback stops safely.
    ck('exact two reservations',len(c.budget.calls)==2)
    ck('conservative reservation within cap',sum(x['utf8_reservation'] for x in c.budget.calls)<=120000)
    rejects('no repeat after two',lambda:c.reserve(req))
    for name in ('request.preview.json','reserved_semantic_pool.json','development_exclusions.json','probe_descriptors.json'):
        s.dump(out/name,s.read(prepared/name))
    protocol=s.read(prepared/'pilot_protocol.json')
    protocol.update(purpose='research188_original_sync_fifo_drop_bound_history_pilot',
        source_protocol=s.rel(prepared/'pilot_protocol.json'),binding='Candidate digest must match decoded model response AND native measurement. Freeze requires protocol, RTL, development exclusions, tools, model records, native results and configuration hashes.',
        probe_exclusion='All four research187 native capacity probes are development. 60 remaining descriptors have never been instantiated or run by this preparation.',
        invocation='Local preparation only. No remote dispatch in these CLIs. A new purpose-bound authorization and transport adapter must be verified before executing the sealed request, without editing it or changing branching/budget.')
    s.dump(out/'pilot_protocol.json',protocol)
    s.dump(out/'decision.json',dict(local_qualification=True,protocol_sealed=True,model_calls=0,new_model_versions=0,real_extra_rejections=0,real_recoveries=0,new_independent_tests=0,
        conditional_recovery=dict(numerator=0,denominator=0,estimate=None),tasks2_3_expanded=False,
        action='LOCAL_PREPARATION_COMPLETE_NO_MODEL_AUTHORIZATION',limitations='H/R equivalent; no new mechanism evidence; native local controls and frozen fixture cannot substitute model recovery.'))
    s.dump(out/'budget_fixture_ledger.json',dict(origin='handwritten local state-machine checks',actual_model_calls=0,simulated_reservations=c.budget.calls,native_stages_simulated=c.budget.native))
    prior=s.read(prepared/'cost.json');s.dump(out/'cost.json',dict(new_native_compile_attempts=0,new_native_executions=0,reused_archive_jobs=12,reused_probe_jobs=8,total_current_task=prior,model_calls=0,formal_calls=0))
    sources=[Path(__file__),Path(p.__file__),prepared/'seal.json',p.LOCK,ROOT/'scripts/research136_prospective_history.py',ROOT/'scripts/research167_adapter_controller.py']
    s.dump(out/'source_bindings.json',binding(*sources))
    summary=['# research187/188 本地控制器与未用语义余量最终结论','',
        '**任务1本地集成与资格核查完成，新的有界协议已封存；没有模型调用。任务2、3未扩展。**','',
        f'research187通过{len(s.read(prepared/"checks.json"))}项接口/分支检查；本次追加{len(checks)}项绑定/冻结/原生对应复核。12份既有原生记录重判；本轮8次新增原生编译及执行全部完成。没有重跑旧FIFO独立验收。',
        '', '部分候选保留2个历史目标配置点、遗漏2个公共目标配置点。替换手写对照普通接受但历史拒绝；联合手写对照两者接受。新增4个开发探针同样满足前后RTL见证及相同区分关系，联合对照无误报、无关键unknown。它们均属于同一真实历史缺陷，不是多个独立Bug。',
        '', '固定64个语义描述符，排除4个预定开发探针后，余60个未实例化组合，每Depth16/32×首拍就绪/背压类15个；未来冻结后每类选择8个，共32。去重依据实际帧长度和排空间隔所在拍，忽略数据、ID、seed及绝对周期。容量核查支持封存，但不保证未来每个组合曝光或通过；无曝光、失败、unknown保留，不补抽。',
        '', '新增候选—原生测量哈希绑定；同一义务允许多条性质。预算沿用最多2次、首轮无区分即停、传输失败即停；仅普通接受/历史拒绝/确认退化/无关键unknown才恢复一次。拒绝保留初始部分集合。冻结必须绑定RTL、工具、开发排除、模型和原生证据；手写夹具无法启动独立测试。',
        '', 'r01因恢复请求超出大小预检失败，原记录保留；r02只精简重复诊断字段，保留采样首呈现、输入输出端点及计数，完整字节记录留存本地，未提高预算或改变接受规则。r01未执行原生探针或模型。最终请求和协议以本目录为准，旧失败未追改。',
        '', '本轮真实模型新版本0、真实额外拒绝0、条件恢复0/0不可估计、新独立验收0。H/R等价，576次搜索负结果保持。结论只涵盖此原始同步FIFO的首拍原子丢帧义务、唯一TID、KEEP关闭和初始化复位，不是全局FIFO完整保护。',
        '', '下一步若继续：针对本封存协议取得新的最多2次授权，再绑定既有远程传输器；不改变请求或扩大分支。当前CLI仅本地运行，不含远程调度。双方接受或无区分机会按协议停止；只有完整恢复后才能运行32个新独立场景。',
        '', '本地复核（不会调用模型，不新增原生执行）：','```powershell','wsl -- python3 scripts/research188_drop_binding_audit.py --prepared deliverables/research187_drop_controller_prepare_20261102_r02 --out deliverables/research188_reaudit','```']
    (out/'SUMMARY.md').write_text('\n'.join(summary)+'\n',encoding='utf-8')
    s.dump(out/'seal.json',{s.rel(path):s.sha(path) for path in sorted(out.rglob('*')) if path.is_file()})
    verify_manifest(out/'seal.json');print('SEALED188',len(checks),'local checks, model0 independent0',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--prepared',type=Path,default=DEFAULT);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();audit(args.prepared.resolve(),args.out.resolve())
