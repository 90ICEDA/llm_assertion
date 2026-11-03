"""Read-only audit of research108's actual four repeated-proposal failures.

This auditor deliberately requires the observed failure path; it does not claim
to validate unexecuted acceptance or holdout branches.
"""
import argparse
import json
from pathlib import Path
import research108_generation_representation as run108
from research93_remote_recovery_audit import response
from research88_cross_parent_audit import inspect_version

p,x,rep,r=run108.p,run108.x,run108.rep,run108.r
ROOT,read,dump,sha=run108.ROOT,run108.read,run108.dump,run108.sha


def run(prep,trial,out):
    run108.verify(prep);run108.grant_check(read(trial/'authorization.json'),prep,trial)
    initial=read(prep/'initial.json');proposal=read(prep/'proposal.json');base=read(prep/'baseline_full.json')
    rows,ev,rec=inspect_version(r.VERSION/'native',proposal,base)
    assert not ev['history']['accepted']
    assert sum(rec[c]['counts']['detections'] for c in ('history','search'))==690
    assert sum(rec[c]['counts']['false_positives'] for c in ('history','search'))==104
    ledger=read(trial/'budget_ledger.json')
    assert [(v['arm'],v['iteration']) for v in ledger]==[('C',0),('E',0),('C',1),('E',1)]
    diagnostics={a:None for a in run108.ARMS};versions=[];calls=[]
    costs={a:dict(calls=0,prompt_tokens=0,completion_tokens=0,wall_seconds=0) for a in run108.ARMS}
    for entry in ledger:
        arm,i=entry['arm'],entry['iteration'];folder=trial/arm/f'v{i}';mf=folder/'model_call'
        req=read(mf/'request.json')
        assert req==rep.request(proposal,rec,r.VERSION/'native',arm,i,diagnostics[arm])
        if i==0:assert req==read(prep/arm/'request.preview.json')
        assert entry['request_sha256']==x.old.acceptance.sha(req)
        assert entry['reservation']==sum(len(m['content'].encode()) for m in req['messages'])+2048+req['max_tokens']<=45000
        text,raw=response(mf);value=read(mf/'model_edit.json');call=read(mf/'result.json');calls.append(call)
        assert raw['complete'] and json.loads(text)==value and call['status']=='response_received' and call['retries']==0
        if arm=='C':candidate,_=p.prior.p.TEXT_ADAPT(value,initial);mapping=None
        else:
            candidate,mapping=rep.adapt(value,proposal,initial)
            assert mapping==read(mf/'edit_mapping.json')
            assert mapping['actions']==value['edits']
            assert all(edit['action']=='replace' for edit in value['edits'])
            by_id={a['id']:a for a in proposal['assertions']}
            for edit in value['edits']:
                assert edit['assertion']=={k:by_id[edit['op_id']][k] for k in rep.FIELDS}
        assert candidate==read(mf/'candidate.json') and candidate['assertions'][0]==initial['assertions'][0]
        assert (mf/'candidate.sva').read_text().strip()=='\n'.join(a['property'] for a in candidate['assertions'])
        assert x.signature(candidate)==x.signature(proposal)
        assert not (folder/'native').exists()
        tr=read(folder/'transition/transition.json')
        assert tr['reason']==dict(kind='repeated_executable_proposal') and not tr['accepted']
        assert tr['proposal_sha256'] is None and tr['rollback_verified']
        assert read(folder/'transition/before.json')==initial and read(folder/'transition/active.json')==initial
        assert tr['previous_sha256']==tr['active_sha256']==x.old.acceptance.sha(initial)
        diagnostics[arm]=dict(reason=tr['reason'],actual_model_text=text)
        versions.append(dict(arm=arm,iteration=i,raw_response=raw,model_edit=value,
            effective_signature=x.signature(candidate),same_as_failed_initial_proposal=True,
            compiled_new=False,accepted=False,edit_mapping=mapping))
        c=costs[arm];c['calls']+=1
        assert call['prompt_tokens'] is not None and call['completion_tokens'] is not None
        c['prompt_tokens']+=call['prompt_tokens'];c['completion_tokens']+=call['completion_tokens'];c['wall_seconds']+=call['wall_seconds']
    outcome=read(trial/'outcome.json');decision=read(trial/'pilot_decision.json');cost=read(trial/'cost.json')['total']
    assert outcome['actual_calls']==cost['model_calls']==4
    assert outcome['states']=={a:dict(calls=2,accepted=False) for a in run108.ARMS}
    assert outcome['unique_new_accepted_versions']==0 and outcome['independent'] is None and not outcome['transport_stopped']
    assert not outcome['automatic_expansion'] and decision==dict(alternative_passed=False,automatic_expansion=False,status='stop_alternative_route')
    assert cost['native_compile_calls']==cost['native_execute_calls']==cost['compile_smoke_execute_calls']==cost['formal_calls']==0
    assert sum(c['prompt_tokens']+c['completion_tokens'] for c in calls)<=180000
    assert cost['prompt_tokens_total']==sum(v['prompt_tokens'] for v in costs.values())
    assert cost['completion_tokens_total']==sum(v['completion_tokens'] for v in costs.values())
    for a in run108.ARMS:assert read(trial/'terminal'/a/'candidate.json')==initial
    assert read(trial/'terminal_versions.json')=={a:x.old.acceptance.sha(initial) for a in run108.ARMS}
    assert not (trial/'freeze.json').exists() and not (trial/'independent_cases.json').exists()
    run108.verify(prep)
    audit=dict(passed=True,new_model_calls=4,new_accepted_versions=0,new_native_calls=0,independent_executed=False,
        native_rows_recomputed=rows,raw_response_verified=True,atomic_actions_from_real_model=True,
        no_local_action_or_predicate_selection=True,all_four_executable_signatures_repeat=True,
        own_feedback_rebuilt_exactly=True,rollback_verified=True,budget_verified=True,
        research100_104_unchanged=True,alternative_route_stopped=True,no_expansion=True,script_sha256=sha(Path(__file__)))
    out.mkdir(parents=True,exist_ok=False)
    for name,obj in [('audit',audit),('versions',versions),('cost',cost),('cost_by_arm',costs)]:dump(out/f'{name}.json',obj)
    lines=['# research108 / 111：完整集合与原子编辑先导实际结果','',
        '**固定预算4/4次真实调用已结束；新接受版本0，新原生执行0，新独立验收未启动。替代表示路线已停止，不扩种子、不启动后续机制实验。**','',
        '|组|实际调用|模型行为|有效性质改变|完整接受|','|---|---:|---|---|---|',
        '|C 完整集合|2|重复原同周期与下一周期性质|无|否|',
        '|E 原子编辑|2|对a1、a2执行replace，但替换内容与原内容完全相同|无|否|','',
        '四份接口均成功解析；不是格式失败。E动作取自原服务响应，经本地适配器原子执行后与C一样重复旧可执行签名。接口工作不能当作恢复成功。重复检查在编译前拒绝，未浪费新原生执行；没有人工选择删除a2。', '',
        '原失败提案的420 OP＋270 BRANCH检出、104条历史/搜索误报（另有6条current9误报）来自已保存的原生实验，本轮仅重算核验，不能计作本轮新检出。误报原因仍是将起始OP的要求延伸到下一条合法指令。两组回退保留旧部分BRANCH基线，不把这个基线声称为完整保护。','',
        '|组|输入tokens|输出tokens|模型墙钟秒|','|---|---:|---:|---:|']
    for a,c in costs.items():lines.append(f"|{a}|{c['prompt_tokens']}|{c['completion_tokens']}|{c['wall_seconds']:.3f}|")
    lines += ['',f"总输入/输出tokens：{cost['prompt_tokens_total']}/{cost['completion_tokens_total']}。新增原生编译、执行及形式化均0。审计复核{rows}条旧原生记录；不记作新仿真。",'',
        '结论：在这个已选定案例、固定种子和每组两次预算内，原子编辑表示未改善完整恢复。不能推广为所有编辑表示均无效，也没有证据声称两个核心机制产生额外收益。research100/104失败记录和更早成功版本/独立结果保持不变。', '',
        '按预先协议停止本路线。本次不继续追加同模型单字段修正、不自动改用其他模型、不启动前瞻防退化或多种子扩展。','',
        '复核（无模型调用）：','```powershell',
        f'wsl -- python3 scripts/research111_representation_failure_audit.py --prepared {prep.relative_to(ROOT).as_posix()} --run {trial.relative_to(ROOT).as_posix()} --out deliverables/research111_audit_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    trace=['# 真实模型动作与展开结果','']
    for v in versions:
        trace += [f"## {v['arm']}/{v['iteration']}",'','```json',json.dumps(v['model_edit'],ensure_ascii=False,indent=2),'```',
            '执行签名：`'+v['effective_signature']+'`。与旧失败提案一致；编译前拒绝。','']
    (out/'CASE_TRACE.md').write_text('\n'.join(trace)+'\n',encoding='utf-8')
    dump(out/'bindings.json',{f.relative_to(ROOT).as_posix():sha(f) for f in [prep/'sealed.json',trial/'authorization.json',trial/'outcome.json',trial/'pilot_decision.json',trial/'cost.json']})
    print('AUDIT111',audit,flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for n in ('prepared','run','out'):ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
