"""Bounded original-RTL history qualification, no model calls or source repairs."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import urllib.request
import research_native_runner as native
import research15_history_ibex54 as ibex

ROOT=native.ROOT
LOCK=ROOT/'deliverables/research159_history_screen_20261028_r01/population_lock.json'
REPO=ROOT/'deliverables/research155_stat_history_20261027_r01/upstream.git'
FIXES={'axis_adapter_keep':'c1c3dc0b66e98a186878b32a4d65cdcd00eaa358','axis_fifo_pause':'e493c6cdb4fd20939b7b9a613e9ab6fd7395ada2'}
dump=native.dump
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','--git-dir='+str(REPO),*args])
def rel(p):return Path(p).relative_to(ROOT).as_posix()


def vectors54():
    rows=[]
    for f in ('li_hint','lui_hint','slli_hint','srli_hint','srai_hint','legal_slli','reserved_slli'):
        for i in (0,1,7,31):
            if f=='li_hint':w=(2<<13)|(i<<2)|1
            elif f=='lui_hint':w=(3<<13)|((i+1 if i<31 else 31)<<2)|1
            elif f=='slli_hint':w=(i<<2)|2
            elif f=='srli_hint':w=(4<<13)|((i%8)<<7)|1
            elif f=='srai_hint':w=(4<<13)|(1<<10)|((i%8)<<7)|1
            elif f=='legal_slli':w=(3<<7)|((i or 1)<<2)|2
            else:w=(1<<12)|(3<<7)|(i<<2)|2
            rows.append(dict(family=f,instruction=w,expected=ibex.oracle(w)))
    rows.append(dict(family='passthrough',instruction=0x13,expected=ibex.oracle(0x13)))
    return rows


def axis_rows(kind):
    rows=[]
    families=('control','ignored_keep_zero','ignored_keep_alternating','reset_cancel') if kind=='adapter' else ('control','pause_first_stall','pause_during_frame','reset_cancel')
    for trial,family in enumerate(families):
        for t in range(40):
            rst=int(t<2 or (family=='reset_cancel' and t in (9,10)))
            valid=int(3<=t<=6)
            data=(trial*32+t-2)&255
            last=int(t in (4,6))
            keep=0 if family=='ignored_keep_zero' else int(t%2==0) if family=='ignored_keep_alternating' else 1
            ready=int(t>=12 and t%4!=0)
            pause=0
            if family=='pause_first_stall':pause=int(8<=t<18)
            elif family=='pause_during_frame':ready=int(t>=8 and t%4!=3);pause=int(9<=t<18)
            rows.append(dict(cycle=len(rows),trial=trial,family=family,phase=t,rst=rst,sv=valid,sd=data,sk=keep,sl=last,mr=ready,pause=pause))
    return rows


def axis_tb(kind,param,rows):
    mw=param if kind=='adapter' else 8
    decl=['module tb; bit clk=0;always #5 clk=~clk;bit rst=1; integer cycle=-1;',
        'bit [7:0] s_axis_tdata=0; bit [0:0] s_axis_tkeep=1;bit s_axis_tvalid=0,s_axis_tlast=0;wire s_axis_tready;',
        'bit [7:0] s_axis_tid=0,s_axis_tdest=0;bit s_axis_tuser=0;',
        f'wire [{mw-1}:0] m_axis_tdata;wire [{mw//8-1}:0] m_axis_tkeep;wire m_axis_tvalid,m_axis_tlast;bit m_axis_tready=0;',
        'wire [7:0] m_axis_tid,m_axis_tdest;wire m_axis_tuser;bit pause_req=0;wire pause_ack;']
    if kind=='adapter':
        decl.append(f'axis_adapter #(.S_DATA_WIDTH(8),.S_KEEP_ENABLE(0),.S_KEEP_WIDTH(1),.M_DATA_WIDTH({mw}),.M_KEEP_ENABLE(1),.M_KEEP_WIDTH({mw//8})) dut(.*);')
        decl.append('assign pause_ack=0;')
    else:
        decl.extend(['wire [2:0] status_depth,status_depth_commit;wire status_overflow,status_bad_frame,status_good_frame;',
            f'axis_fifo #(.DEPTH(4),.DATA_WIDTH(8),.KEEP_ENABLE(0),.KEEP_WIDTH(1),.RAM_PIPELINE({param}),.FRAME_FIFO(0),.PAUSE_ENABLE(1),.FRAME_PAUSE(1)) dut(.*);'])
    decl.extend([
        'hold_valid: assert property (@(posedge clk) disable iff(rst) (m_axis_tvalid && !m_axis_tready) |=> m_axis_tvalid) else $display("ASSERT_FAIL hold_valid cycle=%0d",$sampled(cycle));',
        'hold_payload: assert property (@(posedge clk) disable iff(rst) (m_axis_tvalid && !m_axis_tready) |=> $stable({m_axis_tdata,m_axis_tkeep,m_axis_tlast})) else $display("ASSERT_FAIL hold_payload cycle=%0d",$sampled(cycle));',
        'always @(posedge clk) if(cycle>=0 && !rst && m_axis_tvalid && !m_axis_tready) $display("TRIGGER hold cycle=%0d",cycle);',
        'initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);'])
    for r in rows:
        decl.extend([f"@(negedge clk);cycle={r['cycle']};rst={r['rst']};s_axis_tvalid={r['sv']};s_axis_tdata={r['sd']};s_axis_tkeep={r['sk']};s_axis_tlast={r['sl']};m_axis_tready={r['mr']};pause_req={r['pause']};",
            '@(posedge clk);$display("TRACE cycle=%0d rst=%0d sv=%0d sr=%0d sd=%0d sk=%0d sl=%0d mv=%0d mr=%0d md=%0d mk=%0d ml=%0d pause=%0d ack=%0d",cycle,rst,s_axis_tvalid,s_axis_tready,s_axis_tdata,s_axis_tkeep,s_axis_tlast,m_axis_tvalid,m_axis_tready,m_axis_tdata,m_axis_tkeep,m_axis_tlast,pause_req,pause_ack);'])
    return '\n'.join(decl+['@(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule'])


def tb54(vectors):
    lines=['module tb;bit clk=0;always #5 clk=~clk;logic [31:0] instr_i,instr_o;logic is_compressed_o,illegal_instr_o;integer sample=-1;logic ei,ec;logic [31:0] ed;ibex_compressed_decoder dut(.*);',
        'legality: assert property (@(posedge clk) sample>=0 |-> illegal_instr_o==ei) else $display("ASSERT_FAIL legality sample=%0d",$sampled(sample));',
        'expansion: assert property (@(posedge clk) (sample>=0 && !ei) |-> instr_o==ed) else $display("ASSERT_FAIL expansion sample=%0d",$sampled(sample));',
        'compressed: assert property (@(posedge clk) sample>=0 |-> is_compressed_o==ec) else $display("ASSERT_FAIL compressed sample=%0d",$sampled(sample));',
        'initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);']
    for i,v in enumerate(vectors):
        e=v['expected'];lines.extend([f"@(negedge clk);sample={i};instr_i=32'h{v['instruction']:08x};ei={e['illegal']};ec={e['compressed']};ed=32'h{e['decoded']:08x};",
            '@(posedge clk);$display("TRIGGER encoding sample=%0d",sample);$display("TRACE sample=%0d instr=%0d decoded=%0d compressed=%0d illegal=%0d",sample,instr_i,instr_o,is_compressed_o,illegal_instr_o);'])
    return '\n'.join(lines+['@(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule'])


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);shutil.copy2(LOCK,out/'population_lock.json');sources=[];downloads=[]
    for case,fix in FIXES.items():
        module='axis_adapter' if case=='axis_adapter_keep' else 'axis_fifo'
        parent=git('rev-parse',fix+'^').decode().strip()
        for revision,commit in [('before',parent),('after',fix)]:
            folder=out/case/revision;folder.mkdir(parents=True)
            for f in ('rtl/'+module+'.v','README.md','tb/'+module+'/test_'+module+'.py'):
                dest=folder/Path(f).name;dest.write_bytes(git('show',commit+':'+f))
                sources.append(dict(case=case,revision=revision,commit=commit,source_path=f,path=rel(dest),sha256=sha(dest),exact_git_blob=True))
        (out/case/'fix.patch').write_bytes(git('show','--format=fuller',fix,'--','rtl/'+module+'.v'))
    # Existing original decoder files are reverified against immutable public URLs.
    for revision,commit in [('before','cd15ce88beba8ed8496f414af361f664764f47e2'),('after','5319734180ac4844e43d31ad19dc108aac503037')]:
        folder=out/'ibex54'/revision;folder.mkdir(parents=True)
        for name in ('ibex_compressed_decoder.sv','ibex_defines.sv'):
            old=ibex.OLD/revision/name;dest=folder/name;shutil.copy2(old,dest)
            url=f'https://raw.githubusercontent.com/lowRISC/ibex/{commit}/rtl/{name}'
            record=dict(url=url,local_sha256=sha(dest),status='unknown',retries=0)
            try:
                with urllib.request.urlopen(url,timeout=60) as r:data=r.read()
                record.update(status='verified' if data==dest.read_bytes() else 'mismatch',remote_sha256=hashlib.sha256(data).hexdigest())
            except Exception as e:record.update(error=type(e).__name__+':'+str(e))
            downloads.append(record);sources.append(dict(case='ibex54',revision=revision,commit=commit,path=rel(dest),sha256=sha(dest),immutable_url_verification=record['status']))
        print('SOURCE159 ibex54',revision,downloads[-2:],flush=True)
    shutil.copy2(ibex.OLD/'fix.patch',out/'ibex54/fix.patch')
    shutil.copy2(ibex.OLD/'source.json',out/'ibex54/archived_source.json')
    # Verify exact patch relation in a new copy, never modify the archived originals.
    patchroot=out/'ibex54/patch_validation';(patchroot/'rtl').mkdir(parents=True)
    shutil.copy2(out/'ibex54/before/ibex_compressed_decoder.sv',patchroot/'rtl/ibex_compressed_decoder.sv')
    result,log=native.command(['git','apply',str(out/'ibex54/fix.patch')],patchroot,'apply',30)
    patch_match=result['exit_code']==0 and sha(patchroot/'rtl/ibex_compressed_decoder.sv')==sha(out/'ibex54/after/ibex_compressed_decoder.sv')
    dump(out/'source_manifest.json',dict(sources=sources,downloads=downloads,ibex_patch_exact=patch_match))
    vectors=vectors54();dump(out/'ibex54/vectors.json',vectors);(out/'ibex54/tb.sv').write_text(tb54(vectors))
    for case,kind,params in [('axis_adapter_keep','adapter',[8,32]),('axis_fifo_pause','fifo',[0,1])]:
        rows=axis_rows(kind);dump(out/case/'stimuli.json',rows)
        for p in params:(out/case/f'tb_{p}.sv').write_text(axis_tb(kind,p,rows))
    dump(out/'scope.json',dict(
        axis_adapter_keep=dict(configs='8->8 and 8->32, S_KEEP_ENABLE=0, M_KEEP_ENABLE=1, byte size8',
            contract='Input keep is ignored when disabled (pinned parameter documentation); each accepted input byte and frame boundary preserved on accepted output, legal source held through stall; output valid/payload stable during backpressure.',
            public='ignored_keep_zero / ignored_keep_alternating',history='control and reset_cancel',excluded='No downsize or arbitrary byte size; no preexisting model candidate is inferred.'),
        axis_fifo_pause=dict(configs='Depth4, RAM_PIPELINE0/1, FRAME_FIFO0, PAUSE_ENABLE1, FRAME_PAUSE1, width8',
            contract='Pause between frames; already presented output valid and payload remain stable until handshake except reset. Accepted data/order preserved, reset cancels pending queue. No exact-cycle pause_ack latency claim.',
            public='pause_first_stall',history='control, pause_during_frame, reset_cancel',excluded='Async FIFO touched by same commit is not executed; no extrapolation to async or all depths.'),
        ibex54=dict(configs='Original combinational RV32 compressed decoder, no parameters',
            contract='Pinned PR54/51: compressed HINTs decode as base HINTs, not illegal; independently derive encoding expansions. Reserved high shift bit remains illegal in this historic configuration.',
            public='li_hint and lui_hint',history='slli_hint,srli_hint,srai_hint,legal_slli,reserved_slli,passthrough',excluded='No whole core, no new independent holdout; selected original inputs may repeat old development vectors.'),
        candidate_policy='Handwritten oracle/SVA diagnostics only; no existing generated candidate for these new mechanisms is presumed. Reproduction admission and pilot admission are separate. Stop if qualified editable partial baseline+frontend+meaningful non-whitelist discrimination is not actually established.',
        max_compiles=10,max_executions=10,model_calls=0,formal_calls=0,dataset='development qualification'))
    dump(out/'code_bindings.json',{rel(p):sha(p) for p in (Path(__file__),Path(native.__file__),Path(ibex.__file__))})
    dump(out/'seal.json',{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file()})
    print('PREPARED159 sources/stimuli/scopes, ten original native runs maximum',flush=True)


def verify(prep):
    for n,h in read(prep/'seal.json').items():assert sha(prep/n)==h,n
    for n,h in read(prep/'code_bindings.json').items():assert sha(ROOT/n)==h,n


def trace(folder):
    return [{k:int(v) for k,v in (s.split('=') for s in line.split()[1:])} for line in (folder/'execute.log').read_text().splitlines() if line.startswith('TRACE ')]


def oracle_axis(values,stim,mwidth):
    checks=[];events=[];queue=[];prev=None;legal=True;cancelled=0
    def check(v,ob,e,a):checks.append(dict(cycle=v['cycle'],family=stim[v['cycle']]['family'],obligation=ob,expected=e,observed=a,passed=e==a))
    for v,s in zip(values,stim):
        assert all(v[k]==s[k] for k in ('cycle','rst','sv','sd','sk','sl','mr','pause'))
        if v['rst']:
            if queue:events.append(dict(kind='reset_cancel',cycle=v['cycle'],transactions=list(queue)));cancelled+=len(queue)
            queue=[];prev=None;continue
        if prev and prev['sv'] and not prev['sr']:
            if not v['sv'] or any(v[k]!=prev[k] for k in ('sd','sk','sl')):legal=False
        if prev and prev['mv'] and not prev['mr']:
            check(v,'hold_valid',1,v['mv'])
            check(v,'hold_payload',[prev[k] for k in ('md','mk','ml')],[v[k] for k in ('md','mk','ml')])
        if v['sv'] and v['sr']:
            q=dict(accepted_cycle=v['cycle'],byte=v['sd'],last=v['sl']);queue.append(q);events.append(dict(kind='accepted',**q))
        if v['mv'] and v['mr']:
            active=[i for i in range(mwidth//8) if v['mk']&(1<<i)]
            check(v,'nonempty_output_keep',True,bool(active))
            for index,i in enumerate(active):
                byte=(v['md']>>(8*i))&255
                if not queue:check(v,'no_unrequested_output',False,True);continue
                q=queue.pop(0);check(v,'byte_order',q['byte'],byte)
                last=int(bool(v['ml']) and index==len(active)-1);check(v,'frame_boundary',q['last'],last)
                events.append(dict(kind='response',cycle=v['cycle'],request=q,byte=byte,last=last))
        if s['phase']==39:check(v,'drain_complete',0,len(queue))
        prev=v
    return dict(checks=checks,events=events,legality_confirmed=legal,reset_cancelled_bytes=cancelled,
        failures=[r for r in checks if not r['passed']],interpretation='Byte/last queue and stall obligations independently adjudicated from ports; ignored input tkeep never discards accepted bytes.')


def run(prep,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False);results=[]
    for case,params in [('ibex54',[0]),('axis_adapter_keep',[8,32]),('axis_fifo_pause',[0,1])]:
        for p in params:
            for rev in ('before','after'):
                folder=out/case/f'p{p}'/rev
                source=prep/case/rev
                files=[source/'ibex_defines.sv',source/'ibex_compressed_decoder.sv'] if case=='ibex54' else [source/('axis_adapter.v' if case=='axis_adapter_keep' else 'axis_fifo.v')]
                tb=prep/case/('tb.sv' if case=='ibex54' else f'tb_{p}.sv')
                result=native.run_native(tb.read_text(),folder,extra_sources=files)
                entry=dict(case=case,parameter=p,revision=rev,native=result,status='unknown')
                if result['execution_status']=='completed':
                    values=trace(folder);dump(folder/'trace.json',values)
                    if case=='ibex54':
                        vec=read(prep/case/'vectors.json');assert len(values)==len(vec);checks=[]
                        for v,s in zip(values,vec):
                            assert v['instr']==s['instruction'];e=ibex.oracle(s['instruction'])
                            for field in ('illegal','compressed','decoded'):
                                if field=='decoded' and e['illegal']:continue
                                checks.append(dict(sample=v['sample'],family=s['family'],obligation=field,expected=e[field],observed=v[field],passed=e[field]==v[field]))
                        oracle=dict(checks=checks,failures=[r for r in checks if not r['passed']],legality_confirmed=True)
                    else:
                        rows=read(prep/case/'stimuli.json');assert len(values)==len(rows)
                        oracle=oracle_axis(values,rows,p if case=='axis_adapter_keep' else 8)
                    dump(folder/'oracle.json',oracle)
                    entry.update(status='violated' if oracle['failures'] else 'no_violation_in_scope',failed=len(oracle['failures']),legality_confirmed=oracle['legality_confirmed'])
                results.append(entry);dump(out/'progress.json',results)
                print('NATIVE159',case,p,rev,result['compile_status'],result['execution_status'],entry.get('failed'),flush=True)
    dump(out/'results.json',dict(results=results,model_calls=0,formal_calls=0));verify(prep)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run']);ap.add_argument('--prepared',type=Path);ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    else:run(a.prepared.resolve(),a.out.resolve())
