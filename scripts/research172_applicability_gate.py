"""New, obligation-aware gate. Never rewrites archived acceptance results.

Applicability is separate from verdict (pass/violation/unknown). A disabled or
nonapplicable obligation has verdict=None, never pass. Native SVA remains the
assertion evaluator; this module judges independent reference obligations only.
"""
import argparse
from collections import Counter
import copy
import itertools
import json
from pathlib import Path
import re
import research171_nonhandshake_audit as audit

s=audit.s;q=s.q
OLD=q.ROOT/'deliverables/research169_scope_controller_prepare_20261028_r02'
RUN=audit.RUN
c=s.load('applicability_controller',Path(__file__).parent/'research167_adapter_controller.py')
c.q=q;c.PURPOSE='research172_obligation_applicability_history_pilot'
legacy_measure=c.measure
OBLIGATIONS=('nonfinal_keep','final_nonempty','stall_valid','stall_payload')
KEEP={'nonfinal_keep','final_nonempty'}


def state(applicable=False,verdict=None,reason='not_applicable',expected=None,observed=None):
    assert (not applicable and verdict is None) or (applicable and verdict in ('pass','violation','unknown'))
    return dict(applicable=applicable,verdict=verdict,reason=reason,expected=expected,observed=observed)


def reference_table(trace):
    reference=audit.replay(trace);table={};previous=None
    for v in trace:
        cycle=v['cycle'];row={ob:state() for ob in OBLIGATIONS};sample=reference['samples'][cycle]
        if v['rst']:
            row={ob:state(reason='reset_cancels') for ob in OBLIGATIONS};previous=None
        else:
            if v['mv'] and v['mr']:
                if sample['applicability']!='applicable_transfer':
                    for ob in KEEP:row[ob]=state(True,'unknown','unresolved_transfer_reference')
                else:
                    ep=reference['episodes'][sample['episode']]
                    ob='final_nonempty' if ep['expected_last'] else 'nonfinal_keep'
                    passed=v['mk']!=0 if ob=='final_nonempty' else v['mk']==15
                    row[ob]=state(True,'pass' if passed else 'violation','accepted_reference_group',
                        'nonzero' if ob=='final_nonempty' else 15,v['mk'])
            if previous and previous['sid']==v['sid'] and previous['mv'] and not previous['mr']:
                row['stall_valid']=state(True,'pass' if v['mv'] else 'violation','previous_sample_stalled',1,v['mv'])
                expected=[previous[k] for k in ('md','mk','ml')];observed=[v[k] for k in ('md','mk','ml')]
                row['stall_payload']=state(True,'pass' if observed==expected else 'violation','previous_sample_stalled',expected,observed)
            previous=v
        table[cycle]=row
    return reference,table


def alarm_verdict(reference,table,cycle,assertion,own_trigger):
    obs=assertion['obligations'];decision=dict(cycle=cycle,assertion=assertion['label'],obligations=obs,
        category='unknown',matched_obligations=[],reason=None,transaction=None)
    if not own_trigger:decision['reason']='no_own_effective_trigger';return decision
    if cycle not in table:decision['reason']='missing_sample';return decision
    if reference['trace_issues']:decision['reason']='trace_incomplete';return decision
    sample=reference['samples'][cycle]
    if sample['sid'] in reference['illegal_source_scenarios']:decision['reason']='illegal_source';return decision
    states={ob:table[cycle][ob] for ob in obs};decision['reference_states']=states
    if any(x['verdict']=='unknown' for x in states.values()):decision['reason']='applicable_reference_unknown';return decision
    failed=[ob for ob,v in states.items() if v['verdict']=='violation']
    if failed:
        decision.update(category='target_detection',matched_obligations=failed,reason='native_failure_and_matching_reference_violation');return decision
    applicable=[x for x in states.values() if x['applicable']]
    if applicable:
        if len(applicable)!=len(states) and not set(obs)<=KEEP:
            decision['reason']='mixed_unresolved_obligation_applicability';return decision
        decision.update(category='false_positive',reason='applicable_reference_pass_but_native_failure');return decision
    # Only mapped KEEP assertions may claim an early KEEP witness. Do not let
    # another obligation's failure borrow an unrelated subsequent KEEP error.
    if not set(obs)<=KEEP:decision['reason']='no_applicable_mapped_obligation';return decision
    early=audit.classify(reference,cycle,assertion['label'])
    decision['transaction']=early
    if early['category']=='confirmed_false_positive':
        # A property can fire beyond its self-declared scope. NA is still NOT
        # pass: this rejection requires a separately verified legal transfer.
        decision.update(category='false_positive',reason='independently_legal_transfer_alarm_outside_declared_scope')
        return decision
    if early['category']!='confirmed_early_detection':decision['reason']=early['reason'];return decision
    future=table[early['transfer_cycle']]
    matched=[ob for ob in obs if future[ob]['verdict']=='violation']
    if not matched:decision['reason']='early_witness_wrong_obligation';return decision
    decision.update(category='early_detection',matched_obligations=matched,reason='same_stable_transaction_confirmed_later')
    return decision


def judge(candidate,legacy,records,scenarios,protected):
    result=copy.deepcopy(legacy)
    result['gate_version']='research172_applicability_v1'
    result['legacy_comparison_only']={k:legacy.get(k) for k in ('ordinary','history','false_before','false_after','unknown')}
    if legacy['unknown']:
        result.update(ordinary=False,history=False);return result
    unknown=[];false={};direct={};triggered={};details={};labels={a['label']:a for a in candidate}
    for rev in ('before','after'):
        trace=legacy['evidence'][rev]['trace'];ref,table=reference_table(trace)
        if ref['trace_issues'] or ref['illegal_source_scenarios']:unknown.append(rev+':reference_unknown')
        if any(v['verdict']=='unknown' for row in table.values() for v in row.values()):unknown.append(rev+':applicable_reference_unknown')
        own={k:set() for k in labels}
        for t in records[rev]['triggers']:
            if t['id'] not in labels:unknown.append(rev+':unknown_trigger_label');continue
            anchor=int(re.fullmatch(r'cycle=(\d+)',t['detail'])[1]);due=anchor+(labels[t['id']]['timing']=='next_sample')
            if due not in table:unknown.append(rev+':unresolved_trigger_horizon');continue
            if trace[due]['rst']:continue
            own[t['id']].add(due)
        rows=[]
        for f in records[rev]['failures']:
            cycle=int(re.fullmatch(r'cycle=(\d+)',f['detail'])[1])
            if f['id'] not in labels:unknown.append(rev+':unknown_failure_label');continue
            r=alarm_verdict(ref,table,cycle,labels[f['id']],cycle in own[f['id']]);rows.append(r)
            if r['category']=='unknown':unknown.append(f"{rev}:{f['id']}:{cycle}:{r['reason']}")
        false[rev]=sorted({r['cycle'] for r in rows if r['category']=='false_positive'})
        detected={(r['cycle'],ob) for r in rows if r['category']=='target_detection' for ob in r['matched_obligations']}
        # Early detection removes a false-positive attribution ONLY. It does
        # not replace direct target coverage or earn an additional discovery.
        targets=set(legacy['public_targets']+legacy['history_targets']) if rev=='before' else set()
        direct[rev]=set();triggered[rev]=set();coverage=[]
        for cycle in sorted(targets):
            needed=[ob for ob in KEEP if table[cycle][ob]['verdict']=='violation']
            if not needed:unknown.append(rev+':target_outside_confirmed_obligations:'+str(cycle))
            d=bool(needed) and all((cycle,ob) in detected for ob in needed)
            t=bool(needed) and all(any(ob in a['obligations'] and cycle in own[a['label']] for a in candidate) for ob in needed)
            if d:direct[rev].add(cycle)
            if t:triggered[rev].add(cycle)
            coverage.append(dict(cycle=cycle,obligations=needed,detected=d,triggered=t))
        # Save explicit states at applicable cycles and every alarm cycle. All
        # omitted cycles are explicitly counted nonapplicable, never passes.
        alarm_cycles={r['cycle'] for r in rows}
        detail_table={cycle:row for cycle,row in table.items() if cycle in alarm_cycles or any(x['applicable'] for x in row.values())}
        counts=Counter((ob,v['verdict'] if v['applicable'] else 'not_applicable') for row in table.values() for ob,v in row.items())
        details[rev]=dict(alarms=rows,target_coverage=coverage,obligation_samples=detail_table,
            counts={ob:{ver:counts[ob,ver] for ver in ('pass','violation','unknown','not_applicable')} for ob in OBLIGATIONS},
            early_detection_count=sum(r['category']=='early_detection' for r in rows),
            early_transaction_ids=sorted({r['transaction']['episode_id'] for r in rows if r['category']=='early_detection'}),
            own_effective_triggers={k:sorted(v) for k,v in own.items()})
    public=set(legacy['public_targets']);history=set(legacy['history_targets']);found=direct['before'];trig=triggered['before']
    fp=sorted(set(false['before']+false['after']))
    ordinary=not(unknown or fp or public-found or public-trig)
    historical=ordinary and not(history-found or history-trig)
    result.update(ordinary=ordinary,history=historical,unknown=unknown,false_before=false['before'],false_after=false['after'],new_false=fp,
        lost=sorted(set(protected)-found),public_missed=sorted(public-found),history_missed=sorted(history-found),
        public_untriggered=sorted(public-trig),history_untriggered=sorted(history-trig),obligation_evaluation=details)
    return result


def measure(candidate,folder,scenarios,protected=()):
    original=legacy_measure(candidate,folder,scenarios,protected)
    records={rev:q.read(folder/rev/'result.json') for rev in ('before','after')}
    return judge(candidate,original,records,scenarios,protected)


c.measure=measure


class LocalBackend(c.FixtureBackend):
    def generate(self,req,path,current):
        name=next(self.names);self.used.append(name);self.current=name
        if name=='archived169':return dict(status='response_received'),q.read(RUN/'shared/model_call/candidate.json')
        if name=='transport':return dict(status='transport_timeout'),None
        if name=='interface':return dict(status='response_received'),None
        return dict(status='response_received'),q.read(c.P/'controls'/f'{name}.json')['assertions']
    def native(self,candidate,path,scenarios):
        return RUN/'shared/native' if self.current=='archived169' else c.N/self.current


def prepare(out):
    c.verify(OLD);old_hash=q.sha(RUN/'outcome.json');checks,check=s.check_list()
    out.mkdir(parents=True,exist_ok=False)
    for name in ('initial.json','protected.json','model_config.json'):q.dump(out/name,q.read(OLD/name))
    request=q.read(OLD/'request.preview.json');body=json.loads(request['messages'][1]['content']);original=copy.deepcopy(body)
    body['acceptance']='Both policies use the same native public targets and obligation applicability checks. Not-applicable is not pass. Applicable reference verdict is pass, violation or unknown. A native failure on reference-pass is a false positive; unresolved attribution rejects. A non-handshake KEEP alarm is only attributed as early detection when the same previously accepted output remains stable without reset through an actual independently violating handshake. Early alarms do not replace required direct target detection/trigger or add discoveries. Historical policy additionally requires prior/history target coverage. No reference data or successful candidate is supplied by this rule.'
    request['messages'][1]['content']=json.dumps(body,separators=(',',':'))
    check('only acceptance explanation changed',{k for k in body if body[k]!=original[k]}=={'acceptance'})
    q.dump(out/'request.preview.json',request)
    protocol=q.read(OLD/'protocol.json');protocol.update(purpose=c.PURPOSE,status='new_gate_local_validation_no_model_authorization',
        gate_version='research172_applicability_v1',
        acceptance_change='Explicit per-obligation applicability, pass/violation/unknown; same-transaction confirmed early alarms no longer called false positives. Direct target detection/trigger and all actual false-positive/unknown rejection requirements retained.',
        historical_scope='H/R equivalent; added-history coverage only; all-component false-positive guard common to O/H.',
        old_decisions='Immutable. Archived169 replay is a retrospective local control, not new acceptance or prospective effectiveness.',
        funding='No new real calls authorized. Unspent research169 conditional call cannot transfer.')
    q.dump(out/'protocol.json',protocol)
    scenarios=q.read(c.P/'scenarios.json');protected=q.read(out/'protected.json');evals={}
    for name in ('baseline','replacement','complementary','overbroad','archived169'):
        if name=='archived169':candidate=q.read(RUN/'shared/model_call/candidate.json');folder=RUN/'shared/native'
        else:candidate=q.read(c.P/'controls'/f'{name}.json')['assertions'];folder=c.N/name
        ev=measure(candidate,folder,scenarios,protected);evals[name]=ev;q.dump(out/'local_native_rejudgment'/f'{name}.json',ev)
    check('baseline still misses public',not evals['baseline']['ordinary'] and len(evals['baseline']['public_missed'])==8)
    check('replacement still discriminates',evals['replacement']['ordinary'] and not evals['replacement']['history'] and len(evals['replacement']['lost'])==12)
    check('complementary control passes',evals['complementary']['history'] and not evals['complementary']['unknown'])
    check('overbroad genuine false positives rejected',not evals['overbroad']['ordinary'] and len(evals['overbroad']['false_after'])==32)
    fixed=evals['archived169']
    check('archived early case locally compatible only',fixed['ordinary'] and fixed['history'] and not fixed['unknown'])
    check('all68 early deduplicated',fixed['obligation_evaluation']['before']['early_detection_count']==68 and len(fixed['obligation_evaluation']['before']['early_transaction_ids'])==16)
    check('no weakening direct coverage',not fixed['public_missed'] and not fixed['history_missed'] and not fixed['lost'])
    # Unit controls are marked synthetic; none are passed off as RTL/model runs.
    trace=fixed['evidence']['before']['trace'];ref,table=reference_table(trace)
    assertion=next(a for a in q.read(RUN/'shared/model_call/candidate.json') if a['label']=='keep_never_zero_when_valid')
    early=next(r for r in fixed['obligation_evaluation']['before']['alarms'] if r['category']=='early_detection');anchor=early['cycle'];end=early['transaction']['transfer_cycle']
    check('nonhandshake not pass',all(not table[anchor][ob]['applicable'] and table[anchor][ob]['verdict'] is None for ob in KEEP))
    controls=[]
    def unknown_case(name,values,prop=assertion,own=True):
        r,t=reference_table(values);v=alarm_verdict(r,t,anchor,prop,own)
        check(name,v['category']=='unknown');controls.append(dict(name=name,origin='synthetic_classifier_unit_test_not_native',result=v))
    unknown_case('no own trigger cannot borrow another assertion',trace,own=False)
    unknown_case('trace truncation rejects',copy.deepcopy(trace[:end]))
    v=copy.deepcopy(trace[:anchor+2]);v[-1]['rst']=1;unknown_case('reset cancels early witness',v)
    v=copy.deepcopy(trace);v[anchor+1]['md']^=1;unknown_case('unstable payload rejects',v)
    v=copy.deepcopy(trace);v[anchor+1]['mv']=0;unknown_case('valid withdrawal rejects',v)
    v=copy.deepcopy(trace);v.pop(anchor+1);unknown_case('missing sample rejects',v)
    wrong=copy.deepcopy(assertion);wrong['obligations']=['stall_valid']
    unknown_case('wrong obligation cannot borrow first-presentation target',trace,wrong)
    # Reference unknown explicitly overrides absence of alarms.
    t=copy.deepcopy(table);t[anchor]['final_nonempty']=state(True,'unknown','synthetic_unresolved_reference')
    check('applicable unknown is not pass',alarm_verdict(ref,t,anchor,assertion,True)['category']=='unknown')
    # Wrong mappings cannot buy target detection in the complete gate.
    raw_candidate=q.read(RUN/'shared/model_call/candidate.json');bad=copy.deepcopy(raw_candidate)
    for a in bad:
        if 'keep' in a['label']:a['obligations']=['stall_valid']
    legacy=legacy_measure(raw_candidate,RUN/'shared/native',scenarios,protected)
    records={rev:q.read(RUN/'shared/native'/rev/'result.json') for rev in ('before','after')}
    bad_ev=judge(bad,legacy,records,scenarios,protected)
    check('wrong mappings reject entire gate',not bad_ev['ordinary'] and bool(bad_ev['public_missed']))
    rec=copy.deepcopy(records)
    rec['before']['triggers']=[t for t in rec['before']['triggers'] if t['id']=='hold_payload']
    missing=judge(raw_candidate,legacy,rec,scenarios,protected)
    check('missing own triggers reject complete gate',not missing['ordinary'] and bool(missing['unknown']))
    check('cancel resets explicit NA',all(not x['applicable'] and x['verdict'] is None for x in table[0].values()))
    q.dump(out/'synthetic_controls.json',controls)
    # Same budget controller, real paths replaced only by labeled existing native fixtures.
    for i,names in enumerate([['replacement','complementary'],['replacement','replacement'],['archived169'],['overbroad'],['interface'],['transport']]):
        backend=LocalBackend(names);path=out/'controller_checks'/str(i);c.execute(out,path,backend);r=q.read(path/'outcome.json')
        check('state path budget '+str(i),len(backend.used)==(2 if i<2 else 1))
        check('no real recovery statistic '+str(i),not r['real_chain_success'] and r['conditional_recovery_denominator']==0)
        check('independent entry only after recovery '+str(i),backend.independent_called==(i==0))
        check('zero local model calls '+str(i),q.read(path/'cost.json')['model_calls']==0)
        if i<2:check('old H retained after first rejection '+str(i),q.read(path/'shared_decision.json')['active_hashes']['H']==c.digest(q.read(out/'initial.json')))
    for measured,o,h,lost,fp,u in itertools.product((False,True),(False,True),(False,True),(0,1),(0,1),(0,1)):
        check('branch '+str((measured,o,h,lost,fp,u)),(c.branch('response_received',measured,o,h,lost,fp,u)=='history_once')==(measured and o and not h and bool(lost or fp) and not u))
    budget=c.Budget();budget.reserve_call('shared',request)
    second=copy.deepcopy(request);second['seed']=16508;budget.reserve_call('recovery',second,'history_once')
    try:budget.reserve_call('recovery',second,'history_once')
    except ValueError:check('third call forbidden',True)
    else:raise AssertionError('third call allowed')
    check('no independent inputs generated',not list(out.rglob('scenarios.json')))
    check('old rejection unmodified',q.sha(RUN/'outcome.json')==old_hash and q.read(RUN/'outcome.json')['status']=='stop_ordinary_rejects')
    q.dump(out/'checks.json',checks)
    q.dump(out/'metrics.json',dict(local_checks=len(checks),actual_model_calls=0,new_native_compiles=0,new_native_executions=0,
        archived_records_reused=10,new_accepted_model_versions=0,new_independent_tests=0,conditional_recovery=dict(numerator=0,denominator=0,rate=None)))
    bindings=q.read(OLD/'code_bindings.json')
    for p in (Path(__file__),Path(audit.__file__),OLD/'seal.json',RUN/'outcome.json',RUN/'shared/model_call/candidate.json'):
        bindings[q.old.rel(p)]=q.sha(p)
    for root in (RUN/'shared/native',c.N):
        for p in root.rglob('*'):
            if p.is_file() and 'obj_dir' not in p.parts:bindings[q.old.rel(p)]=q.sha(p)
    q.dump(out/'code_bindings.json',bindings)
    (out/'SUMMARY.md').write_text(f'''# research172 新义务适用性接受检查

新版本已实现、接入原预算执行控制器并完成本地验证。{len(checks)}项检查通过；模型调用0、原生新增编译/执行0，复用10份已完成原生记录。没有新接受模型版本或独立测试。

## 新规则

分别保存义务是否适用，以及适用时的pass/violation/unknown。不适用或复位取消的verdict为null，不再当作pass。参考判定来自接受字节队列、实际握手和上一周期背压；断言仍由原生SVA执行。

原生失败按该性质映射的义务逐项归因：适用且参考通过才算真正误报；匹配参考违例才算检出；无法判定则拒绝。非握手KEEP报警只有在同一输出不变、无取消、后来实际握手并违反同一义务时才归为提前检出；它不补算缺失的直接目标检出、不新增缺口、不替代必要触发。性质必须有自己的触发记录，不能借其他性质或其他义务的证据。

普通/历史规则共用上述检查；历史规则仍仅额外要求历史目标保护。H/R等价限制保持。真实误报、unknown、目标漏报和触发缺失仍拒绝。

## 本地验证

| 记录/对照 | 新规则本地结果 |
| --- | --- |
| 原部分基线 | 公共8个漏报，仍拒绝 |
| 手写局部替换 | 普通接受、历史拒绝；丢失12个旧检出 |
| 手写互补集合 | 完整规则通过 |
| 过宽断言 | 修复后32个真正误报，仍拒绝 |
| research169旧提案 | 68个提前报警对应16个事务；新规则局部复核兼容，非新模型接受 |
| 取消、截断、丢样本、撤回valid、载荷变化、错义务及缺自身触发 | 拒绝或unknown，不被提前归因掩盖 |

research169原拒绝及活动版本保持不变；本地旧提案复核是用于修正判定器的开发对照，不能追认为真实成功或机制增量。条件恢复仍0/0、不可估计。

## 新封存协议

公共请求只更新接受规则说明；模型、采样、初始候选、参数接口和开发信息保持原样，未加入旧成功提案或独立数据。仍最多2次：共享新提案1次，仅普通接受/历史拒绝且确认退化无unknown才恢复1次；无重试、无机会即停、不扩种子。恢复完整通过后才冻结并生成32个新独立场景。没有本轮真实调用授权，不转用旧余额。

本次修改依据已观察的research169开发失败，因此未来验证必须使用新真实提案；不能把这次局部复核当作前瞻效果。已使用的开发场景保持排除，旧独立数据未读取。

复核命令（无模型调用）：
```powershell
wsl -- python3 scripts/research172_applicability_gate.py verify --prepared {q.old.rel(out)}
```
''',encoding='utf-8')
    s.seal_files(out);c.verify(out);s.c.verify(OLD)
    print('SEALED172',len(checks),'checks; model0; old rejection preserved',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','verify','run'])
    for name in ('prepared','out','authorization'):ap.add_argument('--'+name,type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='verify':c.verify(a.prepared.resolve());s.c.verify(OLD);print('VERIFIED172; no model')
    else:c.run(a.prepared.resolve(),a.out.resolve(),a.authorization.resolve())
