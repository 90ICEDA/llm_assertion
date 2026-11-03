"""Audit paired single-step causal contrasts. No model or simulator calls."""
import argparse
import json
from pathlib import Path
import shutil
import research43_paired_ablation as campaign
import research17_loop as loop
import research31_gate as gate
from research28_report import raw_response
from research35_campaign import join_results
from research29_drain import assess
from research17_report import cost_audit

read,dump=loop.read,loop.dump
digest=campaign.digest


def protection_losses(before,after,verdict):
    """Unknown/missing/changed rows never establish concrete protection loss."""
    old,new=loop.inspect(before),loop.inspect(after)
    confirmed={};unconfirmed={};cache={}
    identity=lambda r:{k:r.get(k) for k in ('obligation','stimulus_sha256','oracle')}
    for reason in verdict['reasons']:
        kind=reason['kind']
        if kind not in ('new_legal_false_positive','lost_target_detection','lost_obligation_trigger'):continue
        for key in reason['evidence_keys']:
            a,b=old['rows'].get(key),new['rows'].get(key)
            okay=bool(a and b and key not in old['unknown']|new['unknown'] and identity(a)==identity(b))
            if okay and kind=='lost_obligation_trigger':
                okay=all(gate.applicability(r,cache)['status']=='required' for r in (a,b))
            (confirmed if okay else unconfirmed).setdefault(kind,[]).append(key)
    return dict(confirmed=confirmed,unconfirmed=unconfirmed)


def report(run,out):
    outcome=read(run/'outcome.json')
    assert outcome['status']=='six_proposals_twelve_paired_arms_completed','Incomplete trial; do not report success.'
    out.mkdir(parents=True,exist_ok=False)
    prep=gate.portable(read(run/'prepared_source.json')['path'])
    initial=read(prep/'shared_initial.json');history=read(prep/'history_cases.json')
    hist_path=gate.portable(read(prep/'history_binding.json')['path'])
    historical=read(hist_path);common=read(prep/'core/qualification/common/result.json')
    checks=[]
    def check(name,v):checks.append(dict(name=name,passed=bool(v)))
    check('protected_prior_freezes_and_tests',campaign.protected()==read(prep/'protected.json'))
    check('history_source_bound',digest(hist_path)==read(prep/'history_binding.json')['sha256'])
    check('six_calls',outcome['calls']==6 and outcome['reserved']==6)
    check('twelve_arms',len(outcome['decisions'])==12)
    cases=history+[c for s in campaign.SEEDS for c in read(prep/f's{s}/acquired_cases.json')]
    used={loop.sha(c['rows']) for c in cases}|set(read(prep/'excluded_tests.json')['input_hashes'])
    split=read(run/'common_independent_split.json');test_cases=split['boundary_cases']+split['drain_cases']
    inputs={loop.sha(c['rows']) for c in test_cases}
    check('fresh_common_56_48',len(test_cases)==56 and len(inputs)==48 and not used&inputs)
    eval_cache={};arms={};pairs={};examples=[]
    for seed in campaign.SEEDS:
        target=read(prep/f's{seed}/core/qualification/acquired/result.json')
        for stream,names in (('ordinary',('A','C')),('search',('B','D'))):
            folder=run/f's{seed}'/stream;call_folder=folder/'model_call';label=f'{seed}/{stream}'
            saved=read(folder/'pair_result.json')
            request=read(call_folder/'request.json')
            check(label+':sealed_request',request==read(prep/f's{seed}/{stream}/request.preview.json'))
            check(label+':parameters',request['seed']==seed and request['temperature']==0.2)
            edit=read(call_folder/'model_edit.json') if (call_folder/'model_edit.json').exists() else None
            candidate=read(call_folder/'candidate.json') if (call_folder/'candidate.json').exists() else None
            if edit is not None:check(label+':raw_model_response',raw_response(call_folder,edit))
            if candidate is not None:check(label+':no_predicate_rewrite',campaign.assemble(edit,initial)==candidate)
            after=read(folder/'visible_native/result.json') if candidate else None
            before=join_results([common,target]) if stream=='search' else common
            if candidate:
                plain=campaign.current_decision(before,after,edit)
                check(label+':current_decision',plain==read(folder/'plain_decision.json')==saved['plain'])
                full=read(folder/'history_native/result.json')
                hg=gate.decide(historical['group']['ledger'],full['group']['ledger']) if full.get('group') else dict(accepted=False,reasons=[dict(kind='history_native_unavailable')])
                check(label+':history_gate',hg==read(folder/'historical_gate.json'))
                check(label+':plain_committed_before_history',
                    (folder/'plain_decision.json').stat().st_mtime<=(folder/'history_native/result.json').stat().st_mtime)
                check(label+':gated_is_strict_addition',saved['gated']['accepted']==bool(plain['accepted'] and full['healthy'] and hg['accepted']))
                old_info=loop.inspect(historical['group']['ledger'])
                new_info=loop.inspect(full['group']['ledger']) if full.get('group') else None
                detail=dict(lost_detections=len(old_info['detections']-new_info['detections']),
                    new_false_positives=len(new_info['false_positives']-old_info['false_positives']),
                    unknown=len(new_info['unknown'])) if new_info else None
                kinds=[r['kind'] for r in hg['reasons']]
                losses=protection_losses(historical['group']['ledger'],full['group']['ledger'],hg) if new_info else dict(confirmed={},unconfirmed={})
                concrete=any(losses['confirmed'].values())
            else:
                plain=saved['plain'];full=None;hg=None;detail=None;kinds=[];concrete=False;losses=dict(confirmed={},unconfirmed={})
                check(label+':unusable_not_accepted',not plain['accepted'] and not saved['gated']['accepted'])
                check(label+':unusable_no_native',not (folder/'visible_native').exists() and not (folder/'history_native').exists())
            benefit=bool(plain['accepted'] and not saved['gated']['accepted'] and concrete)
            pairs[label]=dict(seed=seed,stream=stream,proposal_hash=saved['proposal_hash'],
                native_proposal_available=candidate is not None,
                reason_characters=len(edit.get('reason','')) if edit else None,
                reason_exceeds_declared_limit=bool(edit and len(edit.get('reason',''))>128),
                same_actual_proposal=True,plain_accepted=plain['accepted'],gated_accepted=saved['gated']['accepted'],
                historical_change=detail,gate_rejection_kinds=kinds,additional_protection_observed=benefit,
                protection_losses=losses,current_failed=not plain['accepted'],call=saved['call'])
            examples.append(dict(seed=seed,stream=stream,initial_properties=initial['assertions'],
                model_edit=edit,proposed_properties=candidate['assertions'] if candidate else None,
                paired_decisions=dict(plain=plain,gated=saved['gated']),
                visible_native_metrics=saved['current'],history_native_metrics=saved['history'],
                native_target_records=(plain.get('target_gate') or {}).get('target_rows',[])))
            for name in names:
                key=f's{seed}/{name}';arm=run/'arms'/key
                decided=read(arm/'decision.json');frozen=read(arm/'frozen_candidate.json')
                expected_decision=plain if name==names[0] else saved['gated']
                check(key+':paired_decision_bound',decided['accepted']==expected_decision['accepted'])
                expected=candidate if decided['accepted'] else initial
                check(key+':retained_version',frozen==expected and loop.sha(frozen)==decided['frozen_hash']==read(arm/'freeze.json')['candidate_sha256'])
                check(key+':shared_proposal',decided['proposal_hash']==saved['proposal_hash'])
                binding=read(arm/'evaluation_binding.json');eval_path=run/binding['physical_evaluation']
                h=loop.sha(frozen)
                check(key+':evaluation_binding',binding['candidate_hash']==h and read(eval_path/'core/frozen_candidate.json')==frozen)
                if h not in eval_cache:
                    actual_split=read(eval_path/'independent/split.json');summary=read(eval_path/'independent/summary.json')
                    check(h+':identical_input_batch',all(actual_split[k]==split[k] for k in ('seed','boundary_cases','drain_cases')))
                    check(h+':after_all_freeze',(eval_path/'independent/split.json').stat().st_mtime>=(run/'all_arms_freeze.json').stat().st_mtime)
                    combined=read(eval_path/'independent/combined.json')
                    check(h+':native_test_metrics',campaign.metrics(combined)==summary['metrics'])
                    drains=assess(eval_path/'independent/drain',split['drain_cases'],read(eval_path/'independent/drain/result.json'))
                    check(h+':drain_exposure',drains==read(eval_path/'independent/drain_assessment.json'))
                    valid=combined['healthy'] and drains['passed'] and all(v['detections']>0 and v['triggers']>0 and not any(v[k] for k in ('misses','false_positives','unknown')) for v in summary['metrics']['obligations'].values())
                    check(h+':finite_acceptance',bool(valid)==summary['all_five_pass_on_first_attributed_evidence'])
                    eval_cache[h]=summary
                arms[key]=dict(decision=decided,independent=eval_cache[h],logical_model_calls=1,
                    physical_model_call_shared_with=[f's{seed}/{n}' for n in names],
                    independent_evaluation_shared_by_exact_hash=True)
    first_test=min(p.stat().st_mtime for p in (run/'evaluation').glob('*/independent/split.json'))
    check('all_calls_before_tests',all(p.stat().st_mtime<=first_test for p in run.glob('s*/*/model_call/attempt.json')))
    check('all_arm_freezes_before_tests',all(p.stat().st_mtime<=first_test for p in (run/'arms').glob('s*/*/freeze.json')))
    deltas=[]
    for seed in campaign.SEEDS:
        for left,right,meaning in (('B','A','search_without_gate'),('D','C','search_with_gate'),('C','A','gate_without_search'),('D','B','gate_with_search')):
            l=arms[f's{seed}/{left}']['independent'];r=arms[f's{seed}/{right}']['independent']
            deltas.append(dict(seed=seed,contrast=left+'-'+right,meaning=meaning,
                pass_difference=int(l['all_five_pass_on_first_attributed_evidence'])-int(r['all_five_pass_on_first_attributed_evidence']),
                counts_difference={k:l['metrics']['counts'][k]-r['metrics']['counts'][k] for k in ('detections','misses','false_positives','unknown','later_attribution_unknown')}))
    run_files=campaign.files(run);cost=cost_audit(run,run_files)
    check('physical_cost_six_calls',cost['total']['model_calls']==6)
    totals={n:dict(accepted=sum(arms[f's{s}/{n}']['decision']['accepted'] for s in campaign.SEEDS),
                  independent_pass=sum(arms[f's{s}/{n}']['independent']['all_five_pass_on_first_attributed_evidence'] for s in campaign.SEEDS)) for n in campaign.ARMS}
    result=dict(audit_passed=all(c['passed'] for c in checks),checks=checks,pairs=pairs,arms=arms,
        totals=totals,deltas=deltas,observed_additional_protection=sum(p['additional_protection_observed'] for p in pairs.values()),
        physical_model_calls=6,logical_arm_model_calls=12,unique_independent_inputs=48,shared_test_scenarios=56,
        unique_frozen_candidates=len(eval_cache),cost=cost['total'],
        scope='Single-step paired decision effect on one selected artificial-fault FIFO task, not independent twelve-call or multi-round policy evidence. Search contrast still includes model-response variation; no guaranteed superiority.')
    result['mechanism_exposure']=dict(
        native_usable_proposals=sum(p['native_proposal_available'] for p in pairs.values()),
        current_gate_accepted_proposals=sum(p['plain_accepted'] for p in pairs.values()),
        incremental_gate_benefit_rate=(result['observed_additional_protection']/sum(p['plain_accepted'] for p in pairs.values())
            if any(p['plain_accepted'] for p in pairs.values()) else None),
        interpretation='No eligible proposals means the incremental gate effect is not estimable; zero accepted arms is not evidence of zero mechanism value.')
    dump(out/'results.json',result);dump(out/'cost.json',cost);dump(out/'case_examples.json',examples)
    lines=['# research43：成对提案的四组消融','',
        f"记录审计 {sum(c['passed'] for c in checks)}/{len(checks)}。实际 6 次模型生成，12 个成对处理结果，不是12次独立模型调用。",'',
        '|组|新搜索证据|历史门控|接受/3|五义务有限独立验收/3|','|---|---|---|---:|---:|']
    for n,a in campaign.ARMS.items():lines.append(f"|{n}|{a['search']}|{a['gate']}|{totals[n]['accepted']}|{totals[n]['independent_pass']}|")
    lines += ['',f"实际6次调用中，可进入原生执行的提案 {result['mechanism_exposure']['native_usable_proposals']}/6；普通当前检查接受 {result['mechanism_exposure']['current_gate_accepted_proposals']}/6。历史门控额外保住保护的提案数：{result['observed_additional_protection']}。分母为0时机制效应不可估计，不能解释为机制收益为0，也不能用旧坏提案补成成功。",'',
        'A/C、B/D各共享一次真实提案。所有12臂先冻结，再使用同一批56场景/48种输入；完全相同候选共享实际回放，不重复计样本。', '',
        '逐种子 B−A、D−C、C−A、D−B 的检出、漏报、误报和unknown差值见 results.json/deltas。保留失败、keep、接口拒绝以及后续归因unknown；无目标曝光不能算通过。', '',
        '本轮是已知FIFO人工故障任务上的单轮成对实验。门控对比控制了提案差异；搜索对比仍可能含模型随机性。三个请求种子不能建立普遍统计优势。','',
        '成本（调用、仿真与测量成本按实际物理记录；金额不可用）：','```json',json.dumps(cost['total'],ensure_ascii=False,indent=2),'```','',
        '搜索物理成本来自 research42，B/D逻辑上各需同种子的4次契约查询；共享获取只付一次物理成本。当前门控后的全历史回放对A/B属于离线测量，对C/D属于处理成本。独立回放全部属于测量。', '',
        '完整模型编辑、当前目标触发和门控决定见 case_examples.json。实际命令：','```powershell',
        f'wsl -- python3 scripts/research43_paired_ablation.py run --prepared {prep.relative_to(loop.ROOT).as_posix()} --out {run.relative_to(loop.ROOT).as_posix()} --authorization {prep.relative_to(loop.ROOT).as_posix()}/authorization.json','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    shutil.copy2(__file__,out/'audit_source.py')
    # Hash each physical artifact once in this audit; shared evaluations are
    # references, not copied native command records or manufactured executions.
    dump(out/'run_manifest.json',{p.relative_to(run).as_posix():digest(p) for p in run_files})
    print('PAIRED_AUDIT',result['audit_passed'],'gate_increment',result['observed_additional_protection'],flush=True)
    assert result['audit_passed'],[c for c in checks if not c['passed']]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();report(a.run.resolve(),a.out.resolve())
