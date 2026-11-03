"""Reproduce a real historical fix using immutable before/after source downloads.

Extract the saved benchmark testbench verbatim; do not run its destructive
container bootstrap. Additional port-level boundary checks are a separate cohort.
"""
import argparse
import json
import re
import shutil
from pathlib import Path
import run_repair_contract as e


def main(run):
    root=e.ROOT/'deliverables'/run/'historical_screening/ibex_54'
    old=e.ROOT/'deliverables/obligation_evidence_20261013_r01/historical_screening/ibex_54'
    (root/'execution').mkdir(exist_ok=False)
    for name in ('source.json','fix.patch','test.patch','tb_script.sh','prepare_script.sh'):
        shutil.copy2(old/name,root/name)
    text=(old/'tb_script.sh').read_text()
    tb=text.split("<<'EOF'\n",1)[1].split('\nEOF',1)[0]+'\n'
    (root/'benchmark_tb.sv').write_text(tb)
    vectors=[]
    def add(family, instruction, illegal, decoded=None):
        vectors.append(dict(family=family,instruction=instruction,illegal=illegal,compressed=1,decoded=decoded))
    # Public architectural encodings: C.LI x0 sign-extends its immediate into
    # ADDI x0,x0,imm; C.LUI x0 nonzero immediate is a LUI x0 hint.
    for imm in range(64):
        ci=(2<<13)|((imm>>5)<<12)|((imm&31)<<2)|1
        si=imm if imm<32 else imm-64
        add('c_li_x0',ci,0,((si&4095)<<20)|0x13)
        ci=(3<<13)|((imm>>5)<<12)|((imm&31)<<2)|1
        if imm:
            add('c_lui_x0_nonzero',ci,0,((si&0xfffff)<<12)|0x37)
        else: add('reserved_c_lui_zero',ci,1)
    for reg in range(8):
        for arithmetic in (0,1):
            ci=(4<<13)|(arithmetic<<10)|(reg<<7)|1
            rd=reg+8
            add('c_srai_zero' if arithmetic else 'c_srli_zero',ci,0,
                (arithmetic<<30)|(rd<<15)|(5<<12)|(rd<<7)|0x13)
            add('reserved_rv32_shift_high',ci|(1<<12),1)
    for rd in range(1,32):
        ci=(rd<<7)|2
        add('c_slli_zero',ci,0,(rd<<15)|(1<<12)|(rd<<7)|0x13)
        add('reserved_rv32_slli_high',ci|(1<<12),1)
    # A normal compressed arithmetic control and the original issue encoding.
    add('issue_0x7065',0x7065,0,0xffff9000|0x37)
    e.dump(root/'boundary_vectors.json',vectors)
    lines=['module tb; reg [31:0] instr_i; wire [31:0] instr_o; wire is_compressed_o,illegal_instr_o;',
           'integer errors=0; ibex_compressed_decoder dut(.*); initial begin',
           '$dumpfile("wave.vcd"); $dumpvars(0,tb);']
    for i,v in enumerate(vectors):
        expr=f"illegal_instr_o !== 1'b{v['illegal']} || is_compressed_o !== 1'b1"
        if v['decoded'] is not None:expr+=f" || instr_o !== 32'h{v['decoded']:08x}"
        lines += [f"instr_i=32'h{v['instruction']:08x}; #1;",
            f'$display("TRACE {i} input=%h decoded=%h compressed=%b illegal=%b",instr_i,instr_o,is_compressed_o,illegal_instr_o);',
            f'if ({expr}) begin errors=errors+1; $display("BOUNDARY_FAIL {i}"); end']
    lines+=['$display("BOUNDARY_ERRORS %0d",errors); if(errors) $fatal(1,"boundary checks"); $finish; end endmodule']
    (root/'boundary_tb.sv').write_text('\n'.join(lines)+'\n')
    result=[]
    for revision in ('before','after'):
        for cohort in ('benchmark','boundary'):
            folder=root/'execution'/revision/cohort;folder.mkdir(parents=True)
            for name in ('ibex_defines.sv','ibex_compressed_decoder.sv'):
                shutil.copy2(root/revision/name,folder/name)
            shutil.copy2(root/(cohort+'_tb.sv'),folder/'tb.sv')
            b=e.command(['iverilog','-g2012','-s','tb','-o','sim.out','ibex_defines.sv','ibex_compressed_decoder.sv','tb.sv'],folder,'compile')
            s=e.command(['vvp','sim.out'],folder,'simulate') if b['status']=='ok' else None
            r=dict(revision=revision,cohort=cohort,compile=b,simulate=s,
                   status=s['status'] if s else b['status'],run=e.rel(folder))
            if s:
                out=(folder/'simulate.stdout').read_text()
                r['failed_checks']=len(re.findall(r'CHECK_FAIL|BOUNDARY_FAIL',out))
                r['passed']=s['status']=='ok' and ('TB_PASS' in out if cohort=='benchmark' else 'BOUNDARY_ERRORS 0' in out)
            result.append(r)
            (folder/'reproduce.sh').write_text('#!/bin/sh\nset -eu\ncd "'+str(folder)+'"\niverilog -g2012 -s tb -o sim.out ibex_defines.sv ibex_compressed_decoder.sv tb.sv\nvvp sim.out\n')
    source=e.read(root/'source.json')
    admitted=all(r['compile']['status']=='ok' and (r.get('passed') if r['revision']=='after' else r.get('failed_checks',0)>0) for r in result)
    e.dump(root/'reproduction.json',dict(source=source,results=result,admitted=admitted,
        actual_environment='WSL Ubuntu, Icarus 12.0; original benchmark SV body and source bytes unchanged; container paths/build wrapper adapted',
        original_test_scope='HWE-Bench supplied regression, not claimed to be an upstream test at the time of repair',
        boundary_count=len(vectors),boundary_basis=['https://github.com/lowRISC/ibex/issues/51','https://github.com/lowRISC/ibex/pull/54','https://docs.riscv.org/reference/isa/unpriv/c-st-ext.html'],
        generator_visible=False,stage3_inclusion=False,reset='combinational decoder: no clock or reset',
        limitation='One module and targeted legal/illegal encoding families; not full processor or entire ISA verification; not evidence of assertion refinement benefit',
        hashes={e.rel(p):e.sha(p) for p in [root/'benchmark_tb.sv',root/'boundary_tb.sv',root/'boundary_vectors.json',root/'fix.patch',*root.glob('before/*.sv'),*root.glob('after/*.sv')]}))
    print(json.dumps(dict(admitted=admitted,boundary_count=len(vectors),results=[{k:r.get(k) for k in ('revision','cohort','passed','failed_checks')} for r in result])))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);main(p.parse_args().run)
