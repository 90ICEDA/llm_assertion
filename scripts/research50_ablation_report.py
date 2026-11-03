"""Audit50 with the corrected interface and explicit changed-proposal denominator."""
import argparse
import json
from pathlib import Path
import shutil
import research43_report as reusable
import research50_controlled_ablation as campaign

read,dump=campaign.read,campaign.dump


def report(run,out):
    original=campaign.base.assemble
    campaign.base.assemble=campaign.interface.assemble
    try:reusable.report(run,out)
    finally:campaign.base.assemble=original
    shutil.copy2(out/'SUMMARY.md',out/'reused_audit_summary.md')
    result=read(out/'results.json');prep=campaign.base.gate.portable(read(run/'prepared_source.json')['path'])
    checks=[]
    def check(name,value):checks.append(dict(name=name,passed=bool(value)));assert value,name
    check('correct_protocol',read(run/'protocol.json')==read(prep/'protocol.json'))
    for name,h in read(prep/'prepared_hashes.json').items():check('sealed:'+name,campaign.base.digest(prep/name)==h)
    for name,h in read(prep/'source_snapshot/hashes.json').items():check('executed_source:'+name,campaign.base.digest(run/'source_snapshot'/name)==h)
    changed_eligible=[];keep_eligible=[];concrete_benefits=[];unusable=[]
    for seed in campaign.base.SEEDS:
        for stream in ('ordinary','search'):
            key=f'{seed}/{stream}';folder=run/f's{seed}/{stream}'
            pair=read(folder/'pair_result.json');request=read(folder/'model_call/request.json')
            edit=read(folder/'model_call/model_edit.json') if (folder/'model_call/model_edit.json').exists() else None
            candidate=read(folder/'model_call/candidate.json') if (folder/'model_call/candidate.json').exists() else None
            check(key+':new_output_cap',request['max_tokens']==2048)
            check(key+':no_legacy_reason_limit','maxLength' not in json.loads(request['messages'][1]['content'])['output_schema']['properties']['reason'])
            if candidate is None:unusable.append(key)
            if pair['plain']['accepted']:
                (changed_eligible if edit['operation']=='replace_one' else keep_eligible).append(key)
                full=read(folder/'history_native/result.json')
                hist=campaign.base.gate.portable(read(prep/'history_binding.json')['path'])
                losses=reusable.protection_losses(read(hist)['group']['ledger'],full['group']['ledger'],read(folder/'historical_gate.json'))
                if not pair['gated']['accepted'] and any(losses['confirmed'].values()):concrete_benefits.append(key)
    details=dict(changed_current_pass_proposals=changed_eligible,keep_current_pass_proposals=keep_eligible,
        unusable=unusable,confirmed_incremental_gate_rejections=concrete_benefits,
        changed_proposal_benefit_rate=(len(set(concrete_benefits)&set(changed_eligible))/len(changed_eligible) if changed_eligible else None),
        interpretation='Keeps are eligible admission outcomes but provide no exposure to modification-induced regression. No changed current-pass proposal => repair-regression benefit not estimable.',
        scope='Three fixed seeds, paired one-step admission contrasts; not12 independent model samples or a multi-round feedback policy ablation.')
    dump(out/'changed_proposal_estimand.json',details)
    dump(out/'additional_audit.json',dict(passed=True,checks=checks))
    # The reused audit field concerns its legacy43 protocol, not this protocol.
    # Keep original results as audit output and report effective semantics here.
    lines=['# research50：修正接口后的受控四组实验','',
        '复用原生配对审计通过；本轮理由长度不限制可执行语义，旧43结果不追改。原审计中reason_exceeds_declared_limit字段仅对应旧128字符阈值，不能用于本轮拒绝。','',
        '|组|新搜索证据|历史门控|接纳（含keep）/3|接受新修改/3|冻结后有限独立通过/3|','|---|---|---|---:|---:|---:|']
    initial_hash=campaign.loop.sha(read(prep/'shared_initial.json'))
    for name,arm in campaign.base.ARMS.items():
        total=result['totals'][name]
        changed=sum(bool(result['arms'][f's{seed}/{name}']['decision']['accepted']) and
                    result['arms'][f's{seed}/{name}']['decision']['frozen_hash']!=initial_hash
                    for seed in campaign.base.SEEDS)
        lines.append(f'|{name}|{arm["search"]}|{arm["gate"]}|{total["accepted"]}|{changed}|{total["independent_pass"]}|')
    lines+=['',f'当前检查通过且修改性质的真实提案：{len(changed_eligible)}；当前检查通过的keep：{len(keep_eligible)}；有确认保护损失的额外拒绝：{len(concrete_benefits)}。',
        '无合格修改提案时，防退化修复收益不可估计。不能用旧失败提案、研究48的回放拒绝或验证器测试数据填充处理组。',
        '','A/C共享同一普通反馈真实提案，B/D共享同一搜索反馈提案；共6次物理模型调用、12个逻辑组结果。各组同初始集合、规格和模型参数；搜索证据仅B/D可见。',
        '全部组先冻结，再生成公共新独立批次。相同候选哈希共享一次实际执行，不扩大样本量；无新接受版本也保留其初始集合的测试失败。',
        '','搜索比较沿用research42固定候选对、3种子与相同查询预算的完整结果：契约未显示超过分歧、差分或固定覆盖对照的收益。不能将单种子相对随机补测的收益推广成契约特有优势。',
        '','这是单轮配对决策实验。多轮自适应反馈策略的完整消融仍需另做；三个模型请求种子不证明服务侧采样完全可复现。',
        '','物理成本见cost.json；各搜索臂逻辑计4查询/24原生执行，6次调用全计费；105历史回放对C/D是处理成本，对A/B是冻结后测量成本。独立测试全部是测量成本。',
        '','```json',json.dumps(result['cost'],ensure_ascii=False,indent=2),'```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    shutil.copy2(Path(__file__),out/'effective_audit_source.py')
    print('CONTROLLED_AUDIT',len(checks),'changed_eligible',len(changed_eligible),'concrete_gate_rejections',len(concrete_benefits),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();report(a.run.resolve(),a.out.resolve())
