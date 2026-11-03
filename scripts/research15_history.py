"""Original Ibex #166 decoder reproduction with independent ISA adjudication.

WSL python3 scripts/research15_history.py prepare|run|report
Original downloaded RTL is never rewritten. No model calls or abstract DUT.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import subprocess

import research_native_runner as native

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/research15_history_20261015_r01'
CONFIGS=[dict(RV32E=0,RV32M=1),dict(RV32E=0,RV32M=0),dict(RV32E=1,RV32M=1)]
read=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
dump=native.dump


def oracle(instruction,new,config):
    """ISA encoding reference independent of RTL and checked assertion text.

    Scope is BRANCH, OP (RV32I/M), and the ADDI NOP used in this experiment.
    New/stalled phase does not change whether an encoding is illegal.
    """
    op=instruction&127;f3=(instruction>>12)&7;f7=(instruction>>25)&127
    if op==0x63:return int(f3 not in (0,1,4,5,6,7))
    if op==0x33:
        return int(not (f7==0 or (f7==0x20 and f3 in (0,5)) or (f7==1 and config['RV32M'])))
    if instruction==0x13:return 0
    raise ValueError('unqualified instruction family')


def prepare():
    assert not (OUT/'protocol.json').exists()
    meta=read(OUT/'ibex166_archived_metadata.json');live=read(OUT/'ibex166_live_pr.json')
    assert live['number']==166 and live['merged'] and live['merge_commit_sha']==meta['merge_commit_sha']
    assert live['body']==meta['body']
    (OUT/'fix.patch').write_text(meta['fix_patch'])
    (OUT/'benchmark_tb_script.sh').write_text(meta['tb_script'])
    (OUT/'benchmark_prepare_script_NOT_EXECUTED.sh').write_text(meta['prepare_script'])
    protocol=dict(case_id='lowRISC/ibex#166',upstream=meta['html_url'],issue='https://github.com/lowRISC/ibex/issues/163',
        before_commit=meta['base']['sha'],after_commit=meta['commits'][0]['sha'],merge_commit=meta['merge_commit_sha'],
        module='ibex_decoder',rtl_policy='Original bytes downloaded from immutable GitHub commit URLs; no source translation or logic edits',
        obligations=[dict(id='illegal_branch_persists',text='BRANCH funct3 010/011 is illegal throughout instruction execution, including instr_new_i=0 stall cycles',source='official PR #166 body; RISC-V branch encodings'),dict(id='op_bit28_illegal',text='Register-register OP encodings with bit28 set are illegal for these historical RV32IM configurations',source='official PR #166 body; RISC-V OP encoding table')],
        legal_stimulus='Decoder interface accepts any instruction bits, including illegal encodings. An instruction is first presented with instr_new_i=1, then held stable with instr_new_i=0 for its remaining execution samples. illegal_c_insn_i=0. These are module-interface stimuli, not a demonstrated full-core fetch/retire protocol.',
        configurations=CONFIGS,seed=202610150166,
        independent_oracle='Python ISA encoding classification in oracle(), not candidate alarm or buggy/fixed waveform difference',
        observation='combinational decoder sampled at positive edge, inputs changed on prior negative edge; decoder has no clock/reset port',
        assertion_origin='handwritten equality to expected independent ISA classification; no LLM-generated SVA',
        holdout_status='New reproduction inputs frozen before execution; no model/candidate selection. Not a frozen learned-assertion generalization experiment.',
        whole_processor_trap='not tested; original HWE-Bench full-core reproducer archived but not executed',
        native_sva=True,formal_proof=False,model_calls=0,
        source_download_attempts=[dict(environment='Windows sandbox',status='socket_access_denied',attempts=5),dict(environment='Windows elevated authorized read-only HTTP',status='success',source_files=4,official_PR_records=1)])
    dump(OUT/'protocol.json',protocol)
    rng=random.Random(protocol['seed']);transactions=[]
    def add(family,word,hold):
        transactions.append(dict(id=len(transactions),family=family,instruction=word,hold_samples=hold))
    add('issue_163_illegal_branch',0x7d10b363,5)
    add('benchmark_illegal_alu',0x1613ac33,5)
    for f3 in range(8):
        for j in range(8):
            # All register indices are below 16 so RV32E does not add ambiguity.
            word=(rng.randrange(16)<<20)|(rng.randrange(16)<<15)|(f3<<12)|0x63
            word|=(rng.randrange(32)<<25)|(rng.randrange(32)<<7)
            add('branch_reserved' if f3 in (2,3) else 'branch_legal',word,rng.randrange(2,7))
    for f3 in range(8):
        for f7 in (0,8,9,0x20,0x28,1):
            word=(f7<<25)|(rng.randrange(16)<<20)|(rng.randrange(16)<<15)|(f3<<12)|(rng.randrange(1,16)<<7)|0x33
            add('op_bit28' if word&(1<<28) else 'op_control',word,rng.randrange(2,7))
    add('nop_control',0x13,3)
    # Specific benchmark ALU uses x24/x26, so RV32E would add an unrelated error;
    # normalize only this NEW stimulus to lower registers, never the DUT source.
    transactions[1]['instruction']=(0x1613ac33&~((31<<7)|(31<<15)|(31<<20)))|(3<<7)|(2<<15)|(1<<20)
    samples=[]
    for txn in transactions:
        for phase in range(txn['hold_samples']):
            samples.append(dict(sample_id=len(samples),transaction_id=txn['id'],phase=phase,instruction=txn['instruction'],instr_new=int(phase==0),family=txn['family'],expected=[oracle(txn['instruction'],phase==0,c) for c in CONFIGS]))
    dump(OUT/'transactions.json',transactions);dump(OUT/'samples.json',samples)
    lines=['module tb;','bit clk=0; always #5 clk=~clk;','logic [31:0] instr; logic instr_new; logic [2:0] illegal,expected; integer sample_id=-1,txn_id=-1,phase=-1;']
    for i,c in enumerate(CONFIGS):
        lines += [f"ibex_decoder #(.RV32E({c['RV32E']}),.RV32M({c['RV32M']})) dut_{i}(.instr_new_i(instr_new),.instr_rdata_i(instr),.illegal_c_insn_i(1'b0),.illegal_insn_o(illegal[{i}]));",
            f'assert property (@(posedge clk) (sample_id>=0) |-> (illegal[{i}]==expected[{i}])) else $display("ASSERT_FAIL isa_{i} sample=%0d txn=%0d phase=%0d",sample_id,txn_id,phase);']
    lines += ['always @(posedge clk) if(sample_id>=0) begin', '$display("TRIGGER isa sample=%0d",sample_id);', '$display("TRACE sample=%0d txn=%0d phase=%0d instr=%h new=%b expected=%b observed=%b",sample_id,txn_id,phase,instr,instr_new,expected,illegal);','end','initial begin $dumpfile("wave.vcd"); $dumpvars(0,tb);']
    for s in samples:
        exp=sum(b<<i for i,b in enumerate(s['expected']))
        lines.append(f"@(negedge clk); sample_id={s['sample_id']}; txn_id={s['transaction_id']}; phase={s['phase']}; instr=32'h{s['instruction']:08x}; instr_new=1'b{s['instr_new']}; expected=3'b{exp:03b};")
    lines += ['@(posedge clk); #1; $display("NATIVE_RUN_COMPLETE"); $finish; end endmodule']
    (OUT/'tb.sv').write_text('\n'.join(lines)+'\n')
    shutil.copy2(Path(__file__),OUT/Path(__file__).name)
    shutil.copy2(Path(native.__file__),OUT/Path(native.__file__).name)
    files=[p for sub in ('before','after') for p in (OUT/sub).glob('*.sv')]+[OUT/n for n in ['protocol.json','transactions.json','samples.json','tb.sv','fix.patch',Path(__file__).name,Path(native.__file__).name]]
    dump(OUT/'freeze.json',{str(p.relative_to(ROOT)):sha(p) for p in files})
    print(json.dumps(dict(transactions=len(transactions),samples=len(samples),configs=len(CONFIGS))))


def guard():
    assert all(sha(ROOT/p)==h for p,h in read(OUT/'freeze.json').items())


def run():
    guard();folder=OUT/'patch_validation';folder.mkdir(exist_ok=False)
    (folder/'rtl').mkdir();shutil.copy2(OUT/'before/ibex_decoder.sv',folder/'rtl/ibex_decoder.sv')
    rec,log=native.command(['git','apply',str(OUT/'fix.patch')],folder,'apply_patch',30)
    match=rec['exit_code']==0 and sha(folder/'rtl/ibex_decoder.sv')==sha(OUT/'after/ibex_decoder.sv')
    dump(folder/'result.json',dict(exact_patch_applies=match,before=sha(OUT/'before/ibex_decoder.sv'),after=sha(OUT/'after/ibex_decoder.sv')))
    assert match
    for revision in ('before','after'):
        r=native.run_native((OUT/'tb.sv').read_text(),OUT/'execution'/revision,extra_sources=[OUT/revision/'ibex_defines.sv',OUT/revision/'ibex_decoder.sv'])
        print(revision,r['compile_status'],r['execution_status'],r['property_status'],flush=True)


def report():
    guard();samples=read(OUT/'samples.json');results=[];witnesses=[]
    for revision in ('before','after'):
        p=OUT/'execution'/revision;r=read(p/'result.json');observations=[]
        if r['execution_status']=='completed':
            for line in (p/'execute.log').read_text().splitlines():
                if not line.startswith('TRACE '):continue
                f=dict(z.split('=') for z in line.split()[1:]);sid=int(f['sample']);s=samples[sid]
                assert int(f['instr'],16)==s['instruction'] and int(f['new'])==s['instr_new']
                observed=int(f['observed'],2)
                for i,c in enumerate(CONFIGS):
                    expect=oracle(s['instruction'],s['instr_new'],c);actual=(observed>>i)&1
                    observations.append(dict(**s,configuration=i,oracle_expected=expect,observed=actual,violation=actual!=expect))
            assert len(observations)==len(samples)*len(CONFIGS)
        failures=[z for z in observations if z['violation']]
        assert r['execution_status']!='completed' or len(failures)==len(r.get('failures',[]))
        dump(p/'independent_adjudication.json',observations)
        by_family={f:dict(checks=sum(z['family']==f for z in observations),violations=sum(z['family']==f for z in failures)) for f in sorted({s['family'] for s in samples})}
        results.append(dict(revision=revision,compile_status=r['compile_status'],execution_status=r['execution_status'],native_property_status=r['property_status'],checks=len(observations),violations=len(failures),transactions_with_violation=len({z['transaction_id'] for z in failures}),family_results=by_family,compile_wall_seconds=r['compile']['wall_seconds'],simulation_wall_seconds=r.get('execute',{}).get('wall_seconds'),version=r['tool_version']))
    before=read(OUT/'execution/before/independent_adjudication.json');after=read(OUT/'execution/after/independent_adjudication.json')
    for b,a in zip(before,after):
        assert (b['sample_id'],b['configuration'])==(a['sample_id'],a['configuration'])
        if b['violation'] and not a['violation']:
            witnesses.append(dict(sample_id=b['sample_id'],transaction_id=b['transaction_id'],phase=b['phase'],instruction=b['instruction'],configuration=b['configuration'],obligation='illegal_branch_persists' if b['instruction']&127==0x63 else 'op_bit28_illegal',expected=b['oracle_expected'],before=b['observed'],after=a['observed']))
    dump(OUT/'repair_witnesses.json',witnesses)
    summary=dict(case_id='lowRISC/ibex#166',results=results,admitted_original_module=all(z['execution_status']=='completed' for z in results) and results[0]['violations']>0 and results[1]['violations']==0,repair_witnesses=len(witnesses),covered_repair_obligations=sorted({z['obligation'] for z in witnesses}),full_core_trap_reproduction=False,abstract_model=False,model_calls=0,formal_calls=0,source_sha256={str(p.relative_to(OUT)):sha(p) for rev in ('before','after') for p in (OUT/rev).glob('*.sv')})
    dump(OUT/'summary.json',summary)
    lines=['# Original historical Ibex #166 reproduction','', 'The original downloaded decoder and package are compiled unchanged. A handwritten native SVA checks against frozen independent ISA classifications; a separate Python oracle adjudicates actual port traces. No LLM-generated assertion or full-core trap reproduction is claimed.', '', '| Revision | Compile | Execution | Checks | Violations | Transactions with violation |','|---|---|---|---:|---:|---:|']
    for z in results:lines.append(f"| {z['revision']} | {z['compile_status']} | {z['execution_status']} | {z['checks']} | {z['violations']} | {z['transactions_with_violation']} |")
    lines += ['',f"Repair witnesses: {len(witnesses)} sample/config observations; these are not independent bugs. Both obligations: {summary['covered_repair_obligations']}.", '', 'The native assertions are deliberately simple ISA-output checks. Simulation within these inputs is not formal proof. Original HWE-Bench full-core script is archived, not run. Zero model calls. Protocol, exact commands, tool version, raw logs, VCD, source hashes, transaction IDs and independent judgments are retained.', '', 'Sources: [PR #166](https://github.com/lowRISC/ibex/pull/166), [issue #163](https://github.com/lowRISC/ibex/issues/163). Before c96ece04296c3c69df578d760aa8a66f9b886fef; fixed 3bcbb50630a7cb0278623a8a1f5d262e0220dd86. Original patch application exactly reproduces fixed decoder bytes.', '', 'Reproduction: `python3 scripts/research15_history.py prepare`, then `run`, then `report` in WSL after saving the pinned source downloads. Existing runs are exclusive. See protocol.json for all parameters and source constraints.']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run','report']);a=ap.parse_args();globals()[a.action]()
