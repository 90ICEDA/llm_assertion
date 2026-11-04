"""Unified, evidence-linked report; pending experiments never become successes."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import statistics
from research194_metrics import temporal_detection

ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'deliverables'


def read(path,default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def url(path):
    return '../'+Path(path).relative_to(D).as_posix()


def table(rows,columns):
    if not rows:return '<p class="pending">尚无本轮完成的实际结果。</p>'
    def cell(value):
        if isinstance(value,(list,dict)):value=json.dumps(value,ensure_ascii=False)
        if isinstance(value,float):value=round(value,3)
        return html.escape(str(value))
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(label)+'</th>' for key,label in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+cell(row.get(key,'—'))+'</td>' for key,label in columns)+'</tr>' for row in rows)+'</tbody></table></div>'


def trajectories(folder):
    folder=Path(folder).resolve()
    result=[]
    for p in sorted(folder.rglob('refinement/outcome.json')) if folder.exists() else []:
        row=read(p);m=read(p.parent/'terminal_measurement.json',{})
        if row.get('status')!='frozen':continue
        row.setdefault('parent_bug',m.get('parent_bug'))
        row.setdefault('historical_fix_confirmed',m.get('historical_fix_confirmed'))
        # An outer interruption may freeze a valid checkpoint before the usual
        # summary is written. Read paid response records rather than treating
        # missing summary token fields as zero. The archived outcome is intact.
        paid=[read(f,{}) for f in sorted(p.parent.glob('round*/model_call/result.json'))]
        if paid:
            row['archived_outcome_model_tokens_known']=row.get('model_tokens_known')
            row['model_tokens_known']=sum((r.get('prompt_tokens') or 0)+(r.get('completion_tokens') or 0) for r in paid)
            row['model_token_unknown_calls']=sum(r.get('model_calls',0)>0 and (r.get('prompt_tokens') is None or r.get('completion_tokens') is None) for r in paid)
            row['token_cost_basis']='Persisted actual model result records, including interrupted trajectories.'
        rounds=read(p.parent/'rounds.json',[]);history=read(p.parent/'controller_history.json',[])
        for key,value in dict(accepted_rounds=sum(r.get('status')=='accepted' for r in rounds),
            effective_rounds=sum(r.get('status')=='accepted' for r in rounds),
            regression_proposed=sum(bool(r.get('decision',{}).get('regression')) for r in rounds),
            regression_accepted=sum(r.get('status')=='accepted' and bool(r.get('decision',{}).get('regression')) for r in rounds),
            interface_failures=sum(r.get('status') in ('interface_rejected','no_change') for r in rounds)).items():
            row.setdefault(key,value)
        stage_summary={stage:dict(native_proposals=sum(r.get('stage')==stage for r in rounds),
            accepted=sum(r.get('stage')==stage and r.get('status')=='accepted' for r in rounds)) for stage in ('free','local','compose','regenerate')}
        row['history_loss_proposals']=sum(bool(r.get('decision',{}).get('lost_ids') or r.get('decision',{}).get('historical_any_cycle_lost_ids')) for r in rounds)
        row['new_fp_proposals']=sum(bool(r.get('decision',{}).get('new_false_positive_ids')) for r in rounds)
        temporal=temporal_detection(m)
        result.append(dict(**row,folder=str(p.parent.relative_to(ROOT)),stage_summary=stage_summary,
            structural_empty_domain_certificates=sum(r.get('event')=='structural_local_domain_empty' for r in history),
            target_count=len(m.get('targets',[])),miss_count=len(set(m.get('targets',[]))-set(m.get('detected_ids',[]))),
            detected_count=len(m.get('detected_ids',[])),fp_count=len(m.get('false_positives',[])),
            transaction_miss_count=len(temporal['transaction_missed_ids']),late_detected_count=len(temporal['late_detected_ids']),
            unknown_count=len(m.get('critical_unknown',[])),
            exposed_obligations=sorted({e['obligation'] for e in m.get('evidence',[]) if e.get('status')=='confirmed' and e.get('counted_target')}),
            covered_obligations=m.get('covered_obligations',[])))
    return result


def aggregate(rows,groups,acceptance):
    result=[]
    for name,search,strategy in groups:
        rr=[r for r in rows if r.get('search_strategy',r.get('search'))==search and r['strategy']==strategy]
        if not rr:continue
        item=dict(method=name,search=search,refinement=strategy,trajectories=len(rr),parents=len({r['case_id'] for r in rr}),
            accepted_rounds=sum(r.get('accepted_rounds',0) for r in rr),effective_rounds=sum(r.get('effective_rounds',0) for r in rr),
            regression_proposed=sum(r.get('regression_proposed',0) for r in rr),regression_accepted=sum(r.get('regression_accepted',0) for r in rr),
            history_loss_proposals=sum(r.get('history_loss_proposals',0) for r in rr),new_fp_proposals=sum(r.get('new_fp_proposals',0) for r in rr),
            accepted_local=sum(r['stage_summary']['local']['accepted'] for r in rr),
            accepted_compose=sum(r['stage_summary']['compose']['accepted'] for r in rr),
            accepted_regenerate=sum(r['stage_summary']['regenerate']['accepted'] for r in rr),
            model_calls=sum(r.get('actual_model_calls',r.get('model_calls',0)) for r in rr),
            known_tokens=sum(r.get('model_tokens_known',0) for r in rr),unknown_token_calls=sum(r.get('model_token_unknown_calls',0) for r in rr),
            native_compiles=sum(r.get('native_compile_attempts',0) for r in rr),interface_failures=sum(r.get('interface_failures',0) for r in rr),
            native_cost_unknown_trajectories=sum('native_compile_attempts' not in r and r.get('actual_model_calls',r.get('model_calls',0))>0 for r in rr),
            development_fp=sum(r['fp_count'] for r in rr),development_misses=sum(r['miss_count'] for r in rr),
            development_transaction_misses=sum(r['transaction_miss_count'] for r in rr),
            development_late_detected=sum(r['late_detected_count'] for r in rr),
            unknown_trajectories=sum(r['unknown_count']>0 or not r.get('causal_comparison_eligible',True) for r in rr))
        item['acceptance_rate_per_actual_model_call']=item['accepted_rounds']/item['model_calls'] if item['model_calls'] else None
        folders={r['folder'] for r in rr};aa=[a for a in acceptance if a.get('folder') in folders]
        item['independent_versions']=len({a['id'] for a in aa})
        eligible=[a for a in aa if a['valid_reachable_fault'] and a['target_transaction_obligations'] and not a['unknown_records']]
        item['independent_unknown_version_faults']=sum(bool(a['unknown_records']) for a in aa)
        item['independent_parent_macro_detection_rate']=statistics.mean(
            statistics.mean(a['transaction_detected']/a['target_transaction_obligations'] for a in eligible if a['parent_bug']==parent)
            for parent in {a['parent_bug'] for a in eligible}) if eligible else None
        for output,field in (('independent_parent_macro_necessary_obligation_protection','necessary_obligation_transaction_protection_rate'),
                             ('independent_parent_macro_fp_records','false_positive_records')):
            item[output]=statistics.mean(statistics.mean(a[field] for a in eligible if a['parent_bug']==parent)
                for parent in {a['parent_bug'] for a in eligible}) if eligible else None
        result.append(item)
    return result


def cross_design_table(acceptance):
    """Descriptive per-parent table; frozen versions and fault scopes stay explicit."""
    result=[]
    arms={'A0':('S0','R1'),'A1':('S3','R1'),'A2':('S0','R3'),'A3':('S3','R3')}
    for case in sorted({r['case_id'] for r in acceptance}):
        for arm,(search,strategy) in arms.items():
            rows=[r for r in acceptance if r.get('case_id')==case and r.get('search_strategy')==search and r.get('strategy')==strategy]
            if not rows:continue
            known=[r for r in rows if r['valid_reachable_fault'] and r['native_complete'] and r['reference_complete'] and not r['unknown_records']]
            unseen=[r for r in known if r['fault_kind']=='unseen_fault_at_reserved_site']
            necessary_rates=[]
            for version in sorted({r['id'] for r in rows}):
                vv=[r for r in rows if r['id']==version]
                if any(r not in known for r in vv):continue
                needed=set().union(*(set(r['necessary_obligations']) for r in vv))
                exposed=set().union(*(set(r['exposed_obligations']) for r in vv))
                failed=set().union(*(set(r['exposed_obligations'])-set(r['fully_transaction_protected_exposed_obligations']) for r in vv))
                necessary_rates.append(len(exposed-failed)/len(needed) if needed else 0)
            result.append(dict(case_id=case,parent_bug=rows[0]['parent_bug'],historical_fix_confirmed=rows[0]['historical_fix_confirmed'],
                arm=arm,versions=len({r['id'] for r in rows}),faults=len({r['fault'] for r in rows}),
                known_version_faults=len(known),unknown_version_faults=sum(bool(r['unknown_records']) for r in rows),
                invalid_or_unexposed_version_faults=sum(not r['valid_reachable_fault'] or not r['target_ids'] for r in rows),
                all_faults_known_versions=len(necessary_rates),
                necessary_obligation_protection_rate=statistics.mean(necessary_rates) if necessary_rates else None,
                known_target_transaction_obligations=sum(r['target_transaction_obligations'] for r in known),
                known_timely_misses=sum(r['misses'] for r in known),known_transaction_misses=sum(r['transaction_misses'] for r in known),
                legal_fp_records=sum(r['false_positive_records'] for r in rows),
                unseen_faults_with_any_detection=sum(bool(r['transaction_detected']) for r in unseen),
                unseen_known_version_faults=len(unseen),
                no_exposure_queries=sum(len(r['no_exposure_queries']) for r in rows),
                full_scope_passed_version_faults=sum(r['full_planned_transaction_scope_pass'] for r in rows)))
    return result


def build(out,search,main,augmentation,fault,independent):
    out,search,main,augmentation,fault,independent=(Path(p).resolve() for p in (out,search,main,augmentation,fault,independent))
    out.mkdir(parents=True,exist_ok=True)
    search_data=read(search/'analysis.json',{})
    sr=search_data.get('tables',[]) if search_data.get('complete') else []
    rr=trajectories(main);ar=trajectories(augmentation)
    acceptance=read(independent/'results.json',[])
    rt=aggregate(rr,[(f'R{i}','S0',f'R{i}') for i in range(4)],acceptance)
    at=aggregate(rr,[('A0','S0','R1'),('A1','S3','R1'),('A2','S0','R3'),('A3','S3','R3')],acceptance)
    source_folders=dict(search=search,main=main,augmentation=augmentation,fault=fault,independent=independent)
    status=dict(search_completed=bool(search_data.get('complete')),main_frozen=len(rr),main_expected=64,
        augmentation_frozen=len(ar),augmentation_expected=16,independent_completed=read(independent/'outcome.json',{}).get('status')=='completed',
        fault_comparison_completed=len(read(fault/'results.json',[]))==27,
        historical_results='Preserved and linked; not rerun by this report.',
        report_is_not_completion_certificate=True)
    tables=dict(search=sr,refinement=rt,ablation=at,independent=acceptance,cross_design=cross_design_table(acceptance),fault=read(fault/'summary.json',[]),status=status)
    dump(out/'tables.json',tables);dump(out/'trajectory_index.json',rr+ar)
    paths=[p for folder in source_folders.values() for p in folder.glob('*.json') if p.is_file()]
    dump(out/'source_bindings.json',{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    body=['<h1>REGuard：跨设计时序机制实验</h1>',
        '<p>本页区分模块实现、原生实验执行、断言改善和独立验收。没有模型响应或独立测试结果的项目保持待完成，不以手写控制实验替代真实模型结果。</p>',
        '<p><a href="../reguard_mechanisms_20261103_r01/report.html">历史统一入口：onehot、11 对候选、复杂 FIFO、协议与 Ibex 索引</a>。旧结果、初始候选、证据与失败记录均保留。</p>',
        '<p><a href="../research194_cases_registry_20261103_r01/registry.json">四类新增案例的义务、来源、触发与验收准备度注册表</a> · <a href="acceptance_registration.json">独立验收预注册</a> · <a href="actual_costs.json">实际成本账本</a></p>',
        '<h2>范围与统计口径</h2>',
        '<p>新增 Arbiter、Counter、UART 使用真实项目 RTL 和明确标注的人工义务故障；Ibex 使用上游 PR #2374 的真实 flush 子修复，验证压缩译码器与 IF 的交界契约，不代表完整 CPU 或该 PR 后续原子提交修改。所有结果为有限原生仿真，不是形式证明。</p>',
        '<p>固定两种选择/模型请求种子，公开刺激本身相同；不能称为两套独立测试样本。缺口分别按事务与义务、归一化事务波形上下文去重，父 Bug 单独汇总。及时性要求首个义务违例采样点告警；事务检出允许同事务同义务的任一已确认违例周期告警。迟到检出单列，不等于整个事务漏报；多个失败周期不重复计数。</p>',
        '<p>本轮独立验收在所有注册模型版本冻结后才开放。未曝光、未触发、执行失败和参考未知单列。模型金额无账单或价格依据时保留未知，只报告实测调用、tokens 和运行时间。</p>',
        '<p>原生查询预算相同，每条查询固定两次 RTL 执行；本轮尚未验证按可变运行时间选择查询的优势。实际运行秒数和主动规划开销另列，不能称为等墙钟预算。</p>',
        '<p>R/A 与增强实验使用相同的注册预算上限；未知、截断、诊断异常和历史去重会造成实际调用及回放成本不同。实际成本逐条报告，不将这些结果解释为严格等实际花费下的优越性。</p>',
        '<h2>当前状态</h2><pre>'+html.escape(json.dumps(status,ensure_ascii=False,indent=2))+'</pre>',
        '<h2>S0–S3：同候选、同实际查询预算</h2>',
        table(sr,[('strategy','策略'),('queries','查询'),('native_execution_attempts','原生执行'),('new_distinct_gaps','新增及时性缺口'),('new_trace_context_distinct_gaps','上下文去重及时性缺口'),('pooled_late_detected_ids_count','含基线迟到检出'),('pooled_transaction_missed_ids_count','含基线完全漏报'),('native_seconds','原生秒'),('planning_seconds','规划秒'),('critical_unknown','关键未知')])]
    if len(rr)<64 or len(ar)<16 or not status['independent_completed']:
        body.insert(1,'<p class="pending"><strong>实验仍在进行：以下模型表只包含已冻结轨迹，尚不能作最终策略比较。最终独立验收未完成时，不给出泛化通过结论。完整物理成本账本将在整批结束后刷新，运行期间可能仍是较早快照。</strong></p>')
    for name in ('trace_context_mean_cost_curve.png','trace_context_per_design_cost_curves.png'):
        if (search/name).exists():body.append('<img alt="有效缺口随实际原生执行成本变化" src="'+url(search/name)+'">')
    common=[('method','策略'),('trajectories','冻结轨迹'),('parents','父案例'),('accepted_rounds','接受轮次'),('accepted_local','局部接受'),('accepted_compose','组合接受'),('accepted_regenerate','再生成接受'),('history_loss_proposals','丢失历史检出提案'),('new_fp_proposals','新增误报提案'),('regression_accepted','接受退化'),('interface_failures','无效接口/无修改'),('model_calls','真实调用'),('known_tokens','已知 tokens'),('unknown_token_calls','tokens 未知调用'),('development_fp','开发误报'),('development_misses','开发首违例未检出'),('development_late_detected','开发迟到检出'),('development_transaction_misses','开发完全漏报'),('independent_parent_macro_detection_rate','独立父 Bug 宏平均检出率'),('independent_parent_macro_necessary_obligation_protection','独立必要义务保护率'),('independent_unknown_version_faults','独立未知版本×故障')]
    common.insert(-1,('independent_parent_macro_fp_records','独立合法误报记录宏平均'))
    body.extend(['<h2>R0–R3：同 S0 证据序列的多轮细化</h2>',table(rt,common),
        '<p>开发指标对应各自累计已见证据；只有冻结后共同验收输入的结果可作最终质量比较。R0/R1/R2/R3 的编辑权限与历史保护门均封存在协议中。</p>',
        '<p>本轮 R3 可调用首轮均因缺失义务无法由受限字段编辑新增而凭结构证书进入组合阶段；这属于义务组合，不得称为局部字段修复收益。后续实际 local/compose/regenerate 原生提案及接受轮数分别保留在 trajectory_index.json。</p>',
        '<h2>A0–A3：2×2 组合消融</h2>',table(at,common),
        '<p>A0=S0R1，A1=S3R1，A2=S0R3，A3=S3R3；这些是同一实际运行的别名，不能重复计入成本。</p>',
        '<p>汇总表的独立宏平均仅描述各策略已知结果，可能覆盖不同的可判定故障子集。策略优劣与组合增益须查看共同目标集合上的配对分析；未知、未曝光均不补成通过。</p>',
        '<h2>跨设计、跨未见故障独立验收</h2>',
        table(tables['cross_design'],[('case_id','设计'),('arm','冻结策略'),('versions','种子版本数'),('faults','故障数'),('known_version_faults','可判定版本×故障'),('unknown_version_faults','未知版本×故障'),('necessary_obligation_protection_rate','全部故障合并必要义务保护'),('all_faults_known_versions','义务指标可判定版本数'),('legal_fp_records','合法误报记录'),('known_transaction_misses','已知目标完全漏报'),('unseen_faults_with_any_detection','检出任一目标的新故障×版本'),('unseen_known_version_faults','可判定新故障×版本'),('no_exposure_queries','未曝光查询'),('full_scope_passed_version_faults','完整范围通过版本×故障')]),
        '<p>上表按父案例列示，两种子是同一父 Bug 的重复；新故障检出计数的单位明确为故障×版本，不能解释为独立父 Bug 数。必要义务保护要求该版本在各故障上已曝光的相关事务全部检出，未曝光义务仍留在分母，未知版本不填通过。</p><details><summary>逐冻结版本、逐故障完整验收记录</summary>',
        table(acceptance,[('id','冻结版本'),('parent_bug','父 Bug'),('fault','故障'),('valid_reachable_fault','独立确认有效'),('target_transactions','真实事务数'),('detected','及时检出'),('late_detected','迟到检出'),('transaction_misses','完全漏报'),('false_positive_records','合法误报'),('untriggered','首违例未触发'),('unknown_records','未知'),('necessary_obligation_transaction_protection_rate','必要义务保护率'),('no_exposure_queries','未曝光查询'),('full_planned_transaction_scope_pass','完整事务计划范围通过')]),
        '</details>',
        '<h2>探索：故障族三策略</h2>',table(tables['fault'],[('case','设计'),('strategy','策略'),('mutants','变异尝试'),('valid','有效可达'),('gap_obligations','缺口义务'),('compile_attempts','编译成本'),('native_seconds','原生秒')]),
        '<p>修复区域策略的区域是人工主故障注入区域。独立故障保留不同具体位置；不同算子名称不证明广义算子家族完全独立。增强收益必须由无增强/有增强的冻结版本在共同未见故障上比较后确认。</p>',
        '<p><a href="../research194_fault_regrade_20261103_r01/report.html">故障三策略完整报告</a> · <a href="../research194_fault_temporal_sidecar_20261103_r01/report.html">及时性、迟到检出与完全漏报的只读复核</a></p>',
        '<h2>机制正反案例与证据链</h2>'])
    if (out/'case_cards/case_cards.html').exists():body.append('<p><a href="case_cards/case_cards.html">模型修改与冻结验收的完整正反案例链</a></p>')
    if (out/'case_atlas.html').exists():body.append('<p><a href="case_atlas.html">案例图册：实际 SVA、关键事务波形、定位与验收表</a></p>')
    for name,label in (('mechanism_examples.json','主动搜索正反例：原 SVA、查询目标、关键事务波形和证据 ID'),('evidence_links.json','搜索证据与细化轨迹连接表'),('audit.json','原生触发、参考监视器与成本审计')):
        if (search/name).exists():body.append('<p><a href="'+url(search/name)+'">'+label+'</a></p>')
    body.append('<p>搜索发现缺口不能直接算作 SVA 改善。完整链必须同时具备：已确认新证据、修改操作、冻结断言以及共同独立验收改善。不存在符合条件的正例时明确报告，不拼接不同实验制造收益。</p>')
    if status['independent_completed']:
        body.append('<h2>共同验收集合上的机制收益</h2>')
        active_path=D/'research194_active_outcomes_20261103_r01/analysis.json'
        active=read(active_path,{})
        if active.get('status')=='completed':
            body.append('<p>以下搜索比较保留输出预算截断后的冻结版本（ITT），仅使用各策略共同可判定的故障与目标；完整运行的严格配对另列于原始分析。</p>')
            body.append(table(active.get('intention_to_treat',{}).get('population',[]),[
                ('method','搜索'),('comparator','对照'),('fully_paired_parents','完整配对父Bug'),
                ('parent_macro_transaction_rate_delta','事务检出率增量'),('parent_macro_timely_rate_delta','及时检出率增量')]))
            body.append('<p><a href="'+url(active_path)+'">搜索配对结果、排除原因与严格完成口径</a> · <a href="'+url(active_path.parent/'evidence_edit_final_links.json')+'">证据→真实模型请求→修改→冻结保留链</a></p>')
        interactions_path=D/'research194_ablation_interactions_20261103_r01/analysis.json'
        interactions=read(interactions_path,{})
        if interactions:
            ii=interactions.get('summaries',{}).get('intention_to_treat',{})
            contrast_rows=[dict(metric=m,**v) for m,v in (ii.get('parent_macro_contrasts') or {}).items()]
            body.append('<p>组合交互项 = A3−A2−A1+A0。检出率上的正值表示描述性的额外收益；误报上的正值表示增加误报。它不是统计显著性证明。</p>')
            body.append(table(contrast_rows,[('metric','指标'),('active_without_local','主动搜索单独增量'),('active_with_local','主动搜索在R3上的增量'),('local_without_active','R3单独增量'),('local_with_active','R3在主动搜索上的增量'),('interaction','交互项')]))
            body.append('<p><a href="'+url(interactions_path)+'">2×2 逐父Bug、种子、故障配对与未知项</a></p>')
        for relative,label in (
            ('research194_refinement_posthoc_20261103_r01/independent_refinement_pairs.json','R3 与 R2/R0：共同证据下的新增检出、丢失检出和合法误报'),
            ('research194_refinement_posthoc_20261103_r01/population_qualification_reconciliation.json','口径核对：正常终止案例与排除开发 unknown 提案的保守敏感性子集'),
            ('research194_refinement_posthoc_20261103_r01/representative_development_cards.json','真实局部修改、组合、再生成失败与截断的开发案例'),
            ('research194_refinement_posthoc_20261103_r01/localization_mechanism_coverage.json','六类定位与修改机制的实际覆盖矩阵'),
            ('research194_refinement_posthoc_20261103_r01/outer_exception_diagnostics.json','UART 诊断空值异常：实际调用成本、纯函数重放及隔离修复验证'),
            ('research194_fault_augmentation_audit_20261103_r01/report.html','有无故障增强：未见故障上的配对收益与原生验收审计')):
            path=D/relative
            if path.exists():body.append('<p><a href="'+url(path)+'">'+label+'</a></p>')
    conclusions=read(out/'conclusions.json',{})
    if conclusions:
        body.insert(1,'<h2>本轮结论与未覆盖范围</h2>'+''.join('<p>'+html.escape(x)+'</p>' for x in conclusions.get('findings',[]))+table(conclusions.get('scope',[]),[('item','任务'),('status','完成口径'),('remaining','仍不能声称')])+'<p><a href="completion.json">最终执行、交付与审计清单</a> · <a href="conclusions.json">结论及来源</a></p>')
    if (out/'case_cards/itt_case_cards.html').exists():
        body.append('<p><a href="case_cards/itt_case_cards.html">ITT 附录：截断或中断后保留版本的实际收益链</a>。与严格完成案例分开，不把保留的中间改进称为完整三轮通过。</p>')
    body.append('<h2>可审计产物</h2>')
    for name,label in (('research194_refinement_prepare_20261103_r01','主实验'),('research194_augmentation_prepare_20261103_r01','故障增强')):
        prepared=D/name
        if (prepared/'review.json').exists():
            body.append('<p>'+label+'：<a href="'+url(prepared/'protocol.json')+'">封存协议</a> · <a href="'+url(prepared/'review.json')+'">调用上限与准备状态</a></p>')
    for key,folder in source_folders.items():
        for name in ('protocol.json','analysis.json','outcome.json','summary.json','review.json'):
            if (folder/name).exists():body.append('<p><a href="'+url(folder/name)+'">'+key+'/'+name+'</a></p>')
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>REGuard 跨设计实验</title><style>body{font:16px/1.6 system-ui;max-width:1400px;margin:40px auto;padding:0 24px;color:#203040;background:#fafbfc}h1,h2{line-height:1.3}h2{margin-top:36px}a{color:#135db0}table{border-collapse:collapse;font-size:13px;background:white}td,th{border:1px solid #d3dce5;padding:8px;vertical-align:top;max-width:320px;overflow-wrap:anywhere}th{background:#e9f0f8;white-space:nowrap}.scroll{overflow-x:auto}pre{white-space:pre-wrap;background:#edf1f5;padding:16px}img{max-width:100%;background:white}.pending{color:#885518}</style><body>'+''.join(body)+'</body></html>'
    (out/'report.html').write_text(page,encoding='utf-8')
    print(json.dumps(status,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=D/'reguard_mechanisms_20261103_r02')
    p.add_argument('--search',type=Path,default=D/'research194_active_native_20261103_r02')
    p.add_argument('--main',type=Path,default=D/'research194_refinement_execute_20261103_r01')
    p.add_argument('--augmentation',type=Path,default=D/'research194_augmentation_execute_20261103_r01')
    p.add_argument('--fault',type=Path,default=D/'research194_fault_regrade_20261103_r01')
    p.add_argument('--independent',type=Path,default=D/'research194_independent_20261103_r01')
    args=p.parse_args();build(**vars(args))
