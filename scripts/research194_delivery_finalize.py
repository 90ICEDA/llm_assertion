"""Finalize an auditable delivery after the sealed campaign; never run models."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'deliverables'
OUT=D/'reguard_mechanisms_20261103_r02'
CAM=D/'research194_campaign_execute_20261103_r01'

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def build():
    campaign=read(CAM/'outcome.json')
    acceptance=read(CAM/'independent/outcome.json')
    assert campaign['status']=='completed' and acceptance['status']=='completed'
    assert acceptance['all_frozen_unchanged'] and acceptance['frozen_versions']==80
    cost=read(OUT/'actual_costs.json')
    models=read(D/'research194_refinement_posthoc_20261103_r01/summary.json')
    assert cost['model_calls_with_final_record']==models['completed_actual_model_calls']==168
    assert cost['known_total_tokens']==models['known_tokens']==8666140
    assert cost['actual_retries']==0
    results=read(CAM/'independent/results.json')
    assert len(results)==252
    fault=read(D/'research194_fault_augmentation_audit_20261103_r01/summary.json')
    assert fault['status']=='passed' and fault['failures']==0
    tests=(OUT/'unit_tests.log').read_text(encoding='utf-8')
    ntests=int(re.search(r'Ran (\d+) tests',tests).group(1))
    assert '\nOK\n' in tests
    active=read(D/'research194_active_outcomes_20261103_r01/analysis.json')
    interaction=read(D/'research194_ablation_interactions_20261103_r01/analysis.json')
    assert active['status']=='completed'
    contrasts=interaction['summaries']['intention_to_treat']['parent_macro_contrasts']
    scopes=[
        dict(item='历史矩阵与统一入口',status='保留旧索引并接入本轮真实执行',remaining='历史全部结果逐项重新复现'),
        dict(item='S0–S3 主动证据搜索',status='四设计、两选择种子、同实际查询预算；最终修改与独立结果已连接',remaining='S3 优于 S2；可变墙钟成本选择；任意复杂窗口的充分验证'),
        dict(item='R0–R3 多轮细化',status='三轮上限；真实局部、组合、再生成及历史回放均有记录',remaining='各定位类型均有成功局部修复；低成本或总体稳定性优势'),
        dict(item='故障族增强',status='三种变异策略、开发反馈及预留位置独立验收已执行',remaining='跨种子稳定独立收益；正式第三创新'),
        dict(item='设计扩展',status='Arbiter、Counter、UART、Ibex flush 子修复已原生接通',remaining='前三者是真实历史 Bug；Ibex 完整异常/流水线/CPU 验证'),
        dict(item='2×2 消融与验收',status='80冻结版本+4初始对照；96次共享原生执行；252版本×故障记录',remaining='所有轨迹完整三轮；全部故障参考可判定；任一版本完整范围通过'),
        dict(item='两个机制正反案例',status='严格案例、ITT保留版本案例、实际SVA/波形/定位/验收分层交付',remaining='强行填充不存在的合格正例；把整套R3收益孤立归因于局部操作')]
    findings=[
        '本轮注册的跨设计实验及冻结后独立验收已经执行完成；执行完成不等于所有版本通过，也不等于原始研究目标已全面证明。没有改动测试集以追求正面结果。',
        '实际使用168/219次授权调用，8,666,140 tokens，0重试；5次输出预算截断、2条UART诊断空值异常轨迹及所有unknown均保留。金额无账单依据，记为未知。',
        '新增原生搜索的上下文去重缺口为S0/S1/S2/S3=32/8/39/39，合并独有缺口均为0。S3没有证明优于S2。共同独立验收的R1细化链ITT口径中，S3对S0与S2的三父案例事务检出率宏平均差均约−8.65个百分点；该描述性结果不支持总体优势。',
        'S0上的R0/R1/R2/R3接受修改为3/3/2/7次，R3的7次为2次局部、5次组合，实际tokens最高。实际局部成功集中在Counter触发范围；窗口、事务匹配与例外专用操作仍缺成功实测。再生成成功与失败另有真实记录。',
        'R3相对R2在可判定独立配对中，逐种子、故障汇总新增Counter 71和Ibex 1个事务×义务检出，未丢失检出；这些汇总数不能作为独立父Bug或跨种子独立样本数。Counter同时新增1个新输入合法告警（跨三个故障重放仍只算一个输入告警）。排除全部开发unknown提案及异常终止的R配对敏感性子集没有保留正增益，不能称为总体稳定性优势。',
        '案例主卡的正常终止筛选保留被拒绝的开发unknown提案，因此与上述更严格的R敏感性子集不同。Arbiter/19419同时存在主动搜索和R3整套策略的正面链，独立各增48个事务×义务检出且无丢失/新增误报；这些增益来自primary故障的新输入，不是两个未见故障的泛化增益。R3该例实际为义务组合，不能称为局部字段修改收益。失败卡保留Ibex主动链损失8个检出及Arbiter另一种子R3无额外收益。',
        '39次接受修改的已见合法历史审计没有新增细粒度告警；这不能保证未见合法输入无误报。历史损失拒绝案例同时也缺正收益，不能据此声称历史门独立改变了接受决策。',
        '2×2共同可判定、两种子完整配对的父案例数为3。等故障权重的事务检出率交互项为'+f"{100*contrasts['transaction_rate']['interaction']:+.2f}"+'个百分点，及时检出率为'+f"{100*contrasts['timely_rate']['interaction']:+.2f}"+'个百分点；方向不同，不支持概括性组合优势或统计显著性结论。',
        '故障增强在Counter/19419的未见输出位故障上检出2→11（6个load、3个clear新增目标），19407却2→0；Ibex无增益，另两设计受unknown影响。实际调用2对3且包含失败，不能把全部差异纯归因于增强。没有父案例跨两种子稳定获益，第三模块保持探索性。',
        '252条版本×故障记录均对应独立确认可达的故障，其中26条有候选相关unknown，105条至少存在未曝光查询；完整计划事务范围通过数和全部必要义务保护通过数均为0。不能将这些记录当作252个独立父Bug。',
        '新案例包含真实项目RTL上的3个人工义务故障父案例及1个真实Ibex flush子修复。两种子共享公开刺激，只有选择/模型请求种子不同。R/A有相同预算上限，但停止、失败与去重使实际花费不同；这不是严格等实际花费的胜负实验。全部验收为有限原生仿真，不是形式证明。',
        'UART空值定位异常已在独立适配器中修复并测试，未修改本轮封存代码或重跑失败样本；当前结果仍反映原缺陷。后续需要新版本验证，不能把适配器测试算作当前轨迹修复成功。']
    source_paths=[
        CAM/'outcome.json',CAM/'frozen_versions.json',CAM/'independent/outcome.json',CAM/'independent/results.json',
        OUT/'actual_costs.json',OUT/'tables.json',OUT/'trajectory_index.json',OUT/'unit_tests.log',
        OUT/'case_cards/case_cards.json',OUT/'case_cards/itt_case_cards.json',OUT/'case_atlas.html',
        D/'research194_active_native_20261103_r02/analysis.json',D/'research194_active_outcomes_20261103_r01/analysis.json',
        D/'research194_ablation_interactions_20261103_r01/analysis.json',
        D/'research194_refinement_posthoc_20261103_r01/independent_refinement_pairs.json',
        D/'research194_refinement_posthoc_20261103_r01/population_qualification_reconciliation.json',
        D/'research194_refinement_posthoc_20261103_r01/localization_mechanism_coverage.json',
        D/'research194_refinement_posthoc_20261103_r01/sealed_model_call_audit.json',
        D/'research194_fault_augmentation_audit_20261103_r01/summary.json']
    bindings={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    dump(OUT/'conclusions.json',dict(findings=findings,scope=scopes,source_bindings=bindings))
    cards=read(OUT/'case_cards/case_cards.json')
    itt=read(OUT/'case_cards/itt_case_cards.json')
    completion=dict(status='registered_experiments_completed_with_research_limitations',timestamp_utc=datetime.now(timezone.utc).isoformat(),
        all_original_research_claims_proven=False,scope=scopes,actual_model_calls=168,authorized_ceiling=219,known_tokens=8666140,retries=0,
        frozen_experimental_versions=80,initial_controls=4,independent_physical_compiles=96,independent_physical_executions=96,
        independent_version_fault_records=len(results),unknown_version_fault_records=sum(r['unknown_records']>0 for r in results),
        records_with_unexposed_queries=sum(bool(r['no_exposure_queries']) for r in results),
        full_planned_transaction_scope_passes=sum(r['full_planned_transaction_scope_pass'] for r in results),
        all_necessary_obligations_protected=sum(r['all_necessary_obligations_protected'] for r in results),
        tests_passed=ntests,audit_checks=fault['checks'],audit_failures=0,
        strict_case_card_statuses=[{k:c.get(k) for k in ('mechanism','kind','status','full_positive_chain')} for c in cards],
        itt_case_cards_file='case_cards/itt_case_cards.json',
        read_only_rebuild_commands=[
            'python3 -B scripts/research194_active_outcome_analysis.py --campaign deliverables/research194_campaign_execute_20261103_r01 --out deliverables/research194_active_outcomes_20261103_r01',
            'python3 -B scripts/research194_ablation_interactions.py',
            'python3 -B scripts/research194_case_cards.py --main deliverables/research194_campaign_execute_20261103_r01/base --independent deliverables/research194_campaign_execute_20261103_r01/independent --out deliverables/reguard_mechanisms_20261103_r02/case_cards',
            'python3 -B scripts/research194_case_atlas.py',
            'python3 -B scripts/research194_cost_audit.py',
            'python3 -B scripts/research194_delivery_finalize.py',
            'python3 -B scripts/research194_report.py --main deliverables/research194_campaign_execute_20261103_r01/base --augmentation deliverables/research194_campaign_execute_20261103_r01/augmentation --independent deliverables/research194_campaign_execute_20261103_r01/independent'],
        deliverables=dict(search_table_and_cost_curves='report.html',refinement_table='report.html',ablation_table='report.html',cross_design_fault_acceptance='report.html',mechanism_cases='case_atlas.html'),
        source_bindings=bindings,
        analysis_source_bindings={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'scripts').glob('research194_*.py'))})
    dump(OUT/'completion.json',completion)
    continuation=read(OUT/'continuation.json')
    continuation.update(status=completion['status'],actual_model_calls=168,remaining_unused_authorized_calls=51,
        unused_authorization_is_not_a_new_experiment_plan=True,next_steps_only_after_actual_approval=[],
        final_completion='completion.json',final_conclusions='conclusions.json')
    dump(OUT/'continuation.json',continuation)
    print(json.dumps({k:completion[k] for k in ('status','actual_model_calls','tests_passed','full_planned_transaction_scope_passes')}))

if __name__=='__main__':build()
