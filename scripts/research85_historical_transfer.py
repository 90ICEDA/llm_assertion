"""Freeze existing artifacts, then replicate original decoder boundaries locally."""
import argparse
import collections
import json
import random
import re
import shutil
import time
from pathlib import Path
from unittest.mock import patch

import research63_phase_qualified as qualified
import research15_history_ibex54 as compressed
import research64_search_value as accounting

base=qualified.base
ROOT,read,dump,sha=base.ROOT,base.read,base.dump,base.sha
PRIOR=ROOT/'deliverables/research63_independent_20261023_r02'
SEEDS=(8501,8513,8521)


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    ib=out/'ibex166';ib.mkdir()
    for name in ('candidate.json','candidate.sva','source_binding.json','tool_config.json'):
        shutil.copy2(PRIOR/name,ib/name)
    for rev in ('before','after'):shutil.copytree(PRIOR/rev,ib/rev)
    for name,h in read(ib/'source_binding.json')['source_sha256'].items():assert sha(ib/name)==h
    # Read only input encodings from old tests to exclude reuse; no outcome-based selection.
    excluded=set(read(PRIOR/'development_exclusion.json')['words'])
    excluded.update(t['instruction'] for t in read(PRIOR/'independent_cases.json'))
    dump(ib/'excluded_words.json',sorted(excluded))
    comp=out/'ibex54';comp.mkdir()
    historical=read(compressed.OLD/'reproduction.json')
    assert all(sha(ROOT/p)==h for p,h in historical['hashes'].items())
    for rev in ('before','after'):shutil.copytree(compressed.OLD/rev,comp/rev)
    for name in ('source.json','fix.patch'):shutil.copy2(compressed.OLD/name,comp/name)
    shutil.copy2(compressed.OUT/'protocol.json',comp/'source_protocol.json')
    old54={r['instruction']&65535 for p in (compressed.OLD/'boundary_vectors.json',compressed.OUT/'vectors.json') for r in read(p)}
    dump(comp/'excluded_low16.json',sorted(old54))
    dump(out/'protocol.json',dict(seeds=SEEDS,model_calls=0,formal_calls=0,
        ibex166='Unchanged real-model research62 accepted candidate. 96 instruction words per seed, four RV32E/M configurations, first and held phases. Freeze before generation; exclude all recorded lineage development and research63 tests plus earlier seeds in this batch. No edits or acceptance selection.',
        ibex166_rule='Reuse source-qualified research63 r02 rule: OP first and held actual exposure; BRANCH held exposure and first correct triggered; legal controls; no misses, false alarms across all properties, required-untriggered or critical unknown.',
        ibex54='Original before/after compressed decoder. Up to8 distinct remaining low16 encodings per family/seed, without replacement. All engineering properties derived from existing independent encoding oracle, NOT LLM-generated. No parameters in original module.',
        ibex54_rule='Report every predeclared family, remaining pool, actual before-violation/after-satisfaction and reference mismatches. Empty pools remain unexposed, not passed; never recycle old anchors as new evidence.',
        families54=['slli_hint','li_hint','lui_hint','right_shift_hint','legal_control','reserved_control'],
        stopping='Three fixed seeds; no adaptive extension or model calls. Freeze unchanged if failures; any later use for tuning reclassifies entire associated batch as development.',
        scope='Two original historical decoder modules, not full cores. Candidate generalization is not generation success rate; #54 is reproduction transfer only, not either mechanism incremental benefit.',
        git_commit=None,created=time.time()))
    dump(out/'code_versions.json',{p.relative_to(ROOT).as_posix():sha(p) for p in (ROOT/'scripts').glob('*.py')})
    dump(out/'freeze.json',dict(time=time.time(),files={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()}))
    print('SEALED85',len(excluded),'#166 exclusions',len(old54),'#54 exclusions',flush=True)


def verify(out):
    for p,h in read(out/'freeze.json')['files'].items():assert sha(out/p)==h,p
    for p,h in read(out/'code_versions.json').items():assert sha(ROOT/p)==h,p


def family54(word):
    q=word&3;f=word>>13;rd=(word>>7)&31;sh=(word>>2)&31;hi=(word>>12)&1
    if q==2 and f==0 and not hi and (rd==0 or sh==0):return 'slli_hint'
    if q==1 and f==2 and rd==0:return 'li_hint'
    if q==1 and f==3 and rd==0 and (sh or hi):return 'lui_hint'
    if q==1 and f==4 and ((word>>10)&3) in (0,1) and not hi and sh==0:return 'right_shift_hint'
    try:z=compressed.oracle(word)
    except ValueError:return None
    if q==3:return None
    return 'reserved_control' if z['illegal'] else 'legal_control'


def bench54(vectors):
    lines=['module tb; bit clk=0; always #5 clk=~clk; logic [31:0] instr_i,instr_o,expected_decoded; logic is_compressed_o,illegal_instr_o,expected_compressed,expected_illegal; integer sample=-1; ibex_compressed_decoder dut(.*);',
        'assert property (@(posedge clk) (sample>=0) |-> (illegal_instr_o==expected_illegal)) else $display("ASSERT_FAIL legality sample=%0d",sample);',
        'assert property (@(posedge clk) (sample>=0) |-> (is_compressed_o==expected_compressed)) else $display("ASSERT_FAIL compressed sample=%0d",sample);',
        'assert property (@(posedge clk) (sample>=0 && !expected_illegal) |-> (instr_o==expected_decoded)) else $display("ASSERT_FAIL expansion sample=%0d",sample);',
        'always @(posedge clk) if(sample>=0) begin $display("TRIGGER encoding sample=%0d",sample); $display("TRACE sample=%0d instr=%h decoded=%h compressed=%b illegal=%b",sample,instr_i,instr_o,is_compressed_o,illegal_instr_o); end',
        'initial begin $dumpfile("wave.vcd"); $dumpvars(0,tb);']
    for i,v in enumerate(vectors):
        z=compressed.oracle(v['instruction'])
        lines.append(f"@(negedge clk); sample={i}; instr_i=32'h{v['instruction']:08x}; expected_decoded=32'h{z['decoded']:08x}; expected_compressed={z['compressed']}; expected_illegal={z['illegal']};")
    lines.append('@(posedge clk); #1; $display("NATIVE_RUN_COMPLETE"); $finish; end endmodule')
    return '\n'.join(lines)+'\n'


def replay54(out,seed,excluded):
    path=out/'ibex54'/f's{seed}';path.mkdir()
    families=read(out/'protocol.json')['families54'];pool={f:[] for f in families}
    for word in range(65536):
        if word in excluded:continue
        f=family54(word)
        if f:pool[f].append(word)
    rng=random.Random(seed);vs=[]
    for f in families:
        for low in rng.sample(pool[f],min(8,len(pool[f]))):
            vs.append(dict(instruction=(rng.randrange(1,65536)<<16)|low,low16=low,family=f))
            excluded.add(low)
    dump(path/'vectors.json',vs);dump(path/'generation.json',dict(seed=seed,remaining_pool={f:len(pool[f]) for f in families},generated_at=time.time()))
    traces={};native={};audit=[]
    for rev in ('before','after'):
        r=compressed.native.run_native(bench54(vs),path/rev,extra_sources=[out/'ibex54'/rev/n for n in ('ibex_defines.sv','ibex_compressed_decoder.sv')])
        native[rev]=r;traces[rev]=[]
        if r['execution_status']!='completed':continue
        for line in (path/rev/'execute.log').read_text().splitlines():
            if not line.startswith('TRACE '):continue
            z=dict(s.split('=') for s in line.split()[1:]);v=vs[int(z['sample'])]
            assert int(z['instr'],16)==v['instruction']
            expected=compressed.oracle(v['instruction'])
            actual=dict(compressed=int(z['compressed']),illegal=int(z['illegal']),decoded=int(z['decoded'],16))
            bad=[k for k in expected if (k!='decoded' or not expected['illegal']) and expected[k]!=actual[k]]
            traces[rev].append(dict(**v,expected=expected,actual=actual,failures=bad))
        assert len(traces[rev])==len(vs)
        assert sum(len(r['failures']) for r in traces[rev])==len(native[rev]['failures'])
        assert (path/rev/'wave.vcd').stat().st_size>0
    healthy=all(native[v]['compile_status']=='passed' and native[v]['execution_status']=='completed' for v in native)
    for f in families:
        pairs=[(a,b) for a,b in zip(traces['before'],traces['after']) if a['family']==f]
        exposure=sum(bool(a['failures']) and not b['failures'] for a,b in pairs)
        unknown=sum(bool(b['failures']) for a,b in pairs)
        audit.append(dict(family=f,planned=sum(v['family']==f for v in vs),observed=len(pairs),target_exposure=exposure,
            unknown=unknown,status='unexposed' if not pairs else 'unknown' if unknown or not healthy else
                'original_violation_reproduced' if exposure else 'control_satisfied_no_target_exposure'))
    dump(path/'adjudication.json',traces)
    result=dict(seed=seed,healthy=healthy,families=audit,learned_assertions=False,model_calls=0)
    dump(path/'summary.json',result);print('IBEX54',seed,audit,flush=True)
    return result


def run(out):
    verify(out);assert not (out/'run_started.json').exists()
    dump(out/'run_started.json',dict(time=time.time()))
    excluded=set(read(out/'ibex166/excluded_words.json'));ex54=set(read(out/'ibex54/excluded_low16.json'))
    results=[];start=time.perf_counter()
    for seed in SEEDS:
        path=out/'ibex166'/f's{seed}';path.mkdir()
        for name in ('candidate.json','tool_config.json'):shutil.copy2(out/'ibex166'/name,path/name)
        for rev in ('before','after'):shutil.copytree(out/'ibex166'/rev,path/rev)
        txns=base.generate(seed,excluded)
        assert not excluded & {t['instruction'] for t in txns}
        excluded.update(t['instruction'] for t in txns)
        dump(path/'generation.json',dict(seed=seed,generated_at=time.time(),freeze_sha256=sha(out/'freeze.json')))
        dump(path/'independent_cases.json',txns)
        result=base.old.replay(read(path/'candidate.json'),txns,'independent',path/'independent',path,configs=base.CONFIGS)
        if result['healthy']:
            audit=base.native_audit(path,result)
            with patch.object(base.old,'CONFIGS',base.CONFIGS):
                guard=base.guards.all_property_guard(result,{v:read(path/'independent'/v/'result.json') for v in ('before','after')},read(path/'candidate.json'))
            summary=qualified.summarize(result,guard);dump(path/'audit.json',audit)
        else:summary=dict(passed=False,counts=result['counts'],status='native_failure',native_status=result['native_status'])
        dump(path/'summary.json',summary);results.append(dict(case='ibex166',seed=seed,**summary))
        print('IBEX166',seed,summary['passed'],summary['counts'],flush=True)
        results.append(dict(case='ibex54',**replay54(out,seed,ex54)))
    verify(out)
    dump(out/'summary.json',dict(results=results,elapsed_seconds=time.perf_counter()-start,model_calls=0,
        new_model_acceptances=0,independent166_passes=sum(r.get('passed',False) for r in results if r['case']=='ibex166'),
        independent166_denominator=3,models_generation_success_rate=None,
        mechanism_increment='Not identified by this transfer replay. #54 is original-RTL reproduction with engineering properties, not learned-SVA or recovery success.'))
    dump(out/'cost.json',accounting.native_cost(out))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=('prepare','run','verify'))
    ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();globals()[a.action](a.out.resolve())
