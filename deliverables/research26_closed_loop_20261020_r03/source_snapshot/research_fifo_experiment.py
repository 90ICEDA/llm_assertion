"""Replay real axis_fifo RTL with independent handshake/transaction oracles.

This is an engineering experiment, not an historical-bug reproduction or LLM run.
Run under Linux/WSL with python3 and Icarus Verilog on PATH.
"""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import json
import math
import random
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / 'deliverables/research_fifo_20261014_r01'
OBLIGATIONS = {
    'order_payload': 'Every accepted output equals the oldest outstanding accepted input payload.',
    'no_unsolicited_output': 'Every accepted output corresponds to an outstanding accepted input since reset.',
    'stall_stability': 'Output valid and payload persist while valid and not ready, except reset cancellation.',
    'drain_no_loss': 'After input stops and ready remains asserted, all outstanding accepted inputs drain within the finite experiment bound.',
    'reset_cancellation': 'Reset cancels every pending transaction; no pre-reset item may reappear after reset.',
}


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(cmd, cwd, stem):
    begin = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=90)
        result = dict(command=cmd, cwd=str(cwd), exit_code=proc.returncode,
                      elapsed_seconds=time.monotonic()-begin)
        (cwd / (stem + '.log')).write_text(proc.stdout + proc.stderr)
    except subprocess.TimeoutExpired as exc:
        result = dict(command=cmd, cwd=str(cwd), exit_code=None, timeout=True,
                      elapsed_seconds=time.monotonic()-begin)
        (cwd / (stem + '.log')).write_text(str(exc))
    write_json(cwd / (stem + '.json'), result)
    return result


def stimulus(seed, cycles=140):
    """Intent schedule; the HDL producer holds the actual request until handshake."""
    rng = random.Random(seed)
    rows = []
    for i in range(cycles):
        reset = i < 3 or i in (61, 62, 103)
        if i < 18: valid, ready = 1, 0  # fill and hold a pending request
        elif i < 45: valid, ready = 1, 1  # sustained overlap
        elif i < 61: valid, ready = int(i % 4 != 0), int(i % 5 > 1)
        elif i < 104: valid, ready = int(rng.random() < .8), int(rng.random() < .55)
        elif i < 112: valid, ready = 1, 0
        else: valid, ready = 0, 1  # fair, finite drain interval
        rows.append(dict(cycle=i, rst=int(reset), intent=valid,
                         ready=ready, data=rng.randrange(1, 2**24)))
    return rows


def testbench(rows, depth, pipeline, mutant):
    # Mutants leave the internal ready/valid network unchanged. Identical actual
    # input handshakes across paired runs can therefore be checked explicitly.
    inject = {
        'correct': 'assign mdata = raw_data; assign mvalid = raw_valid;',
        'corrupt': 'assign mdata = raw_data ^ 32\'h1; assign mvalid = raw_valid;',
        'duplicate_payload': 'assign mdata = (raw_count % 4 == 3) ? last_data : raw_data; assign mvalid = raw_valid;',
        'drop': 'assign mdata = raw_data; assign mvalid = raw_valid && (raw_count % 4 != 3);',
    }[mutant]
    drives = '\n'.join(
        f'    drive({r["cycle"]}, {r["rst"]}, {r["intent"]}, {r["ready"]}, 32\'d{r["data"]});'
        for r in rows)
    return f'''`timescale 1ns/1ps
module tb;
  reg clk=0; always #5 clk=~clk;
  reg rst=1, svalid=0, mready=0;
  reg [31:0] sdata=0;
  wire sready, raw_valid, mvalid;
  wire [31:0] raw_data, mdata;
  reg previous_accept=0;
  integer raw_count=0;
  reg [31:0] last_data=0;
  {inject}
  axis_fifo #(.DEPTH({depth}), .DATA_WIDTH(32), .KEEP_ENABLE(0),
    .KEEP_WIDTH(1), .LAST_ENABLE(0), .ID_ENABLE(0), .DEST_ENABLE(0),
    .USER_ENABLE(0), .RAM_PIPELINE({pipeline}), .FRAME_FIFO(0)) dut (
    .clk(clk), .rst(rst), .s_axis_tdata(sdata), .s_axis_tkeep(1'b1),
    .s_axis_tvalid(svalid), .s_axis_tready(sready), .s_axis_tlast(1'b0),
    .s_axis_tid(8'b0), .s_axis_tdest(8'b0), .s_axis_tuser(1'b0),
    .m_axis_tdata(raw_data), .m_axis_tvalid(raw_valid), .m_axis_tready(mready),
    .pause_req(1'b0));
  task drive(input integer cyc, input integer reset_i, input integer intent_i,
             input integer ready_i, input [31:0] payload_i);
    begin
      @(negedge clk);
      rst=reset_i; mready=ready_i;
      if (rst) begin svalid=0; sdata=0; end
      else if (!svalid || previous_accept) begin svalid=intent_i; sdata=payload_i; end
      @(posedge clk);
      $display("TRACE %0d %0d %0d %0d %0d %0d %0d %0d",cyc,rst,svalid,sready,sdata,mvalid,mready,mdata);
      previous_accept=svalid && sready;
      if (rst) begin raw_count<=0; last_data<=0; end
      else if (raw_valid && mready) begin raw_count<=raw_count+1; last_data<=raw_data; end
    end
  endtask
  initial begin
    $dumpfile("wave.vcd"); $dumpvars(0,tb);
{drives}
    #1; $finish;
  end
endmodule
'''


def parse_trace(path):
    names = ['cycle', 'rst', 'svalid', 'sready', 'sdata', 'mvalid', 'mready', 'mdata']
    return [dict(zip(names, (None if any(c in x.lower() for c in 'xz') else int(x)
                            for x in line.split()[1:])))
            for line in path.read_text().splitlines() if line.startswith('TRACE ')]


def oracle(trace, drain_start=112):
    """Port-history queue oracle, independent of all evaluated SVA strings.

    Output items pair with oldest accepted input; reset cancels pending items.
    Payload mismatches do not alter transaction IDs or oracle queue state.
    """
    queue = collections.deque()
    txns, checks, violations, legal_errors, cancelled = [], [], [], [], []
    prev = None
    epoch = 0
    unknown = []
    coverage = collections.Counter()
    def check(cycle, obligation, ok, transaction=None, **details):
        rec = dict(cycle=cycle, obligation=obligation, passed=bool(ok),
                   transaction_id=transaction, **details)
        checks.append(rec)
        if not ok: violations.append(rec)
    for t in trace:
        c = t['cycle']
        if any(t[n] is None for n in ('rst','svalid','sready','mvalid','mready')):
            unknown.append(dict(cycle=c, reason='unknown control value'))
            prev = None
            continue
        if t['rst']:
            for txn in queue:
                txn.update(cancel_cycle=c, outcome='reset_cancelled')
                cancelled.append(txn['transaction_id'])
            coverage['reset_with_pending'] += bool(queue)
            queue.clear()
            epoch += 1
            prev = None
            continue
        if prev and prev['svalid'] and not prev['sready']:
            if not t['svalid'] or t['sdata'] != prev['sdata']:
                legal_errors.append(dict(cycle=c, reason='producer changed pending unaccepted request'))
        if prev and prev['mvalid'] and not prev['mready']:
            check(c, 'stall_stability', t['mvalid'] and t['mdata']==prev['mdata'])
            coverage['backpressure'] += 1
        push = t['svalid'] and t['sready']
        pop = t['mvalid'] and t['mready']
        coverage['simultaneous_accept_output'] += bool(push and pop)
        coverage['idle'] += not t['svalid']
        # This RTL is buffered (minimum latency one edge), so output precedes
        # this edge's input in the transaction model. No same-edge bypass.
        if pop:
            check(c, 'no_unsolicited_output', bool(queue))
            if queue:
                txn = queue.popleft()
                check(c, 'order_payload', t['mdata']==txn['data'],
                      txn['transaction_id'], expected=txn['data'], actual=t['mdata'])
                txn.update(response_cycle=c, latency=c-txn['accept_cycle'],
                           observed_data=t['mdata'], outcome='responded')
                coverage['multi_cycle_response'] += txn['latency'] > 1
        if push:
            txn = dict(transaction_id=f'e{epoch}:t{len(txns)}', epoch=epoch,
                       accept_cycle=c, data=t['sdata'], response_cycle=None,
                       cancel_cycle=None, outcome='pending')
            txns.append(txn)
            queue.append(txn)
        if t['mvalid'] and not queue and not pop:
            # A presented output can be evaluated even if not accepted, but
            # transaction completion remains strictly a handshake event.
            check(c, 'no_unsolicited_output', False, detail='presented while reference queue empty')
        prev = t
    drain_valid = all(not t['svalid'] and t['mready'] and not t['rst']
                      for t in trace[-12:]) and len(trace) >= 12
    if drain_valid:
        check(trace[-1]['cycle'], 'drain_no_loss', not queue,
              outstanding=[t['transaction_id'] for t in queue])
    else:
        unknown.append(dict(reason='no fair complete final drain suffix'))
    # Cancellation is established structurally by epoch bookkeeping and checked
    # through all post-reset payload/order/unsolicited-output observations.
    return dict(legality='legal' if not legal_errors else 'illegal', legality_errors=legal_errors,
                obligation_verdict='violation' if violations else ('unknown' if unknown else 'no_violation_in_execution'),
                checks=checks, violations=violations, transactions=txns,
                reset_cancelled_transaction_ids=cancelled, coverage=dict(coverage), unknown=unknown,
                scope='finite RTL simulation; not a formal proof')


def diagnostic_candidates(trace):
    """Auxiliary Python predicates; NEVER labelled native SVA execution."""
    result = {}
    for name in ('valid_only', 'stable_under_backpressure'):
        triggers, failures = [], []
        for p,t in zip(trace,trace[1:]):
            if p['rst'] or t['rst']: continue
            if name=='valid_only':
                trigger=bool(p['svalid'] and p['sready'])
                ok=bool(t['mvalid'])
            else:
                trigger=bool(p['mvalid'] and not p['mready'])
                ok=bool(t['mvalid'] and p['mdata']==t['mdata'])
            if trigger:
                triggers.append(t['cycle'])
                if not ok: failures.append(t['cycle'])
        result[name]=dict(trigger_cycles=triggers, violation_cycles=failures,
                          checker='auxiliary_python_predicate_not_native_SVA')
    return result


def run_one(out, rtl, split, seed, depth, pipeline, mutant):
    folder=out/'runs'/split/f'd{depth}_p{pipeline}_s{seed}'/mutant
    folder.mkdir(parents=True, exist_ok=True)
    rows=stimulus(seed)
    write_json(folder/'intent_schedule.json',rows)
    (folder/'tb.sv').write_text(testbench(rows,depth,pipeline,mutant))
    shutil.copy2(rtl,folder/'axis_fifo.v')
    compilation=command(['iverilog','-g2012','-s','tb','-o','sim.vvp','axis_fifo.v','tb.sv'],folder,'compile')
    execution=None
    if compilation['exit_code']==0:
        execution=command(['vvp','sim.vvp'],folder,'execute')
    trace=parse_trace(folder/'execute.log') if execution and execution['exit_code']==0 else []
    result=oracle(trace) if trace else dict(legality='unknown',obligation_verdict='unknown',violations=[],transactions=[],coverage={})
    result.update(split=split, seed=seed, depth_requested=depth,
                  ram_depth_actual=2**math.ceil(math.log2(depth)), ram_pipeline=pipeline,
                  mutation=mutant, provenance='repository_upstream_RTL' if mutant=='correct' else 'artificial_output_boundary_mutation',
                  compile_status='success' if compilation['exit_code']==0 else 'error',
                  execution_status='completed' if trace else 'unknown',
                  native_sva_status='not_executed_iverilog_unsupported',
                  candidate_diagnostics=diagnostic_candidates(trace),
                  cost=dict(compile_seconds=compilation['elapsed_seconds'], simulation_seconds=execution['elapsed_seconds'] if execution else None,
                            model_calls=0, model_tokens=None, formal_seconds=None),
                  artifact_directory=str(folder.relative_to(out)))
    write_json(folder/'trace.json',trace)
    write_json(folder/'evidence.json',result)
    return result,trace


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,default=DEFAULT_OUT)
    args=ap.parse_args()
    out=args.out.resolve(); out.mkdir(parents=True,exist_ok=True)
    rtl=ROOT/'external/verilog-axis/rtl/axis_fifo.v'
    candidate_text='''// ENGINEERING CONTROLS ONLY; no LLM provenance.
// Native support is probed separately; Python results are auxiliary only.
ap_valid_only: assert property (@(posedge clk) disable iff (rst) (svalid && sready) |=> mvalid);
ap_stable: assert property (@(posedge clk) disable iff (rst) (mvalid && !mready) |=> (mvalid && $stable(mdata)));
'''
    (out/'initial_engineering_candidates.sva').write_text(candidate_text)
    config=dict(depths=[2,3,4],ram_pipeline=[0,2],development_seeds=[202610141,202610142],
                independent_test_seeds=[916211,916273],mutations=['correct','corrupt','duplicate_payload','drop'],
                source=str(rtl), source_sha256=sha(rtl), source_url='https://github.com/alexforencich/verilog-axis/blob/master/rtl/axis_fifo.v',
                source_provenance='existing vendored source; exact upstream commit unverified',
                obligations=OBLIGATIONS,handshake='accept iff valid && ready at pre-NBA rising edge',
                reset='synchronous active high; pending requests and queue contents cancelled',
                latency='buffered FIFO; variable latency under backpressure; no fixed next-cycle response obligation',
                capacity='RAM depth rounds up to a power of two; pipeline adds storage; do not assume DEPTH is total capacity',
                dedup_rule='one gap per mutation and violated obligation; depth/pipeline/seed/waveform are replications, not discoveries',
                historical_fifo_presented='unknown; these mutants are not a witness for the original presented defect',
                python_version=subprocess.run(['python3','--version'],capture_output=True,text=True).stdout.strip())
    write_json(out/'config.json',config)
    command(['iverilog','-V'],out,'iverilog_version')
    command(['git','rev-parse','HEAD'],out,'repository_version')
    # Explicit native SVA compile probe, no lowering and no assertion stripping.
    (out/'native_probe.sv').write_text('module probe(input clk,rst,a,b);\nap: assert property (@(posedge clk) disable iff (rst) a |=> b);\nendmodule\n')
    probe=command(['iverilog','-g2012','-s','probe','-o','probe.vvp','native_probe.sv'],out,'native_sva_probe')
    write_json(out/'native_sva_status.json',dict(compile_exit_code=probe['exit_code'],tool_support='unsupported' if probe['exit_code'] else 'requires_execution_validation',property_verdict='unknown',trigger_status='unavailable',scope='Icarus direct concurrent assertion probe; no restricted-checker substitution'))
    results=[]; paired=[]
    for split in ('development','independent_test'):
        if split=='independent_test':
            write_json(out/'freeze.json',dict(frozen_at_unix=time.time(),assertion_sha256=sha(out/'initial_engineering_candidates.sva'),
                runner_sha256=sha(Path(__file__)),status='engineering_candidate_freeze_no_LLM_refinement',
                test_access='independent schedules first generated after freeze; no candidate selection from their results',
                limitations='same generator distribution; not external validation; native SVA unavailable'))
        seeds=config['development_seeds' if split=='development' else 'independent_test_seeds']
        for depth in config['depths']:
            for pipeline in config['ram_pipeline']:
                for seed in seeds:
                    fixed=None
                    for mutant in config['mutations']:
                        result,trace=run_one(out,rtl,split,seed,depth,pipeline,mutant)
                        results.append(result)
                        if mutant=='correct': fixed=(result,trace)
                        else:
                            same_inputs=[{k:t[k] for k in ('cycle','rst','svalid','sready','sdata','mready')} for t in trace]==[{k:t[k] for k in ('cycle','rst','svalid','sready','sdata','mready')} for t in fixed[1]]
                            paired.append(dict(split=split,depth=depth,pipeline=pipeline,seed=seed,mutation=mutant,
                                same_legal_input_schedule=same_inputs and result['legality']=='legal' and fixed[0]['legality']=='legal',
                                witness=fixed[0]['obligation_verdict']=='no_violation_in_execution' and result['obligation_verdict']=='violation' and same_inputs,
                                violated_obligations=sorted({v['obligation'] for v in result['violations']}),
                                evidence=result['artifact_directory']+'/evidence.json'))
    write_json(out/'results.json',results)
    write_json(out/'paired_witnesses.json',paired)
    counts=collections.Counter((r['split'],r['mutation'],r['obligation_verdict']) for r in results)
    summary=dict(runs=len(results),paired_witnesses=sum(p['witness'] for p in paired),
                 unique_artificial_obligation_gaps=sorted({(p['mutation'],o) for p in paired if p['witness'] for o in p['violated_obligations']}),
                 illegal_runs=sum(r['legality']!='legal' for r in results),
                 native_sva_runs=0,model_calls=0,formal_runs=0,
                 coverage=dict(sum((collections.Counter(r['coverage']) for r in results if r['mutation']=='correct'),collections.Counter())),
                 counts=[dict(split=k[0],mutation=k[1],verdict=k[2],count=v) for k,v in sorted(counts.items())],
                 limitations=['No real LLM generation/refinement in this experiment.','Concurrent native SVA unsupported by installed Icarus; auxiliary predicate diagnostics are not native assertion results.','No original historical FIFO defect validated.','No formal proof.','Independent engineering test uses fresh seeds after freeze but same generator family.'])
    write_json(out/'summary.json',summary)
    with (out/'results.csv').open('w',newline='') as f:
        fields=['split','seed','depth_requested','ram_depth_actual','ram_pipeline','mutation','legality','obligation_verdict','compile_status','execution_status','native_sva_status','artifact_directory']
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(results)
    (out/'REPORT.md').write_text('# Complex FIFO RTL execution\n\n'+
        'Reuses vendored `axis_fifo.v`. Every output is aligned to an accepted input (`valid && ready`), with explicit reset cancellation. Depth 3 rounds to RAM depth 4; pipeline storage is additional.\n\n'+
        f'{summary["runs"]} RTL runs; {summary["paired_witnesses"]}/{len(paired)} same-input artificial-mutant contrast witnesses; {summary["illegal_runs"]} illegal/unknown stimulus runs.\n\n'+
        'Independent tests use seeds first generated after the engineering candidate freeze. No LLM-generated or refined final assertion is claimed. Native SVA probe fails with the installed Icarus version. All Python candidate checks are auxiliary diagnostics.\n\n'+
        'Evidence and waveforms: `runs/<split>/d<depth>_p<pipeline>_s<seed>/<mutation>/`. Queue oracle obligations, request/response cycles, data ordering, cancellation and latency are in `evidence.json`; actual port traces in `trace.json`; commands/logs and VCD retained.\n\n'+
        'Raw differences are never counted alone: a witness requires fixed oracle pass, mutant obligation violation and identical legal stimuli. Deduplication counts mutation/obligation pairs, not waveform variants. The original FIFO presented bug remains unknown.\n\n'+
        'Run: `python3 scripts/research_fifo_experiment.py`\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    main()
