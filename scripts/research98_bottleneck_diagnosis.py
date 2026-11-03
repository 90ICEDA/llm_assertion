"""Offline diagnosis of research94; never calls a model or changes candidates.

Shape-only normalization below is a diagnostic counterfactual, never an accepted
proposal. Existing experiment results and independent tests are not modified.
"""
import argparse
import copy
import json
import re
from pathlib import Path
import research94_prospective_gate_pilot as p
from research93_remote_recovery_audit import response

x=p.x
ROOT,read,dump,sha=p.ROOT,p.read,p.dump,p.sha
FIELDS=('antecedent','consequent','timing','obligations')


def paired_witness(example,result):
    """Bind by full identity, not a short sample number or display label."""
    rows=result['ledger']
    selected=[r for r in rows if r['evidence_id']==example['evidence_id']]
    if len(selected)!=1:raise ValueError('evidence_identity')
    row=selected[0]
    for key in ('sample','configuration','revision','obligation','expected','observed','native'):
        if row[key]!=example[key]:raise ValueError('mismatched_'+key)
    mate=[r for r in rows if r['sample']==row['sample'] and r['configuration']==row['configuration']
          and r['obligation']==row['obligation'] and r['revision']!=row['revision']]
    if len(mate)!=1:raise ValueError('paired_revision_identity')
    revisions={r['revision']:r for r in (row,mate[0])}
    s=row['sample'];w=s['instruction']
    return dict(evidence_id=row['evidence_id'],cohort=s['cohort'],sample_id=s['sample_id'],
        transaction_id=s['transaction_id'],phase_index=s['phase'],instr_new=s['instr_new'],
        phase_name='first' if s['instr_new'] else 'held',configuration=row['configuration'],
        instruction_decimal=w,instruction_hex=f'0x{w:08x}',opcode=w&127,bit28=(w>>28)&1,bit31=(w>>31)&1,
        obligation=row['obligation'],revisions={k:dict(evidence_id=v['evidence_id'],
            expected_illegal=v['expected'],actual_illegal=v['observed'],oracle=v['oracle'],native=v['native'])
            for k,v in revisions.items()})


def run(prep,trial,out):
    x.verify(prep)
    paths=[prep/'sealed.json',trial/'outcome.json',trial/'pilot_decision.json',trial/'cost.json',
           ROOT/'scripts/research94_prospective_gate_pilot.py',ROOT/'scripts/research90_text_recovery.py',
           ROOT/'scripts/research55_native_plan_alignment.py']
    ledger=read(trial/'budget_ledger.json');assert len(ledger)==4
    calls=[];bodies=[];decoded=[];checks=[];initial=read(prep/'initial.json')
    first=read(trial/'shared/v0/model_call/candidate.json')
    results={c:read(trial/'shared/v0/native'/c/'result.json') for c in ('alignment','search','history')}
    sources={};rows_rebound=0
    for entry in ledger:
        folder=trial/entry['path']/'model_call'
        for name in ('request.json','response.stream.raw','response.assembled.json','model_edit.json','result.json'):
            paths.append(folder/name)
        req=read(folder/'request.json');body=json.loads(req['messages'][1]['content']);bodies.append(body)
        text,raw=response(folder);edit=read(folder/'model_edit.json');assert json.loads(text)==edit
        assert body['actual_model_op_rule']==dict(opcode=51,bit_index=28,bit_value=True,phase='every_sample')
        checks.append('actual_correct_rule_'+entry['path'])
        profile={k:len(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()) for k,v in body.items()}
        call=read(folder/'result.json');assert call['status']=='response_received' and raw['finish']=='stop'
        current_bad={k for a in body['current_op'] for k in a if k not in FIELDS}
        emitted_bad=[sorted(set(a)-set(FIELDS)) for a in edit['assertions']]
        analysis=dict(path=entry['path'],prompt_tokens=call['prompt_tokens'],completion_tokens=call['completion_tokens'],
            body_utf8_bytes=len(req['messages'][1]['content'].encode()),field_utf8_bytes=profile,
            json_schema_sent='json_schema' in req.get('response_format',{}),
            response_format=req.get('response_format'),local_schema_not_in_wire='format' not in req,
            correct_plan=body['actual_model_op_rule'],current_candidate_nonoutput_fields=sorted(current_bad),
            emitted_nonoutput_fields=emitted_bad,
            current_bit31_occurrences=json.dumps(body['current_op']).count('instr[31]'),
            emitted_single_bit_references=[sorted(set(map(int,re.findall(r'instr\[(\d+)\]',a['antecedent'])))) for a in edit['assertions']],
            raw_response_verified=True,finish=raw['finish'],candidate_status=call['candidate_status'])
        if entry['path']!='shared/v0':
            # Diagnostic only: remove redundant metadata, never change an expression.
            clean=copy.deepcopy(edit)
            for a in clean['assertions']:
                assert set(a)-set(FIELDS)=={'property'}
                del a['property']
            c,_=p.prior.p.TEXT_ADAPT(clean,initial)
            assert x.signature(c)==x.signature(first)
            analysis['shape_only_counterfactual']=dict(interface_parses=True,
                exact_shared_executable_signature=True,new_native_execution=False,
                old_native_result_applicable_by_exact_identity=True,experiment_acceptance_unchanged=True)
            checks.append('format_only_cannot_fix_'+entry['path'])
        for example in body['actual_feedback']['development_counterexamples']:
            cohort=example['cohort']
            result=results[cohort] if entry['path']!='shared/v0' else read(prep/'baseline_native'/cohort/'result.json')
            view=paired_witness(example,result);decoded.append(dict(call=entry['path'],**view));rows_rebound+=2
            assert view['opcode']==51 and view['bit28']==1 and view['bit31']==0
            assert view['revisions']['before']['expected_illegal']==1 and view['revisions']['before']['actual_illegal']==0
            assert view['revisions']['after']['expected_illegal']==1 and view['revisions']['after']['actual_illegal']==1
            assert all(not a['trigger'] for r in view['revisions'].values() for a in r['native']['assertions'])
            checks.append('paired_native_witness_'+entry['path']+'_'+example['evidence_id'])
        analysis['feedback_examples']=len(body['actual_feedback']['development_counterexamples'])
        analysis['feedback_examples_explicitly_decode_both_bits']=sum('bit28' in e and 'bit31' in e for e in body['actual_feedback']['development_counterexamples'])
        analysis['supplementary_controls_explicit_bit28']=sum('bit28' in e for e in body['measured_development_controls'])
        analysis['supplementary_controls_explicit_bit31']=sum('bit31' in e for e in body['measured_development_controls'])
        calls.append(analysis)
    # Verify the compressed after excerpt exactly, to separate added reading work
    # from a source corruption. No upstream lookup or independent-data access.
    rtl=bodies[0]['rtl'];before=rtl['before_op'];after=rtl['after_op']
    for rev,meta in (('before',before),('after',after)):
        f=ROOT/meta['file'];paths.append(f);assert sha(f)==meta['file_sha256']
        lines=f.read_text().splitlines(keepends=True)
        sources[rev]=''.join(lines[meta['start_line']-1:meta['end_line']])
    assert sources['before']==before['text']
    lines=sources['before'].splitlines(keepends=True)
    for e in sorted(rtl['after_op_reconstruction']['edits'],key=lambda e:e['before_start_zero_based'],reverse=True):
        lines[e['before_start_zero_based']:e['before_end_exclusive']]=e['replacement_lines']
    assert ''.join(lines)==sources['after'];checks.append('rtl_reconstruction_exact')
    # Check feedback freshness and whether it actually introduced new observations.
    init=bodies[0]['actual_feedback'];ordinary=bodies[1]['actual_feedback']
    assert init['visible_counts']==ordinary['visible_counts']
    assert init['required_untriggered']==ordinary['required_untriggered']
    assert [e['evidence_id'] for e in init['development_counterexamples']]==[e['evidence_id'] for e in ordinary['development_counterexamples']]
    checks.append('ordinary_feedback_same_measurements_not_stale_transport')
    assert bodies[2]==bodies[3];checks.append('H_R_identical_messages')
    # Negative binding tests: do not let a reformatted table create new evidence.
    e=bodies[1]['actual_feedback']['development_counterexamples'][0]
    for label,alter in [('wrong_word',lambda z:z['sample'].__setitem__('instruction',z['sample']['instruction']^1)),
                        ('wrong_sample',lambda z:z['sample'].__setitem__('sample_id',999999)),
                        ('wrong_observed',lambda z:z.__setitem__('observed',1)),
                        ('wrong_id',lambda z:z.__setitem__('evidence_id','not_an_evidence'))]:
        bad=copy.deepcopy(e);alter(bad)
        try:paired_witness(bad,results[e['cohort']])
        except ValueError:checks.append(label+'_rejected')
        else:raise AssertionError(label)
    bindings={f.relative_to(ROOT).as_posix():sha(f) for f in paths}
    facts=dict(correct_rule_present_all_calls=True,source_reconstruction_exact=True,
        raw_response_itself_uses_wrong_bit=True,no_evidence_of_transport_truncation=True,
        output_shape_inconsistent_with_current_candidate_metadata=True,
        structured_schema_only_local_not_transmitted=True,
        first_to_ordinary_same_counts_same_examples=True,
        first_to_ordinary_actual_extra_assertion_untriggered=True,
        all_forwarded_misses_have_bit28_one_bit31_zero=True,
        format_only_fix_repeats_failed_executable=True,
        H_R_same_messages_and_seed=True,
        model_internal_cause='unknown; anchoring and decoding/presentation burden are hypotheses, not identified causal effects',
        no_new_model_or_native_calls=True,accepted_versions_added=0,independent_tests_used=False)
    out.mkdir(parents=True,exist_ok=False)
    for name,obj in [('facts',facts),('request_profiles',calls),('paired_development_witnesses',decoded),
                     ('checks',dict(passed=True,count=len(checks),checks=checks)),('source_bindings',bindings)]:dump(out/f'{name}.json',obj)
    example=decoded[0]
    lines=['# research98：research94 位域与反馈瓶颈定位','',
        '本轮只读本地审计；真实模型调用0、原生执行0、新接受版本0、新独立验收0。research94所有失败与research93既有独立结果保持原样。', '',
        '## 已证实的链路事实','',
        '1. 四份实际发送请求都有正确OP规则：opcode=51、bit_index=28、每个采样适用。原服务响应本身写instr[31]，不是编译器把28改成31。响应完整终止，未发现传输截断。',
        '2. current_op把待修复的旧bit31性质同时作为antecedent和property传入，附带id/delay/property等内部字段。输出前端却只允许antecedent/consequent/timing/obligations。三份后续响应新增property后被前端拒绝。程序内部schema没有随远程请求发送；线上只有json_object，不能声称服务端已做字段schema约束。',
        '3. 局部接口反事实：仅去掉property、表达式与时序不动，三份响应虽可解析，执行签名都与已原生失败的首版完全相同。这只是本地诊断，不修订实验接受结论、不产生新模型候选。仅解决格式不足以解决漏报。',
        '4. 真实诊断确实送达。普通组与首轮反馈的计数和证据ID完全相同：新增next_sample仍依赖同一永不触发的前件。更新反馈正确增加了第二条性质的未触发记录，但没有新的区分性行为观测。不是错误读取旧响应。',
        '5. 三组后续提示没有把同一样本的bit28/bit31及before/after输出直接并列；反例指令为十进制大整数，主要反例只给before记录。补充controls已有bit28与前后行为，但没有bit31，需要跨字段自行对应。诊断是真实的，表示仍增加了定位负担。',
        '6. 修复后RTL以补丁重构方式呈现，已与真实文件逐字核验一致。旧/新RTL都有instr[31]的合法检查；历史修复实际去掉!instr[28]的跳过分支。模型选择了已有检查，未覆盖修复差异。源资料没有损坏，但补丁阅读与默认分支推理增加负担。','',
        '## 一条确切反例','',
        f"指令 {example['instruction_hex']}（十进制{example['instruction_decimal']}），opcode={example['opcode']}，bit28={example['bit28']}、bit31={example['bit31']}。初始采样 instr_new={example['instr_new']}。独立规则要求illegal=1；before实际0，after实际1。当前两条性质的前件都因bit31=0而不触发，next_sample不能补救这一点。",
        '完整配对身份包含cohort、transaction、sample、phase、configuration、revision和evidence_id；本地错误指令/采样/输出/ID负检查均拒绝。数字sample_id本身不是全局唯一键；本轮没有发现实际采样串线。','',
        '|调用|输入tokens|输出tokens|反馈条数|原始反例直接列两位|',
        '|---|---:|---:|---:|---:|']
    for c in calls:lines.append(f"|{c['path']}|{c['prompt_tokens']}|{c['completion_tokens']}|{c['feedback_examples']}|{c['feedback_examples_explicitly_decode_both_bits']}|")
    lines+=['','输入约6千tokens；没有服务截断证据，不能把“反馈过长”作为已证实根因。H/R是同信息的两次独立请求但消息和种子完全相同，不能把重复结果当作两个不同诊断策略的因果比较。','',
        '## 能下的结论与不能下的结论','',
        '已经定位到：规则到谓词没有生成时的一致性约束；输入断言元数据与输出schema不对称；反馈没将关键位差异和双版本输出绑定为紧凑诊断。原生验收有效挡住了错误，但验收本身不会保证模型修改有效。',
        '“旧性质锚定”“模型偏好显式bit31分支”“解码与跨字段对应负担”均与记录一致，但本轮没有随机受控模型干预，不能断言某一项是模型内部原因，也不能保证清理提示即可恢复。当前流程没有完整计划生成门槛；只有传入的既有正确子判断。它未约束新性质，不能据此得出完整计划门槛有效或无效。','',
        '## 下一步的最小修复边界','',
        '- 对未来请求，只输出允许编辑的四个断言字段，将旧性质明确标为已失败候选；将程序生成的property/id/delay留在本地。输出字段白名单明示；服务端schema支持须另行验证，不能假定已有支持。',
        '- 用允许的开发证据构造已绑定的十六进制/两个位值/首或保持阶段/before-after结果/实际触发表；不补写正确SVA，不扩大任何组可见证据。此报告配对表仅为本地审计，不是已授权的新模型请求。',
        '- 保持原生目标、151事务历史、重复拒绝和冻结后独立标准。对格式合法但同一错误前件的版本直接给出实际不触发证据；不靠文本匹配把bit28出现当成功。',
        '- 只有另行封存固定预算、相同信息与相同验收标准的对照，才能检验这些改动是否帮助真实生成。先导不合格即止；本轮不追加调用、不扩种子。','',
        f'本地检查{len(checks)}项通过；绑定复核{rows_rebound}条前后记录（含跨调用重复引用，非新独立证据）。', '',
        '复核命令：','```powershell',
        f'wsl -- python3 scripts/research98_bottleneck_diagnosis.py --prepared {prep.relative_to(ROOT).as_posix()} --run {trial.relative_to(ROOT).as_posix()} --out deliverables/research98_diagnosis_NEW','```']
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for name,h in bindings.items():assert sha(ROOT/name)==h
    x.verify(prep)
    print('DIAGNOSIS98',dict(checks=len(checks),paired_rows=rows_rebound,model_calls=0,native_calls=0),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ('prepared','run','out'):ap.add_argument('--'+name,type=Path,required=True)
    a=ap.parse_args();run(a.prepared.resolve(),a.run.resolve(),a.out.resolve())
