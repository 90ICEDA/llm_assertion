"""Native-marker qualification and rejection tests for temporal feedback."""
import argparse
import copy
import json
from pathlib import Path
import research104_temporal_recovery as r
from research88_cross_parent_audit import inspect_version

x,p,t=r.x,r.p,r.temporal
ROOT,read,dump,sha=r.ROOT,r.read,r.dump,r.sha


def run(prep,out):
    r.verify(prep);checks=[]
    def check(name,value):
        assert value,name
        checks.append(name)
    def rejects(name,fn):
        try:fn()
        except (ValueError,KeyError,AssertionError):checks.append(name)
        else:raise AssertionError(name)
    candidate=read(prep/'proposal.json');base=read(prep/'baseline_full.json')
    rows,ev,records=inspect_version(r.VERSION/'native',candidate,base)
    check('proposal_failed_original_rules',not ev['history']['accepted'])
    check('all_targets_already_detected',sum(records[c]['counts']['detections'] for c in ('search','history'))==690)
    check('real_legal_false_alarms',sum(records[c]['counts']['false_positives'] for c in ('search','history'))==104)
    ctx=t.context(r.VERSION/'native',candidate,records)
    bound=0;fp_bound=0;unavailable=0
    for cohort,res in records.items():
        for row in res['ledger']:
            for a in row['native']['assertions']:
                if not (a['trigger'] or a['failed']):continue
                e=t.bind(ctx,cohort,row['evidence_id'],a['id']);check_name=f'{cohort}/{row["evidence_id"]}/{a["id"]}'
                assert t.validate(e,ctx),check_name
                bound+=1
                if row['expected']==row['observed']==0 and a['failed']:
                    assert e['check_assertion_failed'] and e['anchor_antecedent_cover']
                    fp_bound+=1
    check('all_exposed_native_events_bound',bound>0 and unavailable==0)
    visible=p.feedback(ev,records,True)
    events=t.selected_events(candidate,records,r.VERSION/'native',visible)
    check('three_cohort_false_alarm_examples',len(events['false_alarm_boundaries'])==3)
    check('first_and_held_positive_controls',{e['check']['phase_name'] for e in events['preserve_first_and_held_controls']}=={'first','held'})
    event=next(e for e in events['false_alarm_boundaries'] if e['cohort']=='alignment')
    check('actual_anchor9_check10',event['anchor']['sample_id']==9 and event['check']['sample_id']==10)
    check('transaction1_to2',event['anchor']['transaction_id']==1 and event['check']['transaction_id']==2 and event['transaction_switched'])
    check('anchor_cover_not_current_cover',event['anchor_antecedent_cover'] and not event['check_cycle_antecedent_cover'] and event['check_assertion_failed'])
    check('legal_check_output_zero',event['check']['actual_illegal']==event['check']['expected_illegal']==0)
    changes=[('anchor_sample',lambda e:e['anchor'].__setitem__('sample_id',10)),
        ('check_sample',lambda e:e['check'].__setitem__('sample_id',9)),
        ('anchor_transaction',lambda e:e['anchor'].__setitem__('transaction_id',2)),
        ('check_transaction',lambda e:e['check'].__setitem__('transaction_id',1)),
        ('switch_boolean',lambda e:e.__setitem__('transaction_switched',False)),
        ('anchor_cover',lambda e:e.__setitem__('anchor_antecedent_cover',False)),
        ('current_cover',lambda e:e.__setitem__('check_cycle_antecedent_cover',True)),
        ('failure',lambda e:e.__setitem__('check_assertion_failed',False)),
        ('output',lambda e:e['check'].__setitem__('actual_illegal',1)),
        ('configuration',lambda e:e['configuration'].__setitem__('RV32E',1-e['configuration']['RV32E'])),
        ('revision',lambda e:e.__setitem__('revision','after' if e['revision']=='before' else 'before')),
        ('missing_anchor',lambda e:e.pop('anchor'))]
    for name,mutate in changes:
        bad=copy.deepcopy(event);mutate(bad)
        rejects(name+'_rejected',lambda bad=bad:t.validate(bad,ctx))
    badctx=copy.deepcopy(ctx)
    rev=event['revision'];name=event['marker_binding']['configuration_label'];cycle=event['anchor']['sample_id']
    badctx['alignment']['markers'][rev]['TRIGGER'].remove((name,cycle))
    rejects('missing_native_anchor_marker_rejected',lambda:t.bind(badctx,'alignment',event['check_evidence_id'],event['assertion_id']))
    badctx=copy.deepcopy(ctx);badctx['alignment']['assertions'][event['assertion_id']]['delay']=0
    rejects('delay_timing_mismatch_rejected',lambda:t.bind(badctx,'alignment',event['check_evidence_id'],event['assertion_id']))
    req=t.request(candidate,records,r.VERSION/'native',0)
    check('sealed_request_exact',req==read(prep/'request.preview.json'))
    body=json.loads(req['messages'][1]['content'])
    check('only_editable_fields',all(set(a)==set(t.fmt.FIELDS) for a in body['current_op']))
    check('no_predicate_changes',body['current_op']==[{k:a[k] for k in t.fmt.FIELDS} for a in candidate['assertions'][1:]])
    check('no_success_or_test_reference',not any(s in json.dumps(req) for s in ('research93','research92_real','frozen/','independent_cases')))
    check('bound_events_exact',body['actual_feedback']['temporal_binding']==events)
    check('first_request_fits_fixed_budget',sum(len(m['content'].encode()) for m in req['messages'])+2048+req['max_tokens']<=40000)
    # Unknown/ordinary failures still keep the fixed invocation ceiling.
    testout=ROOT/'deliverables/research104_AUTH_TEST_NOT_RUN'
    grant=dict(purpose='research104_temporal_recovery',authorized_calls=2,endpoint=p.prior.transport.DEFAULT_URL,
        model=p.prior.transport.DEFAULT_MODEL,prepared_sha256=sha(prep/'sealed.json'),run_output=testout.relative_to(ROOT).as_posix())
    r.grant_check(grant,prep,testout)
    for key,value in [('purpose','research100_presentation_pilot'),('authorized_calls',4),('prepared_sha256','wrong')]:
        bad=copy.deepcopy(grant);bad[key]=value
        rejects('invalid_grant_'+key,lambda bad=bad:r.grant_check(bad,prep,testout))
    check('no_test_remote_run_created',not testout.exists())
    r.verify(prep);out.mkdir(parents=True,exist_ok=False)
    dump(out/'preflight.json',dict(passed=True,count=len(checks),checks=checks,native_rows_recomputed=rows,
        events_bound=bound,false_alarm_events_bound=fp_bound,unknown_bindings=unavailable,
        new_model_calls=0,new_native_calls=0,script_sha256=sha(Path(__file__))))
    dump(out/'selected_boundaries.json',events)
    (out/'SUMMARY.md').write_text('\n'.join([
        '# research103–105：起始采样→检查采样→事务切换反馈','',
        f'{len(checks)}项本地检查通过，复核{rows}条原生记录，绑定{bound}条实际触发/失败事件，其中{fp_bound}条合法误报事件。没有新增模型或原生调用。', '',
        '每条事件按cohort、revision、configuration、evidence_id、assertion_id定位；起始周期=检查周期−性质实际delay。分别核对原生起始TRIGGER、检查ASSERT_FAIL和检查周期自己的cover，不能把延迟触发字段误读为当前前件。事务和指令切换均从原生TRACE核对。', '',
        '示例：sample9/transaction1的OP触发a2；sample10/transaction2已是合法指令，illegal实际及参考均0，但a2仍要求后件为真。sample9 cover=true，sample10当前cover=false，sample10 failure=true。这是明确的跨事务误报。', '',
        '新请求只选各允许开发cohort的一条已有误报，并附实际检出的首周期/保持阶段控制；完整误报总数及151事务验收不缩减。没有自动删除下一周期性质，也没有输出手写正确SVA。', '',
        '固定新预算：最多2次同一Highway/Qwen72B调用，种子10407/10408；无重试，接受或传输失败即停，不扩种子。每版仍须满足420 OP＋270 BRANCH全部检出、无合法误报/关键unknown、必要触发及历史保持。完整接受后才冻结并生成96新指令、四配置独立测试。',
        '这是已观察失败提案的选定恢复实验，不是前瞻随机机制增量对照；research100的失败和预算不追改。真实新调用尚未执行，须另行用途绑定授权。', '',
        '复核（无模型调用）：','```powershell',
        f'wsl -- python3 scripts/research105_temporal_preflight.py --prepared {prep.relative_to(ROOT).as_posix()} --out deliverables/research105_preflight_NEW','```', '',
        '授权后执行：','```powershell',
        f'wsl -- python3 scripts/research104_temporal_recovery.py run --prepared {prep.relative_to(ROOT).as_posix()} --out deliverables/research104_real_20261025_r01 --authorization deliverables/research104_authorization_20261025_r01.json','```'])+'\n',encoding='utf-8')
    print('PREFLIGHT105',dict(checks=len(checks),native_rows=rows,events_bound=bound,false_alarm_events=fp_bound,new_calls=0),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--prepared',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.out.resolve())
