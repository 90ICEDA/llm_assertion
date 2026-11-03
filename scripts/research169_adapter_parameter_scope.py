"""Local assertion-host parameter binding qualification and new sealed protocol.

Old research167 code, request, response and failed outcome remain immutable.
No model call is made by prepare/native/seal. run requires a new scoped grant.
"""
import argparse
import copy
import importlib.util
import json
from pathlib import Path


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


SCRIPTS=Path(__file__).resolve().parent
# Isolated modules: do not modify globals used by historical audit entrypoints.
q=load('adapter_scope_qualification',SCRIPTS/'research165_adapter_qualification.py')
c=load('adapter_scope_controller',SCRIPTS/'research167_adapter_controller.py')
OLD=q.ROOT/'deliverables/research167_adapter_controller_prepare_20261028_r02'
OLD_RUN=q.ROOT/'deliverables/research167_adapter_run_20261028_r01'
PARAMETERS=dict(S_DATA_WIDTH=8,S_KEEP_ENABLE=0,S_KEEP_WIDTH=1,M_DATA_WIDTH=32,M_KEEP_ENABLE=1,M_KEEP_WIDTH=4)
q.SIGNALS=q.SIGNALS|set(PARAMETERS)
raw_bench=q.bench
INSTANCE='axis_adapter #(.S_DATA_WIDTH(8),.S_KEEP_ENABLE(0),.S_KEEP_WIDTH(1),.M_DATA_WIDTH(32),.M_KEEP_ENABLE(1),.M_KEEP_WIDTH(4)) dut(.*);'
BOUND_INSTANCE='axis_adapter #('+','.join('.'+k+'('+k+')' for k in PARAMETERS)+') dut(.*);'


def bench(assertions,scenarios):
    text=raw_bench(assertions,scenarios)
    if text.count(INSTANCE)!=1 or not text.startswith('module tb;'):raise ValueError('unrecognized_harness_no_binding')
    declarations='\n'+'\n'.join(f'localparam int {k} = {v};' for k,v in PARAMETERS.items())+'\n'
    guards=[f'({k} != dut.{k})' for k in PARAMETERS]
    guards+=['($bits(s_axis_tdata) != S_DATA_WIDTH)','($bits(s_axis_tkeep) != S_KEEP_WIDTH)',
             '($bits(m_axis_tdata) != M_DATA_WIDTH)','($bits(m_axis_tkeep) != M_KEEP_WIDTH)']
    guard='\ninitial begin if ('+' || '.join(guards)+') $fatal(1,"PARAMETER_SCOPE_MISMATCH"); end\n'
    return text.replace('module tb;','module tb;'+declarations,1).replace(INSTANCE,BOUND_INSTANCE+guard,1)


q.bench=bench;c.q=q;c.PURPOSE='research169_parameter_bound_adapter_history_pilot'


def read(p):return q.read(p)
def dump(p,v):q.dump(p,v)


def check_list():
    checks=[]
    def check(name,value):
        checks.append(dict(check=name,passed=bool(value)));assert value,name
    return checks,check


def seal_files(out):
    dump(out/'seal.json',{p.relative_to(out).as_posix():q.sha(p) for p in out.rglob('*') if p.is_file() and p!=out/'seal.json'})


def verify_files(out):
    for p,h in read(out/'seal.json').items():assert q.sha(out/p)==h,p
    for p,h in read(out/'code_bindings.json').items():assert q.sha(q.ROOT/p)==h,p


def prepare(out):
    c.verify(OLD)
    out.mkdir(parents=True,exist_ok=False);checks,check=check_list()
    response=read(OLD_RUN/'shared/model_call/model_edit.json')
    original=read(OLD_RUN/'outcome.json')
    check('old failure unmodified',original['status']=='stop_interface_or_repeat' and not original['first']['measured'])
    adapted=c.adapt(response)
    check('model expression tree preserved',adapted==response['assertions'])
    # q module is isolated: old validator must still reject original response.
    old=load('unchanged_legacy_controller',SCRIPTS/'research167_adapter_controller.py')
    try:old.adapt(response)
    except ValueError as e:check('legacy validator still rejects',str(e)=='non_interface_identifier')
    else:raise AssertionError('old interface changed')
    scenarios=read(c.P/'scenarios.json')
    bound=bench(adapted,scenarios);unbound=raw_bench(adapted,scenarios)
    check('only declarations and instance binding change',bound.count('PARAMETER_SCOPE_MISMATCH')==1)
    for a in adapted:
        check('unaltered antecedent '+a['label'],'('+a['antecedent']+')' in bound)
        check('unaltered consequent '+a['label'],'('+a['consequent']+')' in bound)
    for k,v in PARAMETERS.items():
        check('single constant declaration '+k,bound.count(f'localparam int {k} = {v};')==1)
        check('DUT receives same constant '+k,('.'+k+'('+k+')') in bound)
    for forbidden in ('BYTE_LANES','OTHER_WIDTH','dut.M_KEEP_WIDTH','oracle_value'):
        bad=copy.deepcopy(response);bad['assertions'][0]['consequent']=forbidden+' == 4'
        try:c.adapt(bad)
        except ValueError:check('reject undeclared or hierarchical '+forbidden,True)
        else:raise AssertionError(forbidden)
    for k in PARAMETERS:
        trial=copy.deepcopy(response);trial['assertions'][0]['consequent']=k+' >= 0'
        check('allow explicitly bound parameter '+k,c.adapt(trial)==trial['assertions'])
    dump(out/'parameters.json',PARAMETERS)
    dump(out/'scenarios.json',scenarios)
    dump(out/'raw_model_diagnostic.json',dict(origin='research167 archived failed response; local development diagnostic ONLY, never a new model proposal',assertions=adapted))
    # Literal control is a pre-existing handwritten fixture, not a patched model response.
    literal=read(c.P/'controls/complementary.json')['assertions']
    replacement=[a for a in adapted if a['label']!='nonfinal_keep_full']
    dump(out/'local_replacement.json',dict(origin='handwritten local diagnostic removal, never sent to model',assertions=replacement))
    for name,text in [('unbound',unbound),('bound_archived',bound),('literal_control',bench(literal,scenarios)),('replacement_control',bench(replacement,scenarios))]:
        (out/(name+'.sv')).write_text(text,encoding='utf-8')
    # Deliberately bind DUT to width3 while host width remains4. The guard must stop execution.
    mismatch=bound.replace('.M_KEEP_WIDTH(M_KEEP_WIDTH)','.M_KEEP_WIDTH(3)')
    (out/'mismatch.sv').write_text(mismatch,encoding='utf-8')
    dump(out/'checks.json',checks)
    dump(out/'execution_plan.json',dict(model_calls=0,max_compiles=9,max_executions=7,
        cases=['unbound before/after expected compile failure','bound archived response before/after local diagnostic',
               'handwritten literal control before/after','handwritten replacement before/after','mismatched binding after expected failure'],
        all_data='existing33 development only; no independent inputs drawn',old_result_preserved=True))
    dependencies=read(OLD/'code_bindings.json')
    dependencies[q.old.rel(Path(__file__))]=q.sha(Path(__file__))
    for p in [OLD/'seal.json',OLD_RUN/'outcome.json',OLD_RUN/'shared/model_call/model_edit.json']:
        dependencies[q.old.rel(p)]=q.sha(p)
    dump(out/'code_bindings.json',dependencies);seal_files(out);verify_files(out)
    print('PREPARED169',len(checks),'local checks; no model',flush=True)


def native(prep,out):
    verify_files(prep);out.mkdir(parents=True,exist_ok=False);results=[]
    for name in ('unbound','bound_archived','literal_control','replacement_control','mismatch'):
        for rev in (('after',) if name=='mismatch' else ('before','after')):
            folder=out/name/rev
            n=q.old.native.run_native((prep/(name+'.sv')).read_text(),folder,extra_sources=[c.P/'rtl'/rev/'axis_adapter.v'])
            results.append(dict(case=name,revision=rev,result=n));dump(out/'progress.json',results)
            print('NATIVE169',name,rev,n['compile_status'],n['execution_status'],flush=True)
    dump(out/'results.json',results);verify_files(prep)


def seal(prep,native_out,out):
    verify_files(prep);c.verify(OLD);checks,check=check_list()
    results=read(native_out/'results.json');check('exact9 local compilations',len(results)==9)
    for x in results:
        n=x['result'];label=x['case']+' '+x['revision']
        if x['case']=='unbound':
            check('unbound rejected '+label,n['compile_status']!='passed' and n['execution_status']!='completed')
            check('unbound native names width',(native_out/x['case']/x['revision']/'compile.log').read_text().find('M_KEEP_WIDTH')>=0)
        elif x['case']=='mismatch':
            check('mismatched scope never passes',n['compile_status']!='passed' or n['execution_status']!='completed')
        else:check('native completes '+label,n['compile_status']=='passed' and n['execution_status']=='completed')
    scenarios=read(prep/'scenarios.json');protected=read(OLD/'protected.json')
    candidates=dict(bound_archived=read(prep/'raw_model_diagnostic.json')['assertions'],literal_control=read(c.P/'controls/complementary.json')['assertions'],replacement_control=read(prep/'local_replacement.json')['assertions'])
    evaluations={k:c.measure(v,native_out/k,scenarios,protected) for k,v in candidates.items()}
    full=evaluations['bound_archived'];replacement=evaluations['replacement_control']
    check('archived local diagnostic all targets and history',full['ordinary'] and full['history'] and not full['unknown'] and not full['lost'] and not full['new_false'])
    check('local public8 history20 actual targets',len(full['public_targets'])==8 and len(full['history_targets'])==20)
    check('meaningful replacement distinction preserved',replacement['ordinary'] and not replacement['history'] and len(replacement['lost'])==12 and not replacement['unknown'])
    for rev in ('before','after'):
        # All stimulus, RTL output, failures and effective triggers must match literal local control.
        a=full['evidence'][rev];b=evaluations['literal_control']['evidence'][rev]
        for field in ('trace','failed','effective_triggers','oracle'):
            check('same literal and parameter diagnostic '+rev+' '+field,a[field]==b[field])
    out.mkdir(parents=True,exist_ok=False)
    for name in ('initial.json','protected.json','model_config.json'):
        dump(out/name,read(OLD/name))
    req=read(OLD/'request.preview.json');body=json.loads(req['messages'][1]['content']);original_body=copy.deepcopy(body)
    body['assertion_host_scope']=dict(module='tb',parameters=PARAMETERS,
        declaration='Each listed name is a tb localparam; the DUT instance is configured with those same constants. They are not runtime inputs. Other DUT parameters/internal/hierarchical names are unavailable.',
        permitted_identifiers=sorted(q.SIGNALS),sampled_functions=['$past','$stable'],
        expressions_preserved='The interface validates and inserts original expressions unchanged; it never replaces names with literals or edits predicate semantics.',
        unchanged_fixed_scope='8-to-32 only, original before/after RTL, all prior public and historical rules unchanged.')
    req['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    removed=copy.deepcopy(body);removed.pop('assertion_host_scope')
    check('only request change is explicit scope',removed==original_body)
    check('no archived model response added',body['current_assertions']==read(OLD/'initial.json'))
    dump(out/'request.preview.json',req)
    protocol=read(OLD/'protocol.json');protocol.update(purpose=c.PURPOSE,status='parameter_binding_locally_verified_sealed_no_new_authorization',
        assertion_host_parameters=PARAMETERS,prior_failure='research167 remains interface_rejected; archived response replay is local diagnostic, not model acceptance or recovery',
        generator_change='Explicit host parameter binding only; no new model, seed, predicates, development scenarios or acceptance criteria.',
        real_recovery_rate=dict(numerator=0,denominator=0,estimate=None),funding='New purpose-bound authorization required; unused research167 recovery quota not transferred.')
    dump(out/'protocol.json',protocol)
    # Reuse legacy branch/budget tests on its unchanged request, then execute the new request through same fixture state machine.
    legacy_checks=c.local_checks(OLD,out/'legacy_controller_checks')
    for i,(names,expected) in enumerate([(['replacement','complementary'],'local_fixture_gate_only'),(['complementary'],'stop_both_accept'),(['overbroad'],'stop_ordinary'),(['transport'],'stop_transport')]):
        backend=c.FixtureBackend(names);path=out/'bound_request_branch_checks'/str(i)
        c.execute(out,path,backend);r=read(path/'outcome.json')
        if i==0:check('new request conditional recovery branch local only',r['first']['branch']=='history_once' and r['full_recovery_accepted'] and not r['real_chain_success'])
        else:check('new request stop no recovery '+str(i),r['first']['branch']!='history_once' and not r['full_recovery_accepted'] and len(backend.used)==1)
        check('new request causes zero real calls '+str(i),read(path/'cost.json')['model_calls']==0)
    check('no independent input selection',not list(out.rglob('scenarios.json')))
    dump(out/'native_evaluations.json',evaluations);dump(out/'checks.json',checks)
    costs=dict(model_calls=0,formal_calls=0,native_compiles=len(results),native_executions=sum(x['result']['native_simulation_calls'] for x in results),
        compile_seconds=sum(x['result']['compile']['wall_seconds'] for x in results),execute_seconds=sum(x['result'].get('execute',{}).get('wall_seconds',0) for x in results))
    dump(out/'cost.json',costs)
    bindings=read(prep/'code_bindings.json');bindings[q.old.rel(prep/'seal.json')]=q.sha(prep/'seal.json')
    for p in native_out.rglob('*'):
        if p.is_file() and 'obj_dir' not in p.parts:bindings[q.old.rel(p)]=q.sha(p)
    dump(out/'code_bindings.json',bindings)
    total=len(read(prep/'checks.json'))+len(checks)+len(legacy_checks)
    (out/'SUMMARY.md').write_text(f'''# 参数作用域核查与新协议封存

本地检查共{total}项通过。模型调用0；原生编译{costs['native_compiles']}次，执行{costs['native_executions']}次；没有新独立测试。

根因：DUT模块参数不自动进入外层tb作用域。旧接口拒绝M_KEEP_WIDTH；原生未绑定对照也编译失败。新接口在tb显式声明固定配置的6个localparam，并将同一值传入DUT实例；运行时核对DUT参数及接口位宽。只开放已绑定参数，仍拒绝未知参数、内部信号及层级引用。

没有替换research167响应的参数名、谓词或时间关系。它在新宿主中的回放仅作为本地接口诊断：公共8/8、历史20/20违例采样检出，无合法误报、无关键unknown，保留12个旧检出点；与既有手写字面量对照的完整波形、失败及触发位置一致。这不是新模型接受、自动恢复或独立验收；旧research167失败记录保持不变。

手写局部替换对照仍为普通接受、历史拒绝、丢失12个旧检出点。错误绑定对照被拒绝。不能把这些对照计为真实防退化收益。条件恢复仍0/0、不可估计，H/R等价限制保持。

新请求只增加显式作用域说明，保持模型、种子、开发信息、初始部分断言与接受规则；没有发送本轮诊断响应或手写成功性质。相同控制器已完成新请求分支预检。最多2次的分支和停止条件保持不变，尚未取得新用途授权，不挪用旧剩余额度。

后续只有普通接受、历史拒绝且确认退化、无关键unknown才恢复一次；完整恢复后才冻结并抽取32个新独立场景，仅验收H版本。没有合格分支即停止。

复核命令（无模型调用）：
```powershell
wsl -- python3 scripts/research169_adapter_parameter_scope.py verify --prepared {q.old.rel(out)}
```
本地原生输入：{q.old.rel(prep)}；运行记录：{q.old.rel(native_out)}。
''',encoding='utf-8')
    seal_files(out);c.verify(out);c.verify(OLD)
    print('SEALED169',total,'checks; model0; conditional recovery0/0',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','native','seal','verify','run'])
    for n in ('prepared','executed','out','authorization'):ap.add_argument('--'+n,type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='native':native(a.prepared.resolve(),a.out.resolve())
    elif a.action=='seal':seal(a.prepared.resolve(),a.executed.resolve(),a.out.resolve())
    elif a.action=='verify':c.verify(a.prepared.resolve());c.verify(OLD);print('VERIFIED169; no model call')
    else:c.run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
