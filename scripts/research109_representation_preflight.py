"""Atomic edit correctness, equal-information checks and native qualification."""
import argparse
import copy
import json
from pathlib import Path
import research108_generation_representation as pilot
from research88_cross_parent_audit import inspect_version
from research93_remote_recovery_audit import response

p,x,rep,r=pilot.p,pilot.x,pilot.rep,pilot.r
ROOT,read,dump,sha=pilot.ROOT,pilot.read,pilot.dump,pilot.sha


def run(prep,out):
    pilot.verify(prep);checks=[]
    def check(name,value):
        assert value,name
        checks.append(name)
    def rejects(name,fn):
        try:fn()
        except (ValueError,KeyError,AssertionError,TypeError):checks.append(name)
        else:raise AssertionError(name)
    initial=read(prep/'initial.json');current=read(prep/'proposal.json');original=copy.deepcopy(current)
    text,raw=response(r.VERSION/'model_call');edit=read(r.VERSION/'model_call/model_edit.json')
    check('initial_failed_proposal_real_model_origin',json.loads(text)==edit and p.prior.p.TEXT_ADAPT(edit,initial)[0]==current)
    rows,ev,records=inspect_version(r.VERSION/'native',current,read(prep/'baseline_full.json'))
    check('current_rejected_not_active_accepted',not ev['history']['accepted'])
    check('fixed_full_target_denominator',sum(records[c]['counts']['detections'] for c in ('history','search'))==690)
    properties=[{k:a[k] for k in rep.FIELDS} for a in current['assertions'][1:]]
    ids=[a['id'] for a in current['assertions'][1:]]
    def pack(actions):return dict(operation='edit_op_set',reason='LOCAL INTERFACE TEST ONLY; never sent to model',edits=actions)
    def equivalent(name,actions,expected):
        before=copy.deepcopy(current);value=pack(actions)
        result,mapping=rep.adapt(value,current,initial)
        full=p.prior.p.TEXT_ADAPT(dict(operation='replace_op',reason=value['reason'],assertions=expected),initial)[0]
        check(name+'_same_executable_candidate',result==full)
        check(name+'_branch_unchanged',result['assertions'][0]==initial['assertions'][0])
        check(name+'_input_unmodified',current==before)
        check(name+'_mapping_predicates_exact',mapping['expanded_model_edit']['assertions']==expected)
        return result
    c=equivalent('empty_edit_keeps_all',[],properties);check('empty_edit_detected_by_existing_repeat_rule',x.signature(c)==x.signature(current))
    equivalent('explicit_keep',[dict(action='keep',op_id=i) for i in ids],properties)
    for idx,op_id in enumerate(ids):
        # Both possible removals tested equally; no preferred edit in requests.
        equivalent('remove_'+op_id,[dict(action='remove',op_id=op_id)],[a for j,a in enumerate(properties) if j!=idx])
        for bit in (0,7,19,31):
            prop=dict(antecedent=f'instr[{bit}]',consequent='illegal_insn',timing='same_sample',obligations=['op_bit28_illegal'])
            expected=copy.deepcopy(properties);expected[idx]=prop
            equivalent(f'replace_{op_id}_bit{bit}',[dict(action='replace',op_id=op_id,assertion=prop)],expected)
    extra=dict(antecedent='instr_new',consequent='illegal_insn',timing='next_sample',obligations=['op_bit28_illegal'])
    equivalent('add_owned_predicate',[dict(action='add',assertion=extra)],properties+[extra])
    for count in (1,2,3):
        target=[dict(antecedent=f'instr[{j+2}]',consequent='illegal_insn',timing='same_sample',obligations=['op_bit28_illegal']) for j in range(count)]
        equivalent(f'full_set_expressibility_{count}',[dict(action='remove',op_id=i) for i in ids]+[dict(action='add',assertion=a) for a in target],target)
    # Atomic targeting references the input snapshot; earlier removes never shift IDs.
    equivalent('stable_ids_remove_then_replace',[dict(action='remove',op_id=ids[0]),dict(action='replace',op_id=ids[1],assertion=extra)],[extra])
    bad_actions=[('branch_edit',[dict(action='remove',op_id='a0')]),('unknown_id',[dict(action='keep',op_id='missing')]),
        ('duplicate_target',[dict(action='keep',op_id=ids[0]),dict(action='remove',op_id=ids[0])]),
        ('wrong_action',[dict(action='erase',op_id=ids[0])]),('extra_field',[dict(action='remove',op_id=ids[0],property='injected')]),
        ('remove_all',[dict(action='remove',op_id=i) for i in ids]),
        ('too_many_properties',[dict(action='add',assertion=extra),dict(action='add',assertion=extra)]),
        ('nonstring_id',[dict(action='remove',op_id=[ids[0]])]),
        ('invalid_late_action',[dict(action='remove',op_id=ids[0]),dict(action='remove',op_id='a0')])]
    for name,actions in bad_actions:
        rejects(name,lambda actions=actions:rep.adapt(pack(actions),current,initial))
        check(name+'_no_partial_mutation',current==original)
    for name,mutation in [('wrong_timing',lambda a:a.__setitem__('timing','eventually')),
        ('branch_obligation',lambda a:a.__setitem__('obligations',['illegal_branch_persists'])),
        ('extra_property',lambda a:a.__setitem__('property','invented')),
        ('unknown_signal',lambda a:a.__setitem__('antecedent','not_a_signal'))]:
        bad=copy.deepcopy(extra);mutation(bad)
        rejects(name,lambda bad=bad:rep.adapt(pack([dict(action='replace',op_id=ids[0],assertion=bad)]),current,initial))
    req={a:rep.request(current,records,r.VERSION/'native',a,0) for a in pilot.ARMS}
    bodies={a:json.loads(q['messages'][1]['content']) for a,q in req.items()}
    for a in pilot.ARMS:
        check('sealed_request_'+a,req[a]==read(prep/a/'request.preview.json'))
        check('reservation_'+a,sum(len(m['content'].encode()) for m in req[a]['messages'])+2048+req[a]['max_tokens']<=45000)
        check('no_answer_or_test_reference_'+a,not any(s in json.dumps(req[a]) for s in ('research93','research92_real','independent_cases','LOCAL INTERFACE TEST')))
    for key in bodies['C']:
        if key!='output_contract':check('same_information_'+key,bodies['C'][key]==bodies['E'][key])
    check('same_system_message',req['C']['messages'][0]==req['E']['messages'][0])
    check('same_model_seed_sampling',{k:v for k,v in req['C'].items() if k!='messages'}=={k:v for k,v in req['E'].items() if k!='messages'})
    check('no_selected_action_in_prompt','edits' not in bodies['E'] and isinstance(bodies['E']['output_contract']['edits'],str))
    # Existing native controls verify that the experiment has not weakened the gate.
    for name,expected in [('positive',True),('known_overbroad',False)]:
        f=r.old.SOURCE/'controls'/name;c=read(f/'candidate.json')
        n,ce,_=inspect_version(f/'native',c,read(prep/'baseline_full.json'));rows+=n
        check(name+'_original_native_decision',ce['history']['accepted']==expected)
    dummy=ROOT/'deliverables/research108_AUTH_TEST_NOT_RUN'
    grant=dict(purpose='research108_representation_pilot',authorized_calls=4,endpoint=p.prior.transport.DEFAULT_URL,model=p.prior.transport.DEFAULT_MODEL,
        prepared_sha256=sha(prep/'sealed.json'),run_output=dummy.relative_to(ROOT).as_posix())
    pilot.grant_check(grant,prep,dummy)
    for key,value in [('purpose','research104_temporal_recovery'),('authorized_calls',2),('prepared_sha256','wrong')]:
        bad=copy.deepcopy(grant);bad[key]=value
        rejects('grant_'+key,lambda bad=bad:pilot.grant_check(bad,prep,dummy))
    check('no_fake_run_created',not dummy.exists())
    check('research100_104_unchanged',pilot.protected_failures()==read(prep/'protected_failures.json'))
    pilot.verify(prep);out.mkdir(parents=True,exist_ok=False)
    dump(out/'preflight.json',dict(passed=True,checks=checks,count=len(checks),native_rows_recomputed=rows,
        new_model_calls=0,new_native_calls=0,all_edit_fixtures_local_only=True,script_sha256=sha(Path(__file__))))
    (out/'SUMMARY.md').write_text('\n'.join([
        '# research107–109：替代生成表示的封存先导','',
        f'{len(checks)}项本地检查通过；复核{rows}条既有原生日志。没有新模型调用或原生执行。旧research100/104失败的请求、响应、成本和结果哈希均保持不变。', '',
        '选择的唯一替代变量是生成表示：C生成完整OP集合；E由模型选择keep/remove/replace/add。保留的性质来自既有真实模型版本；新表达式/动作来自新的真实响应。程序只执行原子编辑并复用原前端，不选择删除目标、不改位号、不代写后件/时序。',
        'C/E初始请求除output_contract外的正文完全相同；系统、模型、采样、失败候选、组件标识、开发时序证据与原生接受标准均相同。E支持C所支持的任意1..3条OP集合，BRANCH同样不可修改。语法/接口失败照实计入预算，不把编辑表示产生的错误豁免。', '',
        '本地测试覆盖两种删除、保留、替换、增加、完整集合表达等价、错ID/重复ID/BRANCH修改/错误字段拒绝和原子性。所有测试动作仅在本地，不进入模型提示，不算模型成功。', '',
        '|项目|封存规则|','|---|---|',
        '|真实预算|C/E各最多2次，共最多4次；不挪用|',
        '|模型|同Highway/Qwen72B；种子10807/10808，temperature0.2，输出1024|',
        '|顺序|C0、E0、各自被拒绝后最多一次细化|',
        '|验收|current9与完整151，420 OP＋270 BRANCH、无合法误报/关键unknown、必要触发及历史门控|',
        '|停止|接受即停；传输失败全局停止；无重试、无新种子|',
        '|独立测试|全部终态冻结后，有新接受版本才生成96新指令、四配置并回放两组|',
        '|路线资格|E必须完整接受且新独立通过；否则停止。通过也不自动启动机制比较|', '',
        '这是已选定案例的公共生成能力验证，不是两个核心创新的收益实验，也不是多种子稳定性结论。', '',
        '本地复核：','```powershell',f'wsl -- python3 scripts/research109_representation_preflight.py --prepared {prep.relative_to(ROOT).as_posix()} --out deliverables/research109_preflight_NEW','```', '',
        '获新用途预算授权后执行：','```powershell',f'wsl -- python3 scripts/research108_generation_representation.py run --prepared {prep.relative_to(ROOT).as_posix()} --out deliverables/research108_real_20261025_r01 --authorization deliverables/research108_authorization_20261025_r01.json','```'])+'\n',encoding='utf-8')
    print('PREFLIGHT109',dict(checks=len(checks),native_rows=rows,new_calls=0),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--prepared',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.out.resolve())
