"""Audit three fixed-seed searches and sealed ordinary/search request isolation.

No model invocation. Native records and independent transaction checks are
recomputed; findings are explicitly scoped to the fixed artificial-fault task.
"""
import argparse
import json
from pathlib import Path
import research70_multiseed_prepare as run
import research64_native_audit as native
import research68_result_audit as replay_audit


def audit(root,out):
    run.verify(root);out.mkdir(parents=True,exist_ok=False)
    b=run.b;checks=[];records=0;summaries={};ready=[];costs={}
    for seed in b.SEEDS:
        source=root/'search'/f's{seed}'
        native.audit(source,out/f's{seed}'/'search_native')
        n=run.read(out/f's{seed}'/'search_native/audit.json')
        records+=n['native_replays_verified']
        b.summarize_search(source)
        summaries[str(seed)]=run.read(source/'summary.json')
        prep=root/'prepared_v4'/f's{seed}'
        qualified=run.read(prep/'qualification.json')['passed']
        checks.append(dict(seed=seed,qualification=qualified))
        costs[str(seed)]=dict(search=run.read(source/'cost.json'),
                             qualification=run.read(prep/'cost.json') if (prep/'cost.json').exists() else None,
                             reference=run.read(source/'reference_costs.json'))
        if not qualified:continue
        run.preflight.verify(root,prep)
        dest=root/'ready'/f's{seed}'
        for rel,h in run.read(dest/'sealed.json').items():assert b.search.digest(dest/rel)==h,rel
        initial=run.read(dest/'shared_initial.json')
        with b.extension.installed():
            for group,key in (('common','common_cases.json'),('search','search_cases.json')):
                records+=replay_audit.raw_replay(prep/'core/native'/group,run.read(dest/key),initial,checks)
        req={s:run.read(dest/s/'request.preview.json') for s in ('ordinary','search')}
        bodies={s:json.loads(r['messages'][1]['content']) for s,r in req.items()}
        for key in run.read(dest/'isolation.json')['public_fields']:
            assert bodies['ordinary'][key]==bodies['search'][key]
        for case in run.read(dest/'search_cases.json'):
            assert case['id'] not in json.dumps(req['ordinary'])
            assert case['id'] in json.dumps(bodies['search']['actual_observations'])
        for s,r in req.items():
            assert r['seed']==seed and r['max_tokens']==2048
            assert all(marker not in json.dumps(r) for marker in
                       ('research63','research69_pilot','verified_model_applicability_plan'))
            ready.append(dict(seed=seed,stream=s,path=str(dest/s/'request.preview.json'),
                              sha256=b.search.digest(dest/s/'request.preview.json')))
        checks.append(dict(seed=seed,request_hashes_and_public_helpers_equal=True,
                           search_isolated=True,no_successful_pilot_candidate_or_test_in_prompt=True))
    run.verify(root)
    run.dump(out/'audit.json',dict(passed=True,checks=checks,native_records_recomputed=records,
        requests=ready,all_three_seeds_qualified=len(ready)==6,model_calls=0,new_native_calls=0,
        source_sha256=b.search.digest(Path(__file__))))
    run.dump(out/'results.json',summaries);run.dump(out/'costs.json',costs)
    lines=['# research70：先导通过后的多种子本地准备','',
        'research69 的实际目标、105历史及新独立验收通过后，才启动本批。固定种子6711/6719/6733，旧公共候选、五方法、每方法四查询不变。没有调用模型。','',
        '|种子|方法|公共之外去重缺口|首发现查询|重复动作|关键unknown|后续归因unknown|',
        '|---|---|---|---|---|---|---|']
    for seed,summary in summaries.items():
        for name,m in summary['methods'].items():
            first=','.join(str(v) for v in m['first_query'].values()) or '未找到'
            lines.append(f"|{seed}|{name}|{len(m['keys'])}|{first}|{m['repeated_actions']}|{m['unknown']}|{m['later_attribution_unknown']}|")
    lines+=['',f"契约相对全部对照并集的独有缺口（逐种子）：{ {s:v['contract_extra_vs_all'] for s,v in summaries.items()} }。",
        '', '已知人工故障不会因更换种子变成新历史Bug；按候选、义务、错误机制去重，持续背压长短波形不重复算收益。公共解除边界不计新增；额外信息仅搜索组可见。零优势、未发现见证及unknown均保留。',
        '', '三个种子的本地执行相互独立并行；墙钟耗时受资源竞争影响，不作为严格隔离的性能优势。每方法查询/实际原生/参考判定成本仍逐项记录。',
        '',f"原生日志重算{records}份。合格请求{len(ready)}/6，哈希见audit.json；实际成本及参考判定调用逐条保存在costs.json，审计成本在各seed/search_native/audit.json另列。",
        '', '尚未执行远程单轮共享提案对照或独立多轮策略消融；没有生成新提案、接受版本或新的组间独立测试。两类结论分开：前者仅测同一提案的门控决定，后者需要各组独立调用与反馈轨迹。',
        '', '旧先导3次额度已用完。下一批若授权，单轮配对最多6次；独立多轮另外最多24次，均无传输重试。现有封存并非调用授权。新测试必须在各组冻结后生成，不能使用research69测试选候选。',
        '', '复核（输出目录须新建）：','```powershell',
        f'wsl -- python3 scripts/research70_prepare_audit.py --run {root.relative_to(run.ROOT).as_posix()} --out deliverables/research70_audit_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('AUDIT',records,'native records;',len(ready),'sealed requests; model calls0',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args();audit(a.run.resolve(),a.out.resolve())
