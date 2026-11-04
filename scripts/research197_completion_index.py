"""Evidence-backed completion review; no model calls or acceptance selection."""
from collections import Counter
from html import escape
import json
from pathlib import Path
from research194_refinement_runner import ROOT,read,dump
from research194_report import table


def build():
    d=ROOT/'deliverables';out=d/'reguard_mechanisms_20261104_r07'
    main=read(out/'summary.json');extra=read(out/'corrected_isolation.json')
    original=read(d/'research197_typed_cards_20261104_r01/diagnostics.json')
    corrected=read(d/'research197_corrected_cards_20261104_r01/diagnostics.json')
    selected=read(d/'research197_case_cards_20261104_r01/selection.json')
    card_kinds={c['kind'] for c in selected['cards']}
    acceptance=read(d/'research197_combined_independent_20261104_r01/native/results.json')
    controls={(r['case_id'],r['fault']):r for r in acceptance if r['id'].endswith('/initial_control')}
    effects=[]
    for r in acceptance:
        if not r['id'].endswith('/T_corrected'):continue
        b=controls[(r['case_id'],r['fault'])]
        effects.append(dict(id=r['id'],fault=r['fault'],target_transaction_obligations=r['target_transaction_obligations'],
            initial_detected=b['transaction_detected'],corrected_detected=r['transaction_detected'],
            initial_false_positives=b['false_positive_records'],corrected_false_positives=r['false_positive_records'],
            unknown_records=r['unknown_records'],full_planned_scope_pass=r['full_planned_transaction_scope_pass']))
    rows=original['rows']+corrected['rows'];coverage=[];paths=[]
    tables=read(out/'tables.json')
    first_stages=dict(Counter(r['requested_stage'] for r in original['rows']
        if r['arm'] is None and r['id'].endswith('_R3') and r['round']==1))
    search={r['strategy']:r for r in tables['search']}
    pairs={(r['group'],r['arm']):r for r in tables['paired']}
    isolation={r['arm']:r for r in extra['paired_summary']}
    findings=[
        dict(mechanism='主动证据搜索',finding=f"S0/S1/S2/S3 的去重上下文缺口为 {search['S0']['confirmed_context_gaps']}/{search['S1']['confirmed_context_gaps']}/{search['S2']['confirmed_context_gaps']}/{search['S3']['confirmed_context_gaps']}，新增父案例义务缺口类型均为 0。",
            interpretation=f"S3 的证据数量没有优势，但接入相同 R1 后，父案例平均事务×义务检出率为 {pairs['S','S3']['transaction_rate']:.2%}，S0 为 {pairs['S','S0']['transaction_rate']:.2%}。数量与最终修复收益不同；这仍是三个父案例上的描述性结果。"),
        dict(mechanism='自动定位与回退',finding=f"主 R3 首轮阶段：{first_stages}；原主实验接受的局部修改为 0。",
            interpretation='自动流程经常未进入局部阶段；进入后又可能被接口或接受门拒绝。专用操作能够执行，不能替代定位和策略编排的端到端有效性证明。'),
        dict(mechanism='专用局部操作隔离比较',finding=f"纠正契约后接受 {extra['corrected_accepted']}/6 个局部修改；F/P/纠正 T 的父案例平均检出率为 {isolation['F']['transaction_rate']:.2%}/{isolation['P']['transaction_rate']:.2%}/{isolation['T_corrected']['transaction_rate']:.2%}。",
            interpretation='窗口与多在途匹配有独立改善，Counter 精确延迟修改失败。原 T 的冲突契约必须单列；纠正 T 仍未获得总体检出优势。'),
        dict(mechanism='组合消融',finding='A0/A1/A2/A3 的父案例平均检出率为 '+ '/'.join(f"{pairs['A',a]['transaction_rate']:.2%}" for a in ('A0','A1','A2','A3'))+'。',
            interpretation='主动搜索的收益未在自动 R3 组合中保留。本轮未证明组合增益；共同 token 和服务耗时截面另列，不能当作严格等实际耗时随机实验。')]
    for identity in sorted({r['id'] for r in original['rows']}):
        rr=sorted((r for r in original['rows'] if r['id']==identity),key=lambda r:r['round'])
        requested=[r['requested_stage'] for r in rr if r['requested_stage']]
        native=[r['requested_stage'] for r in rr if r['native_executed']]
        if any(s in requested for s in ('local','compose','regenerate')):
            paths.append(dict(id=identity,requested_stages=requested,native_executed_stages=native,
                complete_three_stage_request=all(s in requested for s in ('local','compose','regenerate')),
                complete_three_stage_native=all(s in native for s in ('local','compose','regenerate')),
                outcomes=[r['classification'] for r in rr]))
    for cid in sorted({r['case_id'] for r in rows}):
        for cohort in ('main_and_original_isolation','corrected_T'):
            rr=[r for r in rows if r['case_id']==cid and (r['id'].endswith('/T_corrected'))==(cohort=='corrected_T')]
            coverage.append(dict(case_id=cid,cohort=cohort,registered_round_slots=len(rr),requests=sum(bool(r['requested_stage']) for r in rr),
                native_executed=sum(r['native_executed'] for r in rr),native_complete=sum(r['native_complete'] is True for r in rr),
                accepted=sum(r['accepted'] for r in rr),accepted_local=sum(r['accepted'] and r['requested_stage']=='local' for r in rr),
                classifications=dict(Counter(r['classification'] for r in rr))))
    review=dict(model_calls=main['physical_dispatch_attempts']+extra['corrected_dispatches'],
        known_tokens=main['known_tokens']+extra['corrected_known_tokens'],
        unknown_usage_calls=main['unknown_usage_calls']+extra['corrected_unknown_usage_calls'],
        original_versions=66,corrected_versions=6,historical_parent_bugs=2,injected_parent_bugs=1,
        coverage=coverage,fallback_paths=paths,
        complete_three_stage_requests=sum(p['complete_three_stage_request'] for p in paths),
        complete_three_stage_native_paths=sum(p['complete_three_stage_native'] for p in paths),
        preregistered_case_card_coverage={k:k in card_kinds for k in ('active_benefit','active_no_benefit','local_success','local_failure','composition_success')},
        corrected_independent_effects=effects,
        main_r3_first_request_stages=first_stages,mechanism_findings=findings,
        independent_records=len(acceptance),independent_full_scope_pass_records=sum(r['full_planned_transaction_scope_pass'] for r in acceptance),
        independent_unknown_version_fault_records=sum(bool(r['unknown_records']) for r in acceptance),
        independent_unexposed_version_fault_records=sum(bool(r['no_exposure_queries']) for r in acceptance),
        limitations=[
            'Response windows are compiled over 1..32 sampled cycles, not arbitrary unbounded SVA sequences.',
            'ID Queue uses three unique outstanding IDs and response age 1..8; same-ID reuse and arbitrary concurrency are not covered.',
            'The ID Queue development defect is injected. Only common_cells PR #190 and PR #242 are historical repairs.',
            'Original typed-only T had a contradictory operation example. Its results remain separate from the six corrected requests.',
            'A requested stage, a parsed operation, native execution, gate acceptance and independent improvement are distinct events.',
            'Common-cost analysis selects completed prefixes; it is not a randomized equal-wall-time experiment.',
            'Qualification probes written by the experimenter are excluded from real model success counts.',
            'Failures and absence of superiority are experimental results; missing successful branch execution remains visible.'])
    dump(out/'remaining_work_review.json',review)
    body=['<!doctype html><meta charset="utf-8"><title>R197 remaining work review</title>',
        '<style>body{font:15px/1.6 system-ui;max-width:1300px;margin:30px auto;padding:20px}table{border-collapse:collapse}td,th{border:1px solid #bbc9d2;padding:7px}.scroll{overflow:auto}pre{white-space:pre-wrap;background:#edf3f7;padding:16px}</style>',
        '<h1>剩余工作：执行覆盖与结论边界</h1>',
        '<p>本轮加入两个真实历史修复和一个明确标注的注入故障，对响应窗口、多在途匹配及三轮回退进行实际模型实验。原 T 与纠正 T 分开保存。执行完成、接受修改与独立收益分别统计。</p>',
        '<p><a href="report.html">S/R/A 表、成本曲线及独立验收</a> · <a href="remaining_work_review.json">完整覆盖矩阵</a> · <a href="combined_audit.json">两批授权与联合验收审计</a></p>',
        '<h2>案例与来源</h2>',
        '<ul><li>stream_delay：common_cells <a href="https://github.com/pulp-platform/common_cells/pull/190">PR #190</a>，有限响应窗口、精确延迟和握手。</li>',
        '<li>delta_counter：common_cells <a href="https://github.com/pulp-platform/common_cells/pull/242">PR #242</a>，溢出跨周期捕获与保持。</li>',
        '<li>ID Queue：上游真实 RTL，开发故障为人工注入；三个不同 ID 同时在途，包含反向响应、peek 与 clear。</li></ul>',
        '<p><a href="../reguard_mechanisms_20261104_r06/report.html">来源、原生资格验证与封存请求</a></p>',
        '<h2>机制收益与失败原因</h2>',table(findings,[('mechanism','机制'),('finding','实际结果'),('interpretation','解释与边界')]),
        '<h2>逐案例执行覆盖</h2>',table(coverage,[(k,k) for k in coverage[0]]),
        '<h2>实际回退覆盖</h2>',
        '<p>local → compose → regenerate 三阶段均有请求的轨迹：'+str(review['complete_three_stage_requests'])+'；三个阶段均到达原生执行的轨迹：'+str(review['complete_three_stage_native_paths'])+'。接口失败不记为原生成功。</p>',
        table(paths,[(k,k) for k in paths[0]]) if paths else '<p>没有已尝试的局部回退轨迹。</p>',
        '<h2>原始与纠正操作契约</h2><p><a href="../research197_typed_cards_20261104_r01/cards.html">全部原 T 案例</a> · <a href="../research197_corrected_cards_20261104_r01/cards.html">全部纠正 T 案例</a> · <a href="../research197_case_cards_20261104_r01/cards.html">机制案例与独立结果</a></p>',
        '<h2>纠正组独立效果</h2><p>以下以同一案例的初始冻结候选为控制。检出单位为去重的事务×义务，不能当成独立 Bug 数量；两个种子也不是两个父 Bug。不同故障复用同一合法轨迹，误报数不能跨故障相加当成独立样本。</p>',
        table(effects,[(k,k) for k in effects[0]]),
        '<p>主实验案例卡覆盖（false 表示未找到符合既定规则的实例）：</p><pre>'+escape(json.dumps(review['preregistered_case_card_coverage'],ensure_ascii=False,indent=2))+'</pre>',
        '<h2>适用范围</h2><pre>'+escape(json.dumps(review['limitations'],ensure_ascii=False,indent=2))+'</pre>']
    (out/'remaining_work_review.html').write_text('\n'.join(body),encoding='utf-8')
    page=out/'report.html';html=page.read_text(encoding='utf-8')
    if 'remaining_work_review.html' not in html:
        page.write_text(html+'\n<p><a href="remaining_work_review.html">剩余工作完成核查：来源、实际操作、回退覆盖与限制</a></p>',encoding='utf-8')
    print({k:review[k] for k in ('model_calls','known_tokens','complete_three_stage_requests','complete_three_stage_native_paths')},flush=True)


if __name__=='__main__':build()
