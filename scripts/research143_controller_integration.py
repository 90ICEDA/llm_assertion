"""Local controller tests backed by existing native records, never LLM output.

Network and real model dispatch are disabled. These test protocol transitions,
not model recovery rates. No independent inputs/outcomes are read or generated.
"""
import argparse
import copy
import json
from pathlib import Path
import time
from unittest.mock import patch
import research142_mapped_history_pilot as c

read,dump,digest,rel=c.read,c.dump,c.digest,c.rel
CACHE={}


class LocalBackend:
    mode='local_controller_test_not_model_experiment'
    def __init__(self, steps, prep):
        self.steps=steps;self.index=0;self.prep=prep;self.events=[];self.current=None

    def generate(self, req, folder, current):
        folder.mkdir(parents=True,exist_ok=False)
        self.current=self.steps[self.index];self.index+=1
        dump(folder/'local_request.json',req)
        self.events.append(dict(kind='local_generate_stub',step=self.current,at=time.time()))
        if self.current=='transport_failure':
            dump(folder/'local_stub.json',dict(status='timeout',not_a_model_call=True))
            return dict(status='timeout'),None
        if self.current=='initial_repeat':value=c.p.q.as_edit(read(self.prep/'initial.json'))
        else:
            source='historical_loss' if self.current=='critical_unknown' else self.current
            source='split' if source=='interface_invalid' else source
            value=read(c.QUAL_PREP/'fixtures'/source/'edit.json')
            if self.current=='interface_invalid':value['assertions'][0]['obligations']=['invalid']
        try:
            # Use the exact real output adapter; transport itself is never called.
            model=object.__new__(c.Model)
            candidate,kind=model.save_decoded_output(folder,value,current,'unused_local_test')
        except (ValueError,AssertionError,TypeError,KeyError) as exc:
            dump(folder/'local_stub.json',dict(not_a_model_call=True,interface_error=type(exc).__name__))
            return dict(status='response_received'),None
        dump(folder/'local_stub.json',dict(not_a_model_call=True,fixture=self.current,output_kind=kind))
        return dict(status='response_received'),candidate

    def evaluate(self,candidate,folder,baseline):
        source='historical_loss' if self.current=='critical_unknown' else self.current
        native=c.QUAL_RUN/source/'native'
        assert candidate==read(c.QUAL_RUN/source/'candidate.json')
        if source not in CACHE:CACHE[source]=c.mapping.inspect_version(native,candidate,baseline)
        count,ev,records=copy.deepcopy(CACHE[source])
        folder.mkdir(parents=True,exist_ok=False)
        dump(folder/'local_native_reference.json',dict(path=rel(native),rows_reaudited=count,
             decision_sha256=digest(native/'decision.json'),new_native_execution=False))
        if self.current=='critical_unknown':
            ev['all_property_guards']['history']['unknown'].append(dict(kind='explicit_local_unknown_injection'))
        self.events.append(dict(kind='local_cached_native',source=source,at=time.time()))
        return ev,records,native

    def independent(self,prep,out,active,baseline,records):
        assert read(out/'terminal_freeze.json')['versions']=={a:c.x.old.acceptance.sha(v) for a,v in active.items()}
        assert all(read(out/'terminal_frozen'/a/'candidate.json')==v for a,v in active.items())
        self.events.append(dict(kind='local_independent_hook_only',at=time.time()))
        dump(out/'local_independent_hook.json',dict(called_after_freeze=True,new_inputs=0,new_executions=0,
             not_an_independent_result=True,freeze_sha256=digest(out/'terminal_freeze.json')))
        return None


def audit(prep,out):
    opened=c.p.q.guard();c.verify(prep)
    out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,ok):
        assert ok,name
        checks.append(name)
    def rejects(name,action):
        try:action()
        except (AssertionError,ValueError,KeyError):check(name,True)
        else:raise AssertionError(name)
    grant=dict(purpose=c.PURPOSE,authorized_calls=2,endpoint=c.p.transport.DEFAULT_URL,
               model=c.p.s.MODEL,prepared_sha256=digest(prep/'sealed.json'),run_output=rel(out/'never_run'))
    # Synthetic grant is used only for parser tests, never saved or dispatched.
    for key,value in [('purpose',c.p.PURPOSE),('authorized_calls',3),('endpoint','https://invalid.example'),
                      ('model','different'),('prepared_sha256','0'*64),('run_output','wrong')]:
        bad=dict(grant);bad[key]=value
        rejects('grant_'+key,lambda:c.validate_grant(prep,out/'never_run',bad))
    check('authorization_absent',not (prep/'authorization.json').exists())
    scenarios={
        'both_accept':(['permuted'],'stop_both_accept_no_discrimination',False),
        'ordinary_rejects':(['branch_first_only'],'stop_ordinary_rejects',False),
        'recovery_succeeds':(['historical_loss','split'],'recovered_full151',True),
        'recovery_repeats':(['historical_loss','historical_loss'],'stop_recovery_failed',False),
        'recovery_transport':(['historical_loss','transport_failure'],'stop_recovery_failed',False),
        'critical_unknown':(['critical_unknown'],'stop_unknown',False),
        'interface_invalid':(['interface_invalid'],'stop_interface_or_repeat',False),
        'initial_repeat':(['initial_repeat'],'stop_interface_or_repeat',False),
        'transport_failure':(['transport_failure'],'stop_transport',False),
    }
    # Guard both remote dispatch paths and direct network access. Cached native
    # audit reads existing files; no executable or model process is launched.
    with (patch.object(c.Model,'call',side_effect=AssertionError('real_model_forbidden')),
         patch('urllib.request.build_opener',side_effect=AssertionError('network_forbidden')),
         patch('socket.create_connection',side_effect=AssertionError('network_forbidden'))):
        for name,(steps,want,recovered) in scenarios.items():
            folder=out/'local_scenarios'/name;folder.mkdir(parents=True)
            backend=LocalBackend(steps,prep);c.execute(prep,folder,backend)
            outcome=read(folder/'outcome.json');dump(folder/'local_events.json',backend.events)
            check(name+'/state',outcome['completed'] and outcome['status']==want)
            check(name+'/consumed_exact_local_steps',backend.index==len(steps))
            check(name+'/not_real_model_results',outcome['actual_model_calls']==0 and not outcome['qualified_chain']
                  and not outcome['new_independent_executed'] and outcome['mode']==backend.mode)
            check(name+'/native_not_rerun',read(folder/'cost.json')['native_compiles']==read(folder/'cost.json')['native_executions']==0)
            check(name+'/freeze_eligibility',(folder/'terminal_freeze.json').exists()==recovered)
            check(name+'/heldout_hook_eligibility',(folder/'local_independent_hook.json').exists()==recovered)
            if recovered:
                check(name+'/freeze_before_hook',read(folder/'terminal_freeze.json')['time']<=backend.events[-1]['at'])
            initial=read(prep/'initial.json')
            if name.startswith('recovery_'):
                negative=read(c.QUAL_RUN/'historical_loss/candidate.json')
                check(name+'/O_accepts',read(folder/'arms/O/v0/active.json')==negative)
                check(name+'/H_retains',read(folder/'arms/H/v0/active.json')==initial)
                target=read(c.QUAL_RUN/'split/candidate.json') if recovered else initial
                check(name+'/H_terminal',read(folder/'arms/H/v1/active.json')==target)
                req=read(folder/'history/v1/model_call/local_request.json')
                body=json.loads(req['messages'][1]['content'])
                check(name+'/H_actual_failure_feedback',set(body['actual_feedback']['visible_counts'])=={'alignment','search','history'}
                      and body['current_assertions']==[{k:a[k] for k in c.p.q.FIELDS} for a in negative['assertions']])
            first=read(folder/'shared/v0/model_call/local_request.json')
            check(name+'/shared_exact',first==read(prep/'request.preview.json'))
            check(name+'/public_only',set(json.loads(first['messages'][1]['content'])['actual_feedback']['visible_counts'])=={'alignment','search'})
    # Independent summarizer is label-projected too. Test it on DEVELOPMENT
    # records only, with development configs; not new independent acceptance.
    summaries={}
    for name in ('split','permuted','duplicate'):
        candidate=read(c.QUAL_RUN/name/'candidate.json');folder=c.QUAL_RUN/name/'native/search'
        result=read(folder/'result.json');c.mapping.validate_ledger(result,candidate)
        guard=c.x.all_guard(folder,result,candidate)
        with patch.object(c.x.holdout.base,'CONFIGS',c.x.old.CONFIGS):
            summaries[name]=c.x.holdout.summarize(result,guard)
        check('heldout_summary_on_dev/'+name,summaries[name]['passed'])
    check('heldout_summary_order_independent',summaries['split']['counts']==summaries['permuted']['counts']==summaries['duplicate']['counts'])
    check('global_no_dispatch',not list(out.rglob('attempt.json')) and not list(out.rglob('compile.json'))
          and not list(out.rglob('execute.json')) and not list(out.rglob('independent_cases.json')))
    # Admission and request isolation; private fixtures are not part of the
    # model preview. Exact original candidate inventory/selection is retained.
    req=read(prep/'request.preview.json');body=json.loads(req['messages'][1]['content'])
    check('shared_O_H',req==read(prep/'arms/O/request.preview.json')==read(prep/'arms/H/request.preview.json'))
    check('new_contract',body['output_contract']==c.mapping.CONTRACT)
    check('old_positional_contract_absent','First item labels' not in json.dumps(req))
    check('no_fixture_or_independent_inputs',not any(v in json.dumps(req) for v in
          ('local_history_loss','local_positive','archived136_exact','independent_cases.json','research133')))
    check('unchanged_candidate_selection',read(prep/'selection.json')==read(c.OLD_PREP/'selection.json')
          and read(prep/'candidate_matrix.json')==read(c.OLD_PREP/'candidate_matrix.json'))
    check('native_budget_tests',sum(e=='third_call' for e in read(prep/'controller_checks.json'))==1)
    c.verify(prep)
    dump(out/'checks.json',checks);dump(out/'read_audit.json',sorted(opened))
    dump(out/'audit.json',dict(passed=True,checks=len(checks),controller_checks=len(read(prep/'controller_checks.json')),
        local_scenarios=len(scenarios),cached_native_versions_reaudited=sorted(CACHE),
        cached_native_rows_reaudited=sum(v[0] for v in CACHE.values()),model_calls=0,new_native_calls=0,
        new_model_acceptances=0,new_independent_tests=0,real_incremental_rejections=None,real_recoveries=None,
        no_model_authorization_requested=True,prepared_seal=digest(prep/'sealed.json')))
    text=['# research142：新义务映射已接入前瞻控制器','',
          '候选组装、当前/历史原生门控、原生日志审计和两轮反馈均使用research139标签映射。每项义务可有多条性质且顺序不限，仍保持总2–6条。普通规则与完整151历史要求不变。',
          '已封存原部分基线、全部候选及排除理由、同一公共请求、模型/参数、种子14207/14208、停止分支和新接口源代码。新映射是公共基础设施修正，不计为两个核心机制的收益。', '',
          '固定先导：共享新提案1次；仅普通接受、历史拒绝，且确认旧检出丢失或新增合法误报、无关键unknown时，再允许历史反馈恢复1次。无机会、接口失败、重复或传输失败即停；恢复失败不加轮次、不扩种子。',
          '实际调度预算：模型最多2次、每次最多1024输出token，保守输入/输出预留每次40000、总80000；每次300秒，阶段开始前检查总1200秒。原生每提案预留6次编译/执行，最多12；仅恢复接受后的独立O/H预留4次，总16。编译冒烟不重复计数。',
          '历史拒绝时持久化保留旧活动版本；发送失败提案作反馈不会替换活动版本。完整恢复接受后才先冻结两组，再生成96个新指令、四配置独立测试；旧独立输入仅此时读取用于去重，不读取结果，research133排除在读取范围外。', '',
          f'本地集成{len(checks)}项检查、预算/分支{len(read(prep/"controller_checks.json"))}项检查通过；9条本地路径演练，复核{sum(v[0] for v in CACHE.values())}条既有原生开发记录。网络和真实模型调用在演练中禁用。',
          '本地演练包含额外拒绝→回退→恢复→冻结入口，但使用明确标注的本地夹具和缓存原生记录。不是新的模型提案、恢复成功率或独立通过；本轮模型0、原生新增执行0、新接受模型版本0、新独立测试0。',
          'research136旧接口失败、research140旧响应回顾性通过、research133独立结果均保留。H/R语义等价；未来只能检验增加历史检查的作用，不主张R独有收益。', '',
          '本轮只完成本地集成和封存，不申请或使用模型额度。将来执行需新的用途、封存哈希和输出目录绑定的明确最多2次授权，不能转用research136剩余条件性额度。', '',
          '封存核验：','```powershell',f'wsl -- python3 scripts/research142_mapped_history_pilot.py verify --prepared {rel(prep)}','```',
          '本地集成复核（新输出目录，无模型调用）：','```powershell',
          f'wsl -- python3 scripts/research143_controller_integration.py --prepared {rel(prep)} --out deliverables/research143_recheck','```']
    (out/'SUMMARY.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    dump(out/'source_bindings.json',{rel(Path(__file__)):digest(Path(__file__)),rel(prep/'sealed.json'):digest(prep/'sealed.json')})
    dump(out/'sealed.json',{f.relative_to(out).as_posix():digest(f) for f in out.rglob('*') if f.is_file()})
    print('INTEGRATED143',len(checks),'checks; model0 native0',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--prepared',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();audit(a.prepared.resolve(),a.out.resolve())
