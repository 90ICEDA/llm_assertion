"""Read-only prerequisite audit for a new independent acceptance batch.

This command never generates tests or calls a model/simulator. A retained old
freeze cannot stand in for a newly accepted SVA set. The manifest is scoped to
the inspected campaign, not an assertion that all past exposure is inventoried.
"""
import argparse
from pathlib import Path
import shutil
import research48_sva_campaign as campaign

read,dump=campaign.read,campaign.dump


def audit(run,out):
    out.mkdir(parents=True,exist_ok=False)
    prep=campaign.gate.portable(read(run/'prepared_source.json')['path'])
    outcome=read(run/'outcome.json');freeze=read(run/'core/freeze.json')
    candidate=read(run/'core/frozen_candidate.json');initial=read(prep/'shared_initial.json')
    versions=[];bindings={};development=[]
    def bind(path):
        bindings[str(path)]=campaign.common.digest(path)
    for path in (run/'outcome.json',run/'core/freeze.json',run/'core/frozen_candidate.json',
                 prep/'shared_initial.json',prep/'protocol.json',prep/'plan_binding.json'):
        bind(path)
    for version in sorted((run/'core').glob('v*')):
        decision=read(version/'decision.json');bind(version/'decision.json')
        proposed=read(version/'model_call/candidate.json') if (version/'model_call/candidate.json').exists() else None
        gates={name:read(version/(name+'.json')) for name in ('current_gate','native_window_gate','history_gate')}
        for name in gates:bind(version/(name+'.json'))
        bind(version/'model_call/request.json')
        versions.append(dict(version=version.name,candidate_present=proposed is not None,
            decision_accepted=decision['accepted'],gates_accepted={k:v['accepted'] for k,v in gates.items()},
            equals_frozen=proposed is not None and proposed==candidate))
    for name in ('cases.json','history_cases.json'):
        source=prep/name;bind(source)
        for case in read(source):
            development.append(dict(source=str(source),scenario=case['id'],depth=case['depth'],pipeline=case['pipeline'],
                mode=case['mode'],input_sha256=campaign.loop.sha(case['rows']),case_sha256=campaign.loop.sha(case)))
    expected=read(prep/'expected.private.json');bind(prep/'expected.private.json')
    for row in expected:
        source=campaign.gate.portable(row['source'])
        assert campaign.common.digest(source)==row['source_sha256']
        bind(source)
    actual_hash=campaign.loop.sha(candidate)
    matching=[v for v in versions if v['candidate_present'] and v['decision_accepted'] and
              all(v['gates_accepted'].values()) and v['equals_frozen']]
    consistent=actual_hash==freeze['candidate_sha256']==outcome['frozen_hash']
    new_accepted=outcome['accepted'] is True and len(matching)==1 and candidate!=initial and consistent
    reasons=[]
    if outcome['accepted'] is not True:reasons.append('campaign_has_no_accepted_new_sva')
    if not matching:reasons.append('no_frozen_candidate_passes_all_three_native_gates')
    if candidate==initial:reasons.append('existing_freeze_is_retained_initial_set')
    if not consistent:reasons.append('frozen_hash_inconsistent')
    manifest=dict(development=development,unique_current_campaign_input_hashes=sorted({c['input_sha256'] for c in development}),
        source_hashes=bindings,model_plan_windows=len(expected),
        scope='Inspected research48 current/history scenarios and referenced plan sources. These inputs must be excluded from future holdout.',
        all_prior_campaign_exposure_inventory_complete=False,
        remaining_inventory='Before actual holdout, merge all prior prompt/search/refinement/selection inputs and prior independent test exclusions, with source hashes; this campaign manifest alone is insufficient.')
    dump(out/'development_manifest.json',manifest)
    result=dict(status='candidate_eligible_inventory_pending' if new_accepted else 'blocked_no_new_accepted_candidate',
        new_accepted_candidate=new_accepted,reasons=reasons,versions=versions,
        existing_frozen_hash=actual_hash,frozen_hash_consistent=consistent,
        existing_freeze_is_initial=candidate==initial,new_freeze_created=False,
        independent_seed_drawn=False,new_test_inputs_generated=False,independent_execution=False,
        model_calls=0,native_calls=0,formal_calls=0,
        independent_result=None,whole_case_pass=None,
        existing_holdout_entry='research35_campaign.holdout',
        required_obligations=list(campaign.loop.model.SPECS),
        required_scope='Freeze accepted model version and configuration before fresh seed/inputs; depths2/4/8, legal controls and actual targets, explicit exposure per obligation, critical unknowns reject.',
        contamination_rule='If test evidence drives modification or selection, relabel the whole batch development and generate a new post-freeze batch.')
    dump(out/'readiness.json',result)
    assert all(campaign.common.digest(Path(p))==h for p,h in bindings.items())
    text=('# 新独立验收前置核查\n\n状态：'+result['status']+'。\n\n'
        'research48没有新接受的SVA。v0、v2虽原生编译执行，当前目标与历史门控均拒绝；v1为HTTP400无候选。'
        '现有freeze.json的理由是失败后保留原集合，不能当作第2项新接受版本。\n\n'
        f'现有冻结哈希：`{actual_hash}`。与初始集合一致，哈希一致性通过。\n\n'
        '已保存本研究当前/105历史场景的开发输入哈希、配置来源和11个周期窗口原生来源。'
        '此清单只覆盖所核查研究，不能代替所有历史提示/搜索/选择数据的完整排除清单。\n\n'
        '没有生成新冻结版本、随机种子或独立测试，没有新增模型/仿真/形式化调用；独立结果为空，不记通过或失败。\n\n'
        '现有research35_campaign.holdout可继续复用：按冻结后的新种子生成多深度边界与排空场景，检查与开发/既有曝光输入哈希无重合，'
        '逐项要求五项义务具有实际触发及检出证据，保留后续归因unknown。已有功能不等于本轮已执行。\n\n'
        '需先完成第2项：真实模型的新断言集合通过当前目标、必需窗口与105历史场景。之后补全全部历史曝光排除清单，'
        '绑定新冻结版本，再生成和执行新独立批次。测试失败如参与修改，该批整体转为开发数据。\n')
    (out/'SUMMARY.md').write_text(text,encoding='utf-8')
    shutil.copy2(Path(__file__),out/'audit_source.py')
    print('READINESS',result['status'],'versions',len(versions),'development_entries',len(development),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();audit(a.run.resolve(),a.out.resolve())
