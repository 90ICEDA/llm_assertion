"""Audit research67 preparation and research61/62 pairing without model calls."""
import argparse
import json
from pathlib import Path
import research67_controlled_campaign as run
import research67_preflight as preflight
import research66_paired_audit as retrospective
import research64_native_audit as native_audit


def audit(root,out):
    out.mkdir(parents=True,exist_ok=False)
    run.verify(root)
    checks=[]
    def check(label,value):
        assert value,label
        checks.append(label)
    old=run.ROOT/'deliverables/research66_paired_audit_20261024_r01'
    retrospective.verify(old)
    proposed=retrospective.ROOTS[0]/'v0'
    result=retrospective.ordinary(
        run.read(proposed/'alignment/result.json'),run.read(proposed/'alignment/alignment_gate.json'),
        run.read(proposed/'search/result.json'),run.read(proposed/'all_property_guard.json')['search'],
        novel=run.read(proposed/'model_call/novelty.json')['accepted'])
    check('research61 R0 recalculated',result==run.read(old/'paired_decisions.json')['R0'])
    check('research61 actual reject',not run.read(proposed/'decision.json')['accepted'])
    full=retrospective.aggregate(run.read(proposed/'history/result.json'),run.read(proposed/'search/result.json'))
    info=retrospective.old.acceptance.inspect(full['ledger'])
    base=retrospective.old.acceptance.inspect(run.read(retrospective.P/'baseline_full.json')['ledger'])
    check('636 new legal false alarms',len(info['false_positives']-base['false_positives'])==636)
    check('no target protection lost by rejected proposal',not(base['detections']-info['detections']))
    check('final690 retained',run.read(old/'final_repair.json')['protection']['counts']['detections']==690)
    check('not a uniformly budgeted historical experiment',run.read(old/'budget.json')['prospective_common_cap'] is None)
    search=root/'search'/f's{run.PILOT}'
    native_audit.audit(search,out/'native_records')
    run.summarize_search(search)
    check('public registry unchanged',run.search.digest(search/'public_feedback.json')==run.read(search/'public_freeze.json')['sha256'])
    prep=root/'prepared_v4'/f's{run.PILOT}'
    qualified=run.read(prep/'qualification.json')
    for p,h in run.read(prep/'sealed.json').items():check('prepared hash '+p,run.search.digest(prep/p)==h)
    check('qualification passed',qualified['passed'])
    a=run.read(prep/'ordinary/request.preview.json');b=run.read(prep/'search/request.preview.json')
    aa=json.loads(a['messages'][1]['content']);bb=json.loads(b['messages'][1]['content'])
    for key in ('rtl_and_common_contract','confirmed_obligations','current_assertions','output_schema','temporal_semantics','ordinary_observations'):
        check('shared helper '+key,aa[key]==bb[key])
    for c in run.read(prep/'search_cases.json'):check('search evidence excluded from ordinary '+c['id'],c['id'] not in json.dumps(a))
    current=run.read(prep/'shared_initial.json');target=run.read(prep/'core/native/search/result.json')
    keep=dict(operation='keep',assertion_id='',assertions=[],reason='Audit fixture only, not a model response')
    check('real missed evidence rejects keep',not run.paired.current_decision(target,target,keep)['accepted'])
    # Exercise durable refusal with real candidate identities, but no false claim
    # that this fixture is an experimental model proposal or an accepted repair.
    peer=run.read(root/'candidates/valid.json')
    refusal=dict(accepted=False,reasons=[dict(kind='audit_fixture_not_model_result')])
    retained=run.journal(out/'journal_fixture',current,peer,refusal)
    check('refused active version retains prior bytes',retained==current)
    check('refused active hash persisted',run.read(out/'journal_fixture/active_transition.json')['active_hash']==run.loop.sha(current))
    # Call the real guarded entry point with an invalid zero-call grant. It must
    # fail before model construction, credential access or run directory creation.
    grant=out/'invalid_grant_fixture.json';run.dump(grant,dict(authorized_calls=0,purpose='research67_pilot'))
    check('pilot has not started',not (root/'pilot_run').exists())
    try:preflight.pilot(root,grant)
    except AssertionError:check('zero grant denied',not (root/'pilot_run').exists())
    else:raise AssertionError('unauthorized_model_entry')
    try:run.run_search(root,run.SEEDS[0])
    except (AssertionError,FileNotFoundError,TypeError):check('multiseed denied before pilot pass',not (root/'search'/f's{run.SEEDS[0]}').exists())
    else:raise AssertionError('multiseed_before_pilot')
    check('research63 bytes unchanged',run.protected()==run.read(root/'protected_research63.json'))
    run.verify(root)
    run.dump(out/'audit.json',dict(passed=True,checks=checks,new_model_calls=0,new_native_calls=0,
        source_sha256=run.search.digest(Path(__file__)),native_audit='native_records/audit.json',
        limits='Decision/journal fixtures test implementation only. research61 pairing remains retrospective. No new model, accepted proposal, or independent result is inferred.'))
    report(root,out)
    print('AUDIT',len(checks),flush=True)


def report(root,out):
    search=root/'search'/f's{run.PILOT}';s=run.read(search/'summary.json');q=run.read(root/'prepared_v4'/f's{run.PILOT}'/'qualification.json')
    cost=run.read(search/'cost.json')['total'];native=run.read(out/'native_records/audit.json')
    rows=['# research67：受控验证准备与先导搜索实跑','',
        'research61→62的回顾性配对结论复核成立：相同提案按R0接受，增加历史合法事务后因636条新误报拒绝。历史完整绝对检查同样会拒绝；不能把三个拒绝理由计为三份收益。旧版本仅保留270个BRANCH检出；research62后来修复690个目标，但没有统一预设预算。', '',
        '|任务|状态|','|---|---|',
        '|配对接受决定复核|已重算，仍为回顾性分析|',
        '|公共辅助、搜索、四组、两种估计目标及条件种子协议|执行前已封存|',
        '|先导种子搜索与有效见证资格|本地原生实跑完成|',
        '|真实模型先导及冻结后独立验收|尚未调用；需要新的最多3次先导授权|',
        '|多种子共享提案配对决定|先导通过后才执行，尚未运行|',
        '|多轮独立四组策略轨迹|尚未运行，不能用共享提案结果替代|',
        '|各组新冻结测试|尚无本轮新模型版本，未启动|','',
        '所有组固定同一模型配置、AST组件替换接口、公共规格和原生周期门控；模型周期计划均关闭，不提供旧成功计划。仅搜索证据与历史回放开关不同。先导最多3次；后续共享提案最多6次、多轮独立最多24次，须另授权，未自动沿用旧额度。', '',
        '|搜索方法|公共外去重缺口|重复动作|无新增查询|关键unknown|后续归因unknown|','|---|---:|---:|---:|---:|---:|']
    for m,v in s['methods'].items():rows.append(f"|{m}|{len(v['keys'])}|{v['repeated_actions']}|{v['zero_new_queries']}|{v['unknown']}|{v['later_attribution_unknown']}|")
    rows+=['',f"契约搜索相对所有对照并集的额外缺口：{len(s['contract_extra_vs_all'])}。固定种子{run.PILOT}、每方法4查询；已知人工FIFO故障、Depth4/Pipeline1，只是一项开发性先导比较。历史已知与公共之外的新暴露分别标记，不声称发现新历史Bug或稳定收益。",'',
        f"搜索实际原生编译/执行：{cost['native_compile_calls']}/{cost['native_execute_calls']}；原生日志复算{native['native_replays_verified']}份。逐次参考模型/采样/配对判定计时见search/s6703/reference_costs.json；审计额外成本单列。本轮模型调用、tokens和形式化查询均0。资格回放成本不混入搜索查询，见prepared_v2/s6703/cost.json。旧prepared目录的correct路径冲突失败保留；新回放去除重复独立correct案例，每个故障仍实际执行相同correct对照，没有改变搜索或接受规则。",'',
        f"公共回放：{q['common']}；新搜索回放：{q['target']}；按事先规则选入{q['selected_gaps']}个不同机制的有效见证。每个见证有合法性、同输入前后义务判断、触发分类及原生来源。",'',
        'research63 r02仅逐文件计算字节哈希以验证保留，没有读取其测试内容或结果来调参、选候选或生成请求。新独立输入尚未生成；若未来使用测试失败改进，必须整批转开发并另立冻结测试。', '',
        '先导执行器已具备真实请求、重复提案拒绝、可见证据门控、105场景历史回放及逐轮active版本记录。日志夹具检查不计为真实修复或回滚成功。多种子执行仍需先导通过、后续入口集成/验收及独立额度，不能将封存协议表述为完成实验。', '',
        '可复核命令（新审计目录）：','```powershell',
        'wsl -- python3 scripts/research67_audit.py --run '+str(root.relative_to(run.ROOT)).replace('\\','/')+' --out deliverables/research67_audit_NEW','```','',
        '下一步：授权后运行已封存的先导请求；只有新版本通过目标、历史和新独立验收，才开展固定三种子的配对决定及独立多轮实验。先导失败原样报告并停止，不换种子或拿独立失败回喂本协议。']
    (out/'SUMMARY.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.run.resolve(),a.out.resolve())
