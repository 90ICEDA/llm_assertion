"""Real RTL temporal adapters. Reuse the R194 executor; immutable old studies.

PR190/PR242 are original historical revisions. ID queue is real upstream RTL
with explicitly artificial faults. All reference state is independent Python;
no DUT internals or reference verdicts are supplied as assertion inputs.
"""
import copy
from pathlib import Path
import random
import re
from research195_refinement_adapter import clone
from research194_refinement_runner import ROOT,read,dump,bind_measurement
from research194_refinement import digest
import research195_history_case as delta

IDS=('historical_stream_delay','id_queue_matching','historical_delta_counter')
SRC=ROOT/'deliverables/research197_history_sources_20261104_r01'
BEFORE='534340f6166ce0370222e40741ec5729dc34770e';AFTER='66b3934d6478f255a668a8d6de026730c25f52c5'
CC=ROOT/'external/common_cells'

def prop(label,ant,cons,ob,timing='same_sample'):
    return dict(label=label,antecedent=ant,consequent=cons,obligations=[ob],timing=timing)

def past(e,n):return '('+e+')' if n==0 else f'$past(({e}),{n})'

def response_window(response,lo,hi,anchor):
    if not 1<=lo<=hi<=anchor<=32:raise ValueError('response_window_bounds')
    late=' || '.join(past(response,anchor-n) for n in range(lo,hi+1))
    early=' && '.join('!'+past(response,anchor-n) for n in range(1,lo)) or "1'b1"
    return f'({early}) && ({late})'

def match_window(lo=1,hi=8):
    return ' || '.join(f'({past("inp_req && inp_gnt",n)} && (out_id == {past("inp_id",n)}) && (out_data == {past("inp_data",n)}))' for n in range(lo,hi+1))

def get_case(cid):
    if cid==IDS[0]:
        inputs=dict(rst_n=1,valid=1,ready=1,payload=8)
        outputs=dict(out_valid=1,in_ready=1,out_payload=8,launch=1)
        ob=['response_window','exact_latency','handshake_payload']
        initial=[prop('window',past('launch',21),response_window('out_valid',1,21,21),'response_window')]
        alternative=[prop('window',past('launch',21),response_window('out_valid',18,21,21),'response_window')]
        sources=[str((SRC/r/name).relative_to(ROOT)).replace('\\','/') for r in (BEFORE,AFTER) for name in ('stream_delay.sv','counter.sv','delta_counter.sv')]
        parent='pulp-platform/common_cells#190';historical=True
        spec=('Original stream_delay FixedDelay=16, StallRandom=0. A valid rising edge launches a held request. '
              'The FSM consumes one launch edge, 16 decrement edges and one zero-detection edge: output valid first appears at age 18. '
              'The environment holds valid/payload until accepted and releases ready at age 18..21. '
              'At age 21 require no output-valid at ages 1..17 and at least one output-valid at ages 18..21. '
              'Reset cancels outstanding work. launch is a passive valid rising-edge signal, not an oracle label. '
              'Deadline checking is sampled $past expansion, not arbitrary SVA sequence syntax.')
    elif cid==IDS[1]:
        inputs=dict(rst_n=1,clear=1,inp_req=1,inp_id=2,inp_data=8,out_req=1,out_id=2,pop=1)
        outputs=dict(inp_gnt=1,out_gnt=1,out_valid=1,out_data=8,full=1,empty=1)
        ob=['transaction_match','queue_state','reset_cancel']
        initial=[prop('matching','out_req && out_gnt && out_valid','out_data == $past(inp_data)','transaction_match')]
        alternative=[prop('matching','out_req && out_gnt && out_valid',match_window(),'transaction_match')]
        sources=[str((CC/'src'/n).relative_to(ROOT)).replace('\\','/') for n in ('cc_pkg.sv','cc_lzc.sv','cc_onehot_to_bin.sv','cc_id_queue.sv')]
        parent='pulp-platform/common_cells/cc_id_queue/artificial_data_fault';historical=False
        spec=('Original cc_id_queue, Capacity=4, IdWidth=2, FullBw=0. Accepted inputs are stored per ID; output can select IDs in any order. '
              'Reads return the oldest pending payload of the requested ID; pop removes it, non-pop is a legal peek. '
              'Input has priority over output. All traffic uses unique IDs while outstanding and response age 1..8; three requests may be pending. '
              'Clear/reset cancels queued requests. SVA sees only interface signals. New reserved faults must remain outside development.')
    elif cid==IDS[2]:
        c=delta.get_case();inputs=delta.INPUTS;outputs=delta.OUTPUTS;ob=delta.OBS
        initial=c['initial'];alternative=delta.controls()['improved'];sources=[str((delta.SRC/r/'delta_counter.sv').relative_to(ROOT)).replace('\\','/') for r in (delta.BEFORE,delta.AFTER)]
        parent=delta.PARENT;historical=True;spec=c['specification']
    else:raise ValueError(cid)
    return dict(id=cid,parent_bug=parent,historical_fix_confirmed=historical,inputs=inputs,outputs=outputs,
        input_signals=inputs,output_signals=outputs,signals=list(inputs)+list(outputs)+['cycle'],obligations=ob,
        initial=copy.deepcopy(initial),candidate_pool=[copy.deepcopy(initial),copy.deepcopy(alternative)],sources=sources,
        disable='!rst_n',reset='rst_n',specification=spec,
        provenance=dict(real_project_RTL=True,historical_fix_confirmed=historical,parent_bug=parent,
            scope='Standalone original RTL with external protocol monitor; handwritten initial candidates and qualification controls are not model results.'))

def query_pool(cid,split='development',seed=19707):
    if split not in ('development','independent'):raise ValueError(split)
    rng=random.Random(seed+(800000 if split=='independent' else 0));queries=[]
    for index in range(4):
        if cid==IDS[0]:
            rows=[dict(rst_n=0,valid=0,ready=0,payload=0) for _ in range(3+index)]
            rows.append(dict(rst_n=1,valid=0,ready=0,payload=0))
            for burst in range(1+index%2):
                value=rng.randrange(1,256);stall=(index+burst)%4
                for age in range(19+stall):rows.append(dict(rst_n=1,valid=1,ready=int(age>=18+stall),payload=value))
                rows.extend(dict(rst_n=1,valid=0,ready=1,payload=rng.randrange(256)) for _ in range(24))
            family=f'latency16_stall{index}'
        elif cid==IDS[1]:
            base=dict(rst_n=1,clear=0,inp_req=0,inp_id=0,inp_data=0,out_req=0,out_id=0,pop=0)
            rows=[dict(base,rst_n=0) for _ in range(3)]+[dict(base)]
            tags=rng.sample(range(4),3);payloads=rng.sample(range(1,256),3)
            for tag,value in zip(tags,payloads):rows.append(dict(base,inp_req=1,inp_id=tag,inp_data=value))
            order=list(reversed(tags)) if index%2==0 else tags[1:]+tags[:1]
            if index==1:rows.append(dict(base,out_req=1,out_id=order[0],pop=0))
            if index==2:
                rows.append(dict(base,clear=1));rows.append(dict(base))
                for tag,value in zip(tags,payloads):rows.append(dict(base,inp_req=1,inp_id=tag,inp_data=value))
            for tag in order:rows.append(dict(base,out_req=1,out_id=tag,pop=1))
            rows.extend(dict(base) for _ in range(3));family=f'tag_interleave_{index}'
        else:
            rows=copy.deepcopy(delta.query_pool(split='development')[index%2]['rows'])
            # Fresh arithmetic boundaries, same exact unsigned contract.
            value=rng.choice([12,13,14]) if index%2==0 else rng.choice([0,1,2])
            for r in rows:
                if r['load'] and r['data']!=7:r['data']=value
                if r['en'] and r['delta']==3:r['delta']=rng.choice([4,5,6])
            if index>=2:rows=[copy.deepcopy(rows[0]) for _ in range(index)]+rows
            family=f'arithmetic_boundary_{index}'
        queries.append(dict(id=f'{cid}/{split}/{digest(rows)[:16]}',family=family,rows=rows,semantic_key=digest(rows),
            split=split,obligations=get_case(cid)['obligations'],dimensions=['window','matching','reset','backpressure'],
            constraints=['External legal inputs only','No forced DUT internal state','Bounded finite history; independent monitor validates obligations'],estimated_cost=2))
    return queries

def _expanded(path,stack=()):
    path=Path(path)
    if path in stack:raise ValueError('include_cycle')
    return re.sub(r'`include\s+"([^"]+)"',lambda m:_expanded(CC/'include'/m[1],(*stack,path)),path.read_text())

def sources(cid,folder,fault):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    if cid==IDS[0]:
        rev=BEFORE if fault=='primary' else AFTER
        original=[SRC/rev/n for n in ('delta_counter.sv','counter.sv','stream_delay.sv')]
    elif cid==IDS[1]:original=[CC/'src'/n for n in ('cc_pkg.sv','cc_lzc.sv','cc_onehot_to_bin.sv','cc_id_queue.sv')]
    else:original=[delta.SRC/(delta.BEFORE if fault=='primary' else delta.AFTER)/'delta_counter.sv']
    text='`define COMMON_CELLS_ASSERTS_OFF\n'+'\n'.join(_expanded(p) for p in original)
    if cid==IDS[1] and fault=='primary':
        old="oup_data_o = data_t'(linked_data_q[head_tail_q[match_in_idx].head].data);"
        if text.count(old)!=1:raise ValueError('mutation_site')
        text=text.replace(old,"oup_data_o = data_t'(linked_data_q[head_tail_q[match_in_idx].head].data ^ 8'h01);")
    elif fault not in ('correct','primary'):raise ValueError('unregistered_fault')
    p=folder/'expanded_upstream.sv';p.write_text(text);return [p]

def bench(cid,candidate,rows,fault='correct'):
    if cid==IDS[2]:return delta.bench(cid,candidate,rows,fault)
    c=get_case(cid);lines=['module tb;','bit clk=0;always #5 clk=~clk;integer cycle=-1;']
    for k,width in {**c['inputs'],**c['outputs']}.items():lines.append(f'logic '+(f'[{width-1}:0] ' if width>1 else '')+k+'=0;')
    if cid==IDS[0]:
        lines+=['logic prior_valid=0;always @(posedge clk) prior_valid <= rst_n && valid;assign launch=valid && !prior_valid;',
          'stream_delay #(.FixedDelay(16),.StallRandom(0),.payload_t(logic[7:0])) dut(.clk_i(clk),.rst_ni(rst_n),.payload_i(payload),.ready_o(in_ready),.valid_i(valid),.payload_o(out_payload),.ready_i(ready),.valid_o(out_valid));']
    else:lines+=['cc_id_queue #(.IdWidth(2),.Capacity(4),.FullBw(0),.data_t(logic[7:0])) dut(.clk_i(clk),.rst_ni(rst_n),.clr_i(clear),.inp_id_i(inp_id),.inp_data_i(inp_data),.inp_req_i(inp_req),.inp_gnt_o(inp_gnt),.exists_data_i(8\'b0),.exists_mask_i(8\'b0),.exists_req_i(1\'b0),.exists_o(),.exists_gnt_o(),.oup_id_i(out_id),.oup_pop_i(pop),.oup_req_i(out_req),.oup_data_o(out_data),.oup_data_valid_o(out_valid),.oup_gnt_o(out_gnt),.full_o(full),.empty_o(empty));']
    for a in candidate:
        op='|=>' if a['timing']=='next_sample' else '|->';label=a['label'];ant=a['antecedent'];cons=a['consequent']
        lines += [f'{label}: assert property (@(posedge clk) disable iff(!rst_n) ({ant}) {op} ({cons})) else $display("ASSERT_FAIL {label} cycle=%0d",$sampled(cycle));',
            f'assert property (@(posedge clk) disable iff(!rst_n) !({ant})) else $display("TRIGGER {label} cycle=%0d",$sampled(cycle));']
    fields=list(c['inputs'])+list(c['outputs'])
    lines+=['always @(posedge clk) if(cycle>=0) $display("TRACE cycle=%0d '+' '.join(k+'=%0d' for k in fields)+'",cycle,'+','.join(fields)+');',
       'initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);']
    for i,row in enumerate(rows):lines+=['@(negedge clk);cycle='+str(i)+';'+' '.join(f'{k}={v};' for k,v in row.items())+' @(posedge clk);#1;']
    lines+=['$display("NATIVE_RUN_COMPLETE");$finish;end endmodule'];return '\n'.join(lines)

def reference(cid,traces):
    if cid==IDS[2]:
        result=delta.reference(cid,traces)
        # Every obligation is an implication defined at every sample. Absent
        # antecedents are explicitly inapplicable, not missing reference data.
        for t in traces:
            active={c['obligation'] for c in result['checks'] if c['cycle']==t['cycle']}
            for ob in set(delta.OBS)-active:result['checks'].append(dict(cycle=t['cycle'],transaction=t['cycle'],obligation=ob,passed=True,applicable=False))
        return result
    checks=[];unknown=[];pending={};history=[];start=None;max_pending=0;consumed=[]
    for i,r in enumerate(traces):
        verdict={ob:True for ob in get_case(cid)['obligations']};tx=i
        if cid==IDS[0]:
            if not r['rst_n']:start=None
            if r['launch'] and r['rst_n']:start=i
            age=i-start if start is not None else None;tx=start if start is not None else i
            if age is not None and r['rst_n']:
                expected=int(18<=age and r['valid'])
                # All schedules remove valid immediately after the sole handshake.
                verdict['exact_latency']=r['out_valid']==expected
                verdict['handshake_payload']=r['in_ready']==int(expected and r['ready']) and r['out_payload']==r['payload']
                if age==21:
                    observations=traces[start+1:i+1]
                    verdict['response_window']=not any(t['out_valid'] for t in observations[:17]) and any(t['out_valid'] for t in observations[17:21])
            if age is not None and age>21 and not r['valid']:start=None
        else:
            if not r['rst_n']:pending={}
            size=sum(len(q) for q in pending.values());verdict['queue_state']=r['empty']==int(size==0) and r['full']==int(size==4)
            if r['rst_n']:
                ready=int(size<4);ig=int(bool(r['inp_req'] and ready));og=int(bool(r['out_req'] and not ig))
                verdict['queue_state'] &= r['inp_gnt']==ready and r['out_gnt']==og
                q=pending.get(r['out_id'],[])
                expected_valid=bool(og and q)
                verdict['transaction_match']=r['out_valid']==int(expected_valid)
                if expected_valid:
                    request=q[0];tx=request['cycle'];verdict['transaction_match'] &= r['out_data']==request['data']
                    if r['pop']:consumed.append(dict(request=request,response_cycle=i));q.pop(0)
                if ig:pending.setdefault(r['inp_id'],[]).append(dict(cycle=i,data=r['inp_data'],tag=r['inp_id']))
                if r['clear']:pending={}
            max_pending=max(max_pending,sum(len(q) for q in pending.values()))
        for ob,passed in verdict.items():checks.append(dict(cycle=i,transaction=tx,obligation=ob,passed=bool(passed)))
    if cid==IDS[1] and any(pending.values()):unknown.append('incomplete_pending_tail')
    return dict(checks=checks,unknown=unknown,max_simultaneously_pending=max_pending,consumed=consumed)

def runtime():
    m=clone('research194_cases');m.CONFIG={cid:get_case(cid) for cid in IDS};m.FAULTS={cid:[] for cid in IDS}
    bound=[Path(__file__),*sorted((CC/'include').rglob('*.svh'))]
    for cfg in m.CONFIG.values():cfg['sources'] += [str(p.relative_to(ROOT)).replace('\\','/') for p in bound]
    m.get_case=get_case;m.query_pool=query_pool;m._sources=sources;m._bench=bench;m.reference=reference
    return m

def validate(cid,candidate):return runtime().validate(cid,candidate)
def evaluate(cid,candidate,out,queries=None,split='development',fault='primary',**kwargs):
    return runtime().evaluate(cid,candidate,out,queries=queries,split=split,fault=fault,**kwargs)

class CaseAdapter:
    def __init__(self,cid):
        self.case_id=cid;self.case=get_case(cid);self.case['rtl']={p:(ROOT/p).read_text() for p in self.case['sources']}
    def validate(self,candidate):return validate(self.case_id,candidate)
    def evaluate(self,candidate,out,queries):return bind_measurement(evaluate(self.case_id,candidate,out,queries=queries),candidate)
