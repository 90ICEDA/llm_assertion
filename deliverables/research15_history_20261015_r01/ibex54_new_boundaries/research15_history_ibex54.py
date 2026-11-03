"""New Ibex #54 encoding boundary replay; old vectors remain development anchors.

python3 scripts/research15_history_ibex54.py prepare|run|report
No model calls, no RTL rewriting, no learned-assertion holdout claim.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import random
import shutil
import research_native_runner as native

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/research15_history_20261015_r01/ibex54_new_boundaries'
OLD=ROOT/'deliverables/obligation_evidence_20261013_r02/historical_screening/ibex_54'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
dump=native.dump


def oracle(word):
    if word&3==3:return dict(compressed=0,illegal=0,decoded=word)
    ci=word&65535;q=ci&3;f3=ci>>13;rd=(ci>>7)&31;sh=(ci>>2)&31;hi=(ci>>12)&1;imm=sh+(hi<<5);signed=imm if imm<32 else imm-64
    if q==2 and f3==0:
        return dict(compressed=1,illegal=hi,decoded=(sh<<20)|(rd<<15)|(1<<12)|(rd<<7)|0x13)
    if q==1 and f3==2:
        return dict(compressed=1,illegal=0,decoded=((signed&4095)<<20)|(rd<<7)|0x13)
    if q==1 and f3==3 and rd!=2:
        return dict(compressed=1,illegal=int(imm==0),decoded=((signed&0xfffff)<<12)|(rd<<7)|0x37)
    if q==1 and f3==4 and ((ci>>10)&3) in (0,1):
        arithmetic=(ci>>10)&1;rd=8+((ci>>7)&7)
        return dict(compressed=1,illegal=hi,decoded=(arithmetic<<30)|(sh<<20)|(rd<<15)|(5<<12)|(rd<<7)|0x13)
    raise ValueError(f'unknown encoding {word:08x}')


def prepare():
    OUT.mkdir(parents=True,exist_ok=False)
    historical=read(OLD/'reproduction.json')
    assert all(sha(ROOT/p)==h for p,h in historical['hashes'].items())
    for rev in ('before','after'):shutil.copytree(OLD/rev,OUT/rev)
    for name in ('source.json','downloads_retry.json','fix.patch'):shutil.copy2(OLD/name,OUT/('prior_'+name))
    oldlow={z['instruction']&65535 for z in read(OLD/'boundary_vectors.json')}
    anchors=[0x4005,0x7065,0x8081,0x8481,0x0082];oldlow.update(anchors)
    rng=random.Random(202610150054);vectors=[];used=set()
    def add(family,ci,cohort='new_boundary'):
        if ci in used:return
        if cohort=='new_boundary' and ci&3!=3 and ci in oldlow:return
        used.add(ci)
        word=ci if ci&3==3 or cohort=='old_anchor' else (rng.randrange(1,65536)<<16)|ci
        vectors.append(dict(id=len(vectors),cohort=cohort,family=family,instruction=word,low16=ci&65535,expected=oracle(word),novel_low16_vs_prior=(ci&3==3 or (ci&65535) not in oldlow)))
    for sh in range(32):add('new_c_slli_x0_hint',(sh<<2)|2)
    for rd in (1,2,15,31):
        for sh in (1,2,15,31):add('legal_slli',(rd<<7)|(sh<<2)|2)
        for imm in (0,1,31,32,63):add('legal_li',(2<<13)|((imm>>5)<<12)|(rd<<7)|((imm&31)<<2)|1)
    for rd in (1,3,15,31):
        for imm in (0,1,31,32,63):add('lui_zero_reserved' if imm==0 else 'legal_lui',(3<<13)|((imm>>5)<<12)|(rd<<7)|((imm&31)<<2)|1)
    for arithmetic in (0,1):
        for rp in (0,1,7):
            for sh in (1,7,31):add('legal_srai' if arithmetic else 'legal_srli',(4<<13)|(arithmetic<<10)|(rp<<7)|(sh<<2)|1)
    for rd in (0,1,15,31):
        for sh in (0,1,31):add('rv32_high_shift_reserved',(1<<12)|(rd<<7)|(sh<<2)|2)
    for word in (0x13,0x123456b7,0x00008067,0x00100073):add('uncompressed_passthrough',word)
    for word in anchors:add('original_repair_anchor',word,'old_anchor')
    assert len([v for v in vectors if v['family']=='new_c_slli_x0_hint'])==32
    dump(OUT/'vectors.json',vectors)
    dump(OUT/'protocol.json',dict(case_id='lowRISC/ibex#54',prior_source_manifest_verified=True,
        before_commit='cd15ce88beba8ed8496f414af361f664764f47e2',after_commit='5319734180ac4844e43d31ad19dc108aac503037',fix_commit='687952e42f3eff68348770ae0c55bc5c0f036d3e',
        source='https://github.com/lowRISC/ibex/pull/54',spec='https://riscv.github.io/riscv-isa-manual/snapshot/spec/',
        reference_rule='C.SLLI rd=x0 or shamt=0 are HINTs; RV32 shamt[5]=1 is reserved for custom extensions, not enabled in this fixed historical decoder.',
        legal_input='Any instruction word is permitted at the combinational decoder input; reserved encodings must set illegal, uncompressed words pass through this decoder and are not certified full-ISA legal.',
        parameters='Original module has no parameters; fixed RV32 historical decoder. No invented parameter sweep.',
        novelty='New compressed inputs differ in their semantic low16 encoding from the 223 old boundary records and 5 original benchmark encodings. Random upper16 is not counted as additional novelty.',
        new_boundary_count=sum(v['cohort']=='new_boundary' for v in vectors),old_anchor_count=sum(v['cohort']=='old_anchor' for v in vectors),seed=202610150054,
        split='Old anchors are development. New vectors are frozen before replay, validating engineering properties only; not independent validation of LLM-generated assertions.',
        native_assertion_origin='Handwritten properties derived from independent encoding oracle, not model output',formal_proof=False,model_calls=0))
    lines=['module tb; bit clk=0; always #5 clk=~clk; logic [31:0] instr_i,instr_o,expected_decoded; logic is_compressed_o,illegal_instr_o,expected_compressed,expected_illegal; integer sample=-1; ibex_compressed_decoder dut(.*);',
        'assert property (@(posedge clk) (sample>=0) |-> (illegal_instr_o==expected_illegal)) else $display("ASSERT_FAIL legality sample=%0d",sample);',
        'assert property (@(posedge clk) (sample>=0) |-> (is_compressed_o==expected_compressed)) else $display("ASSERT_FAIL compressed sample=%0d",sample);',
        'assert property (@(posedge clk) (sample>=0 && !expected_illegal) |-> (instr_o==expected_decoded)) else $display("ASSERT_FAIL expansion sample=%0d",sample);',
        'always @(posedge clk) if(sample>=0) begin $display("TRIGGER encoding sample=%0d",sample); $display("TRACE sample=%0d instr=%h decoded=%h compressed=%b illegal=%b",sample,instr_i,instr_o,is_compressed_o,illegal_instr_o); end',
        'initial begin $dumpfile("wave.vcd"); $dumpvars(0,tb);']
    for v in vectors:
        z=v['expected'];lines.append(f"@(negedge clk); sample={v['id']}; instr_i=32'h{v['instruction']:08x}; expected_decoded=32'h{z['decoded']:08x}; expected_compressed={z['compressed']}; expected_illegal={z['illegal']};")
    lines.append('@(posedge clk); #1; $display("NATIVE_RUN_COMPLETE"); $finish; end endmodule')
    (OUT/'tb.sv').write_text('\n'.join(lines)+'\n');shutil.copy2(Path(__file__),OUT/Path(__file__).name)
    frozen=[p for p in OUT.rglob('*') if p.is_file()]
    dump(OUT/'freeze.json',{str(p.relative_to(ROOT)):sha(p) for p in frozen})
    print(json.dumps(dict(vectors=len(vectors),new=sum(v['cohort']=='new_boundary' for v in vectors),anchors=5)))


def guard():assert all(sha(ROOT/p)==h for p,h in read(OUT/'freeze.json').items())


def run():
    guard()
    for rev in ('before','after'):
        r=native.run_native((OUT/'tb.sv').read_text(),OUT/'execution'/rev,extra_sources=[OUT/rev/'ibex_defines.sv',OUT/rev/'ibex_compressed_decoder.sv'])
        print(rev,r['compile_status'],r['execution_status'],r['property_status'],flush=True)


def report():
    guard();vectors=read(OUT/'vectors.json');rows=[]
    for rev in ('before','after'):
        p=OUT/'execution'/rev;r=read(p/'result.json');judgments=[]
        for line in (p/'execute.log').read_text().splitlines():
            if not line.startswith('TRACE '):continue
            z=dict(s.split('=') for s in line.split()[1:]);v=vectors[int(z['sample'])];expected=oracle(v['instruction']);actual=dict(compressed=int(z['compressed']),illegal=int(z['illegal']),decoded=int(z['decoded'],16))
            assert int(z['instr'],16)==v['instruction']
            failures=[k for k in expected if (k!='decoded' or not expected['illegal']) and expected[k]!=actual[k]]
            judgments.append(dict(**v,actual=actual,failures=failures))
        assert len(judgments)==len(vectors)
        assert sum(len(j['failures']) for j in judgments)==len(r['failures'])
        dump(p/'independent_adjudication.json',judgments)
        for cohort in ('new_boundary','old_anchor'):
            js=[j for j in judgments if j['cohort']==cohort]
            rows.append(dict(revision=rev,cohort=cohort,vectors=len(js),violating_vectors=sum(bool(j['failures']) for j in js),failures=sum(len(j['failures']) for j in js),by_family={f:dict(vectors=sum(j['family']==f for j in js),violating_vectors=sum(j['family']==f and bool(j['failures']) for j in js)) for f in sorted({j['family'] for j in js})},compile_status=r['compile_status'],execution_status=r['execution_status']))
    dump(OUT/'summary.json',dict(results=rows,source_module_original=True,abstract_model=False,model_calls=0,formal_calls=0,native_SVA=True,learned_assertion_holdout=False,new_parameter_configurations=0))
    (OUT/'README.md').write_text('# Ibex #54 new encoding boundaries\n\nNew low16 encodings are frozen before original-RTL replay, separately from five old development anchors. The original module has no parameters. This validates handwritten engineering properties with native SVA and a separate encoding oracle; it is not independent validation of learned assertions.\n\n'+json.dumps(rows,indent=2)+'\n\nSources and exact original commits are in protocol.json; commands, native logs, waves and independent per-vector judgments are under execution/. Run `python3 scripts/research15_history_ibex54.py prepare`, `run`, `report` in WSL. Existing output is exclusive.\n')
    print(json.dumps(rows),flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run','report']);a=ap.parse_args();globals()[a.action]()
