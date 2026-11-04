"""Read-only, raw-record audit of two real A-arm outcomes; no model/simulator."""
import argparse
import copy
import hashlib
import html
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode=True
import research188_drop_binding_audit as b

p,s,ROOT=b.p,b.s,b.ROOT
RUN=ROOT/'deliverables/research192_ablation_20261103_r01'
TEST=ROOT/'deliverables/research192_independent_20261103_r01'


def main(out):
    out.mkdir(parents=True,exist_ok=False)
    bindings={};checks=[]
    def text(path):
        value=path.read_bytes();bindings[s.rel(path)]=hashlib.sha256(value).hexdigest()
        return value.decode('utf-8')
    def read(path):return json.loads(text(path))
    def ck(name,ok):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    def native_audit(job,candidate,exact_bench=True):
        folder=Path(job['folder']);raw=read(folder/'result.json');log=text(folder/'execute.log')
        for key,prefix in [('failures','ASSERT_FAIL'),('triggers','TRIGGER')]:
            markers=[dict(id=a,detail=z.strip()) for a,z in re.findall(r'^'+prefix+r'\s+(\S+)(.*)$',log,re.M)]
            ck(s.rel(folder)+' '+key+' raw log binding',markers==raw[key])
        ck(s.rel(folder)+' completed command',read(folder/'compile.json')['exit_code']==0 and
           read(folder/'execute.json')['exit_code']==0 and 'NATIVE_RUN_COMPLETE' in log)
        ck(s.rel(folder)+' execution result',raw==job['result'])
        tb=text(folder/'tb.sv')
        if exact_bench:ck(s.rel(folder)+' exact candidate bench',tb==p.bench(candidate,job['depth'],job['policy'],job['rows']))
        traces=s.traces(folder);ref=p.q.reference(traces,job['depth'])
        ck(s.rel(folder)+' reference known',not ref['unknown'])
        return traces,ref,raw
    results=read(TEST/'results.json');grades=read(TEST/'grades.json')
    test_jobs=read(TEST/'executions.json');test_measurements=read(TEST/'measurements.json')
    renamed=read(TEST/'renamed_properties.json')
    cards=[]
    for seed,arm in [(19207,'A3'),(19219,'A1')]:
        folder=RUN/f'seed{seed}'/arm
        initial=read(folder/'initial.json');candidate=read(folder/'model_call/candidate.json')
        edit=read(folder/'model_call/model_edit.json');terminal=read(folder/'terminal.json')
        sva=text(folder/'model_call/candidate.sva');decision=read(folder/'decision.json')
        measured=read(folder/'measurement.json');baseline=read(folder/'baseline_measurement.json')
        jobs=read(folder/'native/executions.json');protected=baseline['detected_ids']
        recomputed=b.bound_measure(candidate,jobs,protected)
        for field in ('ordinary_accept','historical_accept','detected_ids','triggered_ids','public_targets',
                      'historical_targets','lost','false_positives','critical_unknown'):
            ck(f'{seed}/{arm} independent recomputation {field}',recomputed[field]==measured[field])
        ck(f'{seed}/{arm} accepted terminal exact real proposal',terminal==candidate and decision['accepted'])
        if arm=='A3':
            changed=copy.deepcopy(initial);changed[0]['antecedent']='first_present'
            ck('A3 exactly one localized antecedent edit',candidate==changed and
               edit['edits']==[dict(op='replace_field',assertion=initial[0]['label'],field='antecedent',value='first_present')])
        else:
            ck('A1 exact model expression adaptation',p.adapt(edit)==candidate)
            a=next(a for a in candidate if a['label']=='stalled_first_oversize_drop')
            ck('A1 stalled response entailed by trigger',a['consequent']=='!m_axis_tready' and '!m_axis_tready' in a['antecedent'])
        excerpts=[]
        for job in jobs:
            traces,ref,native=native_audit(job,candidate)
            if job['depth']!=16 or job['revision']!='before':continue
            for event in ref['events']:
                cy=event['first']['cycle'];assertion=[]
                for a in candidate:
                    assertion.append(dict(label=a['label'],trigger=any(r['id']==a['label'] and r['detail']==f'cycle={cy}' for r in native['triggers']),
                        failed=any(r['id']==a['label'] and r['detail']==f'cycle={cy}' for r in native['failures'])))
                target=Path(job['folder']);wave=target/'wave.vcd'
                if wave.exists():bindings[s.rel(wave)]=s.sha(wave)
                excerpts.append(dict(scene=job['scene_id'],first_violation_cycle=cy,
                    accepted_beats=len(event['accepted']),output_handshakes=len(event['outputs']),
                    samples=[r for r in traces if cy-2<=r['cycle']<=cy+2],assertions=assertion,
                    waveform=s.rel(wave),raw_log=s.rel(target/'execute.log'),testbench=s.rel(target/'tb.sv')))
        # Check the old protection by re-adjudicating the original archived logs.
        old_jobs=[]
        for depth in p.q.DEPTHS:
            for policy in p.q.POLICIES:
                for rev in ('before','after'):
                    f=p.ARCHIVE/'native'/str(depth)/policy/rev
                    old_jobs.append(dict(scene_id=f'{depth}/{policy}',depth=depth,policy=policy,revision=rev,
                        folder=str(f),rows=p.q.rows(depth,policy),result=read(f/'result.json')))
        old=b.bound_measure(initial,old_jobs,protected)
        ck(f'{seed}/{arm} initial historical detections recomputed',old['detected_ids']==baseline['detected_ids'])
        for job in old_jobs:
            if job['depth']==16 and job['revision']=='before':
                traces,ref,raw=native_audit(job,initial,exact_bench=False)
                for ev in ref['events']:
                    cy=ev['first']['cycle']
                    excerpts.append(dict(stage='initial_baseline',scene=job['scene_id'],first_violation_cycle=cy,
                        samples=[r for r in traces if cy-1<=r['cycle']<=cy+1],
                        original_assertion_trigger=any(r['id']==initial[0]['label'] and r['detail']==f'cycle={cy}' for r in raw['triggers']),
                        original_assertion_failed=any(r['id']==initial[0]['label'] and r['detail']==f'cycle={cy}' for r in raw['failures']),
                        raw_log=s.rel(Path(job['folder'])/'execute.log'),waveform=s.rel(Path(job['folder'])/'wave.vcd')))
        independent=next(r for r in results if r['experiment']=='ablation' and r['seed']==seed and r['arm']==arm)
        ck(f'{seed}/{arm} independent exact terminal binding',independent['sha256']==s.sha(folder/'terminal.json'))
        key=independent['physical_version'];rechecked=b.bound_measure(renamed[key],test_jobs)
        for field in ('detected_ids','triggered_ids','public_targets','historical_targets','false_positives','critical_unknown'):
            ck(f'{seed}/{arm} independent raw re-adjudication {field}',rechecked[field]==test_measurements[key][field])
        for field in ('passed','exposed','misses','missing_exposure','unknown','false_positives','whole_scope_pass'):
            ck(f'{seed}/{arm} independent grade {field}',independent[field]==grades[key][field])
        example=next(v for v in grades[key]['per_scene'] if v['exposed_targets'] and
                     (bool(v['false_negative_ids']) if arm=='A1' else v['passed']))
        selected_job=next(j for j in test_jobs if j['scene_id']==example['scene_id'] and j['revision']=='before')
        traces,ref,raw=native_audit(selected_job,renamed[key],exact_bench=False)
        event=ref['events'][0];cy=event['first']['cycle']
        test_excerpt=dict(scene=example['scene_id'],grade=example,
            samples=[r for r in traces if cy-2<=r['cycle']<=cy+2],
            raw_log=s.rel(Path(selected_job['folder'])/'execute.log'),waveform=s.rel(Path(selected_job['folder'])/'wave.vcd'))
        newly_detected=sorted(set(measured['detected_ids'])-set(protected))
        lost=sorted(set(protected)-set(measured['detected_ids']))
        ck(f'{seed}/{arm} loss identity exact',lost==decision['lost'])
        if arm=='A1':ck('A1 total unchanged but identity replaced',len(protected)==len(measured['detected_ids'])==2 and len(lost)==len(newly_detected)==2)
        else:ck('A3 both old and new protected',len(protected)==2 and len(measured['detected_ids'])==4 and not lost)
        cards.append(dict(seed=seed,arm=arm,real_model=True,kind='localized_improvement' if arm=='A3' else 'accepted_historical_regression',
            original_sva=[f"{a['label']}: assert property (@(posedge clk) disable iff(rst) ({a['antecedent']}) |-> ({a['consequent']}));" for a in initial],
            modified_sva=sva,model_edit=edit,localization=read(folder/'localization.json'),
            causal_explanation=('首呈现恰好ready=1时旧前件不触发。真实模型仅删除!ready限制，原响应约束保持；两种ready类别都检出且合法事务无误报。' if arm=='A3' else
                '模型误将已确认的stalled违例报警当作应消除的问题。新的stalled性质前件已含!ready，响应仍为!ready，因此触发却永远不失败。ready性质要求同拍!ready，仅保留ready类检出。普通门只要求公共ready目标，没有阻止已知stalled检出丢失。'),
            old_detected=protected,new_detected=measured['detected_ids'],gained=newly_detected,lost=lost,
            native_gate=dict(actual=decision,ordinary_accept=measured['ordinary_accept'],historical_accept=measured['historical_accept'],
                note='历史门布尔值来自同一真实提案的已执行测量；不是另一次R3模型试验'),
            development=dict(targets=4,detected=len(measured['detected_ids']),false_positives=len(measured['false_positives']),
                unknown=measured['critical_unknown'],waveforms=excerpts),
            independent=dict(result=independent,representative_transaction=test_excerpt,
                acceptance='整批未通过；4/16无曝光不能计通过。' if arm=='A3' else '整批未通过；12个曝光目标中6漏报，另4/16无曝光。',
                result_path=s.rel(TEST/'results.json'),grades_path=s.rel(TEST/'grades.json'),measurements_path=s.rel(TEST/'measurements.json')),
            links=dict(original=s.rel(folder/'initial.json'),proposal=s.rel(folder/'model_call/candidate.sva'),
                model_edit=s.rel(folder/'model_call/model_edit.json'),decision=s.rel(folder/'decision.json'),
                measurement=s.rel(folder/'measurement.json'),baseline=s.rel(folder/'baseline_measurement.json'),
                independent=s.rel(TEST/'results.json')),
            limitations=['单个原始FIFO父Bug、初始化复位、唯一TID、同拍首呈现义务。','这是新输入验收，不是新故障泛化。',
                '不能由两个代表案例推出总体优势；A0同seed也可能成功，另一seed的A3存在局部接口失败。',
                'effective_rounds=1仅表示新增检出对象；负例同时丢失旧对象，不能解释为净收益。']))
    for name,digest in bindings.items():ck('unchanged '+name,s.sha(ROOT/name)==digest)
    for name,value in [('case_cards.json',cards),('checks.json',checks),('source_bindings.json',bindings)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def anchor(path,label):return '<a href="../../'+html.escape(path)+'">'+html.escape(label)+'</a>'
    body='<!doctype html><meta charset="utf-8"><title>真实A消融正负案例</title><style>body{font:16px/1.6 system-ui;margin:32px;color:#1b293f;max-width:1200px}pre{white-space:pre-wrap;background:#eef2f8;padding:16px}table{border-collapse:collapse}td,th{border:1px solid #bac7d8;padding:7px;text-align:left}article{margin-bottom:48px}a{overflow-wrap:anywhere}</style><h1>真实A消融：局部修复与历史退化</h1><p>只读复核模型原始输出、实际testbench、执行日志、原生标记与独立事务参考；没有新模型或仿真调用。两个冻结版本的独立整批验收均未通过。</p>'
    for c in cards:
        ir=c['independent']['result'];body+='<article><h2>'+str(c['seed'])+' / '+c['arm']+'</h2><p>'+html.escape(c['causal_explanation'])+'</p>'
        body+='<h3>原始SVA</h3><pre>'+html.escape('\n'.join(c['original_sva']))+'</pre><h3>真实模型修改</h3><pre>'+html.escape(c['modified_sva'])+'</pre>'
        body+='<p>开发：旧检出 '+html.escape(str(c['old_detected']))+'；新检出 '+html.escape(str(c['new_detected']))+'。接受='+str(c['native_gate']['actual']['accepted'])+'；退化='+str(c['native_gate']['actual']['regression'])+'。</p>'
        body+='<p>独立新输入：'+str(ir['exposed']-ir['misses'])+'/'+str(ir['exposed'])+'曝光目标检出；FP='+str(ir['false_positives'])+'；FN='+str(ir['misses'])+'；无曝光='+str(ir['missing_exposure'])+'/'+str(ir['scenarios'])+'；whole_scope_pass='+str(ir['whole_scope_pass'])+'。</p>'
        body+='<h3>关键开发事务</h3>'
        for ex in c['development']['waveforms']:
            body+='<p>'+html.escape(ex.get('stage','modified')+' '+ex['scene'])+' · '+anchor(ex['raw_log'],'原始日志')+' · '+anchor(ex['waveform'],'VCD')+'</p><pre>'+html.escape(json.dumps(ex,ensure_ascii=False,indent=2))+'</pre>'
        body+='<h3>独立验收事务</h3><pre>'+html.escape(json.dumps(c['independent']['representative_transaction'],ensure_ascii=False,indent=2))+'</pre>'
        for label,path in c['links'].items():body+='<p>'+anchor(path,label)+'</p>'
        body+='<p>'+html.escape(' '.join(c['limitations']))+'</p></article>'
    body+='<p>审计检查 '+str(len(checks))+' 项通过；详见checks.json和source_bindings.json。</p>'
    (out/'case_cards.html').write_text(body,encoding='utf-8')
    (out/'summary.json').write_text(json.dumps(dict(cards=2,checks=len(checks),all_checks_passed=True,
        new_model_calls=0,new_simulation_calls=0,new_fault_generalization=False),indent=2)+'\n')
    print(json.dumps(dict(output=s.rel(out),cards=2,checks=len(checks))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();out=args.out.resolve()
    if not out.is_relative_to(ROOT/'deliverables'):raise ValueError('workspace deliverables only')
    main(out)
