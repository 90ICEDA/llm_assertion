"""Original Ibex #2374 flush sub-fix, at the compressed-decoder pipeline boundary.

Both revisions are original upstream modules. The harness drives the IF-stage
flush contract; it is not a full CPU or the later atomic-commit fix verification.
"""
import copy
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'deliverables/research194_ibex_sources_20261103_r01'
PARENT='lowRISC/ibex#2374/flush_subfix'
SIGNALS=dict(rst_n=1,valid=1,ready=1,flush=1,instr=32,instr_out=32,expanded=2,illegal=1,state=3)
OBS=['flush_cancel','expansion_match','stall_hold','reset_cancel']
FAULTS=[
 dict(id='primary',split='development',operator='historical_before',site='expansion_state_update',obligation='flush_cancel'),
 dict(id='dev_ready_gate',split='development',operator='gate_flush_by_ready',site='flush_enable',obligation='flush_cancel'),
 dict(id='dev_stall_advance',split='development',operator='force_ready',site='ready_input',obligation='stall_hold'),
 dict(id='test_valid_gate',split='independent',operator='gate_flush_by_valid',site='flush_input_connection',obligation='flush_cancel'),
 dict(id='test_reset_disconnect',split='independent',operator='ignore_mid_reset',site='reset_input_connection',obligation='reset_cancel'),
]


def prop(label,ant,cons,ob,timing='next_sample'):
    return dict(label=label,antecedent=ant,consequent=cons,timing=timing,obligations=[ob])


def register():
    import research194_cases as c
    if 'ibex_flush' not in c.CONFIG:
        c.CONFIG['ibex_flush']=dict(id='ibex_flush',module='ibex_compressed_decoder',reset='rst_n',disable='!rst_n',
            inputs={k:SIGNALS[k] for k in ('rst_n','valid','ready','flush','instr')},
            outputs={k:SIGNALS[k] for k in ('instr_out','expanded','illegal','state')},
            obligations=OBS,parent_bug=PARENT,historical_fix_confirmed=True,
            sources=[str((SOURCE/rev/name).relative_to(ROOT)).replace('\\','/') for rev in ('before','after') for name in ('ibex_compressed_decoder.sv','ibex_pkg.sv','ibex_if_stage.sv')],
            initial=[prop('flush_when_valid_ready','flush && valid && ready','state == 0','flush_cancel')],
            alternative=[prop('flush_while_stalled','flush && !ready','state == 0','flush_cancel'),
                prop('wrong_zero_delay','flush','state == 0','flush_cancel','same_sample')],
            instance='original upstream compressed decoder; IF pc_set && PC_EXC boundary contract',
            spec='On exception/interrupt IF flush, next sampled expansion state is idle even when valid or ready is low. Reset cancels expansion. Until consumption, expanded instruction remains stable unless flushed or reset. New compressed instruction after cancellation must restart at its own first micro-operation.')
        c.FAULTS['ibex_flush']=copy.deepcopy(FAULTS)
    return c


def get_case(case_id='ibex'):
    c=register();cfg=copy.deepcopy(c.CONFIG['ibex_flush'])
    cfg['id']='ibex_flush';cfg['signals']=list(SIGNALS)+['cycle']
    cfg['input_signals']=cfg['inputs'];cfg['output_signals']=cfg['outputs']
    cfg['candidate_pool']=[cfg['initial'],cfg['alternative']]
    cfg['candidate_provenance']='handwritten partial initial and contrasting temporal seeds; original DUT Bug/fix is real'
    cfg['faults']=[x for x in copy.deepcopy(FAULTS) if x['split']=='development']
    cfg['provenance']=dict(real_project_RTL=True,historical_fix_confirmed=True,
        upstream='https://github.com/lowRISC/ibex/pull/2374',
        before='022f084096baed0a9b5ebdf697ed2965f13e8ed8',after='3642b159632b754ad782f6b6d092ee1c24146168',
        sources={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in cfg['sources']},
        scope='Original compressed decoder at legal IF flush/ready/valid boundary, not full CPU. Only first flush sub-fix, not later atomic retirement changes.')
    return cfg


def validate(case_id,candidate):
    c=register()
    # Registered alias enters the common validator, not the ibex delegation.
    return c.validate('ibex_flush',candidate)


def instruction(kind,rlist=7,spimm=0):
    return (0b101<<13)|({'push':0b11000,'pop':0b11010}[kind]<<8)|(rlist<<4)|(spimm<<2)|2


def micro_ops(word):
    """Architectural register/stack operations, independent of RTL FSM encodings."""
    r=(word>>4)&15;spimm=(word>>2)&3;kind=(word>>8)&31
    if kind not in (24,26) or r<4:return None
    regs=[1]+([8] if r>=5 else [])+([9] if r>=6 else [])+list(range(18, min(26,r+12)))
    if r==15:regs=list(range(18,28))+[1,8,9]
    regs=sorted(regs,reverse=True)
    stack=(16 if r<=7 else 32 if r<=11 else 48 if r<=14 else 64)+16*spimm
    ops=[]
    for i,reg in enumerate(regs):
        if kind==24:
            imm=(-4*(i+1))&4095
            ops.append(((imm>>5)<<25)|(reg<<20)|(2<<15)|(2<<12)|((imm&31)<<7)|0x23)
        else:
            imm=stack-4*(i+1)
            ops.append((imm<<20)|(2<<15)|(2<<12)|(reg<<7)|3)
    imm=(-stack if kind==24 else stack)&4095
    ops.append((imm<<20)|(2<<15)|(2<<7)|0x13)
    return ops


def query_pool(case_id='ibex',split='development',seed=19407):
    c=register()
    if split not in ('development','independent'):raise ValueError('split')
    # Different instruction payloads, pause positions and lengths; no outcome
    # substitution. Independent descriptors are only constructed on explicit use.
    rlist=7 if split=='development' else 9
    offset=0 if split=='development' else 1
    queries=[]
    for index,family in enumerate(('normal','flush_ready','flush_stall','flush_invalid','reset')):
        rows=[]
        def add(n=1,**kw):
            for _ in range(n):rows.append(dict(rst_n=kw.get('rst_n',1),valid=kw.get('valid',0),ready=kw.get('ready',0),flush=kw.get('flush',0),instr=kw.get('instr',0x13)))
        a=instruction('push',rlist,offset);b=instruction('pop',rlist-1,offset)
        add(3,rst_n=0)
        count=1+(seed%2)
        add(count,valid=1,ready=1,instr=a)
        add(1+offset,valid=1,ready=0,instr=a)
        if family=='normal':
            add(len(micro_ops(a))-count,valid=1,ready=1,instr=a)
        elif family=='reset':
            add(rst_n=0,instr=a)
        else:
            add(valid=int(family!='flush_invalid'),ready=int(family=='flush_ready'),flush=1,instr=a)
        add(2,valid=0,ready=0,instr=0x13)
        add(len(micro_ops(b)),valid=1,ready=1,instr=b)
        add(3)
        digest=c.digest(rows)
        queries.append(dict(id='ibex_flush/'+family+'/'+digest[:12],family=family,rows=rows,
            obligations=OBS,dimensions=['trigger','response','window','transaction','exception'],estimated_cost=2,
            constraints=['hold expanded instruction until accepted or canceled','invalid implies not ready','flush represents IF pc_set_i && pc_mux_i==PC_EXC','reset may interrupt expansion'],
            split=split,semantic_key=digest,evidence_visibility='public_development' if split=='development' else 'heldout_after_freeze'))
    return queries


def expanded_header(path,seen=()):
    if path in seen:raise ValueError('include_cycle')
    text=path.read_text()
    base=ROOT/'external/opentitan/hw/ip/prim/rtl'
    return re.sub(r'`include\s+"([^"]+)"',lambda m:expanded_header(base/m[1],(*seen,path)),text)


def sources(folder,fault):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    revision='before' if fault=='primary' else 'after'
    if fault not in ('correct','primary','dev_ready_gate','dev_stall_advance','test_valid_gate','test_reset_disconnect'):
        raise ValueError('unknown_fault')
    text=expanded_header(SOURCE/revision/'ibex_compressed_decoder.sv')
    if fault=='dev_ready_gate':
        text=text.replace('flush_expanded_i ? CmIdle','(flush_expanded_i && id_in_ready_i) ? CmIdle')
    source=(SOURCE/revision/'ibex_pkg.sv').read_text()+'\n'+text
    path=folder/'original_with_expanded_includes.sv';path.write_text(source)
    return [path]


def bench(candidate,rows,fault='correct'):
    decl=['`timescale 1ns/1ps','module tb;','reg clk=0; always #5 clk=~clk;','integer cycle=-1;',
          'reg rst_n=0,valid=0,ready=0,flush=0;reg[31:0]instr=0;wire[31:0]instr_out;wire[1:0]expanded;wire illegal;wire[2:0]state;',
          'reg reset_seen=0;always @(posedge clk) if(rst_n) reset_seen<=1;']
    reset='(rst_n || reset_seen)' if fault=='test_reset_disconnect' else 'rst_n'
    ready="1'b1" if fault=='dev_stall_advance' else 'ready'
    flush='(flush && valid)' if fault=='test_valid_gate' else 'flush'
    # No package type in this TB; default parameter enables Zcmp at both commits.
    ports=f'.clk_i(clk),.rst_ni({reset}),.valid_i(valid),.id_in_ready_i({ready}),.instr_i(instr),.instr_o(instr_out),.is_compressed_o(),.gets_expanded_o(expanded),.illegal_instr_o(illegal)'
    if fault!='primary':ports+=f',.flush_expanded_i({flush})'
    decl.append('ibex_compressed_decoder dut('+ports+');assign state=dut.cm_state_q;')
    for a in candidate:
        op='|=>' if a['timing']=='next_sample' else '|->'
        decl.append(f'''{a['label']}: assert property (@(posedge clk) disable iff(!rst_n) ({a['antecedent']}) {op} ({a['consequent']})) else $display("ASSERT_FAIL {a['label']} cycle=%0d",$sampled(cycle));
assert property (@(posedge clk) disable iff(!rst_n) !({a['antecedent']})) else $display("TRIGGER {a['label']} cycle=%0d",$sampled(cycle));''')
    fields=list(SIGNALS)
    decl.append('initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);')
    for i,row in enumerate(rows):
        decl.append('@(negedge clk);cycle='+str(i)+';'+' '.join(f'{k}={v};' for k,v in row.items()))
        decl.append('@(posedge clk);$display("TRACE cycle=%0d '+' '.join(k+'=%0d' for k in fields)+'",cycle,'+','.join(fields)+');')
    decl.append('@(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule')
    return '\n'.join(decl)


def reference(traces):
    checks=[];unknown=[];ops=None;index=0;tid=-1;previous=None
    def record(row,ob,expect,actual,tx):
        checks.append(dict(cycle=row['cycle'],obligation=ob,passed=expect==actual,expected=expect,actual=actual,transaction=tx))
    for row in traces:
        if not row['rst_n']:
            ops=None;index=0;tid=-1;record(row,'reset_cancel',0,row['state'],row['cycle'])
        else:
            if previous and previous['flush']:
                ops=None;index=0;tid=-1;record(row,'flush_cancel',0,row['state'],previous['cycle'])
            if previous and previous['rst_n'] and previous['valid'] and not previous['ready'] and not previous['flush'] and row['instr']==previous['instr']:
                record(row,'stall_hold',previous['instr_out'],row['instr_out'],tid)
            if row['valid']:
                if ops is None:
                    ops=micro_ops(row['instr']);index=0;tid=row['cycle']
                    if ops is None:unknown.append('unsupported_instruction:'+str(row['cycle']))
                if ops:
                    record(row,'expansion_match',ops[index],row['instr_out'],tid)
                    record(row,'expansion_match',0,row['illegal'],tid)
                    record(row,'expansion_match',2 if row['ready'] and index==len(ops)-1 else 1,row['expanded'],tid)
                    if row['ready']:
                        index+=1
                        if index==len(ops):ops=None;index=0
        previous=row
    return dict(checks=checks,unknown=sorted(set(unknown)))


def evaluate(case_id,candidate,out,queries=None,split='development',fault='primary',cleanup=True):
    c=register()
    return c.evaluate('ibex_flush',candidate,out,queries=query_pool('ibex_flush',split) if queries is None else queries,split=split,fault=fault,cleanup=cleanup)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--family',default='flush_stall')
    a=p.parse_args();case=get_case();queries=[q for q in query_pool() if q['family']==a.family]
    m=evaluate('ibex',case['initial'],a.out,queries)
    print(json.dumps(dict(targets=len(m['targets']),detected=len(m['detected_ids']),unknown=m['critical_unknown'],cost=m['cost'])))
