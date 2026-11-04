"""Readable, source-bound completion review; no execution or model calls."""
import hashlib
import json
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / 'deliverables'
OUT = D / 'reguard_mechanisms_20261104_r09'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def table(rows, columns):
    def fmt(value):
        if value is None:
            return '未知'
        if isinstance(value, float):
            return f'{value:.4f}'
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)
    return '<div class="scroll"><table><tr>' + ''.join('<th>'+escape(label)+'</th>' for _, label in columns) + '</tr>' + ''.join('<tr>'+''.join('<td>'+escape(fmt(row.get(key)))+'</td>' for key, _ in columns)+'</tr>' for row in rows) + '</table></div>'


def main():
    sources = [OUT / name for name in ('summary.json', 'tables.json', 'cost_analysis.json', 'final_audit.json')]
    sources += [D/'research198_independent_20261104_r01/native/results.json', D/'research198_finish_20261104_r01/outcome.json', D/'research198_composition_fix_20261104_r01/replay.json']
    summary, tables, costs, audit, grades, finish, replay = map(read, sources)
    if audit['status'] != 'passed' or finish['status'] != 'registered_experiment_and_delivery_complete':
        raise ValueError('finish_and_audit_required')
    sections = [r for r in costs['summary'] if r['budget_label'] == 'minimum_observed_total' or (r['axis'] == 'round' and r['budget_label'] in ('3', '5'))]
    faults = []
    for cid, fault in sorted({(r['case_id'], r['fault']) for r in grades}):
        rows = [r for r in grades if r['case_id'] == cid and r['fault'] == fault]
        model = [r for r in rows if r.get('role') != 'initial_control']
        faults.append(dict(case_id=cid, fault=fault, records=len(rows),
            all_reachable=all(r['valid_reachable_fault'] for r in rows),
            unknown=sum(bool(r['unknown_records']) for r in rows),
            unexposed=sum(bool(r.get('no_exposure_queries')) for r in rows),
            full_pass_model_versions=sum(r['full_planned_transaction_scope_pass'] for r in model),
            any_model_detection=any(r['transaction_detected'] for r in model)))
    bindings = {str(p.resolve()): sha(p) for p in sources + [Path(__file__)]}
    data = dict(summary=summary, paired=tables['paired'], common_cost_sections=sections,
        fault_qualification=faults, interactions=tables['interactions'], source_bindings=bindings,
        scope='Supplement only; no changed sealed experimental sources, no new model or native calls.')
    body = ['<!doctype html><meta charset="utf-8"><title>REGuard R198 完成核查</title><style>body{font:16px/1.65 sans-serif;max-width:1250px;margin:35px auto;padding:0 20px}table{border-collapse:collapse;font-size:14px}td,th{border:1px solid #bcc7d0;padding:8px}.scroll{overflow:auto}code{background:#eef2f6}</style>',
        '<h1>R198：自动局部优先、专用操作与回退实测</h1>',
        '<p>本批注册实验已完成，不能据此宣称所有回退分支都已覆盖、所有断言通过验收，或新方法总体优越。</p>',
        '<p><a href="report.html">本批完整表及原始索引</a> · <a href="../reguard_mechanisms_20261104_r07/report.html">此前统一实验矩阵、S0–S3 及成本曲线</a> · <a href="../research198_case_cards_20261104_r01/cards.html">七张案例卡：SVA、波形、定位与验收</a> · <a href="final_audit.json">主实验审计</a> · <a href="completion_review.json">本页数据与来源哈希</a></p>',
        '<h2>本次补齐了什么</h2>',
        f'<p>36 条轨迹全部冻结，实际调用 {summary["model_calls"]} 次，上限 180 次；已知用量 {summary["known_tokens"]:,} tokens，未知用量调用 {summary["unknown_usage_calls"]} 次。所有组最多五次调用，另按三轮、五轮和实际成本截面比较。局部优先策略先处理已有组件的可定位缺陷，再按实测失败或结构证书进入组合与再生成；接口失败与未变化提案不构成语义失败证据。</p>',
        f'<p>共接受 {summary["accepted_local"]} 次局部修改，按策略为 {escape(json.dumps(summary["accepted_local_by_policy"], ensure_ascii=False))}。这是开发接受门结果，独立收益见下表。自动流程中的专用操作不再仅依赖手写资格测试或隔离 T 组。</p>',
        '<h2>回退覆盖：两条路径分别计数</h2>',
        f'<p>真实模型确认走完“局部部分改善 → 结构证书确认仍缺义务 → 组合被拒 → 重新生成并原生判定”的轨迹有 {summary["partial_improvement_structural_three_stage_paths"]} 条。纯粹“局部被拒 → 组合被拒 → 重新生成”的同候选、已确认三阶段链有 {summary["full_native_three_stage_paths"]} 条。后者仍是未观察到的分支，不能用前者替代。编译失败、请求阶段出现或手写回退测试均不计作确认链。</p>',
        '<p><a href="fallback_paths.json">逐轨迹阶段与证书</a> · <a href="attempt_matrix.json">180 个轮次槽：未尝试、接口失败、unknown、拒绝和接受</a></p>',
        '<h2>父案例配对结果</h2><p>每个父案例使用两种子、所有比较组共同可判定的故障，再对父案例等权平均。transaction_rate 为同事务任意周期检出率，timely_rate 为及时检出率；fp_records 是合法误报记录数，不能作独立 Bug 数。必要义务保护另外统计。</p>',
        table(tables['paired'], [('group','比较'),('arm','策略'),('paired_parents','父案例数'),('transaction_rate','事务检出率'),('timely_rate','及时检出率'),('fp_records','平均误报记录'),('necessary_obligation_rate','必要义务保护率')]),
        '<h2>共同成本与轮次截面</h2><p>下表完整保留预先登记的三轮、五轮及每个配对块最小实际总成本截面，不按结果挑选预算。tokens 和 service_seconds 使用成本以内最后一个完成的检查点；service_seconds 为本批增量细化的模型服务与原生执行耗时。S0/S3 获取阶段复用旧测量，历史获取成本单独归档，不能把本表称为新一轮端到端主动搜索成本。supported_parents 表示所有组实际都达到该预算的父案例数。该分析不是严格等墙钟时间的随机重跑。</p>',
        table(sections, [('group','比较'),('axis','成本轴'),('budget_label','截面'),('arm','策略'),('paired_parents','可判定父案例'),('supported_parents','共同成本支持'),('transaction_rate','事务检出率'),('timely_rate','及时检出率'),('legal_fp_records','平均误报记录')]),
        '<h2>冻结版本的新故障验收</h2>',
        f'<p>{len(grades)} 条版本×故障记录不是 {len(grades)} 个独立 Bug。共 {summary["independent_full_scope_pass_records"]} 条记录通过完整计划范围检查；含 unknown 的记录 {summary["independent_unknown_records"]} 条，含未曝光查询的记录 {summary["independent_unexposed_records"]} 条。开发原故障和独立预留故障分别保留；本次输入及预留故障未发送至模型。</p>',
        table(faults, [('case_id','父案例'),('fault','故障'),('records','版本记录'),('all_reachable','可达确认'),('unknown','未知记录'),('unexposed','未曝光记录'),('full_pass_model_versions','完整通过模型版本'),('any_model_detection','存在模型版本检出')]),
        '<h2>边界及未被结果支持的推断</h2><ul><li>自动局部优先和纠正的操作契约一起变化；本批不能单独归因于其中一个实现改变。</li><li>这是固定开发证据的 S0/S3 × 细化策略比较；未新增 S1/S2 搜索，也未重跑在线适应性获取。</li><li>窗口限制在有限采样周期；ID Queue 为不同 ID、有限响应年龄和并发数，故障人工注入。PR #190/#242 有真实历史修复来源，不能将它们等同于完整 Ibex 异常流水线。</li><li>独立的组合权限修正适配器只使用当前保留候选的证据，避免被拒提案影响覆盖判断。全部 32 份实际组合响应回放后解析结果无变化；它不是本批收益的解释，也未混入主实验。</li><li>没有总体优势、再生成失败、预留故障漏检均是有效结果。纯局部拒绝后的完整确认链仍未观察到，未来若需要该分支的模型证据，应单独注册满足前置条件的实验。</li></ul>',
        '<p>文字勘误：封存协议 limits 及直接继承该字段的 summary 中仍有旧版 “Three rounds” 说明。实际授权、运行参数、逐轮记录和本次成本登记均为最多五次调用；三轮仅为预登记比较截面。保留封存文件不回写，本处明确纠正该描述。</p>',
        '<p><a href="../research198_composition_fix_20261104_r01/replay.json">组合解析修正回放</a> · <a href="completion_review_audit.json">本页来源及链接核验</a></p>']
    (OUT/'completion_review.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'completion_review.html').write_text('\n'.join(body),encoding='utf-8')
    # The receipt is created before checking its own link, then finalized.
    receipt = OUT/'completion_review_audit.json'
    receipt.write_text('{}',encoding='utf-8')
    links = []
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            href = dict(attrs).get('href') if tag == 'a' else None
            if not href: return
            uri = urlsplit(href)
            if not uri.scheme and uri.path:
                p = (OUT/unquote(uri.path)).resolve()
                links.append(dict(href=href,exists=p.is_file()))
    Links().feed((OUT/'completion_review.html').read_text(encoding='utf-8'))
    if not all(r['exists'] for r in links): raise ValueError('broken_review_link')
    result = dict(status='passed',model_calls=0,native_calls=0,links=links,source_bindings=bindings,
        output_hashes={n:sha(OUT/n) for n in ('completion_review.json','completion_review.html')},
        main_audit_checks=audit['checks'],scope='Supplement source and link consistency, not proof of superiority.')
    receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status='passed',links=len(links),main_checks=audit['checks'],report=str(OUT/'completion_review.html')),ensure_ascii=False))


if __name__ == '__main__':
    main()
