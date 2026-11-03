"""Prospective three-seed paired2x2 continuation using the qualified44 interface.

Reuse43's native evidence isolation, paired gate contrast, freeze and holdout.
No old successful SVA or47 plan is inserted into any model request.
"""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path

import research17_loop as loop
import research43_paired_ablation as base
import research44_interface as interface
import research45_campaign as qualified
from research17_report import cost_audit

ROOT=loop.ROOT
read,dump=loop.read,loop.dump
SEARCH=ROOT/'deliverables/research42_search_20261022_r01'
EXPOSURE=ROOT/'deliverables/research42_search_inputs_20261022_r01/exposed_inputs.json'
ORIGINAL_SETTINGS=base.settings


def settings(seed):
    result=ORIGINAL_SETTINGS(seed)
    result.update(max_model_calls=1,max_tokens=400000,max_wall_seconds=7200,
                  expression_format='recursive_ast_reason_metadata_v2')
    result['options']['num_predict']=2048
    return result


@contextmanager
def corrected_interface(protocol=None,destination=None):
    old_model,old_settings=base.Model,base.settings
    old_prepare=loop.prepare
    base.Model,base.settings=qualified.Model,settings
    if protocol is not None:
        def prepare_actual(folder):
            old_prepare(folder)
            if Path(folder)==destination:dump(Path(folder)/'protocol.json',protocol)
        loop.prepare=prepare_actual
    try:yield
    finally:
        base.Model,base.settings=old_model,old_settings
        loop.prepare=old_prepare


def exposure_inventory(exclude):
    """Hash every saved case/split/stimulus container, without using outcomes.

    Only hashes reach the holdout overlap check. No old test sample or outcome
    enters a request, selection, or generator. Missing historical inputs cannot
    be reconstructed; retained source/exclusion registries are merged as well.
    """
    sources=[];hashes=set();unreadable=[]
    def inputs(value):
        if isinstance(value,list):
            if value and all(isinstance(r,dict) and {'cycle','intent','ready','data'}<=set(r) for r in value):
                yield value
            else:
                for item in value:yield from inputs(item)
        elif isinstance(value,dict):
            if isinstance(value.get('rows'),list):
                yield from inputs(value['rows'])
            else:
                for key,item in value.items():
                    if key not in ('ledger','trace','reference_trace','messages','metrics'):
                        yield from inputs(item)
    for folder,dirs,files in os.walk(ROOT/'deliverables'):
        path=Path(folder)
        dirs[:]=[d for d in dirs if d not in ('source_snapshot','__pycache__','model_call','obj_dir','.git')
                 and not d.startswith('compiled') and path/d!=exclude]
        for name in files:
            if not (name in ('case.json','split.json','stimulus.json','common_independent_split.json') or name.endswith('cases.json')):continue
            source=path/name
            try:
                value=read(source);found={loop.sha(rows) for rows in inputs(value)}
            except (OSError,ValueError,TypeError) as exc:
                unreadable.append(dict(path=str(source),error=type(exc).__name__));continue
            if found:
                hashes.update(found);sources.append(dict(path=str(source),sha256=base.digest(source),input_hashes=sorted(found)))
    assert not unreadable,unreadable
    return dict(input_hashes=sorted(hashes),sources=sources,unreadable=unreadable,
        scope='All available saved case/split/stimulus containers under deliverables, plus inherited exposure registries. Hash-only exclusion; not independence from known fault families.')


def prepare(out):
    # This performs actual initial/common/target qualification; no remote calls.
    base.prepare(SEARCH,out,EXPOSURE)
    finish_prepare(out)


def finish_prepare(out,indexed_inventory=None):
    assert read(out/'protocol.json').get('experiment')!='research50_prospective_paired_one_step_three_seed'
    assert read(out/'qualification.json')['passed'] and (out/'local_cost.json').exists()
    initial=read(out/'shared_initial.json');previews={};checks=[]
    def check(name,okay):checks.append(dict(name=name,passed=bool(okay)));assert okay,name
    for seed in base.SEEDS:
        bodies={}
        for stream in ('ordinary','search'):
            path=out/f's{seed}/{stream}/request.preview.json'
            request=qualified.request_from(read(path),initial,seed)
            dump(path,request);previews[path.relative_to(out).as_posix()]=base.digest(path)
            bodies[stream]=json.loads(request['messages'][1]['content'])
            check(f'{seed}/{stream}:uniform_sampling',request['max_tokens']==2048 and request['temperature']==0.2 and request['seed']==seed)
            check(f'{seed}/{stream}:no_reason_length_semantic_gate','maxLength' not in bodies[stream]['output_schema']['properties']['reason'])
            check(f'{seed}/{stream}:no_prior_repair_or_plan',not any(k in bodies[stream] for k in
                ('actual_previous_attempt','verified_model_applicability_plan','verified_plan_field_bindings')))
        for key in ('rtl_and_common_contract','current_assertions','confirmed_obligations','ordinary_observations','output_schema'):
            check(f'{seed}:common:{key}',bodies['ordinary'][key]==bodies['search'][key])
        check(f'{seed}:search_only_evidence',bool(bodies['search']['actual_observations']) and not bodies['ordinary']['actual_observations'])
        for case in read(out/f's{seed}/acquired_cases.json'):
            check(f'{seed}:hidden_search_case:{case["mode"]}',case['id'] not in json.dumps(bodies['ordinary']))
    if indexed_inventory is None:
        inventory=exposure_inventory(out)
    else:
        raw=read(indexed_inventory)
        assert raw['format']=='raw_input_inventory_v1' and not raw['unreadable']
        row_hashes=[loop.sha(rows) for rows in raw['unique_rows']]
        inventory=dict(input_hashes=sorted(set(row_hashes)),unreadable=[],
            sources=[dict(path=str(ROOT/s['path']),sha256=s['sha256'],
                          input_hashes=sorted({row_hashes[i] for i in s['row_ids']})) for s in raw['sources']],
            indexed_source=dict(path=str(indexed_inventory),sha256=base.digest(indexed_inventory),
                                file_index_sha256=raw['file_index_sha256'],
                                builder_sha256=base.digest(ROOT/'scripts/research50_inventory.cjs')),
            scope='Saved case/split/stimulus containers indexed by Windows rg; row hashes computed by the same Python sha as the holdout. Hash-only exclusion; not new fault families.')
    dump(out/'all_saved_input_exposure.json',inventory)
    if indexed_inventory is not None:
        (out/'inventory_builder.cjs').write_bytes((ROOT/'scripts/research50_inventory.cjs').read_bytes())
    excluded=read(out/'excluded_tests.json')
    excluded['input_hashes']=sorted(set(excluded['input_hashes'])|set(inventory['input_hashes'])|qualified.extra_exclusions())
    excluded['all_saved_input_inventory']=dict(path=str(out/'all_saved_input_exposure.json'),sha256=base.digest(out/'all_saved_input_exposure.json'))
    dump(out/'excluded_tests.json',excluded)
    keep=dict(operation='keep',assertion_id='',assertions=[],reason='local qualification only; '+'x'*256)
    check('metadata_does_not_reject_valid_keep',interface.assemble(keep,initial)==initial)
    for bad in ({**keep,'assertion_id':'a4'},{**keep,'operation':'invented'},{**keep,'reason':None}):
        try:interface.assemble(bad,initial)
        except (AssertionError,ValueError,TypeError):check('invalid_ast_still_rejected',True)
        else:raise AssertionError('invalid_edit_accepted')
    protocol=read(out/'protocol.json')
    protocol.update(experiment='research50_prospective_paired_one_step_three_seed',max_output_tokens=2048,
        preview_hashes=previews,interface='research44_interface: reason metadata preserved; executable AST restrictions retained',
        logical_groups='A ordinary, B search, C ordinary+history gate, D search+history gate. A/C share one real proposal; B/D share one real proposal per seed.',
        estimand='One-step paired admission effect, not multi-round adaptive feedback policy effect. Six physical model calls,12 logical arms; no manufactured proposal.',
        eligibility='Gate benefit only for current-pass/full-history-reject real proposals with independently confirmed loss. Report current-pass keeps separately from changed eligible proposals; zero changed eligibility means repair gate benefit not estimable.',
        no_pilot_selection='All six preregistered streams run regardless of previous proposal success; no successful pilot is selected or supplied.',
        cost_alignment='One model call per stream/seed, same2048 cap. Search4 queries per B/D logical arm,105 history for C/D treatment; A/B history is postdecision measurement only. Shared physical work charged once, logical costs separately.',
        holdout='All12 accepted-or-retained versions freeze before one fresh common56-case batch. Exact candidate duplicates share physical replay, not independent samples. Rejected versions are not reported as new accepted repairs.',
        historical_results='research42 negative search result and research43 interface failures remain unchanged; this is a new protocol with corrected interface and output cap.',
        authorization='Requires a new six-call grant. No unused restricted prior grants are automatically transferred.')
    dump(out/'protocol.json',protocol)
    dump(out/'interface_isolation_qualification.json',dict(passed=True,checks=checks,physical_model_calls=0,
        exclusion_hashes=len(excluded['input_hashes']),inventory_sources=len(inventory['sources'])))
    base.snapshot(out)
    dump(out/'local_cost.json',cost_audit(out,base.files(out)))
    (out/'SUMMARY.md').write_text('# research50：公平四组对照准备\n\n'
        f'接口与隔离检查{len(checks)}/{len(checks)}通过。3个固定种子，每种子普通/搜索各1次真实调用，A/C与B/D分别共享提案做门控对照。'
        '公共初始候选通过105历史基线；每种子2条当前搜索漏报已重新原生确认。\n\n'
        '这是单轮配对决策实验，不是多轮自适应细化策略的完整消融。实际收益由真实提案和冻结后公共测试决定；没有合格提案时不宣称收益。'
        '此时尚未调用远程模型、未冻结实验各组、未生成独立测试。\n\n'
        f'独立输入排除已合并{len(excluded["input_hashes"])}个已保存输入哈希；来源保存在all_saved_input_exposure.json。'
        '旧独立测试内容和结果不会发送模型。\n\n'
        '六份请求位于s4201|s4211|s4217/ordinary|search/request.preview.json。真实运行需新增最多6次调用授权，无重试。\n',encoding='utf-8')
    dump(out/'prepared_hashes.json',{p.relative_to(out).as_posix():base.digest(p) for p in base.files(out)
        if p.suffix=='.json' and p.name!='prepared_hashes.json' and 'source_snapshot' not in p.parts})
    print('CONTROLLED_PREPARED',len(checks),'checks',len(excluded['input_hashes']),'excluded inputs; model_calls=0',flush=True)


def run(prep,out,authorization):
    auth=read(authorization);protocol=read(prep/'protocol.json')
    assert auth['scope']=='research50_three_seed_paired_ablation' and auth['authorized_calls']==6
    assert protocol['experiment']=='research50_prospective_paired_one_step_three_seed'
    assert auth['preview_hashes']==protocol['preview_hashes']
    with corrected_interface(protocol,out):base.run(prep,out,authorization)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','finish-prepare','run'))
    p.add_argument('--out',required=True,type=Path);p.add_argument('--prepared',type=Path);p.add_argument('--authorization',type=Path)
    p.add_argument('--indexed-inventory',type=Path)
    a=p.parse_args();out=a.out.resolve();assert ROOT in out.parents
    if a.action=='prepare':prepare(out)
    elif a.action=='finish-prepare':finish_prepare(out,a.indexed_inventory.resolve())
    else:run(a.prepared.resolve(),out,a.authorization.resolve())
