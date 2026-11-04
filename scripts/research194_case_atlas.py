"""Render existing evidence cards; never synthesize waveforms or run experiments."""
import html
import hashlib
import json
import os
import re
from pathlib import Path
import research194_report as report

ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'deliverables'
OUT=D/'reguard_mechanisms_20261103_r02/case_atlas.html'


def esc(x):return html.escape(str(x))
def pre(x):return '<pre>'+esc(x if isinstance(x,str) else json.dumps(x,ensure_ascii=False,indent=2))+'</pre>'
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def repository_path(value):
    """Resolve this repository's recorded WSL or Windows paths on either host."""
    value=str(value).replace('\\','/')
    match=re.match(r'^(?:[A-Za-z]:|/mnt/[a-z])/'+re.escape(ROOT.name)+r'(?:/(.*))?$',value)
    path=ROOT/(match.group(1) or '') if match else Path(value)
    if not path.is_absolute():path=ROOT/path
    path=path.resolve()
    if not path.is_relative_to(ROOT):raise ValueError('recorded_path_outside_repository')
    return path


def link(path,label):
    path=repository_path(path)
    return '<a href="'+esc(os.path.relpath(path,OUT.parent).replace('\\','/'))+'">'+esc(label)+'</a>'


def native_sva_record(measurement,candidate=None):
    """Return original source lines only after candidate and native binding."""
    measurement_path=None
    if isinstance(measurement,(str,Path)):
        measurement_path=repository_path(measurement)
        measurement=report.read(measurement_path,{})
    expected=(measurement or {}).get('candidate_sha256')
    if not expected:return dict(status='unavailable',reason='missing_measurement_candidate_hash')
    if candidate is not None and digest(candidate)!=expected:
        return dict(status='unavailable',reason='candidate_measurement_hash_mismatch')
    rejected=[]
    for job in (measurement or {}).get('executions',[]):
        result=job.get('result',{})
        if result.get('compile_status')!='passed' or result.get('execution_status')!='completed':
            rejected.append('native_not_successfully_executed');continue
        folder=repository_path(job['folder'])
        tb=folder/'tb.sv'
        if not tb.exists():rejected.append('missing_testbench');continue
        source=tb.read_text(encoding='utf-8')
        if hashlib.sha256(source.encode()).hexdigest()!=result.get('source_sha256'):
            rejected.append('testbench_native_source_hash_mismatch');continue
        protocol_path=folder.parent.parent/'protocol.json';protocol=report.read(protocol_path,{})
        native_candidate=protocol.get('candidate',[])
        expected_candidate=candidate
        if expected_candidate is None:
            choices=[native_candidate,*protocol.get('case',{}).get('candidate_pool',[])]
            expected_candidate=next((c for c in choices if c and digest(c)==expected),None)
        if not expected_candidate:
            rejected.append('candidate_not_bound_to_native_protocol');continue
        # The execution may contain multiple comparison candidates. Select only
        # exact recorded assertion bodies, preserving the actual native labels.
        selected=[];unused=list(native_candidate)
        for assertion in expected_candidate:
            body={k:v for k,v in assertion.items() if k!='label'}
            bound=next((a for a in unused if {k:v for k,v in a.items() if k!='label'}==body),None)
            if bound is None:break
            selected.append(dict(native_label=bound['label'],candidate_label=assertion['label']));unused.remove(bound)
        if len(selected)!=len(expected_candidate):
            rejected.append('assertion_body_not_in_native_protocol');continue
        lines=[]
        for item in selected:
            found=[line.strip() for line in source.splitlines() if re.match(r'^\s*'+re.escape(item['native_label'])+r'\s*:\s*assert\s+property\b',line) and 'ASSERT_FAIL' in line]
            if len(found)!=1:break
            lines.extend(found)
        if len(lines)!=len(selected):rejected.append('missing_or_ambiguous_native_assertion');continue
        return dict(status='bound',lines=lines,label_mapping=selected,candidate_sha256=expected,
            tb_path=str(tb),tb_source_sha256=result['source_sha256'],native_protocol_path=str(protocol_path),
            native_protocol_sha256=hashlib.sha256(protocol_path.read_bytes()).hexdigest(),
            measurement_path=str(measurement_path) if measurement_path else None,
            measurement_sha256=hashlib.sha256(measurement_path.read_bytes()).hexdigest() if measurement_path else None,
            query_id=job.get('query_id'),variant=job.get('variant'),rejected_prior_jobs=rejected)
    return dict(status='unavailable',reason='no_candidate_bound_executed_native_sva',rejected_jobs=rejected)


def native_sva(measurement,candidate=None):
    record=native_sva_record(measurement,candidate)
    if record['status']!='bound':return '<p>没有可绑定的已执行原生 SVA；候选结构见完整记录。</p>'+pre(record)
    return pre('\n'.join(record['lines']))+'<p>'+link(record['tb_path'],'实际编译的 testbench')+'</p><details><summary>候选、原生标签与源码绑定</summary>'+pre({k:v for k,v in record.items() if k!='lines'})+'</details>'


def wave(rows):
    if not rows:return '<p>此记录无可绑定的关键波形，不补造。</p>'
    if not isinstance(rows,list) or not isinstance(rows[0],dict):return pre(rows)
    keys=list(dict.fromkeys(k for row in rows for k in row))
    return report.table(rows,[(k,k) for k in keys])


def build():
    body=['<h1>REGuard 机制案例图册</h1><p>每段 SVA 均直接取自实际编译的 testbench；波形来自原生 trace。开发改善与独立验收收益分开显示，接口拒绝不算语义退化。</p>',
          '<p>主卡筛选要求正常终止、相同初始候选/模型及可判定共同独立验收，不排除被拒绝的开发 unknown 提案，也不要求实际跑满三轮。R 策略配对报告另有排除全部开发 unknown 提案的更严格敏感性子集；两者不应混用。</p>']
    path=D/'reguard_mechanisms_20261103_r02/case_cards/case_cards.json'
    for card in report.read(path,[]):
        body.append('<section><h2>'+esc(card['mechanism']+' / '+card['kind'])+'</h2>')
        if not card.get('trajectory'):
            body.append(pre(card)+'</section>');continue
        row=card['trajectory'];folder=ROOT/row['folder'];bridge=card.get('evidence_to_edit_bridge')
        if card['mechanism']=='localized_refinement':
            body.append('<p>本卡比较 S0R3 与 S0R0 整套策略，包含定位、历史保护及义务组合；独立收益不能孤立归因于局部字段修改。实际阶段统计：</p>'+pre(row.get('stage_summary')))
        body.append('<p>'+esc(f"{row['case_id']} · seed {row['seed']} · {row.get('search_strategy')} / {row['strategy']}")+'</p>')
        body.append('<p>完整正面证据链：'+esc(card.get('full_positive_chain'))+'</p>'+pre(card.get('selection_reason')))
        body.append('<h3>初始候选</h3>'+native_sva(folder/'round01/current_measurement.json',card['original_sva'])+'<details><summary>结构化初始候选</summary>'+pre(card['original_sva'])+'</details>')
        if bridge:
            rd=folder/f"round{bridge['round']:02}"
            body.append('<h3>有效修改前的原生 SVA</h3>'+native_sva(rd/'current_measurement.json',bridge.get('candidate_before')))
        body.append('<h3>关键事务波形</h3>'+wave(card.get('key_transaction_waveform',[])))
        body.append('<h3>定位与修改决定</h3>'+pre([dict(round=m['round'],localization=m.get('localization'),decision=m.get('decision')) for m in card.get('modifications',[])]))
        body.append('<h3>最终冻结 SVA</h3>'+native_sva(folder/'terminal_measurement.json',card['modified_frozen_sva']))
        body.append('<h3>独立验收</h3>'+report.table(card.get('acceptance',[]),[
            ('fault','故障'),('target_transaction_obligations','目标事务×义务'),('detected','及时检出'),
            ('late_detected','迟到检出'),('transaction_misses','完全漏报'),('false_positive_records','合法误报'),
            ('unknown_records','未知'),('full_planned_transaction_scope_pass','计划范围通过')]))
        body.append('<p>'+link(path,'完整案例、比较组及来源绑定')+'</p></section>')
    itt_path=path.with_name('itt_case_cards.json')
    body.append('<h2>ITT 独立附录：中断后保留版本</h2><p>以下仅表示截断或外层异常后，冻结保留版本仍有可核对的正面证据链；不表示完整执行三轮、整条策略通过或总体优势。严格主卡与本附录分开。</p>')
    for item in report.read(itt_path,[]):
        body.append('<section><h3>'+esc(item['mechanism'])+'</h3>')
        if not item.get('trajectory'):
            body.append(pre(item)+'</section>');continue
        row=item['trajectory'];folder=ROOT/row['folder'];bridge=item.get('evidence_to_edit_bridge')
        body.append('<p>'+esc(f"{row['case_id']} · seed {row['seed']} · {row.get('search_strategy')} / {row['strategy']}")+'</p>')
        body.append('<h4>中断原因与完整比较资格</h4>'+pre(item.get('trajectory_qualification')))
        body.append('<h4>选择规则与共同验收改善</h4>'+pre(item.get('selection_reason')))
        body.append('<h4>初始候选原生 SVA</h4>'+native_sva(folder/'round01/current_measurement.json',item['original_sva']))
        if bridge:
            body.append('<h4>真实接受修改前</h4>'+native_sva(folder/f"round{bridge['round']:02}"/'current_measurement.json',bridge.get('candidate_before')))
        body.append('<h4>关键事务波形</h4>'+wave(item.get('key_transaction_waveform',[])))
        body.append('<h4>定位、接受修改与冻结保留绑定</h4>'+pre(dict(bridge=bridge,modifications=item.get('modifications'))))
        body.append('<h4>最终保留版本原生 SVA</h4>'+native_sva(folder/'terminal_measurement.json',item['modified_frozen_sva']))
        body.append('<h4>共同独立验收</h4>'+report.table(item.get('acceptance',[]),[
            ('fault','故障'),('target_transaction_obligations','目标事务×义务'),('detected','及时检出'),
            ('late_detected','迟到检出'),('transaction_misses','完全漏报'),('false_positive_records','合法误报记录'),('unknown_records','未知')]))
        body.append('<p>'+esc(item.get('interpretation'))+'</p><p>'+link(itt_path,'完整 ITT 记录与比较版本')+'</p></section>')
    dev=D/'research194_refinement_posthoc_20261103_r01/representative_development_cards.json'
    body.append('<h2>开发阶段局部机制：正面与失败记录</h2><p>以下记录解释实际修改行为，不独自证明泛化收益。某轮提案可能被拒绝，或后来被其他版本替代。</p>')
    for name,card in report.read(dev,{}).items():
        if not isinstance(card,dict) or 'call' not in card:continue
        call=card['call']
        body.append('<section><h3>'+esc(name)+'</h3><p>'+esc(f"{call['case_id']} · {call['arm']} · round {call['round']} · {call['stage']} · {call['runner_status']}")+'</p>')
        body.append('<h4>修改前原生 SVA</h4>'+native_sva(card.get('before_measurement'),card.get('original_assertions')))
        body.append('<h4>关键事务波形</h4>'+wave(card.get('key_waveform',[])))
        body.append('<h4>定位和模型原始修改</h4>'+pre(dict(localization=card.get('localization'),model_edit=card.get('raw_model_edit'))))
        if card.get('native_proposal_executed'):
            body.append('<h4>实际执行的提案 SVA</h4>'+native_sva(card.get('proposal_measurement'),card.get('proposed_assertions')))
        else:body.append('<p>此提案未进入原生执行；接口失败不作为原生语义失败。</p>')
        body.append(pre(dict(accepted=call['accepted'],timely_gained=len(call.get('timely_gained_ids',[])),
            transaction_gained=len(call.get('transaction_gained_ids',[])),history_lost=len(call.get('any_cycle_history_lost_ids',[])),
            independent_acceptance=card.get('independent_acceptance'),caution=card.get('caution'))))
        body.append('<p>'+link(dev,'完整开发记录及测量路径')+'</p></section>')
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>REGuard 机制案例图册</title><style>body{font:15px/1.6 system-ui;max-width:1400px;margin:35px auto;padding:20px;color:#203040}section{border-top:2px solid #c8d4df;margin-top:28px;padding-top:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#eef3f7;padding:14px}.scroll{overflow-x:auto}table{border-collapse:collapse;font-size:13px}td,th{border:1px solid #ccd5df;padding:7px}a{color:#1763a3}</style><body>'+''.join(body)+'</body></html>',encoding='utf-8')
    print(OUT)


if __name__=='__main__':build()
