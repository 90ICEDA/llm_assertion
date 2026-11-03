"""Runtime-input FIFO testbench and independent port-history contract oracle.

No model calls. All output fault modes are artificial boundary mutations of the
vendored real axis_fifo RTL, never claimed as upstream historical bugs.
"""
from __future__ import annotations
import collections
import json
from pathlib import Path
import shutil
from research_fifo_experiment import ROOT, parse_trace, write_json, sha

RTL=ROOT/'external/verilog-axis/rtl/axis_fifo.v'
MODES=('correct','corrupt','duplicate_payload','drop','reset_residue')
OBLIGATIONS=('order_payload','no_unsolicited_output','stall_stability','drain_no_loss','reset_cancellation')


def testbench_template(depth=2,pipeline=0):
    if not (2<=depth<=8 and 0<=pipeline<=2):
        raise ValueError('Finite-drain contract qualified only for requested depth 2..8, pipeline 0..2')
    return '''`timescale 1ns/1ps
module tb;
  reg clk=0; always #5 clk=~clk;
  reg rst=1, svalid=0, mready=0, drain_due=0;
  reg [31:0] sdata=0;
  wire sready, raw_valid, mvalid;
  wire [31:0] raw_data, mdata;
  integer native_cycle=-1, raw_count=0, fault_mode=0;
  reg [31:0] last_data=0, residue_data=0;
  reg previous_accept=0, previous_rst=1, residue_pending=0;
  string input_path;
  integer fd, scan_count, cyc_arg, rst_arg, intent_arg, ready_arg, drain_arg;
  reg [31:0] data_arg;
  initial if ($value$plusargs("fault=%d",fault_mode)) begin end
  assign mdata = (fault_mode==4 && residue_pending && !rst) ? residue_data :
    fault_mode==1 ? raw_data ^ 32'h1 :
    (fault_mode==2 && raw_count%4==3) ? last_data : raw_data;
  assign mvalid = (fault_mode==4 && residue_pending && !rst) ? 1'b1 :
    raw_valid && !(fault_mode==3 && raw_count%4==3);
  always @(posedge clk) begin
    previous_rst<=rst;
    if (rst) begin
      raw_count<=0; last_data<=0;
      // A pending raw output is cancelled by synchronous reset. Fault mode 4
      // intentionally resurrects exactly this value after reset release.
      if (!previous_rst && raw_valid) begin residue_data<=raw_data; residue_pending<=1; end
    end else begin
      if (raw_valid && mready) begin raw_count<=raw_count+1; last_data<=raw_data; end
      if (residue_pending && mready) residue_pending<=0;
    end
  end
  axis_fifo #(.DEPTH(DEPTH_VALUE), .DATA_WIDTH(32), .KEEP_ENABLE(0),
    .KEEP_WIDTH(1), .LAST_ENABLE(0), .ID_ENABLE(0), .DEST_ENABLE(0),
    .USER_ENABLE(0), .RAM_PIPELINE(PIPELINE_VALUE), .FRAME_FIFO(0)) dut (
    .clk(clk),.rst(rst),.s_axis_tdata(sdata),.s_axis_tkeep(1'b1),
    .s_axis_tvalid(svalid),.s_axis_tready(sready),.s_axis_tlast(1'b0),
    .s_axis_tid(8'b0),.s_axis_tdest(8'b0),.s_axis_tuser(1'b0),
    .m_axis_tdata(raw_data),.m_axis_tvalid(raw_valid),.m_axis_tready(mready),.pause_req(1'b0));
  // NATIVE_REFERENCE
  // NATIVE_PROPERTIES
  task drive(input integer cyc, input integer reset_i, input integer intent_i,
             input integer ready_i, input [31:0] payload_i, input integer drain_i);
    begin
      @(negedge clk);
      native_cycle=cyc;rst=reset_i;mready=ready_i;drain_due=drain_i;
      if (rst) begin svalid=0;sdata=0;end
      else if (!svalid || previous_accept) begin svalid=intent_i;sdata=payload_i;end
      @(posedge clk);
      $display("TRACE %0d %0d %0d %0d %0d %0d %0d %0d",cyc,rst,svalid,sready,sdata,mvalid,mready,mdata);
      previous_accept=svalid && sready;
    end
  endtask
  initial begin
    $dumpfile("wave.vcd");$dumpvars(0,tb);
    if ($value$plusargs("stimulus=%s",input_path)) begin
      fd=$fopen(input_path,"r");
      if (!fd) $fatal(1,"Missing input schedule");
      while (!$feof(fd)) begin
        scan_count=$fscanf(fd,"%d %d %d %d %d %d\\n",cyc_arg,rst_arg,intent_arg,ready_arg,data_arg,drain_arg);
        if (scan_count==6) drive(cyc_arg,rst_arg,intent_arg,ready_arg,data_arg,drain_arg);
        else if (!$feof(fd)) $fatal(1,"Malformed input schedule");
      end
      $fclose(fd);
    end else begin
      drive(0,1,0,0,0,0);drive(1,1,0,0,0,0);drive(2,0,0,1,0,0);
    end
    #1;$display("NATIVE_RUN_COMPLETE");$finish;
  end
endmodule
'''.replace('DEPTH_VALUE',str(depth)).replace('PIPELINE_VALUE',str(pipeline))


def save_schedule(folder,rows):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    write_json(folder/'stimulus.json',rows)
    path=folder/'stimulus.txt'
    path.write_text(''.join(f'{i} {r["rst"]} {r["intent"]} {r["ready"]} {r["data"]} {r.get("drain_due",0)}\n' for i,r in enumerate(rows)))
    return path.resolve()


def oracle(trace,rows):
    """Independent accepted-transaction queue, no candidate or DUT internals.

    Reset-residue attribution uses unique payloads of actually cancelled
    accepted inputs. Reused payload values are marked unknown rather than
    being claimed as uniquely attributable reset failures.
    """
    pending=collections.deque(); txns=[]; checks=[]; violations=[]; unknown=[]; illegal=[]
    cancelled=[]; completed=[]; prior=None; epoch=0; in_reset=False
    coverage=collections.Counter()
    def record(cycle,obligation,passed,tid=None,**kw):
        item=dict(cycle=cycle,obligation=obligation,passed=bool(passed),transaction_id=tid,**kw)
        checks.append(item)
        if not passed:violations.append(item)
    for t in trace:
        cycle=t['cycle']
        if any(t.get(k) is None for k in ('rst','svalid','sready','mvalid','mready')):
            unknown.append(dict(cycle=cycle,reason='unknown_control'));prior=None;continue
        if t['rst']:
            if not in_reset:epoch+=1
            in_reset=True
            for txn in pending:
                txn.update(cancel_cycle=cycle,outcome='reset_cancelled')
                cancelled.append(txn)
            coverage['reset_with_pending']+=bool(pending)
            pending.clear();prior=None;continue
        in_reset=False
        if prior and prior['svalid'] and not prior['sready'] and (not t['svalid'] or t['sdata']!=prior['sdata']):
            illegal.append(dict(cycle=cycle,reason='unaccepted_input_not_held'))
        if prior and prior['mvalid'] and not prior['mready']:
            if t['mdata'] is None or prior['mdata'] is None:
                unknown.append(dict(cycle=cycle,reason='unknown_stalled_payload'))
            else:record(cycle,'stall_stability',t['mvalid'] and t['mdata']==prior['mdata'])
            coverage['backpressure']+=1
        push=t['svalid'] and t['sready'];pop=t['mvalid'] and t['mready']
        if (push and t['sdata'] is None) or (pop and t['mdata'] is None):
            unknown.append(dict(cycle=cycle,reason='unknown_accepted_payload'))
        coverage['simultaneous_accept_response']+=bool(push and pop)
        coverage['idle']+=not t['svalid']
        if pop:
            record(cycle,'no_unsolicited_output',bool(pending))
            expected=pending[0] if pending else None
            matches=[x for x in cancelled if x['data']==t['mdata']]
            if cancelled and t['mdata'] is not None:
                if matches and expected and expected['data']==t['mdata']:
                    unknown.append(dict(cycle=cycle,reason='reset_payload_identity_ambiguous'))
                else:record(cycle,'reset_cancellation',not matches,
                    matches[0]['transaction_id'] if matches else None,
                    cancelled_accept_cycle=matches[0]['accept_cycle'] if matches else None,
                    cancel_cycle=matches[0]['cancel_cycle'] if matches else None,observed_data=t['mdata'])
            if pending:
                txn=pending.popleft()
                if t['mdata'] is not None and txn['data'] is not None:
                    record(cycle,'order_payload',t['mdata']==txn['data'],txn['transaction_id'],expected=txn['data'],actual=t['mdata'])
                txn.update(response_cycle=cycle,latency=cycle-txn['accept_cycle'],observed_data=t['mdata'],outcome='responded')
                completed.append(txn);coverage['multi_cycle_response']+=txn['latency']>1
        if push:
            txn=dict(transaction_id=f'e{epoch}:t{len(txns)}',epoch=epoch,accept_cycle=cycle,data=t['sdata'],response_cycle=None,cancel_cycle=None,outcome='pending')
            txns.append(txn);pending.append(txn)
        prior=t
    fair_samples=0
    for t in reversed(trace):
        if t['rst'] or t['svalid'] or not t['mready']:break
        fair_samples+=1
    # Scope enforced by testbench_template: RAM depth <=8, RAM_PIPELINE<=2,
    # OUTPUT_FIFO_ENABLE=0. RTL has at most RAM_PIPELINE+1 read pipeline
    # registers (axis_fifo.v:196), so <=11 stored items and pipeline-fill
    # latency fit inside 18 continuously ready, input-idle samples.
    fair=fair_samples>=18
    if rows and rows[-1].get('drain_due'):
        if fair:record(trace[-1]['cycle'],'drain_no_loss',not pending,outstanding=[x['transaction_id'] for x in pending])
        else:unknown.append(dict(reason='drain_due_without_actual_fair_drain',actual_fair_samples=fair_samples,required=18))
    if len(trace)!=len(rows):unknown.append(dict(reason='trace_length_mismatch',expected=len(rows),actual=len(trace)))
    return dict(legality='illegal' if illegal else 'legal',legality_errors=illegal,checks=checks,violations=violations,
        verdict='unknown' if unknown else 'violation' if violations else 'no_violation_within_execution',
        transactions=txns,cancelled=cancelled,pending=list(pending),coverage=dict(coverage),unknown=unknown,
        drain_scope=dict(max_ram_depth=8,max_ram_pipeline=2,output_fifo_enabled=False,required_fair_samples=18,actual_fair_samples=fair_samples),
        scope='finite transaction oracle; no formal proof; reset attribution requires unique accepted payload identity')


def build(candidate,folder,depth=2,pipeline=0):
    import research15_native_interface as interface
    # The native agent owns validated property parsing and real cover triggers.
    return interface.compile_candidate(candidate,Path(folder),testbench_template(depth,pipeline))


def execute(compiled,folder,rows,mode):
    import research15_native_interface as interface
    return interface.run_replay(compiled,Path(folder),rows,MODES.index(mode) if isinstance(mode,str) else mode)
