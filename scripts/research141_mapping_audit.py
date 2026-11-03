"""Read-only audit of the sealed local mapping qualification and provenance."""
import argparse
import copy
import json
from pathlib import Path
import research140_mapping_qualification as q

m, p = q.m, q.p
read, dump, digest, rel = q.read, q.dump, q.digest, q.rel


def audit(prep, run, out):
    opened = p.q.guard(); q.verify(prep)
    out.mkdir(parents=True, exist_ok=False)
    checks = []
    def check(name, ok):
        assert ok, name
        checks.append(name)
    for name, sha in read(run/'sealed.json').items():
        check('run_hash/'+name, digest(run/name) == sha)
    check('native_qualification_passed', read(run/'outcome.json')['passed'])
    check('no_remote_calls', not list(run.rglob('attempt.json')) and read(run/'cost.json')['model_calls'] == 0)
    check('no_heldout', not list(run.rglob('independent_cases.json')))
    initial = read(q.PREVIOUS/'initial.json')
    baseline_folder = p.QUAL/'native_controls/baseline/native'
    records = {k:read(baseline_folder/k/'result.json') for k in ('alignment','search','history')}
    check('executable_builder_matches_sealed_preview', m.request(initial, records, baseline_folder, False, 0) == read(prep/'request.preview.json'))
    bindings = []
    for name in read(prep/'protocol.json')['native_cases']:
        folder = run/name/'native'
        candidate = read(run/name/'candidate.json')
        check(name+'/model_expressions_preserved', candidate == m.adapt(read(prep/'fixtures'/name/'edit.json')))
        detail = read(folder/'assertion_evidence_mapping.json')
        recs = {k:read(folder/k/'result.json') for k in ('alignment','search','history')}
        for ob in (m.BRANCH,m.OP):
            check(name+'/'+ob+'/all_assertions_mapped', set(detail[ob]) == m.ids(candidate,ob))
            for ident, observed in detail[ob].items():
                entries = [(r,a) for rec in recs.values() for r in rec['ledger'] if r['obligation']==ob
                           for a in r['native']['assertions'] if a['id']==ident]
                actual = dict(trigger_evidence=sorted({r['evidence_id'] for r,a in entries if a['trigger']}),
                              violation_evidence=sorted({r['evidence_id'] for r,a in entries if a['causal_detection']}))
                check(name+'/'+ob+'/'+ident+'/actual_evidence', observed==actual)
                bindings.append(dict(case=name,obligation=ob,assertion=ident,
                                     triggers=len(actual['trigger_evidence']), detections=len(actual['violation_evidence'])))
        # Preserve info isolation in the shared feedback builder for arbitrary
        # order, including the public-accept/history-reject local fixture.
        for history in (False, True):
            req = m.request(candidate,recs,folder,history,int(history))
            body = json.loads(req['messages'][1]['content'])
            check(name+'/request_labels/'+str(history), body['current_assertions']==[
                {k:a[k] for k in p.q.FIELDS} for a in candidate['assertions']])
            check(name+'/visible_cohorts/'+str(history), set(body['actual_feedback']['visible_counts'])==
                  ({'alignment','search','history'} if history else {'alignment','search'}))
        bad = copy.deepcopy(candidate)
        bad['assertions'][1]['id'] = bad['assertions'][0]['id']
        try: m.ids(bad,m.OP)
        except ValueError: check(name+'/duplicate_id_rejected',True)
        else: raise AssertionError('duplicate id passed')
    check('archived_edit_unchanged', read(prep/'fixtures/archived136_exact/edit.json') ==
          read(q.FAILED/'shared/v0/model_call/model_edit.json'))
    check('research136_still_interface_failure', read(q.FAILED/'outcome.json')['status']=='stop_interface_or_repeat'
          and not (q.FAILED/'shared/v0/native').exists())
    cost=read(run/'cost.json'); result=read(run/'results.json')
    dump(out/'mapping_matrix.json',bindings)
    dump(out/'audit.json',dict(passed=True,checks=len(checks),model_calls=0,native_calls=0,
         source_qualification_native_calls=cost['native_executions'],new_model_acceptances=0,new_independent_tests=0,
         archived136_retrospective_decisions=result['archived136_exact']['O_H'],research136_unchanged=True,
         applicability='Local original decoder development evidence, 2–6 properties, same/next-sample frontend; native split controls are same-sample. No new model success or independent generalization claim.'))
    dump(out/'checks.json', checks); dump(out/'read_audit.json',sorted(opened))
    dump(out/'source_bindings.json',{rel(f):digest(f) for f in [Path(__file__),prep/'sealed.json',run/'sealed.json']})
    # A small summary belongs with the audited experiment, not a new model run.
    text = ['# 多条性质义务映射：最终本地审计','',
            '根因：原始通用组装器与账本支持一项义务对应多条性质；早期固定BRANCH组件的局部门控把a0以外都当作OP。research135/136的槽位限制是该历史实现的兼容约束，不是SVA语义要求。',
            '新research139适配器允许任意顺序、每项义务多条性质；首/保持周期门控按声明义务绑定ID。两项义务须齐备、总2–6条、单条单义务。表达式和时序不由程序改写；所有原生失败仍经独立解码与全性质误报审查。','',
            '|验证|结果|','|---|---|',
            '|拆分、OP置首、重复性质|三组均O/H通过，完整151事务690/690，误报/漏报/关键unknown为0；证据集合相同|',
            '|缺失BRANCH保持、错误标签、额外合法误报|全部拒绝|',
            '|历史退化对照|O通过/H拒绝，丢失141个旧检出；仍是本地夹具|',
            f"|research136原响应原样回放|回顾性O/H={result['archived136_exact']['O_H']}，检出{result['archived136_exact']['detections']}/690；不改旧失败、不算新模型成功|",'',
            f"准备49项检查；原生执行核查{read(run/'outcome.json')['checks']}项，复核{read(run/'outcome.json')['native_rows_reaudited']}条记录；本次只读审计{len(checks)}项。实际48次编译及48次仿真，模型调用0，形式化0，独立测试0。",'',
            '接口、请求预览、正负对照和本地协议已在运行前封存，结果另行封存。请求构造已对全部排列/失效对照验证当前断言不丢失、公共/历史信息隔离。旧research136文件哈希不变，research133未读取。',
            '下一步若开展远程试验，应将新接口、门控和审计入口共同接入新的固定预算控制器并另行封存。当前仅完成本地接口资格；不自动使用旧剩余额度，不将回顾性通过算作前瞻恢复或机制增量。','',
            '复核命令（无模型和原生新调用，输出目录须不存在）：','```powershell',
            f'wsl -- python3 scripts/research141_mapping_audit.py --prepared {rel(prep)} --run {rel(run)} --out deliverables/research141_recheck', '```']
    (out/'SUMMARY.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    q.verify(prep)
    dump(out/'sealed.json',{f.relative_to(out).as_posix():digest(f) for f in out.rglob('*') if f.is_file()})
    print('AUDIT141',len(checks),'passed;model0;native0',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','run','out'): parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args();audit(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
