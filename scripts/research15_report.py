"""Evidence-based stage report; absent experiments remain explicitly incomplete."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from research15_pipeline import ROOT,OUT,read,dump

NATIVE=ROOT/'deliverables/research15_native_20261015_r01'
SEARCH=ROOT/'deliverables/research15_search_20261015_r01/fixed_initial_negative'
HISTORY=ROOT/'deliverables/research15_history_20261015_r01'


def report():
    initialization=read(OUT/'native_readjudication/initialization_summary.json')
    by_version={r['version']:r for r in initialization['results']}
    versions=[];examples=[]
    for name,version in [('initial','original'),('initial_semantic_repair','semantic_repair'),
                         ('initial_temporal_repair','initial_temporal_continuation')]:
        call=NATIVE/'model_calls'/name;candidate=read(call/'candidate.json')
        evaluation=by_version[version]
        folder=ROOT/evaluation['artifacts']
        fixed=read(folder/'correct/replay.json')
        versions.append(dict(model_call=name,model_result=read(call/'result.json'),
            sva=(call/'candidate.sva').read_text(),candidate=candidate,
            counts=evaluation['current_counts'],accepted=False,
            compile=fixed['native']['compile_status'],execution=fixed['native']['execution_status'],
            trigger_source=fixed['native']['trigger_measurement'],evidence_directory=evaluation['artifacts']))
        hit=fixed['native']['failures'][0] if fixed['native']['failures'] else None
        if hit:
            cycle=int(re.search(r'cycle=(\d+)',hit['detail'])[1])
            examples.append(dict(version=name,sva=(call/'candidate.sva').read_text(),native_failure=hit,
                actual_samples=[r for r in fixed['trace'] if cycle-1<=r['cycle']<=cycle],
                independent_oracle_checks=[r for r in fixed['oracle']['checks'] if r['cycle']==cycle],
                correct_rtl_verdict=fixed['oracle']['verdict'],artifact=evaluation['artifacts'],
                acceptance='rejected',independent_test='not run; no accepted final candidate'))
    native=dict(status='three_actual_model_native_replay_attempts_all_rejected',versions=versions,
        accepted_version=None,original_two_call_budget_succeeded=False,extra_temporal_calls=1,
        four_arm_native_ablation='implemented_not_executed',final_frozen_independent_test='not_executed',
        blocker='No shared initial order assertion passed finite native qualification; extra timing repair also failed. No templates substituted.',
        audit='Authoritative initialization counts are readjudicated against legal control alarms. Original first version had 3 raw alleged detections, corrected to attribution unknown; rejection unchanged.',
        source_limit='Exact generated SVA, compiled TB and command logs retained. First qualification Python process imported the earlier adapter; later readjudication has a saved current adapter hash. The delivery source snapshot is not retroactively claimed to be that earlier imported Python version.',
        model_provider='actual local Ollama; generic remote transport inherited but not exercised',formal_proof=False)
    dump(NATIVE/'summary.json',native);dump(OUT/'evidence_examples.json',examples)
    search=read(SEARCH/'summary.json');search_audit=read(OUT/'search_independent_audit.json')
    history=read(HISTORY/'combined_summary.json');costs=read(OUT/'physical_cost_ledger.json')
    rows=[
        ('真实LLM→原生SVA反馈链','已运行，未通过','3次真实模型生成/修改均原生编译执行并拒绝；无可接受最终版本。','scripts/research15_native_models.py','research15_native_20261015_r01/summary.json'),
        ('契约反馈驱动四法搜索','已验证有限运行，负结果','48查询/240原生回放；首个真实候选固定；无可导出的有效tail-loss细化见证。','scripts/research15_search_experiment.py','research15_search_20261015_r01/fixed_initial_negative/summary.json'),
        ('原11对候选四法对比','此前已运行，本轮复用','旧36/37/43/43独立候选缺口；不是本轮原生结果，无总体优势结论。','scripts/research_search_compare.py','research_search_20261014_r01/pair_results.json'),
        ('多SVA义务证据库/接受门','已实现与定向资格检查，完整机制未验证','12个门检查+13个适配器检查；实际模型版本无历史有效保护可供完整集合细化验收。','scripts/research15_acceptance.py','research15_integration_20261015_r01/gate_qualification.json'),
        ('复杂FIFO及复位取消','已验证有限工程范围','本轮Depth2与Depth5(实际8)、pipeline0/1；明确人工reset residue和tail loss故障，不能计原始presented bug成功。','scripts/research15_search_runtime.py','research15_search_20261015_r01/engineering_qualification/summary.json'),
        ('原生四组消融','仅实现，尚未执行','缺少通过资格检查的公共初始候选，且严格搜索treatment_witness为空；旧stat过程检查器四臂不能替代。','scripts/research15_native_experiment.py',None),
        ('最终冻结断言独立测试','尚未执行','没有接受版本；未生成或查看预定本轮holdout，不以历史工程测试替代。','scripts/research15_native_experiment.py',None),
        ('Ibex原始RTL案例','已验证模块级有限范围','#166新增，#54扩展新边界；手写原生SVA/独立ISA oracle，尚未纳入LLM细化。','scripts/research15_history.py','research15_history_20261015_r01/combined_summary.json'),
        ('六原始父Bug完整保护','未完成，0/6已证完整成功','stat来源接口不符；FIFO presented未见证；spill/intr部分语义unknown；其余未完成原生整体验收。',None,'research15_integration_20261015_r01/parent_status.json'),
    ]
    matrix=[dict(requirement=a,status=b,result=c,code=d,artifact=e) for a,b,c,d,e in rows]
    dump(OUT/'completion_matrix.json',matrix)
    dump(OUT/'results.json',dict(stage_complete=False,native=native,search=search,
        search_attribution=search_audit['per_method'],historical=history,
        parent_status=read(OUT/'parent_status.json'),costs=costs['per_owner'],model_costs=costs['model_totals'],
        formal_calls=0,monetary_cost=None,completion_matrix=matrix))
    lines=['# 2026-10-15 实际完成情况与续作结果','',
        '**整体任务尚未完成，期待的完整证据链尚未成立。** 本轮实际修改代码、调用本地模型、运行原生SVA和复杂FIFO搜索，并新增历史RTL复现。负结果、unknown及未执行项均保留。','',
        '## 完成矩阵','', '| 要求 | 状态 | 实际结果及限制 |','|---|---|---|']
    for a,b,c,_,_ in rows:lines.append(f'| {a} | {b} | {c} |')
    lines += ['', '## 真模型初始化与修改轨迹','',
        '同一 qwen2.5-coder:7b-instruct 实际调用3次。输入包含共享RTL、人工修复前后边界RTL、规格和义务；公开参考队列是工程脚手架。前两次公共初始化预算失败后，第三次作为单列额外时序修复，不能称原预算成功。', '',
        '| 版本 | 模型实际property | 合法误报 | 有效对照检出 | 首违例未检出 | 归因unknown | 结果 |',
        '|---|---|---:|---:|---:|---:|---|']
    for v in versions:
        c=v['counts'];prop=v['candidate']['assertions'][0]['property'].replace('|',r'\|')
        lines.append(f'| {v["model_call"]} | `{prop}` | {c["false_positives"]} | {c["detections"]} | {c["misses"]} | {c["unknown"]} | 拒绝 |')
    lines += ['', '每版798条“义务×采样周期”证据行，不是798笔事务或独立缺陷。第一版把当前输入sdata当输出，第二版错误使用下一拍，第三版仍下一拍并增加$past。全部可编译、可执行、有原生前件cover，却语义失败。原始第一版曾将同时误报合法对照的3个报警计检出，独立复核已更正为unknown；原始记录保留，拒绝结论不变。','',
        '原生前件cover从实际property提取，取消信任模型单独声明trigger；覆盖资格真实观察到2次触发、1次失败。12项接受门与13项适配器检查仅为逻辑资格，不算端到端成功。证据库拒绝遗漏历史记录、新FP、丢失已确认检出/触发及当前目标未修复。触发保留是有限观察代理，不能证明逻辑相关性或全局无退化。','',
        '逐版真实样本和原生失败：`evidence_examples.json`。完整模型请求/原始响应/usage、candidate.sva、TB、trace/oracle、wave.vcd、编译执行日志位于native目录。修正归属另存`native_readjudication/`，不覆写失败版本。','',
        '## 四法搜索：真实候选的负结果','',
        '4方法×2参数/种子×6查询=48查询；每查询同输入correct+4人工故障=240原生回放，另2次编译默认短执行。固定首个真实模型候选，未挑选较好的失败候选。Depth=2/pipeline=0及Depth=5/pipeline=1（RAM实际8）。所有数据均为开发数据。','',
        '| 方法 | 查询 | 同一误报类 | 独立漏报缺口类 | 对照检出事件 | 归因unknown事件 |','|---|---:|---:|---:|---:|---:|']
    for method,s in search_audit['per_method'].items():
        lines.append(f'| {method} | {s["queries"]} | {s["semantic_classes_by_kind"].get("false_positive",0)} | {s["independent_missed_gap_classes"]} | {s["event_classes"].get("causal_detection",0)} | {s["event_classes"].get("attribution_unknown",0)} |')
    lines += ['', '全部方法都找到同一误报类。零独立漏报缺口不代表保护完整：候选误报破坏合法前缀，目标归因大量unknown。普通/分歧方法少数对照检出只是一项reset-residue/order义务上的有限现象，不消除该候选的合法误报。契约策略没有显示优势。工具/输入unknown查询为0，与上述归因unknown不是同一指标。','',
        '契约策略已按本方法历史义务检查、有效cover和检出缺口更新下一测试选择；选择前状态、反馈可见范围及原始结果均保存。442项预算/输入/冻结候选/策略状态审计通过。单property没有候选分歧对，该臂明确退化为均匀探索；不能代替旧11对完整比较。','',
        '工程资格实际验证了跨复位残留（接受5→取消28→复位解除后重现30）及四次请求丢最后一个响应的tail-loss。它们是人工边界故障，工程SVA不冒充模型产物。契约搜索的tail-loss输入确有独立oracle违例，但模型在合法对照上也报警，故`treatment_witness.json`为null，不能构造成功细化链。','',
        '## 原始历史RTL与规格审计','',
        '- Ibex #166：固定前后提交原始decoder字节与补丁吻合；115事务、458采样×3配置，每版本1374检查。before423违例/42事务，after0；两条修复义务均有代表。423不是423个Bug。',
        '- Ibex #54：119条此前223边界+5锚点中未出现的低16编码；32条C.SLLI rd=x0 HINT before违例、after0；87条控制前后通过。另5条旧锚点单列。',
        '- 以上使用手写原生SVA及独立ISA oracle，属于原始模块复现；尚非LLM生成断言独立验证，更不是全核或形式证明。',
        '- stat标注的真实上游是AXI统计模块，不含本地frame_done/stat_valid四信号接口，无法确认本地两拍示例的历史映射及重叠语义。继续unknown。',
        '- 35条历史筛选记录中其余33条未执行；FIFO presented、spill invalid-payload及intr mask/timing继续保留未确认状态。','',
        '## 成本、数据与复现','',
        f'本轮模型3次全部返回：输入{costs["model_totals"]["known_prompt_tokens"]} tokens，输出{costs["model_totals"]["known_completion_tokens"]} tokens；约{costs["model_totals"]["known_wall_seconds"]:.2f}秒，无重试。形式化调用0，金额/能耗不可用。', '',
        '| 模块 | 实际编译 | 实际执行 | 编译墙时秒 | 执行墙时秒 |','|---|---:|---:|---:|---:|']
    for owner,c in costs['per_owner'].items():
        lines.append(f'| {owner} | {c["compile"]["attempts"]} | {c["simulation"]["attempts"]} | {c["compile"]["known_wall_seconds"]:.3f} | {c["simulation"]["known_wall_seconds"]:.3f} |')
    lines += ['', '物理成本包括工程/tool资格及编译附带的短执行，查询预算另算；不把编译缓存重复收费。onehot/Depth0仅4次旧输入回归，结果一致。旧49项封存清单哈希不变。工作区无有效Git HEAD，交付源码快照以SHA256标识；首两次初始化适配器进程版本与事后源码快照不混称，详见重审记录。','',
        '统一入口（在仓库目录运行；NEW_*替换为未使用目录名）：','',
        '```powershell',
        'wsl -- python3 scripts/research15_pipeline.py audit',
        'wsl -- python3 scripts/research15_pipeline.py qualify',
        'wsl -- python3 scripts/research15_pipeline.py report',
        'wsl -- python3 scripts/research15_pipeline.py search --run NEW_SEARCH --candidate deliverables/research15_native_20261015_r01/model_calls/initial/candidate.json --budget 6',
        'wsl -- python3 scripts/research15_pipeline.py native --run NEW_NATIVE --stage initial',
        'wsl -- python3 scripts/research15_pipeline.py native --run NEW_NATIVE --stage qualify',
        'wsl -- python3 scripts/research15_pipeline.py native --run NEW_NATIVE --stage temporal',
        'wsl -- python3 scripts/research15_pipeline.py history --run NEW_HISTORY --stage prepare',
        'wsl -- python3 scripts/research15_pipeline.py history --run NEW_HISTORY --stage run',
        'wsl -- python3 scripts/research15_pipeline.py history --run NEW_HISTORY --stage report',
        '```','',
        '模型命令会真实调用本地Ollama。统一调度器复用本轮实际运行模块；新调度分支未额外重复昂贵模型实验。没有shared_initial时baseline/arms应停止，不能把unqualified候选默认为接受。','',
        '## 未完成与具体阻塞','',
        '1. 真实FIFO局部order初始SVA仍未合格，三个实际模型输出分别错误处理数据身份/采样时刻；这不是凭据缺失或工具不能编译。下一阶段应针对生成接口/采样语义改进，并保持真实反馈轨迹。',
        '2. 原生四组消融仅代码存在，尚未执行；公共初始资格失败且有效treatment为空。不能用旧stat过程检查器实验或本轮工程SVA代替。',
        '3. 没有可接受的最终集合，所以新冻结独立测试未执行。旧全部观测属开发数据，历史119新向量不冒充学习后holdout。',
        '4. 六原始父Bug完整保护仍0/6得到本流程确认；义务局部结果、工程故障和原始历史模块复现分开统计。通用远程模型、原生形式化和更多历史案例仍未验证。',
        '5. 证据链停在“无法得到可接受初始模型断言/可用搜索细化见证”；尚不能证明两个机制在自动细化后保留历史有效保护并通过新独立场景。框架保持不变，不修改成功标准。','']
    (OUT/'REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    (NATIVE/'REPORT.md').write_text('# Native model experiment\n\nAll three actual model candidates were rejected. See `summary.json` and the integrated report at `../research15_integration_20261015_r01/REPORT.md` for authoritative readjudicated counts. Four-arm native ablation and final independent testing were not executed.\n')
    print(json.dumps(dict(report=str(OUT/'REPORT.md'),whole_task_complete=False)))


def seal():
    snapshot=OUT/'delivery_source_snapshot';snapshot.mkdir(exist_ok=True)
    sources={}
    for path in sorted((ROOT/'scripts').glob('research15_*.py')):
        shutil.copy2(path,snapshot/path.name)
        sources[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
    dump(OUT/'source_manifest.json',dict(files=sources,scope='Delivery source state; actual executed TB and command logs remain in each run. Not a retroactive execution-version claim.'))
    index=[]
    for owner in ('native','search','history','regression'):
        base=ROOT/f'deliverables/research15_{owner}_20261015_r01'
        for directory,dirs,files in os.walk(base):
            dirs[:]=[d for d in dirs if d not in ('obj_dir','tools','source_snapshot','execution_source_snapshot','__pycache__')]
            folder=Path(directory)
            if 'replay.json' in files:
                index.append(dict(owner=owner,type='actual_native_replay',path=str((folder/'replay.json').relative_to(ROOT)),
                    sha256=hashlib.sha256((folder/'replay.json').read_bytes()).hexdigest(),split='development'))
    with (OUT/'evidence_index.jsonl').open('w',encoding='utf-8') as stream:
        for item in index:stream.write(json.dumps(item)+'\n')
    dump(OUT/'evidence_index_summary.json',dict(replay_references=len(index),distinct_findings_claim=False,
        historical_evidence='See history combined_summary.json/transactions.json and ibex54_new_boundaries; separate ISA format.',
        final_llm_independent_test_references=0))
    files=[p for p in OUT.glob('*') if p.is_file() and p.name!='delivery_manifest.json']
    for base in (NATIVE,SEARCH,HISTORY):files += [p for p in base.glob('*') if p.is_file() and p.suffix in ('.json','.md')]
    dump(OUT/'delivery_manifest.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(files))})
    print(json.dumps(dict(source_files=len(sources),replay_references=len(index),manifest_files=len(set(files)))))


if __name__=='__main__':report()
