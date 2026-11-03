"""Local source/specification audit and fresh original-RTL exposure checks.

No model calls, no historical attribution inferred from artificial mutants,
and no old independent outcomes used. prepare seals source, scope and stimuli.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from unittest.mock import patch
import research_native_runner as native

ROOT=native.ROOT
CC='03d98106aa19952a10360d2230def85144a0008b'
AXIS='48ff7a7e2ef782cf778d47910cf85835c64b1bce'
CASE=ROOT/'rtl_cases_real_scale210_independent/case438_cc_fifo_protocol_suppress_2'
STAT=ROOT/'rtl_cases_real_scale210_independent_next/case505_axis_stat_counter_frame_pulse_early'
dump=native.dump
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rel(p):return Path(p).relative_to(ROOT).as_posix()


def git_blob(repo,commit,name):
    return subprocess.run(['git','-C',str(repo),'show',commit+':'+name],check=True,capture_output=True).stdout


def fifo_rows(depth):
    rows=[]
    def add(n=1,**kw):
        base=dict(rst=1,push=0,pop=0,data=0,clr=0,flush=0);base.update(kw)
        rows.extend([dict(base) for _ in range(n)])
    if depth==0:
        for payload,stall,control in itertools.product((0,1,127,255),(0,1,3),('none','clr','flush')):
            add(2,rst=0);add(**({control:1} if control!='none' else {}))
            add(stall,push=1,data=payload);add(push=1,pop=1,data=payload);add()
        # Explicit reset cancellation of a presented, unaccepted item.
        add(2,push=1,data=85);add(2,rst=0);add(3)
    else:
        add(2,rst=0);add()
        for i in range(depth):add(push=1,data=32+i)
        add(3);add(pop=1)
        for i in range(3):add(push=1,pop=1,data=80+i)
        add(depth-1,pop=1);add(2)
        add(push=1,data=123);add(flush=1);add(2)
        add(push=1,data=234);add(2,rst=0);add(2)
    return [dict(r,cycle=i) for i,r in enumerate(rows)]


def stat_local_rows():
    rows=[]
    def add(n=1,**kw):
        base=dict(rst=1,event=0,length=0,scope='isolated');base.update(kw)
        rows.extend([dict(base) for _ in range(n)])
    for length in (0,1,127,255):
        add(2,rst=0);add();add(event=1,length=length);add(4)
    add(2,rst=0,scope='overlap_unknown');add(event=1,length=17,scope='overlap_unknown')
    add(event=1,length=91,scope='overlap_unknown');add(4,scope='overlap_unknown')
    add(2,rst=0);add(event=1,length=39);add(2,rst=0);add(4)
    return [dict(r,cycle=i) for i,r in enumerate(rows)]


def stat_axis_rows(width):
    rows=[];lanes=width//8
    for epoch,lengths in enumerate(((2,3),(1,),(1,2,1))):
        start=len(rows)
        def add(n=1,**kw):
            base=dict(rst=0,valid=0,ready=1,last=0,keep=(1<<lanes)-1,trigger=0,tag=epoch+1,out_ready=1,epoch=epoch)
            base.update(kw);rows.extend([dict(base) for _ in range(n)])
        add(2,rst=1);add(2)
        for length in lengths:
            for beat in range(length):
                last=int(beat==length-1);keep=(1<<lanes)-1 if not last else (1<<max(1,lanes//2))-1
                add(2,valid=1,ready=0,last=last,keep=keep)
                add(valid=1,last=last,keep=keep)
            add()
        add(3);add(trigger=1,out_ready=0)
        for i in range(45):add(out_ready=int(i>=5 and i%4!=0))
        assert len(rows)>start
    return [dict(r,cycle=i) for i,r in enumerate(rows)]


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);bindings={};git_checks=[]
    sources={'common_cells':(CC,['src/cc_fifo.sv','src/cc_pkg.sv','include/common_cells/assertions.svh','include/common_cells/registers.svh']),
             'verilog-axis':(AXIS,['rtl/axis_stat_counter.v','tb/test_axis_stat_counter.py','README.md'])}
    for project,(commit,names) in sources.items():
        repo=ROOT/'external'/project
        for name in names:
            blob=git_blob(repo,commit,name);f=out/'sources'/project/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_bytes(blob)
            working=repo/name
            git_checks.append(dict(project=project,commit=commit,file=name,git_blob_sha256=sha(f),working_sha256=sha(working),
                newline_normalized_equal=f.read_text()==working.read_text()))
            bindings[rel(working)]=sha(working)
    for label,folder in [('fifo_case',CASE),('stat_case',STAT)]:
        for name in ('correct.v','buggy.v','case_metadata.json','spec.md'):
            f=folder/name;target=out/'sources'/label/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,target);bindings[rel(f)]=sha(f)
    upstream=(out/'sources/common_cells/src/cc_fifo.sv').read_text()
    local=(out/'sources/fifo_case/correct.v').read_text()
    compat="{FifoDepth{data_t'('0)}}"
    assert upstream.replace(compat,"'0")==local
    edit=read(CASE/'case_metadata.json')['mutation_edits'][0]
    assert upstream.count(edit['search'])==1
    mutant=upstream.replace(edit['search'],edit['replace'])
    assert mutant.replace(compat,"'0")== (out/'sources/fifo_case/buggy.v').read_text()
    (out/'sources/common_cells/src/cc_fifo_mutant.sv').write_text(mutant)
    dump(out/'lineage.json',dict(git_objects=git_checks,fifo=dict(original_commit=CC,exact_original_blob=True,
        local_case_diff='Only documented memory-reset compatibility expression; new execution uses original typed expression.',
        mutant='Only the existing recorded empty_o force-zero edit applied to original blob.',historical_fix_commit=None,origin='artificial_mutation_not_historical_fix'),
        stat=dict(original_commit=AXIS,local_signals_absent_in_original=all(x not in (out/'sources/verilog-axis/rtl/axis_stat_counter.v').read_text() for x in ('frame_done_i','frame_len_i','stat_valid_o','stat_len_o')),
            derivation_still_missing=True,historical_admission=False)))
    for depth in (0,2,4):dump(out/f'fifo_d{depth}.json',fifo_rows(depth))
    dump(out/'stat_local.json',stat_local_rows())
    for width in (8,64):dump(out/f'stat_axis_w{width}.json',stat_axis_rows(width))
    protocol=dict(created=time.time(),model_calls=0,formal_calls=0,dataset='new development source/specification exposure audit, not learned-candidate independent testing',
        fifo=dict(configurations=[0,2,4],width=8,fallthrough=0,
            default_assertions='Run original and existing mutant at all three depths with upstream assertions enabled. Depth0 initial rejection is an unsupported configuration result, not a functional witness.',
            conditional='Additional Depth0 runs explicitly COMMON_CELLS_ASSERTS_OFF. Presented stalls only legal under separately named passthrough contract; not under upstream full_write precondition.',
            oracle='Depth0 empty=!push, full=!pop, data=data_i; actual accepted=active && push && pop. For depths2/4 independent queue checks old-head data, empty/full/usage; no forbidden full writes/empty reads; clear/reset cancellation.',
            target='presented means push=1; count idle mismatch separately. Existing force-zero mutation algebraically cannot violate nonempty-on-present in two-state Depth0.',
            success='No historical success from artificial mutation or assertions-disabled unsupported parameter. Require distinct original-repair lineage and legal original witness.'),
        stat_local=dict(scope='Only isolated events under existing local prose; two PRE-NBA samples after event. Overlap deliberately diagnosed but remains specification/provenance unknown.',
            status='Synthetic model only, never original historical stat repair.'),
        stat_original=dict(widths=[8,64],frame_beat_lengths=[[2,3],[1],[1,2,1]],
            specification='Pinned README: count bytes and frames on monitored AXI stream; tlast end-of-frame. Pinned upstream test decodes >HLLL and expects frame/byte counts. Only complete frames before quiet trigger, trigger when not busy, contiguous low tkeep, stable monitor payload through stalls.',
            checks='Independent accepted-beat byte count and accepted-tlast completed-frame count, tick snapshot, tag,14-byte output packet,tlast,output stability through backpressure. No fixed frame_done-to-output latency claim.',
            limitation='Original source only, no repaired revision. Any confirmed discrepancy is a new bounded original-source observation, NOT restored case505 provenance or successful historical repair.'),
        unknown_policy='Missing source mapping, unsupported config, absent exposure or no fixed revision cannot count as historical success. No inferred permission from lack of a ready port.',
        no_old_independent_reads=True)
    dump(out/'protocol.json',protocol)
    for f in (Path(__file__),ROOT/'scripts/research_native_runner.py'):bindings[rel(f)]=sha(f)
    dump(out/'source_bindings.json',bindings)
    dump(out/'sealed.json',{f.relative_to(out).as_posix():sha(f) for f in out.rglob('*') if f.is_file()})
    print('PREPARED152 original source/scope/stimuli; model0',flush=True)


def fifo_tb(prep,rows,depth):
    pkg=(prep/'sources/common_cells/src/cc_pkg.sv').as_posix()
    lines=[f'`include "{pkg}"','module tb;', 'bit clk_i=0; always #5 clk_i=~clk_i;',
        'bit rst_ni=0,clr_i=0,flush_i=0,push_i=0,pop_i=0; bit [7:0] data_i=0; wire [7:0] data_o;',
        f'wire full_o,empty_o; wire [cc_pkg::cnt_width({depth})-1:0] usage_o; integer cycle=-1;',
        f'cc_fifo #(.DataWidth(8),.Depth({depth}),.FallThrough(0)) dut(.*);']
    if depth==0:
        for name,condition in [('idle','!push_i |-> empty_o'),('presented','push_i |-> !empty_o')]:
            lines += [f'{name}: assert property (@(posedge clk_i) disable iff(!rst_ni) ({condition})) else $display("ASSERT_FAIL {name} cycle=%0d",$sampled(cycle));']
    lines += ['initial begin $dumpfile("wave.vcd"); $dumpvars(0,tb);']
    for r in rows:
        lines += [f"@(negedge clk_i); cycle={r['cycle']}; rst_ni={r['rst']}; clr_i={r['clr']}; flush_i={r['flush']}; push_i={r['push']}; pop_i={r['pop']}; data_i={r['data']};",
            '@(posedge clk_i); $display("TRACE cycle=%0d rst=%0d push=%0d pop=%0d data=%0d clr=%0d flush=%0d full=%0d empty=%0d usage=%0d output=%0d",cycle,rst_ni,push_i,pop_i,data_i,clr_i,flush_i,full_o,empty_o,usage_o,data_o);']
    return '\n'.join(lines+['@(negedge clk_i); $display("NATIVE_RUN_COMPLETE"); $finish; end endmodule'])


def local_tb(rows):
    lines=['module tb; bit clk_i=0;always #5 clk_i=~clk_i; bit rst_ni=0,frame_done_i=0;bit [7:0] frame_len_i=0;wire stat_valid_o;wire [7:0] stat_len_o;integer cycle=-1;axis_stat_counter dut(.*);',
           'initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);']
    for r in rows:
        lines += [f"@(negedge clk_i);cycle={r['cycle']};rst_ni={r['rst']};frame_done_i={r['event']};frame_len_i={r['length']};",
            '@(posedge clk_i);$display("TRACE cycle=%0d rst=%0d event=%0d length=%0d valid=%0d data=%0d",cycle,rst_ni,frame_done_i,frame_len_i,stat_valid_o,stat_len_o);']
    return '\n'.join(lines+['@(negedge clk_i);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule'])


def axis_tb(rows,width):
    lanes=width//8
    lines=['module tb;bit clk=0;always #5 clk=~clk;bit rst=1;',f'bit [{lanes-1}:0] monitor_axis_tkeep=0;',
        'bit monitor_axis_tvalid=0,monitor_axis_tready=1,monitor_axis_tlast=0;wire [7:0] m_axis_tdata;wire m_axis_tvalid,m_axis_tlast,m_axis_tuser,busy;bit m_axis_tready=1;bit [15:0] tag=0;bit trigger=0;integer cycle=-1;',
        f'axis_stat_counter #(.DATA_WIDTH({width}),.KEEP_ENABLE({int(width>8)}),.KEEP_WIDTH({lanes})) dut(.*);',
        'hold_output: assert property (@(posedge clk) disable iff(rst) (m_axis_tvalid && !m_axis_tready) |=> (m_axis_tvalid && $stable(m_axis_tdata) && $stable(m_axis_tlast))) else $display("ASSERT_FAIL hold_output cycle=%0d",$sampled(cycle));',
        'initial begin $dumpfile("wave.vcd");$dumpvars(0,tb);']
    for r in rows:
        lines += [f"@(negedge clk);cycle={r['cycle']};rst={r['rst']};monitor_axis_tvalid={r['valid']};monitor_axis_tready={r['ready']};monitor_axis_tlast={r['last']};monitor_axis_tkeep={r['keep']};trigger={r['trigger']};tag={r['tag']};m_axis_tready={r['out_ready']};",
            '@(posedge clk);$display("TRACE cycle=%0d rst=%0d valid=%0d ready=%0d last=%0d keep=%0d trigger=%0d tag=%0d busy=%0d ov=%0d readyout=%0d ol=%0d od=%0d",cycle,rst,monitor_axis_tvalid,monitor_axis_tready,monitor_axis_tlast,monitor_axis_tkeep,trigger,tag,busy,m_axis_tvalid,m_axis_tready,m_axis_tlast,m_axis_tdata);']
    return '\n'.join(lines+['@(negedge clk);$display("NATIVE_RUN_COMPLETE");$finish;end endmodule'])


def trace(folder,rows):
    values=[]
    for line in (folder/'execute.log').read_text().splitlines():
        if line.startswith('TRACE '):values.append({k:int(v) for k,v in (p.split('=') for p in line.split()[1:])})
    assert len(values)==len(rows) and [r['cycle'] for r in values]==list(range(len(rows)))
    return values


def fifo_oracle(values,rows,depth):
    queue=[];events=[];checks=[];legality=[];pending=None
    for v,s in zip(values,rows):
        assert all(v[k]==s[k] for k in ('rst','push','pop','data','clr','flush'))
        t=v['cycle']
        if not s['rst']:
            if pending:events.append(dict(kind='reset_cancel',cycle=t,transaction=pending))
            pending=None;queue=[];continue
        if depth==0:
            if s['push'] and pending is None:pending=dict(presented=t,data=s['data'])
            if pending and s['push']:assert pending['data']==s['data']
            legal=not(s['push'] and not s['pop']) and not(s['pop'] and not s['push'])
            legality.append(dict(cycle=t,conditional_passthrough=True,upstream_io_preconditions=legal,
                                 parameter_supported_with_upstream_assertions=False))
            obligation='nonempty_when_present' if s['push'] else 'empty_when_idle'
            checks.append(dict(cycle=t,obligation=obligation,expected=int(not s['push']),observed=v['empty'],passed=v['empty']==int(not s['push'])))
            checks += [dict(cycle=t,obligation=k,expected=e,observed=v[o],passed=v[o]==e) for k,o,e in [('full_relation','full',int(not s['pop'])),('data_passthrough','output',s['data'])]]
            if s['push'] and s['pop']:
                events.append(dict(kind='accepted_and_responded',cycle=t,transaction=pending,output=v['output']));pending=None
        else:
            allowed=not(s['push'] and len(queue)==depth) and not(s['pop'] and not queue)
            assert allowed
            for name,observed,expected in [('empty',v['empty'],int(not queue)),('full',v['full'],int(len(queue)==depth)),('usage',v['usage'],len(queue))]:
                checks.append(dict(cycle=t,obligation=name,expected=expected,observed=observed,passed=observed==expected))
            if s['pop']:
                q=queue.pop(0);checks.append(dict(cycle=t,obligation='order_payload',expected=q['data'],observed=v['output'],passed=v['output']==q['data']))
                events.append(dict(kind='response',cycle=t,transaction=q,output=v['output']))
            if s['push']:
                q=dict(accepted=t,data=s['data']);queue.append(q);events.append(dict(kind='accepted',cycle=t,transaction=q))
            if s['clr'] or s['flush']:events.append(dict(kind='clear_cancel',cycle=t,transactions=list(queue)));queue=[]
    return dict(checks=checks,events=events,legality=legality,failed=[v for v in checks if not v['passed']])


def local_oracle(values,rows):
    history=[];checks=[]
    for v,s in zip(values,rows):
        assert all(v[k]==s[k] for k in ('rst','event','length'))
        if not s['rst']:history=[];continue
        expected=history[-2]['event'] if len(history)>=2 else 0
        checks.append(dict(cycle=s['cycle'],scope=s['scope'],obligation='valid_two_preedge_samples',expected=expected,observed=v['valid'],passed=v['valid']==expected))
        if expected:
            exp=history[-2]['length'];checks.append(dict(cycle=s['cycle'],scope=s['scope'],obligation='event_captured_length',expected=exp,observed=v['data'],passed=exp==v['data']))
        history.append(s)
    return dict(checks=checks,confirmed_isolated_failures=[v for v in checks if not v['passed'] and v['scope']=='isolated'],
                ambiguous_overlap_diagnostics=[v for v in checks if not v['passed'] and v['scope']=='overlap_unknown'])


def axis_oracle(values,rows,width):
    tick=byte_count=frames=0;packet=[];expected=None;checks=[];events=[];prev=None;pending=None
    for v,s in zip(values,rows):
        assert all(v[k]==s[k] for k in ('rst','valid','ready','last','keep','trigger','tag')) and v['readyout']==s['out_ready']
        t=s['cycle']
        if s['rst']:tick=byte_count=frames=0;packet=[];expected=None;prev=None;pending=None;continue
        if prev and prev['valid'] and not prev['ready']:assert s['valid'] and all(s[k]==prev[k] for k in ('last','keep'))
        if s['trigger']:
            assert not v['busy'] and expected is None
            expected=[s['tag'],tick,byte_count,frames];events.append(dict(kind='snapshot_request',cycle=t,epoch=s['epoch'],expected=expected))
            tick=byte_count=frames=0
        tick+=width//8
        if s['valid']:
            if pending is None:pending=dict(presented=t,keep=s['keep'],last=s['last'])
            if s['ready']:
                byte_count+=s['keep'].bit_count() if width>8 else 1;frames+=s['last']
                events.append(dict(kind='monitor_beat_accepted',cycle=t,epoch=s['epoch'],transaction=pending));pending=None
        if v['ov'] and v['readyout']:
            assert expected is not None
            packet.append(v['od'])
            checks.append(dict(cycle=t,obligation='packet_last_position',passed=v['ol']==int(len(packet)==14)))
            if v['ol']:
                if len(packet)==14:
                    actual=[int.from_bytes(bytes(packet[a:b]),'big') for a,b in ((0,2),(2,6),(6,10),(10,14))]
                    for name,e,a in zip(('tag','ticks','accepted_bytes','completed_frames'),expected,actual):
                        checks.append(dict(cycle=t,epoch=s['epoch'],obligation=name,expected=e,observed=a,passed=e==a))
                    events.append(dict(kind='snapshot_response',cycle=t,epoch=s['epoch'],expected=expected,actual=actual,bytes=packet))
                packet=[];expected=None
        prev=s
    assert expected is None and not packet
    return dict(checks=checks,events=events,failed=[v for v in checks if not v['passed']],
                responses=sum(v['kind']=='snapshot_response' for v in events),repair_revision_available=False)


def verify(prep):
    for name,h in read(prep/'sealed.json').items():assert sha(prep/name)==h,name
    for name,h in read(prep/'source_bindings.json').items():assert sha(ROOT/name)==h,name


def run(prep,out):
    verify(prep);out.mkdir(parents=True,exist_ok=False);results=[]
    original=native.command
    for depth in (0,2,4):
        for disabled in ((False,True) if depth==0 else (False,)):
            for revision in ('original','existing_mutant'):
                folder=out/f'fifo_d{depth}_asserts_{"off" if disabled else "on"}'/revision
                rows=read(prep/f'fifo_d{depth}.json')
                source=prep/'sources/common_cells/src'/('cc_fifo.sv' if revision=='original' else 'cc_fifo_mutant.sv')
                def command(argv,*args,**kw):
                    if '--binary' in argv:argv=[*argv,'-I'+str(prep/'sources/common_cells/include'),*(['+define+COMMON_CELLS_ASSERTS_OFF'] if disabled else [])]
                    return original(argv,*args,**kw)
                with patch.object(native,'command',command):result=native.run_native(fifo_tb(prep,rows,depth),folder,extra_sources=[source])
                entry=dict(case='fifo',depth=depth,upstream_assertions_disabled=disabled,revision=revision,native=result)
                if result['execution_status']=='completed':
                    values=trace(folder,rows);oracle=fifo_oracle(values,rows,depth);dump(folder/'trace.json',values);dump(folder/'oracle.json',oracle)
                    entry['failed']=len(oracle['failed']);entry['exposed_checks']=len(oracle['checks'])
                else:entry['scope_status']='configuration_rejected' if 'Depth must be greater than 0' in (folder/'execute.log').read_text() else 'unknown_tool_or_execution'
                results.append(entry);dump(out/'progress.json',results);print('FIFO152',depth,disabled,revision,result['execution_status'],entry.get('failed'),flush=True)
    for revision in ('correct','buggy'):
        folder=out/'stat_local'/revision;rows=read(prep/'stat_local.json')
        result=native.run_native(local_tb(rows),folder,extra_sources=[prep/'sources/stat_case'/f'{revision}.v'])
        entry=dict(case='stat_local_synthetic',revision=revision,native=result)
        if result['execution_status']=='completed':
            values=trace(folder,rows);oracle=local_oracle(values,rows);dump(folder/'trace.json',values);dump(folder/'oracle.json',oracle)
            entry.update(isolated_failures=len(oracle['confirmed_isolated_failures']),overlap_unknown_diagnostics=len(oracle['ambiguous_overlap_diagnostics']))
        results.append(entry);dump(out/'progress.json',results);print('STAT_LOCAL152',revision,result['execution_status'],flush=True)
    for width in (8,64):
        folder=out/f'stat_original_w{width}';rows=read(prep/f'stat_axis_w{width}.json')
        result=native.run_native(axis_tb(rows,width),folder,extra_sources=[prep/'sources/verilog-axis/rtl/axis_stat_counter.v'])
        entry=dict(case='stat_original',width=width,native=result)
        if result['execution_status']=='completed':
            values=trace(folder,rows);oracle=axis_oracle(values,rows,width);dump(folder/'trace.json',values);dump(folder/'oracle.json',oracle)
            entry.update(reference_failures=oracle['failed'],responses=oracle['responses'])
        results.append(entry);dump(out/'progress.json',results);print('STAT_ORIGINAL152',width,result['execution_status'],entry.get('reference_failures'),flush=True)
    verify(prep)
    dump(out/'results.json',dict(results=results,model_calls=0,formal_calls=0,
        historical_repair_successes=0,historical_case505_mapping='unknown',original_fifo_presented_repair='not_established',
        note='Original-source exposure and conditional mutation reproduction only. No original repaired stat revision and no historical FIFO fix lineage. Simulation is not proof.'))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('action',choices=('prepare','run','verify'));ap.add_argument('--prepared',type=Path);ap.add_argument('--out',type=Path)
    a=ap.parse_args()
    if a.action=='prepare':prepare(a.out.resolve())
    elif a.action=='verify':verify(a.prepared.resolve());print('VERIFIED152')
    else:run(a.prepared.resolve(),a.out.resolve())
