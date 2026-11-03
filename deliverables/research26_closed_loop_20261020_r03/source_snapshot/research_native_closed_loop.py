"""Real Ollama -> native Verilator SVA -> independent FIFO evidence -> revision.

This is a single finite-budget development trajectory on artificial boundary
faults of real axis_fifo RTL. It is not the four-arm mechanism comparison.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.request

import research_native_runner as native
import research_fifo_experiment as fifo
from research_native_model import invoke
from research_acceptance_gate import decide

ROOT, OUT, dump = native.ROOT, native.OUT, native.dump
MODEL = 'qwen2.5-coder:7b-instruct'
ENDPOINT, PROVIDER, KEY_ENV = 'http://127.0.0.1:11434', 'ollama', 'OPENAI_API_KEY'
OPTIONS = dict(seed=2026101431, temperature=0, num_predict=640, num_ctx=16384,
               num_gpu=0, num_thread=8)
RTL = ROOT / 'external/verilog-axis/rtl/axis_fifo.v'
MUTANTS = ('correct', 'corrupt', 'duplicate_payload', 'drop')

REFERENCE = '''
  integer native_cycle=-1;
  always @(negedge clk) native_cycle <= native_cycle+1;
  reg [31:0] ref_mem[0:255];
  integer ref_head=0, ref_tail=0, ref_count=0;
  wire [31:0] ref_expected = ref_mem[ref_head];
  always @(posedge clk) begin
    if (rst) begin ref_head<=0; ref_tail<=0; ref_count<=0; end
    else begin
      if (svalid && sready) begin ref_mem[ref_tail]<=sdata; ref_tail<=(ref_tail+1)%256; end
      if (mvalid && mready && ref_count>0) ref_head<=(ref_head+1)%256;
      ref_count<=ref_count + ((svalid && sready)?1:0) - ((mvalid && mready && ref_count>0)?1:0);
    end
  end
'''


def parse_candidate(content):
    value = json.loads(content)
    assert isinstance(value.get('assertions'), list) and 1 <= len(value['assertions']) <= 4
    for i, item in enumerate(value['assertions']):
        item['id'] = 'a' + str(i)
        assert isinstance(item['property'], str) and isinstance(item['trigger'], str)
        assert not re.search(r'[;`]|\b(?:initial|always|endmodule|assert|assume|cover)\b', item['property'] + item['trigger']), 'unsafe_non_expression'
        expression=item['property']+' '+item['trigger']
        scrubbed=re.sub(r"\b\d*'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]+",'0',expression)
        identifiers=set(re.findall(r'\$?[A-Za-z_][A-Za-z_0-9]*',scrubbed))
        allowed=set('clk rst svalid sready sdata mvalid mready mdata ref_count ref_expected not and or iff throughout intersect within first_match strong weak until until_with s_until s_until_with'.split())
        allowed.update(('$past','$stable','$rose','$fell','$changed','$isunknown','$unsigned','$signed'))
        assert not identifiers-allowed, 'candidate_interface_error:'+','.join(sorted(identifiers-allowed))
        assert isinstance(item.get('obligations'), list)
        assert all(x in fifo.OBLIGATIONS for x in item['obligations'])
    return value


def candidate_sva(candidate):
    lines=[]
    for item in candidate['assertions']:
        i=item['id']
        lines += [f'{i}: assert property (@(posedge clk) disable iff (rst) ({item["property"]}))',
            f'  else $display("ASSERT_FAIL {i} cycle=%0d", $sampled(native_cycle));',
            f'always @(posedge clk) if (!rst && ({item["trigger"]})) $display("TRIGGER {i} cycle=%0d", native_cycle);']
    return '\n'.join(lines)+'\n'


def make_tb(rows, depth, pipeline, candidate):
    source=fifo.testbench(rows,depth,pipeline,'correct')
    dynamic='''integer fault_mode=0;
  initial if ($value$plusargs("fault=%d",fault_mode)) begin end
  assign mdata = fault_mode==1 ? (raw_data ^ 32'h1) :
    (fault_mode==2 && raw_count%4==3) ? last_data : raw_data;
  assign mvalid = raw_valid && !(fault_mode==3 && raw_count%4==3);'''
    source=source.replace('assign mdata = raw_data; assign mvalid = raw_valid;',dynamic)
    source=source.replace('  task drive', REFERENCE+'\n'+candidate_sva(candidate)+'\n  task drive')
    return source.replace('#1; $finish;', '#1; $display("NATIVE_RUN_COMPLETE"); $finish;')


def evaluate(candidate, folder, seed, depth, pipeline):
    folder.mkdir(parents=True,exist_ok=False)
    rows=fifo.stimulus(seed)
    dump(folder/'stimulus.json',rows)
    results={}
    results['correct']=native.run_native(make_tb(rows,depth,pipeline,candidate),folder/'correct',extra_sources=[RTL])
    if results['correct']['compile_status']=='passed':
        for i,mode in enumerate(MUTANTS[1:],1):
            results[mode]=native.replay_native(folder/'correct',folder/mode,[f'+fault={i}'])
    evaluation=dict(status='ok',false_positives=[],detections=[],effective_triggers=[],misses=[],resolved_keys=[],attribution_unknown=[],native_results=results,oracles={})
    fixed_trace=None
    for mode, result in results.items():
        path=folder/mode
        if result['execution_status']!='completed':
            evaluation['status']='unknown';continue
        trace=fifo.parse_trace(path/'execute.log')
        oracle=fifo.oracle(trace)
        dump(path/'trace.json',trace);dump(path/'oracle.json',oracle)
        evaluation['oracles'][mode]=oracle
        if mode=='correct':fixed_trace=trace
        if oracle['legality']!='legal' or oracle['unknown']: evaluation['status']='unknown'
        failures=set()
        for hit in result.get('failures',[]):
            match=re.search(r'cycle=(\d+)',hit['detail'])
            if not match: evaluation['status']='unknown';continue
            assertion=next(a for a in candidate['assertions'] if a['id']==hit['id'])
            for obligation in assertion['obligations']: failures.add((int(match[1]),obligation))
        violations={(v['cycle'],v['obligation']) for v in oracle['violations']}
        prefix=f'd{depth}_p{pipeline}_s{seed}/{mode}'
        fixed_oracle=evaluation['oracles'].get('correct',{})
        input_names=('rst','svalid','sready','sdata','mready')
        paired_inputs=bool(fixed_trace) and len(trace)==len(fixed_trace) and all(
            all(a[n]==b[n] for n in input_names) for a,b in zip(trace,fixed_trace))
        clean_counterfactual=(fixed_oracle.get('legality')=='legal' and not fixed_oracle.get('violations')
            and not fixed_oracle.get('unknown') and not results['correct'].get('failures') and paired_inputs)
        first_violation=min((c for c,o in violations),default=None)
        failure_cycles=[int(re.search(r'cycle=(\d+)',h['detail'])[1]) for h in result.get('failures',[])]
        for cycle,obligation in violations:
            key=f'{prefix}/cycle{cycle}/{obligation}'
            if (cycle,obligation) not in failures:evaluation['misses'].append(key)
            elif clean_counterfactual and cycle==first_violation and not any(c<cycle for c in failure_cycles):
                evaluation['detections'].append(key);evaluation['resolved_keys'].append(key)
            else:evaluation['attribution_unknown'].append(dict(key=key,reason='native symptom hit without clean first-divergence causal attribution'))
        # A failure without independently matching violation is a false positive.
        # Multi-obligation claims are assessed per native failure and its oracle
        # matches, not counted once for each unfailed claimed obligation.
        for hit in result.get('failures',[]):
            cycle=int(re.search(r'cycle=(\d+)',hit['detail'])[1])
            assertion=next(a for a in candidate['assertions'] if a['id']==hit['id'])
            if not any((cycle,o) in violations for o in assertion['obligations']):
                evaluation['false_positives'].append(f'{prefix}/cycle{cycle}/native_failure_without_oracle_violation')
        for sample in trace:
            cycle=sample['cycle']
            if cycle not in failure_cycles and not any(c==cycle for c,o in violations):
                evaluation['resolved_keys'].append(f'{prefix}/cycle{cycle}/native_failure_without_oracle_violation')
        # Trigger instrumentation is explicitly diagnostic; retain obligation
        # presence on this replay but do not claim native SVA cover counts.
        for hit in result.get('triggers',[]):
            a=next(a for a in candidate['assertions'] if a['id']==hit['id'])
            cycle=int(re.search(r'cycle=(\d+)',hit['detail'])[1])
            for o in a['obligations']:
                if any(c['obligation']==o and c['cycle']==cycle for c in oracle['checks']):
                    evaluation['effective_triggers'].append(f'{prefix}/cycle{cycle}/{o}/diagnostic_trigger')
    for key in ('false_positives','detections','effective_triggers','misses','resolved_keys'):
        evaluation[key]=sorted(set(evaluation[key]))
    dump(folder/'evaluation.json',evaluation)
    return evaluation


def context():
    # Both RTL versions are actual source text: a stable real FIFO plus an
    # explicitly artificial output-corruption boundary. No historical claim.
    rtl=RTL.read_text()
    before='assign mdata = raw_data ^ 32\'h1; assign mvalid = raw_valid;'
    after='assign mdata = raw_data; assign mvalid = raw_valid;'
    return dict(bug_description='Artificial output boundary fault of real axis_fifo RTL: bit 0 is flipped on every output. Related development faults may drop or duplicate payloads. This is not a historical upstream bug.',
        shared_unchanged_fifo_rtl=rtl,
        rtl_before=dict(shared_source='shared_unchanged_fifo_rtl',boundary_rtl=before),
        rtl_after=dict(shared_source='shared_unchanged_fifo_rtl',boundary_rtl=after),specification=fifo.OBLIGATIONS,
        confirmed_repair_obligations=list(fifo.OBLIGATIONS),
        semantics='posedge pre-NBA sampling; active-high reset cancels pending transactions; input acceptance svalid&&sready; output acceptance mvalid&&mready; output order oldest accepted input; buffered no same-edge bypass; arbitrary backpressure; no unconditional fixed latency guarantee.',
        allowed_signals='clk rst svalid sready sdata[31:0] mvalid mready mdata[31:0] ref_count ref_expected[31:0]',
        auxiliary_reference_state=REFERENCE,
        tool='Verilator5.020 native assert property with |->, |=>, $past, $stable. Sequence ##2 is unsupported. Do not add procedural failure checks.',
        output_schema={'reason':'explain changes','assertions':[{'property':'SVA property expression only, without clock/reset or assert wrapper','trigger':'ordinary SV boolean diagnostic expression, no temporal operators','obligations':['order_payload'],'reason':'explain exact protection and limitation'}]},
        instructions='Return JSON only. All assertions use @(posedge clk) disable iff(rst). Auxiliary ref_expected and ref_count update on the edge after sampled property evaluation; reference is reset-safe. Accepted-output obligations are evaluated on mvalid && mready, never mere presented requests. Use only allowed signal identifiers. Do not use raw_data, raw_valid, fault_mode, test seeds or DUT internals. Trigger is diagnostic and must match the property antecedent. No constant false antecedents. Prefer complementary assertions for different obligations. No liveness proof is possible in finite simulation.')


def ask(folder, ctx, digest):
    request=dict(model=MODEL,stream=True,format='json',options=OPTIONS,
        messages=[dict(role='system',content='You generate native SystemVerilog assertion sets. Return exactly the requested JSON.'),
                  dict(role='user',content=json.dumps(ctx))])
    result,content=invoke(request,folder,dump,digest,endpoint=ENDPOINT,provider=PROVIDER,key_env=KEY_ENV,timeout=900)
    candidate=None
    if result['status']=='response_received':
        try: candidate=parse_candidate(content)
        except Exception as exc: result.update(candidate_status='parse_rejected',parse_error=repr(exc))
    if candidate:
        dump(folder/'candidate.json',candidate)
        (folder/'candidate.sva').write_text(candidate_sva(candidate))
        result['candidate_status']='parsed'
    dump(folder/'result.json',result)
    return result,candidate


def main(out):
    out.mkdir(parents=True,exist_ok=False)
    tags=json.load(urllib.request.urlopen(ENDPOINT.rstrip('/')+'/api/tags',timeout=10)) if PROVIDER=='ollama' else {'models':[{'name':MODEL,'digest':None}]}
    model=next(m for m in tags['models'] if m['name']==MODEL)
    dump(out/'model_tags.json',tags)
    (out/'shared_axis_fifo.v').write_text(RTL.read_text())
    dump(out/'source_manifest.json',dict(rtl_path=str(RTL),rtl_sha256=hashlib.sha256(RTL.read_bytes()).hexdigest(),
        scripts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(native.__file__),ROOT/'scripts/research_native_model.py',ROOT/'scripts/research_fifo_experiment.py']},
        git_head=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()))
    dump(out/'protocol.json',dict(model=MODEL,model_digest=model['digest'],options=OPTIONS,
        max_calls=2,development_seed=2026101431,independent_seed=2026101497,
        development_parameters=dict(depth=2,pipeline=0),independent_parameters=dict(depth=4,pipeline=2),
        provenance='actual axis_fifo RTL with explicit artificial boundary faults; not parent FIFO presented defect reproduction',
        holdout_policy='Independent schedule is instantiated only after frozen accepted candidate hash; never sent to model. No modifications after independent results.',
        evidence_keys='scenario + cycle + independent violated obligation; duplicate native failures deduplicated',
        limitations=['finite execution not formal proof','trigger counts are procedural diagnostics, not native cover','four-arm mechanism comparison is separate','initial one-property synthesis budget, revision up to four properties']))
    ctx=context();ctx['task']='Generate ONE initial native assertion protecting the highest-priority repair obligation. State the protection limits.'
    calls=[];history=[]
    call,initial=ask(out/'model_calls/initial',ctx,model['digest']);calls.append(call)
    if not initial:
        dump(out/'summary.json',dict(status='initial_generation_failed',calls=calls));return
    before=evaluate(initial,out/'v0_development',2026101431,2,0)
    accepted=initial;accepted_eval=before
    baseline_accepted=before['status']=='ok' and not before['false_positives']
    history.append(dict(version='v0',accepted=baseline_accepted,reason='initial candidate baseline, may retain evidence gaps; unknown or false positives imply no accepted version'))
    feedback=dict(misses=before['misses'],false_positives=before['false_positives'],
        native_execution={k:{x:r.get(x) for x in ('compile_status','tool_support_status','execution_status','property_status','failures')} for k,r in before['native_results'].items()},
        independent_violations={k:v['violations'][:5] for k,v in before['oracles'].items()},
        current_assertions=initial,
        compile_diagnostics=(out/'v0_development/correct/compile.log').read_text()[-10000:])
    ctx=context();ctx.update(task='Revise or add complementary native assertions to repair the actual feedback gaps while preserving prior protection. Maximum four assertions. Preserve sound protection; do not hide triggers or demand fixed latency.',feedback=feedback)
    call,revised=ask(out/'model_calls/revision',ctx,model['digest']);calls.append(call)
    if revised:
        after=evaluate(revised,out/'v1_development',2026101431,2,0)
        # One independently labelled gap is the current repair target. Remaining
        # misses are explicitly retained; acceptance is never whole-case success.
        target_pool=before['false_positives'] or before['misses']
        targets=sorted(target_pool,key=lambda k:int(re.search(r'/cycle(\d+)/',k)[1]))[:1]
        decision=decide(before,after,targets)
        # An unchanged pre-existing false positive cannot be accepted merely
        # because it is not new; no legal execution failures are permitted.
        if after['false_positives']:
            decision['accepted']=False
            decision['reasons'].append(dict(kind='remaining_legal_false_positive',keys=after['false_positives']))
        dump(out/'v1_decision.json',decision)
        history.append(dict(version='v1',**decision))
        if decision['accepted']: accepted,accepted_eval=revised,after
    else:
        history.append(dict(version='v1',accepted=False,reason='model transport or parse failure'))
    dump(out/'history.json',history)
    dump(out/'frozen_candidate.json',accepted)
    (out/'frozen_candidate.sva').write_text(candidate_sva(accepted))
    frozen_hash=hashlib.sha256((out/'frozen_candidate.sva').read_bytes()).hexdigest()
    dump(out/'freeze.json',dict(sha256=frozen_hash,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),status='frozen_before_independent_schedule_generation',candidate_acceptance=('baseline_retained' if baseline_accepted else 'no_accepted_version_diagnostic_baseline_only') if accepted is initial else 'revision_accepted'))
    independent=evaluate(accepted,out/'independent_test',2026101497,4,2)
    def compact(e):return {k:len(e[k]) for k in ('false_positives','detections','misses','effective_triggers')}
    native_runs=[json.loads(p.read_text()) for p in out.rglob('result.json') if p.parent.name in MUTANTS]
    summary=dict(status='completed_finite_native_trajectory',formal_proof=False,calls=calls,history=history,
        initial=compact(before),final_development=compact(accepted_eval),independent_test=compact(independent),
        frozen_sva_sha256=frozen_hash,unprotected_obligations=sorted({k.split('/')[-1] for k in independent['misses']}),
        model_cost=dict(calls=len(calls),retries=0,prompt_tokens=sum(c['prompt_tokens'] for c in calls) if all(c.get('prompt_tokens') is not None for c in calls) else None,completion_tokens=sum(c['completion_tokens'] for c in calls) if all(c.get('completion_tokens') is not None for c in calls) else None,wall_seconds=sum(c['wall_seconds'] for c in calls),monetary_cost='unavailable_local_inference'),
        native_cost=dict(compile_calls=sum('compile' in r for r in native_runs),compile_wall_seconds=sum(r.get('compile',{}).get('wall_seconds',0) for r in native_runs),simulation_calls=sum(r.get('native_simulation_calls',0) for r in native_runs),simulation_wall_seconds=sum(r.get('execute',{}).get('wall_seconds',0) for r in native_runs)),
        attribution_unknown=dict(development=len(accepted_eval['attribution_unknown']),independent=len(independent['attribution_unknown'])),
        formal_cost=dict(calls=0,wall_seconds=0),scope='History replay only; artificial faults on real FIFO. No global non-regression, no historical repair validation, no formal proof.')
    dump(out/'summary.json',summary)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',default=str(OUT/'closed_loop'))
    parser.add_argument('--model',default=MODEL);parser.add_argument('--endpoint',default=ENDPOINT)
    parser.add_argument('--provider',choices=['ollama','openai_compatible'],default=PROVIDER)
    parser.add_argument('--key-env',default=KEY_ENV);parser.add_argument('--seed',type=int,default=OPTIONS['seed'])
    parser.add_argument('--temperature',type=float,default=OPTIONS['temperature']);parser.add_argument('--max-tokens',type=int,default=OPTIONS['num_predict'])
    args=parser.parse_args()
    MODEL,ENDPOINT,PROVIDER,KEY_ENV=args.model,args.endpoint,args.provider,args.key_env
    OPTIONS.update(seed=args.seed,temperature=args.temperature,num_predict=args.max_tokens)
    main(Path(args.out))
