"""Append-only delivery, physical-cost recount and record-level repro packages."""
import argparse
import collections
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import shutil
import time
import datetime
import hashlib
import os
import obligation_isolated_search as iso
from obligation_isolated_search import x


def report_search():
    # Report-only parallel file reads speed up the Windows-mounted filesystem.
    # Every byte is still rehashed. No search cache or unbilled oracle call.
    previous=x.read(x.OUT/'block_r02/prior_artifact_hashes.json')
    start=time.perf_counter();original=x.sha
    paths=list(previous)
    with ThreadPoolExecutor(max_workers=16) as pool:
        values=list(pool.map(lambda p:original(x.ROOT/p),paths))
    actual=dict(zip(paths,values))
    x.dump(x.OUT/'block_r02/prior_rehash.json',dict(files=len(paths),wall_seconds=time.perf_counter()-start,
        changed=[p for p in paths if actual[p]!=previous[p]],method='fresh SHA256 of every file, 16 reader threads, report-only',
        search_cache_hits=0))
    def cached(p):
        rel=x.rel(p)
        return actual[rel] if rel in actual else original(p)
    x.sha=cached
    iso.report()
    x.sha=original


def diagnostics():
    iso.configure();folder=x.OUT/'diagnostics';folder.mkdir(exist_ok=False)
    ledger=x.read(x.OUT/'problem_ledger_complete.json');out=[]
    for row in ledger:
        r=copy.deepcopy(row)
        r['tool_versions']=x.rel(x.OUT/'protocol.json')
        r['original_random_seed']='see original run input and protocol; unavailable per-cell seed is not inferred'
        r['review_budget_cost_scope']='physical reused baseline and new diagnostic runs counted separately; do not sum shared run cost per method-cell'
        r['cpu_cost_original']=None
        r['locating_evidence']='concrete independent trace evidence' if r['findings'] else 'tool diagnostic/spec ambiguity; no semantic failure inferred'
        if r['findings']:
            ev=min(r['findings'],key=lambda e:e['cycle']);source=x.ROOT/ev['run']
            d=x.read(source/'definition.json');cs=x.read(source/'candidates.json')
            inputs=x.read(source/'input.json')[:ev['cycle']+1]
            original_trace=x.read(source/'trace.json')[:ev['cycle']+1]
            raw_source=x.read(x.ROOT/next(z['original'] for z in r['replays'] if z['replay']==ev['run'])/'result.json')
            variant=raw_source.get('variant','correct')
            raw=x.engine.execute_run(d,inputs,cs,'diagnostics/'+r['record_id'],variant)
            dest=x.ROOT/raw['run_id']
            a=x.adjudicate_folder(dest,d) if raw['status']=='ok' else dict(status=raw['status'])
            x.dump(dest/'adjudication.json',a)
            exact=a['status']=='ok' and x.read(dest/'trace.json')==original_trace
            assert exact,r['record_id']
            witness=[e for group in a['evidence'] for e in group if e['kind']==ev['kind'] and e['cycle']==ev['cycle']]
            assert witness,r['record_id']
            r.update(reproduction=x.rel(dest),reproduction_command='sh '+x.rel(dest/'reproduce.sh'),
                witness_cycle=ev['cycle'],expected_and_actual=ev['obligations'],
                minimal_input=x.rel(dest/'input.json'),cycle_trace=x.rel(dest/'trace.json'),waveform=x.rel(dest/'wave.vcd'),
                prefix_execution_exact=True,minimality='shortest observed finding in this record; truncated prefix actually rerun; not globally deletion-minimal')
        else:
            r.update(reproduction=None,minimal_input=None,cycle_trace=None,
                missing_evidence='unsupported candidate execution' if 'checker_or_execution_problem' in r['categories'] else 'authoritative resolved specification / independently adjudicable trace',
                minimality='unknown: no definite semantic witness; original complete attempts retained')
        out.append(r)
    x.dump(folder/'problem_ledger.json',out)
    x.dump(folder/'summary.json',dict(records=len(out),original_states=dict(collections.Counter(r['original_status'] for r in out)),
        classes=dict(collections.Counter(r['reclassified_status'] for r in out)),actual_prefix_reproductions=sum(r.get('prefix_execution_exact',False) for r in out)))
    print(json.dumps(x.read(folder/'summary.json')))


def deliver():
    for required in ['trace_audit/refinement_budget.json','refinement_r04/heldout/summary.json',
                     'refinement_r04/regression_audit/summary.json','fault_holdout_r04/evaluation/results.json',
                     'reset_sensitivity/summary.json','async_history_qualification/result.json','minimal_search/index.json']:
        assert (x.OUT/required).exists(),'not yet executed: '+required
    assert len(list((x.OUT/'refinement_r04').glob('models/*/*/*/result.json')))==24
    folder=x.OUT/'delivery';folder.mkdir(exist_ok=False)
    parents=x.read(x.OLD/'parent_results.json');ledger=x.read(x.OUT/'diagnostics/problem_ledger.json')
    summaries=x.read(x.OUT/'analysis_r02/parent_method_results.json')
    # Scan only concrete command records in this run. Each pathname is counted
    # once, regardless of how many ledger cells or evidence rows reference it.
    physical=[]
    command_paths=list(x.OUT.rglob('*.command.json'))
    with ThreadPoolExecutor(max_workers=16) as pool:
        command_records=list(pool.map(x.read,command_paths))
    for p,r in zip(command_paths,command_records):
        argv=r.get('argv',[])
        if not argv:continue
        tool=Path(argv[0]).name
        if tool not in ('iverilog','vvp'):continue
        path=x.rel(p)
        if '/runs/search/' in path:phase='search'
        elif '/runs/reset_sensitivity/' in path:phase='focused_reset_search'
        elif '/runs/reset_identifier_diagnostic/' in path:phase='post_freeze_reset_identifier_frontend_diagnostic'
        elif '/runs/refinement/' in path:phase='invalidated_refinement_debug_port'
        elif '/runs/refinement_r03/' in path:phase='invalidated_refinement_missing_validator_feedback'
        elif '/runs/refinement_r04/' in path:phase='refinement'
        elif '/runs/fault_holdout/' in path:phase='independent_fault_holdout'
        elif '/runs/regression_audit/' in path:phase='post_freeze_development_regression'
        elif '/legacy_replay/' in path:phase='legacy_feedback_replay'
        elif '/baseline/' in path:phase='baseline_and_checker_qualification'
        elif '/historical_screening/' in path:phase='real_history'
        elif '/runs/minimal/' in path or '/runs/minimal_search/' in path:phase='witness_minimization'
        elif '/runs/diagnostics/' in path:phase='record_diagnostics'
        else:phase='supplemental_qa_and_versions'
        physical.append(dict(path=path,phase=phase,tool=tool,operation='version_probe' if '-V' in argv else 'execute',status=r['status'],wall_seconds=r.get('wall_seconds'),timeout=r.get('timeout_seconds')))
    x.dump(folder/'physical_commands.json',physical)
    costs=[]
    for phase in sorted({r['phase'] for r in physical}):
        rs=[r for r in physical if r['phase']==phase]
        costs.append(dict(phase=phase,compiler_attempts=sum(r['tool']=='iverilog' and r['operation']=='execute' for r in rs),
            simulator_attempts=sum(r['tool']=='vvp' and r['operation']=='execute' for r in rs),version_probes=sum(r['operation']=='version_probe' for r in rs),wall_seconds=sum(r['wall_seconds'] for r in rs),
            statuses=dict(collections.Counter(r['status'] for r in rs)),cpu_seconds=None))
    x.dump(folder/'physical_costs.json',costs)
    block=x.OUT/'refinement_r04';model=[x.read(p) for p in sorted(block.glob('models/*/*/*/result.json'))]
    model_cost=dict(calls=sum(r['model_calls'] for r in model),prompt_tokens=sum(r['prompt_tokens'] or 0 for r in model),
        completion_tokens=sum(r['completion_tokens'] or 0 for r in model),unavailable_token_calls=sum(r['prompt_tokens'] is None or r['completion_tokens'] is None for r in model),
        wall_seconds=sum(r['wall_seconds'] for r in model),statuses=dict(collections.Counter(r['status'] for r in model)),
        token_sum_scope='known tokens only; unavailable calls excluded from sums, never treated as zero measured cost')
    x.dump(folder/'model_costs.json',model_cost)
    x.dump(folder/'invalidated_model_costs.json',{n:x.read(x.OUT/n/'INVALIDATED.json') for n in ('refinement_r02','refinement_r03')})
    start=x.read(x.OUT/'protocol.json')['created_utc']
    x.dump(folder/'elapsed.json',dict(start_utc=start,end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        wall_seconds=time.time()-datetime.datetime.fromisoformat(start.replace('Z','+00:00')).timestamp(),
        scope='end-to-end since r02 prepared, including analysis, filesystem I/O, qualification, abandoned work and waiting; not an algorithm-only timing',
        human_labor_seconds=None,model_probe=x.read(x.OUT/'model_probe/result.json')))
    candidate_hashes=[]
    for k in x.IDS:
        d=x.read(x.OUT/'frozen'/k/'definition.json')
        for c in x.read(x.OUT/'frozen'/k/'candidates.json')['candidates']:
            sva=x.engine.sva(d,c)
            candidate_hashes.append(dict(case=k,candidate_id=c['id'],record_sha256=x.digest(c),
                assertion_ast_sha256=x.digest({n:c[n] for n in ('antecedent','consequent','delay')}),
                exact_sva_text=sva,sva_utf8_sha256=hashlib.sha256(sva.encode('utf-8')).hexdigest(),
                syntax_execution='procedural subset; native SVA unsupported'))
    x.dump(folder/'candidate_text_hashes.json',candidate_hashes)
    allq=[json.loads(s) for s in (block/'queries.jsonl').read_text().splitlines()] if (block/'queries.jsonl').exists() else []
    attempts=[json.loads(s) for s in (block/'query_attempts.jsonl').read_text().splitlines()] if (block/'query_attempts.jsonl').exists() else []
    assert [q['id'] for q in allq]==[a['id'] for a in attempts]
    models_requests=sorted(block.glob('models/*/*/*/request.json'))
    leakage=[]
    for p in models_requests:
        s=p.read_text()
        forbidden=['quarantine','obligation_evidence_monitor','boundary_vectors','fix.patch','hidden_schedule','9817301','second_new_sample_dbg']
        leakage.extend(dict(path=x.rel(p),token=t) for t in forbidden if t in s)
    x.dump(folder/'prompt_boundary_audit.json',dict(requests=len(models_requests),forbidden_marker_hits=leakage,
        implementation='allowlist construction in obligation_refinement_block.call_model; local service only, no filesystem/model tools',
        limits='marker scan complements code audit; not a proof against semantically equivalent leakage',all_queries_accounted=True))
    assert not leakage
    held=x.read(block/'heldout/summary.json') if (block/'heldout/summary.json').exists() else []
    regression=[]
    for p in sorted(block.glob('development/*/*/checkpoint_*.json')):
        c=x.read(p);events=[e for r in c['regression'] for e in r['events']]
        ast=lambda cs:sorted({json.dumps({n:z[n] for n in ('antecedent','consequent','delay')},sort_keys=True) for z in cs})
        regression.append(dict(case=p.parent.parent.name,arm=p.parent.name,round=c['round'],changed=ast(c['before'])!=ast(c['after']),
            raw_record_changed=c['before_sha256']!=c['after_sha256'],change_definition='AST fields only, IDs/provenance/order/duplicate clauses excluded; no general logical-equivalence claim',
            model_status=c['model_status'],fp=sum(e['kind']=='false_positive' for e in events),miss=sum(e['kind']=='miss' for e in events),source=x.rel(p)))
    x.dump(folder/'regression_checkpoints.json',regression)
    if (block/'regression_audit/summary.json').exists():
        x.dump(folder/'acquired_input_regression_summary.json',x.read(block/'regression_audit/summary.json'))
    hist=x.read(x.OUT/'historical_screening/ibex_54/reproduction.json')
    reset_results=x.read(x.OUT/'reset_sensitivity/summary.json')
    x.dump(folder/'reset_sensitivity_summary.json',reset_results)
    faults=x.read(x.OUT/'fault_holdout_r04/evaluation/results.json') if (x.OUT/'fault_holdout_r04/evaluation/results.json').exists() else []
    old_screen=x.read(x.ROOT/'deliverables/obligation_evidence_20261013_r01/historical_screening/screening_complete.json')
    x.dump(folder/'historical_screening_lineage.json',dict(prior_screening=old_screen,
        current_admitted=['lowRISC/ibex#54'] if hist['admitted'] else [],
        correction='Prior blanket Docker/Verilator exclusion was too broad: ibex_54 archived script uses Icarus. This case now independently reproduced; other cases remain deferred, not declared impossible.',
        current_reproduction=x.rel(x.OUT/'historical_screening/ibex_54/reproduction.json')))
    x.dump(folder/'executor_limitations.json',x.read(x.OUT/'async_history_qualification/result.json'))
    x.dump(folder/'reset_identifier_diagnostic.json',x.read(x.OUT/'reset_identifier_diagnostic/summary.json'))
    lines=['# 研究执行交付：2026-10-13 r02','',
        '第1、2项已实际复核和运行；第3项为3个非onehot父案例、单种子、两轮模型修复试验；第4项对冻结结果运行新保留输入，另外复现1个真实历史修复。完整父bug通过均未建立。',
        '', '## 原始记录与诊断', '', '| 父案例 | 原通过 | 原失败 | 原未知 |','|---|---:|---:|---:|']
    for k in x.IDS:
        pp=[p for p in parents if p['case']==k]
        lines.append(f"| {k} | {sum(p['complete_pass'] is True for p in pp)} | {sum(not p['complete_pass'] and not p['unknown'] for p in pp)} | {sum(p['unknown'] for p in pp)} |")
    lines+=['','40条是方法×父案例问题单元，不是40个独立bug。11对来自另一个历史自然候选池。160次基线重放：151条逐周期全同，9条不支持语法；旧反馈11/11同签名，896次原配置编译/仿真记录匹配。',
        '问题台账 diagnostics/problem_ledger.json 保留稳定ID、原状态、候选全文/哈希、规格/义务、证据、逐周期轨迹、命令、未知原因。有确证见证者重新执行了截短前缀。',
        'spill的数据含义、intr的mask采样仍未知。filter两条不可执行自然候选仍未知。参考监视器与checker为不同实现；原生SVA语法探针不支持，因此仅作过程仿真结论。',
        '额外发现旧checker的pN历史只在采样到复位时清除，拍间复位脉冲会残留历史。该问题已复现，独立扩展obligation_checker_async.py通过对照资格测试。冻结实验仍使用旧执行器，结论严格限于实际使用的采样复位场景；没有追溯改写运行记录。',
        '', '## 冻结候选搜索', '', '| 父案例 | 普通/分歧/义务缺口数 | 普通/分歧/义务区分对数 |', '|---|---|---|']
    for k in x.IDS:
        rs=[next(r for r in summaries if r['case']==k and r['method']==m) for m in ('ordinary','disagreement','obligation')]
        lines.append(f"| {k} | {' / '.join(str(r['gap_count']) for r in rs)} | {' / '.join(str(r['pair_count']) for r in rs)} |")
    lines+=['','每方法216次查询（6父×3种子×12），总648次；候选、种子、预算未变。候选级隔离使filter可执行子集得到评价，不能归因于义务搜索。缺口按候选×FP/FN×义务去重；三种方法的额外证据、无收益和遗漏全部保存。',
        '旧反馈漏掉合法前缀接受集合、首次违例前缀漏报和事务捕获区别。候选分歧经独立规格监视器判定后才成为证据。两者有缺陷时不作全局排序。资源曲线同时给出查询数、CPU秒和wall秒；此样本不支持义务搜索普遍优于对照。',
        '局部增益并非全无：逐种子12次预算下，onehot义务臂相对分歧臂每个种子多2个已核验缺口，相对普通补测没有新增；三个种子合并后两者并集均为12，合并计数掩盖了这个差异。spill义务臂相对普通臂每种子独有1个缺口，同时漏掉普通臂发现的2个；其结论只涉及已明确的valid义务。逐项见analysis_r02/paired_gain.json。',
        '另一个预注册局部区块保留相同自然候选，为stat/spill各方法各12次查询（总72），把复位移到挂起事务到期前。义务臂确实产生了取消事件，但缺口仍为stat 13/13/8、spill 11/11/10。此为诊断后的敏感性分析，不替换648次主结果；成本单列。',
        '', '## 模型细化与独立输入', '', '| 父案例 | 组 | 保留输入FP 初始→最终 | 首次违例漏报 初始→最终 | 最终未知场景 |', '|---|---|---:|---:|---:|']
    for r in held:
        a,b=r['metrics']['initial'],r['metrics']['final']
        lines.append(f"| {r['case']} | {r['arm']} | {a['false_positive_events']} → {b['false_positive_events']} | {a['missed_first_violation_events']} → {b['missed_first_violation_events']} | {b['unknown_scenarios']} |")
    lines+=['',f"实际模型调用{model_cost['calls']}次；已知prompt/completion tokens为{model_cost['prompt_tokens']}/{model_cost['completion_tokens']}；token不可得调用{model_cost['unavailable_token_calls']}次。模型、摘要、参数、请求/响应均保存。无手工候选修复。",
        '保留输入在修复前冻结，最终候选冻结后统一运行，之后没有修改。另有三个新同类人工故障在四组查询开始前冻结，未用于生成；该故障隔离晚于第2项搜索启动，因此只作为第3项修复结果的独立检查，不能用于声称第2项未见泛化。',
        '单种子、3父案例、每组两次模型调用不足以证明D相对B/C的一般优势。公共逐次回归见 delivery/regression_checkpoints.json；所有已获取输入的冻结后重放见 refinement_r04/regression_audit。FP减少与新增漏报必须同时检查。必要分支尚未完整验收，不标父bug整体通过。',
        'refinement_r02 因反馈含未授权调试端口而作废；refinement_r03 因验证拒绝原因未反馈、权限白名单不够明确而中止。完整请求、输出和成本均保留。有效比较为统一修正公共接口后从相同初始候选重跑的refinement_r04。作废成本、被中断调用和不可得tokens单独保存，不从总体投入中删除。',
        'r04仍受复位标识符接口限制：stat的8次提案均未被原前端接受，最终仍为初始候选，不能把这种无改善归因为义务方法无效。冻结后对12份最终真实提案原样重放，允许公开标量复位后可执行数从6增至11；见reset_identifier_diagnostic。没有改写提案，也未将这项前端诊断冒充完整修复轨迹。修正前端后的新完整四组闭环：未执行。',
        '当前小样本没有支持D相对B补出更多经过因果核验的必要义务，也没有支持D相对C减少误报。FIFO保留输入的最终FP为A/B/C/D=39/0/19/39；FP较多会提前拒绝前缀，因此较少的漏报计数不能单独解释为保护更强。24个修改检查点中3个在已获取开发输入回归上出现新增误报，详见regression_audit。',
        '', '## 独立同类故障检查', '', '| 父案例 | 组 | 初始→最终 因果归属检测 | 初始→最终 漏报 | 初始→最终 合法误报 |', '|---|---|---:|---:|---:|']
    for k in ('filter','fifo','stat'):
        for arm in ('A','B','C','D'):
            rs={r['version']:r for r in faults if r['case']==k and r['arm']==arm}
            if len(rs)!=2:continue
            a,b=rs['initial'],rs['final']
            lines.append(f"| {k} | {arm} | {len(a['causal_detections'])} → {len(b['causal_detections'])} | {len(a['misses'])} → {len(b['misses'])} | {len(a['false_positive_cycles'])} → {len(b['false_positive_cycles'])} |")
    lines+=['','因果检测仅在相同输入、此前可见前缀一致、合法对照前缀被接受、首次目标违例的唯一变化输出导致同期报警时计数；其余报警仍未知。故障场景有限，三个故障都是人工变异。',
        '', '## 代表性复现与历史案例', '',
        'stat：两拍复位后在t2输入长度19、t3输入73；t4应响应第一笔长度19，旧correct RTL却输出73。见 supplemental_qa/stat_overlap_minimal.json 及其输入、VCD、reproduce.sh。多位前件和两拍重叠/复位测试另外通过。',
        '新增搜索证据另有删除最小复现：filter漏报7拍、stat捕获长度漏报5拍、fifo合法误报3拍；初始两拍复位保留。见minimal_search/index.json。全部15次试验（含无效试次）和实际成本保存，未计入搜索臂预算。',
        f"真实历史Ibex #54：保存的HWE-Bench基准5项修复前失败、后通过；223项补充边界（222个不同输入，保留了原issue的重复回归项）中前失败175项、后0项。admitted={hist['admitted']}。来源 https://github.com/lowRISC/ibex/pull/54 ，修复意图 https://github.com/lowRISC/ibex/issues/51 。",
        '历史修复源码、原补丁、原测试脚本、提交号和新日志见 historical_screening/ibex_54。原测试台逐字保留，构建路径适配到本隔离目录；没有运行会清理仓库或安装系统依赖的容器准备脚本。历史答案未提供给模型；未将此案例计入四组方法比较。',
        '隔离应用原补丁后得到的模块与下载的修复后提交逐字节相同，见historical_screening/ibex_54/patch_validation/result.json。',
        '', '## 复现与限制', '',
        '新运行使用新目录：run_obligation_evidence.py prepare/baseline；audit_obligation_evidence.py complete_ledger/old_pairs/legacy_feedback；obligation_isolated_search.py init/search；obligation_delivery_audit.py report_search/diagnostics。模型有效区块由obligation_refinement_closed_loop.py及obligation_fault_holdout_closed_loop.py执行；依赖/冻结在各脚本中。每一步完整命令可见运行脚本和原始command.json。',
        '旧r01全部45,744个文件已哈希保留并逐字节复核；历史失败、未知、下载失败和重试均未覆盖。源快照和实验协议分别在source_snapshot、block_r02、refinement_r02。',
        '实际成本见 delivery/physical_costs.json、model_costs.json 和 search/queries.jsonl。共享资格检查、旧反馈重放、诊断最小化与方法查询分开记账。CPU不可得处为null。模型人工成本不可得，没有虚记为0。',
        '保留场景隔离审计：9条输入/复位序列去除文件名和周期标签后，与开发查询无完全重复；未证明任意语义等价关系均不存在，因此只作有限事务组合验证，不增加独立bug分母。',
        '待完成：在修正前端上重跑完整模型闭环、更大样本和多种子比较；原生SVA语义交叉核验；spill/intr规格澄清；完整必要分支验收；历史案例上的生成/修复对照。']
    (x.OUT/'README.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    source_files=sorted([*x.ROOT.joinpath('scripts').glob('obligation_*.py'),x.ROOT/'scripts/reproduce_ibex54.py',x.ROOT/'scripts/verify_ibex54_patch.py',x.ROOT/'scripts/run_obligation_evidence.py',x.ROOT/'scripts/obligation_delivery_audit.py'])
    source_index=[]
    for p in dict.fromkeys(source_files):
        target=folder/'implementation_snapshot'/p.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
        source_index.append(dict(source=x.rel(p),snapshot=x.rel(target),sha256=x.sha(p)))
    x.dump(folder/'implementation_manifest.json',source_index)
    manifest={x.rel(p):x.sha(p) for p in [x.OUT/'README.md',x.OUT/'diagnostics/problem_ledger.json',x.OUT/'analysis_r02/parent_method_results.json',folder/'physical_costs.json',folder/'model_costs.json',folder/'prompt_boundary_audit.json']}
    x.dump(folder/'summary_manifest.json',manifest)
    print(json.dumps(dict(delivery=x.rel(x.OUT/'README.md'),model_cost=model_cost,physical_commands=len(physical))))


def seal():
    """Preserve the initial report; issue precise timeout/proposal denominators."""
    folder=x.OUT/'delivery';target=x.OUT/'FINAL_REPORT.md'
    assert not target.exists()
    statuses=[]
    for p in sorted((x.OUT/'refinement_r04').glob('models/*/*/*/result.json')):
        r=x.read(p);error=r.get('error','')
        category='accepted_by_original_interface' if r['status']=='parsed' else 'model_timeout' if 'TimeoutError' in error else 'interface_permission_rejection' if 'permission:' in error else 'other_execution_or_format_failure'
        statuses.append(dict(case=p.parent.parent.parent.name,arm=p.parent.parent.name,round=p.parent.name,category=category,source=x.rel(p),error=error or None))
    raw=x.read(x.OUT/'reset_identifier_diagnostic/results.json')
    correction=dict(final_model_calls=len(raw),available_model_proposals=sum((x.OUT/'refinement_r04/models'/r['case']/r['arm']/'1/response.raw.json').exists() for r in raw),
        no_response_due_to_timeout=['fifo/D/1'],originally_accepted=6,executable_after_scalar_reset_support=11,
        correction='FileNotFoundError in original frontend diagnostic denotes an unavailable timed-out model response, not unsupported candidate syntax.',
        no_candidate_text_changes=True,formal_pilot_status_counts=dict(collections.Counter(r['category'] for r in statuses)))
    x.dump(folder/'model_status_detail.json',statuses);x.dump(folder/'proposal_denominator_correction.json',correction)
    text=(x.OUT/'README.md').read_text()
    text=text.replace('冻结后对12份最终真实提案原样重放，允许公开标量复位后可执行数从6增至11；',
        '12个最终模型调用有11份返回（另1次超时无输出）。冻结后原样重放这11份提案，允许公开标量复位后全部可执行，原前端只接受其中6份；')
    text=text.replace('有效比较为统一修正公共接口后从相同初始候选重跑的refinement_r04。',
        'refinement_r04从相同初始候选重跑，作为受限前端下的正式pilot保留；接口拒绝和一次超时限制其有效性。')
    text=text.replace('第1、2项已实际复核和运行；第3项为3个非onehot父案例、单种子、两轮模型修复试验；第4项对冻结结果运行新保留输入，另外复现1个真实历史修复。完整父bug通过均未建立。',
        '第1、2项已实际复核和运行；第3项在受限前端上完成24次真实模型调用（13次接口接受、10次权限拒绝、1次超时）；第4项完成有限保留输入、三个同类人工故障验收及1个真实历史修复复现。修正前端后的完整四组闭环未执行，没有父bug整体通过。')
    text+='\n本文件为最终入口。README.md保留初始汇总；proposal_denominator_correction.json明确超时不是候选语法失败。所有失败、未知、重跑和作废试验均保留。\n'
    target.write_text(text,encoding='utf-8')
    previous=x.read(x.OUT/'block_r02/prior_artifact_hashes.json');paths=list(previous)
    with ThreadPoolExecutor(max_workers=16) as pool:hashes=list(pool.map(lambda p:x.sha(x.ROOT/p),paths))
    changed=[p for p,h in zip(paths,hashes) if previous[p]!=h]
    x.dump(folder/'final_history_integrity.json',dict(files=len(paths),changed=changed,passed=not changed));assert not changed
    snapshots=[]
    for p in sorted(x.ROOT.joinpath('scripts').glob('obligation_*.py')):
        dest=folder/'final_implementation'/p.name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        snapshots.append(dict(source=x.rel(p),snapshot=x.rel(dest),sha256=x.sha(p)))
    x.dump(folder/'final_implementation_manifest.json',snapshots)
    paths=[]
    for base,dirs,names in os.walk(x.OUT):
        for name in names:
            p=Path(base)/name
            if p in [x.OUT/'seal.stdout',x.OUT/'seal.stderr',folder/'final_artifact_manifest.json']:continue
            paths.append(p)
    with ThreadPoolExecutor(max_workers=16) as pool:hashes=list(pool.map(x.sha,paths))
    x.dump(folder/'final_artifact_manifest.json',dict(files={x.rel(p):h for p,h in zip(paths,hashes)},
        excluded=['seal.stdout','seal.stderr','delivery/final_artifact_manifest.json'],
        reason='the active sealing command streams and this self-referential manifest cannot hash themselves'))
    print(json.dumps(dict(final_report=x.rel(target),artifact_files=len(paths),historical_files_unchanged=len(previous),model_statuses=correction['formal_pilot_status_counts'])))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);p.add_argument('action',choices=['report_search','diagnostics','deliver','seal'])
    a=p.parse_args();x.OUT=x.ROOT/'deliverables'/a.run;globals()[a.action]()
