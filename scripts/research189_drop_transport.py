"""Bind sealed research188 to the existing transport; prepare is offline.

run alone can dispatch, after purpose/seal/output-bound authorization validation.
Local transport fixtures are named and counted separately, never model results.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
import time
import urllib.error
from unittest.mock import patch

import research188_drop_binding_audit as b
import research69_deadline_transport as t

p,s,ROOT=b.p,b.s,b.ROOT
SOURCE=ROOT/'deliverables/research188_drop_binding_prepare_20261102_r01'
PURPOSE='research189_transport_bound_research188_fifo_pilot'
CONFIG=dict(remote_url=p.ENDPOINT,remote_model='deepseek/deepseek-v3-0324',max_model_calls=2,
            max_tokens=120000,max_wall_seconds=1200,call_timeout=300,
            options=dict(seed=16507,temperature=0.2,num_predict=1024))


class Model(t.RemoteModel):
    def __init__(self,out,config):
        super().__init__(out,config)
        # Correct old init-only metadata; inherited call() already caps at300.
        meta=s.read(self.out/'remote_transport_config.json')
        meta['timeout_seconds']=min(300,config['call_timeout'])
        meta['binding']='Exact frozen payload; no stream/format/default prompt injection.'
        s.dump(self.out/'remote_transport_config.json',meta)
        self.pending_request=None
    def _payload(self,*args):
        if self.pending_request is None:raise ValueError('missing_bound_payload')
        return copy.deepcopy(self.pending_request)
    def save_decoded_output(self,folder,value,current,secret):
        candidate=p.adapt(value)
        s.dump(folder/'candidate.json',candidate)
        # Only syntactic wrapper: preserve each expression exactly.
        lines=[f"{a['label']}: assert property (@(posedge clk) disable iff(rst) ({a['antecedent']}) |-> ({a['consequent']}));" for a in candidate]
        (folder/'candidate.sva').write_text('\n'.join(lines)+'\n')
        return candidate,'validated_without_predicate_repair'


def validate_grant(grant,prep,out):
    expected=dict(authorized=True,purpose=PURPOSE,authorized_calls=2,endpoint=p.ENDPOINT,
        model=CONFIG['remote_model'],prepared_sha256=s.sha(prep/'seal.json'),run_output=s.rel(out))
    if any(grant.get(k)!=v for k,v in expected.items()) or type(grant.get('authorized_calls')) is not int:raise ValueError('grant_scope_mismatch')
    if out.exists():raise ValueError('no_resume_or_retry')


def verify(prep):
    b.verify_manifest(prep/'seal.json')
    b.verify_manifest(prep/'source_bindings.json')
    b.verify_manifest(SOURCE/'seal.json')
    b.verify_manifest(SOURCE/'source_bindings.json')
    b.verify_manifest(b.DEFAULT/'seal.json')
    b.verify_manifest(b.DEFAULT/'source_bindings.json')
    if s.read(prep/'request.preview.json')!=s.read(SOURCE/'request.preview.json'):raise ValueError('sealed_request_changed')
    if s.read(prep/'model_config.json')!=CONFIG:raise ValueError('configuration_changed')


class RealBackend:
    mode='real_model'
    def __init__(self,out):self.model=Model(out/'transport',CONFIG)
    def generate(self,req,folder,current,clock):
        self.model.pending_request=copy.deepcopy(req)
        self.model.started=clock.start  # one shared1200s clock, never restart on recovery
        return self.model.call(folder,current,p.OB,{},'prospective_history')
    def native(self,candidate,folder,protected,clock,descriptors=None):
        # Enforce the existing1200s cap also inside compiler/runtime commands.
        original=s.n.command
        def bounded(argv,work,name,timeout=240,env=None):
            remaining=1200-(clock.clock()-clock.start)
            if remaining<=0:raise TimeoutError('controller_wall_budget_exhausted')
            return original(argv,work,name,min(timeout,remaining),env)
        with patch.object(s.n,'command',bounded):
            clock.time_check()
            return b.evaluate(candidate,folder,protected,descriptors)
    def independent(self,prep,out,candidate,controller):
        recovered=out/'recovery/native';models=[x for x in out.rglob('*') if x.is_file() and 'model_call' in x.parts]
        def binds(paths):return {s.rel(v):s.sha(v) for v in paths}
        bindings=dict(protocol=binds([prep/'binding_protocol.json',SOURCE/'pilot_protocol.json',prep/'seal.json']),
            RTL=binds([p.q.P/'frame_fifo_drop'/r/'axis_fifo.v' for r in ('before','after')]),
            development_exclusions=binds([prep/'development_exclusions.json',prep/'probe_descriptors.json']),
            tool_versions=binds(list(recovered.rglob('tool_version.json'))),model_records=binds(models),
            native_results=binds(list(recovered.rglob('result.json'))),
            configuration=binds([prep/'model_config.json',prep/'reserved_semantic_pool.json',prep/'source_bindings.json']))
        freeze=controller.freeze(out/'frozen',bindings,'real_model')
        test=out/'independent';test.mkdir()
        selected=b.select_unseen(s.read(prep/'reserved_semantic_pool.json'),freeze,test)
        # No replacements, feedback, or choice among tested versions.
        result=self.native(candidate,test/'native',(),controller.budget,selected)
        expected={f'test{i}/{d["depth"]}/{d["policy"]}/frame2' for i,d in enumerate(selected)}
        observed=set(result['public_targets'])|set(result['historical_targets'])
        result['missing_exposure_ids']=sorted(expected-observed)
        result['unexpected_exposure_ids']=sorted(observed-expected)
        result['passed']=bool(result['historical_accept'] and expected==observed)
        s.dump(test/'result.json',result)
        return {k:v for k,v in result.items() if k!='reference'}


def costs(out,real):
    attempts=list(out.rglob('attempt.json')) if real else []
    calls=[s.read(f.parent/'result.json') if (f.parent/'result.json').exists() else {} for f in attempts]
    compiles=list(out.rglob('compile.json'));execs=list(out.rglob('execute.json'))
    def total(field):return sum(c[field] for c in calls) if all(c.get(field) is not None for c in calls) else None
    return dict(model_calls=len(calls),prompt_tokens=total('prompt_tokens'),completion_tokens=total('completion_tokens'),
        native_compiles=len(compiles),native_executions=len(execs),compile_seconds=sum(s.read(f)['wall_seconds'] for f in compiles),
        execute_seconds=sum(s.read(f)['wall_seconds'] for f in execs),formal_calls=0,
        note='Usage missing at service terminal remains unavailable. Local transport fixtures are not real calls.')


def execute(prep,out,backend):
    out.mkdir(parents=True,exist_ok=False)
    req=s.read(prep/'request.preview.json');initial=json.loads(req['messages'][1]['content'])['current_assertions']
    protected=s.read(SOURCE/'pilot_protocol.json')['protected_ids'];controller=b.Controller(initial,protected)
    first=None;tests=None;recovered=False;active_o=copy.deepcopy(initial);state='not_started';last=initial
    s.dump(out/'execution_mode.json',dict(mode=backend.mode,local_fixture=backend.mode!='real_model'))
    def ledger():
        s.dump(out/'budget.json',dict(reservations=controller.budget.calls,native_stages=controller.budget.native,
            real_model=backend.mode=='real_model',clock_limit_seconds=1200,per_call_timeout_seconds=300))
    try:
        for index in range(2):
            stage=controller.reserve(req);ledger();s.dump(out/stage/'request.preview.json',req)
            result,candidate=backend.generate(req,out/stage/'model_call',last,controller.budget)
            value=dict(assertions=candidate,reason='Already saved original model reason in model_edit.json') if candidate is not None else None
            proposal=controller.response(result['status'],value);ledger()
            if proposal is None:state=controller.state;break
            measured=backend.native(proposal,out/stage/'native',protected,controller.budget)
            state=controller.decision(proposal,measured)
            s.dump(out/stage/'decision.json',dict(decision=state,measurement={k:v for k,v in measured.items() if k!='reference'},retained_H=controller.retained))
            if index==0:
                first=dict(ordinary=measured['ordinary_accept'],history=measured['historical_accept'],branch=state,lost=measured['lost'],unknown=measured['critical_unknown'])
                if measured['ordinary_accept']:active_o=copy.deepcopy(proposal)
            if state=='history_once':req=p.feedback(req,proposal,measured);last=proposal;continue
            recovered=state=='recovered';break
        s.dump(out/'terminal_versions.json',dict(O=active_o,H=controller.retained))
        if recovered:
            tests=backend.independent(prep,out,controller.retained,controller)
            state=('independent_pass' if tests.get('passed') else 'stop_independent_failed') if backend.mode=='real_model' else 'local_fixture_recovery_branch_only'
    except (Exception,KeyboardInterrupt) as exc:
        state='stop_exception_no_retry'
        # Never save exception text that might include credentials or HTTP bodies.
        s.dump(out/'exception.json',dict(type=type(exc).__name__,retries=0,unknown=True))
    finally:
        ledger();s.dump(out/'terminal_versions.json',dict(O=active_o,H=controller.retained))
        s.dump(out/'cost.json',costs(out,backend.mode=='real_model'))
        outcome=dict(status=state,first=first,full_recovery_accepted=recovered,independent=tests,
            mode=backend.mode,real_chain_success=bool(backend.mode=='real_model' and recovered and tests and tests.get('passed')),
            conditional_recovery_denominator=int(backend.mode=='real_model' and first is not None and first['branch']=='history_once'),
            conditional_recovery_numerator=int(backend.mode=='real_model' and recovered),automatic_expansion=False)
        s.dump(out/'outcome.json',outcome)
    return outcome


def run(prep,out,authorization):
    # All authorization checks precede transport construction or credential access.
    verify(prep);validate_grant(s.read(authorization),prep,out)
    backend=RealBackend(out.parent/(out.name+'_transport'))
    result=execute(prep,out,backend)
    s.dump(out/'authorization.json',s.read(authorization));verify(prep)
    return result


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def guard(event,args):
        if event in ('socket.connect','socket.getaddrinfo'):raise RuntimeError('offline_preparation')
        if event=='open' and isinstance(args[0],(str,bytes)):
            path=Path(args[0]).resolve();name=path.as_posix().lower();mode=args[1]
            if any(x in name for x in ('/.secrets/','/.env','/independent','/holdout','/tested_versions/','/terminal_frozen/')):raise RuntimeError('forbidden_material')
            if isinstance(mode,str) and any(x in mode for x in 'wax+') and path.is_relative_to(p.q.D) and not path.is_relative_to(out):raise RuntimeError('old_artifact_immutable')
    sys.addaudithook(guard)
    def ck(name,ok):
        checks.append(dict(name=name,passed=bool(ok)));s.dump(out/'checks.json',checks);assert ok,name
    def rejects(name,fn):
        try:fn()
        except (ValueError,RuntimeError,AssertionError):ck(name,True);return
        ck(name,False)
    for folder in (SOURCE,b.DEFAULT):
        b.verify_manifest(folder/'seal.json');b.verify_manifest(folder/'source_bindings.json');ck('seal '+folder.name,True)
    for name in ('request.preview.json','reserved_semantic_pool.json','development_exclusions.json','probe_descriptors.json'):
        # Preserve the actual preview file bytes, not just equivalent JSON.
        (out/name).write_bytes((SOURCE/name).read_bytes())
    s.dump(out/'model_config.json',CONFIG)
    req=s.read(out/'request.preview.json');initial=json.loads(req['messages'][1]['content'])['current_assertions'];ctl=p.controls()
    ck('exact request bytes',s.sha(out/'request.preview.json')==s.sha(SOURCE/'request.preview.json'))
    ck('same initial partial',initial==ctl['partial_stalled'])
    # Exercise actual inherited serialization/parser with an entirely in-memory
    # HTTP stand-in and a clearly fake credential. Sockets are independently denied.
    class FakeSecret:
        def read_text(self,**kwargs):return 'LOCAL_FIXTURE_NO_REAL_CREDENTIAL'
    class Response:
        headers={'Content-Type':'application/json'}
        def __init__(self,content):self.content=content
        def read1(self,n):part=self.content[:n];self.content=self.content[n:];return part
        def close(self):pass
    observed=[]
    class Opener:
        def __init__(self,kind,value):self.kind=kind;self.value=value
        def open(self,request,timeout):
            observed.append(dict(url=request.full_url,payload=json.loads(request.data),timeout=timeout))
            if self.kind=='timeout':raise TimeoutError('LOCAL_FIXTURE')
            if self.kind=='http':raise urllib.error.HTTPError(request.full_url,400,'LOCAL_FIXTURE',{},None)
            finish='length' if self.kind=='truncated' else 'stop'
            return Response(json.dumps(dict(model='LOCAL_FIXTURE_NOT_SERVICE',choices=[dict(index=0,finish_reason=finish,message=dict(content=json.dumps(self.value)))] )).encode())
    for kind in ('good','invalid','timeout','http','truncated'):
        folder=out/'local_transport_fixtures'/kind
        model=Model(folder/'transport',CONFIG);model.key_file=FakeSecret();model.pending_request=req
        value=dict(assertions=ctl['replacement_ready'],reason='HANDWRITTEN LOCAL TRANSPORT FIXTURE') if kind!='invalid' else {'invalid':'fixture'}
        before=len(observed)
        with patch.object(t.urllib.request,'build_opener',return_value=Opener(kind,value)):
            result,candidate=model.call(folder/'call',initial,p.OB,{},'local_fixture_not_model')
        s.dump(folder/'fixture_origin.json',dict(real_model_calls=0,network_calls=0,synthetic_response=True))
        ck(kind+' one submission only',len(observed)==before+1)
        ck(kind+' unchanged serialized payload',observed[-1]['payload']==req and s.read(folder/'call/request.json')==req)
        ck(kind+' endpoint exact',observed[-1]['url']==p.ENDPOINT)
        ck(kind+' actual300 timeout',299<=observed[-1]['timeout']<=300 and s.read(folder/'transport/remote_transport_config.json')['timeout_seconds']==300)
        ck(kind+' no invented usage',result['prompt_tokens'] is None and result['completion_tokens'] is None)
        expected={'good':'response_received','invalid':'response_received','timeout':'transport_timeout','http':'service_http_error','truncated':'response_truncated'}[kind]
        ck(kind+' terminal status',result['status']==expected)
        ck(kind+' candidate disposition',(candidate==ctl['replacement_ready']) if kind=='good' else candidate is None)
    # Controller end-to-end local fixtures reuse the measured archived results;
    # they never invoke native tools or independent selection.
    measurements=s.read(b.DEFAULT/'archived_control_results.json')
    natives=s.read(SOURCE/'local_fixture_freeze/freeze.json')['bindings']['native_results']
    for name,c in ctl.items():measurements[name].update(candidate_sha256=p.digest(c),native_bindings=natives)
    class FixtureBackend:
        mode='local_fixture_not_model'
        def __init__(self,names):self.names=iter(names);self.submissions=0;self.holdout_called=False
        def generate(self,request,folder,current,clock):
            self.submissions+=1;self.current=next(self.names)
            if self.current=='timeout':return dict(status='transport_timeout'),None
            if self.current=='invalid':return dict(status='response_received'),None
            return dict(status='response_received'),copy.deepcopy(ctl[self.current])
        def native(self,*args):return copy.deepcopy(measurements[self.current])
        def independent(self,prep,out,candidate,controller):
            self.holdout_called=True
            assert controller.state=='recovered'
            return dict(passed=False,status='spy_only_no_samples_generated_or_executed')
    cases=[('both_accept',['union'],1,False),('ordinary_reject',['overbroad'],1,False),('no_trigger',['vacuous'],1,False),
           ('repeat',['partial_stalled'],1,False),('interface',['invalid'],1,False),('transport',['timeout'],1,False),
           ('recover',['replacement_ready','union'],2,True),('failed_recovery',['replacement_ready','overbroad'],2,False),
           ('recovery_repeat',['replacement_ready','replacement_ready'],2,False),('recovery_transport',['replacement_ready','timeout'],2,False)]
    for name,names,n,holdout in cases:
        backend=FixtureBackend(names);folder=out/'local_controller_fixtures'/name
        result=execute(out,folder,backend)
        ck(name+' bounded submissions',backend.submissions==n)
        ck(name+' conditional independent spy',backend.holdout_called==holdout)
        ck(name+' no real success claimed',not result['real_chain_success'] and result['conditional_recovery_denominator']==0)
        if name in ('failed_recovery','recovery_repeat','recovery_transport'):
            ck(name+' baseline retained',s.read(folder/'terminal_versions.json')['H']==initial)
    # Unknown never unlocks the second request, even with an alleged O accept.
    old=copy.deepcopy(measurements['replacement_ready']);measurements['replacement_ready']['critical_unknown']=['fixture_unknown']
    backend=FixtureBackend(['replacement_ready']);r=execute(out,out/'local_controller_fixtures/unknown',backend)
    ck('unknown stops shared',backend.submissions==1 and r['first']['branch']=='stop_unknown');measurements['replacement_ready']=old
    # Wall-clock and conservative request budgets remain fixed.
    clock=p.Budget(clock=lambda:0);clock.start=-1200
    rejects('1200 deadline before call',lambda:clock.reserve_call('shared',req))
    huge=copy.deepcopy(req);huge['messages'][1]['content']='x'*61000
    rejects('per-call request size stops',lambda:p.Budget().reserve_call('shared',huge))
    s.dump(out/'binding_protocol.json',dict(purpose=PURPOSE,parent_protocol=s.rel(SOURCE/'pilot_protocol.json'),parent_seal_sha256=s.sha(SOURCE/'seal.json'),
        model_calls_authorized=0,max_calls=2,call_timeout_seconds=300,controller_wall_seconds=1200,request_sha256=s.sha(out/'request.preview.json'),
        branch='Unchanged research188: one shared proposal, second only O accept/H reject/confirmed regression/no critical unknown. No retries, no expansion.',
        transport='Existing research69 JSON/SSE/raw logging and credential redaction; exact sealed payload, no inserted messages or stream flags. Init timeout metadata corrected180->300 to match actual inherited call.',
        independent='Only complete recovery, frozen assertions/provenance, then32 new scenes; every planned scene must expose its target. No replacement. Tests never feed back.',
        wall_limit='One1200s clock includes model and native work. Native subprocess deadlines clamp to remaining time. Expiry yields unknown/incomplete, never pass. No budget reset for independent stage.',
        limitations='32-scene independent replay may exceed this fixed wall budget on this host; preserve incomplete result. No extra time or request is automatically granted.',
        local_fixtures='Synthetic transport/controller responses are local tests only; real_model_calls=0; no credentials read and no sockets. H/R equivalent; no mechanism claim.'))
    sources=[Path(__file__),Path(b.__file__),Path(p.__file__),Path(t.__file__),ROOT/'scripts/research17_model.py',ROOT/'scripts/research20_model.py',
        ROOT/'scripts/research167_adapter_controller.py',ROOT/'scripts/research136_prospective_history.py',Path(p.q.__file__),Path(s.__file__),Path(s.n.__file__),SOURCE/'seal.json',SOURCE/'source_bindings.json']
    s.dump(out/'source_bindings.json',{s.rel(f):s.sha(f) for f in sources})
    # A template is deliberately NOT an authorization: supplied scope must be
    # explicit after approval, and the run output is fixed before dispatch.
    s.dump(out/'authorization.required.json',dict(authorized=False,purpose=PURPOSE,authorized_calls=2,endpoint=p.ENDPOINT,model=CONFIG['remote_model'],
        prepared_sha256='REPLACE_WITH_VERIFIED_SEAL_AFTER_EXPLICIT_APPROVAL',run_output='deliverables/research189_fifo_pilot_run_20261102_r01'))
    # Grant checks on a temporary local dummy seal cannot authorize run().
    dummy=out/'local_grant_fixture';dummy.mkdir();s.dump(dummy/'seal.json',{'fixture':True})
    target=out/'not_executed';grant=dict(authorized=True,purpose=PURPOSE,authorized_calls=2,endpoint=p.ENDPOINT,model=CONFIG['remote_model'],prepared_sha256=s.sha(dummy/'seal.json'),run_output=s.rel(target))
    validate_grant(grant,dummy,target);ck('scope-matched local grant validation',True)
    for key in grant:
        changed=dict(grant);changed[key]=None;rejects('reject grant '+key,lambda changed=changed:validate_grant(changed,dummy,target))
    rejects('authorization template rejected',lambda:validate_grant(s.read(out/'authorization.required.json'),dummy,target))
    ck('no real run output',not target.exists())
    s.dump(out/'decision.json',dict(local_transport_binding_passed=True,remote_calls=0,new_native_executions=0,new_independent_tests=0,
        conditional_recovery=dict(numerator=0,denominator=0,estimate=None),tasks2_3_expanded=False,authorization_required=True))
    summary=['# research189：research188远程传输绑定本地复核','',
        f'**{len(checks)}项检查通过；真实模型调用0，新增原生执行0，新独立测试0。**','',
        '首轮发送载荷与research188封存请求完全一致；模型、采样参数、初始候选、接受规则、2次上限及1200秒控制器预算未改。继承传输器保存原始响应、用量及实际超时；初始化元数据180秒修正为实际300秒。旧代码和结果保持不变。',
        '', '本地内存HTTP替身验证真实序列化/解析路径，覆盖正常响应、格式错误、HTTP拒绝、超时和截断；网络独立禁用，未读取密钥。替身记录均标为local fixture，不计真实模型调用或恢复。',
        '', '端到端本地分支检查覆盖双方接受、普通拒绝、空触发、重复、格式失败、传输失败、条件恢复成功/失败/重复/超时及关键unknown。仅普通接受、历史拒绝且确认退化时允许第二次；历史拒绝保留初始部分集合。手写恢复分支只触发测试spy，没有生成独立样本。',
        '', '恢复完整接受才冻结并选择32个新语义场景；除检出/触发/误报/unknown外，逐项检查32个目标是否实际曝光。无曝光不能通过，不补抽。1200秒总预算也约束原生进程，独立阶段可能因时限不足成为未完成/unknown，不能自动增加时间。',
        '', '可申请新用途最多2次调用；此前授权不转用。申请后仍须将明确授权写成用途、封存哈希和输出目录绑定记录，才能使用run入口。条件恢复仍0/0不可估计，H/R等价；任务2/3和576次负结果不变。',
        '', '本地复现：','```powershell','wsl -- python3 scripts/research189_drop_transport.py prepare --out deliverables/research189_recheck','```',
        '', '取得明确授权后才可执行（当前没有授权文件）：','```powershell','wsl -- python3 scripts/research189_drop_transport.py run --prepared deliverables/research189_transport_prepare_20261102_r01 --out deliverables/research189_fifo_pilot_run_20261102_r01 --authorization <authorized-file.json>','```']
    (out/'SUMMARY.md').write_text('\n'.join(summary)+'\n',encoding='utf-8')
    s.dump(out/'seal.json',{s.rel(f):s.sha(f) for f in sorted(out.rglob('*')) if f.is_file()})
    verify(out);print('SEALED189',len(checks),'checks; real calls0; native0; independent0',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['prepare','run']);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--prepared',type=Path);parser.add_argument('--authorization',type=Path);args=parser.parse_args()
    if args.action=='prepare':prepare(args.out.resolve())
    else:
        if args.prepared is None or args.authorization is None:parser.error('run requires prepared AND explicit authorization')
        run(args.prepared.resolve(),args.out.resolve(),args.authorization.resolve())
