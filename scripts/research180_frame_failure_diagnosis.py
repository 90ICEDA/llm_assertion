"""Retrospective local diagnosis of research179; no compilation or model calls.

Bind what was actually sent to native input handshakes, trigger/check samples,
and the unmodified model response. Preserve every previous decision and seal.
"""
import argparse
import json
from pathlib import Path
import research179_frame_controller as c

P=c.ROOT/'deliverables/research179_frame_controller_prepare_20261029_r01'
R=c.ROOT/'deliverables/research179_frame_controller_run_20261029_r01'
A=c.ROOT/'deliverables/research179_frame_controller_report_20261029_r01'


def diagnose(out):
    c.verify(P);out.mkdir(parents=True,exist_ok=False);checks=[]
    def check(name,value):
        checks.append(dict(name=name,passed=bool(value)));c.dump(out/'checks.json',checks)
        assert value,name
    for directory in (A,):
        for name,h in c.read(directory/'seal.json').items():check('prior report hash '+name,c.sha(directory/name)==h)
    for name,h in c.read(A/'source_bindings.json').items():check('prior evidence hash '+name,c.sha(c.ROOT/name)==h)
    call=R/'shared/model_call';request=c.read(call/'request.json');preview=c.read(P/'request.preview.json')
    for key,value in preview.items():check('delivered request '+key,request[key]==value)
    body=json.loads(request['messages'][1]['content']);public=body['public_development']
    raw=c.read(call/'response.assembled.json')['message']['content'];parsed=json.loads(raw)
    edit=c.read(call/'model_edit.json');candidate=c.read(call/'candidate.json')
    check('response JSON preserved',parsed==edit and parsed['assertions']==candidate)
    result=c.read(call/'result.json')
    check('complete untruncated response',result['stream_terminal_received'] and result['done_reason']=='stop')
    check('misinterpreted property came from model',any(a['label']=='single_beat_frame_length' for a in candidate) and not any(a['label']=='single_beat_frame_length' for a in body['current_assertions']))
    monitor=body['interface']['monitor']
    check('previous-clock definition present','prev_complete means the previous clock accepted last' in monitor)
    check('preedge counter meaning present','acc_bytes is bytes in unfinished accepted frame before this edge' in monitor)
    check('next-edge response meaning present','registered output for accepted TLAST is checked next edge' in monitor)
    check('initial set already contains total-byte arithmetic',any('acc_bytes+beat_bytes' in a['consequent'] for a in body['current_assertions']))
    check('ten public samples present',len(public)==10)
    sample_inventory=[]
    for i,sample in enumerate(public):
        accepted=sample['accepted'];count=len(accepted);total=sum(x['bytes'] for x in accepted)
        check(f'public{i} expected equals accepted byte sum',sample['expected_length']==total)
        sample_inventory.append(dict(index=i,config=sample['config'],accepted_cycles=[x['cycle'] for x in accepted],
            accepted_beats=count,bytes_per_beat=[x['bytes'] for x in accepted],expected=total,
            anchor_cycle=sample['before'][0]['cycle'],check_cycle=sample['before'][1]['cycle'],
            legal_before_and_after=all(v[1]['valid'] and v[1]['length']==total for v in (sample['before'],sample['after'])),
            native_aliases=dict(acc='acc_bytes',prev='prev_complete',k='monitor_axis_tkeep',v='monitor_axis_tvalid',r='monitor_axis_tready',last='monitor_axis_tlast',length='frame_len',valid='frame_len_valid')))
    legal_multi=[x for x in sample_inventory if x['accepted_beats']>1 and x['legal_before_and_after']]
    check('four legal multibeat public records',len(legal_multi)==4)
    witnesses=[];all_bindings={};contexts=[]
    ev=c.read(R/'shared/evaluation.json');alarm_ids=set(ev['new_false'])
    for cfg in (0,1):
        for rev in ('before','after'):
            folder=R/'shared/native'/str(cfg)/rev;trace=c.q.s.trace(folder);native=c.read(folder/'result.json')
            check(f'{cfg}/{rev} complete native execution',native['compile_status']=='passed' and native['execution_status']=='completed')
            triggers=c.q.marker_map(native,'triggers');alarms=c.q.marker_map(native,'failures')
            frames,cancelled=c.q.independent_events(trace,cfg)
            for f in frames:
                if rev=='before':contexts.append(dict(config=cfg,anchor=f['anchor_cycle'],check=f['check_cycle'],
                    prev_complete=trace[f['anchor_cycle']]['prev'],accepted_beats=len(f['accepted']),status=f['status']))
                cy=f['check_cycle'];identifier=f'{cfg}/{rev}/single_beat_frame_length/{cy}'
                if identifier not in alarm_ids:continue
                anchor=trace[f['anchor_cycle']];response=trace[cy];accepted=f['accepted']
                expected=sum(b['bytes'] for b in accepted);prior=sum(b['bytes'] for b in accepted[:-1]);tail=accepted[-1]['bytes']
                matches=[(i,p) for i,p in enumerate(public) if p['config']==cfg and p['before'][0]['cycle']==anchor['cycle'] and p['before'][1]['cycle']==cy]
                check(identifier+' one sent record',len(matches)==1);index,sent=matches[0]
                check(identifier+' exact sent native window',sent[rev]==trace[anchor['cycle']:cy+1])
                check(identifier+' exact sent accepted transactions',sent['accepted']==accepted)
                check(identifier+' real native trigger and failure',('single_beat_frame_length',anchor['cycle']) in triggers and ('single_beat_frame_length',cy) in alarms)
                check(identifier+' own antecedent holds',bool(anchor['v'] and anchor['r'] and anchor['last'] and not anchor['prev'] and not anchor['rst']))
                check(identifier+' aligned nonoverlap timing',cy==anchor['cycle']+1 and not response['rst'])
                check(identifier+' correct frame reference',len(accepted)>1 and expected==response['length']==sent['expected_length'] and response['valid']==1)
                check(identifier+' correct monitor arithmetic',anchor['acc']==prior and prior+tail==expected and prior>0)
                check(identifier+' actual erroneous check',response['length']!=tail and candidate[2]['consequent']=='frame_len_valid && frame_len == $past(beat_bytes)')
                stalled=[v['cycle'] for v in trace[accepted[0]['cycle']:anchor['cycle']+1] if v['v'] and not v['r']]
                check(identifier+' stalls not counted as acceptance',not(set(stalled)&{b['cycle'] for b in accepted}))
                witnesses.append(dict(id=identifier,config=cfg,revision=rev,request_sample_index=index,
                    accepted_cycles=[b['cycle'] for b in accepted],accepted_beats=len(accepted),bytes_per_beat=[b['bytes'] for b in accepted],
                    prior_accumulated_bytes=prior,tail_bytes=tail,total_expected_bytes=expected,actual_output_bytes=response['length'],
                    previous_clock_completed=bool(anchor['prev']),trigger_cycle=anchor['cycle'],check_cycle=cy,
                    presented_not_accepted_cycles=stalled,matched_original_request=True,diagnosis='legal_multibeat_false_alarm',
                    trace_path=c.rel(folder/'execute.log')))
            all_bindings.update({c.rel(folder/f):c.sha(folder/f) for f in ('execute.log','result.json','tb.sv')})
    witnesses.sort(key=lambda v:(v['config'],v['revision'],v['check_cycle']))
    check('all eight alarms reconstructed',len(witnesses)==8 and {w['id'] for w in witnesses}==alarm_ids)
    check('same previous-completion value includes one and multi beats',any(x['prev_complete']==0 and x['accepted_beats']==1 for x in contexts) and any(x['prev_complete']==0 and x['accepted_beats']>1 for x in contexts))
    request_text=json.dumps(body)
    explicit_alias_map='acc_bytes' in body['interface'].get('sample_field_aliases',{})
    wrapper_disclosed='disable iff' in request_text
    c.dump(out/'request_delivery_audit.json',dict(request_path=c.rel(call/'request.json'),request_sha256=c.sha(call/'request.json'),
        preview_matched=True,public_sample_count=10,legal_multi_sample_indices=[x['index'] for x in legal_multi],
        all_eight_alarms_have_exact_sent_window=True,monitor_definition=monitor,specification=body['specification'],
        public_inventory=sample_inventory,explicit_sample_alias_map=explicit_alias_map,disable_iff_wrapper_disclosed=wrapper_disclosed,
        prompt_tokens=result['prompt_tokens'],completion_tokens=result['completion_tokens'],
        limitation='Submission log and service usage confirm supplied content, not model attention to every field. One call cannot establish the causal effect of presentation length or aliases.'))
    c.dump(out/'aligned_false_alarms.json',witnesses)
    c.dump(out/'development_contexts.json',contexts)
    diagnosis=dict(primary=dict(classification='model_predicate_and_explanation_contradict_supplied_development_information',
        evidence='prev_complete=false interpreted as single accepted beat despite four sent legal multibeat examples and an explicit previous-clock definition',
        missing_evidence_supported=False,wrong_native_cycle_or_counter_supported=False,model_internal_reason='unknown'),
        secondary=dict(alias_presentation='Short trace aliases acc/prev/k are not explicitly mapped to the SVA signal names in a dedicated schema; facts remain available and consistent.',
            reset_interface='The generated rst antecedent is cancelled by the wrapper disable iff(rst). That wrapper is not explicitly disclosed in the request. This is a separate interface-disclosure issue, not the cause of the eight length false alarms.',
            long_feedback='Only one complete response; 5539 input tokens and ten public records do not establish that the request was too long or that shortening it would help.'),
        decision=dict(current_protocol='STOP. No unchanged-prompt retry, second call, rule change, or retrospective acceptance.',
            presentation_comparison='Conditionally justified as a separate public generation-capability study, not mechanism value. Local evidence supports testing explicit sample-to-signal/anchor/check presentation, but does not predict improvement.',
            prerequisites=['Disclose the fixed clock/reset wrapper to BOTH arms as a common interface fact and revalidate locally.',
                'Fix the same model, initial candidate, full development facts, sampling, native acceptance and budget; vary only data presentation.',
                'Do not add correct replacement predicates, handwritten successful sets or independent data to either arm.',
                'Seal a new protocol and obtain its own bounded authorization before execution; research179 unused conditional call is unavailable.',
                'No full accepted version => stop; accepted version => freeze then fresh independent evaluation; no rerolls.'],
            suggested_upper_bound_if_later_selected='Two presentation arms x at most two model calls (generation and one own actual-feedback refinement), no retry/expansion. Proposed only, not sealed or authorized.'),
        historical_outcome_unchanged=True,new_accepted_versions=0,new_native_runs=0,new_model_calls=0,new_independent_runs=0,
        conditional_recovery={'success':0,'eligible':0,'rate':None},H_R_equivalence=True)
    c.dump(out/'diagnosis.json',diagnosis)
    outcome=c.read(R/'outcome.json')
    check('old refusal remains',outcome['status']=='stop_ordinary_rejects' and not outcome['real_chain_success'])
    check('no extra invocation or future tests',len(list(R.rglob('attempt.json')))==1 and not (R/'recovery').exists() and not (R/'independent').exists())
    c.dump(out/'cost.json',dict(model_calls=0,native_compiles=0,native_executions=0,formal_queries=0,independent_runs=0,kind='read_only_local_retrospective_audit'))
    table='\n'.join('|'+ '|'.join(str(w[k]) for k in ('config','revision','accepted_cycles','accepted_beats','prior_accumulated_bytes','tail_bytes','trigger_cycle','check_cycle','total_expected_bytes','actual_output_bytes'))+'|' for w in witnesses)
    summary=f'''# research180：research179 本地失败诊断

**结论：不是缺少多拍帧证据。首轮实际请求已经给出4组合法多拍样本及其前后输出，逐字覆盖本次8条误报。模型的解释和新增谓词未落实已给出的信息。** 这是对外显提案的判断，不能据此确定模型内部为何忽略信息，或认定再次调用会成功。

## 已发送什么

实际 request.json 与封存首轮请求一致。10条公共样本中，第1、4、6、9项（零起始编号）是合法多拍帧：接受周期[8,11,12]或[22,23]；各拍字节、expected_length、起始采样acc/prev、前后RTL输出均存在。4组样本包含两个RTL版本，覆盖8条误报。接口已明确 prev_complete 指前一时钟接受TLAST，acc_bytes 指本帧此前已接受字节，输出在下一采样检查；初始性质中也已有 acc_bytes+beat_bytes 的总长度表达。

模型仍说明“prev_complete为false时，帧在第一个接受拍完成”，并生成只比较尾拍字节的性质。**前一时钟未完成帧，不等于当前帧没有已接受的前序拍。** 三拍帧cycle9、10仅呈现且ready=0；实际接受为8、11、12，不能误计为五拍。

## 八条逐项对齐

配置0：8位、KEEP关闭；配置1：32位、KEEP启用。累计是起始采样中不含当前尾拍的值。

|配置|版本|实际接受周期|拍数|此前累计|尾拍字节|触发周期|检查周期|应报总字节|实际输出|
|---|---|---|---|---|---|---|---|---|---|
{table}

每条都有原生触发和下一周期失败标记；复位未打断检查。原版和修复版的这些合法输出都正确。被评估性质错误要求“实际输出=尾拍字节”，所以不是提前检出，也不是未知归因。8条是两帧×两配置×两版本的采样点，不是8个Bug。

## 瓶颈分类及限制

|假设|本地结论|
|---|---|
|合法反例未放进请求|排除：四组对应记录已实际发送，接受列表与原生采样逐项相符|
|计数或采样周期错误|未发现：独立握手组帧、acc、尾拍与下一采样输出一致|
|prev_complete规格本身歧义|文字已明确“前一时钟”；模型将其错误等同于单拍类别|
|呈现不够直观|存在可测因素：acc/prev/k等短名未提供显式别名表，未并列表达“拍数、累计、尾拍、总数”；是否导致错误未知|
|请求过长导致错误|不能由单次结果判断；输入5539 tokens、10条样本，响应完整，无法证明缩短后会更好|

另有独立接口披露问题：所有性质都包装 disable iff(rst)，请求未明确展示此包装。模型增加的rst前件因此空触发。应在任何未来协议中向所有组一致说明该公共语义；它不能解释或抵消已确认的8条多拍误报，也不能据此追改旧结果。

## 继续／停止依据

**停止research179原路线的追加调用。** 本轮只完成诊断，不修正候选或规则，不动剩余条件额度，不封存新模型实验。

可有条件准备一个独立的、固定预算的“同一开发事实、不同采样呈现”能力对照：两组共同明确已有时钟/复位包装，保持模型、初始候选、全部允许的开发信息和原生标准一致，只改变短名嵌套记录与显式采样对齐表的呈现方式。不要给处理组追加正确SVA或成功集合，不引入新的计划门槛；此实验只测公共生成能力，不能算两个机制的收益。

若决定开展，必须另行封存并授权；建议上限两组各2次（一次生成、拒绝后一次本组实际反馈），无重试、不扩种子。没有完整接受版本就停止；有接受版本才冻结并准备新独立测试。这里仅记录有依据的可选实验及停止条件，未认定该方式能够改善模型。

research179仍是普通/历史都拒绝，新增接受版本0、真实条件恢复0/0不可估计；H/R等价、576次搜索负结果和旧独立结果保持不变。本轮模型/原生/形式化/独立执行均0，{len(checks)}项本地审计通过。

可复制复核（输出目录需未存在）：
```powershell
wsl -- python3 scripts/research180_frame_failure_diagnosis.py --out deliverables/research180_diagnosis_recheck
```
'''
    (out/'SUMMARY.md').write_text(summary,encoding='utf-8')
    for p in (P/'seal.json',A/'seal.json',call/'request.json',call/'model_edit.json',call/'response.assembled.json',call/'result.json',R/'outcome.json',Path(__file__)):
        all_bindings[c.rel(p)]=c.sha(p)
    c.dump(out/'source_bindings.json',all_bindings);c.q.seal(out)
    # Recheck old seals and exact source hashes after writing only new artifacts.
    c.verify(P)
    for name,h in c.read(A/'source_bindings.json').items():assert c.sha(c.ROOT/name)==h,name
    print('DIAGNOSED180',len(checks),'checks; 8 alarms already present in sent development evidence; model/native0',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);a=p.parse_args();diagnose(a.out.resolve())
