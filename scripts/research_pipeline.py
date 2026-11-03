"""Unified CLI for the 2026-10-14 continuation and honest result aggregation.

Use WSL python3. Stage runs create new namespaces; report only reads experiments.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/research_integration_20261014_r01'


def read(p, default=None):
    return json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else default


def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def seal():
    checks=[]
    for name in ('research_gate_20261014_r01/freeze.json','research_gate_20261014_r01/final_freeze.json',
                 'research_search_20261014_r01/freeze.json'):
        manifest=read(ROOT/'deliverables'/name)
        for path,expected in manifest.items():
            actual=hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
            checks.append(dict(path=path,passed=actual==expected))
    native=ROOT/'deliverables/research_native_20261014_r01/compact_continuation'
    nf=read(native/'freeze.json')
    expected=nf.get('sha256',nf.get('sva_sha256'))
    if expected is None:
        # The native freeze schema uses frozen_sva_sha256 in some versions.
        expected=nf.get('frozen_sva_sha256')
    checks.append(dict(path=str((native/'frozen_proposal.sva').relative_to(ROOT)),
        passed=hashlib.sha256((native/'frozen_proposal.sva').read_bytes()).hexdigest()==expected))
    result=dict(passed=all(c['passed'] for c in checks),checks=checks,
        scope='Frozen inputs/candidates/executed source snapshots; full search raw artifacts separately audited.')
    dump(OUT/'freeze_integrity.json',result)
    assert result['passed'], 'frozen_artifact_changed'
    paths=[p for p in OUT.glob('*') if p.is_file() and p.name!='delivery_manifest.json']
    for name in ('research_fifo_20261014_r01','research_search_20261014_r01','research_gate_20261014_r01',
                 'research_native_20261014_r01','research_ibex_20261014_r01'):
        base=ROOT/'deliverables'/name
        paths += [p for p in base.glob('*.json') if p.is_file()]
        paths += [p for p in base.glob('*.md') if p.is_file()]
    dump(OUT/'delivery_manifest.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(set(paths))})
    print(json.dumps(dict(freeze_checks=len(checks),passed=True,indexed_delivery_files=len(set(paths)))))


def gate_report():
    base=ROOT/'deliverables/research_gate_20261014_r01'
    checkpoints=[read(p) for p in sorted(base.glob('development/*/checkpoint_*.json'))]
    calls=[read(p) for p in sorted(base.glob('models/*/*/result.json'))]
    queries=[json.loads(z) for z in (base/'queries.jsonl').read_text().splitlines()] if (base/'queries.jsonl').exists() else []
    result=dict(completed_model_calls=len(calls),call_status=dict(collections.Counter(c['status'] for c in calls)),
        decisions=[dict(arm=c['arm'],round=c['round'],accepted=c['accepted'],model_status=c['model_status'],
                        gate_enabled=c['gate_enabled'],gate_reasons=c['gate_assessment']['reasons']) for c in checkpoints],
        independent_test=read(base/'independent/summary.json'),
        costs=dict(model_calls=len(calls),model_retries=sum(c.get('retries',0) for c in calls),
            known_prompt_tokens=sum(c.get('prompt_tokens') or 0 for c in calls),
            known_completion_tokens=sum(c.get('completion_tokens') or 0 for c in calls),
            token_unavailable_calls=sum(c.get('prompt_tokens') is None or c.get('completion_tokens') is None for c in calls),
            model_wall_seconds=sum(c['wall_seconds'] for c in calls),queries=len(queries),
            **{n:sum(q.get(n,0) for q in queries) for n in ('compile_attempts','simulation_attempts','sim_cycles','cpu_seconds','wall_seconds')},
            formal_calls=0,monetary_cost=None),
        limitation='Procedural checker only. Stat overlap is a conditional engineered contract, not upstream-confirmed. Trigger relevance is an evaluation proxy, not entailment. Gate repairs one designated gap and preserves confirmed replay protection, not all missed obligations.',
        feedback_limitation='r01 parser errors retained; plain arms receive status but not detailed offending identifier on next call. This is a documented interface limitation, not mechanism superiority evidence.')
    result['config_errata']=read(base/'config_errata.json')
    perarm=[]
    for arm in 'ABCD':
        qs=[q for q in queries if q.get('label','').startswith('gate/'+arm+'/')]
        cs=[c for p in base.glob('models/'+arm+'/*/result.json') for c in [read(p)]]
        perarm.append(dict(arm=arm,model_calls=len(cs),known_input_tokens=sum(c.get('prompt_tokens') or 0 for c in cs),
            known_output_tokens=sum(c.get('completion_tokens') or 0 for c in cs),
            development_queries=len(qs),compile_attempts=sum(q['compile_attempts'] for q in qs),
            simulation_attempts=sum(q['simulation_attempts'] for q in qs),
            accepted=sum(c['accepted'] for c in checkpoints if c['arm']==arm)))
    result['per_arm_costs']=perarm
    denominators={}
    for q in queries:
        parts=q.get('label','').split('/')
        if len(parts)!=5 or parts[0]!='independent':continue
        _,arm,version,cohort,scenario=parts
        key='/'.join((arm,version,cohort))
        counts=denominators.setdefault(key,dict(scenarios=0,legal_control_samples=0,first_target_events=0,later_target_events=0,unknown_queries=0))
        counts['scenarios']+=1
        counts['unknown_queries']+=q['status']!='ok'
        for rr in q['runs']:
            oracle=read(ROOT/rr['run']/'independent_reference.json',{})
            for e in oracle.get('events',[]):
                if rr['variant']=='correct':counts['legal_control_samples']+=bool(e['legal_prefix'])
                elif any(not c['conditional'] and not c['passed'] for c in e['checks']):
                    counts['first_target_events' if e['first_violation'] else 'later_target_events']+=1
    result['independent_denominators']=denominators
    return result


def report():
    OUT.mkdir(exist_ok=True)
    fifo=read(ROOT/'deliverables/research_fifo_20261014_r01/summary.json')
    search=read(ROOT/'deliverables/research_search_20261014_r01/summary.json')
    native=read(ROOT/'deliverables/research_native_20261014_r01/summary.json')
    if native is None:native=read(ROOT/'deliverables/research_native_20261014_r01/closed_loop/summary.json')
    probes=read(ROOT/'deliverables/research_native_20261014_r01/probes_r02/result.json')
    ibex=read(ROOT/'deliverables/research_ibex_20261014_r01/summary.json')
    gate=gate_report()
    summary=dict(date='2026-10-14',scope='stage continuation; not all requested research completed',fifo=fifo,search=search,
        native=native,native_probes=probes,gate=gate,ibex=ibex,
        full_parent_passes=0,repository_commit=None,
        repository_version_reason='Workspace .git is empty; use source hashes and frozen snapshots.',
        pending=['Native four-arm search x non-regression factorial on complex FIFO not executed.',
            'Full confirmed repair-obligation coverage for six parent bugs and generated assertions on historical Ibex not established.',
            'spill invalid-payload and intr mask semantics remain unresolved; stat overlap historical semantics unconfirmed.',
            'FIFO presented original defect remains unknown without a definitive original-target violation witness.',
            'Contract search remains a finite scheduling policy, not a complete general obligation-solving engine.',
            'No formal proof runs; supported native SVA simulation is bounded to Verilator feature subset.',
            'No additional historical bug admitted beyond freshly replayed Ibex #54.'])
    dump(OUT/'results.json',summary)
    dump(OUT/'gate_results.json',gate)
    if native and native.get('model_cost'):
        nc=native['model_cost'];gc=gate['costs']
        model_cost=dict(actual_attempts=gc['model_calls']+nc.get('actual_attempts',0),
            completed_responses=gc['model_calls']+nc.get('completed_calls',0),cancelled_attempts=nc.get('cancelled_calls',0),
            known_prompt_tokens=gc['known_prompt_tokens']+nc.get('known_prompt_tokens',0),
            known_completion_tokens=gc['known_completion_tokens']+nc.get('known_completion_tokens',0),
            usage_unavailable_attempts=gc['token_unavailable_calls']+nc.get('unknown_usage_attempts',0),
            total_prompt_tokens=None,total_completion_tokens=None,monetary_cost=None,
            scope='All actual model attempts in gate r01 and native initial/aborted/compact continuation; none in search/FIFO engineering/Ibex replay.')
        dump(OUT/'model_costs.json',model_cost)
    matrix=[
        dict(requirement='four_policy_search_11_pairs',status='verified_bounded' if search else 'incomplete',
             code='scripts/research_search_compare.py',command='research_pipeline.py search --run NEW --action prepare/run/report',artifact='research_search_20261014_r01',
             limit='procedural diagnosis; finite template/exposure policy; no superiority shown'),
        dict(requirement='complex_fifo',status='verified_bounded' if fifo else 'incomplete',
             code='scripts/research_fifo_experiment.py',command='research_pipeline.py fifo --run NEW',artifact='research_fifo_20261014_r01',
             limit='artificial boundary faults; depth3 rounds4; reset residue mutation missing'),
        dict(requirement='real_model_native_sva_loop',status='executed_with_recorded_outcomes' if native else 'incomplete',
             code='scripts/research_native_closed_loop.py',command='research_pipeline.py native --run NEW',artifact='research_native_20261014_r01/closed_loop',
             limit='status/acceptance must be read from summary; interrupted oversized request counted; compact continuation separate; simulation only; not native 2x2 ablation'),
        dict(requirement='four_arms_with_acceptance_gate',status='executed_with_recorded_failures' if gate['independent_test'] else 'partially_executed',
             code='scripts/research_gate_experiment.py',command='research_pipeline.py gate --run NEW --action prepare/develop/acceptance',artifact='research_gate_20261014_r01',
             limit='stat conditional scoped contract; procedural checker; 5 model interface errors; actual cost differs'),
        dict(requirement='generic_remote_provider',status='implemented_only',code='scripts/research_native_closed_loop.py',
             command='--provider openai_compatible --endpoint URL --key-env ENV_NAME',artifact=None,
             limit='not run; no configured remote provider used; local Ollama alone verified'),
        dict(requirement='ibex_original_reproduction',status='verified_bounded' if ibex and ibex['all_expected_reproduced'] else 'incomplete',
             code='scripts/research_historical_replay.py',command='research_pipeline.py ibex --run NEW',artifact='research_ibex_20261014_r01',
             limit='4 historical tests only; not model-generated SVA protection'),
        dict(requirement='full_requested_evidence_chain_all_parents',status='incomplete',code=None,command=None,artifact=None,
             limit=summary['pending'])]
    dump(OUT/'completion_matrix.json',matrix)
    files=sorted(ROOT.glob('scripts/research_*.py'))
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    for p in files:
        target=OUT/'source_snapshot'/p.name;target.parent.mkdir(exist_ok=True)
        target.write_bytes(p.read_bytes())
    dump(OUT/'source_manifest.json',manifest)
    with (OUT/'gate_costs.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(gate['per_arm_costs'][0]));w.writeheader();w.writerows(gate['per_arm_costs'])
    lines=['# 2026-10-14 研究与实现续作报告','',
        '这是有实际运行产物的阶段性交付，未宣称全部研究完成。旧目录和旧负结果保留。工作区 `.git` 为空，Git 版本不可得；新代码快照与 SHA256 见 source_manifest.json。',
        '', '## 核查及实际改动','',
        '- 历史已有真实 Ollama 请求/响应、11对候选、四组实验和 Ibex 原始RTL回放，不能重新包装为本轮首次完成。',
        '- 历史接受逻辑仅检查能否执行，未拒绝语义退化；旧C/D也不是独立的防退化开关。本轮新增稳定证据键的集合接受门和真正搜索×门的2×2实验。',
        '- 原生工具由本轮局部解包的 Verilator 5.020 提供；保留初次路径配置失败及修正后的资格检查。Icarus过程检查器结果与原生SVA结果分表。',
        '- 复用真实 axis_fifo RTL、原独立监视器、模型流式接口与旧候选，新增复杂FIFO、四法搜索、原生闭环、统一入口和历史复跑，不改旧封存内容。',
        '', '## 搜索比较：同池、同种子、同查询预算','',
        '每方法216查询（6父×3种子×12）；每查询执行buggy/fixed。所有查询均属于开发数据。缺口键按父案例、候选、FP/FN和义务去重；不是独立Bug数。普通差分的波形差异仅作搜索奖励，必须经独立契约裁定才计有效证据。',
        '', '| 方法 | 去重候选缺口 | 区分11对 | 规格unknown查询/216 |','|---|---:|---:|---:|']
    if search:
        for name,r in search['per_method'].items():lines.append(f"| {name} | {r['gaps']} | {r['pairs']}/11 | {r['unknown_spec_queries']}/216 |")
    lines+=['', '契约策略相对普通差分在spill增加一个collision_empty漏报缺口，同时在filter少找到一个qualified_value缺口。本轮不支持契约策略总体优于普通差分。逐对新增与遗漏、重复、代表原始证据见 [搜索报告](../research_search_20261014_r01/REPORT.md)、[逐对结果](../research_search_20261014_r01/pair_results.json)、[真实见证示例](../research_search_20261014_r01/EVIDENCE_EXAMPLES.md)。',
        '', 'stat原始文字支持两拍延迟及原长度，但没有明确重叠允许语义；搜索将相关查询降为unknown。过程检查器unsupported和空触发仍在分母：10944项中576 unsupported、10042有触发、326空触发。',
        '', '## 复杂FIFO与原生SVA','',
        'FIFO以 valid && ready 握手识别接受，独立队列按顺序配对响应，显式记录accept_cycle/response_cycle/latency/reset取消。背压下仅呈现请求不计接受。请求Depth=2/3/4，实际RAM容量分别2/4/4，不能把Depth=3视为新的容量；流水级另占存储。',
        f"96次Icarus RTL执行：24个correct运行无执行范围内违例，72个明确人工边界故障有合法同激励对照，去重后4类mutation/obligation缺口。新种子开发/工程独立测试各48次；不是LLM最终断言通过96次。详见 [FIFO报告](../research_fifo_20261014_r01/REPORT.md)。",
        '', '两次原生工程控制展示负例：next-cycle有效断言在correct上9次误报；稳定性断言38次触发且无失败，却漏掉64次payload违例。这些SVA来自工程控制，不冒充模型产物。[逐事务例子](../research_fifo_20261014_r01/supplement/NATIVE_EXAMPLE.md)。复位取消经过正常轨迹，但未注入专门跨复位残留故障。',
        '', '原生工具资格检查：正向 |=>、反向 |=>、$past 已实际运行；合法 ##2 sequence 在该工具不支持，不能归为模型语法错误。首次配置路径失败保留于probes，修复后见probes_r02。仿真无违例不是形式证明。',
        '', '### 真实模型→原生SVA闭环','']
    if native:
        lines += ['结果来自独立的真实FIFO人工故障轨迹，与过程检查器消融分开。请求含共享RTL、修复前后边界RTL、Bug含义、协议和已声明义务。使用公开辅助队列状态，工程脚手架不属于模型自动推导成果。',
            '', '```json',json.dumps({k:native.get(k) for k in ('status','initial','final_development','independent_test','attribution_unknown','unprotected_obligations','frozen_sva_sha256','model_cost','native_cost')},ensure_ascii=False,indent=2),'```',
            '', '原始请求、响应、每版SVA、原生编译/执行命令、拒绝理由、冻结和独立结果见 [native汇总](../research_native_20261014_r01/summary.json) 和 [完整报告](../research_native_20261014_r01/REPORT.md)。初始真实候选位于closed_loop，过长revision调用取消并保留；compact_continuation是单独增加的第三次尝试，不能称原2调用预算成功。触发计数是诊断标记，不是native cover证明；同周期报警不足以记因果检出。',
            '', '真实初始性质 `mdata[0] == $past(mdata[0])` 把顺序约束误解成跨周期bit稳定，且模型trigger与无前件性质不对应。紧凑续作生成三条重复的相同性质，未增加互补保护。原生编译执行成功不等于义务验收成功；没有可接受版本时冻结测试仅为诊断。归因复核区分合法前缀FP和已有违例后的未知报警，原始计数不覆盖。']
    else:lines+=['仍在运行/尚无完整summary；不得将代码或工程资格检查计为模型闭环完成。']
    lines += ['', '## 防退化集合接受与2×2实际消融','',
        'A=普通反馈；B=普通反馈+新契约证据；C=普通反馈+接受门；D=两者。每组同一初始自然候选、同一模型采样配置、2次真实调用；模型新增证据仅本组可见。所有组都支付自己的历史重放，C/D将检查结果用于拒绝。',
        '', '| 组 | 模型调用 | 输入/输出tokens | 开发查询 | 接受提案 |','|---|---:|---:|---:|---:|']
    for r in gate['per_arm_costs']:
        lines.append(f"| {r['arm']} | {r['model_calls']} | {r['known_input_tokens']}/{r['known_output_tokens']} | {r['development_queries']} | {r['accepted']} |")
    lines += ['', '统计包含接口失败，实际tokens/查询不强行对齐。A/C候选错误未执行提案重放，因此少付查询成本；D反馈包含拒绝信息，会增加提示tokens。r01普通组的下一轮只含错误状态而缺具体越权identifier；不能把错误失败归为搜索机制劣势。运行后已修复未来实验的错误反馈和配置字段，只验证prepare流程，未混入r01结果。config_errata.json列出不可变config内继承过时字段；实际成本以query ledger为准。r01执行源码以该实验目录根部冻结.py为准。',
        '', '实际轨迹：原stat断言为 `frame_done_i |-> stat_valid_o`。模型提案加入 `frame_done_i |-> ##2 stat_len_o` 及以 `rst_ni` 为前件的valid/length检查，未正确比较捕获长度，产生新误报。B允许可执行提案替换；D第0轮实际拒绝并保留原版本。详见 development/*/checkpoint_*.json（含每条新增FP证据键、当前目标、模型原因与重放映射）。',
        '', '接受门只保证指定本轮缺口和已确认历史保护在已重放证据范围内；effective_triggers是输出相关求值代理，不证明语义蕴含。非目标未归因报警、后续事务和未覆盖义务仍需单列，不得宣称全局防退化或父Bug通过。stat试验依赖工程化重叠契约，仅条件实验；不是原历史规格已确认。',
        '', '### 冻结后的新测试（过程检查器、条件stat范围）','',
        '| 组 | 队列 | 初始→最终FP | 初始→最终首次FN | 最终因果检出 | 最终归属unknown |','|---|---|---:|---:|---:|---:|']
    for r in gate['independent_test'] or []:
        a,b=r['initial'],r['final']
        den=gate['independent_denominators'].get('/'.join((r['arm'],'final',r['cohort'])),{})
        lines.append(f"| {r['arm']} | {r['cohort']} | {a['fp']}→{b['fp']}/{den.get('legal_control_samples','?')} | {a['first_misses']}→{b['first_misses']}/{den.get('first_target_events','?')} | {b['causal_detections']} | {b['attribution_unknown']} |")
    lines += ['', '6条新37周期序列在细化前隔离保存，最终哈希冻结后才执行；初始/最终×4组×2故障队列共96次配对查询。新payload故障为人工故障；无独立测试反馈进入模型。若后续据此修改，这批数据必须转为开发数据。',
        '', '所有组因果确认检出为0，原始目标/新数据故障分别有146/97个违例采样的报警归属unknown（各含18个首次违例）；因此零first_misses不是零漏报。stat区块没有已确认的历史成功检出可供保持，只验证了拒绝新增误报的执行作用。B0/D0请求与响应逐字相同，D0拒绝了69个新增误报证据键；C全部是接口拒绝，不能作为语义接受门成功。两故障队列重复使用相同合法控制，198合法采样不能跨队列相加当新独立样本。[只读审计](audit_gate.json)。',
        '', '## 六父与历史RTL状态（不排除困难项）','',
        '| 父案例 | 本轮范围 | 完整保护 |','|---|---|---|',
        '| onehot | 仅搜索回归 | 本轮未做新独立整体验收 |',
        '| filter | 四法新搜索；契约相对差分遗漏一项 | 未建立 |',
        '| FIFO presented/Depth0 | 搜索回归，见证仅idle；presented原始目标缺见证 | unknown |',
        '| spill | collision_empty可判定；invalid payload未决 | unknown |',
        '| stat | isolated scoped搜索；重叠条件模型实验 | 原始完整时序规格未确认，未通过 |',
        '| intr | mask采样语义未决，保留两对unknown | unknown |',
        '| Ibex #54（另列真实案例） | 新复跑4个原始RTL/测试组合全部符合前失败后通过且日志一致 | 原始回归可复现；生成SVA完整保护未建立 |',
        '', 'Ibex来源PR #54，base cd15ce88beba8ed8496f414af361f664764f47e2，fix 687952e42f3eff68348770ae0c55bc5c0f036d3e，merge 5319734180ac4844e43d31ad19dc108aac503037。保存的来源、文件哈希和新命令见 [Ibex复跑](../research_ibex_20261014_r01/summary.json)。不能把复杂FIFO边界人工故障并入真实历史成功率。',
        '', '## 复现命令','',
        '从 `D:\\AssertionForge-main1` 的 PowerShell 运行；NEW目录必须未使用。原生工具沿用当前产物tools，迁移环境须重新配置VERILATOR。',
        '', '```powershell',
        'wsl -- python3 scripts/research_pipeline.py report',
        'wsl -- python3 scripts/research_pipeline.py qualify',
        'wsl -- python3 scripts/research_pipeline.py fifo --run research_fifo_NEW',
        'wsl -- python3 scripts/research_pipeline.py search --run research_search_NEW --action prepare',
        'wsl -- python3 scripts/research_pipeline.py search --run research_search_NEW --action run',
        'wsl -- python3 scripts/research_pipeline.py search --run research_search_NEW --action report',
        'wsl -- python3 scripts/research_pipeline.py gate --run research_gate_NEW --action prepare',
        'wsl -- python3 scripts/research_pipeline.py gate --run research_gate_NEW --action develop',
        'wsl -- python3 scripts/research_pipeline.py gate --run research_gate_NEW --action acceptance',
        'wsl -- python3 scripts/research_pipeline.py native --run research_native_NEW',
        'wsl -- python3 scripts/research_pipeline.py ibex --run research_ibex_NEW','```',
        '', '如需严格复现旧r01 stat运行而非修正后的入口，使用该产物目录根部的冻结脚本并设置 `PYTHONPATH=/mnt/d/AssertionForge-main1/scripts`，指定新--run；原模型服务、digest与工具版本仍须匹配。不要重用已消耗测试来开发新版本。',
        '', '全部成本见results.json/gate_costs.csv及各子实验命令日志。搜索1728编译+1728仿真；并行运行wall_seconds之和不是实际历时。未知金额、token、CPU均标null/不可用，不当作零成本。形式化调用为0。',
        '', '## 未完成与具体限制','']
    lines += ['- '+v for v in summary['pending']]
    lines += ['', '模型总成本另见model_costs.json：11次实际尝试（10次返回、1次取消），已知输入/输出tokens为43697/1583，取消调用用量不可得。',
        '', '未来native统一入口现调用research_native_safe.py：完整RTL/规格不变，反馈每类2代表并保留总数和外部全量记录；加入上下文预算预检。本次只静态核验请求从56482字节缩至30635字节，新增调用0次，不计为修复实验成功。']
    lines += ['', '下一阶段应在支持的原生SVA子集上做复杂FIFO完整四组实验，补专门复位残留故障与更多历史RTL案例；stat/spill/intr需要可靠规格依据。单次局部改善、工程控制和已重放历史保护均不能替代上述完成标准。']
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(fifo_complete=fifo is not None,search_complete=search is not None,native_complete=native is not None,
        gate_calls=gate['completed_model_calls'],gate_independent=gate['independent_test'] is not None,ibex_replayed=bool(ibex and ibex['all_expected_reproduced'])),ensure_ascii=False))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage',choices=['report','index','seal','gate','fifo','search','native','ibex','qualify'])
    ap.add_argument('--action',choices=['prepare','develop','acceptance','run','report'],default='run')
    ap.add_argument('--run',help='New output namespace, required for actual experiments')
    a=ap.parse_args()
    if a.stage=='report':report();return
    if a.stage=='seal':seal();return
    if a.stage=='index':
        raise SystemExit(subprocess.call([sys.executable,str(ROOT/'scripts/research_evidence_index.py')],cwd=ROOT))
    if a.stage=='qualify':argv=[sys.executable,str(ROOT/'scripts/research_gate_qualification.py')]
    else:
        if not a.run:ap.error('--run is required to prevent accidental overwrite of saved experiments')
        if Path(a.run).name!=a.run:ap.error('--run must be a single directory name')
        folder=ROOT/'deliverables'/a.run
        if a.stage=='gate':argv=[sys.executable,'scripts/research_gate_experiment.py',a.action,'--run',a.run]
        elif a.stage=='search':argv=[sys.executable,'scripts/research_search_cli.py','--run',a.run,a.action]
        elif a.stage=='native':argv=[sys.executable,'scripts/research_native_safe.py','--out',str(folder)]
        elif a.stage=='fifo':
            if folder.exists():ap.error('FIFO output already exists; choose a new --run')
            argv=[sys.executable,'scripts/research_fifo_experiment.py','--out',str(folder)]
        else:argv=[sys.executable,'scripts/research_historical_replay.py','--out',str(folder)]
    print('EXEC',json.dumps(argv),flush=True)
    raise SystemExit(subprocess.call(argv,cwd=ROOT))


if __name__=='__main__':main()
