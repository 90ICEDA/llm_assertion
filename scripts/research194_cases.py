"""Opt-in native cross-design adapters; explicit artificial faults on real RTL.

No model, no network. Queries are generated for the requested split only.
Expected outputs are adjudicated by independent Python transaction monitors.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import sys
import time
sys.dont_write_bytecode=True
import research_native_runner as native

ROOT=Path(__file__).resolve().parents[1]


def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def prop(label,ant,cons,ob,timing='same_sample'):
    return dict(label=label,antecedent=ant,consequent=cons,timing=timing,obligations=[ob])


CONFIG={
 'arbiter':dict(module='arbiter',sources=['external/verilog-axis/rtl/arbiter.v','external/verilog-axis/rtl/priority_encoder.v'],
   reset='rst',disable='rst',inputs=dict(rst=1,request=4,acknowledge=4),outputs=dict(grant=4,grant_valid=1,grant_encoded=2),
   obligations=['arbiter_priority','arbiter_valid','arbiter_hold','reset_cancel'],
   initial=[prop('grant_nonempty','(|request) && !(|grant)','(|grant)','arbiter_priority','next_sample')],
   alternative=[prop('grant_valid_now','(|request)','grant_valid','arbiter_valid')],
   instance="arbiter #(.PORTS(4),.ARB_TYPE_ROUND_ROBIN(0),.ARB_BLOCK(1),.ARB_BLOCK_ACK(1),.ARB_LSB_HIGH_PRIORITY(0)) dut (.clk(clk),.rst(rst),.request(request),.acknowledge(acknowledge),.grant(grant),.grant_valid(grant_valid),.grant_encoded(grant_encoded));"),
 'counter':dict(module='cc_counter',sources=['external/common_cells/src/cc_counter.sv','external/common_cells/src/cc_delta_counter.sv'],
   reset='rst_n',disable='!rst_n',inputs=dict(rst_n=1,clr=1,en=1,load=1,down=1,d=4),outputs=dict(q=4,overflow=1),
   obligations=['counter_step','counter_boundary','counter_load','clear_cancel','reset_cancel'],
   initial=[prop('small_up','en && !load && !clr && !down && q < 4',"q == (($past(q) + 1) & 4'hf)",'counter_step','next_sample')],
   alternative=[prop('up_same_cycle','en && !load && !clr && !down',"q == (($past(q) + 1) & 4'hf)",'counter_step')],
   instance="cc_counter #(.Width(4),.StickyOverflow(0)) dut (.clk_i(clk),.rst_ni(rst_n),.clr_i(clr),.en_i(en),.load_i(load),.down_i(down),.d_i(d),.q_o(q),.overflow_o(overflow));"),
 'uart':dict(module='uart_tx',sources=['external/opentitan/hw/ip/uart/rtl/uart_tx.sv'],
   reset='rst_n',disable='!rst_n',inputs=dict(rst_n=1,tx_enable=1,tick_baud_x16=1,parity_enable=1,wr=1,wr_parity=1,wr_data=8),outputs=dict(idle=1,tx=1),
   obligations=['uart_start_delay','uart_data_match','uart_stop','uart_busy','disable_cancel','reset_cancel'],
   initial=[prop('start_exact','txn_active && txn_age == 16',"tx == 1'b0",'uart_start_delay')],
   alternative=[prop('start_early','txn_active && txn_age == 15',"tx == 1'b0",'uart_start_delay'),prop('first_bit','txn_active && txn_age == 32','tx == latched_data[0]','uart_data_match')],
   instance="uart_tx dut (.clk_i(clk),.rst_ni(rst_n),.tx_enable(tx_enable),.tick_baud_x16(tick_baud_x16),.parity_enable(parity_enable),.wr(wr),.wr_parity(wr_parity),.wr_data(wr_data),.idle(idle),.tx(tx));")}


FAULTS={
 'arbiter':[
  dict(id='primary',operator='suppress_update',site='grant_valid_register',obligation='arbiter_valid',search='    grant_valid_reg <= grant_valid_next;',replace='    grant_valid_reg <= grant_valid_reg;',split='development'),
  dict(id='dev_grant_hold',operator='suppress_update',site='grant_register',obligation='arbiter_priority',search='    grant_reg <= grant_next;',replace='    grant_reg <= grant_reg;',split='development'),
  dict(id='dev_hold_ignore_ack',operator='condition_negation',site='blocking_condition',obligation='arbiter_hold',search='ARB_BLOCK && ARB_BLOCK_ACK && grant_valid && !(grant_reg & acknowledge)',replace='ARB_BLOCK && ARB_BLOCK_ACK && grant_valid && (grant_reg & acknowledge)',split='development'),
  dict(id='test_priority',operator='parameter_inversion',site='encoder_priority',obligation='arbiter_priority',search='.LSB_HIGH_PRIORITY(ARB_LSB_HIGH_PRIORITY)',replace='.LSB_HIGH_PRIORITY(!ARB_LSB_HIGH_PRIORITY)',split='independent'),
  dict(id='test_encoding',operator='xor_output',site='encoded_output',obligation='arbiter_priority',search='assign grant_encoded = grant_encoded_reg;',replace="assign grant_encoded = grant_encoded_reg ^ 1'b1;",split='independent')],
 'counter':[
  dict(id='primary',operator='double_step',site='up_arithmetic',obligation='counter_step',file=1,search='counter_d = counter_q + delta_i;',replace='counter_d = counter_q + delta_i + delta_i;',split='development'),
  dict(id='dev_clear_disable',operator='disable_clear',site='state_clear',obligation='clear_cancel',file=1,search="`FFARNC(counter_q, counter_d, clr_i, '0, clk_i, rst_ni)",replace="`FFARNC(counter_q, counter_d, 1'b0, '0, clk_i, rst_ni)",split='development'),
  dict(id='dev_load_offbyone',operator='offset_load',site='load_arithmetic',obligation='counter_load',file=1,search="counter_d = {1'b0, d_i};",replace="counter_d = {1'b0, d_i} + 1'b1;",split='development'),
  dict(id='test_down_invert',operator='direction_inversion',site='down_arithmetic',obligation='counter_step',file=1,search='counter_d = counter_q - delta_i;',replace='counter_d = counter_q + delta_i;',split='independent'),
  dict(id='test_output_msb',operator='xor_output',site='count_output',obligation='counter_boundary',file=1,search='assign q_o = counter_q[Width-1:0];',replace="assign q_o = counter_q[Width-1:0] ^ 4'h8;",split='independent')],
 'uart':[
  dict(id='primary',operator='double_tick',site='baud_divider',obligation='uart_start_delay',search="{1'b0,baud_div_q} + 5'h1",replace="{1'b0,baud_div_q} + 5'h2",split='development'),
  dict(id='dev_data_xor',operator='xor_input',site='frame_load',obligation='uart_data_match',search="wr_data, 1'b0}",replace="(wr_data ^ 8'h01), 1'b0}",split='development'),
  dict(id='dev_disable_ignore',operator='disable_cancel_removal',site='disable_branch',obligation='disable_cancel',search='if (!tx_enable) begin',replace="if (1'b0) begin",split='development'),
  dict(id='test_shift_skip',operator='skip_serial_bit',site='shift_update',obligation='uart_data_match',search="sreg_d    = {1'b1, sreg_q[10:1]};",replace="sreg_d    = {2'b11, sreg_q[10:2]};",split='independent'),
  dict(id='test_short_frame',operator='shorten_frame',site='bit_count_load',obligation='uart_stop',search="(parity_enable ? 4'd11 : 4'd10)",replace="(parity_enable ? 4'd10 : 4'd9)",split='independent')]}


def list_cases():return list(CONFIG)
def get_case(case_id):
    if case_id in ('ibex','ibex_flush'):
        import research194_ibex
        return research194_ibex.get_case(case_id)
    cfg=copy.deepcopy(CONFIG[case_id]);cfg['id']=case_id
    cfg['specification']={
      'arbiter':'Four request bits use highest-index fixed priority. Outputs are registered one cycle after selection. Hold the existing valid grant until acknowledge intersects that grant, regardless of changing requests; then choose the highest current request. grant_valid equals whether a grant exists and grant_encoded identifies its bit. Synchronous active-high rst clears all grant state.',
      'counter':'Unsigned Width=4 counter with one overflow bit, StickyOverflow=0. Active-low asynchronous rst_n clears state. At a rising edge, clr has priority and clears state, then load writes d with overflow zero, then en adds one when down=0 or subtracts one when down=1, wrapping the full five-bit state. Otherwise hold. q exposes low four bits; overflow exposes bit four. Next-sample obligations observe the result of the preceding edge.',
      'uart':'UART transmitter; active-low asynchronous rst_n cancels transmission and drives tx high. tx_enable=0 cancels the frame and exposes idle=1. wr while enabled and idle captures wr_data (LSB first), start bit zero, optional wr_parity, then stop bit one. A free-running divider emits one baud tick every 16 tick_baud_x16 pulses, followed by a registered pulse used for shifting. Public queries include continuous ticks, explicit tick pauses, and two writes with different data; parity is disabled. Input-derived txn_active/txn_age/latched_data track the most recent wr and clear on reset or disable; age=0 in the sample after wr. txn_age counts clock cycles, NOT baud ticks. For the first phase-aligned write with uninterrupted ticks only, start is age16..31, data bit i age32+16*i..47+16*i, stop from age160. Later writes retain divider phase and paused ticks delay transmission. idle is low while the frame remains active.'
    }[case_id]
    cfg['input_signals']=copy.deepcopy(cfg['inputs']);cfg['output_signals']=copy.deepcopy(cfg['outputs'])
    cfg['signals']=list(cfg['inputs'])+list(cfg['outputs'])+['cycle']+(['txn_age','txn_active','latched_data'] if case_id=='uart' else [])
    cfg['candidate_pool']=[cfg['initial'],cfg['alternative']]
    cfg['candidate_provenance']='handwritten partial and contrasting temporal seed; no LLM or historical success claim'
    cfg['provenance']=dict(real_project_RTL=True,historical_fix_confirmed=cfg.get('historical_fix_confirmed',False),cohort=cfg.get('cohort','artificial_obligation_faults'),
        sources={x:hashlib.sha256((ROOT/x).read_bytes()).hexdigest() for x in cfg['sources']},
        note='Upstream source has one locally available commit; no synthetic mutation is attributed to an upstream historical repair.')
    cfg['faults']=copy.deepcopy([f for f in FAULTS[case_id] if f['split']=='development']);return cfg


def validate(case_id,candidate):
    if case_id=='ibex':
        import research194_ibex
        return research194_ibex.validate(case_id,candidate)
    cfg=get_case(case_id);labels=set()
    if not isinstance(candidate,list) or not 1<=len(candidate)<=32:raise ValueError('assertion_count')
    for a in candidate:
        if set(a)!={'label','antecedent','consequent','timing','obligations'}:raise ValueError('candidate_fields')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,79}',a['label']) or a['label'] in labels:raise ValueError('label')
        labels.add(a['label'])
        if a['timing'] not in ('same_sample','next_sample'):raise ValueError('timing')
        if not set(a['obligations'])<=set(cfg['obligations']) or not a['obligations']:raise ValueError('obligations')
        for key in ('antecedent','consequent'):
            exp=a[key]
            if not isinstance(exp,str) or len(exp)>3000 or not exp.strip():raise ValueError('expression')
            if any(t in exp for t in (';','//','/*','`','"','\\')):raise ValueError('statement_not_expression')
            stripped=re.sub(r"\d*'[sS]?[hHbBdDoO][0-9a-fA-F_xXzZ]+",'0',exp)
            ids=set(re.findall(r'[A-Za-z_$][A-Za-z0-9_$]*',stripped))
            if ids-set(cfg['signals'])-{'$past','$stable','$rose','$fell','$onehot','$onehot0','true','false'}:raise ValueError('identifier:'+str(ids-set(cfg['signals'])))
    return copy.deepcopy(candidate)


def render(candidate):
    return '\n'.join(f"{a['label']}: assert property (@(posedge clk) ({a['antecedent']}) {'|=>' if a['timing']=='next_sample' else '|->'} ({a['consequent']}));" for a in candidate)


def controls(case_id):
    """Handwritten specification controls for wiring qualification, never LLM results."""
    if case_id=='counter':
        a=[prop('all_up','en && !load && !clr && !down',"q == (($past(q) + 1) & 4'hf)",'counter_step','next_sample'),
           prop('all_down','en && !load && !clr && down',"q == (($past(q) - 1) & 4'hf)",'counter_step','next_sample'),
           prop('load_value','load && !clr','q == $past(d)','counter_load','next_sample'),
           prop('clear_value','clr','q == 0','clear_cancel','next_sample')]
        a[0]['obligations'].append('counter_boundary');a[1]['obligations'].append('counter_boundary');return a
    if case_id=='arbiter':
        return [prop('priority_next','!grant_valid || (|(grant & acknowledge))',
            "grant == ($past(request[3]) ? 4'b1000 : $past(request[2]) ? 4'b0100 : $past(request[1]) ? 4'b0010 : $past(request[0]) ? 4'b0001 : 4'b0)",'arbiter_priority','next_sample'),
            prop('valid_next','!grant_valid || (|(grant & acknowledge))','grant_valid == (|$past(request))','arbiter_valid','next_sample'),
            prop('hold_next','grant_valid && !(|(grant & acknowledge))','$stable(grant) && grant_valid','arbiter_hold','next_sample')]
    if case_id=='uart':
        a=[prop('before_start','txn_active && txn_age < 16','tx == 1','uart_start_delay'),
           prop('start_bit','txn_active && txn_age >= 16 && txn_age < 32','tx == 0','uart_start_delay'),
           prop('stop_bit','txn_active && txn_age >= 160','tx == 1','uart_stop'),
           prop('accepted_busy','wr && tx_enable','!idle','uart_busy','next_sample'),
           prop('cancel_disable','!tx_enable','tx && idle','disable_cancel','next_sample')]
        for i in range(8):a.append(prop('data'+str(i),f'txn_active && txn_age >= {32+16*i} && txn_age < {48+16*i}',f'tx == latched_data[{i}]','uart_data_match'))
        return a
    raise ValueError('controls_not_available')


def query_pool(case_id,split='development',seed=19407):
    if case_id=='ibex_flush':
        import research194_ibex
        return research194_ibex.query_pool(case_id,split,seed)
    if case_id=='ibex':
        import research194_ibex
        return research194_ibex.query_pool(case_id,split,seed)
    if split not in ('development','independent'):raise ValueError('split')
    rng=random.Random(seed);rows=[];cfg=CONFIG[case_id]
    def defaults():return {k:0 for k in cfg['inputs']}
    def build(family,index):
        rr=[]
        def add(**kw):
            r=defaults();r.update(kw);rr.append(r)
        if case_id=='arbiter':
            for _ in range(3):add(rst=1)
            base=([1,3,8,6,15,0] if split=='development' else [2,5,4,10,9,0])
            for request in base:
                add(request=request,acknowledge=15)
                add(request=15 if family=='hold' else request,acknowledge=0)
                add(request=1 if family=='hold' else request,acknowledge=15)
            if family=='reset':
                add(rst=1,request=15);add(request=0);add(request=4,acknowledge=15)
            for _ in range(3):add(acknowledge=15)
        elif case_id=='counter':
            for _ in range(3):add(rst_n=0)
            add(rst_n=1,load=1,d=0)
            for i in range(19):add(rst_n=1,en=1,down=int(family=='down'))
            add(rst_n=1,load=1,d=15 if split=='development' else 14,en=1)
            for _ in range(4):add(rst_n=1,en=1)
            add(rst_n=1,clr=1,en=1,load=int(family=='clear'),d=9)
            add(rst_n=1,en=1);add(rst_n=0);add(rst_n=1)
            for _ in range(3):add(rst_n=1)
        else:
            for _ in range(3):add(rst_n=0)
            data=([0xA5,0x3C,0x81,0x5A,0xC3] if split=='development' else [0x69,0x96,0x42,0xB4,0x87])[index]
            add(rst_n=1,tx_enable=1,tick_baud_x16=1,wr=1,wr_data=data,parity_enable=0)
            for i in range(190):
                cancel=(family=='disable' and 45<=i<51)
                reset=(family=='reset' and 45<=i<48)
                pause=family=='tick_pause' and (40 if split=='development' else 56)<=i<(49 if split=='development' else 69)
                add(rst_n=int(not reset),tx_enable=int(not cancel),tick_baud_x16=int(not pause))
            if family=='back_to_back':
                for _ in range(5 if split=='development' else 11):add(rst_n=1,tx_enable=1,tick_baud_x16=1)
                add(rst_n=1,tx_enable=1,tick_baud_x16=1,wr=1,wr_data=data^0xFF)
                for _ in range(190):add(rst_n=1,tx_enable=1,tick_baud_x16=1)
            for _ in range(4):add(rst_n=1,tx_enable=1,tick_baud_x16=1)
        return rr
    families={'arbiter':['priority','hold','reset'],'counter':['up','down','clear'],'uart':['serial','disable','reset','back_to_back','tick_pause']}[case_id]
    for i,family in enumerate(families):
        rr=build(family,i)
        rows.append(dict(id=case_id+'/'+family+'/'+digest(rr)[:12],family=family,rows=rr,
            obligations=cfg['obligations'],dimensions=['trigger','response','window','transaction','exception'],
            constraints=['fixed clock pre-edge sampling','legal input values','reset cancels pending transaction']+
                (['write only while independently idle','parity disabled','txn_age counts clocks since most recent write, not baud ticks; divider is free-running', 'tick pause is explicit in input rows' if family=='tick_pause' else 'tick continuously16x baud'] if case_id=='uart' else []),
            estimated_cost=2,split=split,semantic_key=digest(dict(case=case_id,family=family,inputs=rr)),
            evidence_visibility='public_development' if split=='development' else 'heldout_after_freeze'))
    return rows


def _sources(case_id,folder,fault):
    if case_id=='ibex_flush':
        import research194_ibex
        return research194_ibex.sources(folder,fault)
    cfg=CONFIG[case_id];spec=next((f for f in FAULTS[case_id] if f['id']==fault),None)
    if fault not in ('correct',None) and spec is None:raise ValueError('fault')
    result=[]
    for i,source in enumerate(cfg['sources']):
        text=(ROOT/source).read_text()
        if spec and i==spec.get('file',0):
            if not text.count(spec['search']):raise ValueError('mutation_site_missing')
            text=text.replace(spec['search'],spec['replace'])
        if case_id=='counter' and i==1:
            text=text.replace('`include "common_cells/registers.svh"',(ROOT/'external/common_cells/include/common_cells/registers.svh').read_text())
            text=text.replace('`include "common_cells/deprecated/registers.svh"',(ROOT/'external/common_cells/include/common_cells/deprecated/registers.svh').read_text())
        path=folder/Path(source).name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);result.append(path)
    return result


def _bench(case_id,candidate,rows,fault='correct'):
    if case_id=='ibex_flush':
        import research194_ibex
        return research194_ibex.bench(candidate,rows,fault)
    cfg=CONFIG[case_id]
    decl=['`timescale 1ns/1ps','module tb;','reg clk=0; always #5 clk=~clk;','integer cycle=-1;']
    for k,w in cfg['inputs'].items():decl.append(f'reg [{w-1}:0] {k}=0;')
    for k,w in cfg['outputs'].items():decl.append(f'wire [{w-1}:0] {k};')
    if case_id=='uart':
        decl.append('integer txn_age=0; reg txn_active=0; reg[7:0] latched_data=0; always @(posedge clk) if(!rst_n || !tx_enable) begin txn_age<=0;txn_active<=0;latched_data<=0;end else if(wr) begin txn_age<=0;txn_active<=1;latched_data<=wr_data;end else if(txn_active) txn_age<=txn_age+1;')
    decl.append(cfg['instance'])
    for a in candidate:
        ant=a['antecedent'];cons=a['consequent'];op='|=>' if a['timing']=='next_sample' else '|->'
        decl.append(f"{a['label']}: assert property (@(posedge clk) disable iff({cfg['disable']}) ({ant}) {op} ({cons})) else $display(\"ASSERT_FAIL {a['label']} cycle=%0d\",$sampled(cycle));")
        # Native diagnostic assertion avoids cover actions being omitted without coverage.
        decl.append(f"assert property (@(posedge clk) disable iff({cfg['disable']}) !({ant})) else $display(\"TRIGGER {a['label']} cycle=%0d\",$sampled(cycle));")
    fields=list(cfg['inputs'])+list(cfg['outputs'])+(['txn_age','txn_active','latched_data'] if case_id=='uart' else [])
    decl.append('initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);')
    for i,row in enumerate(rows):
        decl.append('@(negedge clk);cycle='+str(i)+';'+' '.join(f'{k}={row[k]};' for k in cfg['inputs']))
        decl.append('@(posedge clk);$display("TRACE cycle=%0d '+' '.join(k+'=%0d' for k in fields)+'",cycle,'+','.join(fields)+');')
    decl.append('@(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule')
    return '\n'.join(decl)+'\n'


def reference(case_id,traces):
    """Protocol-level abstract monitors; no candidate expressions are consulted."""
    if case_id=='ibex_flush':
        import research194_ibex
        return research194_ibex.reference(traces)
    checks=[];unknown=[];cfg=CONFIG[case_id]
    if len(traces)<3:return dict(checks=[],unknown=['short_trace'])
    def record(row,ob,expected,actual,tid):
        checks.append(dict(cycle=row['cycle'],obligation=ob,passed=expected==actual,expected=expected,actual=actual,transaction=tid))
    if case_id=='arbiter':
        grant=0
        for prev,row in zip(traces,traces[1:]):
            if prev['rst']:grant=0;ob='reset_cancel'
            elif grant and not(grant&prev['acknowledge']):ob='arbiter_hold'
            else:grant=1<<(prev['request'].bit_length()-1) if prev['request'] else 0;ob='arbiter_priority'
            record(row,ob,grant,row['grant'],prev['cycle'])
            record(row,'arbiter_valid',int(bool(grant)),row['grant_valid'],prev['cycle'])
            record(row,'arbiter_priority',max(0,grant.bit_length()-1),row['grant_encoded'],prev['cycle'])
    elif case_id=='counter':
        for prev,row in zip(traces,traces[1:]):
            state=prev['q']+16*prev['overflow']
            if not row['rst_n'] or not prev['rst_n']:value=0;ob='reset_cancel'
            elif prev['clr']:value=0;ob='clear_cancel'
            elif prev['load']:value=prev['d'];ob='counter_load'
            elif prev['en']:
                value=(state+(-1 if prev['down'] else 1))%32
                ob='counter_boundary' if (prev['q']==0 and prev['down']) or (prev['q']==15 and not prev['down']) else 'counter_step'
            else:value=state;ob='counter_step'
            record(row,ob,value%16,row['q'],prev['cycle'])
            record(row,'counter_boundary',value//16,row['overflow'],prev['cycle'])
    else:
        ticks=0;pulse=False;symbols=[];tx=1;transaction=-1;position=-1
        for prev,row in zip(traces,traces[1:]):
            ob='uart_busy'
            if not row['rst_n'] or not prev['rst_n']:
                ticks=0;pulse=False;symbols=[];tx=1;transaction=-1;position=-1;ob='reset_cancel'
            else:
                due=pulse
                ticks+=int(bool(prev['tick_baud_x16']));pulse=ticks>=16
                if pulse:ticks-=16
                if not prev['tx_enable']:symbols=[];tx=1;ob='disable_cancel'
                elif prev['wr']:
                    if symbols:unknown.append('write_while_busy:'+str(prev['cycle']))
                    transaction=prev['cycle'];position=-1
                    symbols=[0]+[(prev['wr_data']>>i)&1 for i in range(8)]+([prev['wr_parity']] if prev['parity_enable'] else [])+[1]
                elif due and symbols:
                    tx=symbols.pop(0);position+=1
                    ob='uart_start_delay' if position==0 else 'uart_stop' if not symbols else 'uart_data_match'
                elif symbols:ob='uart_start_delay' if position<0 else 'uart_data_match'
            record(row,ob,tx,row['tx'],transaction)
            record(row,'uart_busy',int(not symbols) if row['tx_enable'] else 1,row['idle'],transaction)
    return dict(checks=checks,unknown=sorted(set(unknown)))


def evaluate(case_id,candidate,out,queries=None,split='development',fault='primary',cleanup=True,_trusted_bundle=False):
    """Each query costs two native jobs; explicit fault='correct' costs one.

Evidence IDs collapse strategy/seed/cycle variants by case+fault+obligation+local
input/output state. No hidden split is generated or inspected as a side effect.
"""
    if case_id=='ibex':
        import research194_ibex
        return research194_ibex.evaluate(case_id,candidate,out,queries=queries,split=split,fault=fault,cleanup=cleanup)
    if _trusted_bundle:
        if len({a['label'] for a in candidate})!=len(candidate):raise ValueError('bundle_duplicate_label')
        candidate=[validate(case_id,[a])[0] for a in candidate]
    else:candidate=validate(case_id,candidate)
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    if not out.is_relative_to(ROOT/'deliverables'):raise ValueError('deliverables only')
    queries=query_pool(case_id,split) if queries is None else queries
    if any(q.get('split',split)!=split for q in queries):raise ValueError('cross_split_query')
    if split=='development' and any(f['id']==fault and f['split']=='independent' for f in FAULTS[case_id]):raise ValueError('test_fault_in_development')
    started=time.monotonic();jobs=[];evidence=[];unknown=[];targets=set();detected=set();triggered=set();fps=[];coverage=set();transactions=set();cleanup_rows=[]
    bound=[Path(__file__),Path(native.__file__)]+[ROOT/p for p in CONFIG[case_id]['sources']]
    if case_id=='counter':bound += [ROOT/'external/common_cells/include/common_cells/registers.svh',ROOT/'external/common_cells/include/common_cells/deprecated/registers.svh']
    if case_id=='ibex_flush':bound.append(ROOT/'scripts/research194_ibex.py')
    bindings={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in bound}
    for p in bound:
        dst=out/'source_snapshot'/(hashlib.sha256(str(p).encode()).hexdigest()[:12]+'_'+p.name);dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(p.read_bytes())
    dump(out/'source_bindings.json',bindings)
    dump(out/'protocol.json',dict(case=get_case(case_id),candidate=candidate,queries=queries,split=split,fault=fault,
        test_access=split=='independent',model_calls=0,oracle='independent protocol-level Python monitor'))
    for qi,query in enumerate(queries):
        pair={}
        for variant in (['correct'] if fault=='correct' else ['correct',fault]):
            folder=out/f'q{qi}'/variant;src=_sources(case_id,out/f'q{qi}'/(variant+'_rtl'),variant)
            try:result=native.run_native(_bench(case_id,candidate,query['rows'],variant),folder,extra_sources=src,timeout=180)
            except Exception as exc:
                result=dict(compile_status='unknown',execution_status='failed',failures=[],triggers=[],error=repr(exc));dump(folder/'result.json',result)
            traces=[]
            if (folder/'execute.log').exists():
                for line in (folder/'execute.log').read_text().splitlines():
                    if line.startswith('TRACE '):traces.append({k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',line)})
            ref=reference(case_id,traces) if result['compile_status']=='passed' and result['execution_status']=='completed' else dict(checks=[],unknown=['native_incomplete'])
            if len(traces)!=len(query['rows']):ref['unknown'].append('trace_length')
            for i,tr in enumerate(traces):
                if i<len(query['rows']) and any(tr.get(k)!=v for k,v in query['rows'][i].items()):ref['unknown'].append('input_mismatch')
            job=dict(query_id=query['id'],variant=variant,folder=str(folder),result=result,trace=traces,reference=ref)
            jobs.append(job);pair[variant]=job;dump(folder/'reference.json',ref)
            if cleanup:
                cache=(folder/'obj_dir').resolve()
                if cache.is_relative_to(out) and cache.is_dir():
                    for derived in cache.iterdir():
                        if derived.is_file() and derived.suffix in ('.gch','.o','.a'):
                            cleanup_rows.append(dict(path=str(derived),bytes=derived.stat().st_size,sha256=hashlib.sha256(derived.read_bytes()).hexdigest(),reason='completed_native_job_derived_cache'))
                            derived.unlink()
                    dump(out/'cleanup_manifest.json',cleanup_rows)
            dump(out/'executions.json',jobs)
        good=pair['correct'];good_legal=not good['reference']['unknown'] and not any(not c['passed'] for c in good['reference']['checks'])
        for variant,job in pair.items():
            badcycles={c['cycle']:[] for c in job['reference']['checks'] if not c['passed']}
            for c in job['reference']['checks']:
                if not c['passed']:badcycles[c['cycle']].append(c)
            checks_by_cycle={}
            for c in job['reference']['checks']:checks_by_cycle.setdefault(c['cycle'],[]).append(c)
            marks=lambda key:{(m['id'],int(re.search(r'cycle=(-?\d+)',m['detail'])[1])) for m in job['result'].get(key,[]) if re.search(r'cycle=(-?\d+)',m['detail'])}
            alarms=marks('failures');trigs=marks('triggers')
            if job['reference']['unknown'] or not good_legal:unknown.append(dict(query=query['id'],variant=variant,reason=job['reference']['unknown'] or ['paired_correct_not_legal']))
            for label,cy in alarms:
                a=next(a for a in candidate if a['label']==label)
                if not set(a['obligations']) & {c['obligation'] for c in checks_by_cycle.get(cy,[])}:
                    if variant=='correct' and good_legal:
                        ev=dict(id=digest(dict(case=case_id,query=query['semantic_key'],cycle=cy,kind='legal_unbound_alarm')),status='confirmed',label='legal',obligation=None,query_id=query['id'],variant=variant,cycle=cy,
                          parent_bug=CONFIG[case_id].get('parent_bug',case_id+'/artificial'),transaction_id=digest(dict(case=case_id,query=query['semantic_key'],variant=variant,cycle=cy)),transaction=cy,
                          assertions=[dict(assertion=label,obligations=a['obligations'],trigger=(label,cy-1 if a['timing']=='next_sample' else cy) in trigs,failure=True)],
                          observations=job['trace'][cy],previous_observations=job['trace'][max(0,cy-1)],source_vcd=str(Path(job['folder'])/'wave.vcd'),source_log=str(Path(job['folder'])/'execute.log'),reason='alarm_on_independently_legal_correct_trace')
                        ev['evidence_id']=ev['id'];evidence.append(ev);fps.append(ev)
                    else:unknown.append(dict(query=query['id'],variant=variant,assertion=label,cycle=cy,reason=['alarm_without_matching_reference_obligation']))
            first_violations={}
            for c in job['reference']['checks']:
                if not c['passed']:
                    first_violations.setdefault((c['transaction'],c['obligation']),c['cycle'])
            for cy,checks in checks_by_cycle.items():
                row=job['trace'][cy];prev=job['trace'][max(0,cy-1)]
                violated=sorted({c['obligation'] for c in checks if not c['passed']})
                status='confirmed' if good_legal and not job['reference']['unknown'] else 'unknown'
                obs=[]
                for a in candidate:
                    tc=cy-1 if a['timing']=='next_sample' else cy
                    obs.append(dict(assertion=a['label'],obligations=a['obligations'],trigger=(a['label'],tc) in trigs,failure=(a['label'],cy) in alarms))
                for ob in sorted({c['obligation'] for c in checks}):
                    tx=next(c['transaction'] for c in checks if c['obligation']==ob)
                    is_bad=ob in violated
                    # Only the first violation of this obligation in this transaction
                    # can be a detection. Later failing cycles are audit evidence.
                    eligible=not is_bad or first_violations[(tx,ob)]==cy
                    txid=digest(dict(case=case_id,query_semantics=query.get('semantic_key',digest(query['rows'])),fault=variant,transaction=tx))
                    eid=digest(dict(transaction=txid,obligation=ob)) if is_bad else digest(dict(case=case_id,obligation=ob,inputs={k:prev[k] for k in CONFIG[case_id]['inputs']},output={k:row[k] for k in CONFIG[case_id]['outputs']}))
                    relevant=[a for a in obs if ob in a['obligations']]
                    # Legal feedback comes from the independently legal paired RTL.
                    # A mutant's temporal history may already contain a violation;
                    # a locally passing cycle cannot certify a delayed alarm as FP.
                    evstatus='unknown' if not is_bad and (violated or variant!='correct') else status
                    ev=dict(id=eid,evidence_id=eid,status=evstatus,label='violation' if is_bad else 'legal',obligation=ob,query_id=query['id'],
                        parent_bug=CONFIG[case_id].get('parent_bug',case_id+'/artificial'),transaction=tx,transaction_id=txid,
                        first_violation=eligible if is_bad else None,counted_target=bool(is_bad and eligible),
                        cycle=cy,variant=variant,observations=row,previous_observations=prev,assertions=relevant,
                        source_vcd=str(Path(job['folder'])/'wave.vcd'),source_log=str(Path(job['folder'])/'execute.log'))
                    evidence.append(ev)
                    if evstatus!='confirmed':continue
                    if is_bad and eligible:
                        targets.add(eid)
                        transactions.add(txid)
                        if any(a['trigger'] for a in relevant):triggered.add(eid)
                        if any(a['failure'] for a in relevant):detected.add(eid);coverage.add(ob)
                    elif not is_bad and any(a['failure'] for a in relevant):fps.append(ev)
    commands=[p for p in out.rglob('compile.json')]+[p for p in out.rglob('execute.json')]
    cost=dict(model_calls=0,queries=len(queries),native_compile_attempts=len(list(out.rglob('compile.json'))),
        native_execution_attempts=len(list(out.rglob('execute.json'))),
        native_seconds=sum(json.loads(f.read_text()).get('wall_seconds',0) for f in commands),wall_seconds=time.monotonic()-started)
    source_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==sha for p,sha in bindings.items())
    if not source_unchanged:unknown.append(dict(reason=['source_changed_during_execution']))
    result=dict(case_id=case_id,parent_bug=CONFIG[case_id].get('parent_bug',case_id+'/artificial'),candidate_sha256=digest(candidate),source_bindings=bindings,source_unchanged=source_unchanged,
        native_complete=all(j['result']['compile_status']=='passed' and j['result']['execution_status']=='completed' and not j['reference']['unknown'] for j in jobs),
        reference_complete=not unknown,targets=sorted(targets),detected_ids=sorted(detected),
        triggered_ids=sorted(triggered),target_transaction_ids=sorted(transactions),parent_count=1,
        count_unit='first_violation_per_transaction_and_obligation; target_transaction_ids deduplicates obligations',
        false_positives=fps,critical_unknown=unknown,evidence=evidence,
        executions=jobs,cost=cost,covered_obligations=sorted(coverage),independent_fault=split=='independent',
        native_sva=True,historical_fix_confirmed=CONFIG[case_id].get('historical_fix_confirmed',False),source_scope=get_case(case_id)['provenance'])
    dump(out/'measurement.json',result);dump(out/'cost.json',cost)
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--case',choices=list_cases(),required=True)
    ap.add_argument('--fault',default='primary');ap.add_argument('--query-limit',type=int,default=1)
    args=ap.parse_args();case=get_case(args.case)
    m=evaluate(args.case,case['initial'],args.out,queries=query_pool(args.case)[:args.query_limit],fault=args.fault)
    print(json.dumps(dict(case=args.case,targets=len(m['targets']),detected=len(m['detected_ids']),fps=len(m['false_positives']),unknown=len(m['critical_unknown']),cost=m['cost'])))
if __name__=='__main__':main()
