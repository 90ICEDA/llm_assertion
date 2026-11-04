"""Real common_cells PR242 qualification; no historical RTL rewriting or model calls.

The 194 evaluator is loaded into an isolated module instance and supplied this
case's harness/reference callbacks. Its sealed source and artifacts stay intact.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'deliverables/research195_history_sources_20261103_r01'
BEFORE='94d285b4b6f7b96649f9d3175e5a6500ec12de00'
AFTER='554ebbcdd3d4d55f9d94dbee47f957af93a835a8'
CASE='historical_delta_counter'
PARENT='pulp-platform/common_cells#242'
INPUTS={'rst_n':1,'clear':1,'en':1,'load':1,'down':1,'delta':4,'data':4}
OUTPUTS={'q':4,'overflow':1}
OBS=['overflow_capture','sticky_hold','clear_load_reset','count_update']

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')

def prop(label,ant,cons,ob,timing='next_sample'):
    return dict(label=label,antecedent=ant,consequent=cons,obligations=[ob],timing=timing)

EVENT='en && !clear && !load && ((!down && ({1\'b0,q}+{1\'b0,delta}>5\'d15)) || (down && delta>q))'

def controls():
    return dict(
      initial=[prop('capture',EVENT,'overflow','overflow_capture','same_sample')],
      improved=[prop('capture',EVENT,'overflow','overflow_capture')],
      exception_initial=[prop('hold','overflow','overflow','sticky_hold')],
      exception_improved=[prop('hold','overflow && !clear && !load','overflow','sticky_hold')],
      complete=[prop('capture',EVENT,'overflow','overflow_capture'),
        prop('hold','overflow && !clear && !load','overflow','sticky_hold'),
        prop('clear_load','clear || load','!overflow','clear_load_reset')])

def get_case(case_id=CASE):
    if case_id!=CASE:raise ValueError(case_id)
    return dict(id=CASE,parent_bug=PARENT,historical_fix_confirmed=True,
      initial=controls()['initial'],candidate_pool=[controls()['initial'],controls()['improved']],
      obligations=OBS,signals=list(INPUTS)+list(OUTPUTS)+['cycle'],input_signals=INPUTS,output_signals=OUTPUTS,
      specification='Width=4, STICKY_OVERFLOW=1. The counter adds/subtracts delta on enabled edges, modulo 16. clear takes precedence over load, load over enable. On enabled unsigned overflow/underflow, overflow must be 1 at the next sampled edge, then remains sticky until synchronous clear/load or asynchronous active-low reset. Reset also clears q. Inputs may change at negative edges; observations are pre-update positive-edge samples.',
      provenance=dict(kind='confirmed_upstream_historical_repair',repository='https://github.com/pulp-platform/common_cells',
        pull_request='https://github.com/pulp-platform/common_cells/pull/242',before=BEFORE,after=AFTER,
        source_scope='Original standalone delta_counter, WIDTH4 STICKY_OVERFLOW1; no artificial mutants and no full-system claim.',
        candidates='handwritten specification controls, qualification only; no LLM or learned improvement claim'),
      rtl=[str(SRC/AFTER/'delta_counter.sv')])

def row(**kwargs):return dict(rst_n=1,clear=0,en=0,load=0,down=0,delta=1,data=0,**kwargs) if not kwargs else {**dict(rst_n=1,clear=0,en=0,load=0,down=0,delta=1,data=0),**kwargs}

def query_pool(case_id=CASE,split='development',seed=19507):
    if case_id!=CASE or split not in ('development','independent'):raise ValueError('case/split')
    # Chosen from arithmetic boundaries, not by candidate outcomes. Independent
    # values/order remain reserved until an explicitly requested independent run.
    values=[(14,3),(1,3)] if split=='development' else [(12,7),(2,5)]
    queries=[]
    for index,(value,delta) in enumerate(values):
        down=index==1
        rows=[row(rst_n=0),row(rst_n=0),row(load=1,data=value),row(en=1,down=int(down),delta=delta),
          row(),row(en=1,down=int(not down),delta=1),row(clear=1),row(),
          row(load=1,data=value),row(en=1,down=int(down),delta=delta),row(),row(load=1,data=7),row(),
          row(load=1,data=value),row(en=1,down=int(down),delta=delta),row(),row(rst_n=0),row(),row()]
        queries.append(dict(id=f'{CASE}_{split}_{index}',split=split,rows=rows,semantic_key=digest(rows),
          family='underflow_clear_load_reset' if down else 'overflow_clear_load_reset',constraints='Legal unsigned 4-bit inputs; asynchronous reset and synchronous clear/load; no DUT internal state forced.'))
    return queries

def bench(case_id,candidate,rows,fault='correct'):
    properties=[]
    for a in candidate:
        implication='|=>' if a['timing']=='next_sample' else '|->'
        properties.append(f'''{a['label']}: assert property (@(posedge clk) disable iff (!rst_n) ({a['antecedent']}) {implication} ({a['consequent']}))
          else $display("ASSERT_FAIL {a['label']} cycle=%0d",$sampled(cycle));
        trigger_{a['label']}: assert property (@(posedge clk) disable iff (!rst_n) !({a['antecedent']}))
          else $display("TRIGGER {a['label']} cycle=%0d",$sampled(cycle));''')
    stimulus=[]
    for cycle,inputs in enumerate(rows):
        stimulus.append('@(negedge clk); cycle='+str(cycle)+'; '+' '.join(f'{k}={v};' for k,v in inputs.items())+' @(posedge clk); #1;')
    return '''module tb;
bit clk=0; always #5 clk=~clk;
logic rst_n=0,clear=0,en=0,load=0,down=0;
logic [3:0] delta=0,data=0,q; logic overflow; integer cycle=-1;
delta_counter #(.WIDTH(4),.STICKY_OVERFLOW(1)) dut(.clk_i(clk),.rst_ni(rst_n),.clear_i(clear),.en_i(en),.load_i(load),.down_i(down),.delta_i(delta),.d_i(data),.q_o(q),.overflow_o(overflow));
'''+'\n'.join(properties)+'''
always @(posedge clk) if(cycle>=0) $display("TRACE cycle=%0d rst_n=%0d clear=%0d en=%0d load=%0d down=%0d delta=%0d data=%0d q=%0d overflow=%0d",cycle,rst_n,clear,en,load,down,delta,data,q,overflow);
initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);
'''+ '\n'.join(stimulus)+ '\n$display("NATIVE_RUN_COMPLETE");$finish;end\nendmodule\n'

def reference(case_id,traces):
    checks=[];unknown=[];expected_q=0;expected_overflow=0;tx=0
    for i,t in enumerate(traces):
        if t['cycle']!=i:unknown.append('cycle_alignment')
        if not t['rst_n']:
            expected_q=0;expected_overflow=0;ob='clear_load_reset';tx+=1
        elif i:
            p=traces[i-1]
            if not p['rst_n']:expected_q=0;expected_overflow=0;ob='clear_load_reset'
            elif p['clear']:expected_q=0;expected_overflow=0;ob='clear_load_reset';tx+=1
            elif p['load']:expected_q=p['data'];expected_overflow=0;ob='clear_load_reset';tx+=1
            else:
                event=p['en'] and (p['delta']>expected_q if p['down'] else expected_q+p['delta']>15)
                ob='overflow_capture' if event else 'sticky_hold'
                expected_overflow=int(bool(expected_overflow or event))
                if p['en']:expected_q=(expected_q+(-p['delta'] if p['down'] else p['delta']))%16
        else:ob='clear_load_reset'
        checks.extend([dict(cycle=i,transaction=tx,obligation='count_update',passed=t['q']==expected_q,expected=expected_q,observed=t['q']),
          dict(cycle=i,transaction=tx,obligation=ob,passed=t['overflow']==expected_overflow,expected=expected_overflow,observed=t['overflow'])])
    return dict(checks=checks,unknown=unknown)

def sources(case_id,folder,fault):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    src=SRC/(AFTER if fault=='correct' else BEFORE)/'delta_counter.sv'
    dest=folder/'delta_counter.sv';dest.write_bytes(src.read_bytes())
    return [dest]

def runtime():
    spec=importlib.util.spec_from_file_location('_research195_history_isolated',ROOT/'scripts/research194_cases.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.CONFIG[CASE]=dict(inputs=INPUTS,outputs=OUTPUTS,parent_bug=PARENT,historical_fix_confirmed=True,
      sources=[str(Path(__file__).relative_to(ROOT)),str((SRC/BEFORE/'delta_counter.sv').relative_to(ROOT)),str((SRC/AFTER/'delta_counter.sv').relative_to(ROOT))])
    module.FAULTS[CASE]=[]
    module.get_case=get_case;module.query_pool=query_pool;module._bench=bench;module._sources=sources;module.reference=reference
    return module

def validate(case_id,candidate):return runtime().validate(case_id,candidate)
def render(candidate):return runtime().render(candidate)
def evaluate(case_id,candidate,out,queries=None,split='development',fault='primary',cleanup=True):
    return runtime().evaluate(case_id,candidate,out,queries=queries,split=split,fault=fault,cleanup=cleanup)

class CaseAdapter:
    def __init__(self):self.case_id=CASE;self.case=get_case()
    def validate(self,candidate):return validate(CASE,candidate)
    def evaluate(self,candidate,out,queries):return evaluate(CASE,candidate,out,queries)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--run',action='store_true');args=ap.parse_args()
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=False)
    commit=json.loads((SRC/'commit.json').read_text(encoding='utf-8-sig'));pr=json.loads((SRC/'pull_request.json').read_text(encoding='utf-8-sig'))
    assert commit['sha']==AFTER and commit['parents'][0]['sha']==BEFORE and pr['merged_at'] and pr['merge_commit_sha']==AFTER
    paths=[Path(__file__),ROOT/'scripts/research194_cases.py',ROOT/'scripts/research_native_runner.py',SRC/'commit.json',SRC/'pull_request.json',SRC/BEFORE/'delta_counter.sv',SRC/AFTER/'delta_counter.sv']
    frozen=dict(case=get_case(),controls=controls(),development=query_pool(),independent_reservation=dict(rule='2 heldout boundary values and reversed direction; separate later input generalization only, same parent bug; not new-fault generalization',values=[[12,7],[2,5]]),source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},model_calls=0)
    dump(out/'frozen_protocol.json',frozen)
    if not args.run:return
    # A single actual candidate bundle shares physical jobs; label projection
    # preserves each control's native verdict. These are qualification controls.
    bundle=[]
    for name in ['initial','improved','exception_initial','exception_improved','complete']:
        for a in controls()[name]:bundle.append({**a,'label':name+'_'+a['label']})
    result=evaluate(CASE,bundle,out/'native',queries=query_pool())
    from research194_metrics import temporal_detection
    report=dict(native_complete=result['native_complete'],reference_complete=result['reference_complete'],parent_bug=PARENT,historical_fix_confirmed=True,
      original_targets=len(result['targets']),original_transactions=len(result['target_transaction_ids']),cost=result['cost'],critical_unknown=result['critical_unknown'],
      any_cycle=temporal_detection(result),by_control={})
    for name in ['initial','improved','exception_initial','exception_improved','complete']:
        labels={name+'_'+a['label'] for a in controls()[name]};ev=copy.deepcopy(result['evidence'])
        for e in ev:e['assertions']=[a for a in e['assertions'] if a['assertion'] in labels]
        detected={e['id'] for e in ev if e['status']=='confirmed' and e['label']=='violation' and e['counted_target'] and any(a['failure'] for a in e['assertions'])}
        fps={(e['query_id'],e['cycle'],e['obligation']) for e in ev if e['status']=='confirmed' and e['label']=='legal' and any(a['failure'] for a in e['assertions'])}
        trig=sum(m['id'] in labels for j in result['executions'] for m in j['result'].get('triggers',[]))
        report['by_control'][name]=dict(timely_detected=len(detected),false_positive_samples=len(fps),native_trigger_markers=trig,
          temporal=temporal_detection({**result,'evidence':ev,'detected_ids':sorted(detected)}))
    report['source_unchanged']=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in frozen['source_hashes'].items())
    dump(out/'qualification.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('any_cycle','by_control')},indent=2))

if __name__=='__main__':main()
