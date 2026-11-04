"""Read-only, scope-explicit consolidation of the R195 follow-up experiments."""
import hashlib
import html
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'deliverables'
OUT = D / 'reguard_mechanisms_20261103_r03'
PATHS = {
    'qualification': 'research195_refinement_qualification_20261103_r01',
    'prepare': 'research195_refinement_prepare_20261103_r01',
    'execution': 'research195_refinement_execute_20261103_r01',
    'independent': 'research195_refinement_independent_20261103_r02',
    'independent_failed': 'research195_refinement_independent_20261103_r01',
    'independent_compat': 'research195_refinement_independent_compat_20261103_r01',
    'refinement_report': 'research195_refinement_report_20261103_r01',
    'active': 'research195_active_native_20261103_r01',
    'cost': 'research195_cost_sections_20261103_r01',
    'uart': 'research195_refinement_uart_replay_20261103_r02',
    'history': 'research195_history_independent_20261103_r01',
    'history_dev': 'research195_history_report_20261103_r01',
}


def read(key, name, default=None):
    p = D / PATHS[key] / name
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default


def link(key, name, label):
    p = D / PATHS[key] / name
    if not p.exists():
        return html.escape(label) + '（尚未生成）'
    return f'<a href="../{PATHS[key]}/{name}">{html.escape(label)}</a>'


def table(headers, rows):
    return '<table><thead><tr>' + ''.join(f'<th>{html.escape(str(h))}</th>' for h in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{html.escape(str(v))}</td>' for v in row) + '</tr>' for row in rows) + '</tbody></table>'


def build():
    OUT.mkdir(exist_ok=True)
    old = {}
    for name in ('source_bindings.json', 'cost_source_bindings.json'):
        old.update(json.loads((D/'reguard_mechanisms_20261103_r02'/name).read_text(encoding='utf-8')))
    changed = [p for p, h in old.items() if not (ROOT/p).exists() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest() != h]
    if changed:
        raise ValueError(f'Previous sealed artifacts changed: {changed}')
    exe = read('execution', 'outcome.json', {})
    ind = read('independent', 'outcome.json', {})
    active = read('active', 'analysis.json', {})
    audit = read('active', 'audit.json', {})
    cost = read('cost', 'analysis.json', {})
    qualification = read('qualification', 'results.json', [])
    uart = read('uart', 'qualification.json', {})
    history = read('history', 'report.json', {})
    refinement = read('refinement_report', 'report.json', {})
    model_summary = refinement.get('summary', {})
    refine_done = ind.get('status') == 'completed'
    active_done = active.get('status') == 'completed' and audit.get('status') == 'passed'
    checks = [
        ['窗口、事务匹配、合法例外的局部修改', '模型实测与独立验收流程已完成' if refine_done else '资格验证完成；模型对照/独立验收进行中', '1–2 周期回溯因果窗口、单在途数据匹配、flush 例外；精确延迟因 unknown 保留 6 个未尝试身份。不能外推至一般响应窗口、多在途事务 ID 或乱序。'],
        ['隔离贡献与实际成本', '已完成历史成本截面；F/P/L 已完成' if refine_done else '已完成历史成本截面；F/P/L 进行中', 'F 无定位自由改写；P 有定位自由改写；L 同定位局部修改。三组固定证据、断言结构和历史门。成本截面只使用预算内完成的调用。'],
        ['可变查询成本与新时序覆盖', '已完成注册比较与原生审计' if active_done else '注册原生比较进行中', 'Arbiter/Counter，2 个配对种子，24/72/216 周期的生成时序；S2、无成本主动、有成本主动。仍是有限生成池。'],
        ['UART 接入与历史修复来源', '已完成集成重放及新增真实历史案例', 'UART 为归档响应端到端原生重放，不是新模型实验；新增 common_cells PR #242，完成原始缺陷复现与预留输入验收。'],
    ]
    completion = dict(version='research195', checks=checks, previous_bound_files=len(old), previous_hash_mismatches=changed,
                      actual_model_calls=exe.get('actual_reserved_calls'), model_execution=exe, independent=ind,
                      model_result_summary=model_summary,
                      active_complete=active_done, uart_causal_comparison_eligible=False,
                      uart_inherited_field_correction='Archived outcome inherited causal_comparison_eligible=true; provenance is archival, so this report excludes it from causal model comparisons.',
                      claim='Bounded follow-up validation; not proof of overall superiority or completion of all TCAD evidence requirements.')
    (OUT/'completion.json').write_text(json.dumps(completion, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    parts = ['<!doctype html><html lang="zh"><meta charset="utf-8"><title>REGuard research195 补充验证</title><style>body{font:16px/1.7 system-ui,sans-serif;margin:36px auto;max-width:1280px;padding:0 24px;color:#182638}table{border-collapse:collapse;width:100%;margin:20px 0}td,th{border:1px solid #cbd4df;text-align:left;padding:10px;vertical-align:top}th{background:#eaf0f6}h1,h2{line-height:1.3}a{color:#165d9b}.note{background:#fff4dc;padding:16px}img{max-width:100%}code{overflow-wrap:anywhere}</style>',
             '<h1>REGuard：覆盖、贡献隔离与实际成本补充验证</h1>',
             '<p>本轮沿用既有执行器、参考监视器和历史保护门。旧 research194 的 '+str(len(old))+' 个绑定文件哈希复核全部一致。新增实验、授权和结果独立存放；手写资格验证、归档响应重放、真实模型输出分别计数。</p>',
             table(['任务','当前状态','范围与边界'], checks),
             '<h2>1. 真实原生资格验证与 F/P/L 对照</h2>',
             '<p>以下是手写控制修改的原生资格验证，作用是证明修改操作可执行、对应证据可判定；不计作 LLM 的成功。Delay 的 unknown 来自告警无法匹配参考义务，而非编译或执行失败。</p>']
    qr=[]
    for r in qualification:
        before=r.get('before',{});after=r.get('after',{})
        qr.append([r['fixture'],r.get('operator'),before.get('detected'),after.get('detected'),str(before.get('fp'))+' → '+str(after.get('fp')),str(before.get('unknown'))+' → '+str(after.get('unknown')),r.get('decision',{}).get('accepted')])
    parts += [table(['类型','结构化操作','修改前检出','修改后检出','合法误报','unknown','历史门接受'],qr),
              '<p>'+link('qualification','results.json','资格结果')+' · '+link('prepare','paired_information_audit.json','同证据配对审计')+' · '+link('refinement_report','report.html','真实模型比较与失败分类')+' · '+link('independent','results.json','冻结版本预留输入验收')+'</p>',
              '<p>F 与 P 的差异是定位信息；P 与 L 的差异是修改空间约束。全部组禁止新增、删除、重绑断言，避免把义务组合的收益归因给局部修改。预留输入使用相同开发故障，不能称为未见故障泛化。</p>',
              '<p>独立验收 r01 曾因新生成器未提供 semantic_key 查询元数据而异常终止。r02 用独立兼容入口补齐该字段，保留原输入、ID、随机种子和所有冻结候选，并保存逐输入一致性检查。失败作业成本单列；没有据验收效果换样例、重新修改 SVA 或追加模型调用。此失败属于执行接口，不计作模型失败。</p>',
              '<p>'+link('independent_compat','query_metadata_diff.json','元数据差异与波形一致性')+' · '+link('independent_compat','original_incident.json','原生失败成本原记录')+' · '+link('independent_compat','incident_correction.json','失败位置归因更正')+'</p>',
              table(['类型','组','注册身份','真实模型调用','门接受','通过语义修复资格检查','接受但目标组件无触发'],[[r['fixture'],r['arm'],r['population'],r['model_calls'],r['accepted'],r.get('semantic_repair_qualified',0),r.get('accepted_component_inactivity',0)] for r in refinement.get('by_fixture_arm',[])]),
              '<p>真实调用：'+str(model_summary.get('actual_model_calls','待汇总'))+'；实际已知 tokens：'+str(model_summary.get('known_tokens','待汇总'))+'。失败分类原样保留：<code>'+html.escape(json.dumps(model_summary.get('classifications',{}),ensure_ascii=False))+'</code>。语义资格尚未确定的项不计为成功；门接受并不等于时序组件修复成功。</p>',
              '<p>独立验收后的有效非空触发改善为 F/P/L = 4/4/2，主要是窗口及 flush 例外的合法误报减少，没有增加目标检出。2 个窗口 L 提案让目标组件在开发和独立输入中均不触发，借助另一条断言维持聚合检出而通过门；不计为有效时序修复。2 个匹配 L 提案丢失已有目标，被共享历史门拒绝。局部修改没有在本轮证明比同定位信息的自由修改更稳定。</p>' if refine_done else '',
              '<p>流程完成不等于完整义务验收通过。窗口和匹配仍各检出 14/16 个事务×义务目标，例外为 2/4；精确延迟为 11/29 且仍有 3 项 unknown，不进入可判定比较。独立验收是新输入、同开发故障，不作为未见故障泛化证据。</p>' if refine_done else '',
              '<p>'+link('refinement_report','cost_sections.json','新 F/P/L 的实际 token 完成前缀截面')+'：在 16k/32k/64k 截面，各组完成 4 次调用，非空触发改善 F/P/L 为 2/2/0；较大的 exception 调用尚未完成。逐配对 min-total 截面仅 F/P/L = 5/1/0 次调用完成，其余保持初始。一次调用不可拆分，因此共同截面不代表三组实际支出相同；组件零触发状态在成本表中仍单列。</p>' if refine_done else '',
              '<h2>2. 实际 token 成本共同截面</h2>',
              '<p>回溯 64 条旧轨迹，先按实际 prompt+completion tokens 和接受历史固定检查点，再映射已有验收记录。失败、截断和无收益调用仍收费；超预算响应不计入收益。192 个比较单元、96 行汇总，新执行 18 个原生任务补齐缺失中间版本，新增模型调用为 0。此处复用旧测试集，不是新独立验收。</p>']
    cr=[]
    for r in cost.get('summary',[]):
        if r['group']=='R' and str(r['budget']) in ('32768','65536','minimum_observed_total'):
            cells=[c for c in cost.get('cells',[]) if c['group']=='R' and str(c['budget_label'])==str(r['budget']) and c['eligible']]
            supported=[]
            for case in sorted({c['case_id'] for c in cells}):
                cc=[c for c in cells if c['case_id']==case]
                if len(cc)==2 and all(c['common_observed_support'] for c in cc):
                    supported.append(statistics.mean(c['mean_metrics'][r['arm']]['transaction_rate'] for c in cc))
            support_mean=f'{statistics.mean(supported):.3f}' if supported else '无共同支持'
            cr.append([r['budget'],r['arm'],r['paired_parents'],r['supported_parents'],f"{r['parent_macro_transaction_rate']:.3f}",support_mean,f"{r['parent_macro_legal_fp_contexts']:.3f}"])
    parts += [table(['token 截面','方法','可配对父案例','实际花费支持父案例','全部配对父案例：事务×义务检出率','仅支持子集：事务×义务检出率','全部配对父案例：合法误报上下文均值'],cr),
              '<p>“可配对”包括已终止并保持冻结状态的轨迹；全部配对均值包括这些预算不足的提前终止轨迹，不能读作支持子集均值。“实际花费支持”要求全部组最终实际消耗达到该截面，但不保证截面内已完成非零调用。minimum_observed_total 在每个父案例/种子内取各组总消耗最小值，不同案例的数值不同；其中 R3 有 6/8 个案例×种子截面尚未完成首次模型调用。高预算点不能解释为全部组进行了等量推理；tokens 也不能替代墙钟成本。旧数据字段 transaction_rate 的分母实为事务×义务目标，本报告已明确更正显示名称。</p>',
              '<p>'+link('cost','curves.html','成本图和可下载 SVG')+' · '+link('cost','report.html','完整 R/S/A 截面')+' · '+link('cost','physical_cost.json','新增原生物理成本')+'</p>',
              '<h2>3. 可变查询成本的主动选择</h2>',
              '<p>同一候选池和初始断言比较 S2、主动选择去除成本项、有成本主动选择。每个设计/种子/策略最多 4 次查询；24、72、216 周期时序覆盖握手保持、确认、复位、计数边界、load/clear、暂停。新增输入通过生成器构造，超出旧固定查询集合，但尚不是通用时序约束求解器。</p>']
    ar=[]
    for r in active.get('tables',[]):
        ar.append([r['strategy'],r['actual_queries'],r['actual_sampled_cycles'],f"{r['native_seconds']:.2f}",f"{r['planning_seconds']:.2f}",r['pooled_distinct_new_contexts'],len(r['exclusive_context_ids']),r['critical_unknown'],r['unknown_evidence_records']])
    if ar:parts.append(table(['策略','真实查询','采样周期','原生秒','规划秒','去重缺口上下文','独有上下文','关键 unknown','保留的 unknown 证据片段'],ar))
    if active_done:
        parts += ['<p>全部 112 个原生作业完成，3,187 项来源/执行/参考结果审计通过。按成本感知 / 无成本主动 / S2 顺序：同 192 周期截面的平均新增上下文为 62.75 / 31.5 / 32.75；同 4 次查询则为 62.75 / 274.25 / 174。共同实际耗时截面下，成本感知策略对两个对照均在 4/4 个案例×种子配对中落后。</p>',
                  '<p>机制分析：Arbiter 的主动查询语义分歧评分全部为 1，无法继续区分选择价值；成本感知策略 16/16 次选择 24 周期查询。收益分子没有预测长波形能贡献多少新上下文，除以周期数造成短查询偏置。固定编译开销较高，缩短波形不等于同比节省耗时。unknown 证据片段仍单独保留，不当成合法或通过。</p>']
    parts += ['<p>缺口上下文包含首次违例未及时检出及合法误报，完全漏报另列。周期成本、编译执行耗时、规划耗时、锁等待分别记录。固定编译开销可能使周期节省不能转化成耗时收益；共同截面不计入尚未完成或超预算查询。</p>',
              '<p>'+link('active','report.html','主动搜索完整报告')+' · '+link('active','analysis.json','配对结果与限定条件')+' · '+link('active','audit.json','原生结果审计')+' · '+link('active','paired_cost_views.png','周期/查询/耗时三轴曲线')+' · '+link('active','wall_cost_analysis.json','实际耗时截面')+'</p>',
              '<h2>4. UART 后续版本接入与真实历史修复</h2>',
              '<p>UART 的未映射义务证据在定位、请求构造、提案执行、历史门和冻结过程中保留。归档响应仅改变合取顺序，新执行 6 个原生任务，因无进展被拒绝并冻结初始版本；模型调用为 0。归档 outcome 继承的 causal_comparison_eligible=true 字段不适用于此重放，本报告明确归一为 false，不纳入模型贡献比较。</p>',
              '<p>'+link('uart','qualification.json','UART 原始记录及重放来源')+'</p>',
              '<p>新增真实父 Bug：<a href="https://github.com/pulp-platform/common_cells/pull/242">pulp-platform/common_cells PR #242</a>。原始修复涉及 sticky overflow 寄存器复位极性；保存官方 PR、commit、父版本及原始 RTL，验证精确上游差异。它与旧人工 Counter 故障是不同父 Bug，但仍属于同一设计家族。</p>']
    hr=[]
    for r in history.get('rows',[]):
        hr.append([r['control'],str(r['detected_obligation_transactions'])+'/'+str(r['targets']),str(r['detected_transactions'])+'/'+str(r['target_transactions']),r['legal_fp_samples'],len(r.get('critical_unknown',[]))])
    parts += [table(['冻结手写版本','义务×事务检出','事务检出','合法误报样本','unknown 项'],hr),
              '<p>预留输入验证中，延迟修正后的手写断言检出 6/6 个违例事务，但只保护 6/10 个义务目标；仍漏掉 sticky-hold 目标。例外修正减少合法误报，却没有目标有效触发或新增检出。完整验收均未通过。“complete” 是控制版本名称，不代表通过。此处是手写版本在同一真实故障的新输入验证，不是模型结果或未见故障泛化。</p>',
              '<p>'+link('history','report.json','预留输入验收')+' · '+link('history_dev','report.json','开发资格验证')+'</p>',
              '<h2>结论的适用范围</h2>',
              '<p class="note">允许结果为无收益或负收益。窗口/匹配/例外控制的资格通过不能代替模型稳定性证据；共同成本截面不能代替足量配对重复；两个设计的主动选择不能代替跨机制普遍优势；UART 集成重放不能代替新模型测试。多在途事务、一般可变窗口、更多真实协议/流水线父 Bug，以及模型对未见故障的独立增益仍需后续实验。</p>',
              '<p><a href="completion.json">机器可读状态</a> · <a href="source_bindings.json">报告来源哈希</a> · <a href="unit_test_validation.json">17 项定向测试</a> · <a href="delivery_audit.json">最终交付审计</a> · <a href="../reguard_mechanisms_20261103_r02/report.html">保持不变的上一版报告</a></p></html>']
    (OUT/'report.html').write_text('\n'.join(parts),encoding='utf-8')
    bindings={}
    for key in PATHS:
        for name in ('results.json','analysis.json','audit.json','report.json','report.html','outcome.json','qualification.json','protocol.json','seal.json','paired_information_audit.json','physical_cost.json','plan.json','wall_cost_analysis.json','mechanism_diagnostics.json','compatibility_protocol.json','query_metadata_diff.json','original_incident.json','incident_correction.json','cost_sections.json','case_cards.json','phase_costs.json'):
            p=D/PATHS[key]/name
            if p.exists():bindings[str(p.relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(p.read_bytes()).hexdigest()
    bindings[str(Path(__file__).resolve().relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (OUT/'source_bindings.json').write_text(json.dumps(bindings,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(OUT/'report.html'),previous_bound_files=len(old),refinement_complete=refine_done,active_complete=active_done)))


if __name__=='__main__':
    build()
